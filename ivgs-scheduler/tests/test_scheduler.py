"""
IVGS v5 — GPU Scheduler Engine Tests
========================================

Tests for GpuScheduler VRAM-aware bin-packing per §12.1.

Test coverage:
- First-fit allocation with VRAM sorting
- Warm-start preference (model already loaded)
- VRAM reservation creation with 5-min TTL
- Reservation extension on heartbeat
- No capacity error when fleet is full
- Multiple job scheduling with correct VRAM accounting
- Reservation cleanup after expiration
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from scheduler import GpuCandidate, GpuScheduler, ScheduleResult


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

class FakeRedis:
    """In-memory Redis mock for testing."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._sets: Dict[str, set] = {}
        self._sorted_sets: Dict[str, Dict[str, float]] = {}
        self._expiry: Dict[str, float] = {}

    def pipeline(self):
        return FakePipeline(self)

    async def hset(
        self,
        key: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        mapping: Optional[Dict] = None,
        **kwargs,
    ):
        """redis-py's real signature: ``hset(name, key, value, mapping=None)``.

        WP-60. This double accepted ONLY the ``mapping=`` form, so every
        production call written as ``hset(key, field, value)`` -- which is the
        documented redis-py call and what `release_vram_usage`,
        `drain_node`, `undrain_node` and `record_model_load` all use --
        raised TypeError inside the test suite while working perfectly against
        real Redis. A test double that rejects a legal call cannot exercise the
        code that makes it; several of the scheduler suite's standing failures
        are this, not the code under test.
        """
        if key not in self._data:
            self._data[key] = {}
        if field is not None:
            self._data[key][field] = value
        if mapping:
            self._data[key].update(mapping)
        self._data[key].update(kwargs)

    async def hget(self, key: str, field: str) -> Optional[str]:
        return self._data.get(key, {}).get(field)

    async def hgetall(self, key: str) -> Dict[str, str]:
        return self._data.get(key, {})

    async def hincrby(self, key: str, field: str, amount: int):
        if key not in self._data:
            self._data[key] = {}
        current = int(self._data[key].get(field, "0"))
        self._data[key][field] = str(current + amount)

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        self._data[key] = value

    async def get(self, key: str) -> Optional[str]:
        val = self._data.get(key)
        if isinstance(val, dict):
            return None
        return val

    async def incr(self, key: str) -> int:
        current = int(self._data.get(key) or 0) + 1
        self._data[key] = str(current)
        return current

    async def decr(self, key: str) -> int:
        current = int(self._data.get(key) or 0) - 1
        self._data[key] = str(current)
        return current

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def delete(self, key: str):
        self._data.pop(key, None)

    async def sadd(self, key: str, *members):
        if key not in self._sets:
            self._sets[key] = set()
        self._sets[key].update(members)

    async def srem(self, key: str, *members):
        if key in self._sets:
            self._sets[key] -= set(members)

    async def smembers(self, key: str) -> set:
        """A COPY, as real redis-py returns.

        WP-60: this handed back the live set object, so any caller that
        iterated the result while removing members -- which
        `cleanup_expired_reservations` and `release_node_reservations` both do
        -- got "Set changed size during iteration" in the suite and correct
        behaviour in production."""
        return set(self._sets.get(key, set()))

    async def scard(self, key: str) -> int:
        return len(self._sets.get(key, set()))

    async def sismember(self, key: str, member: str) -> bool:
        return member in self._sets.get(key, set())

    async def zadd(self, key: str, mapping: Dict[str, float]):
        if key not in self._sorted_sets:
            self._sorted_sets[key] = {}
        self._sorted_sets[key].update(mapping)

    async def zremrangebyscore(self, key: str, min_score, max_score):
        """Drop members whose score falls in [min, max].

        WP-IVGS-06. THE FAKE WAS MISSING THIS AND IT BLOCKED THE WHOLE FILE:
        `LoadBalancer._record_weight_metrics` (`load_balancer.py:304`) trims the
        weight time-series on every call, so EVERY test that reached
        `get_weighted_candidates` with at least one candidate died on
        `AttributeError: 'FakePipeline' object has no attribute
        'zremrangebyscore'` -- four pre-existing tests plus this package's.

        Implemented, not stubbed: it actually removes, so a test can assert the
        trim happened.
        """
        def _bound(v, default):
            if v in ("-inf", "+inf", "inf"):
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        lo = _bound(min_score, float("-inf"))
        hi = _bound(max_score, float("inf"))
        bucket = self._sorted_sets.get(key)
        if not bucket:
            return 0
        doomed = [m for m, score in bucket.items() if lo <= score <= hi]
        for m in doomed:
            del bucket[m]
        return len(doomed)

    async def zrangebyscore(self, key: str, min_score, max_score, **kwargs):
        """Members whose score falls in [min, max]. Used by
        `GpuRegistry.get_alive_nodes` to find nodes heartbeating since the
        stale cutoff."""
        def _bound(v, default):
            if v in ("-inf", "+inf", "inf"):
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        lo = _bound(min_score, float("-inf"))
        hi = _bound(max_score, float("inf"))
        ss = self._sorted_sets.get(key, {})
        return [m for m, score in sorted(ss.items(), key=lambda kv: kv[1])
                if lo <= score <= hi]

    async def zrange(self, key: str, start: int, stop: int, **kwargs):
        ss = self._sorted_sets.get(key, {})
        items = sorted(ss.items(), key=lambda x: x[1])
        if stop == -1:
            return [k for k, v in items[start:]]
        return [k for k, v in items[start:stop + 1]]

    async def zcard(self, key: str) -> int:
        return len(self._sorted_sets.get(key, {}))

    async def expire(self, key: str, seconds: int):
        self._expiry[key] = time.time() + seconds

    async def ping(self):
        return True


