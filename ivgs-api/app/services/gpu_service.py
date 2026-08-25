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
from app.services.scheduler_fleet import (
    SchedulerUnavailable,
    fetch_fleet,
    fleet_node_views,
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

    async def _fleet_views(self) -> List[dict]:
        """The scheduler's fleet, mapped. Raises SchedulerUnavailable."""
        payload = await fetch_fleet()
        self._last_fleet_payload = payload
        return fleet_node_views(payload)

    async def _scheduler_node_response(self, view: dict) -> GpuNodeResponse:
        """One mapped fleet node as a GpuNodeResponse.

        ``active_jobs`` is filled from the scheduler's ``current_jobs`` by
        looking the ids up in render_jobs, so the fleet page shows what a GPU is
        working on. A job id the scheduler holds that the database does not know
        is skipped rather than rendered as a blank row - it means the job was
        deleted under a running reservation, which is information the log
        carries, not something to draw as an unnamed job.
        """
        active_jobs: List[ActiveJobSummary] = []
        for raw_job_id in view["current_jobs"]:
            try:
                job_uuid = UUID(str(raw_job_id))
            except (ValueError, AttributeError):
                continue
            job = await self.db.scalar(
                select(RenderJob).where(RenderJob.id == job_uuid)
            )
            if job is None:
                logger.info(
                    "Scheduler reports job %s on %s; no such render_jobs row",
                    raw_job_id, view["scheduler_node_id"],
                )
                continue
            project_name = await self.db.scalar(
                select(Project.name).where(Project.id == job.project_id)
            )
            active_jobs.append(
                ActiveJobSummary(
                    job_id=job.id,
                    project_name=project_name,
                    stage=job.job_type,
                    started_at=job.started_at,
                )
            )

        return GpuNodeResponse(
            id=view["id"],
            node_hostname=view["node_hostname"],
            gpu_index=view["gpu_index"],
            gpu_model=view["gpu_model"],
            total_vram_mb=view["total_vram_mb"],
            used_vram_mb=view["used_vram_mb"],
            available_vram_mb=view["available_vram_mb"],
            gpu_utilization_pct=view["gpu_utilization_pct"],
            # The scheduler registry carries neither temperature nor power. They
            # come from the node exporters (WP-48) and are left at their schema
            # defaults here rather than being invented from the VRAM figures.
            temperature_c=0.0,
            power_draw_w=0.0,
            power_tdp_w=None,
            compute_capability=None,
            status=view["status"],
            registered_at=view["registered_at"] or datetime.now(timezone.utc),
            last_heartbeat_at=view["last_heartbeat_at"],
            active_jobs=active_jobs,
            reservations=[],
        )

    async def list_nodes(
        self,
        page: int = 1,
        per_page: int = 50,
        status_filter: Optional[str] = None,
    ) -> Tuple[List[GpuNodeResponse], int]:
        """
        List the GPU fleet, read through from the scheduler's registry.

        WP-45 Task 4(b) / WP-40 D-2, RULED read-through. This used to read the
        ``gpu_nodes`` table, which has always had zero rows: workers register
        with the **scheduler** (``POST /register``) and nothing in ivgs-workers
        has ever called ``POST /api/v1/gpu/nodes``. "GPU Nodes Online" showed
        0/0 while three GPUs were alive and working, and the GPU Fleet page
        summed VRAM over an empty array.

        No sync job, as ruled: one source of truth, asked directly. A periodic
        copy would add a fourth registry and a staleness window to a system that
        already had three registries disagreeing.

        Raises ``SchedulerUnavailable`` rather than returning an empty list. The
        caller turns that into a 503 with the reason, because "no nodes" and "I
        could not ask" must not render as the same tile.
        """
        views = await self._fleet_views()
        if status_filter:
            views = [v for v in views if v["status"] == status_filter]

        total = len(views)
        start = (page - 1) * per_page
        page_views = views[start:start + per_page]

        return [await self._scheduler_node_response(v) for v in page_views], total

    async def get_node_by_uuid(self, node_id: UUID) -> Optional[GpuNodeResponse]:
        """One fleet node, resolved by the UUID5 derived from its scheduler id."""
        for view in await self._fleet_views():
            if view["id"] == node_id:
                return await self._scheduler_node_response(view)
        return None

    async def resolve_scheduler_node_id(self, node_id: UUID) -> Optional[str]:
        """The scheduler's own node id for an API-side UUID, or None."""
        for view in await self._fleet_views():
            if view["id"] == node_id:
                return view["scheduler_node_id"]
        return None

    async def drain_scheduler_node(self, node_id: UUID) -> dict:
        """Drain a node through the scheduler that actually schedules on it.

        The old ``drain_node`` set ``gpu_nodes.status = 'draining'`` on a table
        the scheduler does not read, so a drained node kept receiving work. This
        posts to the scheduler's own ``POST /drain/{node_id}``, which is the only
        thing placement consults.
        """
        import httpx

        from app.services.scheduler_fleet import scheduler_base_url

        scheduler_node_id = await self.resolve_scheduler_node_id(node_id)
        if scheduler_node_id is None:
            return {}

        url = f"{scheduler_base_url()}/drain/{scheduler_node_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url)
        except Exception as exc:
            raise SchedulerUnavailable(
                f"could not reach the GPU scheduler to drain "
                f"{scheduler_node_id}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise SchedulerUnavailable(
                f"scheduler refused the drain of {scheduler_node_id}: "
                f"HTTP {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()

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
        Fleet-wide GPU utilization, read through from the scheduler's registry.

        WP-45 Task 4(b). Same change as ``list_nodes`` and for the same reason:
        this aggregated over ``gpu_nodes``, which has zero rows, so
        ``/api/v1/gpu/utilization`` answered ``total_nodes=0, online=0,
        total_vram_mb=0`` on a fleet with three live GPUs and ~2 TB of VRAM
        registered.

        ``active_reservations`` counts nodes reporting a current job. The
        ``gpu_reservations`` table is a different mechanism - the scheduler holds
        its reservations in Redis, and this is the count that corresponds to what
        the fleet is actually doing rather than to rows nobody writes.
        """
        views = await self._fleet_views()

        total_vram = sum(v["total_vram_mb"] for v in views)
        used_vram = sum(v["used_vram_mb"] for v in views)
        online_count = sum(1 for v in views if v["status"] == "online")
        offline_count = sum(1 for v in views if v["status"] == "offline")
        draining_count = sum(1 for v in views if v["status"] == "draining")
        active_reservations = sum(1 for v in views if v["current_jobs"])

        node_summaries = [
            GpuNodeSummary(
                id=v["id"],
                node_hostname=v["node_hostname"],
                gpu_index=v["gpu_index"],
                gpu_model=v["gpu_model"],
                total_vram_mb=v["total_vram_mb"],
                used_vram_mb=v["used_vram_mb"],
                available_vram_mb=v["available_vram_mb"],
                status=v["status"],
                active_reservation_count=len(v["current_jobs"]),
            )
            for v in views
        ]

        fleet_util = (used_vram / total_vram * 100.0) if total_vram > 0 else 0.0

        return GpuFleetSummary(
            total_nodes=len(views),
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
