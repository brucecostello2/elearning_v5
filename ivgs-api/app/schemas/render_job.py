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
    # WP-45 Task 6(f). The Jobs tab drew "—" for stage and "Unassigned" for node
    # from `current_stage` / `assigned_node`, two field names the API has never
    # sent, so every row was identical and identified nothing. These are the
    # columns the API DOES populate; the tab reads them instead, and the fields
    # that genuinely have no source are left blank and labelled rather than
    # filled with a confident-looking placeholder.
    resume_from_stage: Optional[str] = None
    language_code: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
