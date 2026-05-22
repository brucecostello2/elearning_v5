"""
IVGS v5 — GPU Scheduler Engine
=================================

VRAM-aware bin-packing scheduler per §12.1 Table 12-1.

Scheduling algorithm:
1. Job enters via schedule_job()
2. Priority queue assigns effective priority (with anti-starvation aging)
3. Admission controller performs 4-check validation (§12.2)
4. Load balancer selects candidate nodes weighted by utilization
5. Scheduler sorts candidates by available VRAM descending
6. First-fit allocation: first GPU with sufficient VRAM is assigned
7. VRAM reservation created with 5-minute TTL
8. Model concurrency tracked for warm-start preferences

Raises NoCapacityError when no GPU can satisfy the VRAM requirement.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleResult:
    """Result of a successful scheduling decision."""

    node_id: str
    gpu_index: int
    reservation_id: str
    model_name: str
    vram_reserved_mb: int
    estimated_duration_s: int
    scheduled_at: str


@dataclass
class GpuCandidate:
    """A GPU node candidate for scheduling."""

    node_id: str
    gpu_index: int
    gpu_model: str
    total_vram_mb: int
    used_vram_mb: int
    available_vram_mb: int
    gpu_utilization_pct: float
    has_model_loaded: bool
    weight: float = 0.0
    queue_depth: int = 0


@dataclass
class VramReservation:
    """VRAM reservation record per §12.2."""

    reservation_id: str
    job_id: str
    node_id: str
    gpu_index: int
    model_name: str
    vram_mb: int
    created_at: str
    expires_at: str
    ttl_s: int


# ---------------------------------------------------------------------------
# GPU Scheduler
# ---------------------------------------------------------------------------

class GpuScheduler:
    """
    VRAM-aware bin-packing GPU scheduler per §12.1.

    Coordinates all six scheduler components (Table 12-1) to make
    optimal GPU assignment decisions:
    - GpuRegistry: node discovery and health
    - AdmissionController: 4-check validation
    - LoadBalancer: weighted candidate ranking
    - ModelConcurrencyManager: warm-start preferences
    - PriorityQueueManager: priority with anti-starvation
    - CircuitBreaker: error rate protection

    Args:
        registry: GPU node registry for node discovery.
        admission: Admission controller for 4-check validation.
        load_balancer: Load balancer for weighted selection.
        concurrency: Model concurrency manager.
        priority_queue: Priority queue manager.
        circuit_breaker: Circuit breaker for error protection.
        redis: Redis connection for state persistence.
        metrics: Prometheus metrics collector.
    """

    # Redis key prefixes
    RESERVATION_KEY_PREFIX = "sched:reservation:"
    RESERVATION_INDEX_KEY = "sched:reservations:index"
    NODE_RESERVATIONS_PREFIX = "sched:node_reservations:"
    JOB_RESERVATION_PREFIX = "sched:job_reservation:"

    def __init__(
        self,
        registry,
        admission,
        load_balancer,
        concurrency,
        priority_queue,
        circuit_breaker,
        redis: aioredis.Redis,
        metrics,
    ) -> None:
        self._registry = registry
        self._admission = admission
        self._load_balancer = load_balancer
        self._concurrency = concurrency
        self._priority_queue = priority_queue
        self._circuit_breaker = circuit_breaker
        self._redis = redis
        self._metrics = metrics

    async def schedule_job(
        self,
        job_id: str,
        model_name: str,
        vram_requirement_mb: int,
        estimated_duration_s: int,
        priority: str = "normal",
        project_id: Optional[str] = None,
        stage: Optional[int] = None,
    ) -> ScheduleResult:
        """
        Schedule a GPU job using VRAM-aware bin-packing per §12.1.

        The full scheduling pipeline:
        1. Resolve effective priority via PriorityQueueManager
        2. Run 4-check admission control via AdmissionController
        3. Get weighted candidates via LoadBalancer
        4. Sort by available VRAM descending (first-fit bin-packing)
        5. Prefer GPUs with model already loaded (warm-start)
        6. Create VRAM reservation with 5-min TTL
        7. Track model load on selected GPU

        Args:
            job_id: Unique job identifier.
            model_name: Name of the model to schedule.
            vram_requirement_mb: VRAM needed in megabytes.
            estimated_duration_s: Estimated job duration in seconds.
            priority: Priority level (urgent/normal/batch).
            project_id: Optional project ID for phase gate validation.
            stage: Optional pipeline stage for phase gate validation.

        Returns:
            ScheduleResult with assigned node, GPU, and reservation details.

        Raises:
            PhaseGateError: Stage transition validation failed.
            NoCapacityError: No GPU has sufficient VRAM.
            ConcurrencyLimitError: Per-GPU concurrency limit exceeded.
            CircuitBreakerOpenError: All candidate GPUs have open circuits.
        """
        log = logger.bind(
            job_id=job_id,
            model_name=model_name,
            vram_mb=vram_requirement_mb,
            priority=priority,
        )
        log.info("scheduling_pipeline_start")

        start_time = time.monotonic()

        # --- Step 1: Resolve effective priority ---
        effective_priority = await self._priority_queue.resolve_priority(
            job_id=job_id,
            base_priority=priority,
        )
        log.debug("priority_resolved", effective_priority=effective_priority)

        # --- Step 2: 4-check admission control (§12.2) ---
        await self._admission.validate(
            job_id=job_id,
            model_name=model_name,
            vram_requirement_mb=vram_requirement_mb,
            project_id=project_id,
            stage=stage,
        )
        log.debug("admission_passed")

        # --- Step 3: Get weighted candidates from load balancer ---
        candidates = await self._load_balancer.get_weighted_candidates(
            model_name=model_name,
            vram_requirement_mb=vram_requirement_mb,
        )

        if not candidates:
            from main import NoCapacityError
            raise NoCapacityError(
                f"No GPU nodes available for model '{model_name}' "
                f"requiring {vram_requirement_mb} MB VRAM"
            )

        log.debug("candidates_found", count=len(candidates))

        # --- Step 4: Sort by available VRAM descending (first-fit) ---
        # Prefer GPUs with model already loaded (warm-start bonus)
        candidates.sort(
            key=lambda c: (
                c.has_model_loaded,  # True sorts after False (warm-start preferred)
                c.available_vram_mb,  # Higher available VRAM preferred
            ),
            reverse=True,
        )

        # --- Step 5: First-fit allocation ---
        selected: Optional[GpuCandidate] = None
        for candidate in candidates:
            # Check circuit breaker for this specific node
            cb_open = await self._circuit_breaker.is_open(candidate.node_id)
            if cb_open:
                log.debug(
                    "candidate_skipped_circuit_breaker",
                    node_id=candidate.node_id,
                )
                continue

            # Check concurrency limit for this GPU
            can_accept = await self._concurrency.can_accept(
                node_id=candidate.node_id,
                gpu_index=candidate.gpu_index,
                model_name=model_name,
            )
            if not can_accept:
                log.debug(
                    "candidate_skipped_concurrency",
                    node_id=candidate.node_id,
                    gpu_index=candidate.gpu_index,
                )
                continue

            # Sufficient VRAM check
            if candidate.available_vram_mb >= vram_requirement_mb:
                selected = candidate
                break

        if selected is None:
            from main import NoCapacityError
            raise NoCapacityError(
                f"No GPU can satisfy {vram_requirement_mb} MB VRAM "
                f"for model '{model_name}' — all candidates filtered "
                f"by circuit breaker, concurrency, or insufficient VRAM"
            )

        log.info(
            "gpu_selected",
            node_id=selected.node_id,
            gpu_index=selected.gpu_index,
            available_vram=selected.available_vram_mb,
            warm_start=selected.has_model_loaded,
        )

        # --- Step 6: Create VRAM reservation ---
        reservation = await self._create_reservation(
            job_id=job_id,
            node_id=selected.node_id,
            gpu_index=selected.gpu_index,
            model_name=model_name,
            vram_mb=vram_requirement_mb,
            estimated_duration_s=estimated_duration_s,
        )

        # --- Step 7: Track model load ---
        await self._concurrency.record_model_load(
            node_id=selected.node_id,
            gpu_index=selected.gpu_index,
            model_name=model_name,
            job_id=job_id,
        )

        # --- Update metrics ---
        elapsed = time.monotonic() - start_time
        self._metrics.set_vram_used(
            selected.node_id,
            selected.gpu_index,
            selected.used_vram_mb + vram_requirement_mb,
        )
        self._metrics.set_queue_depth(
            selected.node_id,
            effective_priority,
            await self._get_node_queue_depth(selected.node_id),
        )

        log.info(
            "scheduling_complete",
            reservation_id=reservation.reservation_id,
            elapsed_s=round(elapsed, 4),
        )

        return ScheduleResult(
            node_id=selected.node_id,
            gpu_index=selected.gpu_index,
            reservation_id=reservation.reservation_id,
            model_name=model_name,
            vram_reserved_mb=vram_requirement_mb,
            estimated_duration_s=estimated_duration_s,
            scheduled_at=reservation.created_at,
        )

    async def _create_reservation(
        self,
        job_id: str,
        node_id: str,
        gpu_index: int,
        model_name: str,
        vram_mb: int,
        estimated_duration_s: int,
    ) -> VramReservation:
        """
        Create a VRAM reservation with 5-minute TTL per §12.2.

        The reservation is stored in Redis with automatic expiration.
        Workers must call PUT /heartbeat within the TTL to keep it active.

        Args:
            job_id: Job identifier.
            node_id: Assigned node hostname.
            gpu_index: Assigned GPU device index.
            model_name: Model name being scheduled.
            vram_mb: VRAM amount reserved.
            estimated_duration_s: Expected job duration.

        Returns:
            VramReservation record.
        """
        reservation_id = f"res-{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        ttl_s = 300  # 5-minute TTL per §12.2
        expires_at = datetime.fromtimestamp(
            now.timestamp() + ttl_s, tz=timezone.utc
        )

        reservation = VramReservation(
            reservation_id=reservation_id,
            job_id=job_id,
            node_id=node_id,
            gpu_index=gpu_index,
            model_name=model_name,
            vram_mb=vram_mb,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            ttl_s=ttl_s,
        )

        # Store reservation in Redis with TTL
        reservation_key = f"{self.RESERVATION_KEY_PREFIX}{reservation_id}"
        reservation_data = {
            "reservation_id": reservation.reservation_id,
            "job_id": job_id,
            "node_id": node_id,
            "gpu_index": str(gpu_index),
            "model_name": model_name,
            "vram_mb": str(vram_mb),
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
            "estimated_duration_s": str(estimated_duration_s),
        }

        pipe = self._redis.pipeline()

        # Store reservation hash
        pipe.hset(reservation_key, mapping=reservation_data)
        pipe.expire(reservation_key, ttl_s)

        # Add to reservation index (for listing/cleanup)
        pipe.sadd(self.RESERVATION_INDEX_KEY, reservation_id)

        # Add to per-node reservation set
        node_res_key = f"{self.NODE_RESERVATIONS_PREFIX}{node_id}"
        pipe.sadd(node_res_key, reservation_id)

        # Map job to reservation
        job_res_key = f"{self.JOB_RESERVATION_PREFIX}{job_id}"
        pipe.set(job_res_key, reservation_id, ex=ttl_s)

        # Update node VRAM usage
        await self._registry.add_vram_usage(node_id, gpu_index, vram_mb)

        await pipe.execute()

        logger.info(
            "reservation_created",
            reservation_id=reservation_id,
            node_id=node_id,
            gpu_index=gpu_index,
            vram_mb=vram_mb,
            ttl_s=ttl_s,
        )

        return reservation

    async def get_reservation(
        self, reservation_id: str
    ) -> Optional[VramReservation]:
        """
        Retrieve a VRAM reservation by ID.

        Args:
            reservation_id: Reservation identifier.

        Returns:
            VramReservation if found, None otherwise.
        """
        reservation_key = f"{self.RESERVATION_KEY_PREFIX}{reservation_id}"
        data = await self._redis.hgetall(reservation_key)

        if not data:
            return None

        return VramReservation(
            reservation_id=data["reservation_id"],
            job_id=data["job_id"],
            node_id=data["node_id"],
            gpu_index=int(data["gpu_index"]),
            model_name=data["model_name"],
            vram_mb=int(data["vram_mb"]),
            created_at=data["created_at"],
            expires_at=data["expires_at"],
            ttl_s=300,
        )

    async def extend_reservation(
        self, reservation_id: str, extension_s: int = 300
    ) -> bool:
        """
        Extend a reservation TTL on heartbeat per §12.2.

        Called when a worker sends a heartbeat to keep its reservation alive.

        Args:
            reservation_id: Reservation to extend.
            extension_s: Extension duration in seconds (default: 5 min).

        Returns:
            True if reservation was extended, False if not found.
        """
        reservation_key = f"{self.RESERVATION_KEY_PREFIX}{reservation_id}"
        exists = await self._redis.exists(reservation_key)
        if not exists:
            return False

        now = datetime.now(timezone.utc)
        new_expiry = datetime.fromtimestamp(
            now.timestamp() + extension_s, tz=timezone.utc
        )

        pipe = self._redis.pipeline()
        pipe.hset(reservation_key, "expires_at", new_expiry.isoformat())
        pipe.expire(reservation_key, extension_s)

        # Also extend job-to-reservation mapping
        job_id = await self._redis.hget(reservation_key, "job_id")
        if job_id:
            job_res_key = f"{self.JOB_RESERVATION_PREFIX}{job_id}"
            pipe.expire(job_res_key, extension_s)

        await pipe.execute()

        logger.debug(
            "reservation_extended",
            reservation_id=reservation_id,
            new_expiry=new_expiry.isoformat(),
        )
        return True

    async def _get_node_queue_depth(self, node_id: str) -> int:
        """Get the number of active reservations for a node."""
        node_res_key = f"{self.NODE_RESERVATIONS_PREFIX}{node_id}"
        members = await self._redis.smembers(node_res_key)

        # Filter out expired reservations
        active_count = 0
        for res_id in members:
            res_key = f"{self.RESERVATION_KEY_PREFIX}{res_id}"
            if await self._redis.exists(res_key):
                active_count += 1
            else:
                # Clean up stale index entry
                await self._redis.srem(node_res_key, res_id)
                await self._redis.srem(self.RESERVATION_INDEX_KEY, res_id)

        return active_count

    async def get_active_reservations(self) -> List[VramReservation]:
        """
        Get all active VRAM reservations.

        Returns:
            List of active VramReservation records.
        """
        all_ids = await self._redis.smembers(self.RESERVATION_INDEX_KEY)
        reservations: List[VramReservation] = []

        for res_id in all_ids:
            reservation = await self.get_reservation(res_id)
            if reservation is not None:
                reservations.append(reservation)
            else:
                # Clean up stale index entry
                await self._redis.srem(self.RESERVATION_INDEX_KEY, res_id)

        return reservations

    async def get_job_reservation(self, job_id: str) -> Optional[str]:
        """
        Get the reservation ID for a job.

        Args:
            job_id: Job identifier.

        Returns:
            Reservation ID if found, None otherwise.
        """
        job_res_key = f"{self.JOB_RESERVATION_PREFIX}{job_id}"
        return await self._redis.get(job_res_key)
