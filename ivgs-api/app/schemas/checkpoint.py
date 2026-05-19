"""
Checkpoint Pydantic schemas per §5.2.4.

Includes: CheckpointResponse, CheckpointDetailResponse,
CheckpointListResponse, ResumeResponse.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CheckpointResponse(BaseModel):
    """Pipeline checkpoint summary for list endpoints."""

    id: UUID
    job_id: UUID
    stage_name: str
    stage_index: Optional[int] = None
    status: str
    version_fingerprint: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckpointDetailResponse(BaseModel):
    """Pipeline checkpoint detail with full data."""

    id: UUID
    job_id: UUID
    stage_name: str
    stage_index: Optional[int] = None
    checkpoint_data: Optional[Dict[str, Any]] = None
    output_refs: Optional[Dict[str, Any]] = None
    version_fingerprint: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckpointListResponse(BaseModel):
    """All checkpoints for a job with summary info."""

    job_id: UUID
    total_stages: int = 0
    completed_stages: int = 0
    failed_stages: int = 0
    last_successful_stage: Optional[str] = None
    checkpoints: List[CheckpointResponse] = []


class ResumeResponse(BaseModel):
    """Response after triggering pipeline resume from checkpoint."""

    job_id: UUID
    resume_from_stage: str
    new_job_id: Optional[UUID] = None
    message: str
