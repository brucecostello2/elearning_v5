"""REST endpoints for multi-language localization."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.localization import LocalizationConfig, LocalizedAsset
from app.schemas.localization import (
    LocalizationRequest, LocalizationStatusResponse,
    LocalizedAssetResponse, SupportedLanguagesResponse,
)
from app.services.localization_service import LocalizationService
import uuid

router = APIRouter(prefix="/api/v1", tags=["localization"])


def get_localization_service() -> LocalizationService:
    from app.core.dependencies import get_services
    return get_services().localization


@router.post("/jobs/{job_id}/localize",
             response_model=LocalizationStatusResponse)
async def start_localization(
    job_id: uuid.UUID,
    request: LocalizationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    service: LocalizationService = Depends(get_localization_service),
):
    """Start localization pipeline for one or more target languages."""
    results = []
    for lang in request.target_languages:
        existing = db.query(LocalizationConfig).filter_by(
            job_id=job_id, target_language=lang).first()
        if existing and existing.status == "complete":
            results.append({"language": lang, "status": "already_complete",
                             "config_id": existing.id})
            continue
        config = existing or LocalizationConfig(
            job_id=job_id,
            source_language=request.source_language,
            target_language=lang,
            tts_voice_id=request.voice_map.get(lang),
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        # Dispatch Celery task
        from ivgs_workers.tasks.localization_task import localize_job_task
        celery_result = localize_job_task.delay(
            str(job_id), lang, config.id)
        config.celery_task_id = celery_result.id
        db.commit()
        results.append({"language": lang, "status": "queued",
                         "config_id": config.id})
    return LocalizationStatusResponse(job_id=str(job_id), languages=results)


@router.get("/jobs/{job_id}/localizations",
            response_model=list[LocalizationStatusResponse])
async def list_localizations(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    configs = db.query(LocalizationConfig).filter_by(
        job_id=job_id).all()
    return [LocalizationStatusResponse.from_orm(c) for c in configs]


@router.get("/jobs/{job_id}/localizations/{lang}",
            response_model=LocalizationStatusResponse)
async def get_localization(
    job_id: uuid.UUID,
    lang: str,
    db: Session = Depends(get_db),
):
    config = db.query(LocalizationConfig).filter_by(
        job_id=job_id, target_language=lang).first()
    if not config:
        raise HTTPException(404, f"No localization for language: {lang}")
    return LocalizationStatusResponse.from_orm(config)


@router.get("/localization/languages",
            response_model=SupportedLanguagesResponse)
async def supported_languages(
    service: LocalizationService = Depends(get_localization_service),
):
    return SupportedLanguagesResponse(
        languages=service.get_supported_languages())
