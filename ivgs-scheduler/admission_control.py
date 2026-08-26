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

from dataclasses import dataclass
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
    # WP-60 Task 3: the never-expiring twin written by
    # `GpuScheduler._create_reservation`. See that constant for why it exists.
    RESERVATION_LEDGER_PREFIX = "sched:reservation_ledger:"
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
        ledger_key = f"{self.RESERVATION_LEDGER_PREFIX}{reservation_id}"
        data = await self._redis.hgetall(res_key)

        # WP-60 Task 3 — THE LEAK, AND WHY IT COULD NOT BE SWEPT UP.
        #
        # This used to raise the moment `res_key` was gone. `res_key` carries a
        # 300s TTL while the jobs it covers run for up to 3900s, so for every
        # long render the release arrived AFTER the record it needed and could
        # only fail. `used_vram_mb` -- a counter with no TTL -- stayed up.
        #
        # Measured on the live fleet, 2026-08-26 01:37 UTC:
        #   gpu:node:node-03:gpu0  used_vram_mb=16384
        #                          current_job_id=""      (no job running)
        #   sched:reservation:*    NO KEYS EXIST ANYWHERE (all expired)
        # A registration an hour old already 16 GB short, and nothing left in
        # Redis that could say who owed it. Admission control computes headroom
        # as total minus used (`_check_vram_availability`), so node-03 was
        # silently 16 GB smaller than it is.
        #
        # It is a one-way ratchet: every reservation on a job longer than the
        # TTL leaks, permanently, and only a re-registration ever clears it.
        # (One did, at 02:46 -- which is why the counter reads 0 today. That is
        # accidental recovery, not a fix.)
        #
        # The ledger is consulted when the TTL'd record is gone, so a late
        # release still knows what to give back.
        recovered_from_ledger = False
        if not data:
            data = await self._redis.hgetall(ledger_key)
            recovered_from_ledger = bool(data)

        if not data:
            from main import ReservationNotFoundError
            raise ReservationNotFoundError(
                f"Reservation '{reservation_id}' not found or expired"
            )

        if recovered_from_ledger:
            logger.warning(
                "reservation_released_after_expiry",
                reservation_id=reservation_id,
                node_id=data.get("node_id"),
                vram_mb=data.get("vram_mb"),
                detail=(
                    "the TTL'd reservation record was already gone; released "
                    "from the durable ledger. A job outliving its reservation "
                    "TTL is expected for long renders and is not an error - "
                    "but before WP-60 this path leaked the VRAM instead."
                ),
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
        pipe.delete(ledger_key)
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
        Release VRAM held by expired reservations, and tidy the index.

        WP-60 Task 3 — THIS FUNCTION WAS THE LEAK'S ALIBI.

        It was the only thing in the system that noticed an expired
        reservation, and its own comment recorded why it could do nothing
        about it:

            # Reservation key expired - clean up index entries
            # We don't know the node_id anymore, so scan all node sets

        It did not know the node_id because the expired hash WAS the only
        record of it. So it removed the bookkeeping that said VRAM was
        outstanding while leaving the VRAM outstanding -- turning a visible
        leak into an invisible one, on a five-minute timer. It reported the
        count it cleaned as if that were a recovery.

        `release_node_reservations` had the same hole from the other side: it
        called `release_reservation`, which raised for anything expired, and
        swallowed that into a warning.

        With the durable ledger in place this now performs a real release for
        every expired reservation it finds, and the two counts are reported
        separately so "swept" can never again be mistaken for "recovered".

        Returns:
            Number of expired reservations whose VRAM was actually released.
        """
        assert self._redis is not None
        all_ids = await self._redis.smembers(self.RESERVATION_INDEX_KEY)

        released_count = 0
        orphaned_count = 0
        for res_id in all_ids:
            res_key = f"{self.RESERVATION_KEY_PREFIX}{res_id}"
            if await self._redis.exists(res_key):
                continue  # still live; nothing to do

            try:
                await self.release_reservation(res_id)
                released_count += 1
                continue
            except Exception:
                # No ledger entry either -- a reservation from before this
                # change, or one whose ledger row was removed by hand. The
                # VRAM it holds is NOT recoverable from here, and saying so is
                # the whole point: the operator has `POST /reconcile/{node_id}`
                # for exactly this.
                orphaned_count += 1

            pipe = self._redis.pipeline()
            pipe.srem(self.RESERVATION_INDEX_KEY, res_id)
            all_node_ids = await self._redis.smembers("gpu:nodes:all")
            for node_id in all_node_ids:
                pipe.srem(f"{self.NODE_RESERVATIONS_PREFIX}{node_id}", res_id)
            await pipe.execute()

        if orphaned_count:
            logger.error(
                "expired_reservations_without_ledger",
                count=orphaned_count,
                detail=(
                    "these reservations expired with no durable ledger row, so "
                    "the VRAM they reserved cannot be attributed to a node and "
                    "remains counted against it. Run POST /reconcile/{node_id} "
                    "to recompute used_vram_mb from live reservations."
                ),
            )

        return released_count

    async def reconcile_node_vram(self, node_id: str) -> Dict[str, Any]:
        """
        Recompute a node's ``used_vram_mb`` from the reservations that exist.

        WP-60 Task 3. The operator's release path, and the reconciler
        registration now calls instead of blindly reseeding.

        ``used_vram_mb`` is a free-running counter: `add_vram_usage` does
        `HINCRBY`, `release_vram_usage` does a read-modify-write, and nothing
        has ever checked the total against the reservations that justify it.
        A counter with no derivation cannot self-correct, so any lost release
        is permanent. This derives the truth and states the drift rather than
        silently overwriting -- a silent overwrite is how the accidental
        recovery at re-registration hid the defect for as long as it did.

        Returns a dict describing what it found and what it changed. Safe to
        run at any time: it never invents a reservation, and a node genuinely
        holding 16 GB of live reservations keeps its 16 GB.
        """
        assert self._redis is not None

        node_res_key = f"{self.NODE_RESERVATIONS_PREFIX}{node_id}"
        reservation_ids = await self._redis.smembers(node_res_key)

        derived_mb = 0
        counted: List[str] = []
        for res_id in reservation_ids:
            data = await self._redis.hgetall(
                f"{self.RESERVATION_KEY_PREFIX}{res_id}"
            )
            if not data:
                data = await self._redis.hgetall(
                    f"{self.RESERVATION_LEDGER_PREFIX}{res_id}"
                )
            if not data:
                continue
            try:
                derived_mb += int(data.get("vram_mb", 0))
            except (TypeError, ValueError):
                continue
            counted.append(res_id)

        node_key = f"gpu:node:{node_id}"
        raw = await self._redis.hget(node_key, "used_vram_mb")
        try:
            current_mb = int(raw or 0)
        except (TypeError, ValueError):
            current_mb = 0

        drift_mb = current_mb - derived_mb
        if drift_mb != 0:
            await self._redis.hset(node_key, "used_vram_mb", str(derived_mb))
            logger.warning(
                "node_vram_reconciled",
                node_id=node_id,
                previous_used_vram_mb=current_mb,
                derived_used_vram_mb=derived_mb,
                drift_mb=drift_mb,
                live_reservations=len(counted),
                detail=(
                    "used_vram_mb did not match the reservations backing it. "
                    "A positive drift is leaked reservation - VRAM counted "
                    "against the node that no live reservation justifies."
                ),
            )

        return {
            "node_id": node_id,
            "previous_used_vram_mb": current_mb,
            "used_vram_mb": derived_mb,
            "drift_mb": drift_mb,
            "live_reservations": len(counted),
            "reconciled": drift_mb != 0,
        }

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
