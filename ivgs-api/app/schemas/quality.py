"""
Quality score Pydantic schemas per §5.2.3.

Includes: QualityScoreResponse, FlaggedAssetResponse,
QualityApproveRequest, QualityRejectRequest.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QualityScoreResponse(BaseModel):
    """Quality score for a single asset."""

    id: UUID
    asset_id: UUID
    job_id: Optional[UUID] = None
    quality_score: Optional[float] = None
    safety_score: Optional[float] = None
    scoring_details: Optional[Dict[str, Any]] = None
    decision: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlaggedAssetResponse(BaseModel):
    """Flagged asset requiring human review."""

    id: UUID
    asset_id: UUID
    job_id: Optional[UUID] = None
    quality_score: Optional[float] = None
    safety_score: Optional[float] = None
    scoring_details: Optional[Dict[str, Any]] = None
    decision: str
    created_at: datetime
    asset_type: Optional[str] = None
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class QualityApproveRequest(BaseModel):
    """Request body for approving a flagged asset."""

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional review notes",
    )


class QualityRejectRequest(BaseModel):
    """Request body for rejecting a flagged asset (triggers regeneration)."""

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Reason for rejection",
    )
    regenerate: bool = Field(
        default=True,
        description="Whether to trigger asset regeneration",
    )


class JobQualityResponse(BaseModel):
    """All quality scores for a job."""

    job_id: UUID
    total_assets: int = 0
    approved_count: int = 0
    flagged_count: int = 0
    rejected_count: int = 0
    average_quality_score: Optional[float] = None
    average_safety_score: Optional[float] = None
    scores: List[QualityScoreResponse] = []
