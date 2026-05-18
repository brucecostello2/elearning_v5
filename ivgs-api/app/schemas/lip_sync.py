from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


class LipSyncValidationResponse(BaseModel):
    id: int
    asset_id: int
    job_id: str
    scene_id: str
    sync_score: float
    scoring_model: str
    frame_level_scores: Optional[List[Dict]]
    mouth_movement_correlation: Optional[float]
    frozen_frame_count: int
    passed: bool
    threshold_used: float
    validated_at: datetime

    class Config:
        from_attributes = True
