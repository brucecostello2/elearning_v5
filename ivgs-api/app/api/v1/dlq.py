"""
Dead Letter Queue API endpoints per §5.2.2.

Endpoints:
- GET    /api/v1/dlq/messages                — Paginated list with filters
- GET    /api/v1/dlq/messages/{id}           — Detail with full traceback
- POST   /api/v1/dlq/messages/{id}/replay    — Re-enqueue original task
- POST   /api/v1/dlq/messages/{id}/discard   — Mark as discarded with reason
- GET    /api/v1/dlq/analytics               — Failure analytics
- POST   /api/v1/dlq/bulk-replay             — Bulk replay by filter criteria

RBAC: Admin and operator roles.
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.dlq import (
    DLQMessageResponse,
    DLQDetailResponse,
    DLQDiscardRequest,
    DLQBulkReplayRequest,
    DLQBulkReplayResponse,
    DLQAnalyticsResponse,
)
from app.services.dlq_service import DLQService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dlq", tags=["Dead Letter Queue"])


@router.get(
    "/messages",
    response_model=PaginatedResponse[DLQMessageResponse],
    summary="List DLQ messages",
)
async def list_dlq_messages(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    category: Optional[str] = Query(
        default=None,
        description="Filter by failure category (transient/config/external/resource)",
    ),
    task_name: Optional[str] = Query(default=None, description="Filter by task name"),
    from_date: Optional[datetime] = Query(default=None, description="Messages after date"),
    to_date: Optional[datetime] = Query(default=None, description="Messages before date"),
    resolution: Optional[str] = Query(
        default=None,
        description="Filter by resolution (replayed/discarded/escalated)",
    ),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Paginated list of DLQ messages. Supports category, task_name, date, and resolution filters."""
    service = DLQService(db)
    messages, total = await service.list_messages(
        page=page,
        per_page=per_page,
        category=category,
        task_name=task_name,
        from_date=from_date,
        to_date=to_date,
        resolution=resolution,
    )
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=messages,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@router.get(
    "/messages/{message_id}",
    response_model=DLQDetailResponse,
    summary="Get DLQ message detail",
)
async def get_dlq_message(
    message_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Detail with full traceback and task arguments."""
    service = DLQService(db)
    message = await service.get_message(message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"DLQ message {message_id} not found",
                }
            },
        )
    return message


@router.post(
    "/messages/{message_id}/replay",
    response_model=DLQDetailResponse,
    summary="Replay DLQ message",
)
async def replay_dlq_message(
    message_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Re-enqueue original task with same arguments."""
    service = DLQService(db)
    try:
        result = await service.replay_message(message_id, current_user.username)
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
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"DLQ message {message_id} not found",
                }
            },
        )
    return result


@router.post(
    "/messages/{message_id}/discard",
    response_model=DLQDetailResponse,
    summary="Discard DLQ message",
)
async def discard_dlq_message(
    message_id: UUID,
    data: DLQDiscardRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Mark DLQ message as discarded with reason."""
    service = DLQService(db)
    try:
        result = await service.discard_message(
            message_id, data.reason, current_user.username
        )
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
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"DLQ message {message_id} not found",
                }
            },
        )
    return result


@router.get(
    "/analytics",
    response_model=DLQAnalyticsResponse,
    summary="DLQ failure analytics",
)
async def get_dlq_analytics(
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Failure analytics: counts by category, task, and time period."""
    service = DLQService(db)
    return await service.get_analytics()


@router.post(
    "/bulk-replay",
    response_model=DLQBulkReplayResponse,
    summary="Bulk replay DLQ messages",
)
async def bulk_replay_dlq(
    data: DLQBulkReplayRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Bulk replay by filter criteria. Only replays unresolved messages."""
    service = DLQService(db)
    return await service.bulk_replay(data, current_user.username)
