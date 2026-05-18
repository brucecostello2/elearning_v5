from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime


class LocalizationRequest(BaseModel):
    source_language: str = "en"
    target_languages: List[str]
    voice_map: Dict[str, str] = {}   # language_code → voice_id


class LocalizationLanguageStatus(BaseModel):
    language: str
    status: str
    config_id: Optional[int]


class LocalizationStatusResponse(BaseModel):
    job_id: str
    languages: List[LocalizationLanguageStatus]

    class Config:
        from_attributes = True


class LocalizedAssetResponse(BaseModel):
    id: int
    scene_id: Optional[str]
    asset_type: str
    asset_path: Optional[str]
    quality_score: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SupportedLanguagesResponse(BaseModel):
    languages: List[Dict]
