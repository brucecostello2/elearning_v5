"""
Render job Pydantic schemas per §5.1.7.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    """Render job response."""

    id: UUID
    project_id: UUID
    celery_task_id: Optional[str] = None
    job_type: str
    node_id: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: Optional[int] = None
    failure_category: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