class FakePipeline:
    """Fake Redis pipeline."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._commands: List = []

    def hset(self, key, field=None, value=None, mapping=None, **kwargs):
        """Mirrors redis-py's ``hset(name, key, value, mapping=None)``."""
        self._commands.append(("hset", key, field, value, mapping, kwargs))
        return self

    def expire(self, key, seconds):
        self._commands.append(("expire", key, seconds))
        return self

    def sadd(self, key, *members):
        self._commands.append(("sadd", key, members))
        return self

    def srem(self, key, *members):
        self._commands.append(("srem", key, members))
        return self

    def set(self, key, value, ex=None):
        self._commands.append(("set", key, value, ex))
        return self

    def incr(self, key):
        self._commands.append(("incr", key))
        return self

    def decr(self, key):
        self._commands.append(("decr", key))
        return self

    def delete(self, key):
        self._commands.append(("delete", key))
        return self

    def zadd(self, key, mapping):
        self._commands.append(("zadd", key, mapping))
        return self

    def zremrangebyscore(self, key, min_score, max_score):
        self._commands.append(("zremrangebyscore", key, min_score, max_score))
        return self

    async def execute(self):
        for cmd in self._commands:
            op = cmd[0]
            if op == "hset":
                await self._redis.hset(
                    cmd[1], field=cmd[2], value=cmd[3], mapping=cmd[4], **cmd[5]
                )
            elif op == "incr":
                await self._redis.incr(cmd[1])
            elif op == "decr":
                await self._redis.decr(cmd[1])
            elif op == "expire":
                await self._redis.expire(cmd[1], cmd[2])
            elif op == "sadd":
                await self._redis.sadd(cmd[1], *cmd[2])
            elif op == "srem":
                await self._redis.srem(cmd[1], *cmd[2])
            elif op == "set":
                await self._redis.set(cmd[1], cmd[2], ex=cmd[3] if len(cmd) > 3 else None)
            elif op == "delete":
                await self._redis.delete(cmd[1])
            elif op == "zadd":
                await self._redis.zadd(cmd[1], cmd[2])
            elif op == "zremrangebyscore":
                await self._redis.zremrangebyscore(cmd[1], cmd[2], cmd[3])
        self._commands.clear()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def mock_registry():
    registry = AsyncMock()
    registry.get_alive_nodes = AsyncMock(return_value=[])
    registry.get_all_nodes = AsyncMock(return_value=[])
    registry.add_vram_usage = AsyncMock()
    registry.release_vram_usage = AsyncMock()
    registry.get_node_jobs = AsyncMock(return_value=[])
    registry.add_node_job = AsyncMock()
    registry.remove_node_job = AsyncMock()
    return registry


@pytest.fixture
def mock_admission():
    admission = AsyncMock()
    admission.validate = AsyncMock()
    return admission


@pytest.fixture
def mock_load_balancer():
    lb = AsyncMock()
    lb.get_weighted_candidates = AsyncMock(return_value=[])
    return lb


@pytest.fixture
def mock_concurrency():
    concurrency = AsyncMock()
    concurrency.can_accept = AsyncMock(return_value=True)
    concurrency.record_model_load = AsyncMock()
    concurrency.release_model_load = AsyncMock()
    return concurrency


@pytest.fixture
def mock_priority_queue():
    pq = AsyncMock()
    pq.resolve_priority = AsyncMock(return_value="normal")
    return pq


