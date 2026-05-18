"""REST API endpoints for composition manifest management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.manifest_service import ManifestService
from app.schemas.manifest import ManifestResponse, ManifestValidationResult

router = APIRouter(prefix="/api/v1/jobs", tags=["manifests"])


@router.get("/{job_id}/manifest", response_model=ManifestResponse)
def get_manifest(job_id: str, db: Session = Depends(get_db)):
    """Get composition manifest for a job."""
    svc = ManifestService(db)
    try:
        manifest = svc._get_or_raise(job_id)
        return ManifestResponse.model_validate(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{job_id}/manifest/generate", response_model=ManifestResponse)
def generate_manifest(job_id: str, db: Session = Depends(get_db)):
    """Generate (or regenerate) manifest from job checkpoints.

    Only valid when manifest is in draft state or doesn't exist.
    """
    svc = ManifestService(db)
    try:
        manifest = svc.generate_manifest(job_id)
        return ManifestResponse.model_validate(manifest)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{job_id}/manifest/lock", response_model=ManifestResponse)
def lock_manifest(job_id: str, db: Session = Depends(get_db)):
    """Lock manifest — validates all assets exist, then freezes timeline.

    After locking, render tasks can begin. No further timeline changes
    are possible without invalidating and regenerating.
    """
    svc = ManifestService(db)
    try:
        manifest = svc.lock_manifest(job_id)
        return ManifestResponse.model_validate(manifest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{job_id}/manifest/validate",
             response_model=ManifestValidationResult)
def validate_manifest(job_id: str, db: Session = Depends(get_db)):
    """Validate manifest asset integrity and timing consistency."""
    svc = ManifestService(db)
    try:
        result = svc.validate_manifest(job_id)
        return ManifestValidationResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
