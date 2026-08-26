"""
Render job API endpoints per §5.1.7.

Endpoints:
- GET    /api/v1/jobs                  — List render jobs across all projects
- GET    /api/v1/projects/{id}/jobs    — List render jobs for project
- GET    /api/v1/jobs/{id}             — Get job detail
- POST   /api/v1/jobs/{id}/cancel      — Cancel running job
"""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user, get_service_or_user
from app.core.rbac import require_operator_or_admin
from app.models.project import Project
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.render_job import JobResponse
from app.services.job_service import FAILED_STATUSES, TERMINAL_STATUSES, JobService
from shared.models.enums import UserRole

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


async def _visible_project_ids(
    db: AsyncSession, current_user: User,
) -> Optional[List[UUID]]:
    """The projects this user may see jobs for, or None for "all of them".

    Mirrors ProjectService._get_project_or_none's rule exactly: operators are
    scoped to projects they created, admins and the service account are not.
    Returning None rather than a list of every id keeps the admin query a plain
    scan instead of an IN over the whole table.
    """
    if current_user.role != UserRole.OPERATOR.value:
        return None
    rows = await db.execute(
        select(Project.id).where(Project.created_by == current_user.id)
    )
    return [r[0] for r in rows.all()]


@job_router.get(
    "",
    response_model=PaginatedResponse[JobResponse],
    summary="List render jobs across all projects",
)
async def list_all_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    status_filter: Optional[str] = Query(
        default=None, alias="status",
        description="Filter by job_status: pending | running | success | failed",
    ),
    job_type: Optional[str] = Query(
        default=None, description="Filter by job_type, e.g. image_generation"
    ),
    project_id: Optional[UUID] = Query(
        default=None, description="Restrict to one project"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List render jobs across every project the caller may see, newest first.

    WP-45 Task 6(a) / WP-40 §9.5. No such route existed, so the Pipeline Tracker
    listed projects and then walked each project's jobs - 1 + N requests per
    poll - and sent its state/search/date filters to the projects route, which
    ignores every one of them, so none of the filter controls did anything.

    RBAC matches the project routes: operators see their own projects' jobs.
    """
    scope = await _visible_project_ids(db, current_user)
    service = JobService(db)
    jobs, total = await service.list_all_jobs(
        page=page,
        per_page=per_page,
        status_filter=status_filter,
        job_type=job_type,
        project_id=project_id,
        project_ids=scope,
    )
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
    celery_task_id: _Optional[str] = None


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
    previous_status = job.status
    job.status = payload.status
    if payload.error_message is not None:
        job.error_message = payload.error_message
    if payload.failure_category is not None:
        job.failure_category = payload.failure_category
    if payload.stage is not None:
        job.resume_from_stage = payload.stage
    if payload.celery_task_id is not None:
        job.celery_task_id = payload.celery_task_id

    # WP-45 Task 5 / WP-40 D-4. This is the choke point every worker status
    # change passes through, which is why the stamping lives here: one site
    # rather than one per stage. Checkpoint-derived duration stays the fallback.
    JobService.stamp_status_timestamps(job, payload.status)

    await db.commit()
    await db.refresh(job)

    # WP-45 Task 2(c) / P1.4q, RULED. A terminal failure returns the project to
    # DRAFT so the operator can retrigger it. Without this the project stays in
    # whatever in-progress state it reached and POST /trigger answers 409
    # INVALID_STATE_TRANSITION forever - the operator's documented recourse was
    # an UPDATE statement against the database.
    #
    # Only on the EDGE into failure. A repeated "failed" callback (the worker
    # retries this call) must not walk the project back to DRAFT a second time
    # after somebody has deliberately moved it on.
    if payload.status in FAILED_STATUSES and previous_status not in TERMINAL_STATUSES:
        from app.services.project_service import ProjectService, active_job

        # WP-62 Task 3. THE RESET NOW REQUIRES THIS TO HAVE BEEN THE LAST LIVE
        # WORK ON THE PROJECT, AND THAT IS THE WHOLE FIX FOR THE FROZEN STEPPER.
        #
        # MEASURED, on the live fleet, project 64207933 on 2026-08-26:
        #
        #   09:07:47.255Z  "Storyboard approved ... prev_state=STORYBOARD_
        #                   GENERATION"  -> projects.state = MEDIA_GENERATION
        #   09:07:47.645Z  projects.updated_at moves; state is DRAFT
        #   09:07:49.184Z  PATCH .../state MANIFEST_GENERATION -> 409
        #                   "Invalid state transition: DRAFT -> MANIFEST_
        #                    GENERATION. Valid: [TRANSCRIPT_REFINEMENT, ERROR]"
        #   09:07:53.017Z  AUDIO_GENERATION      -> 409, same reason
        #   09:08:24.332Z  TALKING_HEAD_RENDER   -> 409, same reason
        #
        # Four hundred milliseconds after a human released the storyboard, a
        # STALE job's failure callback walked the project back to DRAFT. The
        # run carried on -- stages 4, 5 and 6 all executed and all reported --
        # and every report was refused, because the project was now three hops
        # behind the pipeline running inside it. The stepper sat at step 1
        # while the render completed.
        #
        # So a writer existed (WP-45 built it and it works: the STORYBOARD_
        # GENERATION hop at 09:00:36 was accepted), the choke point is here,
        # and c12fa967 is the same story with an older timestamp -- reset to
        # DRAFT at 15:31:10 by a failed image_generation job, then a
        # final_render that SUCCEEDED at 15:39:57 whose COMPLETE hop had
        # nowhere legal to go from DRAFT.
        #
        # THE RESET ITSELF IS NOT WRONG AND IS NOT REMOVED. P1.4q exists
        # because a project stuck in an in-progress state answers 409 forever
        # and the operator's documented recourse was an UPDATE statement. What
        # was wrong is that it fired on the failure of ANY job of the project,
        # including one that had already been superseded. `active_job` is the
        # same "is a run in flight" question the WP-61 guard asks; if the
        # answer is yes, this failure was not the end of the project's work and
        # resetting would abandon a live run.
        still_running = await active_job(db, job.project_id)
        if still_running is not None:
            logger.info(
                "P1.4q reset SKIPPED: job %s failed but project %s still has a "
                "%s %s run (job %s). Resetting to DRAFT here would strand the "
                "live run - every subsequent stage hop would be refused as an "
                "illegal transition out of DRAFT.",
                job_id, job.project_id, still_running.status,
                still_running.job_type, still_running.id,
            )
        else:
            previous_project_state = await ProjectService(db).reset_after_terminal_failure(
                job.project_id,
                reason=f"job {job_id} failed: {payload.error_message or payload.status}",
            )
            if previous_project_state:
                logger.info(
                    "P1.4q: project %s returned to DRAFT from %s after job %s failed",
                    job.project_id, previous_project_state, job_id,
                )

    return JobResponse.model_validate(job)
