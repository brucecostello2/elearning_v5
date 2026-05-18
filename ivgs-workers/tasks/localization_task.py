"""Celery task for the full localization pipeline (one target language)."""
import logging
from celery import Task
from ivgs_workers.celeryconfig import app as celery_app
from app.services.localization_service import LocalizationService
from app.services.manifest_service import ManifestService
from app.middleware.checkpoint import CheckpointService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.localize_job",
    queue="gpu_tts",
    acks_late=True,
    max_retries=2,
    default_retry_delay=120,
    time_limit=7200,   # 2h hard limit
)
def localize_job_task(
    job_id: str,
    target_language: str,
    config_id: int,
) -> Dict:
    """
    Run the complete localization pipeline for one target language:
    1. Translate transcript via GPT-4
    2. Generate TTS per scene in target language
    3. Align captions to new audio
    4. Recompose video with localized assets
    """
    import os
    from app.core.dependencies import get_services

    logger.info("Starting localization: job=%s lang=%s config=%d",
                job_id, target_language, config_id)

    services = get_services()
    service: LocalizationService = services.localization

    success = service.run_full_localization(
        job_id=job_id,
        target_language=target_language,
        config_id=config_id,
    )

    if success:
        logger.info("Localization complete: job=%s lang=%s",
                    job_id, target_language)
        return {"success": True, "language": target_language}
    else:
        logger.error("Localization failed: job=%s lang=%s",
                     job_id, target_language)
        raise RuntimeError(
            f"Localization pipeline failed for {job_id} → {target_language}")


from typing import Dict
