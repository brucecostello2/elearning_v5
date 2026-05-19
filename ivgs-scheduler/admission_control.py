"""
IVGS v5 — Admission Controller
==================================

4-check admission control system per §12.2 Table 12-2.

Check sequence:
1. Phase Gate Check: Validates job state machine — job must be in a valid
   state to advance to requested stage. Prevents out-of-order execution.
   Failure: Reject with 409 Conflict (PhaseGateError).

2. VRAM Availability Check: Queries gpu_nodes for nodes with sufficient
   available VRAM. Available VRAM = total_vram_mb − sum of active reservations.
   Failure: Reject with NoCapacityError; queue for retry.

3. Concurrency Limit Check: Enforces per-node maximum parallel tasks
   (configurable; default: 1 video gen job per GPU). Prevents VRAM fragmentation.
   Failure: Reject; caller retries via backoff.

4. Circuit Breaker Check: If the target GPU has >20% error rate in the past
   10 minutes, the circuit is open. New jobs rejected and routed to
   alternative GPU; if all open, DLQ.
   Failure: Route to alternative GPU; if all open, DLQ.

Successful admission results in a gpu_reservations record with 5-minute TTL.
Workers must call PUT /heartbeat within 5 minutes to keep the reservation active;
expired reservations are automatically released.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdmissionResult:
    """Result of successful admission control."""

    passed: bool
    checks_passed: List[str]
    node_id: Optional[str] = None
    gpu_index: Optional[int] = None
    message: str = ""


@dataclass(frozen=True)
class ReservationReleaseResult:
    """Result of releasing a VRAM reservation."""

    reservation_id: str
    node_id: str
    gpu_index: int
    vram_freed_mb: int


# ---------------------------------------------------------------------------
# Valid Pipeline Stage Transitions per §6.1
# ---------------------------------------------------------------------------

# Maps current stage → set of valid next stages
VALID_STAGE_TRANSITIONS: Dict[int, Set[int]] = {
    0: {1},           # Initial → Stage 1 (Storyboard)
    1: {2},           # Stage 1 → Stage 2 (Prompt Enhancement)
    2: {3, 4},        # Stage 2 → Stage 3 (Images) or Stage 4 (Voice)
    3: {4, 5, 6},     # Stage 3 → Stage 4, 5, or 6
    4: {3, 5, 6},     # Stage 4 → Stage 3, 5, or 6
    5: {6},           # Stage 5 → Stage 6 (Talking Head)
    6: {7},           # Stage 6 → Stage 7 (Draft Composition)
    7: {8},           # Stage 7 → Stage 8 (Final Render)
    8: set(),         # Stage 8 is terminal
}


# ---------------------------------------------------------------------------
# Admission Controller
# ---------------------------------------------------------------------------

class AdmissionController:
    """
    4-check admission control system per §12.2.

    Performs sequential validation of:
    1. Phase gate (state machine)
    2. VRAM availability
    3. Concurrency limits
    4. Circuit breaker state

    Args:
        registry: GPU node registry for node queries.
        circuit_breaker: Circuit breaker for error rate checks.
        concurrency: Model concurrency manager.
        reservation_ttl_s: VRAM reservation TTL (default: 300s per §12.2).
        redis: Redis connection for state.
        metrics: Prometheus metrics collector.
    """

    # Redis key prefixes
    RESERVATION_KEY_PREFIX = "sched:reservation:"
    RESERVATION_INDEX_KEY = "sched:reservations:index"
    NODE_RESERVATIONS_PREFIX = "sched:node_reservations:"
    JOB_STATE_PREFIX = "sched:job_state:"

    # Default per-GPU concurrency limit per §12.2 Check #3
    DEFAULT_MAX_PARALLEL_PER_GPU = 1

    def __init__(
        self,
        registry,
        circuit_breaker,
        concurrency,
        reservation_ttl_s: int = 300,
        redis: Optional[aioredis.Redis] = None,
        metrics=None,
        max_parallel_per_gpu: int = DEFAULT_MAX_PARALLEL_PER_GPU,
    ) -> None:
        self._registry = registry
        self._circuit_breaker = circuit_breaker
        self._concurrency = concurrency
        self._reservation_ttl_s = reservation_ttl_s
        self._redis = redis
        self._metrics = metrics
        self._max_parallel_per_gpu = max_parallel_per_gpu

    async def validate(
        self,
        job_id: str,
        model_name: str,
        vram_requirement_mb: int,
        project_id: Optional[str] = None,
        stage: Optional[int] = None,
    ) -> AdmissionResult:
        """
        Execute the full 4-check admission control pipeline per §12.2.

        Each check must pass before proceeding to the next. Failures
        raise specific exceptions per Table 12-2.

        Args:
            job_id: Unique job identifier.
            model_name: Model name for concurrency tracking.
            vram_requirement_mb: Required VRAM in megabytes.
            project_id: Project ID for phase gate validation.
            stage: Pipeline stage for phase gate validation.

        Returns:
            AdmissionResult on success.

        Raises:
            PhaseGateError: Check #1 failed — invalid stage transition.
            NoCapacityError: Check #2 failed — insufficient VRAM.
            ConcurrencyLimitError: Check #3 failed — too many parallel tasks.
            CircuitBreakerOpenError: Check #4 failed — all GPUs have open circuits.
        """
        log = logger.bind(
            job_id=job_id,
            model_name=model_name,
            vram_mb=vram_requirement_mb,
        )
        log.info("admission_control_start")
        checks_passed: List[str] = []

        # --- Check #1: Phase Gate per §12.2 Table 12-2 ---
        await self._check_phase_gate(job_id, project_id, stage)
        checks_passed.append("phase_gate")
        log.debug("check_1_phase_gate_passed")

        # --- Check #2: VRAM Availability per §12.2 Table 12-2 ---
        await self._check_vram_availability(vram_requirement_mb)
        checks_passed.append("vram_availability")
        log.debug("check_2_vram_availability_passed")

        # --- Check #3: Concurrency Limit per §12.2 Table 12-2 ---
        await self._check_concurrency_limit(model_name)
        checks_passed.append("concurrency_limit")
        log.debug("check_3_concurrency_limit_passed")

        # --- Check #4: Circuit Breaker per §12.2 Table 12-2 ---
        await self._check_circuit_breaker()
        checks_passed.append("circuit_breaker")
        log.debug("check_4_circuit_breaker_passed")

        log.info(
            "admission_control_passed",
            checks_passed=checks_passed,
        )

        return AdmissionResult(
            passed=True,
            checks_passed=checks_passed,
            message="All 4 admission checks passed",
        )

    async def _check_phase_gate(
        self,
        job_id: str,
        project_id: Optional[str],
        stage: Optional[int],
    ) -> None:
        """
        Check #1: Phase Gate — validate stage transition per §12.2.

        Validates that the job's current state allows advancing to
        the requested stage. Prevents out-of-order execution.

        Raises:
            PhaseGateError: Invalid stage transition.
        """
        if stage is None or project_id is None:
            # No stage validation needed (non-pipeline job)
            return

        # Get current job state from Redis
        assert self._redis is not None
        state_key = f"{self.JOB_STATE_PREFIX}{project_id}"
        current_stage_str = await self._redis.get(state_key)
        current_stage = int(current_stage_str) if current_stage_str else 0

        valid_next = VALID_STAGE_TRANSITIONS.get(current_stage, set())
        if stage not in valid_next:
            from main import PhaseGateError
            raise PhaseGateError(
                f"Invalid stage transition for project '{project_id}': "
                f"current stage {current_stage} → requested stage {stage}. "
                f"Valid next stages: {sorted(valid_next)}"
            )

    async def _check_vram_availability(
        self, vram_requirement_mb: int
    ) -> None:
        """
        Check #2: VRAM Availability — verify sufficient GPU capacity per §12.2.

        Queries the registry for alive nodes and checks if any has
        sufficient available VRAM to satisfy the requirement.

        Raises:
            NoCapacityError: No GPU has sufficient available VRAM.
        """
        alive_nodes = await self._registry.get_alive_nodes()

        if not alive_nodes:
            from main import NoCapacityError
            raise NoCapacityError(
                "No alive GPU nodes available in the fleet"
            )

        # Check if any node has sufficient VRAM
        max_available = 0
        for node in alive_nodes:
            available = node.total_vram_mb - node.used_vram_mb
            max_available = max(max_available, available)
            if available >= vram_requirement_mb:
                return  # At least one node can satisfy

        from main import NoCapacityError
        raise NoCapacityError(
            f"No GPU has sufficient VRAM: need {vram_requirement_mb} MB, "
            f"max available is {max_available} MB across {len(alive_nodes)} nodes"
        )

    async def _check_concurrency_limit(self, model_name: str) -> None:
        """
        Check #3: Concurrency Limit — enforce per-GPU parallel task limit per §12.2.

        Default: 1 video generation job per GPU to prevent VRAM fragmentation.
        Checks all alive nodes to ensure at least one can accept a new task.

        Raises:
            ConcurrencyLimitError: All GPUs at concurrency limit.
        """
        alive_nodes = await self._registry.get_alive_nodes()

        for node in alive_nodes:
            can_accept = await self._concurrency.can_accept(
                node_id=node.node_id,
                gpu_index=node.gpu_index,
                model_name=model_name,
            )
            if can_accept:
                return  # At least one node can accept

        from main import ConcurrencyLimitError
        raise ConcurrencyLimitError(
            f"All {len(alive_nodes)} alive GPUs are at concurrency limit "
            f"for model '{model_name}' (max parallel: {self._max_parallel_per_gpu})"
        )

    async def _check_circuit_breaker(self) -> None:
        """
        Check #4: Circuit Breaker — verify at least one GPU has closed circuit per §12.2.

        If all GPUs have open circuit breakers (>20% error rate in last 10 min),
        the job cannot be scheduled and should be routed to DLQ.

        Raises:
            CircuitBreakerOpenError: All GPUs have open circuit breakers.
        """
        alive_nodes = await self._registry.get_alive_nodes()

        open_count = 0
        for node in alive_nodes:
            is_open = await self._circuit_breaker.is_open(node.node_id)
            if not is_open:
                return  # At least one GPU has closed circuit

            open_count += 1

        from main import CircuitBreakerOpenError
        raise CircuitBreakerOpenError(
            f"All {open_count} alive GPU nodes have open circuit breakers "
            f"(>20% error rate in last 10 minutes). "
            f"Job should be routed to DLQ."
        )

    async def release_reservation(
        self, reservation_id: str
    ) -> ReservationReleaseResult:
        """
        Release a VRAM reservation on job completion per §12.3.

        Frees reserved VRAM on the assigned GPU and removes the
        reservation record from Redis.

        Args:
            reservation_id: Reservation identifier to release.

        Returns:
            ReservationReleaseResult with freed VRAM amount.

        Raises:
            ReservationNotFoundError: Reservation not found.
        """
        assert self._redis is not None
        res_key = f"{self.RESERVATION_KEY_PREFIX}{reservation_id}"
        data = await self._redis.hgetall(res_key)

        if not data:
            from main import ReservationNotFoundError
            raise ReservationNotFoundError(
                f"Reservation '{reservation_id}' not found or expired"
            )

        node_id = data["node_id"]
        gpu_index = int(data["gpu_index"])
        vram_mb = int(data["vram_mb"])
        job_id = data.get("job_id", "")
        model_name = data.get("model_name", "")

        # Release VRAM on the node
        await self._registry.release_vram_usage(node_id, gpu_index, vram_mb)

        # Remove job from node's active list
        await self._registry.remove_node_job(node_id, job_id)

        # Release model concurrency slot
        await self._concurrency.release_model_load(
            node_id=node_id,
            gpu_index=gpu_index,
            model_name=model_name,
            job_id=job_id,
        )

        # Clean up Redis keys
        pipe = self._redis.pipeline()
        pipe.delete(res_key)
        pipe.srem(self.RESERVATION_INDEX_KEY, reservation_id)
        pipe.srem(f"{self.NODE_RESERVATIONS_PREFIX}{node_id}", reservation_id)
        if job_id:
            pipe.delete(f"sched:job_reservation:{job_id}")
        await pipe.execute()

        logger.info(
            "reservation_released",
            reservation_id=reservation_id,
            node_id=node_id,
            gpu_index=gpu_index,
            vram_freed_mb=vram_mb,
        )

        if self._metrics:
            used = int(
                await self._redis.hget(
                    f"gpu:node:{node_id}", "used_vram_mb"
                )
                or "0"
            )
            self._metrics.set_vram_used(node_id, gpu_index, used)

        return ReservationReleaseResult(
            reservation_id=reservation_id,
            node_id=node_id,
            gpu_index=gpu_index,
            vram_freed_mb=vram_mb,
        )

    async def release_node_reservations(self, node_id: str) -> int:
        """
        Release all reservations for a specific node.

        Called when a node is detected as dead to free its VRAM.

        Args:
            node_id: Node identifier whose reservations to release.

        Returns:
            Number of reservations released.
        """
        assert self._redis is not None
        node_res_key = f"{self.NODE_RESERVATIONS_PREFIX}{node_id}"
        reservation_ids = await self._redis.smembers(node_res_key)

        released = 0
        for res_id in reservation_ids:
            try:
                await self.release_reservation(res_id)
                released += 1
            except Exception:
                logger.warning(
                    "failed_to_release_dead_node_reservation",
                    reservation_id=res_id,
                    node_id=node_id,
                )

        logger.info(
            "node_reservations_released",
            node_id=node_id,
            count=released,
        )
        return released

    async def cleanup_expired_reservations(self) -> int:
        """
        Clean up expired VRAM reservations.

        Scans all tracked reservations and removes those whose Redis keys
        have expired (TTL elapsed). Returns the number cleaned up.

        Returns:
            Number of expired reservations cleaned up.
        """
        assert self._redis is not None
        all_ids = await self._redis.smembers(self.RESERVATION_INDEX_KEY)

        expired_count = 0
        for res_id in all_ids:
            res_key = f"{self.RESERVATION_KEY_PREFIX}{res_id}"
            exists = await self._redis.exists(res_key)
            if not exists:
                # Reservation key expired — clean up index entries
                pipe = self._redis.pipeline()
                pipe.srem(self.RESERVATION_INDEX_KEY, res_id)

                # We don't know the node_id anymore, so scan all node sets
                # This is acceptable because cleanup runs infrequently
                all_node_ids = await self._redis.smembers("gpu:nodes:all")
                for node_id in all_node_ids:
                    pipe.srem(
                        f"{self.NODE_RESERVATIONS_PREFIX}{node_id}", res_id
                    )

                await pipe.execute()
                expired_count += 1

        return expired_count

    async def update_job_state(
        self, project_id: str, stage: int
    ) -> None:
        """
        Update the job state for phase gate tracking.

        Called after a stage completes successfully to record
        the new current stage.

        Args:
            project_id: Project identifier.
            stage: Completed stage number.
        """
        assert self._redis is not None
        state_key = f"{self.JOB_STATE_PREFIX}{project_id}"
        await self._redis.set(state_key, str(stage))

        logger.debug(
            "job_state_updated",
            project_id=project_id,
            stage=stage,
        )

    async def get_job_state(self, project_id: str) -> int:
        """
        Get the current pipeline stage for a project.

        Args:
            project_id: Project identifier.

        Returns:
            Current stage number (0 if not started).
        """
        assert self._redis is not None
        state_key = f"{self.JOB_STATE_PREFIX}{project_id}"
        stage_str = await self._redis.get(state_key)
        return int(stage_str) if stage_str else 0
