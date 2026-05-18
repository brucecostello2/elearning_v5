"""GpuRegistry — GPU node registration and heartbeat tracking."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db_models import GpuNode

logger = logging.getLogger(__name__)

# Threshold after which a node is considered dead
DEAD_THRESHOLD_SECONDS = 60
CONFIRMED_DEAD_SECONDS = 120


class GpuRegistry:
    """Manages GPU node lifecycle: registration, heartbeats, drain, removal."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register_node(
        self,
        hostname: str,
        gpu_index: int,
        gpu_model: str,
        total_vram_mb: int,
        compute_capability: Optional[str] = None,
    ) -> int:
        """Register a GPU node, or update it if already registered.

        Called by workers on startup. Safe to call multiple times for
        the same (hostname, gpu_index) — will update the existing record.

        Args:
            hostname:           VM/container hostname.
            gpu_index:          GPU device index (0-based).
            gpu_model:          Human-readable model name (e.g., "NVIDIA RTX 3090").
            total_vram_mb:      Total VRAM in MB.
            compute_capability: CUDA compute capability string.

        Returns:
            id of the GpuNode record.
        """
        existing = (
            self.db.query(GpuNode)
            .filter_by(node_hostname=hostname, gpu_index=gpu_index)
            .first()
        )

        now = datetime.now(timezone.utc)

        if existing is not None:
            existing.gpu_model = gpu_model
            existing.total_vram_mb = total_vram_mb
            existing.compute_capability = compute_capability
            existing.status = "online"
            existing.last_heartbeat_at = now
            self.db.flush()
            logger.info("Re-registered GPU: %s:gpu%d (%s, %dMB)",
                        hostname, gpu_index, gpu_model, total_vram_mb)
            return existing.id

        node = GpuNode(
            node_hostname=hostname,
            gpu_index=gpu_index,
            gpu_model=gpu_model,
            total_vram_mb=total_vram_mb,
            compute_capability=compute_capability,
            status="online",
            last_heartbeat_at=now,
        )
        self.db.add(node)
        self.db.flush()
        logger.info("Registered new GPU: %s:gpu%d (%s, %dMB)",
                    hostname, gpu_index, gpu_model, total_vram_mb)
        return node.id

    def update_heartbeat(
        self,
        hostname: str,
        gpu_index: int,
        metrics: Dict[str, Any],
    ) -> bool:
        """Update last_heartbeat_at and metrics for a node.

        Args:
            hostname:  Node hostname.
            gpu_index: GPU device index.
            metrics:   Dict with keys: gpu_util_pct, mem_used_mb,
                       mem_total_mb, temperature_c, power_draw_w.

        Returns:
            True if node was found and updated, False otherwise.
        """
        node = (
            self.db.query(GpuNode)
            .filter_by(node_hostname=hostname, gpu_index=gpu_index)
            .first()
        )
        if node is None:
            logger.warning("Heartbeat for unknown node: %s:gpu%d",
                           hostname, gpu_index)
            return False

        node.last_heartbeat_at = datetime.now(timezone.utc)
        if node.status in ("offline", "suspected_dead"):
            node.status = "online"
            logger.info("Node recovered: %s:gpu%d", hostname, gpu_index)

        self.db.flush()
        return True

    def detect_dead_workers(
        self,
        threshold_seconds: int = DEAD_THRESHOLD_SECONDS,
    ) -> List[GpuNode]:
        """Find nodes whose heartbeat has gone silent.

        Args:
            threshold_seconds: Seconds since last heartbeat before marking dead.

        Returns:
            List of GpuNode instances that have been marked offline/dead.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)
        silent_nodes = (
            self.db.query(GpuNode)
            .filter(
                GpuNode.status == "online",
                GpuNode.last_heartbeat_at <= cutoff,
            )
            .all()
        )

        for node in silent_nodes:
            age = (
                datetime.now(timezone.utc) - node.last_heartbeat_at
            ).total_seconds()
            if age > CONFIRMED_DEAD_SECONDS:
                node.status = "offline"
                logger.error("Node confirmed dead: %s:gpu%d (silent %.0fs)",
                             node.node_hostname, node.gpu_index, age)
            else:
                node.status = "suspected_dead"
                logger.warning("Node suspected dead: %s:gpu%d (silent %.0fs)",
                               node.node_hostname, node.gpu_index, age)

        if silent_nodes:
            self.db.flush()

        return silent_nodes

    def get_available_nodes(self, min_vram_mb: int = 0) -> List[GpuNode]:
        """Return online nodes with at least min_vram_mb available."""
        return [
            n for n in self.db.query(GpuNode)
            .filter(GpuNode.status == "online").all()
            if n.available_vram_mb >= min_vram_mb and n.is_alive
        ]

    def drain_node(self, node_id: int) -> None:
        """Stop scheduling new tasks to a node (maintenance/decommission)."""
        node = self.db.query(GpuNode).filter_by(id=node_id).first()
        if node:
            node.status = "draining"
            self.db.flush()
            logger.info("Node %d (%s:gpu%d) set to draining",
                        node_id, node.node_hostname, node.gpu_index)

    def get_node(self, hostname: str, gpu_index: int) -> Optional[GpuNode]:
        """Fetch a node by hostname and GPU index."""
        return (
            self.db.query(GpuNode)
            .filter_by(node_hostname=hostname, gpu_index=gpu_index)
            .first()
        )
