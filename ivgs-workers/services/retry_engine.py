"""
IVGS v5 — Retry Policy Engine
========================================

Retry policy loading, exponential backoff calculation, and attempt tracking
per §6.2 Table 6-4.

Retry policies per stage type:
- LLM (transcript, storyboard): 4 retries, 5s → 15s → 45s → 135s
- Image generation:              3 retries, 10s → 30s → 90s
- Video generation:              2 retries, 30s → 90s
- TTS audio:                     3 retries, 10s → 30s → 90s
- Talking head:                  2 retries, 30s → 90s
- Composition / FFmpeg:          2 retries, 30s → 90s

On exhaustion actions per Table 6-4:
- LLM:          → DLQ
- Image:        → Fallback chain + DLQ
- Video:        → Fallback chain + DLQ
- TTS audio:    → Kokoro fallback + DLQ
- Talking head: → SadTalker fallback + DLQ
- Composition:  → DLQ

Retry attempts stored in task_retries table (Table 13):
  id, job_id, stage_name, attempt_number, failure_type,
  error_message, error_traceback, retry_after_seconds, created_at
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Stage Types
# ---------------------------------------------------------------------------

class StageType(str, Enum):
    """Pipeline stage types for retry policy lookup per §6.2 Table 6-4."""

    LLM = "llm"
    IMAGE = "image"
    VIDEO = "video"
    TTS = "tts"
    TALKING_HEAD = "talking_head"
    COMPOSITION = "composition"


class ExhaustionAction(str, Enum):
    """Action to take when retries are exhausted per Table 6-4."""

    DLQ = "dlq"
    FALLBACK_AND_DLQ = "fallback_and_dlq"
    KOKORO_FALLBACK_AND_DLQ = "kokoro_fallback_and_dlq"
    SADTALKER_FALLBACK_AND_DLQ = "sadtalker_fallback_and_dlq"


# ---------------------------------------------------------------------------
# Retry Policy Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """
    Immutable retry policy for a pipeline stage type per §6.2 Table 6-4.

    Attributes:
        stage_type: Pipeline stage category.
        max_retries: Maximum retry attempts before exhaustion.
        backoff_sequence: Ordered delay sequence in seconds.
        on_exhaustion: Action to take after max retries exceeded.
    """

    stage_type: StageType
    max_retries: int
    backoff_sequence: tuple[float, ...]
    on_exhaustion: ExhaustionAction


# Table 6-4: Retry Policy per Stage Type — hardcoded per specification
RETRY_POLICIES: dict[StageType, RetryPolicy] = {
    StageType.LLM: RetryPolicy(
        stage_type=StageType.LLM,
        max_retries=4,
        backoff_sequence=(5.0, 15.0, 45.0, 135.0),
        on_exhaustion=ExhaustionAction.DLQ,
    ),
    StageType.IMAGE: RetryPolicy(
        stage_type=StageType.IMAGE,
        max_retries=3,
        backoff_sequence=(10.0, 30.0, 90.0),
        on_exhaustion=ExhaustionAction.FALLBACK_AND_DLQ,
    ),
    StageType.VIDEO: RetryPolicy(
        stage_type=StageType.VIDEO,
        max_retries=2,
        backoff_sequence=(30.0, 90.0),
        on_exhaustion=ExhaustionAction.FALLBACK_AND_DLQ,
    ),
    StageType.TTS: RetryPolicy(
        stage_type=StageType.TTS,
        max_retries=3,
        backoff_sequence=(10.0, 30.0, 90.0),
        on_exhaustion=ExhaustionAction.KOKORO_FALLBACK_AND_DLQ,
    ),
    StageType.TALKING_HEAD: RetryPolicy(
        stage_type=StageType.TALKING_HEAD,
        max_retries=2,
        backoff_sequence=(30.0, 90.0),
        on_exhaustion=ExhaustionAction.SADTALKER_FALLBACK_AND_DLQ,
    ),
    StageType.COMPOSITION: RetryPolicy(
        stage_type=StageType.COMPOSITION,
        max_retries=2,
        backoff_sequence=(30.0, 90.0),
        on_exhaustion=ExhaustionAction.DLQ,
    ),
}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class RetryAttemptRecord(BaseModel):
    """Schema for a retry attempt record per Table 13 (task_retries)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = Field(..., description="Parent render job UUID")
    stage_name: str = Field(..., description="Pipeline stage name")
    attempt_number: int = Field(..., description="Current attempt count")
    failure_type: str = Field(
        ...,
        description="transient/config/external/resource",
    )
    error_message: str = Field(default="", description="Error description")
    error_traceback: str = Field(default="", description="Full stack trace")
    retry_after_seconds: float = Field(
        ...,
        description="Backoff delay before next attempt",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class RetryDecision(BaseModel):
    """Result of a retry evaluation — should retry, wait, or exhaust."""

    should_retry: bool = Field(
        ...,
        description="True if another retry attempt should be made",
    )
    attempt_number: int = Field(
        ...,
        description="Current attempt number (1-based)",
    )
    max_retries: int = Field(
        ...,
        description="Maximum retries for this stage type",
    )
    backoff_seconds: float = Field(
        default=0.0,
        description="Seconds to wait before next retry",
    )
    exhaustion_action: Optional[ExhaustionAction] = Field(
        default=None,
        description="Action if retries exhausted (None if should_retry)",
    )
    stage_type: StageType


# ---------------------------------------------------------------------------
# Retry Engine
# ---------------------------------------------------------------------------

class RetryEngine:
    """
    Retry policy engine per §6.2 Table 6-4.

    Responsibilities:
    - Look up retry policy by stage type
    - Calculate exponential backoff delay for current attempt
    - Record retry attempts in task_retries table (Table 13)
    - Determine exhaustion action (DLQ, fallback chain, or specific fallback)
    - Integrate with Celery retry mechanism (countdown parameter)

    Usage in base_task.py:
        decision = retry_engine.evaluate(stage_type, current_attempt, failure_type)
        if decision.should_retry:
            self.retry(countdown=decision.backoff_seconds)
        else:
            # Handle exhaustion_action
    """

    def __init__(
        self,
        db_session_factory: Any,
        policies: dict[StageType, RetryPolicy] | None = None,
    ) -> None:
        """
        Initialize retry engine.

        Args:
            db_session_factory: Async SQLAlchemy session factory for
                task_retries table access.
            policies: Optional override policies (defaults to Table 6-4).
        """
        self._db_session_factory = db_session_factory
        self._policies = policies or RETRY_POLICIES
        self._log = logger.bind(service="retry_engine")

    def get_policy(self, stage_type: StageType) -> RetryPolicy:
        """
        Get the retry policy for a stage type.

        Args:
            stage_type: Pipeline stage type per §6.2 Table 6-4.

        Returns:
            RetryPolicy: The configured policy for this stage type.

        Raises:
            KeyError: If no policy configured for the stage type.
        """
        if stage_type not in self._policies:
            raise KeyError(
                f"No retry policy configured for stage type: {stage_type.value}"
            )
        return self._policies[stage_type]

    def calculate_backoff(
        self,
        stage_type: StageType,
        attempt_number: int,
    ) -> float:
        """
        Calculate backoff delay for a specific retry attempt.

        Uses the pre-defined backoff sequence from Table 6-4. If the
        attempt_number exceeds the sequence length, returns the last
        value in the sequence.

        Args:
            stage_type: Pipeline stage type.
            attempt_number: Current attempt number (1-based).

        Returns:
            Backoff delay in seconds.
        """
        policy = self.get_policy(stage_type)
        sequence = policy.backoff_sequence

        # attempt_number is 1-based; sequence is 0-indexed
        index = min(attempt_number - 1, len(sequence) - 1)
        return sequence[index]

    def evaluate(
        self,
        stage_type: StageType,
        current_attempt: int,
        failure_type: str = "transient",
    ) -> RetryDecision:
        """
        Evaluate whether a retry should be attempted.

        Core decision logic:
        1. Non-retryable failures (config) → immediate exhaustion
        2. current_attempt < max_retries → retry with backoff
        3. current_attempt >= max_retries → exhaustion action

        Args:
            stage_type: Pipeline stage type per Table 6-4.
            current_attempt: Current attempt number (1-based).
            failure_type: Error classification from ErrorClassifier.

        Returns:
            RetryDecision: Whether to retry, the backoff, or exhaustion action.
        """
        policy = self.get_policy(stage_type)

        # Config errors are never retryable — immediate DLQ
        if failure_type == "config":
            self._log.info(
                "retry_skipped_config_error",
                stage_type=stage_type.value,
                attempt=current_attempt,
            )
            return RetryDecision(
                should_retry=False,
                attempt_number=current_attempt,
                max_retries=policy.max_retries,
                backoff_seconds=0.0,
                exhaustion_action=policy.on_exhaustion,
                stage_type=stage_type,
            )

        if current_attempt < policy.max_retries:
            backoff = self.calculate_backoff(
                stage_type, current_attempt + 1
            )
            self._log.info(
                "retry_scheduled",
                stage_type=stage_type.value,
                attempt=current_attempt,
                max_retries=policy.max_retries,
                backoff_seconds=backoff,
                failure_type=failure_type,
            )
            return RetryDecision(
                should_retry=True,
                attempt_number=current_attempt,
                max_retries=policy.max_retries,
                backoff_seconds=backoff,
                exhaustion_action=None,
                stage_type=stage_type,
            )

        # Retries exhausted
        self._log.warning(
            "retries_exhausted",
            stage_type=stage_type.value,
            attempt=current_attempt,
            max_retries=policy.max_retries,
            exhaustion_action=policy.on_exhaustion.value,
            failure_type=failure_type,
        )
        return RetryDecision(
            should_retry=False,
            attempt_number=current_attempt,
            max_retries=policy.max_retries,
            backoff_seconds=0.0,
            exhaustion_action=policy.on_exhaustion,
            stage_type=stage_type,
        )

    async def record_attempt(
        self,
        *,
        job_id: str,
        stage_name: str,
        attempt_number: int,
        failure_type: str,
        error_message: str = "",
        error_traceback: str = "",
        retry_after_seconds: float = 0.0,
    ) -> RetryAttemptRecord:
        """
        Record a retry attempt in the task_retries table (Table 13).

        Creates an audit trail of all retry attempts for post-mortem
        analysis and monitoring dashboards.

        Args:
            job_id: Parent render job UUID.
            stage_name: Pipeline stage name string.
            attempt_number: Current attempt number (1-based).
            failure_type: Error classification.
            error_message: Human-readable error description.
            error_traceback: Full Python stack trace.
            retry_after_seconds: Backoff delay applied.

        Returns:
            RetryAttemptRecord: The created retry record.
        """
        record = RetryAttemptRecord(
            job_id=job_id,
            stage_name=stage_name,
            attempt_number=attempt_number,
            failure_type=failure_type,
            error_message=error_message,
            error_traceback=error_traceback,
            retry_after_seconds=retry_after_seconds,
        )

        async with self._db_session_factory() as session:
            async with session.begin():
                from sqlalchemy import insert
                # ⛔ WP-54: THIS IMPORT CANNOT BE REPAIRED BY RENAMING, and is left standing
                # deliberately so the gap it names stays visible. Ledger P2.60.
                #
                # ASSUMED: an `ivgs_api` package exposing `app.models.TaskRetry`.
                # PROVIDED: the worker image ships `shared.models.{enums, model_store}` and
                # nothing else -- checked inside the running container, where `app.models`
                # fails too. `TaskRetry` is defined only in `ivgs-api/app/models/task_retry.py`, which is not copied into this image.
                # There is no module path that resolves, so a rename would move the failure,
                # not remove it.
                from ivgs_api.app.models import TaskRetry

                await session.execute(
                    insert(TaskRetry.__table__).values(
                        id=record.id,
                        job_id=record.job_id,
                        stage_name=record.stage_name,
                        attempt_number=record.attempt_number,
                        failure_type=record.failure_type,
                        error_message=record.error_message,
                        error_traceback=record.error_traceback,
                        retry_after_seconds=record.retry_after_seconds,
                        created_at=record.created_at,
                    )
                )

        self._log.info(
            "retry_attempt_recorded",
            record_id=record.id,
            job_id=job_id,
            stage_name=stage_name,
            attempt_number=attempt_number,
            failure_type=failure_type,
            retry_after_seconds=retry_after_seconds,
        )

        return record

    async def get_attempt_history(
        self,
        job_id: str,
        stage_name: str | None = None,
    ) -> list[RetryAttemptRecord]:
        """
        Retrieve retry attempt history for a job.

        Args:
            job_id: Parent render job UUID.
            stage_name: Optional filter by stage name.

        Returns:
            List of retry attempt records ordered by attempt_number.
        """
        async with self._db_session_factory() as session:
            from sqlalchemy import select
            # ⛔ WP-54: THIS IMPORT CANNOT BE REPAIRED BY RENAMING, and is left standing
            # deliberately so the gap it names stays visible. Ledger P2.60.
            #
            # ASSUMED: an `ivgs_api` package exposing `app.models.TaskRetry`.
            # PROVIDED: the worker image ships `shared.models.{enums, model_store}` and
            # nothing else -- checked inside the running container, where `app.models`
            # fails too. `TaskRetry` is defined only in `ivgs-api/app/models/task_retry.py`, which is not copied into this image.
            # There is no module path that resolves, so a rename would move the failure,
            # not remove it.
            from ivgs_api.app.models import TaskRetry

            table = TaskRetry.__table__
            query = (
                select(table)
                .where(table.c.job_id == job_id)
                .order_by(table.c.attempt_number.asc())
            )

            if stage_name is not None:
                query = query.where(table.c.stage_name == stage_name)

            result = await session.execute(query)
            rows = result.fetchall()

        return [
            RetryAttemptRecord(
                id=str(row.id),
                job_id=str(row.job_id),
                stage_name=row.stage_name,
                attempt_number=row.attempt_number,
                failure_type=row.failure_type,
                error_message=row.error_message or "",
                error_traceback=row.error_traceback or "",
                retry_after_seconds=float(row.retry_after_seconds),
                created_at=row.created_at,
            )
            for row in rows
        ]
