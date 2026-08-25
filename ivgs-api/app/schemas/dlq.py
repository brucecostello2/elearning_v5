"""
DLQ Pydantic schemas per §5.2.2.

Includes: DLQMessageResponse, DLQDetailResponse, DLQDiscardRequest,
DLQBulkReplayRequest, DLQAnalyticsResponse.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DLQMessageResponse(BaseModel):
    """DLQ message summary for list endpoints."""

    id: UUID
    original_queue: Optional[str] = None
    task_name: Optional[str] = None
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    failure_category: Optional[str] = None
    retry_count_exhausted: Optional[int] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    resolution: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DLQDetailResponse(BaseModel):
    """DLQ message detail with full traceback and task arguments."""

    id: UUID
    original_queue: Optional[str] = None
    task_name: Optional[str] = None
    task_args: Optional[Any] = None
    task_kwargs: Optional[Dict[str, Any]] = None
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    traceback: Optional[str] = None
    failure_category: Optional[str] = None
    retry_count_exhausted: Optional[int] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    resolution: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DLQDiscardRequest(BaseModel):
    """Request body for discarding a DLQ message."""

    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="Reason for discarding this message",
    )


class DLQBulkReplayRequest(BaseModel):
    """Request body for bulk replaying DLQ messages by filter."""

    category: Optional[str] = Field(
        default=None,
        pattern="^(transient|config|external|resource)$",
        description="Filter by failure category",
    )
    task_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Filter by task name",
    )
    from_date: Optional[datetime] = Field(
        default=None,
        description="Filter messages created after this date",
    )
    to_date: Optional[datetime] = Field(
        default=None,
        description="Filter messages created before this date",
    )


class DLQCategoryCount(BaseModel):
    """Count of DLQ messages per failure category."""

    category: str
    count: int


class DLQTaskCount(BaseModel):
    """Count of DLQ messages per task name."""

    task_name: str
    count: int


class DLQDailyCount(BaseModel):
    """Count of DLQ messages per day."""

    date: str
    count: int


class DLQAnalyticsResponse(BaseModel):
    """DLQ failure analytics: counts by category, task, and time."""

    total_messages: int = 0
    unresolved_count: int = 0
    replayed_count: int = 0
    discarded_count: int = 0
    escalated_count: int = 0
    by_category: List[DLQCategoryCount] = []
    by_task: List[DLQTaskCount] = []
    by_day: List[DLQDailyCount] = []


class DLQBulkReplayResponse(BaseModel):
    """Response for bulk replay operation.

    WP-45 Task 3: ``replayed_count`` counts messages that produced a broker
    message. It used to count every row the loop touched, whether or not
    anything was re-enqueued - so the number was the size of the filter, not the
    size of the action. ``skipped_count`` and ``skipped_reasons`` exist so a
    partial replay reports itself as partial instead of rounding up.
    """

    replayed_count: int = 0
    message_ids: List[UUID] = []
    skipped_count: int = 0
    skipped_reasons: List[str] = []
