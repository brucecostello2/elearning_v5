"""
Asset Pydantic schemas per §5.1.5.

Includes: AssetUploadResponse, AssetResponse, AssetFilter.
"""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssetUploadResponse(BaseModel):
    """Response returned after successful asset upload to SeaweedFS."""

    id: UUID
    seaweedfs_fid: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    asset_type: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    content_hash: Optional[str] = None
    # WP-45 Task 1. `was_deduplicated` tells the caller whether these bytes were
    # stored or an existing row was re-referenced. It used to be unknowable from
    # the response: a dedup hit and a fresh upload were byte-identical replies.
    generation_params_hash: Optional[str] = None
    generation_metadata: Optional[Dict[str, Any]] = None
    reference_count: int = 1
    was_deduplicated: bool = False
    # WP-56 / AD-09.4.2. Non-null when this asset is a library REFERENCE rather
    # than an independent upload. Declared here only because the API populates
    # it — see the WP-40/43 rule in app/schemas/library.py.
    library_asset_id: Optional[UUID] = None

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
    # WP-45 Task 1: the dedup key and the provenance record, both persisted by
    # the upload route and both readable here. `check_duplicate_asset` in the
    # worker fleet reads `id` and `seaweedfs_path` off this shape.
    generation_params_hash: Optional[str] = None
    generation_metadata: Optional[Dict[str, Any]] = None
    # WP-56 / AD-09.4.2: the library origin, or null for pipeline-generated media.
    library_asset_id: Optional[UUID] = None
    # WP-63 Task 7(c) / migration 0036. NULL means this is the CURRENT asset for
    # its scene; otherwise it names the asset that replaced it. A superseded row
    # is retained, not deleted, so every consumer that wants "the current image
    # for this scene" must read this rather than sort by `created_at` and hope.
    superseded_by: Optional[UUID] = None
    superseded_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetFilter(BaseModel):
    """Query parameters for asset listing."""

    scene_id: Optional[UUID] = None
    asset_type: Optional[str] = None
    language_code: Optional[str] = None
    storage_tier: Optional[str] = None
