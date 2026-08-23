"""
Checkpoint service: queries, resume orchestration, clear.

Per §5.2.4 — provides access to pipeline checkpoint data for
monitoring and resume-from-failure capability.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import PipelineCheckpoint
from app.models.render_job import RenderJob
from app.schemas.checkpoint import (
    CheckpointCreateRequest,
    CheckpointResponse,
    CheckpointDetailResponse,
    CheckpointListResponse,
    ResumeResponse,
)

logger = logging.getLogger(__name__)


class CheckpointService:
    """Business logic for pipeline checkpoint management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_checkpoints(self, job_id: UUID) -> Optional[CheckpointListResponse]:
        """
        List all stage checkpoints for a job with summary info.

        Returns None if the job does not exist.
        """
        job_result = await self.db.execute(
            select(RenderJob).where(RenderJob.id == job_id)
        )
        if job_result.scalar_one_or_none() is None:
            return None

        result = await self.db.execute(
            select(PipelineCheckpoint)
            .where(PipelineCheckpoint.job_id == job_id)
            .order_by(PipelineCheckpoint.stage_index, PipelineCheckpoint.created_at)
        )
        checkpoints = result.scalars().all()

        completed = sum(1 for c in checkpoints if c.status == "complete")
        failed = sum(1 for c in checkpoints if c.status == "failed")

        last_successful = None
        for cp in reversed(checkpoints):
            if cp.status == "complete":
                last_successful = cp.stage_name
                break

        return CheckpointListResponse(
            job_id=job_id,
            total_stages=len(checkpoints),
            completed_stages=completed,
            failed_stages=failed,
            last_successful_stage=last_successful,
            checkpoints=[
                CheckpointResponse.model_validate(c) for c in checkpoints
            ],
        )

    async def upsert_checkpoint(
        self,
        job_id: UUID,
        payload: CheckpointCreateRequest,
    ) -> Optional[CheckpointDetailResponse]:
        """Write (or update) one stage checkpoint. Returns None if job not found.

        UPSERT rather than INSERT, deliberately. ``ix_pipeline_checkpoints_job_stage``
        is on ``(job_id, stage_name)`` and every stage calls ``save_checkpoint``
        twice - once with "running" at entry, once with its terminal status - so a
        plain insert would leave two rows per stage and ``list_checkpoints``'s
        "last successful stage" walk would depend on insertion order rather than on
        outcome.

        ``started_at`` is stamped on the first write for a stage, ``completed_at``
        only when the status becomes terminal, so the pair gives a real per-stage
        duration - which is the evidence WP-07's exit gate asks for when proving a
        completed stage did not re-execute.
        """
        job_result = await self.db.execute(
            select(RenderJob).where(RenderJob.id == job_id)
        )
        if job_result.scalar_one_or_none() is None:
            return None

        result = await self.db.execute(
            select(PipelineCheckpoint).where(
                PipelineCheckpoint.job_id == job_id,
                PipelineCheckpoint.stage_name == payload.stage_name,
            )
        )
        checkpoint = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        terminal = payload.status in ("complete", "failed", "skipped")

        if checkpoint is None:
            checkpoint = PipelineCheckpoint(
                job_id=job_id,
                stage_name=payload.stage_name,
                stage_index=payload.stage_index,
                checkpoint_data=payload.checkpoint_data or {},
                output_refs=payload.output_refs,
                version_fingerprint=payload.version_fingerprint,
                status=payload.status,
                started_at=now,
                completed_at=now if terminal else None,
            )
            self.db.add(checkpoint)
        else:
            checkpoint.status = payload.status
            if payload.stage_index is not None:
                checkpoint.stage_index = payload.stage_index
            if payload.checkpoint_data is not None:
                checkpoint.checkpoint_data = payload.checkpoint_data
            if payload.output_refs is not None:
                checkpoint.output_refs = payload.output_refs
            if payload.version_fingerprint is not None:
                checkpoint.version_fingerprint = payload.version_fingerprint
            if checkpoint.started_at is None:
                checkpoint.started_at = now
            if terminal:
                checkpoint.completed_at = now

        await self.db.commit()
        await self.db.refresh(checkpoint)

        logger.info(
            f"Checkpoint written: job={job_id} stage={payload.stage_name} "
            f"status={payload.status}"
        )
        return CheckpointDetailResponse.model_validate(checkpoint)

    async def get_stage_checkpoint(
        self,
        job_id: UUID,
        stage_name: str,
    ) -> Optional[CheckpointDetailResponse]:
        """Get specific stage checkpoint data for a job."""
        result = await self.db.execute(
            select(PipelineCheckpoint).where(
                PipelineCheckpoint.job_id == job_id,
                PipelineCheckpoint.stage_name == stage_name,
            )
        )
        checkpoint = result.scalar_one_or_none()
        if checkpoint is None:
            return None
        return CheckpointDetailResponse.model_validate(checkpoint)

    async def resume_from_checkpoint(
        self,
        job_id: UUID,
        resumed_by: str,
    ) -> Optional[ResumeResponse]:
        """
        Trigger pipeline resume from last successful checkpoint.

        Finds the last completed stage and creates a new render job
        starting from the next stage.
        """
        job_result = await self.db.execute(
            select(RenderJob).where(RenderJob.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        if job is None:
            return None

        if job.status != "failed":
            raise ValueError(
                f"Cannot resume job in '{job.status}' state. "
                f"Only 'failed' jobs can be resumed from checkpoints."
            )

        # Find last successful checkpoint
        result = await self.db.execute(
            select(PipelineCheckpoint)
            .where(
                PipelineCheckpoint.job_id == job_id,
                PipelineCheckpoint.status == "complete",
            )
            .order_by(PipelineCheckpoint.stage_index.desc())
            .limit(1)
        )
        last_checkpoint = result.scalar_one_or_none()

        if last_checkpoint is None:
            resume_stage = "transcript_refinement"
        else:
            # Determine next stage from the completed one
            stage_order = [
                "transcript_refinement",
                "storyboard_generation",
                "media_generation",
                "manifest_generation",
                "audio_generation",
                "talking_head_render",
                "prototype_draft",
                "final_render",
            ]
            current_idx = None
            for i, name in enumerate(stage_order):
                if name == last_checkpoint.stage_name:
                    current_idx = i
                    break

            if current_idx is not None and current_idx + 1 < len(stage_order):
                resume_stage = stage_order[current_idx + 1]
            else:
                resume_stage = last_checkpoint.stage_name

        # Create a new render job for the resume (BUG-CHECKPOINT-STAGE fix).
        # job_type must be a valid job_type enum value; we use "final_render"
        # as a neutral sentinel. The actual stage to resume from is recorded
        # in the new resume_from_stage column (added by migration 0024) and
        # consumed by the pipeline dispatcher (see commented Celery dispatch below).
        new_job = RenderJob(
            project_id=job.project_id,
            job_type="final_render",
            resume_from_stage=resume_stage,
            status="pending",
        )
        self.db.add(new_job)
        await self.db.commit()
        await self.db.refresh(new_job)

        logger.info(
            f"Pipeline resume: original_job={job_id} new_job={new_job.id} "
            f"resume_from={resume_stage} by={resumed_by}"
        )

        # Phase 5: dispatch Celery task
        # celery_app.send_task(
        #     "pipeline.execute_stage",
        #     args=[str(new_job.id)],
        #     kwargs={"resume_from": resume_stage, "original_job_id": str(job_id)},
        # )

        return ResumeResponse(
            job_id=job_id,
            resume_from_stage=resume_stage,
            new_job_id=new_job.id,
            message=(
                f"Pipeline resumed from stage '{resume_stage}'. "
                f"New job created: {new_job.id}"
            ),
        )

    async def clear_checkpoints(
        self,
        job_id: UUID,
        cleared_by: str,
    ) -> Optional[int]:
        """
        Clear all checkpoints for a job (full pipeline restart).

        Returns the number of checkpoints deleted, or None if job not found.
        """
        job_result = await self.db.execute(
            select(RenderJob).where(RenderJob.id == job_id)
        )
        if job_result.scalar_one_or_none() is None:
            return None

        result = await self.db.execute(
            delete(PipelineCheckpoint)
            .where(PipelineCheckpoint.job_id == job_id)
            .returning(PipelineCheckpoint.id)
        )
        deleted_ids = result.scalars().all()
        await self.db.commit()

        logger.info(
            f"Checkpoints cleared: job={job_id} count={len(deleted_ids)} "
            f"by={cleared_by}"
        )
        return len(deleted_ids)
