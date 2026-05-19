"""
Render job service: job listing, detail, and cancel.

Per §5.1.7 — read-only in this phase (Phase 3).
Actual job creation happens via project trigger and pipeline execution (Phase 5).
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.render_job import RenderJob

logger = logging.getLogger(__name__)


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

    async def cancel_job(self, job_id: UUID) -> Optional[RenderJob]:
        """
        Cancel a running or pending job.

        Sets status to 'failed' with error_message indicating user cancellation.
        Phase 5: will also revoke the Celery task.
        """
        job = await self.get_job(job_id)
        if job is None:
            return None

        if job.status not in ("pending", "running"):
            raise ValueError(
                f"Cannot cancel job in '{job.status}' state. "
                f"Only 'pending' or 'running' jobs can be cancelled."
            )

        job.status = "failed"
        job.error_message = "Cancelled by user"
        job.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(f"Job cancelled: id={job_id}")

        # Phase 5: revoke Celery task
        # if job.celery_task_id:
        #     celery_app.control.revoke(job.celery_task_id, terminate=True)

        return job
