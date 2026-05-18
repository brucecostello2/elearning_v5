"""REST endpoints for lip sync validation."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from app.core.database import get_db
from app.models.lip_sync import LipSyncValidation
from app.schemas.lip_sync import LipSyncValidationResponse

router = APIRouter(prefix="/api/v1", tags=["lip-sync"])


@router.get("/jobs/{job_id}/lip-sync/validations",
            response_model=List[LipSyncValidationResponse])
async def list_lip_sync_validations(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    records = db.query(LipSyncValidation).filter_by(
        job_id=job_id).order_by(
        LipSyncValidation.validated_at.desc()).all()
    return [LipSyncValidationResponse.from_orm(r) for r in records]


@router.get("/jobs/{job_id}/lip-sync/validations/{scene_id}",
            response_model=LipSyncValidationResponse)
async def get_lip_sync_validation(
    job_id: uuid.UUID,
    scene_id: str,
    db: Session = Depends(get_db),
):
    record = db.query(LipSyncValidation).filter_by(
        job_id=job_id, scene_id=scene_id).order_by(
        LipSyncValidation.validated_at.desc()).first()
    if not record:
        raise HTTPException(404, f"No lip sync validation for scene {scene_id}")
    return LipSyncValidationResponse.from_orm(record)


@router.post("/jobs/{job_id}/lip-sync/validations/{scene_id}/retry")
async def retry_lip_sync(
    job_id: uuid.UUID,
    scene_id: str,
    db: Session = Depends(get_db),
):
    """Trigger re-validation of lip sync after regeneration."""
    record = db.query(LipSyncValidation).filter_by(
        job_id=job_id, scene_id=scene_id).order_by(
        LipSyncValidation.validated_at.desc()).first()
    if not record:
        raise HTTPException(404, "No validation record found for retry")
    from ivgs_workers.tasks.lip_sync_validation_task import validate_lip_sync_task
    task = validate_lip_sync_task.delay(
        str(job_id), record.asset_id,
        None, None)  # paths resolved from asset record in worker
    return {"task_id": task.id, "status": "queued"}
