"""
IVGS v5 — GPU Node Registry
===============================

Node registration, heartbeat tracking, and dead worker detection per §12.1.

Key responsibilities:
- Register GPU nodes with model/VRAM specifications
- Track heartbeats with 60-second stale threshold per §12.1
- Detect dead workers and release their resources
- Support node draining (no new jobs, existing complete)
- Query available nodes filtered by VRAM and health

All state is persisted in Redis for resilience across scheduler restarts.

Redis key structure:
- gpu:node:{node_id}         — Hash with node metadata
- gpu:nodes:all              — Set of all registered node IDs
- gpu:nodes:alive            — Sorted set by last heartbeat
- gpu:nodes:draining         — Set of draining node IDs
- gpu:node:{node_id}:jobs    — Set of active job IDs on node
- gpu:heartbeat:{node_id}    — String with last heartbeat epoch
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class GpuNodeInfo:
    """GPU node information stored in registry."""

    node_id: str
    node_hostname: str
    gpu_index: int
    gpu_model: str
    total_vram_mb: int
    used_vram_mb: int
    compute_capability: str
    last_heartbeat_epoch: float
    last_heartbeat_iso: str
    is_alive: bool
    is_draining: bool
    gpu_utilization_pct: float
    current_job_id: Optional[str] = None
    worker_id: Optional[str] = None
    heartbeat_data: Optional[Dict[str, Any]] = None

    @property
    def available_vram_mb(self) -> int:
        """Calculate available VRAM."""
        return max(0, self.total_vram_mb - self.used_vram_mb)


# ---------------------------------------------------------------------------
# GPU Registry
# ---------------------------------------------------------------------------

class GpuRegistry:
    """
    GPU node registry with heartbeat tracking per §12.1.

    Manages the fleet of GPU nodes, tracking their health,
    VRAM utilization, and current workload. Dead workers are
    detected after 60 seconds without heartbeat.

    Args:
        redis: Redis connection for state persistence.
        stale_threshold_s: Seconds before a node is considered dead (default: 60).
        metrics: Prometheus metrics collector.
    """

    # Redis key prefixes
    NODE_PREFIX = "gpu:node:"
    ALL_NODES_KEY = "gpu:nodes:all"
    ALIVE_NODES_KEY = "gpu:nodes:alive"
    DRAINING_NODES_KEY = "gpu:nodes:draining"
    NODE_JOBS_PREFIX = "gpu:node_jobs:"
    HEARTBEAT_PREFIX = "gpu:heartbeat:"
    VRAM_USAGE_PREFIX = "gpu:vram_usage:"

    def __init__(
        self,
        redis: aioredis.Redis,
        stale_threshold_s: int = 60,
        metrics=None,
    ) -> None:
        self._redis = redis
        self._stale_threshold_s = stale_threshold_s
        self._metrics = metrics

    def _node_key(self, node_id: str) -> str:
        """Build Redis key for a node."""
        return f"{self.NODE_PREFIX}{node_id}"

    def _make_node_id(self, node_hostname: str, gpu_index: int) -> str:
        """Generate a deterministic node ID from hostname and GPU index."""
        return f"{node_hostname}:gpu{gpu_index}"

    async def register_node(
        self,
        node_hostname: str,
        gpu_index: int,
        gpu_model: str,
        total_vram_mb: int,
        compute_capability: str,
    ) -> str:
        """
        Register a GPU node per §12.3 POST /register.

        Creates or updates a node entry in the registry. Initial registration
        sets used_vram to 0 and marks the node as alive.

        Args:
            node_hostname: Node hostname (e.g., 'node-04').
            gpu_index: GPU device index on the node.
            gpu_model: GPU model name (e.g., 'RTX 5000 Pro').
            total_vram_mb: Total VRAM in megabytes.
            compute_capability: CUDA compute capability.

        Returns:
            Deterministic node ID (e.g., 'node-04:gpu0').
        """
        node_id = self._make_node_id(node_hostname, gpu_index)
        now = time.time()
        now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()

        node_data = {
            "node_id": node_id,
            "node_hostname": node_hostname,
            "gpu_index": str(gpu_index),
            "gpu_model": gpu_model,
            "total_vram_mb": str(total_vram_mb),
            "used_vram_mb": "0",
            "compute_capability": compute_capability,
            "last_heartbeat_epoch": str(now),
            "last_heartbeat_iso": now_iso,
            "is_draining": "0",
            "gpu_utilization_pct": "0.0",
            "current_job_id": "",
            "worker_id": "",
            "registered_at": now_iso,
        }

        pipe = self._redis.pipeline()
        pipe.hset(self._node_key(node_id), mapping=node_data)
        pipe.sadd(self.ALL_NODES_KEY, node_id)
        pipe.zadd(self.ALIVE_NODES_KEY, {node_id: now})
        pipe.set(f"{self.HEARTBEAT_PREFIX}{node_id}", str(now))
        await pipe.execute()

        if self._metrics:
            self._metrics.set_vram_used(node_id, gpu_index, 0)
            self._metrics.set_gpu_utilization(node_id, gpu_index, 0.0)

        logger.info(
            "node_registered",
            node_id=node_id,
            gpu_model=gpu_model,
            total_vram_mb=total_vram_mb,
        )

        return node_id

    async def update_heartbeat(
        self,
        worker_id: str,
        node_hostname: str,
        gpu_index: int,
        current_job_id: Optional[str] = None,
        heartbeat_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update worker heartbeat per §12.3 PUT /heartbeat.

        Updates the node's last heartbeat timestamp and optional
        utilization metrics. Workers must call this within the
        5-minute reservation TTL per §12.2.

        Args:
            worker_id: Worker process identifier.
            node_hostname: Node hostname.
            gpu_index: GPU device index.
            current_job_id: Currently executing job ID (if any).
            heartbeat_data: Additional data (GPU util, temp, etc.).

        Raises:
            NodeNotFoundError: If the node is not registered.
        """
        node_id = self._make_node_id(node_hostname, gpu_index)
        node_key = self._node_key(node_id)

        exists = await self._redis.exists(node_key)
        if not exists:
            from main import NodeNotFoundError
            raise NodeNotFoundError(
                f"Node '{node_id}' not found in registry. "
                f"Call POST /register first."
            )

        now = time.time()
        now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()

        updates = {
            "last_heartbeat_epoch": str(now),
            "last_heartbeat_iso": now_iso,
            "worker_id": worker_id,
            "current_job_id": current_job_id or "",
        }

        # Extract GPU utilization from heartbeat data
        gpu_util = 0.0
        if heartbeat_data:
            gpu_util = float(heartbeat_data.get("gpu_utilization_pct", 0.0))
            updates["gpu_utilization_pct"] = str(gpu_util)

            # Store temperature if provided
            if "gpu_temperature_c" in heartbeat_data:
                updates["gpu_temperature_c"] = str(
                    heartbeat_data["gpu_temperature_c"]
                )

        pipe = self._redis.pipeline()
        pipe.hset(node_key, mapping=updates)
        pipe.zadd(self.ALIVE_NODES_KEY, {node_id: now})
        pipe.set(f"{self.HEARTBEAT_PREFIX}{node_id}", str(now))
        await pipe.execute()

        if self._metrics:
            self._metrics.set_gpu_utilization(node_id, gpu_index, gpu_util)

        logger.debug(
            "heartbeat_updated",
            node_id=node_id,
            worker_id=worker_id,
            current_job_id=current_job_id,
            gpu_util=gpu_util,
        )

    async def detect_dead_nodes(self) -> List[str]:
        """
        Detect nodes with stale heartbeats (>60s threshold per §12.1).

        Returns:
            List of dead node IDs removed from the alive set.
        """
        cutoff = time.time() - self._stale_threshold_s
        # Get nodes with heartbeats older than cutoff
        dead_ids = await self._redis.zrangebyscore(
            self.ALIVE_NODES_KEY, "-inf", str(cutoff)
        )

        if dead_ids:
            pipe = self._redis.pipeline()
            for node_id in dead_ids:
                pipe.zrem(self.ALIVE_NODES_KEY, node_id)
            await pipe.execute()

            for node_id in dead_ids:
                logger.warning(
                    "dead_node_detected",
                    node_id=node_id,
                    stale_threshold_s=self._stale_threshold_s,
                )

        return list(dead_ids)

    async def get_alive_nodes(self) -> List[GpuNodeInfo]:
        """
        Get all alive (non-stale) GPU nodes.

        Returns:
            List of GpuNodeInfo for alive nodes, excluding draining nodes.
        """
        cutoff = time.time() - self._stale_threshold_s
        alive_ids = await self._redis.zrangebyscore(
            self.ALIVE_NODES_KEY, str(cutoff), "+inf"
        )

        draining_ids = await self._redis.smembers(self.DRAINING_NODES_KEY)

        nodes: List[GpuNodeInfo] = []
        for node_id in alive_ids:
            if node_id in draining_ids:
                continue
            node = await self._get_node_info(node_id)
            if node is not None:
                nodes.append(node)

        return nodes

    async def get_all_nodes(self) -> List[GpuNodeInfo]:
        """
        Get all registered GPU nodes (alive and dead).

        Returns:
            List of GpuNodeInfo for all registered nodes.
        """
        all_ids = await self._redis.smembers(self.ALL_NODES_KEY)
        cutoff = time.time() - self._stale_threshold_s
        draining_ids = await self._redis.smembers(self.DRAINING_NODES_KEY)

        nodes: List[GpuNodeInfo] = []
        for node_id in all_ids:
            node = await self._get_node_info(node_id)
            if node is not None:
                # Determine alive status
                hb_str = await self._redis.get(
                    f"{self.HEARTBEAT_PREFIX}{node_id}"
                )
                if hb_str:
                    node.is_alive = float(hb_str) >= cutoff
                else:
                    node.is_alive = False
                node.is_draining = node_id in draining_ids
                nodes.append(node)

        return nodes

    async def _get_node_info(self, node_id: str) -> Optional[GpuNodeInfo]:
        """
        Load node information from Redis.

        Args:
            node_id: Node identifier.

        Returns:
            GpuNodeInfo if found, None otherwise.
        """
        data = await self._redis.hgetall(self._node_key(node_id))
        if not data:
            return None

        cutoff = time.time() - self._stale_threshold_s
        last_hb = float(data.get("last_heartbeat_epoch", "0"))
        draining_ids = await self._redis.smembers(self.DRAINING_NODES_KEY)

        return GpuNodeInfo(
            node_id=data["node_id"],
            node_hostname=data["node_hostname"],
            gpu_index=int(data["gpu_index"]),
            gpu_model=data["gpu_model"],
            total_vram_mb=int(data["total_vram_mb"]),
            used_vram_mb=int(data.get("used_vram_mb", "0")),
            compute_capability=data["compute_capability"],
            last_heartbeat_epoch=last_hb,
            last_heartbeat_iso=data.get("last_heartbeat_iso", ""),
            is_alive=last_hb >= cutoff,
            is_draining=node_id in draining_ids,
            gpu_utilization_pct=float(data.get("gpu_utilization_pct", "0.0")),
            current_job_id=data.get("current_job_id") or None,
            worker_id=data.get("worker_id") or None,
        )

    async def drain_node(self, node_id: str) -> int:
        """
        Mark a node for draining per §12.3 POST /drain/{node_id}.

        Draining nodes accept no new jobs but continue processing active ones.

        Args:
            node_id: Node identifier to drain.

        Returns:
            Number of active jobs on the draining node.

        Raises:
            NodeNotFoundError: If the node is not registered.
        """
        node_key = self._node_key(node_id)
        exists = await self._redis.exists(node_key)
        if not exists:
            from main import NodeNotFoundError
            raise NodeNotFoundError(f"Node '{node_id}' not found in registry")

        await self._redis.sadd(self.DRAINING_NODES_KEY, node_id)
        await self._redis.hset(node_key, "is_draining", "1")

        # Count active jobs
        jobs_key = f"{self.NODE_JOBS_PREFIX}{node_id}"
        active_jobs = await self._redis.scard(jobs_key)

        logger.info(
            "node_draining",
            node_id=node_id,
            active_jobs=active_jobs,
        )

        return active_jobs

    async def undrain_node(self, node_id: str) -> None:
        """
        Remove draining status from a node.

        Args:
            node_id: Node identifier to undrain.
        """
        await self._redis.srem(self.DRAINING_NODES_KEY, node_id)
        node_key = self._node_key(node_id)
        await self._redis.hset(node_key, "is_draining", "0")

        logger.info("node_undrained", node_id=node_id)

    async def add_vram_usage(
        self, node_id: str, gpu_index: int, vram_mb: int
    ) -> None:
        """
        Increment VRAM usage for a node.

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.
            vram_mb: VRAM amount to add in megabytes.
        """
        node_key = self._node_key(node_id)
        await self._redis.hincrby(node_key, "used_vram_mb", vram_mb)

        if self._metrics:
            used = int(await self._redis.hget(node_key, "used_vram_mb") or "0")
            self._metrics.set_vram_used(node_id, gpu_index, used)

    async def release_vram_usage(
        self, node_id: str, gpu_index: int, vram_mb: int
    ) -> None:
        """
        Decrement VRAM usage for a node.

        Args:
            node_id: Node identifier.
            gpu_index: GPU device index.
            vram_mb: VRAM amount to release in megabytes.
        """
        node_key = self._node_key(node_id)
        current = int(
            await self._redis.hget(node_key, "used_vram_mb") or "0"
        )
        new_usage = max(0, current - vram_mb)
        await self._redis.hset(node_key, "used_vram_mb", str(new_usage))

        if self._metrics:
            self._metrics.set_vram_used(node_id, gpu_index, new_usage)

    async def get_node_jobs(self, node_id: str) -> List[str]:
        """
        Get active job IDs on a node.

        Args:
            node_id: Node identifier.

        Returns:
            List of active job IDs.
        """
        jobs_key = f"{self.NODE_JOBS_PREFIX}{node_id}"
        return list(await self._redis.smembers(jobs_key))

    async def add_node_job(self, node_id: str, job_id: str) -> None:
        """Track a job as active on a node."""
        jobs_key = f"{self.NODE_JOBS_PREFIX}{node_id}"
        await self._redis.sadd(jobs_key, job_id)

    async def remove_node_job(self, node_id: str, job_id: str) -> None:
        """Remove a job from the node's active list."""
        jobs_key = f"{self.NODE_JOBS_PREFIX}{node_id}"
        await self._redis.srem(jobs_key, job_id)

    async def get_nodes_with_model(self, model_name: str) -> List[str]:
        """
        Get node IDs that have a specific model loaded.

        Used by the scheduler for warm-start preferences per §12.1.

        Args:
            model_name: Model name to search for.

        Returns:
            List of node IDs with the model loaded.
        """
        # Model tracking is handled by ModelConcurrencyManager
        # This is a convenience query
        all_ids = await self._redis.smembers(self.ALL_NODES_KEY)
        result: List[str] = []
        for node_id in all_ids:
            models_key = f"gpu:models:{node_id}"
            is_loaded = await self._redis.sismember(models_key, model_name)
            if is_loaded:
                result.append(node_id)
        return result

    async def remove_node(self, node_id: str) -> None:
        """
        Remove a node from the registry entirely.

        Args:
            node_id: Node identifier to remove.
        """
        pipe = self._redis.pipeline()
        pipe.delete(self._node_key(node_id))
        pipe.srem(self.ALL_NODES_KEY, node_id)
        pipe.zrem(self.ALIVE_NODES_KEY, node_id)
        pipe.srem(self.DRAINING_NODES_KEY, node_id)
        pipe.delete(f"{self.HEARTBEAT_PREFIX}{node_id}")
        pipe.delete(f"{self.NODE_JOBS_PREFIX}{node_id}")
        pipe.delete(f"{self.VRAM_USAGE_PREFIX}{node_id}")
        await pipe.execute()

        logger.info("node_removed", node_id=node_id)
