"""
GPU service: node registry, reservation management, fleet utilization,
and time-series history (per GPU Fleet Monitoring Spec v1.1).

Per §5.2.1 — manages GPU node lifecycle and VRAM reservation tracking.
Actual GPU scheduling logic is in Phase 8 (GPU Scheduler microservice).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.gpu_node import GpuNode, GpuReservation
from app.models.gpu_metrics_history import GpuMetricsHistory
from app.models.render_job import RenderJob
from app.models.project import Project
from app.schemas.gpu import (
    GpuNodeCreate,
    GpuNodeUpdate,
    GpuNodeResponse,
    GpuReservationResponse,
    GpuFleetSummary,
    GpuNodeSummary,
    ActiveJobSummary,
    GpuUtilizationPoint,
)

logger = logging.getLogger(__name__)

# Maximum points returned in a single history response.
# Per GPU Fleet Monitoring Spec v1.1 §3.3 / amendment 5.
# A 30d range at 30-second collection x 5 nodes ~ 432,000 rows - protects
# against unbounded responses. Returns 413 rather than silent truncation.
MAX_HISTORY_POINTS = 5000


class GpuService:
    """Business logic for GPU node and reservation management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_nodes(
        self,
        page: int = 1,
        per_page: int = 50,
        status_filter: Optional[str] = None,
    ) -> Tuple[List[GpuNodeResponse], int]:
        """
        List all registered GPU nodes with current status and VRAM utilization.

        Returns paginated list with computed fields.
        """
        query = select(GpuNode).options(selectinload(GpuNode.reservations))

        if status_filter:
            query = query.where(GpuNode.status == status_filter)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(GpuNode.node_hostname, GpuNode.gpu_index)
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        nodes = result.scalars().unique().all()

        responses = []
        for node in nodes:
            responses.append(await self._to_response(node))

        return responses, total

    async def get_node(self, node_id: UUID) -> Optional[GpuNodeResponse]:
        """Get a single GPU node by ID with reservations."""
        result = await self.db.execute(
            select(GpuNode)
            .options(selectinload(GpuNode.reservations))
            .where(GpuNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        if node is None:
            return None
        return await self._to_response(node)

    async def register_node(self, data: GpuNodeCreate) -> GpuNodeResponse:
        """
        Register a new GPU node or update existing.

        Uses upsert logic: if (node_hostname, gpu_index) already exists,
        update the record instead of creating a duplicate.
        """
        existing_result = await self.db.execute(
            select(GpuNode).where(
                GpuNode.node_hostname == data.node_hostname,
                GpuNode.gpu_index == data.gpu_index,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            if data.gpu_model is not None:
                existing.gpu_model = data.gpu_model
            if data.total_vram_mb is not None:
                existing.total_vram_mb = data.total_vram_mb
            if data.compute_capability is not None:
                existing.compute_capability = data.compute_capability
            existing.status = "online"
            existing.last_heartbeat_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            logger.info(
                f"GPU node re-registered: host={data.node_hostname} "
                f"gpu={data.gpu_index}"
            )
            return await self._to_response(existing)

        node = GpuNode(
            node_hostname=data.node_hostname,
            gpu_index=data.gpu_index,
            gpu_model=data.gpu_model,
            total_vram_mb=data.total_vram_mb,
            compute_capability=data.compute_capability,
            status="online",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        self.db.add(node)
        await self.db.commit()
        await self.db.refresh(node)
        logger.info(
            f"GPU node registered: id={node.id} host={data.node_hostname} "
            f"gpu={data.gpu_index} model={data.gpu_model}"
        )
        return await self._to_response(node)

    async def update_node(
        self, node_id: UUID, data: GpuNodeUpdate
    ) -> Optional[GpuNodeResponse]:
        """Update a GPU node's metadata or status."""
        result = await self.db.execute(
            select(GpuNode)
            .options(selectinload(GpuNode.reservations))
            .where(GpuNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        if node is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(node, field, value)

        await self.db.commit()
        await self.db.refresh(node)
        logger.info("GPU node updated: id=%s fields=%s", node_id, list(update_data.keys()))
        return await self._to_response(node)

    async def drain_node(self, node_id: UUID) -> Optional[GpuNodeResponse]:
        """
        Mark a GPU node for draining (stop scheduling new jobs).

        Sets status to 'draining'. Active reservations are not interrupted;
        the scheduler will not assign new work to this node.
        """
        result = await self.db.execute(
            select(GpuNode)
            .options(selectinload(GpuNode.reservations))
            .where(GpuNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        if node is None:
            return None

        if node.status == "draining":
            raise ValueError(f"Node {node.node_hostname}:{node.gpu_index} is already draining")

        if node.status == "offline":
            raise ValueError(f"Node {node.node_hostname}:{node.gpu_index} is offline")

        node.status = "draining"
        await self.db.commit()
        await self.db.refresh(node)
        logger.info(
            f"GPU node draining: id={node_id} host={node.node_hostname} "
            f"gpu={node.gpu_index}"
        )
        return await self._to_response(node)

    async def get_node_reservations(
        self,
        node_id: UUID,
        active_only: bool = True,
    ) -> Optional[List[GpuReservationResponse]]:
        """Get active VRAM reservations for a GPU node."""
        node_result = await self.db.execute(
            select(GpuNode).where(GpuNode.id == node_id)
        )
        if node_result.scalar_one_or_none() is None:
            return None

        query = select(GpuReservation).where(GpuReservation.gpu_node_id == node_id)
        if active_only:
            query = query.where(
                GpuReservation.status.in_(["reserved", "active"])
            )
        query = query.order_by(GpuReservation.reserved_at.desc())
        result = await self.db.execute(query)
        reservations = result.scalars().all()
        return [GpuReservationResponse.model_validate(r) for r in reservations]

    async def get_fleet_utilization(self) -> GpuFleetSummary:
        """
        Fleet-wide GPU utilization summary with per-node breakdown.

        Aggregates VRAM usage across all registered nodes.
        """
        result = await self.db.execute(
            select(GpuNode).options(selectinload(GpuNode.reservations))
            .order_by(GpuNode.node_hostname, GpuNode.gpu_index)
        )
        nodes = result.scalars().unique().all()

        total_vram = 0
        used_vram = 0
        online_count = 0
        offline_count = 0
        draining_count = 0
        active_reservations = 0
        node_summaries = []

        for node in nodes:
            node_total = node.total_vram_mb or 0
            node_used = node.used_vram_mb
            node_available = node.available_vram_mb

            total_vram += node_total
            used_vram += node_used

            if node.status == "online":
                online_count += 1
            elif node.status == "offline":
                offline_count += 1
            elif node.status == "draining":
                draining_count += 1

            active_res_count = sum(
                1 for r in (node.reservations or [])
                if r.status in ("reserved", "active")
            )
            active_reservations += active_res_count

            node_summaries.append(
                GpuNodeSummary(
                    id=node.id,
                    node_hostname=node.node_hostname,
                    gpu_index=node.gpu_index,
                    gpu_model=node.gpu_model,
                    total_vram_mb=node_total,
                    used_vram_mb=node_used,
                    available_vram_mb=node_available,
                    status=node.status,
                    active_reservation_count=active_res_count,
                )
            )

        fleet_util = (used_vram / total_vram * 100.0) if total_vram > 0 else 0.0

        return GpuFleetSummary(
            total_nodes=len(nodes),
            online_nodes=online_count,
            offline_nodes=offline_count,
            draining_nodes=draining_count,
            total_vram_mb=total_vram,
            used_vram_mb=used_vram,
            available_vram_mb=total_vram - used_vram,
            fleet_utilization_pct=round(fleet_util, 2),
            active_reservations=active_reservations,
            nodes=node_summaries,
        )

    async def _to_response(self, node: GpuNode) -> GpuNodeResponse:
        """Convert a GpuNode model to a GpuNodeResponse."""
        active_jobs = []
        for reservation in (node.reservations or []):
            if reservation.status in ("reserved", "active") and reservation.job_id:
                job_result = await self.db.execute(
                    select(RenderJob).where(RenderJob.id == reservation.job_id)
                )
                job = job_result.scalar_one_or_none()
                if job:
                    project_name = None
                    proj_result = await self.db.execute(
                        select(Project.name).where(Project.id == job.project_id)
                    )
                    proj_row = proj_result.first()
                    if proj_row:
                        project_name = proj_row[0]

                    active_jobs.append(
                        ActiveJobSummary(
                            job_id=job.id,
                            project_name=project_name,
                            stage=job.job_type,
                            started_at=job.started_at,
                        )
                    )

        reservation_responses = [
            GpuReservationResponse.model_validate(r)
            for r in (node.reservations or [])
        ]

        return GpuNodeResponse(
            id=node.id,
            node_hostname=node.node_hostname,
            gpu_index=node.gpu_index,
            gpu_model=node.gpu_model,
            total_vram_mb=node.total_vram_mb,
            used_vram_mb=node.used_vram_mb,
            available_vram_mb=node.available_vram_mb,
            gpu_utilization_pct=0.0,
            temperature_c=0.0,
            power_draw_w=0.0,
            power_tdp_w=node.power_tdp_w,
            compute_capability=node.compute_capability,
            status=node.status,
            registered_at=node.registered_at,
            last_heartbeat_at=node.last_heartbeat_at,
            active_jobs=active_jobs,
            reservations=reservation_responses,
        )

    # ------------------------------------------------------------------
    # History endpoint per GPU Fleet Monitoring Spec v1.1
    # ------------------------------------------------------------------

    async def get_utilization_history(
        self, range_str: str
    ) -> List[GpuUtilizationPoint]:
        """Time-series GPU metrics for the requested range per spec 8.2.2.

        Returns rows from gpu_metrics_history JOINed with gpu_nodes to
        include node_hostname for client-side correlation. Ordered by
        (gpu_node_id, recorded_at) so consumers can group per-node series.

        Range format: <int><unit> where unit in {m, h, d}.
        Examples: "30m", "1h", "24h", "7d", "30d".

        Hard cap at MAX_HISTORY_POINTS per Spec v1.1 amendment 5.
        Raises HTTPException 413 if the query would exceed it. We do
        NOT silently LIMIT - a truncated chart would be misleading.

        Raises:
            HTTPException 400 if range_str format is invalid
            HTTPException 400 if range_str exceeds 30d retention boundary
            HTTPException 413 if query would exceed MAX_HISTORY_POINTS
        """
        # Range parsing
        if not range_str or len(range_str) < 2:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": (
                            f"Invalid range format '{range_str}'; "
                            f"expected <int><unit>"
                        ),
                        "details": [{"field": "range", "issue": "format"}],
                    }
                },
            )

        try:
            amount = int(range_str[:-1])
            unit = range_str[-1].lower()
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": (
                            f"Invalid range '{range_str}'; "
                            f"numeric prefix required"
                        ),
                    }
                },
            )

        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"Range must be positive; got '{range_str}'",
                    }
                },
            )

        unit_map = {"m": "minutes", "h": "hours", "d": "days"}
        if unit not in unit_map:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"Unsupported range unit '{unit}'; use m/h/d",
                    }
                },
            )

        delta = timedelta(**{unit_map[unit]: amount})

        # 30-day retention boundary per spec 4.2 Table 19
        if delta > timedelta(days=30):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": (
                            f"Range '{range_str}' exceeds 30-day "
                            f"retention boundary"
                        ),
                    }
                },
            )

        cutoff = datetime.now(timezone.utc) - delta

        # Pre-query count check (Spec v1.1 amendment 5)
        count_query = (
            select(func.count())
            .select_from(GpuMetricsHistory)
            .where(GpuMetricsHistory.recorded_at >= cutoff)
        )
        try:
            count_result = await self.db.execute(count_query)
            row_count = count_result.scalar() or 0
        except Exception:
            logger.exception(
                "gpu_utilization_history_count_failed range=%s cutoff=%s",
                range_str, cutoff.isoformat(),
            )
            raise

        if row_count > MAX_HISTORY_POINTS:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": (
                            f"Range '{range_str}' would return "
                            f"{row_count} points, exceeding cap of "
                            f"{MAX_HISTORY_POINTS}. Request a smaller range."
                        ),
                        "details": {
                            "requested_points": row_count,
                            "max_points": MAX_HISTORY_POINTS,
                            "requested_range": range_str,
                        },
                    }
                },
            )

        # Main query
        query = (
            select(
                GpuMetricsHistory.gpu_node_id,
                GpuNode.node_hostname,
                GpuMetricsHistory.recorded_at,
                GpuMetricsHistory.gpu_util_pct,
                GpuMetricsHistory.mem_util_pct,
                GpuMetricsHistory.temperature_c,
                GpuMetricsHistory.power_draw_w,
                GpuMetricsHistory.active_job_count,
                GpuMetricsHistory.queue_depth,
            )
            .join(GpuNode, GpuMetricsHistory.gpu_node_id == GpuNode.id)
            .where(GpuMetricsHistory.recorded_at >= cutoff)
            .order_by(
                GpuMetricsHistory.gpu_node_id,
                GpuMetricsHistory.recorded_at,
            )
        )

        try:
            result = await self.db.execute(query)
            rows = result.all()
        except Exception:
            logger.exception(
                "gpu_utilization_history_query_failed range=%s cutoff=%s",
                range_str, cutoff.isoformat(),
            )
            raise

        return [
            GpuUtilizationPoint(
                gpu_node_id=r.gpu_node_id,
                node_hostname=r.node_hostname,
                recorded_at=r.recorded_at,
                gpu_util_pct=r.gpu_util_pct,
                mem_util_pct=r.mem_util_pct,
                temperature_c=r.temperature_c,
                power_draw_w=r.power_draw_w,
                active_job_count=r.active_job_count,
                queue_depth=r.queue_depth,
            )
            for r in rows
        ]
