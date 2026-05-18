"""PipelineOrchestrator — resumable stage-by-stage pipeline execution.

The orchestrator is the central coordinator for all pipeline jobs. It
builds the stage execution graph, queries checkpoints to skip completed
stages, dispatches Celery tasks, and handles failures.

Key behaviour:
- On first run: dispatches all stages in order
- On resume: skips stages with status='complete', re-dispatches from
  the first incomplete stage
- On permanent failure: marks job as 'failed' and stops

Usage:
    orchestrator = PipelineOrchestrator(db_session)
    orchestrator.execute_pipeline(job_id=42)
    # After a crash:
    orchestrator.resume_pipeline(job_id=42)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from celery import signature
from sqlalchemy.orm import Session

from app.middleware.checkpoint import CheckpointService, PIPELINE_STAGE_ORDER
from app.services.retry_policy import RetryPolicy
from app.models.checkpoint import PipelineCheckpoint

logger = logging.getLogger(__name__)


@dataclass
class StageDefinition:
    """Defines a single pipeline stage."""

    name: str
    index: int
    celery_task_name: str
    queue: str
    max_retries: int = 4
    timeout_seconds: int = 300
    build_args: Callable[[int, "StageContext"], Dict[str, Any]] = field(
        default_factory=lambda: lambda job_id, ctx: {}
    )


@dataclass
class StageContext:
    """Carries outputs from completed stages to subsequent stage arg builders."""

    job_id: int
    checkpoint_outputs: Dict[str, Optional[Dict[str, Any]]] = field(
        default_factory=dict
    )

    def get_output(self, stage: str, key: str, default: Any = None) -> Any:
        """Safely retrieve output from a prior stage."""
        outputs = self.checkpoint_outputs.get(stage)
        if not outputs:
            return default
        return outputs.get(key, default)


class PipelineOrchestrator:
    """Coordinates resumable pipeline execution across Celery tasks.

    Each stage is dispatched as a Celery task. The orchestrator does not
    block waiting for task completion — instead, each task calls back into
    the orchestrator (via a dedicated Celery task) on completion to trigger
    the next stage. This enables Celery Beat to detect stalled pipelines.
    """

    STAGE_DEFINITIONS: List[StageDefinition] = [
        StageDefinition(
            name="transcript",
            index=0,
            celery_task_name="tasks.transcript.refine_transcript_task",
            queue="default",
            max_retries=4,
            timeout_seconds=120,
        ),
        StageDefinition(
            name="storyboard",
            index=1,
            celery_task_name="tasks.storyboard.generate_storyboard_task",
            queue="default",
            max_retries=4,
            timeout_seconds=120,
        ),
        StageDefinition(
            name="image_gen",
            index=2,
            celery_task_name="tasks.image_generation.generate_images_task",
            queue="gpu_image",
            max_retries=3,
            timeout_seconds=300,
        ),
        StageDefinition(
            name="tts",
            index=3,
            celery_task_name="tasks.tts.generate_tts_task",
            queue="default",
            max_retries=3,
            timeout_seconds=120,
        ),
        StageDefinition(
            name="talking_head",
            index=4,
            celery_task_name="tasks.talking_head.generate_talking_head_task",
            queue="gpu_video",
            max_retries=2,
            timeout_seconds=600,
        ),
        StageDefinition(
            name="motion_graphics",
            index=5,
            celery_task_name="tasks.motion_graphics.render_motion_graphics_task",
            queue="default",
            max_retries=4,
            timeout_seconds=300,
        ),
        StageDefinition(
            name="composition",
            index=6,
            celery_task_name="tasks.composition.compose_video_task",
            queue="composition",
            max_retries=2,
            timeout_seconds=900,
        ),
    ]

    def __init__(self, db: Session) -> None:
        self.db = db
        self.checkpoint_svc = CheckpointService(db)
        self.retry_policy = RetryPolicy(db)
        self._stage_map: Dict[str, StageDefinition] = {
            s.name: s for s in self.STAGE_DEFINITIONS
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def execute_pipeline(self, job_id: int) -> None:
        """Start a fresh pipeline execution from the first stage.

        If checkpoints already exist (e.g., partial run), this delegates
        to resume_pipeline to avoid re-executing completed stages.

        Args:
            job_id: ID of the job to execute.
        """
        resume_point = self.checkpoint_svc.get_resume_point(job_id)

        if resume_point is None:
            logger.info("Job %s pipeline already complete — skipping", job_id)
            return

        # Determine the first stage that needs execution
        first_stage_name = resume_point
        logger.info("Starting pipeline: job=%s from stage=%s",
                    job_id, first_stage_name)

        self._update_job_status(job_id, "running")
        self._dispatch_stage(job_id, first_stage_name)

    def resume_pipeline(self, job_id: int) -> None:
        """Resume a pipeline from the last successful checkpoint.

        This is the crash-recovery entry point. Called by the WorkerSupervisor
        when it detects an orphaned job.

        Args:
            job_id: ID of the failed/orphaned job to resume.
        """
        is_valid, issues = self.checkpoint_svc.validate_integrity(job_id)
        if not is_valid:
            logger.warning("Checkpoint integrity issues for job %s: %s",
                           job_id, issues)

        resume_stage = self.checkpoint_svc.get_resume_point(job_id)
        if resume_stage is None:
            logger.info("Resume called but job %s is complete", job_id)
            self._update_job_status(job_id, "complete")
            return

        logger.info("Resuming pipeline: job=%s stage=%s", job_id, resume_stage)
        self._update_job_status(job_id, "running")
        self._dispatch_stage(job_id, resume_stage)

    def handle_stage_completion(self, job_id: int,
                                 completed_stage: str) -> None:
        """Called by a Celery task after successful stage execution.

        Finds the next stage and dispatches it. If all stages are done,
        marks the job as complete.

        Args:
            job_id:          Job that just completed a stage.
            completed_stage: Name of the stage that just completed.
        """
        next_stage = self._get_next_stage(completed_stage)

        if next_stage is None:
            logger.info("All stages complete: job=%s", job_id)
            self._update_job_status(job_id, "complete")
            return

        logger.info("Dispatching next stage: job=%s stage=%s",
                    job_id, next_stage)
        self._dispatch_stage(job_id, next_stage)

    def handle_stage_failure(
        self,
        job_id: int,
        stage: str,
        error: str,
        failure_type: str = "transient",
    ) -> None:
        """Called by a Celery task when a stage fails.

        Applies retry policy: if retries remain, re-dispatches after
        backoff delay. If retries exhausted, marks job as failed.

        Args:
            job_id:       Job that experienced the failure.
            stage:        Stage that failed.
            error:        Error message / traceback summary.
            failure_type: Classification: transient/config/external/resource.
        """
        self.checkpoint_svc.mark_stage_failed(job_id, stage, error)
        self.db.commit()

        should_retry, backoff = self.retry_policy.evaluate(
            job_id=job_id,
            stage=stage,
            failure_type=failure_type,
        )

        if should_retry:
            logger.info("Scheduling retry: job=%s stage=%s backoff=%ss",
                        job_id, stage, backoff)
            self._dispatch_stage_with_countdown(job_id, stage, backoff)
        else:
            logger.error("Retries exhausted for job=%s stage=%s — marking failed",
                         job_id, stage)
            self._update_job_status(job_id, "failed")

    # ------------------------------------------------------------------
    # Stage dispatch internals
    # ------------------------------------------------------------------

    def _dispatch_stage(self, job_id: int, stage_name: str) -> None:
        """Build task args and send stage task to Celery immediately."""
        self._dispatch_stage_with_countdown(job_id, stage_name, countdown=0)

    def _dispatch_stage_with_countdown(
        self,
        job_id: int,
        stage_name: str,
        countdown: int,
    ) -> None:
        """Dispatch a stage task with optional delay (for retry backoff)."""
        stage_def = self._stage_map.get(stage_name)
        if stage_def is None:
            raise ValueError(f"Unknown pipeline stage: {stage_name}")

        # Mark stage as running in checkpoint table
        self.checkpoint_svc.mark_stage_running(
            job_id, stage_name, stage_def.index
        )
        self.db.commit()

        # Build Celery task signature and send
        task_sig = signature(
            stage_def.celery_task_name,
            args=[job_id],
            kwargs={},
            queue=stage_def.queue,
            countdown=countdown,
            time_limit=stage_def.timeout_seconds + 60,
            soft_time_limit=stage_def.timeout_seconds,
        )
        task_sig.apply_async()

        logger.debug("Dispatched: %s for job=%s countdown=%s",
                     stage_def.celery_task_name, job_id, countdown)

    # ------------------------------------------------------------------
    # Stage graph helpers
    # ------------------------------------------------------------------

    def _get_next_stage(self, current_stage: str) -> Optional[str]:
        """Return the next stage name after current_stage, or None if last."""
        try:
            idx = PIPELINE_STAGE_ORDER.index(current_stage)
        except ValueError:
            return None
        next_idx = idx + 1
        if next_idx >= len(PIPELINE_STAGE_ORDER):
            return None
        return PIPELINE_STAGE_ORDER[next_idx]

    # ------------------------------------------------------------------
    # Job status helper
    # ------------------------------------------------------------------

    def _update_job_status(self, job_id: int, status: str) -> None:
        """Update the status column on the jobs table."""
        self.db.execute(
            sa_text("UPDATE jobs SET status = :s, updated_at = now() "
                    "WHERE id = :id"),
            {"s": status, "id": job_id},
        )
        self.db.commit()


# Avoid circular import for sa_text
from sqlalchemy import text as sa_text  # noqa: E402
