"""
IVGS v5 — Composition Manifest REST API Endpoints
===================================================

Implements §5.2.5:
  GET  /api/v1/jobs/{id}/manifest          — Get manifest with timeline JSON
  POST /api/v1/jobs/{id}/manifest/generate  — Build manifest from storyboard + assets
  POST /api/v1/jobs/{id}/manifest/lock      — Freeze timeline
  POST /api/v1/jobs/{id}/manifest/validate  — Validate asset references + checksums
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User

logger = logging.getLogger("ivgs.api.manifests")

router = APIRouter(prefix="/api/v1/jobs", tags=["manifests"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ManifestTimelineLayer(BaseModel):
    layer_type: str  # background | talking_head | lower_third | captions | audio
    asset_id: str
    start_time_ms: int
    end_time_ms: int
    position: Optional[str] = None  # e.g., "bottom-right", "full-frame"


class ManifestScene(BaseModel):
    scene_index: int
    start_time_ms: int
    end_time_ms: int
    layers: list[ManifestTimelineLayer]


class ManifestResponse(BaseModel):
    id: str
    job_id: str
    status: str  # draft | locked
    timeline_json: dict
    total_duration_ms: int
    scene_count: int
    created_at: datetime
    locked_at: Optional[datetime] = None


class ManifestGenerateRequest(BaseModel):
    render_params: Optional[dict] = None


class ManifestValidationResult(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    total_assets_checked: int
    checksum_matches: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{job_id}/manifest", response_model=ManifestResponse)
async def get_manifest(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManifestResponse:
    """GET /api/v1/jobs/{id}/manifest — Get composition manifest with timeline JSON."""
    result = await db.execute(
        select("*").select_from(
            __import__("sqlalchemy").text("composition_manifests")
        ).where(
            __import__("sqlalchemy").text("job_id = :job_id")
        ),
        {"job_id": job_id},
    )
    # Use SQLAlchemy ORM model in production:
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT id, job_id, status, timeline_json, total_duration_ms, "
                "scene_count, created_at, locked_at "
                "FROM composition_manifests WHERE job_id = :job_id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"job_id": job_id},
        )
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"No manifest found for job {job_id}"}},
        )

    return ManifestResponse(
        id=str(row.id),
        job_id=str(row.job_id),
        status=row.status,
        timeline_json=row.timeline_json,
        total_duration_ms=row.total_duration_ms,
        scene_count=row.scene_count,
        created_at=row.created_at,
        locked_at=row.locked_at,
    )


@router.post("/{job_id}/manifest/generate", response_model=ManifestResponse)
async def generate_manifest(
    job_id: str,
    request: ManifestGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManifestResponse:
    """POST /api/v1/jobs/{id}/manifest/generate — Build manifest from storyboard and assets."""
    from sqlalchemy import text as sa_text

    # Verify job exists and is in correct state
    job_row = (
        await db.execute(
            sa_text("SELECT id, project_id, status FROM render_jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
    ).fetchone()

    if not job_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"Job {job_id} not found"}},
        )

    # Fetch scenes for the project
    scenes = (
        await db.execute(
            sa_text(
                "SELECT id, scene_index, narration_text, visual_description, "
                "media_type, duration_seconds "
                "FROM storyboard_scenes WHERE project_id = :project_id "
                "ORDER BY scene_index"
            ),
            {"project_id": str(job_row.project_id)},
        )
    ).fetchall()

    if not scenes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VALIDATION_ERROR",
                              "message": "No storyboard scenes found for this project"}},
        )

    # Fetch assets for the project
    assets = (
        await db.execute(
            sa_text(
                "SELECT id, scene_id, asset_type, seaweedfs_fid, sha256_hash "
                "FROM assets WHERE project_id = :project_id"
            ),
            {"project_id": str(job_row.project_id)},
        )
    ).fetchall()

    assets_by_scene = {}
    for asset in assets:
        scene_id = str(asset.scene_id) if asset.scene_id else "__global__"
        assets_by_scene.setdefault(scene_id, []).append(asset)

    # Build timeline JSON
    timeline_scenes = []
    current_time_ms = 0
    for scene in scenes:
        duration_ms = int(scene.duration_seconds * 1000)
        scene_assets = assets_by_scene.get(str(scene.id), [])

        layers = []
        for asset in scene_assets:
            layers.append({
                "layer_type": _asset_type_to_layer(asset.asset_type),
                "asset_id": str(asset.id),
                "seaweedfs_fid": asset.seaweedfs_fid,
                "checksum": asset.sha256_hash,
                "start_time_ms": current_time_ms,
                "end_time_ms": current_time_ms + duration_ms,
            })

        timeline_scenes.append({
            "scene_index": scene.scene_index,
            "start_time_ms": current_time_ms,
            "end_time_ms": current_time_ms + duration_ms,
            "layers": layers,
        })
        current_time_ms += duration_ms

    manifest_id = str(uuid.uuid4())
    timeline_json = {
        "version": "1.0",
        "scenes": timeline_scenes,
        "render_params": request.render_params or {
            "resolution_1080p": {"width": 1920, "height": 1080, "crf": 18, "fps": 30},
            "resolution_4k": {"width": 3840, "height": 2160, "crf": 20, "fps": 30},
        },
    }

    await db.execute(
        sa_text(
            "INSERT INTO composition_manifests "
            "(id, job_id, status, timeline_json, total_duration_ms, scene_count, created_at) "
            "VALUES (:id, :job_id, 'draft', :timeline_json, :total_duration_ms, "
            ":scene_count, :created_at)"
        ),
        {
            "id": manifest_id,
            "job_id": job_id,
            "timeline_json": __import__("json").dumps(timeline_json),
            "total_duration_ms": current_time_ms,
            "scene_count": len(scenes),
            "created_at": datetime.now(timezone.utc),
        },
    )
    await db.commit()

    return ManifestResponse(
        id=manifest_id,
        job_id=job_id,
        status="draft",
        timeline_json=timeline_json,
        total_duration_ms=current_time_ms,
        scene_count=len(scenes),
        created_at=datetime.now(timezone.utc),
    )


@router.post("/{job_id}/manifest/lock", response_model=ManifestResponse)
async def lock_manifest(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManifestResponse:
    """POST /api/v1/jobs/{id}/manifest/lock — Freeze timeline."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT id, status FROM composition_manifests "
                "WHERE job_id = :job_id ORDER BY created_at DESC LIMIT 1"
            ),
            {"job_id": job_id},
        )
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"No manifest found for job {job_id}"}},
        )

    if row.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "MANIFEST_LOCKED",
                              "message": "Manifest is already locked"}},
        )

    now = datetime.now(timezone.utc)
    await db.execute(
        sa_text(
            "UPDATE composition_manifests SET status = 'locked', locked_at = :locked_at "
            "WHERE id = :manifest_id"
        ),
        {"manifest_id": str(row.id), "locked_at": now},
    )
    await db.commit()

    # Re-fetch and return full manifest
    return await get_manifest(job_id, db, current_user)


