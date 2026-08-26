"""
Pipeline checkpoint API endpoints per §5.2.4.

Endpoints:
- POST   /api/v1/jobs/{id}/checkpoints              — Write a stage checkpoint
- GET    /api/v1/jobs/{id}/checkpoints              — List all stage checkpoints
- GET    /api/v1/jobs/{id}/checkpoints/{stage}      — Get specific stage checkpoint
- POST   /api/v1/jobs/{id}/resume                   — Resume from last checkpoint
- DELETE /api/v1/jobs/{id}/checkpoints               — Clear all checkpoints

RBAC: Owner + admin for resume/clear. The write and the two reads also accept
the internal service token (the worker fleet writes the ledger and, since
WP-63 Task 3, reads it back to attribute a failure). Viewers are denied.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.database import get_session
from app.core.rbac import (
    require_operator_or_admin,
    require_service_or_privileged_user,
)
from app.models.user import User
from app.models.render_job import RenderJob
from app.models.project import Project
from app.schemas.checkpoint import (
    CheckpointCreateRequest,
    CheckpointListResponse,
    CheckpointDetailResponse,
    ResumeResponse,
)
from app.api.v1._dispatch_guards import already_running
from app.services.project_service import PipelineAlreadyRunningError
from app.services.checkpoint_service import CheckpointService, ResumeDispatchError
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
    # WP-63 Task 3. WIDENED TO THE SERVICE TOKEN, and only these two GETs.
    #
    # The choke point that writes `render_jobs.error_message`
    # (`ivgs-workers/utils/error_handler.py::update_job_status`) now reads this
    # ledger before it writes a terminal failure, so the job row can name the
    # stage the STAGE ITSELF recorded rather than the stage that happened to
    # report last. It cannot do that on a human JWT: it runs in a Celery worker
    # holding `IVGS_SERVICE_TOKEN`.
    #
    # This is a read of rows the worker fleet wrote, through the gate that
    # already guards the POST beside it, and viewers are still denied. `/resume`
    # and DELETE stay human-facing: those ACT, and no worker calls them.
    current_user: User = Depends(require_service_or_privileged_user),
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


@router.post(
    "/{job_id}/checkpoints",
    response_model=CheckpointDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write a stage checkpoint",
)
async def create_checkpoint(
    job_id: UUID,
    payload: CheckpointCreateRequest,
    # WP-36: this is the route the WORKER FLEET calls, and the worker does not
    # hold a human JWT. require_operator_or_admin resolves through
    # get_current_user, which rejects the internal service token outright with
    # 401 before any role is examined - so every checkpoint the pipeline tried to
    # write was refused. Measured 2026-08-23 from inside ivgs-celery-node02 with
    # the worker's own credential: PATCH /jobs/<id> -> 404 (auth accepted, job
    # absent) while POST /jobs/<id>/checkpoints -> 401 on the same client, same
    # token, same host.
    #
    # require_service_or_privileged_user is the existing gate for exactly this
    # shape (rbac.py:88): it accepts the internal service token, resolving it to
    # the seeded svc-pipeline admin, OR an operator/admin human, and still denies
    # viewers with 403. It is what PATCH /jobs/{job_id} already relies on via
    # get_service_or_user (jobs.py:110).
    #
    # Deliberately NOT widened on /resume or DELETE: those ACT, they are
    # human-facing, and no worker calls them. WP-63 Task 3 did widen the two
    # GETs, and amends this sentence rather than leaving it standing over a
    # decision that has changed - see the note on `list_checkpoints`.
    current_user: User = Depends(require_service_or_privileged_user),
    db: AsyncSession = Depends(get_session),
):
    """Write (or update) a stage checkpoint for a job.

    Ledger P1.2 / WP-07. This route did not exist: the workers'
    ``save_checkpoint`` (ivgs-workers/utils/error_handler.py:427) has been POSTing
    here since the pipeline was built and receiving 405 Method Not Allowed every
    time - measured 2026-08-23, with ``pipeline_checkpoints`` holding 0 rows. The
    helper logged a warning and returned False, and none of its 15 call sites
    checked, so resume-from-failure has never had anything to resume from.

    Upsert, keyed on (job_id, stage_name): each stage writes twice, once at entry
    and once at its outcome.
    """
    await _verify_job_access(job_id, current_user, db)
    service = CheckpointService(db)
    result = await service.upsert_checkpoint(job_id, payload)
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
    # WP-63 Task 3, same reason as the list route above: the failure
    # attribution needs `checkpoint_data` (the per-stage counts) to say how
    # much of a stage failed, and it reads it from a worker.
    current_user: User = Depends(require_service_or_privileged_user),
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
    """Resume the pipeline from the last successful checkpoint.

    WP-45 Task 3, site 7. This used to create a second job row carrying
    ``resume_from_stage`` and dispatch nothing - the stub named
    ``pipeline.execute_stage``, which is not a registered task. The real entry
    point, ``dispatch_pipeline``, has read ``resume_from_stage`` off the job
    context since it was written; nothing ever sent it one.
    """
    await _verify_job_access(job_id, current_user, db)
    service = CheckpointService(db)
    try:
        result = await service.resume_from_checkpoint(job_id, current_user.username)
    except ResumeDispatchError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "DISPATCH_FAILED", "message": str(e)}},
        )
    except PipelineAlreadyRunningError as e:
        # WP-62 Task 6. CAUGHT BEFORE ValueError DELIBERATELY.
        # `PipelineAlreadyRunningError` is a ValueError subclass (WP-61 made it
        # one so existing callers kept behaving), so without this clause the
        # guard would answer INVALID_STATE_TRANSITION - the wrong code, and one
        # an operator would try to fix by changing the project's state.
        raise already_running(e)
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
