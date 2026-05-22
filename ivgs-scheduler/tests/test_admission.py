"""
IVGS v5 — Admission Control Tests
=====================================

Tests for the 4-check admission control system per §12.2 Table 12-2.

Test coverage:
- Check #1: Phase gate validation (valid/invalid transitions)
- Check #2: VRAM availability (sufficient/insufficient)
- Check #3: Concurrency limit (within/exceeded)
- Check #4: Circuit breaker (closed/open)
- Full 4-check pipeline pass/fail combinations
- Reservation release and cleanup
- Project state tracking
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from admission_control import (
    AdmissionController,
    ReservationReleaseResult,
    VALID_STAGE_TRANSITIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    """Simple in-memory Redis mock."""
    from test_scheduler import FakeRedis
    return FakeRedis()


@pytest.fixture
def mock_registry():
    registry = AsyncMock()
    return registry


@pytest.fixture
def mock_circuit_breaker():
    cb = AsyncMock()
    cb.is_open = AsyncMock(return_value=False)
    return cb


@pytest.fixture
def mock_concurrency():
    concurrency = AsyncMock()
    concurrency.can_accept = AsyncMock(return_value=True)
    concurrency.release_model_load = AsyncMock()
    return concurrency


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def admission(
    mock_registry, mock_circuit_breaker, mock_concurrency,
    fake_redis, mock_metrics
):
    return AdmissionController(
        registry=mock_registry,
        circuit_breaker=mock_circuit_breaker,
        concurrency=mock_concurrency,
        reservation_ttl_s=300,
        redis=fake_redis,
        metrics=mock_metrics,
    )


def _make_alive_nodes(count: int, vram_per_node: int = 49152):
    """Helper to create mock alive nodes."""
    nodes = []
    for i in range(count):
        node = MagicMock()
        node.node_id = f"node-{i + 2}:gpu0"
        node.gpu_index = 0
        node.total_vram_mb = vram_per_node
        node.used_vram_mb = 0
        node.gpu_utilization_pct = 0.0
        node.is_alive = True
        node.is_draining = False
        nodes.append(node)
    return nodes


# ---------------------------------------------------------------------------
# Check #1: Phase Gate Tests per §12.2
# ---------------------------------------------------------------------------

class TestPhaseGateCheck:
    """Test phase gate validation (Check #1 per §12.2)."""

    @pytest.mark.asyncio
    async def test_valid_stage_transition(
        self, admission, mock_registry, fake_redis
    ):
        """Test valid stage transition passes phase gate."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(1)

        # Set project at stage 2
        await fake_redis.set("sched:job_state:proj-1", "2")

        result = await admission.validate(
            job_id="job-1",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
            project_id="proj-1",
            stage=3,  # Stage 2 → 3 is valid
        )

        assert result.passed
        assert "phase_gate" in result.checks_passed

    @pytest.mark.asyncio
    async def test_invalid_stage_transition(
        self, admission, fake_redis
    ):
        """Test invalid stage transition fails with PhaseGateError."""
        # Set project at stage 2
        await fake_redis.set("sched:job_state:proj-1", "2")

        from main import PhaseGateError
        with pytest.raises(PhaseGateError, match="Invalid stage transition"):
            await admission.validate(
                job_id="job-1",
                model_name="FLUX.1 Dev",
                vram_requirement_mb=24576,
                project_id="proj-1",
                stage=7,  # Stage 2 → 7 is NOT valid
            )

    @pytest.mark.asyncio
    async def test_no_stage_skips_phase_gate(
        self, admission, mock_registry
    ):
        """Test that no stage/project skips phase gate check."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(1)

        result = await admission.validate(
            job_id="job-1",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
            project_id=None,
            stage=None,
        )

        assert result.passed

    def test_valid_transitions_complete(self):
        """Verify all valid stage transitions are defined per §6.1."""
        assert VALID_STAGE_TRANSITIONS[0] == {1}
        assert VALID_STAGE_TRANSITIONS[1] == {2}
        assert 3 in VALID_STAGE_TRANSITIONS[2]
        assert VALID_STAGE_TRANSITIONS[8] == set()  # Terminal


# ---------------------------------------------------------------------------
# Check #2: VRAM Availability Tests per §12.2
# ---------------------------------------------------------------------------

class TestVramAvailabilityCheck:
    """Test VRAM availability check (Check #2 per §12.2)."""

    @pytest.mark.asyncio
    async def test_sufficient_vram_passes(
        self, admission, mock_registry
    ):
        """Test sufficient VRAM passes check."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(1, 49152)

        result = await admission.validate(
            job_id="job-1",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
        )

        assert result.passed
        assert "vram_availability" in result.checks_passed

    @pytest.mark.asyncio
    async def test_insufficient_vram_fails(
        self, admission, mock_registry
    ):
        """Test insufficient VRAM raises NoCapacityError."""
        nodes = _make_alive_nodes(1, 16384)
        mock_registry.get_alive_nodes.return_value = nodes

        from main import NoCapacityError
        with pytest.raises(NoCapacityError, match="No GPU has sufficient VRAM"):
            await admission.validate(
                job_id="job-1",
                model_name="FLUX.1 Dev",
                vram_requirement_mb=24576,
            )

    @pytest.mark.asyncio
    async def test_no_alive_nodes_fails(
        self, admission, mock_registry
    ):
        """Test no alive nodes raises NoCapacityError."""
        mock_registry.get_alive_nodes.return_value = []

        from main import NoCapacityError
        with pytest.raises(NoCapacityError, match="No alive GPU nodes"):
            await admission.validate(
                job_id="job-1",
                model_name="FLUX.1 Dev",
                vram_requirement_mb=24576,
            )


# ---------------------------------------------------------------------------
# Check #3: Concurrency Limit Tests per §12.2
# ---------------------------------------------------------------------------

class TestConcurrencyLimitCheck:
    """Test concurrency limit check (Check #3 per §12.2)."""

    @pytest.mark.asyncio
    async def test_within_concurrency_limit(
        self, admission, mock_registry, mock_concurrency
    ):
        """Test passing when within concurrency limit."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(1)
        mock_concurrency.can_accept.return_value = True

        result = await admission.validate(
            job_id="job-1",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
        )

        assert "concurrency_limit" in result.checks_passed

    @pytest.mark.asyncio
    async def test_exceeds_concurrency_limit(
        self, admission, mock_registry, mock_concurrency
    ):
        """Test ConcurrencyLimitError when all GPUs at limit."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(2)
        mock_concurrency.can_accept.return_value = False  # All at limit

        from main import ConcurrencyLimitError
        with pytest.raises(ConcurrencyLimitError, match="concurrency limit"):
            await admission.validate(
                job_id="job-1",
                model_name="FLUX.1 Dev",
                vram_requirement_mb=24576,
            )


# ---------------------------------------------------------------------------
# Check #4: Circuit Breaker Tests per §12.2
# ---------------------------------------------------------------------------

class TestCircuitBreakerCheck:
    """Test circuit breaker check (Check #4 per §12.2)."""

    @pytest.mark.asyncio
    async def test_closed_circuit_passes(
        self, admission, mock_registry, mock_circuit_breaker
    ):
        """Test closed circuit breaker passes check."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(1)
        mock_circuit_breaker.is_open.return_value = False

        result = await admission.validate(
            job_id="job-1",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
        )

        assert "circuit_breaker" in result.checks_passed

    @pytest.mark.asyncio
    async def test_all_circuits_open_fails(
        self, admission, mock_registry, mock_circuit_breaker
    ):
        """Test all circuits open raises CircuitBreakerOpenError."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(2)
        mock_circuit_breaker.is_open.return_value = True  # All open

        from main import CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError, match="open circuit breakers"):
            await admission.validate(
                job_id="job-1",
                model_name="FLUX.1 Dev",
                vram_requirement_mb=24576,
            )


# ---------------------------------------------------------------------------
# Full Pipeline Tests
# ---------------------------------------------------------------------------

class TestFullAdmissionPipeline:
    """Test the full 4-check pipeline."""

    @pytest.mark.asyncio
    async def test_all_four_checks_pass(
        self, admission, mock_registry, mock_concurrency, mock_circuit_breaker
    ):
        """Test all 4 checks pass in sequence."""
        mock_registry.get_alive_nodes.return_value = _make_alive_nodes(2)
        mock_concurrency.can_accept.return_value = True
        mock_circuit_breaker.is_open.return_value = False

        result = await admission.validate(
            job_id="job-full",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
        )

        assert result.passed
        assert len(result.checks_passed) == 4
        assert result.checks_passed == [
            "phase_gate",
            "vram_availability",
            "concurrency_limit",
            "circuit_breaker",
        ]


# ---------------------------------------------------------------------------
# Reservation Release Tests
# ---------------------------------------------------------------------------

class TestReservationRelease:
    """Test reservation release and cleanup."""

    @pytest.mark.asyncio
    async def test_release_existing_reservation(
        self, admission, fake_redis, mock_registry, mock_concurrency
    ):
        """Test releasing an existing reservation frees VRAM."""
        # Create a mock reservation
        res_id = "res-test-release"
        res_key = f"sched:reservation:{res_id}"
        await fake_redis.hset(res_key, mapping={
            "reservation_id": res_id,
            "job_id": "job-release",
            "node_id": "node-02:gpu0",
            "gpu_index": "0",
            "vram_mb": "24576",
            "model_name": "FLUX.1 Dev",
        })
        await fake_redis.hset("gpu:node:node-02:gpu0", mapping={
            "used_vram_mb": "24576",
        })

        result = await admission.release_reservation(res_id)

        assert isinstance(result, ReservationReleaseResult)
        assert result.vram_freed_mb == 24576
        mock_registry.release_vram_usage.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_nonexistent_reservation(self, admission):
        """Test releasing non-existent reservation raises error."""
        from main import ReservationNotFoundError
        with pytest.raises(ReservationNotFoundError):
            await admission.release_reservation("res-nonexistent")


# ---------------------------------------------------------------------------
# Job State Tests
# ---------------------------------------------------------------------------

class TestJobState:
    """Test job state tracking for phase gate."""

    @pytest.mark.asyncio
    async def test_update_and_get_state(self, admission, fake_redis):
        """Test updating and retrieving job state."""
        await admission.update_job_state("proj-1", 5)
        state = await admission.get_job_state("proj-1")
        assert state == 5

    @pytest.mark.asyncio
    async def test_default_state_is_zero(self, admission, fake_redis):
        """Test default state for new project is 0."""
        state = await admission.get_job_state("proj-new")
        assert state == 0
