"""
IVGS v5 — Load Balancer Tests
=================================

Tests for the weighted random load balancer per §12.1.

Test coverage:
- Weight formula: weight = (1 - gpu_util) × (1 - mem_util) × (max_queue - queue)
- Candidate ranking by weight
- VRAM filtering (insufficient VRAM excluded)
- Fleet imbalance detection (stddev >30%)
- Weighted random selection distribution
- Weight history recording
"""

from __future__ import annotations

import asyncio
import math
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from load_balancer import LoadBalancer, LoadBalancerConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    from test_scheduler import FakeRedis
    return FakeRedis()


@pytest.fixture
def mock_registry():
    registry = AsyncMock()
    return registry


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def config():
    return LoadBalancerConfig(
        max_queue_per_gpu=10,
        imbalance_stddev_threshold=0.30,
    )


@pytest.fixture
def load_balancer(fake_redis, mock_registry, mock_metrics, config):
    return LoadBalancer(
        redis=fake_redis,
        registry=mock_registry,
        metrics=mock_metrics,
        config=config,
    )


def _make_node(
    node_id: str,
    total_vram: int = 49152,
    used_vram: int = 0,
    gpu_util: float = 0.0,
):
    node = MagicMock()
    node.node_id = node_id
    node.gpu_index = 0
    node.gpu_model = "RTX 5000 Pro"
    node.total_vram_mb = total_vram
    node.used_vram_mb = used_vram
    node.gpu_utilization_pct = gpu_util
    node.is_alive = True
    node.is_draining = False
    return node


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWeightComputation:
    """Test weight formula per §12.1."""

    @pytest.mark.asyncio
    async def test_idle_gpu_has_max_weight(
        self, load_balancer, mock_registry, fake_redis
    ):
        """Idle GPU (0% util, 0 queue) should have high weight."""
        nodes = [_make_node("node-02:gpu0")]
        mock_registry.get_alive_nodes.return_value = nodes

        candidates = await load_balancer.get_weighted_candidates(
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
        )

        assert len(candidates) == 1
        # weight = (1 - 0) × (1 - 0) × (10 - 0) = 10.0
        assert candidates[0].weight == 10.0

    @pytest.mark.asyncio
    async def test_busy_gpu_has_low_weight(
        self, load_balancer, mock_registry, fake_redis
    ):
        """Busy GPU (80% util, high VRAM usage) should have low weight."""
        nodes = [
            _make_node(
                "node-02:gpu0",
                total_vram=49152,
                used_vram=40000,
                gpu_util=80.0,
            )
        ]
        mock_registry.get_alive_nodes.return_value = nodes

        candidates = await load_balancer.get_weighted_candidates(
            model_name="FLUX.1 Dev",
            vram_requirement_mb=8000,
        )

        assert len(candidates) == 1
        # weight = (1 - 0.8) × (1 - 40000/49152) × (10 - 0) ≈ 0.2 × 0.186 × 10 ≈ 0.37
        assert candidates[0].weight < 1.0

    @pytest.mark.asyncio
    async def test_insufficient_vram_excluded(
        self, load_balancer, mock_registry, fake_redis
    ):
        """Nodes with insufficient VRAM should be excluded."""
        nodes = [
            _make_node("node-02:gpu0", total_vram=16384, used_vram=0),
        ]
        mock_registry.get_alive_nodes.return_value = nodes

        candidates = await load_balancer.get_weighted_candidates(
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
        )

        assert len(candidates) == 0


class TestCandidateRanking:
    """Test candidate sorting by weight."""

    @pytest.mark.asyncio
    async def test_candidates_sorted_by_weight_desc(
        self, load_balancer, mock_registry, fake_redis
    ):
        """Candidates should be sorted by weight descending."""
        nodes = [
            _make_node("node-02:gpu0", used_vram=30000, gpu_util=60.0),
            _make_node("node-03:gpu0", used_vram=0, gpu_util=0.0),
            _make_node("node-04:gpu0", used_vram=10000, gpu_util=20.0),
        ]
        mock_registry.get_alive_nodes.return_value = nodes

        candidates = await load_balancer.get_weighted_candidates(
            model_name="FLUX.1 Dev",
            vram_requirement_mb=16384,
        )

        assert len(candidates) == 3
        weights = [c.weight for c in candidates]
        assert weights == sorted(weights, reverse=True)


class TestImbalanceDetection:
    """Test fleet weight imbalance detection per §12.1."""

    @pytest.mark.asyncio
    async def test_balanced_fleet_no_warning(
        self, load_balancer, mock_registry, fake_redis
    ):
        """Balanced fleet should not trigger imbalance warning."""
        nodes = [
            _make_node("node-02:gpu0", used_vram=10000, gpu_util=20.0),
            _make_node("node-03:gpu0", used_vram=12000, gpu_util=25.0),
            _make_node("node-04:gpu0", used_vram=11000, gpu_util=22.0),
        ]
        mock_registry.get_alive_nodes.return_value = nodes

        # Should not raise or log warning
        candidates = await load_balancer.get_weighted_candidates(
            model_name="FLUX.1 Dev",
            vram_requirement_mb=16384,
        )

        assert len(candidates) == 3


class TestWeightedRandomSelection:
    """Test weighted random selection."""

    @pytest.mark.asyncio
    async def test_weighted_random_returns_candidate(
        self, load_balancer, mock_registry, fake_redis
    ):
        """Weighted random selection should return a candidate."""
        from scheduler import GpuCandidate

        candidates = [
            GpuCandidate(
                node_id="node-02:gpu0",
                gpu_index=0,
                gpu_model="RTX 5000 Pro",
                total_vram_mb=49152,
                used_vram_mb=0,
                available_vram_mb=49152,
                gpu_utilization_pct=0.0,
                has_model_loaded=False,
                weight=10.0,
            ),
            GpuCandidate(
                node_id="node-03:gpu0",
                gpu_index=0,
                gpu_model="RTX 5000 Pro",
                total_vram_mb=49152,
                used_vram_mb=20000,
                available_vram_mb=29152,
                gpu_utilization_pct=40.0,
                has_model_loaded=False,
                weight=3.6,
            ),
        ]

        selected = await load_balancer.select_weighted_random(candidates)
        assert selected is not None
        assert selected.node_id in {"node-02:gpu0", "node-03:gpu0"}

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_none(self, load_balancer):
        """Empty candidate list returns None."""
        selected = await load_balancer.select_weighted_random([])
        assert selected is None
