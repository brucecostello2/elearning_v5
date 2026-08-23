"""
Checkpoint Pydantic schemas per §5.2.4.

Includes: CheckpointResponse, CheckpointDetailResponse,
CheckpointListResponse, ResumeResponse.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# The Postgres enum `checkpoint_status` accepts exactly these four labels
# (verified live 2026-08-23 against pg_enum).
CHECKPOINT_STATUSES = ("pending", "complete", "failed", "skipped")

# The workers speak a different vocabulary. `save_checkpoint` call sites send
# "running" (6 sites) or a `StageStatus` value - "success", "partial_success",
# "failed" (ivgs-workers/models/task_result.py:53-58). Only "failed" is a valid
# enum label, so without this map three of four writes would fail on the enum and
# the checkpoint table would hold nothing but failures.
#
# Mapped HERE rather than at the 14 stage call sites because those are stage task
# bodies, which WP-07's brief puts out of scope. See the WP-07 report, Finding 3.
#
# partial_success -> complete is a judgement call: the stage produced its outputs
# and the pipeline advances past it (partial-advance, commit 35d9226), so for
# resume purposes it is done. The original value is preserved in checkpoint_data.
WORKER_STATUS_MAP = {
    "running": "pending",
    "success": "complete",
    "partial_success": "complete",
    "failed": "failed",
}


class CheckpointCreateRequest(BaseModel):
    """Body of POST /jobs/{job_id}/checkpoints, as the workers send it.

    Matches `save_checkpoint`'s payload in
    ivgs-workers/utils/error_handler.py exactly: stage_name, stage_index,
    status, checkpoint_data.
    """

    stage_name: str = Field(..., max_length=64)
    stage_index: Optional[int] = None
    status: str
    checkpoint_data: Optional[Dict[str, Any]] = None
    output_refs: Optional[Dict[str, Any]] = None
    version_fingerprint: Optional[str] = Field(default=None, max_length=128)

    @field_validator("status")
    @classmethod
    def _normalise_status(cls, v: str) -> str:
        """Accept the worker vocabulary and the enum's own labels."""
        lowered = (v or "").strip().lower()
        if lowered in CHECKPOINT_STATUSES:
            return lowered
        mapped = WORKER_STATUS_MAP.get(lowered)
        if mapped is None:
            raise ValueError(
                f"unknown checkpoint status {v!r}; expected one of "
                f"{sorted(set(CHECKPOINT_STATUSES) | set(WORKER_STATUS_MAP))}"
            )
        return mapped


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
