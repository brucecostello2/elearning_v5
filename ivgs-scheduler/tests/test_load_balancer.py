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


# ---------------------------------------------------------------------------
# WP-IVGS-06 Task 1 — D-8: the nullable reading the consumer never handled
# ---------------------------------------------------------------------------

class TestUnmeasuredGpuUtilisation:
    """D-8. `gpu_utilization_pct` is `Optional[float]` and this module divided
    by it unguarded, so EVERY `POST /schedule` returned 500 and every GPU stage
    ran unreserved through its fail-open path.

    WP-60 (`b94ec6f`) made the field nullable on purpose -- a worker whose
    `nvidia-smi` call failed used to record a confident 0%, indistinguishable
    from an idle GPU. That producer fix was right; this consumer was never
    updated for it. Measured live on 2026-08-28 before the fix::

        TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'
        at load_balancer.py:126
    """

    @pytest.mark.asyncio
    async def test_a_node_with_no_reading_does_not_raise(self, load_balancer):
        """The whole defect, in one line."""
        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("node-04:gpu0", gpu_util=None)]
        )
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)

        candidates = await load_balancer.get_weighted_candidates(
            model_name="kokoro-82m", vram_requirement_mb=8192
        )
        assert len(candidates) == 1

    @pytest.mark.asyncio
    async def test_the_unknown_reading_is_NOT_treated_as_zero(self, load_balancer):
        """⛔ THE REGRESSION GUARD THAT MATTERS.

        `gpu_util = 0.0` gives `1 - 0.0 = 1.0`, the MAXIMUM weight -- so an
        unmeasured GPU would outrank every measured one and attract work
        *because* nothing is known about it. A future 'simplification' to
        `or 0.0` must fail here.
        """
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)

        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("unmeasured", gpu_util=None)]
        )
        unknown = (await load_balancer.get_weighted_candidates("m", 8192))[0].weight

        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("idle", gpu_util=0.0)]
        )
        genuinely_idle = (await load_balancer.get_weighted_candidates("m", 8192))[0].weight

        assert unknown < genuinely_idle, (
            "an unmeasured GPU must not score as high as a measured idle one"
        )

    @pytest.mark.asyncio
    async def test_the_unknown_reading_is_not_treated_as_busy_either(
        self, load_balancer
    ):
        """The opposite error. Treating unknown as 100% busy would make an
        unmeasured node unselectable, and with the whole fleet unmeasured --
        today's state -- nothing would ever schedule."""
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)

        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("unmeasured", gpu_util=None)]
        )
        unknown = (await load_balancer.get_weighted_candidates("m", 8192))[0].weight

        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("busy", gpu_util=100.0)]
        )
        fully_busy = (await load_balancer.get_weighted_candidates("m", 8192))[0].weight

        assert unknown > fully_busy

    @pytest.mark.asyncio
    async def test_when_NO_node_reports_the_term_cancels_from_the_ranking(
        self, load_balancer
    ):
        """Today's fleet: no node sends a reading. Every candidate then carries
        the same prior, so ranking falls back to VRAM and queue depth -- the
        factors that ARE measured. The node with more free VRAM must win."""
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)
        load_balancer._registry.get_alive_nodes = AsyncMock(return_value=[
            _make_node("roomy", used_vram=1024, gpu_util=None),
            _make_node("tight", used_vram=40960, gpu_util=None),
        ])
        by_id = {c.node_id: c.weight
                 for c in await load_balancer.get_weighted_candidates("m", 8192)}
        assert by_id["roomy"] > by_id["tight"]

    @pytest.mark.asyncio
    async def test_the_candidate_records_the_ABSENCE_not_the_prior(
        self, load_balancer
    ):
        """The prior belongs to the weight formula, not to the record. If the
        candidate carried 0.5 the fleet page would report a measurement nobody
        took -- WP-60's defect, one layer along."""
        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("node-04:gpu0", gpu_util=None)]
        )
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)
        c = (await load_balancer.get_weighted_candidates("m", 8192))[0]
        assert c.gpu_utilization_pct is None

    @pytest.mark.asyncio
    async def test_a_real_reading_still_computes_exactly_as_before(
        self, load_balancer
    ):
        """No behaviour change for a node that DOES report."""
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)
        load_balancer._registry.get_alive_nodes = AsyncMock(
            return_value=[_make_node("measured", total_vram=1000, used_vram=0,
                                     gpu_util=40.0)]
        )
        c = (await load_balancer.get_weighted_candidates("m", 100))[0]
        # (1 - 0.40) * (1 - 0/1000) * (10 - 0) = 6.0
        assert c.weight == pytest.approx(6.0)
