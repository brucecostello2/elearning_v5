"""Celery task for caption forced-alignment using STT + MFA/Gentle."""
import os
import logging
from typing import Optional
from ivgs_workers.celeryconfig import app as celery_app
from app.services.caption_reconciliation import CaptionReconciliation
from app.services.manifest_service import ManifestService

logger = logging.getLogger(__name__)

WORKDIR = os.environ.get("WORKDIR", "/mnt/workdir")
MFA_PATH = os.environ.get("MFA_PATH", "/opt/mfa")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
REVIEW_THRESHOLD = 0.90   # Flag for human review if STT match < 90%


@celery_app.task(
    name="tasks.align_captions",
    queue="default",
    acks_late=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=600,
)
def align_captions_task(
    job_id: str,
    scene_id: str,
    audio_path: str,
    original_text: str,
    language_code: str = "en",
    update_manifest: bool = True,
) -> dict:
    """
    Run STT → compare → forced alignment → generate SRT/VTT.
    Optionally update the composition manifest with aligned caption timing.
    """
    reconciler = CaptionReconciliation(
        workdir=WORKDIR,
        mfa_path=MFA_PATH,
        whisper_model=WHISPER_MODEL,
    )

    logger.info("Aligning captions: job=%s scene=%s lang=%s",
                job_id, scene_id, language_code)

    srt_path, vtt_path = reconciler.align_captions(
        job_id=job_id,
        scene_id=scene_id,
        audio_path=audio_path,
        original_text=original_text,
        language_code=language_code,
    )

    # Retrieve the saved alignment record to check status
    from app.core.database import get_db_context
    from app.models.caption_alignment import CaptionAlignment
    with get_db_context() as db:
        alignment = db.query(CaptionAlignment).filter_by(
            job_id=job_id, scene_id=scene_id,
            language_code=language_code).order_by(
            CaptionAlignment.created_at.desc()).first()

    if alignment is None:
        raise RuntimeError("Alignment record not persisted")

    if alignment.text_match_ratio < REVIEW_THRESHOLD:
        logger.warning(
            "Caption text match %.2f%% < %.0f%% threshold — "
            "flagging for human review (scene=%s)",
            alignment.text_match_ratio * 100,
            REVIEW_THRESHOLD * 100,
            scene_id,
        )

    # Optionally update composition manifest caption timing
    if update_manifest and alignment.status == "aligned":
        try:
            from app.core.dependencies import get_services
            manifest_svc: ManifestService = get_services().manifest
            manifest_svc.update_scene_captions(
                job_id=job_id,
                scene_id=scene_id,
                srt_path=srt_path,
                vtt_path=vtt_path,
                word_timestamps=alignment.word_timestamps or [],
            )
            logger.info("Manifest caption timing updated for scene %s",
                        scene_id)
        except Exception as exc:
            logger.warning("Manifest update skipped: %s", exc)

    return {
        "success": alignment.status in ("aligned", "review_required"),
        "status": alignment.status,
        "srt_path": srt_path,
        "vtt_path": vtt_path,
        "drift_ms_max": alignment.drift_ms_max,
        "match_ratio": alignment.text_match_ratio,
        "requires_review": alignment.status == "review_required",
    }
