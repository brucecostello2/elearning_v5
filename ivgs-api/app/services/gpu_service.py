"""
GPU service: node registry, reservation management, fleet utilization.

Per §5.2.1 — manages GPU node lifecycle and VRAM reservation tracking.
Actual GPU scheduling logic is in Phase 8 (GPU Scheduler microservice).
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.gpu_node import GpuNode, GpuReservation
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
)

logger = logging.getLogger(__name__)


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
        logger.info(f"GPU node updated: id={node_id} fields={list(update_data.keys())}")
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
            compute_capability=node.compute_capability,
            status=node.status,
            registered_at=node.registered_at,
            last_heartbeat_at=node.last_heartbeat_at,
            active_jobs=active_jobs,
            reservations=reservation_responses,
        )
