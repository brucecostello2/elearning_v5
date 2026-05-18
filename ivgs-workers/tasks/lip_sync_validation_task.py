"""Celery task for SyncNet lip sync validation + auto-retry."""
import os
import logging
from typing import Optional
from ivgs_workers.celeryconfig import app as celery_app
from app.services.lip_sync_validator import (
    LipSyncValidator,
    SYNCNET_THRESHOLD_PASS,
    SYNCNET_THRESHOLD_RETRY,
)
from app.core.database import get_db_context
from app.models.assets import Asset   # Phase 1 assets table

logger = logging.getLogger(__name__)

SYNCNET_MODEL_PATH = os.environ.get("SYNCNET_MODEL_PATH", "")
WORKDIR = os.environ.get("WORKDIR", "/mnt/workdir")
MAX_LIP_SYNC_RETRIES = 2


@celery_app.task(
    name="tasks.validate_lip_sync",
    queue="gpu_video",
    acks_late=True,
    max_retries=0,   # Retries managed manually below
    time_limit=300,
)
def validate_lip_sync_task(
    job_id: str,
    asset_id: int,
    video_path: Optional[str] = None,
    audio_path: Optional[str] = None,
    attempt: int = 1,
) -> dict:
    """
    Validate lip sync quality for a talking-head asset.
    - score >= 0.85: approve and proceed
    - 0.70–0.85: retry talking-head generation (max 2 retries)
    - score < 0.70: fall back to static avatar + waveform
    """
    validator = LipSyncValidator(
        syncnet_model_path=SYNCNET_MODEL_PATH,
        workdir=WORKDIR,
    )

    # Resolve asset paths from DB if not provided
    if video_path is None or audio_path is None:
        with get_db_context() as db:
            asset = db.query(Asset).filter_by(id=asset_id).first()
            if asset is None:
                raise RuntimeError(f"Asset {asset_id} not found")
            video_path = video_path or asset.video_path
            audio_path = audio_path or asset.audio_path
            scene_id = asset.scene_id

    if not video_path or not os.path.exists(video_path):
        raise RuntimeError(f"Video not found: {video_path}")
    if not audio_path or not os.path.exists(audio_path):
        raise RuntimeError(f"Audio not found: {audio_path}")

    validation = validator.validate(
        asset_id=asset_id,
        job_id=job_id,
        scene_id=scene_id,
        video_path=video_path,
        audio_path=audio_path,
        threshold=SYNCNET_THRESHOLD_PASS,
    )

    action = validator.get_action(validation.sync_score)
    logger.info("Lip sync: score=%.3f action=%s attempt=%d",
                validation.sync_score, action, attempt)

    if action == "approve":
        return {
            "approved": True,
            "score": validation.sync_score,
            "asset_id": asset_id,
        }

    elif action == "retry_generation" and attempt < MAX_LIP_SYNC_RETRIES:
        logger.info("Triggering talking-head regeneration (attempt %d/%d)",
                    attempt, MAX_LIP_SYNC_RETRIES)
        # Re-enqueue talking head generation
        from ivgs_workers.tasks.talking_head_task import \
            generate_talking_head_task
        generate_talking_head_task.apply_async(
            kwargs={
                "job_id": job_id,
                "scene_id": scene_id,
                "lip_sync_retry": True,
                "lip_sync_attempt": attempt + 1,
            },
            queue="gpu_video",
        )
        return {
            "approved": False,
            "score": validation.sync_score,
            "action": "retrying_talking_head",
            "attempt": attempt,
        }

    else:
        # Fallback: static avatar + waveform
        logger.warning(
            "Lip sync failed after %d attempts (score=%.3f) — "
            "falling back to static avatar", attempt, validation.sync_score)
        from ivgs_workers.tasks.motion_graphics_task import \
            render_motion_graphics_task
        render_motion_graphics_task.apply_async(
            kwargs={
                "job_id": job_id,
                "scene_id": scene_id,
                "effect": "static_avatar_waveform",
            },
            queue="gpu_video",
        )
        return {
            "approved": False,
            "score": validation.sync_score,
            "action": "fallback_static_avatar",
            "attempt": attempt,
        }
