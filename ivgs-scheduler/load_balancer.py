"""
IVGS v5 — GPU Load Balancer
===============================

Weighted random GPU selection per §12.1 Table 12-1.

Weight formula per spec:
    weight = (1 - gpu_util) × (1 - mem_util) × (max_queue - current_queue)

Higher weight = more available capacity = higher selection probability.
Metrics are stored in Redis time-series for historical tracking.
Imbalance alert fires if weight stddev >30% across the fleet.

The load balancer works in conjunction with the scheduler's first-fit
bin-packing to select candidates ordered by desirability, with the
scheduler making the final allocation based on VRAM availability.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)

#: Weight prior for a node whose heartbeat carried NO utilisation reading.
#: WP-IVGS-06 Task 1.
#:
#: DELIBERATELY NOT 0.0, and the choice is load-bearing. The §12.1 weight is
#: ``(1 - gpu_util) x (1 - mem_util) x queue_headroom``, so ``gpu_util = 0.0``
#: is the MAXIMUM weight -- an unmeasured GPU would be preferred over every
#: measured one, attracting work because nothing is known about it. That is
#: WP-60's lying zero with the sign flipped against us.
#:
#: 0.5 is a neutral prior: it neither rewards nor punishes the absence of a
#: reading. When NO node reports -- today's fleet -- every candidate carries the
#: same factor, it cancels from the ranking, and selection falls back to VRAM
#: and queue depth, both of which are actually measured.
UNKNOWN_GPU_UTIL_PRIOR = 0.5


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LoadBalancerConfig:
    """Load balancer configuration per §12.1."""

    max_queue_per_gpu: int = 10
    imbalance_stddev_threshold: float = 0.30
    metrics_ttl_s: int = 3600
    weight_epsilon: float = 0.001


# ---------------------------------------------------------------------------
# Load Balancer
# ---------------------------------------------------------------------------

class LoadBalancer:
    """
    Weighted random GPU load balancer per §12.1.

    Computes a weight for each GPU node based on current utilization
    and queue depth, then selects candidates using weighted random
    distribution for even load spreading.

    Args:
        redis: Redis connection for metrics time-series.
        registry: GPU node registry for node queries.
        metrics: Prometheus metrics collector.
        config: Load balancer configuration.
    """

    # Redis key prefixes
    METRICS_TS_PREFIX = "lb:metrics:"
    WEIGHT_HISTORY_PREFIX = "lb:weights:"

    def __init__(
        self,
        redis: aioredis.Redis,
        registry,
        metrics=None,
        config: Optional[LoadBalancerConfig] = None,
    ) -> None:
        self._redis = redis
        self._registry = registry
        self._metrics = metrics
        self._config = config or LoadBalancerConfig()

    async def get_weighted_candidates(
        self,
        model_name: str,
        vram_requirement_mb: int,
    ) -> List:
        """
        Get GPU candidates ranked by weighted random selection per §12.1.

        Computes weights for all alive, non-draining nodes with sufficient
        VRAM, then returns them sorted by weight (highest first) for the
        scheduler's first-fit allocation.

        Args:
            model_name: Model name for warm-start checking.
            vram_requirement_mb: Minimum VRAM needed.

        Returns:
            List of GpuCandidate objects sorted by weight descending.
        """
        from scheduler import GpuCandidate

        alive_nodes = await self._registry.get_alive_nodes()
        if not alive_nodes:
            logger.warning("no_alive_nodes_for_balancing")
            return []

        candidates: List[GpuCandidate] = []
        weights: List[float] = []
        unmeasured_nodes: List[str] = []

        for node in alive_nodes:
            available_vram = node.total_vram_mb - node.used_vram_mb
            if available_vram < vram_requirement_mb:
                continue

            # Check if model is already loaded on this GPU
            has_model = await self._check_model_loaded(
                node.node_id, model_name
            )

            # Get current queue depth for this node
            queue_depth = await self._get_queue_depth(node.node_id)

            # Compute weight per §12.1 formula:
            # weight = (1 - gpu_util) × (1 - mem_util) × (max_queue - current_queue)
            #
            # WP-IVGS-06 Task 1. `gpu_utilization_pct` IS NULLABLE and this line
            # divided by it unguarded, so EVERY /schedule call raised
            # `TypeError: unsupported operand type(s) for /: 'NoneType' and
            # 'float'` -> HTTP 500 -> every GPU stage fail-open UNRESERVED.
            #
            # WP-60 (`b94ec6f`) made the field `Optional[float] = None` for a
            # good reason: a worker whose `nvidia-smi` call failed used to have
            # a confident 0% recorded, indistinguishable from a genuinely idle
            # GPU. That fix was right. This consumer was never updated to match
            # -- `load_balancer.py` has not been touched since `48dc12f` -- so a
            # correctness fix in the producer became a crash in the consumer.
            #
            # ⛔ THE UNKNOWN CASE IS NOT 0.0. Substituting zero here would put
            # WP-60's lying zero straight back, one layer down, and it is worse
            # here than it was there: `1 - 0.0 = 1.0` is the MAXIMUM weight, so
            # an unmeasured GPU would outrank every measured one and attract
            # the work precisely because nothing is known about it.
            #
            # A declared neutral prior instead. When no node has a reading --
            # today's fleet state -- every candidate takes the same prior, the
            # term cancels out of the ranking, and selection degrades to the
            # VRAM and queue-depth factors, which ARE measured. That is the
            # honest behaviour: rank on what is known, do not invent the rest.
            util_pct = node.gpu_utilization_pct
            if util_pct is None:
                gpu_util = UNKNOWN_GPU_UTIL_PRIOR
                unmeasured_nodes.append(node.node_id)
            else:
                gpu_util = util_pct / 100.0
            mem_util = node.used_vram_mb / max(node.total_vram_mb, 1)
            queue_headroom = max(
                0,
                self._config.max_queue_per_gpu - queue_depth,
            )

            weight = (
                (1.0 - gpu_util)
                * (1.0 - mem_util)
                * queue_headroom
            )

            # Ensure minimum weight to prevent zero-weight nodes
            weight = max(weight, self._config.weight_epsilon)

            candidate = GpuCandidate(
                node_id=node.node_id,
                gpu_index=node.gpu_index,
                gpu_model=node.gpu_model,
                total_vram_mb=node.total_vram_mb,
                used_vram_mb=node.used_vram_mb,
                available_vram_mb=available_vram,
                gpu_utilization_pct=node.gpu_utilization_pct,
                has_model_loaded=has_model,
                weight=weight,
                queue_depth=queue_depth,
            )
            candidates.append(candidate)
            weights.append(weight)

        # NAMED, not silent. Scheduling still happened; it happened on less
        # information than the formula assumes, and an operator reading these
        # logs should be able to tell those two states apart.
        if unmeasured_nodes:
            logger.warning(
                "gpu_utilization_unknown_using_prior",
                nodes=sorted(set(unmeasured_nodes)),
                unmeasured_count=len(set(unmeasured_nodes)),
                prior=UNKNOWN_GPU_UTIL_PRIOR,
                effect=(
                    "weight ranking falls back to VRAM and queue depth for "
                    "these nodes; their heartbeats carried no nvidia-smi reading"
                ),
            )

        if not candidates:
            logger.warning(
                "no_candidates_after_filtering",
                total_nodes=len(alive_nodes),
                vram_requirement_mb=vram_requirement_mb,
            )
            return []

        # Store weight metrics in Redis time-series
        await self._record_weight_metrics(candidates)

        # Check for imbalance
        await self._check_imbalance(weights)

        # Sort by weight descending (scheduler does first-fit on sorted list)
        candidates.sort(key=lambda c: c.weight, reverse=True)

        logger.debug(
            "candidates_weighted",
            count=len(candidates),
            weights=[round(c.weight, 3) for c in candidates],
        )

        return candidates

    async def select_weighted_random(
        self,
        candidates: List,
    ) -> Optional[Any]:
        """
        Select a single candidate using weighted random distribution.

        Used when the caller wants probabilistic load spreading rather
        than deterministic first-fit.

        Args:
            candidates: List of GpuCandidate objects with weights.

        Returns:
            Selected GpuCandidate, or None if no candidates.
        """
        if not candidates:
            return None

        weights = [c.weight for c in candidates]
        total_weight = sum(weights)
        if total_weight <= 0:
            return random.choice(candidates)

        # Weighted random selection
        r = random.uniform(0, total_weight)
        cumulative = 0.0
        for candidate in candidates:
            cumulative += candidate.weight
            if r <= cumulative:
                return candidate

        return candidates[-1]  # Fallback to last

    async def _check_model_loaded(
        self, node_id: str, model_name: str
    ) -> bool:
        """Check if a model is already loaded on a node's GPU."""
        models_key = f"gpu:models:{node_id}"
        return bool(await self._redis.sismember(models_key, model_name))

    async def _get_queue_depth(self, node_id: str) -> int:
        """Get current job queue depth for a node."""
        jobs_key = f"gpu:node_jobs:{node_id}"
        return await self._redis.scard(jobs_key)

    async def _record_weight_metrics(
        self, candidates: List
    ) -> None:
        """
        Record weight metrics in Redis for historical tracking.

        Uses sorted sets with timestamps as scores for time-series data.
        """
        now = time.time()
        pipe = self._redis.pipeline()

        for candidate in candidates:
            ts_key = f"{self.METRICS_TS_PREFIX}{candidate.node_id}"
            pipe.zadd(ts_key, {f"{now}:{candidate.weight:.4f}": now})
            # Trim to keep only last hour
            cutoff = now - self._config.metrics_ttl_s
            pipe.zremrangebyscore(ts_key, "-inf", str(cutoff))

        await pipe.execute()

    async def _check_imbalance(self, weights: List[float]) -> None:
        """
        Check fleet weight imbalance per §12.1.

        Fires a warning if stddev of weights exceeds 30% of mean.
        """
        if len(weights) < 2:
            return

        mean = sum(weights) / len(weights)
        if mean <= 0:
            return

        variance = sum((w - mean) ** 2 for w in weights) / len(weights)
        stddev = math.sqrt(variance)
        relative_stddev = stddev / mean

        if relative_stddev > self._config.imbalance_stddev_threshold:
            logger.warning(
                "fleet_weight_imbalance",
                stddev=round(stddev, 4),
                mean=round(mean, 4),
                relative_stddev=round(relative_stddev, 4),
                threshold=self._config.imbalance_stddev_threshold,
                weights=[round(w, 3) for w in weights],
            )

    async def get_node_weight_history(
        self, node_id: str, lookback_s: int = 3600
    ) -> List[Tuple[float, float]]:
        """
        Get weight history for a specific node.

        Args:
            node_id: Node identifier.
            lookback_s: How far back to look in seconds.

        Returns:
            List of (timestamp, weight) tuples.
        """
        ts_key = f"{self.METRICS_TS_PREFIX}{node_id}"
        cutoff = time.time() - lookback_s
        entries = await self._redis.zrangebyscore(
            ts_key, str(cutoff), "+inf", withscores=True
        )

        history: List[Tuple[float, float]] = []
        for entry_str, score in entries:
            parts = str(entry_str).split(":")
            if len(parts) == 2:
                try:
                    weight = float(parts[1])
                    history.append((score, weight))
                except ValueError:
                    continue

        return history
