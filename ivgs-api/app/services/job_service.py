"""
Render job service: job listing, detail, cancel, and status transitions.

Per §5.1.7. Job creation happens via project trigger, storyboard approval,
regeneration and checkpoint resume; this module owns what happens to a job row
once it exists.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.render_job import RenderJob

logger = logging.getLogger(__name__)

# job_status values that end a job. WP-45 Task 5: completed_at is stamped on
# entry to any of these, started_at on entry to 'running'.
TERMINAL_STATUSES = ("success", "failed")
# The subset that means the run did not produce what it was asked for. P1.4q
# returns the project to DRAFT on these, so the operator can retrigger.
FAILED_STATUSES = ("failed",)


class JobService:
    """Business logic for render job management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_jobs(
        self,
        project_id: UUID,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[RenderJob], int]:
        """List render jobs for a project, ordered by created_at DESC."""
        query = select(RenderJob).where(RenderJob.project_id == project_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(RenderJob.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        jobs = list(result.scalars().all())

        return jobs, total

    async def get_job(self, job_id: UUID) -> Optional[RenderJob]:
        """Get a single render job by ID."""
        result = await self.db.execute(
            select(RenderJob).where(RenderJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_all_jobs(
        self,
        page: int = 1,
        per_page: int = 50,
        status_filter: Optional[str] = None,
        job_type: Optional[str] = None,
        project_id: Optional[UUID] = None,
        project_ids: Optional[Sequence[UUID]] = None,
    ) -> Tuple[List[RenderJob], int]:
        """List render jobs across every project, newest first.

        WP-45 Task 6(a) / WP-40 §9.5. There was no cross-project job route, so
        the Pipeline Tracker walked projects and then each project's jobs: 1 + N
        requests per poll, 17 of them on the current fleet, and every filter
        control was sent to the *projects* route, which ignores all of them - so
        the state, search and date controls did nothing at all.

        ``project_ids`` is the RBAC scope: an operator sees their own projects'
        jobs, an admin sees everything. It is applied here rather than left to
        the caller so that a future caller cannot forget it.
        """
        query = select(RenderJob)

        if project_ids is not None:
            if not project_ids:
                return [], 0
            query = query.where(RenderJob.project_id.in_(list(project_ids)))
        if project_id is not None:
            query = query.where(RenderJob.project_id == project_id)
        if status_filter:
            query = query.where(RenderJob.status == status_filter)
        if job_type:
            query = query.where(RenderJob.job_type == job_type)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(RenderJob.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    def stamp_status_timestamps(job: RenderJob, new_status: str) -> None:
        """Stamp started_at / completed_at as a job crosses a status boundary.

        WP-45 Task 5 / WP-40 D-4, RULED. ``render_jobs.started_at`` and
        ``.completed_at`` were dead columns: NULL on every one of the 23 rows on
        the fleet, and a grep for either identifier across ivgs-api, ivgs-workers
        and shared/ found only reads and schema declarations. Nothing had ever
        written them. Job duration was reconstructed from pipeline_checkpoints
        instead, which only 2 of 11 terminal jobs had.

        Checkpoint-derived duration REMAINS the fallback, as ruled - it is
        finer-grained and it is what the tracker already knows how to read. These
        columns answer the coarser question the checkpoints cannot: how long the
        job took, including the time before the first stage checkpointed.

        Stamped here, in one place, rather than at each call site, because the
        four sites that move a job (the worker callback, cancel, regeneration
        dispatch and resume) would otherwise each have to remember.
        """
        now = datetime.now(timezone.utc)
        if new_status == "running" and job.started_at is None:
            job.started_at = now
        if new_status in TERMINAL_STATUSES:
            if job.started_at is None:
                # A job that went straight to terminal never announced a start.
                # Recording created_at as the start would be an invention; leaving
                # it NULL says "not measured", which is the truth.
                pass
            if job.completed_at is None:
                job.completed_at = now

    async def cancel_job(self, job_id: UUID) -> Optional[RenderJob]:
        """
        Cancel a running or pending job, and revoke the task actually running it.

        WP-45 Task 3, site 3 - and this was the live operator-facing one. The
        method marked the row ``failed``, said "Job cancelled" in the log, and
        returned 200 with the Celery revoke sitting two lines below as a comment.
        The GPU work carried on to completion: the operator had a Cancel button
        that changed a database row and nothing else, on the one surface where
        "did it actually stop?" is the whole question.

        ``terminate=True`` is deliberate. Without it, revoke only prevents a task
        that has not started from starting - which is exactly the case a cancel
        button is NOT for. With it, the worker is signalled and the running task
        raises. ``signal="SIGTERM"`` lets IVGSBaseTask.on_failure run, so GPU
        reservations are released rather than leaked (WP-08).

        A revoke that cannot be delivered is reported, not swallowed: the row is
        still marked cancelled - the operator asked for that - but the response
        and the log say the task could not be reached, because "cancelled" and
        "cancelled, and the GPU is still busy" are different facts.
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        if job.status not in ("pending", "running"):
            raise ValueError(
                f"Cannot cancel job in '{job.status}' state. "
                f"Only 'pending' or 'running' jobs can be cancelled."
            )

        revoked = False
        revoke_error: Optional[str] = None
        if job.celery_task_id:
            from app.services.celery_producer import celery_app as pipeline_celery

            try:
                pipeline_celery.control.revoke(
                    job.celery_task_id, terminate=True, signal="SIGTERM",
                )
                revoked = True
            except Exception as exc:
                revoke_error = str(exc)
        else:
            revoke_error = "job has no celery_task_id; nothing was dispatched for it"

        job.status = "failed"
        job.error_message = (
            "Cancelled by user"
            if revoked
            else f"Cancelled by user (task not revoked: {revoke_error})"
        )
        self.stamp_status_timestamps(job, "failed")
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(
            "Job cancelled: id=%s celery_task=%s revoked=%s%s",
            job_id, job.celery_task_id or "-", revoked,
            f" revoke_error={revoke_error}" if revoke_error else "",
        )
        return job
