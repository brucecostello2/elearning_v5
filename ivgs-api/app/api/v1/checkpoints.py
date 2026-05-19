"""
Pipeline checkpoint API endpoints per §5.2.4.

Endpoints:
- GET    /api/v1/jobs/{id}/checkpoints              — List all stage checkpoints
- GET    /api/v1/jobs/{id}/checkpoints/{stage}      — Get specific stage checkpoint
- POST   /api/v1/jobs/{id}/resume                   — Resume from last checkpoint
- DELETE /api/v1/jobs/{id}/checkpoints               — Clear all checkpoints

RBAC: Owner + admin for resume/clear. All authenticated for read.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.models.render_job import RenderJob
from app.models.project import Project
from app.schemas.checkpoint import (
    CheckpointListResponse,
    CheckpointDetailResponse,
    ResumeResponse,
)
from app.services.checkpoint_service import CheckpointService
from shared.models.enums import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Pipeline Checkpoints"])


async def _verify_job_access(
    job_id: UUID, current_user: User, db: AsyncSession
) -> RenderJob:
    """
    Verify the user has access to the job.

    Admins can access all jobs. Operators can only access jobs
    belonging to their own projects.
    """
    result = await db.execute(select(RenderJob).where(RenderJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            },
        )

    if current_user.role != UserRole.ADMIN.value:
        proj_result = await db.execute(
            select(Project).where(Project.id == job.project_id)
        )
        project = proj_result.scalar_one_or_none()
        if project and project.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "You do not have access to this job's checkpoints",
                    }
                },
            )

    return job


@router.get(
    "/{job_id}/checkpoints",
    response_model=CheckpointListResponse,
    summary="List all stage checkpoints",
)
async def list_checkpoints(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all stage checkpoints with status for a job."""
    await _verify_job_access(job_id, current_user, db)
    service = CheckpointService(db)
    result = await service.list_checkpoints(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            },
        )
    return result


@router.get(
    "/{job_id}/checkpoints/{stage_name}",
    response_model=CheckpointDetailResponse,
    summary="Get specific stage checkpoint",
)
async def get_stage_checkpoint(
    job_id: UUID,
    stage_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get specific stage checkpoint data including checkpoint_data and output_refs."""
    await _verify_job_access(job_id, current_user, db)
    service = CheckpointService(db)
    result = await service.get_stage_checkpoint(job_id, stage_name)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": (
                        f"Checkpoint for stage '{stage_name}' not found "
                        f"in job {job_id}"
                    ),
                }
            },
        )
    return result


@router.post(
    "/{job_id}/resume",
    response_model=ResumeResponse,
    summary="Resume pipeline from checkpoint",
)
async def resume_pipeline(
    job_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Trigger pipeline resume from last successful checkpoint."""
    await _verify_job_access(job_id, current_user, db)
    service = CheckpointService(db)
    try:
        result = await service.resume_from_checkpoint(job_id, current_user.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                }
            },
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            },
        )
    return result


@router.delete(
    "/{job_id}/checkpoints",
    status_code=status.HTTP_200_OK,
    summary="Clear all checkpoints for a job",
)
async def clear_checkpoints(
    job_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Clear all checkpoints for full pipeline restart."""
    await _verify_job_access(job_id, current_user, db)
    service = CheckpointService(db)
    count = await service.clear_checkpoints(job_id, current_user.username)
    if count is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            },
        )
    return {"deleted_count": count, "message": f"Cleared {count} checkpoints for job {job_id}"}
