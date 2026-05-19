"""
IVGS v5 — Model Concurrency Manager
=======================================

Tracks loaded models per GPU per §12.1 Table 12-1.

Key behaviors:
- Max 2 concurrent loads per model across the fleet
- Prefers GPUs with model already resident (warm-start, avoids reload)
- LRU eviction when GPU model capacity exceeded
- Tracks model load/unload timestamps for LRU ordering

Redis key structure:
- gpu:models:{node_id}                    — Set of loaded model names
- gpu:model_loads:{node_id}:{gpu_index}   — Hash of model→job_id
- gpu:model_fleet:{model_name}            — Set of node_ids running model
- gpu:model_lru:{node_id}:{gpu_index}     — Sorted set, score=timestamp
- gpu:model_concurrent:{model_name}       — Counter of concurrent loads
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ModelLoadInfo:
    """Information about a model load on a GPU."""

    model_name: str
    node_id: str
    gpu_index: int
    job_id: str
    loaded_at: float
    is_active: bool


# ---------------------------------------------------------------------------
# Model Concurrency Manager
# ---------------------------------------------------------------------------

class ModelConcurrencyManager:
    """
    Model concurrency manager per §12.1 Table 12-1.

    Tracks which models are loaded on which GPUs, enforces
    the max-2-concurrent-loads-per-model limit, and manages
    LRU eviction for GPU model capacity.

    Args:
        redis: Redis connection for state persistence.
        max_concurrent: Max concurrent loads per model (default: 2).
        max_models_per_gpu: Max models loaded on a single GPU.
        metrics: Prometheus metrics collector.
    """

    # Redis key prefixes
    NODE_MODELS_PREFIX = "gpu:models:"
    MODEL_LOADS_PREFIX = "gpu:model_loads:"
    FLEET_MODEL_PREFIX = "gpu:model_fleet:"
    LRU_PREFIX = "gpu:model_lru:"
    CONCURRENT_PREFIX = "gpu:model_concurrent:"

    def __init__(
        self,
        redis: aioredis.Redis,
        max_concurrent: int = 2,
        max_models_per_gpu: int = 4,
        metrics=None,
    ) -> None:
        self._redis = redis
        self._max_concurrent = max_concurrent
        self._max_models_per_gpu = max_models_per_gpu
        self._metrics = metrics

    async def can_accept(
        self,
        node_id: str,
        gpu_index: int,
        model_name: str,
    ) -> bool:
        """
        Check if a GPU can accept a new model load per §12.1.

        Verifies:
        1. Fleet-wide concurrent load count < max_concurrent (2)
        2. GPU model slot available (or model already loaded)

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.
            model_name: Model to check.

        Returns:
            True if the GPU can accept the model load.
        """
        # Check 1: Fleet-wide concurrent load limit
        concurrent_key = f"{self.CONCURRENT_PREFIX}{model_name}"
        concurrent_count = int(await self._redis.get(concurrent_key) or "0")

        # If model is already on this GPU, it doesn't count as new
        is_resident = await self._is_model_resident(node_id, model_name)
        if is_resident:
            # Model already loaded — always accept (warm-start)
            return True

        if concurrent_count >= self._max_concurrent:
            logger.debug(
                "model_concurrent_limit_reached",
                model_name=model_name,
                concurrent=concurrent_count,
                max=self._max_concurrent,
            )
            return False

        # Check 2: GPU model slot availability
        lru_key = f"{self.LRU_PREFIX}{node_id}:{gpu_index}"
        loaded_count = await self._redis.zcard(lru_key)

        if loaded_count >= self._max_models_per_gpu:
            # Need LRU eviction — check if eviction is possible
            # (i.e., there's at least one inactive model to evict)
            can_evict = await self._can_evict(node_id, gpu_index)
            if not can_evict:
                logger.debug(
                    "gpu_model_slots_full_no_eviction",
                    node_id=node_id,
                    gpu_index=gpu_index,
                    loaded=loaded_count,
                    max=self._max_models_per_gpu,
                )
                return False

        return True

    async def record_model_load(
        self,
        node_id: str,
        gpu_index: int,
        model_name: str,
        job_id: str,
    ) -> None:
        """
        Record a model load on a GPU per §12.1.

        If GPU model capacity is exceeded, performs LRU eviction of
        the least recently used inactive model.

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.
            model_name: Model being loaded.
            job_id: Job ID triggering the load.
        """
        now = time.time()
        log = logger.bind(
            node_id=node_id,
            gpu_index=gpu_index,
            model_name=model_name,
            job_id=job_id,
        )

        # Check if eviction needed
        lru_key = f"{self.LRU_PREFIX}{node_id}:{gpu_index}"
        loaded_count = await self._redis.zcard(lru_key)

        is_resident = await self._is_model_resident(node_id, model_name)

        if not is_resident and loaded_count >= self._max_models_per_gpu:
            # Perform LRU eviction
            await self._evict_lru(node_id, gpu_index)

        # Record the model load
        pipe = self._redis.pipeline()

        # Add to node's model set
        node_models_key = f"{self.NODE_MODELS_PREFIX}{node_id}"
        pipe.sadd(node_models_key, model_name)

        # Record load details
        loads_key = f"{self.MODEL_LOADS_PREFIX}{node_id}:{gpu_index}"
        pipe.hset(loads_key, model_name, job_id)

        # Add to fleet-wide model tracking
        fleet_key = f"{self.FLEET_MODEL_PREFIX}{model_name}"
        pipe.sadd(fleet_key, node_id)

        # Update LRU timestamp
        pipe.zadd(lru_key, {model_name: now})

        # Increment concurrent counter (if new load)
        if not is_resident:
            concurrent_key = f"{self.CONCURRENT_PREFIX}{model_name}"
            pipe.incr(concurrent_key)

        await pipe.execute()

        log.info(
            "model_load_recorded",
            is_warm_start=is_resident,
        )

    async def release_model_load(
        self,
        node_id: str,
        gpu_index: int,
        model_name: str,
        job_id: str,
    ) -> None:
        """
        Release a model load after job completion per §12.1.

        The model remains loaded (for warm-start) but the active
        job reference is cleared. LRU timestamp is updated.

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.
            model_name: Model being released.
            job_id: Job ID completing.
        """
        log = logger.bind(
            node_id=node_id,
            gpu_index=gpu_index,
            model_name=model_name,
            job_id=job_id,
        )

        now = time.time()
        pipe = self._redis.pipeline()

        # Clear active job reference
        loads_key = f"{self.MODEL_LOADS_PREFIX}{node_id}:{gpu_index}"
        current_job = await self._redis.hget(loads_key, model_name)
        if current_job == job_id:
            pipe.hdel(loads_key, model_name)

        # Decrement concurrent counter
        concurrent_key = f"{self.CONCURRENT_PREFIX}{model_name}"
        pipe.decr(concurrent_key)

        # Update LRU timestamp (model stays loaded for warm-start)
        lru_key = f"{self.LRU_PREFIX}{node_id}:{gpu_index}"
        pipe.zadd(lru_key, {model_name: now})

        await pipe.execute()

        # Ensure concurrent count doesn't go negative
        concurrent_val = int(await self._redis.get(concurrent_key) or "0")
        if concurrent_val < 0:
            await self._redis.set(concurrent_key, "0")

        log.info("model_load_released")

    async def get_loaded_models(
        self, node_id: str, gpu_index: int
    ) -> List[str]:
        """
        Get models currently loaded on a GPU.

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.

        Returns:
            List of loaded model names.
        """
        lru_key = f"{self.LRU_PREFIX}{node_id}:{gpu_index}"
        return list(await self._redis.zrange(lru_key, 0, -1))

    async def get_model_fleet_distribution(
        self, model_name: str
    ) -> List[str]:
        """
        Get all nodes running a specific model.

        Args:
            model_name: Model name.

        Returns:
            List of node IDs with the model loaded.
        """
        fleet_key = f"{self.FLEET_MODEL_PREFIX}{model_name}"
        return list(await self._redis.smembers(fleet_key))

    async def get_concurrent_count(self, model_name: str) -> int:
        """
        Get concurrent load count for a model across the fleet.

        Args:
            model_name: Model name.

        Returns:
            Number of concurrent loads.
        """
        concurrent_key = f"{self.CONCURRENT_PREFIX}{model_name}"
        return int(await self._redis.get(concurrent_key) or "0")

    async def _is_model_resident(
        self, node_id: str, model_name: str
    ) -> bool:
        """Check if a model is already loaded on a node."""
        node_models_key = f"{self.NODE_MODELS_PREFIX}{node_id}"
        return bool(await self._redis.sismember(node_models_key, model_name))

    async def _can_evict(self, node_id: str, gpu_index: int) -> bool:
        """
        Check if LRU eviction is possible on a GPU.

        A model can be evicted only if it has no active job.
        """
        lru_key = f"{self.LRU_PREFIX}{node_id}:{gpu_index}"
        loads_key = f"{self.MODEL_LOADS_PREFIX}{node_id}:{gpu_index}"

        # Get all loaded models sorted by LRU (oldest first)
        models = await self._redis.zrange(lru_key, 0, -1)

        for model_name in models:
            # Check if model has an active job
            active_job = await self._redis.hget(loads_key, model_name)
            if not active_job:
                return True  # This model can be evicted

        return False  # All models have active jobs

    async def _evict_lru(self, node_id: str, gpu_index: int) -> Optional[str]:
        """
        Evict the least recently used inactive model from a GPU per §12.1.

        Only evicts models without active jobs. Scans from oldest to newest
        in the LRU sorted set.

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.

        Returns:
            Name of evicted model, or None if no eviction possible.
        """
        lru_key = f"{self.LRU_PREFIX}{node_id}:{gpu_index}"
        loads_key = f"{self.MODEL_LOADS_PREFIX}{node_id}:{gpu_index}"

        # Get models sorted by LRU timestamp (oldest first)
        models = await self._redis.zrange(lru_key, 0, -1)

        for model_name in models:
            active_job = await self._redis.hget(loads_key, model_name)
            if not active_job:
                # Evict this model
                pipe = self._redis.pipeline()
                pipe.zrem(lru_key, model_name)
                pipe.srem(f"{self.NODE_MODELS_PREFIX}{node_id}", model_name)
                pipe.srem(f"{self.FLEET_MODEL_PREFIX}{model_name}", node_id)
                await pipe.execute()

                logger.info(
                    "model_evicted_lru",
                    node_id=node_id,
                    gpu_index=gpu_index,
                    evicted_model=model_name,
                )
                return model_name

        logger.warning(
            "no_evictable_model",
            node_id=node_id,
            gpu_index=gpu_index,
            loaded_models=models,
        )
        return None
