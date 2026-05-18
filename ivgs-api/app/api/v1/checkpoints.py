"""REST endpoints for pipeline checkpoint management."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.checkpoint import CheckpointService
from app.schemas.checkpoint import (
    CheckpointListResponse,
    CheckpointResponse,
    ResumeRequest,
    ResumeResponse,
)

router = APIRouter(prefix="/jobs/{job_id}/checkpoints", tags=["checkpoints"])


def _svc(db: Session = Depends(get_db)) -> CheckpointService:
    return CheckpointService(db)


@router.get("", response_model=CheckpointListResponse)
def list_checkpoints(
    job_id: int,
    svc: CheckpointService = Depends(_svc),
) -> CheckpointListResponse:
    """List all pipeline checkpoints for a job, ordered by stage index."""
    checkpoints = svc.get_all_checkpoints(job_id)
    return CheckpointListResponse(
        job_id=job_id,
        checkpoints=[CheckpointResponse.from_orm(cp) for cp in checkpoints],
        resume_point=svc.get_resume_point(job_id),
    )


@router.get("/{stage}", response_model=CheckpointResponse)
def get_checkpoint(
    job_id: int,
    stage: str,
    svc: CheckpointService = Depends(_svc),
) -> CheckpointResponse:
    """Fetch a single checkpoint by stage name."""
    cp = svc.get_checkpoint(job_id, stage)
    if cp is None:
        raise HTTPException(status_code=404,
                            detail=f"No checkpoint for stage '{stage}'")
    return CheckpointResponse.from_orm(cp)


@router.post("/resume", response_model=ResumeResponse)
def resume_pipeline(
    job_id: int,
    _req: ResumeRequest,
    db: Session = Depends(get_db),
) -> ResumeResponse:
    """Trigger a pipeline resume from the last successful checkpoint."""
    from app.services.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(db)
    resume_stage = CheckpointService(db).get_resume_point(job_id)

    if resume_stage is None:
        return ResumeResponse(
            job_id=job_id,
            message="Pipeline already complete.",
            resume_stage=None,
        )

    orchestrator.resume_pipeline(job_id)
    return ResumeResponse(
        job_id=job_id,
        message=f"Pipeline resume dispatched from stage '{resume_stage}'.",
        resume_stage=resume_stage,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_checkpoints(
    job_id: int,
    svc: CheckpointService = Depends(_svc),
    db: Session = Depends(get_db),
) -> None:
    """Delete all checkpoints for a job (forces full restart on next run)."""
    svc.clear_checkpoints(job_id)
    db.commit()
