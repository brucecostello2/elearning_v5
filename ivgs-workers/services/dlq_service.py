"""
IVGS v5 — Dead Letter Queue Service
========================================

DLQ entry creation, error classification, storage, and replay dispatch
per §6.2. Failed tasks are routed here after retry exhaustion.

Database table: dead_letter_messages (Table 15)
Columns: id, original_queue, task_name, task_args, task_kwargs,
         exception_type, exception_message, traceback,
         failure_category (transient/config/external/resource),
         retry_count_exhausted, created_at, reviewed_at, reviewed_by,
         resolution (replayed/discarded/escalated)

Index: (failure_category, created_at DESC)

Integration points:
- Called by RetryEngine when max retries exhausted
- Called by FallbackChain when L4 exhausted
- Called by QualityGate when regeneration limit exceeded (§11.3)
- Replayed via POST /api/v1/dlq/messages/{id}/replay
- Periodic processing via Celery Beat every 5 minutes (§6.4)
"""

from __future__ import annotations

import traceback as tb_module
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FailureCategory(str, Enum):
    """Error classification categories per §6.2."""

    TRANSIENT = "transient"
    CONFIG = "config"
    EXTERNAL = "external"
    RESOURCE = "resource"


class DLQResolution(str, Enum):
    """DLQ message resolution outcomes per Table 15."""

    REPLAYED = "replayed"
    DISCARDED = "discarded"
    ESCALATED = "escalated"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class DLQEntry(BaseModel):
    """Schema for creating a DLQ entry per Table 15."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_queue: str = Field(
        ...,
        description="Source Celery queue name (e.g., gpu_image, gpu_video)",
    )
    task_name: str = Field(
        ...,
        description="Fully-qualified Celery task name",
    )
    task_args: list[Any] = Field(
        default_factory=list,
        description="Task positional arguments",
    )
    task_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Task keyword arguments",
    )
    exception_type: str = Field(
        ...,
        description="Exception class name (e.g., TimeoutError)",
    )
    exception_message: str = Field(
        ...,
        description="Human-readable error message",
    )
    traceback: str = Field(
        default="",
        description="Full Python stack trace",
    )
    failure_category: FailureCategory = Field(
        ...,
        description="Error classification: transient/config/external/resource",
    )
    retry_count_exhausted: int = Field(
        default=0,
        description="Total retries attempted before DLQ entry",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class DLQReplayRequest(BaseModel):
    """Request schema for replaying a DLQ message."""

    message_id: str = Field(..., description="DLQ message UUID")
    override_queue: Optional[str] = Field(
        default=None,
        description="Optional: route replay to a different queue",
    )
    override_kwargs: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional: override task kwargs for replay",
    )


class DLQReplayResult(BaseModel):
    """Result of a DLQ replay operation."""

    status: str = Field(default="replayed")
    message_id: str
    new_task_id: str
    replayed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class DLQStats(BaseModel):
    """Aggregated DLQ statistics for monitoring."""

    total_messages: int = 0
    pending_review: int = 0
    replayed: int = 0
    discarded: int = 0
    escalated: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_task: dict[str, int] = Field(default_factory=dict)
    oldest_unreviewed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# DLQ Service
# ---------------------------------------------------------------------------

class DLQService:
    """
    Dead Letter Queue service per §6.2.

    Responsibilities:
    - Create DLQ entries from failed tasks after retry exhaustion
    - Store entries in dead_letter_messages table (Table 15)
    - Support operator review workflows (replay/discard/escalate)
    - Replay messages back to Celery queues
    - Provide aggregated statistics for monitoring dashboards
    - Periodic batch processing via Celery Beat (every 5 minutes)

    Integration:
    - RetryEngine calls send_to_dlq() when max_retries exceeded
    - FallbackChain calls send_to_dlq() when L4 fallback exhausted
    - QualityGate calls send_to_dlq() when regeneration fails (§11.3)
    - API routes expose list/replay/discard/escalate endpoints
    """

    def __init__(
        self,
        db_session_factory: Any,
        celery_app: Any,
    ) -> None:
        """
        Initialize DLQ service.

        Args:
            db_session_factory: Async SQLAlchemy session factory for
                dead_letter_messages table access.
            celery_app: Celery application instance for replay dispatch.
        """
        self._db_session_factory = db_session_factory
        self._celery_app = celery_app
        self._log = logger.bind(service="dlq_service")

    # ------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------

    async def send_to_dlq(
        self,
        *,
        original_queue: str,
        task_name: str,
        task_args: list[Any] | None = None,
        task_kwargs: dict[str, Any] | None = None,
        exception: BaseException | None = None,
        exception_type: str = "",
        exception_message: str = "",
        traceback_str: str = "",
        failure_category: FailureCategory,
        retry_count_exhausted: int = 0,
    ) -> DLQEntry:
        """
        Create a DLQ entry for a failed task per §6.2.

        Called when:
        - RetryEngine exhausts all retry attempts (Table 6-4)
        - FallbackChain exhausts all fallback levels (Table 6-6)
        - QualityGate regeneration fails twice (§11.3 step 6)

        Args:
            original_queue: Source Celery queue name.
            task_name: Fully-qualified Celery task name.
            task_args: Positional arguments of the failed task.
            task_kwargs: Keyword arguments of the failed task.
            exception: The exception object (if available).
            exception_type: Exception class name string override.
            exception_message: Error message string override.
            traceback_str: Pre-formatted traceback string override.
            failure_category: Classification per §6.2 enum.
            retry_count_exhausted: Number of retries attempted.

        Returns:
            DLQEntry: The created DLQ entry with generated UUID.
        """
        if exception is not None:
            exc_type = type(exception).__name__
            exc_message = str(exception)
            exc_traceback = "".join(
                tb_module.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            )
        else:
            exc_type = exception_type
            exc_message = exception_message
            exc_traceback = traceback_str

        entry = DLQEntry(
            original_queue=original_queue,
            task_name=task_name,
            task_args=task_args or [],
            task_kwargs=task_kwargs or {},
            exception_type=exc_type,
            exception_message=exc_message,
            traceback=exc_traceback,
            failure_category=failure_category,
            retry_count_exhausted=retry_count_exhausted,
        )

        async with self._db_session_factory() as session:
            async with session.begin():
                await session.execute(
                    self._insert_dlq_message(entry)
                )

        self._log.info(
            "dlq_entry_created",
            message_id=entry.id,
            task_name=task_name,
            failure_category=failure_category.value,
            retry_count_exhausted=retry_count_exhausted,
            original_queue=original_queue,
        )

        return entry

    async def replay_message(
        self,
        request: DLQReplayRequest,
        reviewed_by: str = "system",
    ) -> DLQReplayResult:
        """
        Replay a DLQ message back to its original Celery queue.

        Re-dispatches the failed task with original arguments (or overrides)
        to the original queue (or override queue). Updates the DLQ record
        with resolution=replayed and reviewed_by/reviewed_at.

        Args:
            request: Replay request with message_id and optional overrides.
            reviewed_by: Username of the reviewing operator.

        Returns:
            DLQReplayResult: Result with new Celery task ID.

        Raises:
            ValueError: If message not found or already resolved.
        """
        async with self._db_session_factory() as session:
            async with session.begin():
                row = await session.execute(
                    select(self._dlq_table()).where(
                        self._dlq_table().c.id == request.message_id
                    )
                )
                message = row.fetchone()

                if message is None:
                    raise ValueError(
                        f"DLQ message not found: {request.message_id}"
                    )

                if message.resolution is not None:
                    raise ValueError(
                        f"DLQ message already resolved: "
                        f"{message.resolution} by {message.reviewed_by}"
                    )

                # Determine queue and kwargs for replay
                replay_queue = (
                    request.override_queue or message.original_queue
                )
                replay_kwargs = (
                    request.override_kwargs
                    if request.override_kwargs is not None
                    else dict(message.task_kwargs)
                )

                # Dispatch via Celery
                result = self._celery_app.send_task(
                    message.task_name,
                    args=list(message.task_args),
                    kwargs=replay_kwargs,
                    queue=replay_queue,
                )

                new_task_id = str(result.id)

                # Update DLQ record
                now = datetime.now(timezone.utc)
                await session.execute(
                    update(self._dlq_table())
                    .where(self._dlq_table().c.id == request.message_id)
                    .values(
                        resolution=DLQResolution.REPLAYED.value,
                        reviewed_at=now,
                        reviewed_by=reviewed_by,
                    )
                )

        replay_result = DLQReplayResult(
            message_id=request.message_id,
            new_task_id=new_task_id,
        )

        self._log.info(
            "dlq_message_replayed",
            message_id=request.message_id,
            new_task_id=new_task_id,
            replay_queue=replay_queue,
            reviewed_by=reviewed_by,
        )

        return replay_result

    async def discard_message(
        self,
        message_id: str,
        reviewed_by: str = "system",
        reason: str = "",
    ) -> None:
        """
        Discard a DLQ message — mark as intentionally ignored.

        Used when an operator determines the failure is non-recoverable
        or the task is no longer relevant.

        Args:
            message_id: DLQ message UUID.
            reviewed_by: Username of the reviewing operator.
            reason: Optional reason for discarding.

        Raises:
            ValueError: If message not found or already resolved.
        """
        async with self._db_session_factory() as session:
            async with session.begin():
                row = await session.execute(
                    select(self._dlq_table()).where(
                        self._dlq_table().c.id == message_id
                    )
                )
                message = row.fetchone()

                if message is None:
                    raise ValueError(f"DLQ message not found: {message_id}")

                if message.resolution is not None:
                    raise ValueError(
                        f"DLQ message already resolved: {message.resolution}"
                    )

                now = datetime.now(timezone.utc)
                await session.execute(
                    update(self._dlq_table())
                    .where(self._dlq_table().c.id == message_id)
                    .values(
                        resolution=DLQResolution.DISCARDED.value,
                        reviewed_at=now,
                        reviewed_by=reviewed_by,
                    )
                )

        self._log.info(
            "dlq_message_discarded",
            message_id=message_id,
            reviewed_by=reviewed_by,
            reason=reason,
        )

    async def escalate_message(
        self,
        message_id: str,
        reviewed_by: str = "system",
        escalation_notes: str = "",
    ) -> None:
        """
        Escalate a DLQ message for higher-level review.

        Used for failures that require infrastructure changes, model
        redeployment, or configuration updates before replay is viable.

        Args:
            message_id: DLQ message UUID.
            reviewed_by: Username of the reviewing operator.
            escalation_notes: Description of escalation reason.

        Raises:
            ValueError: If message not found or already resolved.
        """
        async with self._db_session_factory() as session:
            async with session.begin():
                row = await session.execute(
                    select(self._dlq_table()).where(
                        self._dlq_table().c.id == message_id
                    )
                )
                message = row.fetchone()

                if message is None:
                    raise ValueError(f"DLQ message not found: {message_id}")

                if message.resolution is not None:
                    raise ValueError(
                        f"DLQ message already resolved: {message.resolution}"
                    )

                now = datetime.now(timezone.utc)
                await session.execute(
                    update(self._dlq_table())
                    .where(self._dlq_table().c.id == message_id)
                    .values(
                        resolution=DLQResolution.ESCALATED.value,
                        reviewed_at=now,
                        reviewed_by=reviewed_by,
                    )
                )

        self._log.warning(
            "dlq_message_escalated",
            message_id=message_id,
            reviewed_by=reviewed_by,
            escalation_notes=escalation_notes,
        )

    # ------------------------------------------------------------------
    # Query & Statistics
    # ------------------------------------------------------------------

    async def list_messages(
        self,
        *,
        failure_category: FailureCategory | None = None,
        resolution: DLQResolution | None = None,
        unreviewed_only: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List DLQ messages with filtering and pagination.

        Args:
            failure_category: Filter by failure category.
            resolution: Filter by resolution status.
            unreviewed_only: If True, only return unreviewed messages.
            page: Page number (1-based).
            per_page: Items per page (max 100).

        Returns:
            Tuple of (messages list, total count).
        """
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page

        async with self._db_session_factory() as session:
            table = self._dlq_table()
            query = select(table)
            count_query = select(func.count()).select_from(table)

            # Apply filters
            if failure_category is not None:
                query = query.where(
                    table.c.failure_category == failure_category.value
                )
                count_query = count_query.where(
                    table.c.failure_category == failure_category.value
                )

            if resolution is not None:
                query = query.where(
                    table.c.resolution == resolution.value
                )
                count_query = count_query.where(
                    table.c.resolution == resolution.value
                )

            if unreviewed_only:
                query = query.where(table.c.resolution.is_(None))
                count_query = count_query.where(
                    table.c.resolution.is_(None)
                )

            # Order and paginate
            query = (
                query.order_by(table.c.created_at.desc())
                .offset(offset)
                .limit(per_page)
            )

            result = await session.execute(query)
            rows = result.fetchall()

            count_result = await session.execute(count_query)
            total = count_result.scalar() or 0

        messages = [dict(row._mapping) for row in rows]
        return messages, total

    async def get_statistics(self) -> DLQStats:
        """
        Get aggregated DLQ statistics for monitoring dashboards.

        Returns:
            DLQStats: Aggregate counts by category, task, and resolution.
        """
        async with self._db_session_factory() as session:
            table = self._dlq_table()

            # Total count
            total_result = await session.execute(
                select(func.count()).select_from(table)
            )
            total = total_result.scalar() or 0

            # Pending review (no resolution)
            pending_result = await session.execute(
                select(func.count())
                .select_from(table)
                .where(table.c.resolution.is_(None))
            )
            pending = pending_result.scalar() or 0

            # Resolution counts
            resolution_counts: dict[str, int] = {}
            for res in DLQResolution:
                res_result = await session.execute(
                    select(func.count())
                    .select_from(table)
                    .where(table.c.resolution == res.value)
                )
                resolution_counts[res.value] = res_result.scalar() or 0

            # By category
            category_result = await session.execute(
                select(
                    table.c.failure_category,
                    func.count().label("count"),
                )
                .group_by(table.c.failure_category)
            )
            by_category = {
                row.failure_category: row.count
                for row in category_result.fetchall()
            }

            # By task name
            task_result = await session.execute(
                select(
                    table.c.task_name,
                    func.count().label("count"),
                )
                .group_by(table.c.task_name)
                .order_by(func.count().desc())
                .limit(20)
            )
            by_task = {
                row.task_name: row.count
                for row in task_result.fetchall()
            }

            # Oldest unreviewed
            oldest_result = await session.execute(
                select(func.min(table.c.created_at))
                .select_from(table)
                .where(table.c.resolution.is_(None))
            )
            oldest_unreviewed = oldest_result.scalar()

        return DLQStats(
            total_messages=total,
            pending_review=pending,
            replayed=resolution_counts.get("replayed", 0),
            discarded=resolution_counts.get("discarded", 0),
            escalated=resolution_counts.get("escalated", 0),
            by_category=by_category,
            by_task=by_task,
            oldest_unreviewed_at=oldest_unreviewed,
        )

    # ------------------------------------------------------------------
    # Periodic Processing
    # ------------------------------------------------------------------

    async def process_pending_messages(
        self,
        *,
        auto_replay_transient: bool = True,
        max_auto_replays: int = 10,
    ) -> dict[str, int]:
        """
        Periodic DLQ processing — runs every 5 minutes via Celery Beat.

        Auto-replay policy:
        - Transient failures younger than 1 hour: auto-replay (up to limit)
        - Config/external/resource failures: leave for operator review
        - Messages older than 24 hours unreviewed: log warning

        Args:
            auto_replay_transient: Whether to auto-replay transient failures.
            max_auto_replays: Maximum auto-replays per processing cycle.

        Returns:
            Dict with counts: auto_replayed, flagged_stale, total_pending.
        """
        auto_replayed = 0
        flagged_stale = 0

        async with self._db_session_factory() as session:
            table = self._dlq_table()

            # Get all unreviewed messages
            result = await session.execute(
                select(table)
                .where(table.c.resolution.is_(None))
                .order_by(table.c.created_at.asc())
            )
            pending_messages = result.fetchall()
            total_pending = len(pending_messages)

        now = datetime.now(timezone.utc)

        for msg in pending_messages:
            age_seconds = (now - msg.created_at).total_seconds()

            # Auto-replay transient failures < 1 hour old
            if (
                auto_replay_transient
                and msg.failure_category == FailureCategory.TRANSIENT.value
                and age_seconds < 3600
                and auto_replayed < max_auto_replays
            ):
                try:
                    request = DLQReplayRequest(message_id=str(msg.id))
                    await self.replay_message(
                        request, reviewed_by="auto_processor"
                    )
                    auto_replayed += 1
                except Exception as exc:
                    self._log.error(
                        "dlq_auto_replay_failed",
                        message_id=str(msg.id),
                        error=str(exc),
                    )

            # Flag stale messages (> 24 hours unreviewed)
            if age_seconds > 86400:
                flagged_stale += 1
                self._log.warning(
                    "dlq_stale_message",
                    message_id=str(msg.id),
                    task_name=msg.task_name,
                    failure_category=msg.failure_category,
                    age_hours=round(age_seconds / 3600, 1),
                )

        self._log.info(
            "dlq_periodic_processing_complete",
            total_pending=total_pending,
            auto_replayed=auto_replayed,
            flagged_stale=flagged_stale,
        )

        return {
            "auto_replayed": auto_replayed,
            "flagged_stale": flagged_stale,
            "total_pending": total_pending,
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dlq_table() -> Any:
        """
        Return SQLAlchemy Table reference for dead_letter_messages.

        Uses the declarative model from Phase 2 database models.
        Table schema per Table 15 of the functional specification.
        """
        # ⛔ WP-54: THIS IMPORT CANNOT BE REPAIRED BY RENAMING, and is left standing
        # deliberately so the gap it names stays visible. Ledger P2.60.
        #
        # ASSUMED: an `ivgs_api` package exposing `app.models.DeadLetterMessage`.
        # PROVIDED: the worker image ships `shared.models.{enums, model_store}` and
        # nothing else -- checked inside the running container, where `app.models`
        # fails too. `DeadLetterMessage` is defined only in `ivgs-api/app/models/dead_letter_queue.py`.
        # There is no module path that resolves, so a rename would move the failure,
        # not remove it.
        from ivgs_api.app.models import DeadLetterMessage

        return DeadLetterMessage.__table__

    def _insert_dlq_message(self, entry: DLQEntry) -> Any:
        """
        Build SQLAlchemy INSERT statement for a DLQ entry.

        Args:
            entry: Validated DLQ entry Pydantic model.

        Returns:
            SQLAlchemy insert statement.
        """
        from sqlalchemy import insert

        table = self._dlq_table()
        return insert(table).values(
            id=entry.id,
            original_queue=entry.original_queue,
            task_name=entry.task_name,
            task_args=entry.task_args,
            task_kwargs=entry.task_kwargs,
            exception_type=entry.exception_type,
            exception_message=entry.exception_message,
            traceback=entry.traceback,
            failure_category=entry.failure_category.value,
            retry_count_exhausted=entry.retry_count_exhausted,
            created_at=entry.created_at,
        )