@pytest.fixture
def mock_circuit_breaker():
    cb = AsyncMock()
    cb.is_open = AsyncMock(return_value=False)
    return cb


@pytest.fixture
def mock_metrics():
    metrics = MagicMock()
    metrics.set_vram_used = MagicMock()
    metrics.set_queue_depth = MagicMock()
    metrics.observe_wait_time = MagicMock()
    return metrics


@pytest.fixture
def scheduler(
    fake_redis,
    mock_registry,
    mock_admission,
    mock_load_balancer,
    mock_concurrency,
    mock_priority_queue,
    mock_circuit_breaker,
    mock_metrics,
):
    return GpuScheduler(
        registry=mock_registry,
        admission=mock_admission,
        load_balancer=mock_load_balancer,
        concurrency=mock_concurrency,
        priority_queue=mock_priority_queue,
        circuit_breaker=mock_circuit_breaker,
        redis=fake_redis,
        metrics=mock_metrics,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGpuSchedulerFirstFit:
    """Test first-fit VRAM bin-packing allocation per §12.1."""

    @pytest.mark.asyncio
    async def test_schedule_job_success(
        self, scheduler, mock_load_balancer, mock_circuit_breaker
    ):
        """Test successful job scheduling with first-fit allocation."""
        candidate = GpuCandidate(
            node_id="node-02:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=0,
            available_vram_mb=49152,
            gpu_utilization_pct=0.0,
            has_model_loaded=False,
            weight=1.0,
        )
        mock_load_balancer.get_weighted_candidates.return_value = [candidate]
        mock_circuit_breaker.is_open.return_value = False

        result = await scheduler.schedule_job(
            job_id="test-job-1",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
            estimated_duration_s=300,
            priority="normal",
        )

        assert isinstance(result, ScheduleResult)
        assert result.node_id == "node-02:gpu0"
        assert result.gpu_index == 0
        assert result.vram_reserved_mb == 24576
        assert result.reservation_id.startswith("res-")

    @pytest.mark.asyncio
    async def test_schedule_prefers_warm_start(
        self, scheduler, mock_load_balancer, mock_circuit_breaker
    ):
        """Test that scheduler prefers GPUs with model already loaded per §12.1."""
        cold_gpu = GpuCandidate(
            node_id="node-02:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=0,
            available_vram_mb=49152,
            gpu_utilization_pct=0.0,
            has_model_loaded=False,
            weight=1.0,
        )
        warm_gpu = GpuCandidate(
            node_id="node-03:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=10000,
            available_vram_mb=39152,
            gpu_utilization_pct=20.0,
            has_model_loaded=True,
            weight=0.8,
        )
        mock_load_balancer.get_weighted_candidates.return_value = [
            cold_gpu, warm_gpu
        ]
        mock_circuit_breaker.is_open.return_value = False

        result = await scheduler.schedule_job(
            job_id="test-warm",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
            estimated_duration_s=300,
        )

        # Warm GPU should be preferred
        assert result.node_id == "node-03:gpu0"

    @pytest.mark.asyncio
    async def test_schedule_sorts_by_available_vram(
        self, scheduler, mock_load_balancer, mock_circuit_breaker
    ):
        """Test GPUs sorted by available VRAM descending for first-fit."""
        small_gpu = GpuCandidate(
            node_id="node-02:gpu0",
            gpu_index=0,
            gpu_model="RTX 4090",
            total_vram_mb=24576,
            used_vram_mb=10000,
            available_vram_mb=14576,
            gpu_utilization_pct=40.0,
            has_model_loaded=False,
            weight=0.5,
        )
        large_gpu = GpuCandidate(
            node_id="node-03:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=0,
            available_vram_mb=49152,
            gpu_utilization_pct=0.0,
            has_model_loaded=False,
            weight=1.0,
        )
        mock_load_balancer.get_weighted_candidates.return_value = [
            small_gpu, large_gpu
        ]
        mock_circuit_breaker.is_open.return_value = False

        result = await scheduler.schedule_job(
            job_id="test-sort",
            model_name="CogVideoX 5B",
            vram_requirement_mb=16384,
            estimated_duration_s=600,
        )

        # Large GPU should be selected (more available VRAM)
        assert result.node_id == "node-03:gpu0"

    @pytest.mark.asyncio
    async def test_schedule_no_capacity_error(
        self, scheduler, mock_load_balancer
    ):
        """Test NoCapacityError when no GPU can satisfy VRAM requirement."""
        mock_load_balancer.get_weighted_candidates.return_value = []

        with pytest.raises(Exception, match="No GPU nodes available"):
            await scheduler.schedule_job(
                job_id="test-fail",
                model_name="Large Model",
                vram_requirement_mb=80000,
                estimated_duration_s=300,
            )

    @pytest.mark.asyncio
    async def test_schedule_skips_open_circuit_breaker(
        self, scheduler, mock_load_balancer, mock_circuit_breaker, mock_concurrency
    ):
        """Test that scheduler skips GPUs with open circuit breakers."""
        open_gpu = GpuCandidate(
            node_id="node-02:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=0,
            available_vram_mb=49152,
            gpu_utilization_pct=0.0,
            has_model_loaded=False,
            weight=1.0,
        )
        healthy_gpu = GpuCandidate(
            node_id="node-03:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=20000,
            available_vram_mb=29152,
            gpu_utilization_pct=40.0,
            has_model_loaded=False,
            weight=0.6,
        )
        mock_load_balancer.get_weighted_candidates.return_value = [
            open_gpu, healthy_gpu
        ]
        # Circuit breaker open for node-02, closed for node-03
        mock_circuit_breaker.is_open.side_effect = [True, False]
        mock_concurrency.can_accept.return_value = True

        result = await scheduler.schedule_job(
            job_id="test-cb",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
            estimated_duration_s=300,
        )

        assert result.node_id == "node-03:gpu0"


class TestVramReservation:
    """Test VRAM reservation creation and management."""

    @pytest.mark.asyncio
    async def test_reservation_created_with_ttl(
        self, scheduler, mock_load_balancer, mock_circuit_breaker, fake_redis
    ):
        """Test that reservations are created with 5-minute TTL per §12.2."""
        candidate = GpuCandidate(
            node_id="node-02:gpu0",
            gpu_index=0,
            gpu_model="RTX 5000 Pro",
            total_vram_mb=49152,
            used_vram_mb=0,
            available_vram_mb=49152,
            gpu_utilization_pct=0.0,
            has_model_loaded=False,
            weight=1.0,
        )
        mock_load_balancer.get_weighted_candidates.return_value = [candidate]

        result = await scheduler.schedule_job(
            job_id="test-ttl",
            model_name="FLUX.1 Dev",
            vram_requirement_mb=24576,
            estimated_duration_s=300,
        )

        # Verify reservation was stored
        reservation = await scheduler.get_reservation(result.reservation_id)
        assert reservation is not None
        assert reservation.vram_mb == 24576
        assert reservation.node_id == "node-02:gpu0"

    @pytest.mark.asyncio
    async def test_reservation_extension(
        self, scheduler, fake_redis
    ):
        """Test reservation TTL extension on heartbeat."""
        # Manually create a reservation
        res = await scheduler._create_reservation(
            job_id="test-extend",
            node_id="node-02:gpu0",
            gpu_index=0,
            model_name="FLUX.1 Dev",
            vram_mb=24576,
            estimated_duration_s=300,
        )

        # Extend the reservation
        extended = await scheduler.extend_reservation(res.reservation_id)
        assert extended is True

        # Non-existent reservation
        extended = await scheduler.extend_reservation("res-nonexistent")
        assert extended is False

    @pytest.mark.asyncio
    async def test_get_active_reservations(
        self, scheduler, fake_redis
    ):
        """Test listing all active reservations."""
        # Create multiple reservations
        for i in range(3):
            await scheduler._create_reservation(
                job_id=f"test-list-{i}",
                node_id="node-02:gpu0",
                gpu_index=0,
                model_name="FLUX.1 Dev",
                vram_mb=8192,
                estimated_duration_s=60,
            )

        reservations = await scheduler.get_active_reservations()
        assert len(reservations) == 3


class TestJobReservationMapping:
    """Test job-to-reservation mapping."""

    @pytest.mark.asyncio
    async def test_job_reservation_lookup(self, scheduler, fake_redis):
        """Test looking up reservation ID by job ID."""
        res = await scheduler._create_reservation(
            job_id="test-lookup",
            node_id="node-02:gpu0",
            gpu_index=0,
            model_name="FLUX.1 Dev",
            vram_mb=24576,
            estimated_duration_s=300,
        )

        found_id = await scheduler.get_job_reservation("test-lookup")
        assert found_id == res.reservation_id

    @pytest.mark.asyncio
    async def test_missing_job_reservation(self, scheduler, fake_redis):
        """Test lookup for non-existent job returns None."""
        found = await scheduler.get_job_reservation("nonexistent-job")
        assert found is None