@router.post("/{job_id}/manifest/validate", response_model=ManifestValidationResult)
async def validate_manifest(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ManifestValidationResult:
    """POST /api/v1/jobs/{id}/manifest/validate — Validate asset references + checksums."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT id, timeline_json FROM composition_manifests "
                "WHERE job_id = :job_id ORDER BY created_at DESC LIMIT 1"
            ),
            {"job_id": job_id},
        )
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"No manifest found for job {job_id}"}},
        )

    timeline = (
        __import__("json").loads(row.timeline_json)
        if isinstance(row.timeline_json, str)
        else row.timeline_json
    )

    errors: list[str] = []
    warnings: list[str] = []
    total_checked = 0
    checksum_ok = 0

    for scene in timeline.get("scenes", []):
        for layer in scene.get("layers", []):
            asset_id = layer.get("asset_id")
            expected_checksum = layer.get("checksum")
            total_checked += 1

            asset_row = (
                await db.execute(
                    sa_text("SELECT id, sha256_hash, seaweedfs_fid FROM assets WHERE id = :id"),
                    {"id": asset_id},
                )
            ).fetchone()

            if not asset_row:
                errors.append(f"Asset {asset_id} referenced in manifest does not exist")
                continue

            if expected_checksum and asset_row.sha256_hash == expected_checksum:
                checksum_ok += 1
            elif expected_checksum:
                errors.append(
                    f"Checksum mismatch for asset {asset_id}: "
                    f"expected {expected_checksum}, got {asset_row.sha256_hash}"
                )
            else:
                warnings.append(f"No checksum recorded for asset {asset_id}")

    return ManifestValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        total_assets_checked=total_checked,
        checksum_matches=checksum_ok,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset_type_to_layer(asset_type: str) -> str:
    """Map asset_type enum to composition layer type."""
    mapping = {
        "scene_image": "background",
        "video_clip": "background",
        "animation": "background",
        "tts_audio": "audio",
        "talking_head": "talking_head",
        "caption_srt": "captions",
        "caption_vtt": "captions",
        "lower_third": "lower_third",
    }
    return mapping.get(asset_type, "background")
