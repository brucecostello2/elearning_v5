"""Pydantic schemas for Quality API endpoints."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict


class QualityScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset_id: str
    job_id: str
    scene_id: Optional[str] = None
    asset_type: str
    quality_score: float
    safety_score: Optional[float] = None
    scoring_model: str
    scoring_details: Optional[Dict[str, Any]] = None
    decision: str
    rejection_reason: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None


class QualityDecision(BaseModel):
    decision: str  # approved, rejected
    reason: Optional[str] = None
    reviewer: str = "api"


class FlaggedAssetResponse(QualityScoreResponse):
    rejection_reasons: List[str] = []
