"""Pydantic schemas for DLQ API endpoints."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class DLQMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_queue: str
    task_name: str
    task_id: Optional[str] = None
    exception_type: str
    exception_message: str
    traceback: Optional[str] = None
    failure_category: str
    retry_count_exhausted: int
    job_id: Optional[str] = None
    resolution: str
    replay_task_id: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None


class DLQListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    messages: List[DLQMessageResponse]


class DLQAnalytics(BaseModel):
    by_category: Dict[str, int]
    by_task: Dict[str, int]
    total_pending: int


class ReplayRequest(BaseModel):
    reviewer: str = "api"


class BulkReplayRequest(BaseModel):
    failure_category: Optional[str] = None
    task_name: Optional[str] = None
    max_messages: int = 100
