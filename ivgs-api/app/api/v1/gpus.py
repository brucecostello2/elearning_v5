"""
GPU management API endpoints per §5.2.1.

Endpoints:
- GET    /api/v1/gpu/nodes                        — List all GPU nodes
- POST   /api/v1/gpu/nodes                        — Register a GPU node (admin only)
- GET    /api/v1/gpu/nodes/{id}                   — Get GPU node detail
- PATCH  /api/v1/gpu/nodes/{id}                   — Update GPU node (admin only)
- GET    /api/v1/gpu/nodes/{id}/reservations      — Active VRAM reservations
- POST   /api/v1/gpu/nodes/{id}/drain             — Mark node for draining (admin only)
- GET    /api/v1/gpu/utilization                   — Fleet-wide utilization summary

RBAC: Admin only for mutations. All authenticated users can read.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.gpu import (
    GpuNodeCreate,
    GpuNodeUpdate,
    GpuNodeResponse,
    GpuReservationResponse,
    GpuFleetSummary,
    GpuUtilizationHistoryResponse,
)
from app.services.gpu_service import GpuService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gpu", tags=["GPU Management"])


@router.get(
    "/nodes",
    response_model=PaginatedResponse[GpuNodeResponse],
    summary="List all GPU nodes",
)
async def list_gpu_nodes(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by node status (online/offline/draining)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all registered GPU nodes with current status and VRAM utilization."""
    service = GpuService(db)
    nodes, total = await service.list_nodes(
        page=page, per_page=per_page, status_filter=status_filter
    )
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=nodes,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@router.post(
    "/nodes",
    response_model=GpuNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a GPU node (admin only)",
)
async def register_gpu_node(
    data: GpuNodeCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Register a new GPU node. Uses upsert: re-registers if (hostname, gpu_index) exists."""
    service = GpuService(db)
    return await service.register_node(data)


@router.get(
    "/nodes/{node_id}",
    response_model=GpuNodeResponse,
    summary="Get GPU node detail",
)
async def get_gpu_node(
    node_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get a single GPU node with reservations and active jobs."""
    service = GpuService(db)
    node = await service.get_node(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"GPU node {node_id} not found",
                }
            },
        )
    return node


@router.patch(
    "/nodes/{node_id}",
    response_model=GpuNodeResponse,
    summary="Update GPU node (admin only)",
)
async def update_gpu_node(
    node_id: UUID,
    data: GpuNodeUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update GPU node metadata or status (admin only)."""
    service = GpuService(db)
    node = await service.update_node(node_id, data)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"GPU node {node_id} not found",
                }
            },
        )
    return node


@router.get(
    "/nodes/{node_id}/reservations",
    response_model=list[GpuReservationResponse],
    summary="Get active VRAM reservations for a GPU node",
)
async def get_node_reservations(
    node_id: UUID,
    active_only: bool = Query(default=True, description="Only show active reservations"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Active VRAM reservations for a GPU node."""
    service = GpuService(db)
    reservations = await service.get_node_reservations(node_id, active_only=active_only)
    if reservations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"GPU node {node_id} not found",
                }
            },
        )
    return reservations


@router.post(
    "/nodes/{node_id}/drain",
    response_model=GpuNodeResponse,
    summary="Mark node for draining (admin only)",
)
async def drain_gpu_node(
    node_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Mark GPU node for draining — stops scheduling new jobs (admin only)."""
    service = GpuService(db)
    try:
        node = await service.drain_node(node_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                }
            },
        )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"GPU node {node_id} not found",
                }
            },
        )
    return node


@router.get(
    "/utilization",
    response_model=GpuFleetSummary,
    summary="Fleet-wide GPU utilization summary",
)
async def get_gpu_utilization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Fleet-wide GPU utilization summary with per-node breakdown."""
    service = GpuService(db)
    return await service.get_fleet_utilization()


@router.get(
    "/utilization/history",
    response_model=GpuUtilizationHistoryResponse,
    summary="GPU utilization time-series for the fleet chart (spec 8.2.2)",
)
async def get_gpu_utilization_history(
    range: str = Query(
        default="30m",
        pattern=r"^\d+[mhdMHD]$",
        description=(
            "Time range for history query. Format <int><unit> where unit "
            "is m (minutes), h (hours), or d (days). Maximum 30d per "
            "retention policy. Examples: 30m, 1h, 24h, 7d. "
            "Hard-capped at 5000 points per response - request smaller "
            "range if 413 returned. Per GPU Fleet Monitoring Spec v1.1."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Time-series GPU utilization data for the spec 8.2.2 fleet chart.

    Returns up to 30 days of history, ordered by (gpu_node_id, recorded_at).
    Empty response (history=[], point_count=0) is the expected state when:
      - No GPU nodes registered yet
      - Nodes registered but workers have not produced heartbeats in range
      - All nodes offline or drained

    Empty response is NOT an error. Callers distinguish empty-success
    from error states by HTTP status (200 vs 4xx/5xx).

    Hard cap: 5000 points per response. Larger queries return 413.

    RBAC: All authenticated users may read per spec 5.2.1.
    """
    service = GpuService(db)
    try:
        points = await service.get_utilization_history(range)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "gpu_utilization_history_handler_error range=%s user=%s",
            range, current_user.username,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to retrieve GPU utilization history",
                }
            },
        )

    return GpuUtilizationHistoryResponse(
        history=points,
        range=range.lower(),
        point_count=len(points),
    )
