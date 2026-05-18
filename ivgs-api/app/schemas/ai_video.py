from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class AiVideoGenerationResponse(BaseModel):
    id: int
    job_id: str
    scene_id: str
    model_name: str
    prompt: str
    generation_params: Dict[str, Any]
    vram_used_mb: Optional[int]
    generation_duration_seconds: Optional[float]
    output_path: Optional[str]
    quality_score: Optional[float]
    fallback_level_used: int
    status: str
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class AiVideoStatsResponse(BaseModel):
    total: int
    success_rate: float
    avg_duration_s: float
    fallback_rate: float
