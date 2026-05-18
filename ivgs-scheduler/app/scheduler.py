"""GpuScheduler — VRAM-aware bin-packing scheduling engine.

Implements first-fit bin-packing: sorts online GPU nodes by available
VRAM descending, assigns the job to the first node with sufficient
VRAM, creates a reservation with TTL, and returns the assignment.

Usage:
    sched = GpuScheduler(db_session)
    node_id, gpu_index, reservation_id = sched.schedule_job(
        job_id=42,
        model_name="sdxl",
        vram_requirement_mb=8192,
        estimated_duration_seconds=120,
    )
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

# These models are defined in the shared ivgs-api app package,
# accessed via the shared PostgreSQL database. The scheduler imports
# them from a local stub that maps to the same table names.
from app.db_models import GpuNode, GpuReservation

logger = logging.getLogger(__name__)

RESERVATION_TTL_SECONDS = 300  # 5 minutes


class NoCapacityError(Exception):
    """Raised when no GPU has sufficient VRAM for the requested task."""


class GpuScheduler:
    """Core scheduling engine for the GPU Scheduler microservice.

    All scheduling decisions are backed by PostgreSQL (gpu_nodes and
    gpu_reservations tables). Redis is used for caching fleet status
    to avoid hot-path DB queries on every heartbeat.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def schedule_job(
        self,
        job_id: Optional[int],
        model_name: str,
        vram_requirement_mb: int,
        estimated_duration_seconds: int = 300,
    ) -> Tuple[int, int, int]:
        """Find and reserve a GPU for the given task.

        Implements first-fit bin-packing:
        1. Get all online GPU nodes sorted by available VRAM desc.
        2. Skip nodes without enough free VRAM.
        3. Assign to first qualifying node.
        4. Create a reservation with TTL.

        Args:
            job_id:                    ID of the job to schedule (for reservation).
            model_name:                Model to be loaded (for residency tracking).
            vram_requirement_mb:       Minimum VRAM required in MB.
            estimated_duration_seconds: Used to set reservation expiry.

        Returns:
            Tuple of (gpu_node_id, gpu_index, reservation_id).

        Raises:
            NoCapacityError: If no GPU meets the VRAM requirement.
        """
        # Clean expired reservations before scheduling
        self._cleanup_expired_reservations()

        candidates = self._get_sorted_candidates(vram_requirement_mb)

        if not candidates:
            raise NoCapacityError(
                f"No GPU with {vram_requirement_mb}MB VRAM available. "
                f"All nodes are at capacity or offline."
            )

        # Prefer nodes where the model is already loaded (residency affinity)
        preferred = self._apply_residency_affinity(candidates, model_name)
        chosen = preferred[0]

        # Create reservation
        ttl = max(estimated_duration_seconds + 60, RESERVATION_TTL_SECONDS)
        reservation = GpuReservation(
            gpu_node_id=chosen.id,
            job_id=job_id,
            reserved_vram_mb=vram_requirement_mb,
            model_name=model_name,
            status="reserved",
            reserved_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        )
        self.db.add(reservation)
        self.db.flush()

        logger.info(
            "Scheduled: job=%s model=%s node=%s gpu=%d vram=%dMB "
            "reservation=%d ttl=%ds",
            job_id, model_name, chosen.node_hostname, chosen.gpu_index,
            vram_requirement_mb, reservation.id, ttl,
        )

        return chosen.id, chosen.gpu_index, reservation.id

    def release_reservation(self, reservation_id: int) -> None:
        """Release a GPU reservation, freeing VRAM for future jobs."""
        reservation = (
            self.db.query(GpuReservation)
            .filter_by(id=reservation_id)
            .first()
        )
        if reservation is None:
            logger.warning("Release called on unknown reservation %d",
                           reservation_id)
            return

        reservation.release()
        self.db.flush()
        logger.info("Released reservation %d (vram=%dMB freed)",
                    reservation_id, reservation.reserved_vram_mb)

    def get_fleet_status(self) -> "FleetStatus":
        """Build a fleet-wide GPU availability summary."""
        from app.models import FleetStatus, NodeStatus

        nodes = self.db.query(GpuNode).all()
        node_statuses = []

        for node in nodes:
            active_reservations = [
                r for r in node.reservations
                if r.status in ("reserved", "active") and not r.is_expired()
            ]
            node_statuses.append(NodeStatus(
                node_id=node.id,
                hostname=node.node_hostname,
                gpu_index=node.gpu_index,
                gpu_model=node.gpu_model,
                total_vram_mb=node.total_vram_mb,
                available_vram_mb=node.available_vram_mb,
                status=node.status,
                active_reservations=len(active_reservations),
                is_alive=node.is_alive,
            ))

        total_vram = sum(n.total_vram_mb for n in nodes)
        used_vram = sum(n.total_vram_mb - n.available_vram_mb for n in nodes)

        return FleetStatus(
            nodes=node_statuses,
            total_vram_mb=total_vram,
            used_vram_mb=used_vram,
            utilization_pct=round(used_vram / total_vram * 100, 1)
            if total_vram else 0.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_sorted_candidates(
        self, min_vram_mb: int
    ) -> List[GpuNode]:
        """Return online GPU nodes with sufficient VRAM, best first."""
        nodes = (
            self.db.query(GpuNode)
            .filter(GpuNode.status == "online")
            .all()
        )

        eligible = [n for n in nodes if n.available_vram_mb >= min_vram_mb
                    and n.is_alive]

        # Sort by available VRAM descending (best-fit bin-packing variant)
        eligible.sort(key=lambda n: n.available_vram_mb, reverse=True)
        return eligible

    def _apply_residency_affinity(
        self, candidates: List[GpuNode], model_name: str
    ) -> List[GpuNode]:
        """Reorder candidates to prefer nodes with model already loaded."""
        resident = []
        non_resident = []

        for node in candidates:
            has_model = any(
                r.model_name == model_name
                and r.status == "active"
                for r in node.reservations
            )
            if has_model:
                resident.append(node)
            else:
                non_resident.append(node)

        return resident + non_resident

    def _cleanup_expired_reservations(self) -> int:
        """Mark expired reservations as 'expired' to free VRAM."""
        now = datetime.now(timezone.utc)
        expired = (
            self.db.query(GpuReservation)
            .filter(
                GpuReservation.status.in_(["reserved"]),
                GpuReservation.expires_at <= now,
            )
            .all()
        )
        for r in expired:
            r.status = "expired"
            r.released_at = now

        if expired:
            self.db.flush()
            logger.info("Expired %d stale GPU reservations", len(expired))

        return len(expired)
