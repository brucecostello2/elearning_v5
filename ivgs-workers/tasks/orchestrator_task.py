"""Celery tasks for pipeline orchestration entry points.

These tasks are the external entry points to the pipeline:
- execute_pipeline_task: Start or resume a job (dispatched by API on job creation)
- resume_pipeline_task: Resume an orphaned job (dispatched by WorkerSupervisor)
- stage_completed_task: Called by each stage task on success to advance pipeline
- stage_failed_task: Called by each stage task on failure to apply retry policy
"""
from __future__ import annotations

import logging

from celery import shared_task
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    """Create a new database session for task execution."""
    return SessionLocal()


@shared_task(
    name="tasks.orchestrator.execute_pipeline_task",
    bind=True,
    acks_late=True,
    max_retries=0,  # Orchestrator itself doesn't retry — stages handle retries
)
def execute_pipeline_task(self, job_id: int) -> None:
    """Entry point: start or resume pipeline execution for a job.

    Called by the API when a job is created or manually restarted.
    Uses checkpoints to skip already-complete stages.

    Args:
        job_id: ID of the job to execute.
    """
    logger.info("execute_pipeline_task: job=%d", job_id)
    db = _get_db()
    try:
        orchestrator = PipelineOrchestrator(db)
        orchestrator.execute_pipeline(job_id)
    except Exception as exc:
        logger.error("Pipeline execution failed: job=%d error=%s", job_id, exc)
        raise
    finally:
        db.close()


@shared_task(
    name="tasks.orchestrator.resume_pipeline_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def resume_pipeline_task(self, job_id: int) -> None:
    """Crash recovery entry: resume a stalled pipeline from last checkpoint.

    Called by the WorkerSupervisor when it detects an orphaned job (job
    in 'running' state with no worker heartbeat for >60 seconds).

    Args:
        job_id: ID of the orphaned job to resume.
    """
    logger.info("resume_pipeline_task: job=%d", job_id)
    db = _get_db()
    try:
        orchestrator = PipelineOrchestrator(db)
        orchestrator.resume_pipeline(job_id)
    except Exception as exc:
        logger.error("Pipeline resume failed: job=%d error=%s", job_id, exc)
        raise
    finally:
        db.close()


@shared_task(
    name="tasks.orchestrator.stage_completed_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def stage_completed_task(self, job_id: int, completed_stage: str) -> None:
    """Advance pipeline to the next stage after a stage completes.

    Each stage task calls this on success. The orchestrator decides
    what to dispatch next (or marks job complete if all done).

    Args:
        job_id:          Job that just completed a stage.
        completed_stage: Name of the stage that completed.
    """
    logger.info("stage_completed_task: job=%d stage=%s", job_id, completed_stage)
    db = _get_db()
    try:
        orchestrator = PipelineOrchestrator(db)
        orchestrator.handle_stage_completion(job_id, completed_stage)
    finally:
        db.close()


@shared_task(
    name="tasks.orchestrator.stage_failed_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def stage_failed_task(
    self,
    job_id: int,
    stage: str,
    error: str,
    failure_type: str = "transient",
) -> None:
    """Handle stage failure: apply retry policy, reschedule or mark failed.

    Args:
        job_id:       Job ID.
        stage:        Stage name that failed.
        error:        Error message/traceback.
        failure_type: transient/config/external/resource.
    """
    logger.warning("stage_failed_task: job=%d stage=%s type=%s",
                   job_id, stage, failure_type)
    db = _get_db()
    try:
        orchestrator = PipelineOrchestrator(db)
        orchestrator.handle_stage_failure(job_id, stage, error, failure_type)
    finally:
        db.close()
