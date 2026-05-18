"""Post-generation asset quality validation task.

Called after every asset generation (image, video, audio) to:
  1. Score the asset via QualityValidator
  2. On approved: proceed to next pipeline stage
  3. On flagged:  add to human review queue, hold pipeline
  4. On rejected: trigger regeneration (max 2 attempts per asset)
"""

import logging
from typing import Optional
from celery import shared_task

from app.database import get_db_context
from app.services.quality_validator import QualityValidator
from app.services.corruption_detector import CorruptionDetector
from app.middleware.checkpoint import CheckpointService

logger = logging.getLogger(__name__)
MAX_REGEN_ATTEMPTS = 2


@shared_task(
    name="tasks.quality_validation_task.validate_asset_quality_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
    acks_late=True,
)
def validate_asset_quality_task(
    self,
    job_id: str,
    asset_id: str,
    asset_type: str,       # image, video, audio
    asset_path: str,
    scene_id: Optional[str] = None,
    prompt: Optional[str] = None,
    expected_duration_ms: Optional[int] = None,
    regen_attempt: int = 0,
) -> dict:
    """Validate quality of a generated asset.

    Returns dict with decision and next_action.
    """
    logger.info(
        "Quality validation: job=%s asset=%s type=%s attempt=%d",
        job_id, asset_id, asset_type, regen_attempt
    )

    with get_db_context() as db:
        # First check for corruption
        detector = CorruptionDetector()
        issues = detector.validate_media(asset_path, asset_type)
        if issues:
            logger.error(
                "Asset %s is corrupted: %s", asset_id, issues
            )
            if regen_attempt < MAX_REGEN_ATTEMPTS:
                return {
                    "decision": "rejected",
                    "next_action": "regenerate",
                    "regen_attempt": regen_attempt + 1,
                    "reason": f"Corruption: {'; '.join(issues)}"
                }
            return {
                "decision": "rejected",
                "next_action": "fail_job",
                "reason": "Max regeneration attempts reached — corrupted"
            }

        validator = QualityValidator(db)

        # Route to appropriate validator by type
        if asset_type == 'image':
            score = validator.validate_image(
                asset_id=asset_id, job_id=job_id,
                image_path=asset_path,
                prompt=prompt or '',
                scene_id=scene_id,
            )
        elif asset_type == 'video':
            score = validator.validate_video(
                asset_id=asset_id, job_id=job_id,
                video_path=asset_path,
                scene_id=scene_id,
                expected_duration_ms=expected_duration_ms,
            )
        elif asset_type == 'audio':
            score = validator.validate_audio(
                asset_id=asset_id, job_id=job_id,
                audio_path=asset_path,
                scene_id=scene_id,
            )
        else:
            logger.warning("Unknown asset type '%s' — skipping", asset_type)
            return {"decision": "approved", "next_action": "proceed"}

        decision = score.decision
        logger.info(
            "Quality score: asset=%s score=%.3f decision=%s",
            asset_id, score.quality_score, decision
        )

        if decision == 'approved':
            # Update checkpoint with quality score
            checkpoint_svc = CheckpointService(db)
            try:
                checkpoint_svc.save_checkpoint(
                    job_id=job_id,
                    stage=f'quality_{scene_id or asset_id}',
                    data={
                        "asset_id": asset_id,
                        "quality_score": score.quality_score,
                        "decision": "approved"
                    },
                    outputs={"asset_path": asset_path}
                )
            except Exception:
                pass  # Checkpoint failure non-fatal for quality gate
            return {"decision": "approved", "next_action": "proceed",
                    "quality_score": score.quality_score}

        if decision == 'flagged':
            return {
                "decision": "flagged",
                "next_action": "human_review",
                "quality_score": score.quality_score,
                "score_id": score.id,
            }

        # Rejected — trigger regeneration if under limit
        if regen_attempt < MAX_REGEN_ATTEMPTS:
            return {
                "decision": "rejected",
                "next_action": "regenerate",
                "regen_attempt": regen_attempt + 1,
                "quality_score": score.quality_score,
                "rejection_reasons": score.get_rejection_reasons(),
            }

        return {
            "decision": "rejected",
            "next_action": "fail_job",
            "quality_score": score.quality_score,
            "reason": "Max regeneration attempts reached",
        }
