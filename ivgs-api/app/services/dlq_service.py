"""Dead-Letter Queue management service.

Responsibilities:
  - Ingest failed tasks from RabbitMQ DLQ into PostgreSQL
  - Classify failures by root cause category
  - Replay individual or bulk messages back to original queues
  - Provide failure analytics for Grafana dashboards
  - Circuit breaker: permanent-fail tasks that repeat 3+ times
"""

import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from celery import current_app as celery_app
from sqlalchemy.orm import Session

from app.models.dlq import DeadLetterMessage
from app.core.alerting import send_ops_alert

logger = logging.getLogger(__name__)

# Permanent failure threshold — same task fails 3 times in 24 hours
CIRCUIT_BREAK_THRESHOLD = 3
CIRCUIT_BREAK_WINDOW_HOURS = 24

# Alert when pending DLQ depth exceeds this
DLQ_ALERT_THRESHOLD = 10


class DLQService:
    """Dead-letter queue management service."""

    def __init__(self, db: Session):
        self.db = db

    def process_failed_task(
        self,
        task_name: str,
        task_args: List[Any],
        task_kwargs: Dict[str, Any],
        exception: Exception,
        task_id: Optional[str] = None,
        queue: str = "default",
        retry_count: int = 0,
        job_id: Optional[str] = None,
    ) -> DeadLetterMessage:
        """Ingest a failed task into the DLQ.

        Called by Celery's on_failure handler after retries exhausted.
        Categorizes the failure and stores with full traceback.
        """
        category = self._classify_failure(exception)
        tb = traceback.format_exc()

        msg = DeadLetterMessage(
            original_queue=queue,
            task_name=task_name,
            task_id=task_id,
            task_args=task_args,
            task_kwargs=task_kwargs,
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            traceback=tb,
            failure_category=category,
            retry_count_exhausted=retry_count,
            job_id=job_id,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)

        logger.error(
            "DLQ: ingested %s task (id=%s) category=%s job=%s",
            task_name, task_id, category, job_id
        )

        # Check alert threshold
        pending = (self.db.query(DeadLetterMessage)
                   .filter(DeadLetterMessage.resolution == 'pending')
                   .count())
        if pending >= DLQ_ALERT_THRESHOLD:
            send_ops_alert(
                f"DLQ depth {pending} >= threshold {DLQ_ALERT_THRESHOLD}",
                severity="warning"
            )

        # Circuit breaker check
        if self._should_permanent_fail(task_name):
            logger.error(
                "DLQ CIRCUIT BREAK: %s has failed %d+ times in %dh — "
                "marking permanent",
                task_name, CIRCUIT_BREAK_THRESHOLD, CIRCUIT_BREAK_WINDOW_HOURS
            )
            send_ops_alert(
                f"Permanent failure: {task_name} circuit broken",
                severity="critical"
            )

        return msg

    def replay_message(self, dlq_id: int, replayed_by: str = "api") -> str:
        """Re-enqueue original task to its source queue.

        Returns the new Celery task ID.
        Raises ValueError if message is not in 'pending' state.
        """
        msg = (self.db.query(DeadLetterMessage)
               .filter(DeadLetterMessage.id == dlq_id)
               .first())
        if not msg:
            raise ValueError(f"DLQ message {dlq_id} not found")
        if msg.resolution != 'pending':
            raise ValueError(
                f"Message {dlq_id} already resolved: {msg.resolution}"
            )

        # Re-enqueue via Celery send_task
        result = celery_app.send_task(
            msg.task_name,
            args=msg.task_args,
            kwargs=msg.task_kwargs,
            queue=msg.original_queue,
        )

        msg.replay(new_task_id=result.id)
        msg.reviewed_by = replayed_by
        self.db.commit()

        logger.info(
            "DLQ: replayed message %d as task %s", dlq_id, result.id
        )
        return result.id

    def bulk_replay(
        self,
        failure_category: Optional[str] = None,
        task_name: Optional[str] = None,
        max_messages: int = 100,
    ) -> Dict[str, Any]:
        """Replay multiple DLQ messages matching filter criteria."""
        query = (self.db.query(DeadLetterMessage)
                 .filter(DeadLetterMessage.resolution == 'pending'))
        if failure_category:
            query = query.filter(
                DeadLetterMessage.failure_category == failure_category
            )
        if task_name:
            query = query.filter(
                DeadLetterMessage.task_name == task_name
            )
        messages = query.limit(max_messages).all()

        replayed, failed = 0, 0
        for msg in messages:
            try:
                self.replay_message(msg.id, replayed_by="bulk_replay")
                replayed += 1
            except Exception as e:
                logger.warning("Bulk replay failed for %d: %s", msg.id, e)
                failed += 1

        return {"replayed": replayed, "failed": failed,
                "total": len(messages)}

    def bulk_discard(
        self,
        failure_category: str,
        reviewer: str = "api",
    ) -> int:
        """Discard all pending messages of a given failure category."""
        messages = (self.db.query(DeadLetterMessage)
                    .filter(DeadLetterMessage.resolution == 'pending',
                            DeadLetterMessage.failure_category == failure_category)
                    .all())
        for msg in messages:
            msg.discard(reviewer)
        self.db.commit()
        logger.info(
            "DLQ: bulk discarded %d messages (category=%s)",
            len(messages), failure_category
        )
        return len(messages)

    def get_failure_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """Return analytics for monitoring dashboards."""
        return DeadLetterMessage.get_failure_analytics(self.db, hours)

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _classify_failure(self, exception: Exception) -> str:
        """Classify exception into DLQ failure category."""
        name = type(exception).__name__.lower()
        msg = str(exception).lower()

        if any(k in name for k in ('timeout', 'timedout', 'deadlineexceeded')):
            return 'timeout'
        if any(k in msg for k in ('timeout', 'timed out', 'deadline')):
            return 'timeout'
        if any(k in name for k in ('connection', 'network', 'socket')):
            return 'transient'
        if any(k in msg for k in ('corrupt', 'invalid file', 'truncated')):
            return 'data_corruption'
        if any(k in name for k in ('validation', 'value', 'type', 'attribute')):
            return 'config'
        if any(k in msg for k in ('rate limit', '429', 'quota')):
            return 'external'
        if any(k in msg for k in ('out of memory', 'cuda', 'vram')):
            return 'resource'
        return 'unknown'

    def _should_permanent_fail(self, task_name: str) -> bool:
        """Check if a task has triggered the circuit breaker."""
        cutoff = datetime.utcnow() - timedelta(hours=CIRCUIT_BREAK_WINDOW_HOURS)
        count = (self.db.query(DeadLetterMessage)
                 .filter(DeadLetterMessage.task_name == task_name,
                         DeadLetterMessage.created_at >= cutoff)
                 .count())
        return count >= CIRCUIT_BREAK_THRESHOLD
