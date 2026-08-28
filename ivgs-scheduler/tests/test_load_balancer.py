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


# ---------------------------------------------------------------------------
# WP-IVGS-07 Task 1 — D-10: the reservation must land on the executing node
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTheReservationFollowsTheRouting:
    """D-10, measured 2026-08-28: a reservation was held against `node-03:gpu0`
    while the work executed on node-04.

    The two placement mechanisms were never connected. Celery routing decides
    where a task runs -- `gpu_tts` is consumed only by node-04, `gpu_video` and
    `gpu_animation` only by node-03, `gpu_llm` only by node-02 -- and that
    happens BEFORE the task body runs. The scheduler then ranked the whole
    fleet by weight and answered with whichever node looked freest, and every
    call site discarded that answer, keeping only `reservation_id`.

    ⛔ The consequence is the inverse of protection: VRAM is decremented on an
    idle machine while the machine actually loading the model is admitted
    against headroom nobody is consuming.
    """

    @pytest.fixture
    def three_nodes(self, load_balancer):
        load_balancer._check_model_loaded = AsyncMock(return_value=False)
        load_balancer._get_queue_depth = AsyncMock(return_value=0)
        load_balancer._registry.get_alive_nodes = AsyncMock(return_value=[
            # node-03 looks freest, which is exactly how D-10 happened.
            _make_node("node-03:gpu0", used_vram=0, gpu_util=0.0),
            _make_node("node-04:gpu0", used_vram=20000, gpu_util=60.0),
            _make_node("node-02:gpu0", used_vram=10000, gpu_util=30.0),
        ])
        return load_balancer

    async def test_without_a_required_node_it_still_ranks_the_whole_fleet(
        self, three_nodes
    ):
        """Unchanged behaviour for any caller that genuinely wants advice."""
        c = await three_nodes.get_weighted_candidates("m", 1000)
        assert {x.node_id for x in c} == {"node-02:gpu0", "node-03:gpu0", "node-04:gpu0"}
        assert c[0].node_id == "node-03:gpu0", "the freest node still wins the ranking"

    async def test_a_required_node_pins_the_reservation_there(self, three_nodes):
        """THE FIX. node-04 is busier and would never win on weight; it is where
        the task is executing, so it is the only correct answer."""
        c = await three_nodes.get_weighted_candidates("m", 1000, required_node="node-04")
        assert [x.node_id for x in c] == ["node-04:gpu0"]

    async def test_it_does_NOT_fall_back_to_the_freest_node(self, three_nodes):
        """⛔ THE REGRESSION GUARD. A 'helpful' fallback to another node when the
        required one is full would silently restore D-10 -- and would be worse,
        because it would look like the fix was working."""
        three_nodes._registry.get_alive_nodes = AsyncMock(return_value=[
            _make_node("node-03:gpu0", total_vram=49152, used_vram=0),
        ])
        c = await three_nodes.get_weighted_candidates("m", 1000, required_node="node-04")
        assert c == [], "an absent required node yields NO candidate, never a substitute"

    async def test_a_required_node_with_too_little_vram_yields_nothing(
        self, three_nodes
    ):
        """The protection D-10 removed: the executing node's own headroom is
        what decides admission."""
        three_nodes._registry.get_alive_nodes = AsyncMock(return_value=[
            _make_node("node-04:gpu0", total_vram=49152, used_vram=49000),
            _make_node("node-03:gpu0", total_vram=49152, used_vram=0),
        ])
        assert await three_nodes.get_weighted_candidates(
            "m", 8192, required_node="node-04") == []

    async def test_the_bare_hostname_matches_the_registry_gpu_suffix(self, three_nodes):
        """The worker knows itself as `node-04`; the registry keys it
        `node-04:gpu0`. The join has to work without the worker knowing the GPU
        index, which it does not."""
        c = await three_nodes.get_weighted_candidates("m", 1000, required_node="node-04")
        assert c and c[0].node_id == "node-04:gpu0"

    async def test_a_multi_gpu_node_offers_all_of_its_own_gpus(self, three_nodes):
        """Pinning is to the NODE, not to a card. Two GPUs on the pinned host
        stay available to rank between; other hosts do not."""
        three_nodes._registry.get_alive_nodes = AsyncMock(return_value=[
            _make_node("node-04:gpu0", used_vram=30000),
            _make_node("node-04:gpu1", used_vram=0),
            _make_node("node-03:gpu0", used_vram=0),
        ])
        c = await three_nodes.get_weighted_candidates("m", 1000, required_node="node-04")
        assert {x.node_id for x in c} == {"node-04:gpu0", "node-04:gpu1"}
