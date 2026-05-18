"""RetryPolicy — classifies failures and determines retry eligibility.

Per-task-type retry limits and exponential backoff. Cost-aware ceiling
halts retries if cumulative spend exceeds threshold.

Usage:
    policy = RetryPolicy(db_session)
    should_retry, backoff_seconds = policy.evaluate(
        job_id=42, stage="image_gen",
        failure_type="transient",
    )
"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.retry import TaskRetry, BACKOFF_SEQUENCE

logger = logging.getLogger(__name__)

# Maximum cumulative API cost before halting retries
COST_CEILING_USD = 10.0


@dataclass
class StageRetryConfig:
    """Retry settings for a specific pipeline stage."""

    max_retries: int
    backoff_sequence: list
    # Failure types that are permanently non-retryable
    no_retry_on: tuple = ("config",)


# Per-stage retry configuration
STAGE_RETRY_CONFIGS: Dict[str, StageRetryConfig] = {
    "transcript":      StageRetryConfig(max_retries=4, backoff_sequence=BACKOFF_SEQUENCE),
    "storyboard":      StageRetryConfig(max_retries=4, backoff_sequence=BACKOFF_SEQUENCE),
    "image_gen":       StageRetryConfig(max_retries=3, backoff_sequence=BACKOFF_SEQUENCE),
    "tts":             StageRetryConfig(max_retries=3, backoff_sequence=BACKOFF_SEQUENCE),
    "talking_head":    StageRetryConfig(max_retries=2, backoff_sequence=[5, 30]),
    "motion_graphics": StageRetryConfig(max_retries=4, backoff_sequence=BACKOFF_SEQUENCE),
    "composition":     StageRetryConfig(max_retries=2, backoff_sequence=[15, 60]),
    "default":         StageRetryConfig(max_retries=4, backoff_sequence=BACKOFF_SEQUENCE),
}


class RetryPolicy:
    """Evaluates whether a failed task should be retried.

    Combines attempt count, failure type classification, and cost
    ceiling to produce a binary retry/no-retry decision with backoff.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate(
        self,
        job_id: int,
        stage: str,
        failure_type: str = "transient",
        estimated_cost_usd: float = 0.0,
        error_message: Optional[str] = None,
    ) -> Tuple[bool, int]:
        """Determine if a failed stage should be retried.

        Records the attempt in task_retries and checks all retry
        eligibility conditions.

        Args:
            job_id:             The job that experienced the failure.
            stage:              Stage name (e.g., "image_gen").
            failure_type:       One of: transient, config, external, resource.
            estimated_cost_usd: Cost of this attempt (for cost ceiling).
            error_message:      Error text to store in audit record.

        Returns:
            Tuple of (should_retry: bool, backoff_seconds: int).
            backoff_seconds is 0 if should_retry is False.
        """
        cfg = STAGE_RETRY_CONFIGS.get(stage, STAGE_RETRY_CONFIGS["default"])

        # Count existing attempts for this job+stage
        existing = (
            self.db.query(TaskRetry)
            .filter_by(job_id=job_id, stage_name=stage)
            .count()
        )
        next_attempt = existing + 1

        # Calculate backoff for this attempt
        idx = min(existing, len(cfg.backoff_sequence) - 1)
        backoff = cfg.backoff_sequence[idx]

        # Record this retry attempt
        retry_record = TaskRetry(
            job_id=job_id,
            stage_name=stage,
            attempt_number=next_attempt,
            failure_type=failure_type,
            error_message=error_message,
            retry_after_seconds=backoff,
            estimated_cost_usd=estimated_cost_usd if estimated_cost_usd else None,
        )
        self.db.add(retry_record)

        # Update cumulative cost on jobs table
        if estimated_cost_usd > 0:
            self.db.execute(
                sa_text(
                    "UPDATE jobs SET cumulative_cost_usd = "
                    "cumulative_cost_usd + :cost WHERE id = :id"
                ),
                {"cost": estimated_cost_usd, "id": job_id},
            )

        self.db.flush()

        # --- Eligibility checks ---

        # 1. Non-retryable failure type
        if failure_type in cfg.no_retry_on:
            logger.info("No retry: job=%s stage=%s type=%s (non-retryable)",
                        job_id, stage, failure_type)
            return False, 0

        # 2. Retry count exhausted
        if next_attempt > cfg.max_retries:
            logger.info("No retry: job=%s stage=%s attempts=%d (limit=%d)",
                        job_id, stage, next_attempt, cfg.max_retries)
            return False, 0

        # 3. Cost ceiling exceeded
        cumulative = self._get_cumulative_cost(job_id)
        if cumulative > COST_CEILING_USD:
            logger.warning("No retry: job=%s cost ceiling exceeded (%.2f > %.2f)",
                           job_id, cumulative, COST_CEILING_USD)
            return False, 0

        logger.info("Retry approved: job=%s stage=%s attempt=%d backoff=%ds",
                    job_id, stage, next_attempt, backoff)
        return True, backoff

    @staticmethod
    def classify_failure(exception: Exception) -> str:
        """Classify an exception into one of the four failure categories.

        Returns:
            'transient'  — network errors, rate limits, temporary outages
            'config'     — invalid parameters, missing credentials
            'external'   — external service permanently unavailable
            'resource'   — GPU OOM, disk full, memory exhausted
        """
        exc_name = type(exception).__name__
        exc_str = str(exception).lower()

        if any(k in exc_str for k in ["rate limit", "429", "too many requests",
                                       "timeout", "connection", "network",
                                       "temporary", "retry"]):
            return "transient"

        if any(k in exc_str for k in ["invalid", "authentication", "api key",
                                       "unauthorized", "not found", "400", "401",
                                       "403", "404"]):
            return "config"

        if any(k in exc_str for k in ["out of memory", "cuda out", "oom",
                                       "no space", "disk full", "memory"]):
            return "resource"

        if any(k in exc_str for k in ["service unavailable", "503", "502",
                                       "gateway", "downstream"]):
            return "external"

        return "transient"  # Default to retryable

    def _get_cumulative_cost(self, job_id: int) -> float:
        """Fetch cumulative API cost for this job from the database."""
        row = self.db.execute(
            sa_text("SELECT cumulative_cost_usd FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).first()
        return float(row[0]) if row and row[0] else 0.0


from sqlalchemy import text as sa_text  # noqa: E402
