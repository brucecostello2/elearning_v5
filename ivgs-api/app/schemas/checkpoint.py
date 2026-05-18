"""Pydantic schemas for checkpoint API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class CheckpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    stage_name: str
    stage_index: int
    status: str
    output_refs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class CheckpointListResponse(BaseModel):
    job_id: int
    checkpoints: List[CheckpointResponse]
    resume_point: Optional[str] = None


class ResumeRequest(BaseModel):
    """Request body for POST /checkpoints/resume (currently no required fields)."""
    force_restart: bool = False


class ResumeResponse(BaseModel):
    job_id: int
    message: str
    resume_stage: Optional[str] = None
