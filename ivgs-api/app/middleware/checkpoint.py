"""CheckpointService — persists and loads pipeline stage checkpoints.

This is the single source of truth for pipeline resumability. All
Celery tasks call save_checkpoint() on success and the PipelineOrchestrator
calls get_resume_point() to determine where to restart a failed job.

Usage:
    svc = CheckpointService(db_session)
    svc.save_checkpoint(job_id=42, stage="transcript",
                        stage_index=0, data=params, outputs={"path": "..."})
    resume_from = svc.get_resume_point(job_id=42)  # "image_gen"
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.checkpoint import PipelineCheckpoint

logger = logging.getLogger(__name__)

# Ordered pipeline stages — index determines resume priority
PIPELINE_STAGE_ORDER: List[str] = [
    "transcript",
    "storyboard",
    "image_gen",
    "tts",
    "talking_head",
    "motion_graphics",
    "composition",
]


class CheckpointService:
    """Manages pipeline checkpoint persistence and resume logic.

    All database operations use the provided SQLAlchemy session. The
    caller is responsible for committing the session after mutations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_checkpoint(
        self,
        job_id: int,
        stage: str,
        stage_index: int,
        data: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
    ) -> PipelineCheckpoint:
        """Create or update a checkpoint row for this stage.

        If a checkpoint already exists for (job_id, stage), it is updated
        in-place (idempotent — safe to call multiple times).

        Args:
            job_id:      The job this checkpoint belongs to.
            stage:       Stage name, must be in PIPELINE_STAGE_ORDER.
            stage_index: Position of stage in ordered sequence.
            data:        Input parameters stored for audit/replay.
            outputs:     Output references (file paths, durations, etc.)

        Returns:
            The created or updated PipelineCheckpoint instance.
        """
        checkpoint = (
            self.db.query(PipelineCheckpoint)
            .filter_by(job_id=job_id, stage_name=stage)
            .first()
        )

        fingerprint = self._compute_fingerprint(data)

        if checkpoint is None:
            checkpoint = PipelineCheckpoint(
                job_id=job_id,
                stage_name=stage,
                stage_index=stage_index,
                checkpoint_data=data,
                version_fingerprint=fingerprint,
            )
            self.db.add(checkpoint)

        checkpoint.mark_complete(outputs or {})
        checkpoint.version_fingerprint = fingerprint

        try:
            self.db.flush()
        except Exception as exc:
            self.db.rollback()
            logger.error("Checkpoint save failed job=%s stage=%s: %s",
                         job_id, stage, exc)
            raise

        logger.info("Checkpoint saved: job=%s stage=%s", job_id, stage)
        return checkpoint

    def mark_stage_running(self, job_id: int, stage: str,
                            stage_index: int) -> PipelineCheckpoint:
        """Upsert a checkpoint in 'running' state (before execution starts)."""
        checkpoint = (
            self.db.query(PipelineCheckpoint)
            .filter_by(job_id=job_id, stage_name=stage)
            .first()
        )
        if checkpoint is None:
            checkpoint = PipelineCheckpoint(
                job_id=job_id,
                stage_name=stage,
                stage_index=stage_index,
            )
            self.db.add(checkpoint)

        checkpoint.mark_running()
        self.db.flush()
        return checkpoint

    def mark_stage_failed(self, job_id: int, stage: str,
                           error: str) -> Optional[PipelineCheckpoint]:
        """Mark an existing checkpoint as failed with error detail."""
        checkpoint = (
            self.db.query(PipelineCheckpoint)
            .filter_by(job_id=job_id, stage_name=stage)
            .first()
        )
        if checkpoint:
            checkpoint.mark_failed(error)
            self.db.flush()
        return checkpoint

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_checkpoint(self, job_id: int,
                        stage: str) -> Optional[PipelineCheckpoint]:
        """Fetch checkpoint for a specific stage."""
        return (
            self.db.query(PipelineCheckpoint)
            .filter_by(job_id=job_id, stage_name=stage)
            .first()
        )

    def get_all_checkpoints(self, job_id: int) -> List[PipelineCheckpoint]:
        """Return all checkpoints for a job ordered by stage_index."""
        return (
            self.db.query(PipelineCheckpoint)
            .filter_by(job_id=job_id)
            .order_by(PipelineCheckpoint.stage_index)
            .all()
        )

    def get_resume_point(self, job_id: int) -> Optional[str]:
        """Determine which stage to resume from after a failure.

        Returns the name of the first incomplete stage, or None if all
        stages are complete (pipeline finished).

        Resume logic: skip 'complete' stages, return the first stage
        that is 'pending', 'running', or 'failed'.
        """
        checkpoints = {
            cp.stage_name: cp
            for cp in self.get_all_checkpoints(job_id)
        }

        for stage in PIPELINE_STAGE_ORDER:
            cp = checkpoints.get(stage)
            if cp is None or not cp.is_complete():
                return stage

        return None  # All stages complete

    def get_stage_output(self, job_id: int, stage: str,
                          key: str) -> Any:
        """Convenience method to retrieve a specific output from a checkpoint."""
        cp = self.get_checkpoint(job_id, stage)
        if cp is None or not cp.is_complete():
            return None
        return cp.get_output(key)

    def clear_checkpoints(self, job_id: int) -> int:
        """Delete all checkpoints for a job (for full restart)."""
        deleted = (
            self.db.query(PipelineCheckpoint)
            .filter_by(job_id=job_id)
            .delete(synchronize_session=False)
        )
        self.db.flush()
        logger.info("Cleared %d checkpoints for job=%s", deleted, job_id)
        return deleted

    def validate_integrity(self, job_id: int) -> Tuple[bool, List[str]]:
        """Validate checkpoint data integrity before resumption.

        Returns (is_valid, list_of_issues).
        """
        issues: List[str] = []
        checkpoints = self.get_all_checkpoints(job_id)

        for cp in checkpoints:
            if cp.is_complete():
                if not cp.output_refs:
                    issues.append(
                        f"Stage '{cp.stage_name}' complete but has no output_refs"
                    )

        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_fingerprint(data: Optional[Dict[str, Any]]) -> Optional[str]:
        """Compute a SHA-256 fingerprint of input parameters."""
        if data is None:
            return None
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:32]
