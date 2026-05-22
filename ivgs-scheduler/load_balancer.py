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
            gpu_util = node.gpu_utilization_pct / 100.0
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
