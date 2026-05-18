"""Pydantic schemas for Manifest API endpoints."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class TimelineLayer(BaseModel):
    type: str             # video, audio, caption, image
    path: str
    start_ms: int
    duration_ms: int
    z_index: int = 0


class TimelineScene(BaseModel):
    scene_id: str
    scene_index: int
    start_ms: int
    duration_ms: int
    transition: str = "cut"
    layers: List[TimelineLayer] = []


class ManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: str
    manifest_version: int
    total_duration_ms: int
    resolution_width: int
    resolution_height: int
    framerate: float
    status: str
    checksum: Optional[str] = None
    locked_at: Optional[datetime] = None
    rendered_at: Optional[datetime] = None
    created_at: datetime
    scene_count: int = 0

    @classmethod
    def model_validate(cls, obj, **kwargs):
        instance = super().model_validate(obj, **kwargs)
        if hasattr(obj, 'timeline') and obj.timeline:
            instance.scene_count = len(
                obj.timeline.get('scenes', [])
            )
        return instance


class ManifestValidationResult(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    total_duration_ms: int = 0
    scene_count: int = 0
