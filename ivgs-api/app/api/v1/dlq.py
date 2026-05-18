"""REST API endpoints for Dead-Letter Queue management."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dlq import DeadLetterMessage
from app.services.dlq_service import DLQService
from app.schemas.dlq import (
    DLQMessageResponse, DLQListResponse, DLQAnalytics,
    ReplayRequest, BulkReplayRequest
)

router = APIRouter(prefix="/api/v1/dlq", tags=["dlq"])


@router.get("/messages", response_model=DLQListResponse)
def list_dlq_messages(
    category: Optional[str] = None,
    task_name: Optional[str] = None,
    resolution: Optional[str] = "pending",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """List DLQ messages with optional filters."""
    query = db.query(DeadLetterMessage)
    if category:
        query = query.filter(DeadLetterMessage.failure_category == category)
    if task_name:
        query = query.filter(DeadLetterMessage.task_name == task_name)
    if resolution:
        query = query.filter(DeadLetterMessage.resolution == resolution)

    total = query.count()
    messages = (query.order_by(DeadLetterMessage.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all())

    return DLQListResponse(
        total=total, page=page, page_size=page_size,
        messages=[DLQMessageResponse.model_validate(m) for m in messages]
    )


@router.get("/messages/{dlq_id}", response_model=DLQMessageResponse)
def get_dlq_message(dlq_id: int, db: Session = Depends(get_db)):
    """Get detailed DLQ message including full traceback."""
    msg = db.query(DeadLetterMessage).filter(
        DeadLetterMessage.id == dlq_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail=f"DLQ message {dlq_id} not found")
    return DLQMessageResponse.model_validate(msg)


@router.post("/messages/{dlq_id}/replay")
def replay_message(
    dlq_id: int,
    db: Session = Depends(get_db),
):
    """Replay a single DLQ message back to its original queue."""
    svc = DLQService(db)
    try:
        new_task_id = svc.replay_message(dlq_id)
        return {"status": "replayed", "new_task_id": new_task_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/messages/{dlq_id}/discard")
def discard_message(
    dlq_id: int, reviewer: str = "api",
    db: Session = Depends(get_db),
):
    """Mark a DLQ message as intentionally discarded."""
    msg = db.query(DeadLetterMessage).filter(
        DeadLetterMessage.id == dlq_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.discard(reviewer)
    db.commit()
    return {"status": "discarded"}


@router.get("/analytics", response_model=DLQAnalytics)
def get_analytics(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Return failure analytics for monitoring dashboards."""
    svc = DLQService(db)
    data = svc.get_failure_analytics(hours=hours)
    return DLQAnalytics(**data)


@router.post("/bulk-replay")
def bulk_replay(
    request: BulkReplayRequest,
    db: Session = Depends(get_db),
):
    """Replay multiple messages matching filter criteria."""
    svc = DLQService(db)
    result = svc.bulk_replay(
        failure_category=request.failure_category,
        task_name=request.task_name,
        max_messages=request.max_messages,
    )
    return result
