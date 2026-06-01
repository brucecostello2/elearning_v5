"""
Render job API endpoints per §5.1.7.

Endpoints:
- GET    /api/v1/projects/{id}/jobs    — List render jobs for project
- GET    /api/v1/jobs/{id}             — Get job detail
- POST   /api/v1/jobs/{id}/cancel      — Cancel running job
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user, get_service_or_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.render_job import JobResponse
from app.services.job_service import JobService

logger = logging.getLogger(__name__)

project_job_router = APIRouter(prefix="/projects/{project_id}/jobs", tags=["Jobs"])
job_router = APIRouter(prefix="/jobs", tags=["Jobs"])


@project_job_router.get(
    "",
    response_model=PaginatedResponse[JobResponse],
    summary="List render jobs for project",
)
async def list_jobs(
    project_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List render jobs for project, ordered by created_at DESC."""
    service = JobService(db)
    jobs, total = await service.list_jobs(project_id, page, per_page)
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@job_router.get("/{job_id}", response_model=JobResponse, summary="Get job detail")
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get job detail including checkpoint states and retry history."""
    service = JobService(db)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Job {job_id} not found"}},
        )
    return JobResponse.model_validate(job)


@job_router.post("/{job_id}/cancel", response_model=JobResponse, summary="Cancel running job")
async def cancel_job(
    job_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Cancel running job."""
    service = JobService(db)
    try:
        job = await service.cancel_job(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "INVALID_STATE_TRANSITION", "message": str(e)}},
        )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Job {job_id} not found"}},
        )
    return JobResponse.model_validate(job)


# --- internal job-status callback (PATCH /jobs/{id}); worker fleet, service-token auth ---
from typing import Optional as _Optional
from pydantic import BaseModel as _BaseModel


class JobStatusUpdate(_BaseModel):
    """Body for PATCH /jobs/{id} — internal job-status callback from the worker fleet."""

    status: str
    error_message: _Optional[str] = None
    failure_category: _Optional[str] = None
    stage: _Optional[str] = None


@job_router.patch("/{job_id}", response_model=JobResponse, summary="Update job status (internal)")
async def update_job_status(
    job_id: UUID,
    payload: JobStatusUpdate,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """Update a render job status/error fields. Called by the worker fleet (service token).

    Authenticated by get_service_or_user. Only fields the worker sends are written; `stage`
    (the worker's current stage) is recorded on resume_from_stage.
    """
    service = JobService(db)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Job {job_id} not found"}},
        )
    job.status = payload.status
    if payload.error_message is not None:
        job.error_message = payload.error_message
    if payload.failure_category is not None:
        job.failure_category = payload.failure_category
    if payload.stage is not None:
        job.resume_from_stage = payload.stage
    await db.commit()
    await db.refresh(job)
    return JobResponse.model_validate(job)
