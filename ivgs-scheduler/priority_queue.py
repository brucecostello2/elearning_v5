"""
IVGS v5 — Priority Queue Manager
====================================

Priority queue management per §12.1 Table 12-1.

Priority levels:
- urgent: 0–4 hour SLA (highest priority)
- normal: 4–24 hour SLA (default)
- batch:  24–72 hour SLA (lowest priority)

Anti-starvation mechanism:
- Every 30 minutes waiting, a job's effective priority is bumped +1
- "batch" → "normal" after 30 min, "normal" → "urgent" after 60 min
- Prevents batch jobs from starving indefinitely

Redis key structure:
- pq:job:{job_id}        — Hash with job priority metadata
- pq:queue:urgent        — Sorted set of urgent jobs (score=submit_time)
- pq:queue:normal        — Sorted set of normal jobs
- pq:queue:batch         — Sorted set of batch jobs
- pq:depths              — Hash of queue depth counters
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIORITY_LEVELS = {
    "urgent": 0,
    "normal": 1,
    "batch": 2,
}

PRIORITY_NAMES = {v: k for k, v in PRIORITY_LEVELS.items()}

# SLA windows per §12.1
PRIORITY_SLA_HOURS = {
    "urgent": (0, 4),
    "normal": (4, 24),
    "batch": (24, 72),
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class QueuedJob:
    """A job in the priority queue."""

    job_id: str
    base_priority: str
    effective_priority: str
    submitted_at: float
    aging_bumps: int
    model_name: str
    vram_requirement_mb: int


# ---------------------------------------------------------------------------
# Priority Queue Manager
# ---------------------------------------------------------------------------

class PriorityQueueManager:
    """
    Priority queue manager with anti-starvation aging per §12.1.

    Manages three priority queues (urgent, normal, batch) with automatic
    priority escalation for long-waiting jobs. Every 30 minutes of waiting
    bumps effective priority by +1 level.

    Args:
        redis: Redis connection for queue state.
        aging_interval_s: Anti-starvation aging interval (default: 1800s per §12.1).
        metrics: Prometheus metrics collector.
    """

    # Redis key prefixes
    JOB_PREFIX = "pq:job:"
    QUEUE_PREFIX = "pq:queue:"
    DEPTHS_KEY = "pq:depths"

    def __init__(
        self,
        redis: aioredis.Redis,
        aging_interval_s: int = 1800,
        metrics=None,
    ) -> None:
        self._redis = redis
        self._aging_interval_s = aging_interval_s
        self._metrics = metrics

    async def resolve_priority(
        self,
        job_id: str,
        base_priority: str,
    ) -> str:
        """
        Resolve the effective priority for a job.

        For new jobs, returns the base priority. For existing queued jobs,
        calculates the effective priority based on anti-starvation aging.

        Args:
            job_id: Job identifier.
            base_priority: Base priority level (urgent/normal/batch).

        Returns:
            Effective priority level after aging.
        """
        job_key = f"{self.JOB_PREFIX}{job_id}"
        existing = await self._redis.hgetall(job_key)

        if existing:
            # Existing job — calculate aged priority
            submitted_at = float(existing.get("submitted_at", str(time.time())))
            base = existing.get("base_priority", base_priority)
            effective = self._calculate_effective_priority(
                base, submitted_at
            )
            await self._redis.hset(
                job_key, "effective_priority", effective
            )
            return effective

        # New job — register and return base priority
        now = time.time()
        job_data = {
            "job_id": job_id,
            "base_priority": base_priority,
            "effective_priority": base_priority,
            "submitted_at": str(now),
            "aging_bumps": "0",
        }
        await self._redis.hset(job_key, mapping=job_data)
        await self._redis.expire(job_key, 259200)  # 72h TTL (max SLA)

        # Add to appropriate queue
        queue_key = f"{self.QUEUE_PREFIX}{base_priority}"
        await self._redis.zadd(queue_key, {job_id: now})

        # Update depth counter
        await self._redis.hincrby(self.DEPTHS_KEY, base_priority, 1)

        if self._metrics:
            depths = await self.get_queue_depths()
            for level, depth in depths.items():
                self._metrics.set_queue_depth("fleet", level, depth)

        logger.debug(
            "job_registered_in_queue",
            job_id=job_id,
            priority=base_priority,
        )

        return base_priority

    def _calculate_effective_priority(
        self,
        base_priority: str,
        submitted_at: float,
    ) -> str:
        """
        Calculate effective priority based on aging per §12.1.

        Every aging_interval_s (30 min) of waiting bumps priority +1.
        batch → normal → urgent (ceiling).

        Args:
            base_priority: Original priority level.
            submitted_at: Job submission timestamp.

        Returns:
            Effective priority level.
        """
        elapsed = time.time() - submitted_at
        bumps = int(elapsed // self._aging_interval_s)

        base_level = PRIORITY_LEVELS.get(base_priority, 1)
        effective_level = max(0, base_level - bumps)  # Lower = higher priority

        return PRIORITY_NAMES.get(effective_level, "urgent")

    async def apply_aging(self) -> int:
        """
        Apply anti-starvation aging to all queued jobs per §12.1.

        Scans all queues and bumps the effective priority of jobs
        that have been waiting longer than the aging interval.

        Returns:
            Number of jobs whose priority was aged.
        """
        aged_count = 0
        now = time.time()

        for priority_level in ["batch", "normal"]:
            queue_key = f"{self.QUEUE_PREFIX}{priority_level}"
            job_ids = await self._redis.zrange(queue_key, 0, -1)

            for job_id in job_ids:
                job_key = f"{self.JOB_PREFIX}{job_id}"
                job_data = await self._redis.hgetall(job_key)
                if not job_data:
                    # Job expired — remove from queue
                    await self._redis.zrem(queue_key, job_id)
                    continue

                submitted_at = float(
                    job_data.get("submitted_at", str(now))
                )
                base_priority = job_data.get("base_priority", priority_level)
                old_effective = job_data.get(
                    "effective_priority", priority_level
                )

                new_effective = self._calculate_effective_priority(
                    base_priority, submitted_at
                )

                if new_effective != old_effective:
                    # Priority changed — move to new queue
                    pipe = self._redis.pipeline()

                    # Remove from old queue
                    pipe.zrem(queue_key, job_id)
                    pipe.hincrby(self.DEPTHS_KEY, priority_level, -1)

                    # Add to new queue
                    new_queue_key = f"{self.QUEUE_PREFIX}{new_effective}"
                    pipe.zadd(new_queue_key, {job_id: submitted_at})
                    pipe.hincrby(self.DEPTHS_KEY, new_effective, 1)

                    # Update job metadata
                    bumps = int(job_data.get("aging_bumps", "0")) + 1
                    pipe.hset(
                        job_key,
                        mapping={
                            "effective_priority": new_effective,
                            "aging_bumps": str(bumps),
                        },
                    )

                    await pipe.execute()
                    aged_count += 1

                    logger.info(
                        "job_priority_aged",
                        job_id=job_id,
                        old_priority=old_effective,
                        new_priority=new_effective,
                        bumps=bumps,
                        wait_time_s=round(now - submitted_at, 0),
                    )

        if self._metrics and aged_count > 0:
            depths = await self.get_queue_depths()
            for level, depth in depths.items():
                self._metrics.set_queue_depth("fleet", level, depth)

        return aged_count

    async def remove_job(self, job_id: str) -> None:
        """
        Remove a job from the priority queue after scheduling.

        Args:
            job_id: Job identifier to remove.
        """
        job_key = f"{self.JOB_PREFIX}{job_id}"
        job_data = await self._redis.hgetall(job_key)

        if job_data:
            effective_priority = job_data.get("effective_priority", "normal")
            queue_key = f"{self.QUEUE_PREFIX}{effective_priority}"

            pipe = self._redis.pipeline()
            pipe.zrem(queue_key, job_id)
            pipe.delete(job_key)
            pipe.hincrby(self.DEPTHS_KEY, effective_priority, -1)
            await pipe.execute()

            if self._metrics:
                depths = await self.get_queue_depths()
                for level, depth in depths.items():
                    self._metrics.set_queue_depth("fleet", level, depth)

    async def get_queue_depths(self) -> Dict[str, int]:
        """
        Get current queue depths per priority level.

        Returns:
            Dict mapping priority level to queue depth.
        """
        depths = await self._redis.hgetall(self.DEPTHS_KEY)
        return {
            "urgent": max(0, int(depths.get("urgent", "0"))),
            "normal": max(0, int(depths.get("normal", "0"))),
            "batch": max(0, int(depths.get("batch", "0"))),
        }

    async def get_total_depth(self) -> int:
        """Get total queue depth across all priority levels."""
        depths = await self.get_queue_depths()
        return sum(depths.values())

    async def get_queued_jobs(
        self,
        priority: Optional[str] = None,
        limit: int = 100,
    ) -> List[QueuedJob]:
        """
        Get queued jobs, optionally filtered by priority.

        Args:
            priority: Filter by priority level (None = all).
            limit: Maximum number of jobs to return.

        Returns:
            List of QueuedJob records sorted by submission time.
        """
        levels = [priority] if priority else ["urgent", "normal", "batch"]
        jobs: List[QueuedJob] = []

        for level in levels:
            queue_key = f"{self.QUEUE_PREFIX}{level}"
            job_ids = await self._redis.zrange(
                queue_key, 0, limit - 1, withscores=True
            )

            for job_id, score in job_ids:
                job_key = f"{self.JOB_PREFIX}{job_id}"
                data = await self._redis.hgetall(job_key)
                if data:
                    jobs.append(
                        QueuedJob(
                            job_id=data.get("job_id", job_id),
                            base_priority=data.get("base_priority", level),
                            effective_priority=data.get(
                                "effective_priority", level
                            ),
                            submitted_at=float(
                                data.get("submitted_at", str(score))
                            ),
                            aging_bumps=int(
                                data.get("aging_bumps", "0")
                            ),
                            model_name=data.get("model_name", ""),
                            vram_requirement_mb=int(
                                data.get("vram_requirement_mb", "0")
                            ),
                        )
                    )

        # Sort by submission time (oldest first)
        jobs.sort(key=lambda j: j.submitted_at)
        return jobs[:limit]
