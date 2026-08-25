"""
DLQ service: message listing, replay dispatch, discard, analytics aggregation.

Per §5.2.2 — provides operational access to the dead letter queue for
monitoring and intervention. Replay re-enqueues the original Celery task.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dead_letter_queue import DeadLetterMessage
from app.schemas.dlq import (
    DLQMessageResponse,
    DLQDetailResponse,
    DLQBulkReplayRequest,
    DLQBulkReplayResponse,
    DLQAnalyticsResponse,
    DLQCategoryCount,
    DLQTaskCount,
    DLQDailyCount,
)

logger = logging.getLogger(__name__)

# The queue a replay lands on when the DLQ row does not record one. "default" is
# the orchestrator's own queue and is consumed on node-01, so a replay with a
# lost queue name still reaches a worker rather than sitting in a queue nothing
# reads. Recorded in the response so the operator can see it was a fallback.
FALLBACK_REPLAY_QUEUE = "default"


class DLQReplayError(RuntimeError):
    """A DLQ message could not be re-enqueued.

    WP-45 Task 3, site 4. Replay used to mark the row ``resolution='replayed'``,
    commit, and return a 200 whose body said the message had been replayed -
    with the send_task sitting underneath as a five-line comment. The operator
    was told the failed task had been re-run; nothing had been. Worse, the row
    was now marked resolved, so it dropped out of the unresolved list and out of
    the operator's view: the DLQ's one job is to retain what failed, and its
    replay button quietly discarded messages instead.

    Raised so the resolution is never written for a replay that did not happen.
    """


def _replay_args(message: DeadLetterMessage) -> tuple[list, dict, str]:
    """The (args, kwargs, queue) to re-enqueue a DLQ message with.

    ``task_args`` and ``task_kwargs`` are JSONB and the ORM types them as dicts,
    but Celery needs args to be a sequence. A dict arrives here when the column
    was written from something that was not a list; it is coerced rather than
    passed through, because ``send_task(args={...})`` raises inside the producer
    and would look like a broker fault.
    """
    raw_args = message.task_args
    if raw_args is None:
        args: list = []
    elif isinstance(raw_args, list):
        args = raw_args
    elif isinstance(raw_args, dict):
        # A dict here almost always means positional args were recorded under
        # keys; there is no faithful ordering to recover, so refuse rather than
        # replay the task with arguments in an invented order.
        raise DLQReplayError(
            f"message {message.id} recorded task_args as an object, not a list; "
            "there is no reliable positional order to replay it with."
        )
    else:
        args = [raw_args]

    kwargs = message.task_kwargs if isinstance(message.task_kwargs, dict) else {}
    queue = message.original_queue or FALLBACK_REPLAY_QUEUE
    return args, kwargs, queue


def _send_replay(message: DeadLetterMessage) -> str:
    """Re-enqueue one DLQ message. Returns the new Celery task id."""
    if not message.task_name:
        raise DLQReplayError(
            f"message {message.id} has no task_name, so there is nothing to "
            "re-enqueue. Discard it instead."
        )
    args, kwargs, queue = _replay_args(message)

    from app.services.celery_producer import celery_app as pipeline_celery

    try:
        result = pipeline_celery.send_task(
            message.task_name, args=args, kwargs=kwargs, queue=queue,
        )
    except Exception as exc:
        raise DLQReplayError(
            f"could not re-enqueue {message.task_name} for message "
            f"{message.id}: {exc}"
        ) from exc
    return result.id


class DLQService:
    """Business logic for dead letter queue management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_messages(
        self,
        page: int = 1,
        per_page: int = 50,
        category: Optional[str] = None,
        task_name: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        resolution: Optional[str] = None,
    ) -> Tuple[List[DLQMessageResponse], int]:
        """
        Paginated list of DLQ messages with optional filters.

        Supports: ?category=transient|config|external|resource,
        ?task_name=, ?from_date=, ?to_date=, ?resolution=
        """
        query = select(DeadLetterMessage)

        if category:
            query = query.where(DeadLetterMessage.failure_category == category)
        if task_name:
            query = query.where(DeadLetterMessage.task_name.ilike(f"%{task_name}%"))
        if from_date:
            query = query.where(DeadLetterMessage.created_at >= from_date)
        if to_date:
            query = query.where(DeadLetterMessage.created_at <= to_date)
        if resolution:
            query = query.where(DeadLetterMessage.resolution == resolution)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(DeadLetterMessage.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        messages = result.scalars().all()

        responses = [DLQMessageResponse.model_validate(m) for m in messages]
        return responses, total

    async def get_message(self, message_id: UUID) -> Optional[DLQDetailResponse]:
        """Get full DLQ message detail with traceback and task arguments."""
        result = await self.db.execute(
            select(DeadLetterMessage).where(DeadLetterMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None
        return DLQDetailResponse.model_validate(message)

    async def replay_message(
        self,
        message_id: UUID,
        replayed_by: str,
    ) -> Optional[DLQDetailResponse]:
        """
        Replay a DLQ message: re-enqueue original task with same arguments.

        Marks the message as resolved with resolution='replayed'.
        Phase 5: will dispatch actual Celery task.
        """
        result = await self.db.execute(
            select(DeadLetterMessage).where(DeadLetterMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None

        if message.resolution is not None:
            raise ValueError(
                f"Message already resolved as '{message.resolution}'. "
                f"Cannot replay a resolved message."
            )

        # Dispatch FIRST, mark resolved second. The old order marked the row
        # replayed and then did nothing; this order cannot mark a row replayed
        # unless a broker message exists, and a failed dispatch leaves the
        # message unresolved and still visible in the DLQ - which is where a
        # message that has not been re-run belongs.
        celery_task_id = _send_replay(message)

        message.resolution = "replayed"
        message.reviewed_at = datetime.now(timezone.utc)
        message.reviewed_by = replayed_by

        await self.db.commit()
        await self.db.refresh(message)

        logger.info(
            "DLQ message replayed: id=%s task=%s queue=%s celery_task=%s by=%s",
            message_id, message.task_name,
            message.original_queue or FALLBACK_REPLAY_QUEUE,
            celery_task_id, replayed_by,
        )

        return DLQDetailResponse.model_validate(message)

    async def discard_message(
        self,
        message_id: UUID,
        reason: str,
        discarded_by: str,
    ) -> Optional[DLQDetailResponse]:
        """
        Discard a DLQ message with a reason.

        Marks the message as resolved with resolution='discarded'.
        """
        result = await self.db.execute(
            select(DeadLetterMessage).where(DeadLetterMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None

        if message.resolution is not None:
            raise ValueError(
                f"Message already resolved as '{message.resolution}'. "
                f"Cannot discard a resolved message."
            )

        message.resolution = "discarded"
        message.reviewed_at = datetime.now(timezone.utc)
        message.reviewed_by = discarded_by

        await self.db.commit()
        await self.db.refresh(message)

        logger.info(
            f"DLQ message discarded: id={message_id} task={message.task_name} "
            f"reason={reason!r} by={discarded_by}"
        )
        return DLQDetailResponse.model_validate(message)

    async def bulk_replay(
        self,
        filters: DLQBulkReplayRequest,
        replayed_by: str,
    ) -> DLQBulkReplayResponse:
        """
        Bulk replay DLQ messages matching filter criteria.

        Only replays unresolved messages (resolution IS NULL).
        """
        query = select(DeadLetterMessage).where(
            DeadLetterMessage.resolution.is_(None)
        )

        if filters.category:
            query = query.where(DeadLetterMessage.failure_category == filters.category)
        if filters.task_name:
            query = query.where(
                DeadLetterMessage.task_name.ilike(f"%{filters.task_name}%")
            )
        if filters.from_date:
            query = query.where(DeadLetterMessage.created_at >= filters.from_date)
        if filters.to_date:
            query = query.where(DeadLetterMessage.created_at <= filters.to_date)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        now = datetime.now(timezone.utc)
        replayed_ids = []
        failures: List[str] = []

        for message in messages:
            # Per message, not all-or-nothing. One malformed row in a hundred
            # must not block the other ninety-nine, and a row that could not be
            # replayed stays unresolved so it is still in the operator's list.
            try:
                celery_task_id = _send_replay(message)
            except DLQReplayError as exc:
                failures.append(f"{message.id}: {exc}")
                logger.warning("DLQ bulk replay skipped %s: %s", message.id, exc)
                continue

            message.resolution = "replayed"
            message.reviewed_at = now
            message.reviewed_by = replayed_by
            replayed_ids.append(message.id)
            logger.info(
                "DLQ bulk replay: id=%s task=%s celery_task=%s",
                message.id, message.task_name, celery_task_id,
            )

        await self.db.commit()

        logger.info(
            "DLQ bulk replay: %s replayed, %s skipped, by=%s filters=%s",
            len(replayed_ids), len(failures), replayed_by,
            filters.model_dump(exclude_unset=True),
        )

        # replayed_count counts messages that produced a broker message. It used
        # to count rows the loop had touched, which was every match, whether or
        # not anything was re-run - so the number the operator read was the size
        # of the filter, not the size of the action.
        return DLQBulkReplayResponse(
            replayed_count=len(replayed_ids),
            message_ids=replayed_ids,
            skipped_count=len(failures),
            skipped_reasons=failures[:20],
        )

    async def get_analytics(self) -> DLQAnalyticsResponse:
        """
        DLQ failure analytics: counts by category, task, and time period.

        Aggregates across all DLQ messages for dashboard display.
        """
        # Total counts
        total_result = await self.db.execute(
            select(func.count()).select_from(DeadLetterMessage)
        )
        total = total_result.scalar() or 0

        # Counts by resolution
        resolution_result = await self.db.execute(
            select(
                DeadLetterMessage.resolution,
                func.count().label("cnt"),
            )
            .group_by(DeadLetterMessage.resolution)
        )
        resolution_counts = {row[0]: row[1] for row in resolution_result.all()}

        unresolved = resolution_counts.get(None, 0)
        replayed = resolution_counts.get("replayed", 0)
        discarded = resolution_counts.get("discarded", 0)
        escalated = resolution_counts.get("escalated", 0)

        # Counts by category
        category_result = await self.db.execute(
            select(
                DeadLetterMessage.failure_category,
                func.count().label("cnt"),
            )
            .where(DeadLetterMessage.failure_category.isnot(None))
            .group_by(DeadLetterMessage.failure_category)
            .order_by(func.count().desc())
        )
        by_category = [
            DLQCategoryCount(category=row[0], count=row[1])
            for row in category_result.all()
        ]

        # Counts by task name
        task_result = await self.db.execute(
            select(
                DeadLetterMessage.task_name,
                func.count().label("cnt"),
            )
            .where(DeadLetterMessage.task_name.isnot(None))
            .group_by(DeadLetterMessage.task_name)
            .order_by(func.count().desc())
            .limit(20)
        )
        by_task = [
            DLQTaskCount(task_name=row[0], count=row[1])
            for row in task_result.all()
        ]

        # Counts by day (last 30 days)
        daily_result = await self.db.execute(
            select(
                cast(DeadLetterMessage.created_at, Date).label("day"),
                func.count().label("cnt"),
            )
            .group_by(cast(DeadLetterMessage.created_at, Date))
            .order_by(cast(DeadLetterMessage.created_at, Date).desc())
            .limit(30)
        )
        by_day = [
            DLQDailyCount(date=str(row[0]), count=row[1])
            for row in daily_result.all()
        ]

        return DLQAnalyticsResponse(
            total_messages=total,
            unresolved_count=unresolved,
            replayed_count=replayed,
            discarded_count=discarded,
            escalated_count=escalated,
            by_category=by_category,
            by_task=by_task,
            by_day=by_day,
        )
