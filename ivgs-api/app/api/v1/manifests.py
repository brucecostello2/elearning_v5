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

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.auth import get_service_or_user
from app.models.user import User

logger = logging.getLogger("ivgs.api.manifests")

router = APIRouter(tags=["Manifests"])


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
    current_user: User = Depends(get_service_or_user),
) -> ManifestResponse:
    """GET /api/v1/jobs/{id}/manifest — Get composition manifest with timeline JSON."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT id, job_id, status, timeline, total_duration_ms, "
                "locked_at "
                "FROM composition_manifests WHERE job_id = :job_id "
                "ORDER BY locked_at DESC NULLS LAST LIMIT 1"
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
        __import__("json").loads(row.timeline)
        if isinstance(row.timeline, str)
        else (row.timeline or {})
    )

    return ManifestResponse(
        id=str(row.id),
        job_id=str(row.job_id),
        status=row.status,
        timeline_json=timeline,
        total_duration_ms=row.total_duration_ms or 0,
        scene_count=len(timeline.get("scenes", [])) if isinstance(timeline, dict) else 0,
        locked_at=row.locked_at,
    )


@router.post("/{job_id}/manifest/generate", response_model=ManifestResponse)
async def generate_manifest(
    job_id: str,
    request: ManifestGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_service_or_user),
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
    # WP-27: created_at is selected and ordered on so "latest per scene" is
    # deterministic. Without it there was no basis on which to dedupe, and every
    # asset a scene had ever accumulated became its own layer.
    assets = (
        await db.execute(
            sa_text(
                "SELECT id, scene_id, asset_type, seaweedfs_fid, content_hash, created_at "
                "FROM assets WHERE project_id = :project_id "
                "ORDER BY created_at ASC, id ASC"
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
    # WP-27: scenes that end up with no background layer. Collected so the
    # response can say so rather than returning a manifest that looks complete.
    scenes_without_background: List[int] = []
    for scene in scenes:
        duration_ms = int(scene.duration_seconds * 1000)
        scene_assets = assets_by_scene.get(str(scene.id), [])

        # WP-27 / swallow-register instance 15. This used to append one layer per
        # asset with no filter and no dedup, so a scene with two images and two
        # audio files produced four layers -- all typed "background", because
        # _asset_type_to_layer defaulted every unmapped type to background and
        # only one of its eight keys was a real asset_type. ffmpeg then received
        # a WAV as the scene background.
        #
        # Now: unmapped types are dropped (never promoted to background), and
        # each layer_type keeps only the LATEST asset for the scene. Assets
        # arrive ordered by created_at ASC, so a later row overwrites an earlier
        # one of the same layer_type.
        latest_by_layer: Dict[str, Any] = {}
        for asset in scene_assets:
            layer_type = _asset_type_to_layer(asset.asset_type)
            if layer_type is None:
                logger.info(
                    "manifest_asset_excluded asset_id=%s asset_type=%s scene=%s "
                    "reason=no_layer_mapping",
                    asset.id, asset.asset_type, scene.id,
                )
                continue
            latest_by_layer[layer_type] = {
                "layer_type": layer_type,
                "asset_id": str(asset.id),
                "seaweedfs_fid": asset.seaweedfs_fid,
                "checksum": asset.content_hash,
                "start_time_ms": current_time_ms,
                "end_time_ms": current_time_ms + duration_ms,
            }

        layers = [latest_by_layer[k] for k in sorted(latest_by_layer)]

        # A scene with no background has nothing to composite against. That is
        # the media-generation gap the register notes as separate; it is surfaced
        # rather than passed silently, because a manifest that looks complete and
        # has no picture is how instance 15 stayed hidden.
        if "background" not in latest_by_layer:
            logger.warning(
                "manifest_scene_without_background scene_id=%s scene_index=%s "
                "asset_types=%s",
                scene.id, scene.scene_index,
                [a.asset_type for a in scene_assets],
            )
            scenes_without_background.append(int(scene.scene_index))

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
        # WP-27: recorded in the manifest itself, not only in a log line. A
        # downstream stage can then refuse a manifest whose scenes have no
        # picture, instead of discovering it when ffmpeg does.
        "scenes_without_background": scenes_without_background,
        "render_params": request.render_params or {
            "resolution_1080p": {"width": 1920, "height": 1080, "crf": 18, "fps": 30},
            "resolution_4k": {"width": 3840, "height": 2160, "crf": 20, "fps": 30},
        },
    }
    if scenes_without_background:
        logger.warning(
            "manifest_generated_with_missing_backgrounds job_id=%s scenes=%s",
            job_id, scenes_without_background,
        )

    await db.execute(
        sa_text(
            "INSERT INTO composition_manifests "
            "(id, job_id, status, timeline, total_duration_ms) "
            "VALUES (:id, :job_id, 'draft', :timeline, :total_duration_ms)"
        ),
        {
            "id": manifest_id,
            "job_id": job_id,
            "timeline": __import__("json").dumps(timeline_json),
            "total_duration_ms": current_time_ms,
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
    )


@router.post("/{job_id}/manifest/lock", response_model=ManifestResponse)
async def lock_manifest(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_service_or_user),
) -> ManifestResponse:
    """POST /api/v1/jobs/{id}/manifest/lock — Freeze timeline."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT id, status FROM composition_manifests "
                "WHERE job_id = :job_id ORDER BY locked_at DESC NULLS LAST LIMIT 1"
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
    current_user: User = Depends(get_service_or_user),
) -> ManifestValidationResult:
    """POST /api/v1/jobs/{id}/manifest/validate — Validate asset references + checksums."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT id, timeline FROM composition_manifests "
                "WHERE job_id = :job_id ORDER BY locked_at DESC NULLS LAST LIMIT 1"
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
        __import__("json").loads(row.timeline)
        if isinstance(row.timeline, str)
        else (row.timeline or {})
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
                    sa_text("SELECT id, content_hash, seaweedfs_fid FROM assets WHERE id = :id"),
                    {"id": asset_id},
                )
            ).fetchone()

            if not asset_row:
                errors.append(f"Asset {asset_id} referenced in manifest does not exist")
                continue

            if expected_checksum and asset_row.content_hash == expected_checksum:
                checksum_ok += 1
            elif expected_checksum:
                errors.append(
                    f"Checksum mismatch for asset {asset_id}: "
                    f"expected {expected_checksum}, got {asset_row.content_hash}"
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

# Keyed on the REAL asset_type enum. Verified 2026-08-23 against the live
# database: enum_range(NULL::asset_type) is
#   image, video, audio, document, talking_head, final_render, reference_clip
#
# WP-27. The previous mapping was keyed on scene_image / video_clip / animation
# / tts_audio / caption_srt / caption_vtt / lower_third -- names this schema has
# never used. Exactly ONE of its eight keys (talking_head) was a real enum
# value, so 44 of the 45 assets on the reference project missed the mapping and
# fell through to a `"background"` default. That default is what made a miss
# destructive: an unmapped asset did not become an unknown layer, it became the
# scene's background. Audio, documents and the user's reference clip were all
# eligible to be composited as the picture.
_ASSET_TYPE_TO_LAYER = {
    "image": "background",
    "video": "background",
    "audio": "audio",
    "talking_head": "talking_head",
}

# Present in the enum and deliberately NOT layers: `document` is a source
# upload, `final_render` is pipeline output, `reference_clip` is the presenter
# source consumed by Stage 6. None belongs on a scene timeline.
_ASSET_TYPES_NOT_LAYERS = frozenset({"document", "final_render", "reference_clip"})


def _asset_type_to_layer(asset_type: str) -> Optional[str]:
    """Map an asset_type to a composition layer type, or None if it is not a layer.

    Returns None rather than defaulting to "background". An asset type nobody
    mapped is an asset type nobody has reasoned about, and the safest thing to do
    with it is leave it out of the timeline -- not hand it to ffmpeg as the
    picture.
    """
    return _ASSET_TYPE_TO_LAYER.get(asset_type)
