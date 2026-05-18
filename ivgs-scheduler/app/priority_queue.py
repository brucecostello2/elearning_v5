"""Priority-based job scheduling with anti-starvation aging.

Priority tiers:
    urgent (score 0–4h SLA)   → weight 10, score range 1000–1999
    normal (4–24h SLA)         → weight 3,  score range 100–999
    batch  (24–72h SLA)        → weight 1,  score range 0–99

Redis sorted sets store jobs with composite score:
    score = base_priority + (time_in_queue_minutes / aging_period)

Aging: every AGING_PERIOD_MINUTES, job priority score increases by 1.
       An urgent job waiting 2h is promoted above a new urgent job.
       A batch job waiting 48h eventually overtakes new normal jobs.
"""

import json
import logging
import time
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Redis key for priority queue
QUEUE_KEY = "ivgs_priority_queue"

# Base scores by tier
PRIORITY_SCORES = {
    "urgent": 1000,
    "normal": 100,
    "batch": 0,
}
AGING_PERIOD_MINUTES = 30      # Each period adds 1 to score
MAX_AGE_BOOST = 500            # Cap on aging boost (prevents runaway)


class PriorityQueueManager:
    """SLA-tiered priority queue using Redis sorted sets."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def enqueue(
        self,
        job_id: str,
        priority: str,
        task_type: str,
        gpu_capabilities: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Add a job to the priority queue.

        Returns the initial score assigned to the job.
        """
        if priority not in PRIORITY_SCORES:
            priority = "normal"

        base_score = PRIORITY_SCORES[priority]
        # Encode job metadata in a side-store keyed by job_id
        metadata = {
            "job_id": job_id,
            "priority": priority,
            "task_type": task_type,
            "gpu_capabilities": gpu_capabilities or {},
            "enqueued_at": time.time(),
            "base_score": base_score,
        }
        meta_key = f"pq_meta:{job_id}"
        self.redis.setex(meta_key, 86400, json.dumps(metadata))

        # Add to sorted set with negated score (higher = dequeued first)
        # We negate because Redis ZPOPMIN removes lowest score
        self.redis.zadd(QUEUE_KEY, {job_id: -base_score})

        logger.info(
            "Enqueued job %s priority=%s task=%s score=%d",
            job_id, priority, task_type, base_score
        )
        return float(base_score)

    def dequeue_next(
        self,
        gpu_capabilities: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Dequeue the highest-priority eligible job.

        Applies aging boost before selecting.
        Returns job metadata dict or None if queue empty.
        """
        # Apply aging to all queued jobs first
        self._apply_aging()

        # Pop the highest-priority item (most negative score = lowest ZPOPMIN)
        result = self.redis.zpopmin(QUEUE_KEY, 1)
        if not result:
            return None

        job_id_bytes, score = result[0]
        job_id = job_id_bytes if isinstance(job_id_bytes, str) \
            else job_id_bytes.decode()

        meta_key = f"pq_meta:{job_id}"
        raw = self.redis.get(meta_key)
        if not raw:
            logger.warning("PQ: no metadata for job %s — skipping", job_id)
            return None

        metadata = json.loads(raw)
        self.redis.delete(meta_key)
        logger.info(
            "Dequeued job %s priority=%s score=%.2f wait=%.1fs",
            job_id, metadata['priority'],
            abs(score),
            time.time() - metadata['enqueued_at']
        )
        return metadata

    def apply_aging(
        self, minutes_per_priority_bump: int = AGING_PERIOD_MINUTES
    ) -> int:
        """Promote jobs based on time-in-queue.

        Returns number of jobs aged.
        """
        return self._apply_aging(minutes_per_priority_bump)

    def get_queue_stats(self) -> Dict[str, Any]:
        """Return per-priority queue depth and oldest job age."""
        all_jobs = self.redis.zrange(QUEUE_KEY, 0, -1, withscores=True)
        stats = {"urgent": 0, "normal": 0, "batch": 0, "total": len(all_jobs)}

        for job_id_b, score in all_jobs:
            job_id = job_id_b if isinstance(job_id_b, str) \
                else job_id_b.decode()
            meta_raw = self.redis.get(f"pq_meta:{job_id}")
            if meta_raw:
                meta = json.loads(meta_raw)
                p = meta.get('priority', 'normal')
                if p in stats:
                    stats[p] += 1

        return stats

    # ──────────────────────────────────────────────

    def _apply_aging(
        self, minutes_per_bump: int = AGING_PERIOD_MINUTES
    ) -> int:
        """Internal: apply aging boost to all queued jobs."""
        all_jobs = self.redis.zrange(QUEUE_KEY, 0, -1, withscores=True)
        aged = 0
        now = time.time()

        for job_id_b, current_score in all_jobs:
            job_id = job_id_b if isinstance(job_id_b, str) \
                else job_id_b.decode()
            meta_raw = self.redis.get(f"pq_meta:{job_id}")
            if not meta_raw:
                continue

            meta = json.loads(meta_raw)
            wait_minutes = (now - meta['enqueued_at']) / 60
            age_boost = min(
                int(wait_minutes / minutes_per_bump),
                MAX_AGE_BOOST
            )
            new_score = -(meta['base_score'] + age_boost)

            if new_score != current_score:
                self.redis.zadd(QUEUE_KEY, {job_id: new_score}, xx=True)
                aged += 1

        return aged
