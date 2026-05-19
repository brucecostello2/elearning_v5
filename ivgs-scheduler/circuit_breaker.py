"""
IVGS v5 — Circuit Breaker
=============================

Per-node circuit breaker per §12.2 Table 12-2 Check #4.

Behavior:
- CLOSED (normal): All requests pass through.
- OPEN (tripped): >20% error rate in last 10 minutes → reject new jobs.
- HALF-OPEN (testing): After cool-down, allow a single test request.
  If test succeeds → CLOSED. If test fails → OPEN again.

State transitions:
    CLOSED → OPEN:    error_rate > 20% in sliding 10-min window
    OPEN → HALF_OPEN: cool_down_s elapsed (default: 60s)
    HALF_OPEN → CLOSED: test request succeeds
    HALF_OPEN → OPEN:   test request fails

Redis key structure:
- cb:state:{node_id}       — Current state string
- cb:errors:{node_id}      — Sorted set of error timestamps
- cb:successes:{node_id}   — Sorted set of success timestamps
- cb:opened_at:{node_id}   — Timestamp when circuit was opened
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Dict, Optional

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker States
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Per-node circuit breaker per §12.2.

    Monitors error rates per GPU node and opens the circuit when
    the error rate exceeds 20% in a 10-minute sliding window.
    This prevents scheduling jobs on unhealthy nodes.

    Args:
        redis: Redis connection for state persistence.
        window_s: Sliding window for error rate calculation (default: 600s).
        error_threshold: Error rate threshold to trip (default: 0.20).
        cool_down_s: Time before transitioning from OPEN to HALF_OPEN.
        min_requests: Minimum requests in window before evaluation.
        metrics: Prometheus metrics collector.
    """

    # Redis key prefixes
    STATE_PREFIX = "cb:state:"
    ERRORS_PREFIX = "cb:errors:"
    SUCCESSES_PREFIX = "cb:successes:"
    OPENED_AT_PREFIX = "cb:opened_at:"

    def __init__(
        self,
        redis: aioredis.Redis,
        window_s: int = 600,
        error_threshold: float = 0.20,
        cool_down_s: int = 60,
        min_requests: int = 5,
        metrics=None,
    ) -> None:
        self._redis = redis
        self._window_s = window_s
        self._error_threshold = error_threshold
        self._cool_down_s = cool_down_s
        self._min_requests = min_requests
        self._metrics = metrics

    async def is_open(self, node_id: str) -> bool:
        """
        Check if the circuit breaker is open for a node.

        Also handles the HALF_OPEN transition after cool-down.

        Args:
            node_id: Node identifier.

        Returns:
            True if circuit is OPEN (reject requests), False otherwise.
        """
        state = await self._get_state(node_id)

        if state == CircuitState.CLOSED:
            # Re-evaluate based on recent error rate
            is_tripped = await self._evaluate_error_rate(node_id)
            if is_tripped:
                await self._trip(node_id)
                return True
            return False

        if state == CircuitState.OPEN:
            # Check if cool-down has elapsed
            opened_at_str = await self._redis.get(
                f"{self.OPENED_AT_PREFIX}{node_id}"
            )
            if opened_at_str:
                opened_at = float(opened_at_str)
                elapsed = time.time() - opened_at
                if elapsed >= self._cool_down_s:
                    # Transition to HALF_OPEN
                    await self._set_state(node_id, CircuitState.HALF_OPEN)
                    logger.info(
                        "circuit_half_open",
                        node_id=node_id,
                        elapsed_s=round(elapsed, 1),
                    )
                    return False  # Allow test request
            return True

        if state == CircuitState.HALF_OPEN:
            # Allow a single test request
            return False

        return False

    async def record_success(self, node_id: str) -> None:
        """
        Record a successful request for a node.

        In HALF_OPEN state, a success transitions the circuit back to CLOSED.

        Args:
            node_id: Node identifier.
        """
        now = time.time()

        pipe = self._redis.pipeline()
        success_key = f"{self.SUCCESSES_PREFIX}{node_id}"
        pipe.zadd(success_key, {str(now): now})
        cutoff = now - self._window_s
        pipe.zremrangebyscore(success_key, "-inf", str(cutoff))
        await pipe.execute()

        state = await self._get_state(node_id)
        if state == CircuitState.HALF_OPEN:
            # Test request succeeded — close circuit
            await self._close(node_id)
            logger.info(
                "circuit_closed_after_test",
                node_id=node_id,
            )

    async def record_error(self, node_id: str) -> None:
        """
        Record an error for a node.

        In HALF_OPEN state, an error transitions the circuit back to OPEN.
        In CLOSED state, evaluates if error rate exceeds threshold.

        Args:
            node_id: Node identifier.
        """
        now = time.time()

        pipe = self._redis.pipeline()
        error_key = f"{self.ERRORS_PREFIX}{node_id}"
        pipe.zadd(error_key, {str(now): now})
        cutoff = now - self._window_s
        pipe.zremrangebyscore(error_key, "-inf", str(cutoff))
        await pipe.execute()

        state = await self._get_state(node_id)
        if state == CircuitState.HALF_OPEN:
            # Test request failed — re-open circuit
            await self._trip(node_id)
            logger.warning(
                "circuit_reopened_after_test",
                node_id=node_id,
            )
        elif state == CircuitState.CLOSED:
            # Check if we should trip
            is_tripped = await self._evaluate_error_rate(node_id)
            if is_tripped:
                await self._trip(node_id)

    async def get_state(self, node_id: str) -> str:
        """
        Get the current circuit breaker state string for a node.

        Args:
            node_id: Node identifier.

        Returns:
            State string: 'closed', 'open', or 'half_open'.
        """
        state = await self._get_state(node_id)
        return state.value

    async def get_error_rate(self, node_id: str) -> float:
        """
        Get the current error rate for a node in the sliding window.

        Args:
            node_id: Node identifier.

        Returns:
            Error rate as a float between 0.0 and 1.0.
        """
        now = time.time()
        cutoff = now - self._window_s

        error_count = await self._redis.zcount(
            f"{self.ERRORS_PREFIX}{node_id}", str(cutoff), "+inf"
        )
        success_count = await self._redis.zcount(
            f"{self.SUCCESSES_PREFIX}{node_id}", str(cutoff), "+inf"
        )

        total = error_count + success_count
        if total == 0:
            return 0.0

        return error_count / total

    async def reset(self, node_id: str) -> None:
        """
        Reset the circuit breaker for a node.

        Clears all error/success history and closes the circuit.

        Args:
            node_id: Node identifier.
        """
        pipe = self._redis.pipeline()
        pipe.delete(f"{self.STATE_PREFIX}{node_id}")
        pipe.delete(f"{self.ERRORS_PREFIX}{node_id}")
        pipe.delete(f"{self.SUCCESSES_PREFIX}{node_id}")
        pipe.delete(f"{self.OPENED_AT_PREFIX}{node_id}")
        await pipe.execute()

        if self._metrics:
            self._metrics.set_circuit_breaker_state(node_id, 0)

        logger.info("circuit_breaker_reset", node_id=node_id)

    async def get_all_states(self) -> Dict[str, str]:
        """
        Get circuit breaker states for all tracked nodes.

        Returns:
            Dict mapping node_id to state string.
        """
        # Scan for all state keys
        states: Dict[str, str] = {}
        async for key in self._redis.scan_iter(f"{self.STATE_PREFIX}*"):
            node_id = key.replace(self.STATE_PREFIX, "")
            state_str = await self._redis.get(key)
            if state_str:
                states[node_id] = state_str
        return states

    # --- Internal Methods ---

    async def _get_state(self, node_id: str) -> CircuitState:
        """Get the circuit breaker state from Redis."""
        state_key = f"{self.STATE_PREFIX}{node_id}"
        state_str = await self._redis.get(state_key)
        if state_str:
            try:
                return CircuitState(state_str)
            except ValueError:
                return CircuitState.CLOSED
        return CircuitState.CLOSED

    async def _set_state(self, node_id: str, state: CircuitState) -> None:
        """Set the circuit breaker state in Redis."""
        state_key = f"{self.STATE_PREFIX}{node_id}"
        await self._redis.set(state_key, state.value)

        if self._metrics:
            state_val = 1 if state == CircuitState.OPEN else 0
            self._metrics.set_circuit_breaker_state(node_id, state_val)

    async def _evaluate_error_rate(self, node_id: str) -> bool:
        """
        Evaluate if error rate exceeds threshold per §12.2.

        Returns True if >20% error rate in the last 10 minutes
        and minimum request count is met.
        """
        now = time.time()
        cutoff = now - self._window_s

        error_count = await self._redis.zcount(
            f"{self.ERRORS_PREFIX}{node_id}", str(cutoff), "+inf"
        )
        success_count = await self._redis.zcount(
            f"{self.SUCCESSES_PREFIX}{node_id}", str(cutoff), "+inf"
        )

        total = error_count + success_count

        # Don't trip on insufficient data
        if total < self._min_requests:
            return False

        error_rate = error_count / total
        return error_rate > self._error_threshold

    async def _trip(self, node_id: str) -> None:
        """Open the circuit breaker for a node."""
        now = time.time()
        await self._set_state(node_id, CircuitState.OPEN)
        await self._redis.set(
            f"{self.OPENED_AT_PREFIX}{node_id}", str(now)
        )

        error_rate = await self.get_error_rate(node_id)
        logger.warning(
            "circuit_breaker_tripped",
            node_id=node_id,
            error_rate=round(error_rate, 3),
            threshold=self._error_threshold,
            window_s=self._window_s,
        )

    async def _close(self, node_id: str) -> None:
        """Close the circuit breaker for a node."""
        pipe = self._redis.pipeline()
        pipe.set(f"{self.STATE_PREFIX}{node_id}", CircuitState.CLOSED.value)
        pipe.delete(f"{self.OPENED_AT_PREFIX}{node_id}")
        await pipe.execute()

        if self._metrics:
            self._metrics.set_circuit_breaker_state(node_id, 0)
