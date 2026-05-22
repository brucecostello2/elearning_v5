"""
IVGS v5 — Circuit Breaker Tests
===================================

Tests for the per-node circuit breaker per §12.2.

Test coverage:
- CLOSED → OPEN: error rate >20% in 10 min window
- OPEN → HALF_OPEN: after cool-down period
- HALF_OPEN → CLOSED: test request succeeds
- HALF_OPEN → OPEN: test request fails
- Error rate calculation with sliding window
- Minimum request count before evaluation
- Circuit breaker reset
- State persistence across queries
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from circuit_breaker import CircuitBreaker, CircuitState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    from test_scheduler import FakeRedis
    return FakeRedis()


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def circuit_breaker(fake_redis, mock_metrics):
    return CircuitBreaker(
        redis=fake_redis,
        window_s=600,  # 10 min per §12.2
        error_threshold=0.20,  # 20% per §12.2
        cool_down_s=60,
        min_requests=5,
        metrics=mock_metrics,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCircuitBreakerStates:
    """Test circuit breaker state transitions per §12.2."""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, circuit_breaker):
        """New node starts with CLOSED state."""
        state = await circuit_breaker.get_state("node-02:gpu0")
        assert state == "closed"

    @pytest.mark.asyncio
    async def test_stays_closed_under_threshold(self, circuit_breaker):
        """Circuit stays closed when error rate is under 20%."""
        node = "node-02:gpu0"

        # Record 8 successes and 1 error (11% error rate)
        for _ in range(8):
            await circuit_breaker.record_success(node)
        await circuit_breaker.record_error(node)

        is_open = await circuit_breaker.is_open(node)
        assert is_open is False

    @pytest.mark.asyncio
    async def test_trips_when_error_rate_exceeds_threshold(self, circuit_breaker):
        """Circuit opens when error rate >20% per §12.2."""
        node = "node-02:gpu0"

        # Record 3 successes and 3 errors (50% error rate)
        for _ in range(3):
            await circuit_breaker.record_success(node)
        for _ in range(3):
            await circuit_breaker.record_error(node)

        is_open = await circuit_breaker.is_open(node)
        assert is_open is True

    @pytest.mark.asyncio
    async def test_does_not_trip_below_min_requests(
        self, circuit_breaker
    ):
        """Circuit doesn't trip with fewer than min_requests."""
        node = "node-02:gpu0"

        # Only 2 requests (below min_requests=5)
        await circuit_breaker.record_error(node)
        await circuit_breaker.record_error(node)

        is_open = await circuit_breaker.is_open(node)
        assert is_open is False

    @pytest.mark.asyncio
    async def test_half_open_after_cool_down(
        self, circuit_breaker, fake_redis
    ):
        """Circuit transitions to HALF_OPEN after cool-down per §12.2."""
        node = "node-02:gpu0"

        # Trip the circuit
        for _ in range(3):
            await circuit_breaker.record_success(node)
        for _ in range(3):
            await circuit_breaker.record_error(node)

        # Verify it's open
        is_open = await circuit_breaker.is_open(node)
        assert is_open is True

        # Simulate cool-down elapsed by backdating opened_at
        opened_key = f"cb:opened_at:{node}"
        await fake_redis.set(opened_key, str(time.time() - 120))

        # Should now transition to HALF_OPEN and allow test request
        is_open = await circuit_breaker.is_open(node)
        assert is_open is False

        state = await circuit_breaker.get_state(node)
        assert state == "half_open"

    @pytest.mark.asyncio
    async def test_half_open_closes_on_success(
        self, circuit_breaker, fake_redis
    ):
        """Test request success in HALF_OPEN closes the circuit."""
        node = "node-02:gpu0"

        # Set state to HALF_OPEN
        await fake_redis.set(f"cb:state:{node}", CircuitState.HALF_OPEN.value)

        # Record a success
        await circuit_breaker.record_success(node)

        state = await circuit_breaker.get_state(node)
        assert state == "closed"

    @pytest.mark.asyncio
    async def test_half_open_reopens_on_error(
        self, circuit_breaker, fake_redis
    ):
        """Test request failure in HALF_OPEN reopens the circuit."""
        node = "node-02:gpu0"

        # Set state to HALF_OPEN
        await fake_redis.set(f"cb:state:{node}", CircuitState.HALF_OPEN.value)

        # Record an error
        await circuit_breaker.record_error(node)

        state = await circuit_breaker.get_state(node)
        assert state == "open"


class TestErrorRateCalculation:
    """Test error rate calculation with sliding window."""

    @pytest.mark.asyncio
    async def test_error_rate_calculation(self, circuit_breaker):
        """Test error rate is computed correctly."""
        node = "node-02:gpu0"

        # 7 successes, 3 errors = 30% error rate
        for _ in range(7):
            await circuit_breaker.record_success(node)
        for _ in range(3):
            await circuit_breaker.record_error(node)

        rate = await circuit_breaker.get_error_rate(node)
        assert abs(rate - 0.3) < 0.01

    @pytest.mark.asyncio
    async def test_zero_requests_returns_zero_rate(self, circuit_breaker):
        """No requests should return 0.0 error rate."""
        rate = await circuit_breaker.get_error_rate("node-new:gpu0")
        assert rate == 0.0


class TestCircuitBreakerReset:
    """Test circuit breaker reset."""

    @pytest.mark.asyncio
    async def test_reset_clears_all_state(
        self, circuit_breaker, fake_redis
    ):
        """Reset should clear all error/success history."""
        node = "node-02:gpu0"

        # Record some activity
        for _ in range(5):
            await circuit_breaker.record_error(node)

        # Reset
        await circuit_breaker.reset(node)

        state = await circuit_breaker.get_state(node)
        assert state == "closed"

        rate = await circuit_breaker.get_error_rate(node)
        assert rate == 0.0
