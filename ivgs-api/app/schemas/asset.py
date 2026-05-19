"""
Asset Pydantic schemas per §5.1.5.

Includes: AssetUploadResponse, AssetResponse, AssetFilter.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetUploadResponse(BaseModel):
    """Response returned after successful asset upload to SeaweedFS."""

    id: UUID
    seaweedfs_fid: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    asset_type: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    content_hash: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AssetResponse(BaseModel):
    """Full asset metadata response per §5.1.5."""

    id: UUID
    project_id: UUID
    scene_id: Optional[UUID] = None
    asset_type: str
    seaweedfs_fid: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    language_code: Optional[str] = None
    generation_prompt_id: Optional[UUID] = None
    storage_tier: str = "hot"
    preserve_flag: bool = False
    content_hash: Optional[str] = None
    reference_count: int = 1
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetFilter(BaseModel):
    """Query parameters for asset listing."""

    scene_id: Optional[UUID] = None
    asset_type: Optional[str] = None
    language_code: Optional[str] = None
    storage_tier: Optional[str] = None
