"""Periodic DLQ processing task — runs every 5 minutes via Celery Beat.

Scans RabbitMQ dead-letter queue, ingests new messages into PostgreSQL,
categorizes failures, and fires alerts when thresholds are breached.

Beat schedule entry (add to celeryconfig.py):
    "process-dlq": {
        "task": "tasks.dlq_processor_task.process_dlq_task",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "default"}
    }
"""

import json
import logging
from typing import Any, Dict, List

from celery import shared_task

from app.database import get_db_context
from app.services.dlq_service import DLQService

logger = logging.getLogger(__name__)

# RabbitMQ Management API endpoint for DLQ inspection
RABBITMQ_MGMT_URL = __import__('os').environ.get(
    'RABBITMQ_MGMT_URL', 'http://node-01:15672'
)
RABBITMQ_USER = __import__('os').environ.get('RABBITMQ_USER', 'guest')
RABBITMQ_PASS = __import__('os').environ.get('RABBITMQ_PASS', 'guest')

# DLQ queue names to scan
DLQ_QUEUE_NAMES = [
    'default.dlq',
    'gpu_image.dlq',
    'gpu_video.dlq',
    'gpu_tts.dlq',
    'composition.dlq',
]


@shared_task(
    name="tasks.dlq_processor_task.process_dlq_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="default",
)
def process_dlq_task(self) -> Dict[str, Any]:
    """Scan RabbitMQ DLQs and ingest new failures into PostgreSQL.

    Returns summary dict with counts of ingested, alerted, skipped.
    """
    logger.info("DLQ Processor: starting scan of %d queues",
                len(DLQ_QUEUE_NAMES))
    ingested = 0
    skipped = 0

    with get_db_context() as db:
        svc = DLQService(db)

        for queue_name in DLQ_QUEUE_NAMES:
            messages = _fetch_dlq_messages(queue_name)
            if not messages:
                continue

            for raw_msg in messages:
                try:
                    _ingest_message(svc, queue_name, raw_msg)
                    ingested += 1
                except Exception as e:
                    logger.error(
                        "DLQ ingest failed for queue %s: %s",
                        queue_name, e
                    )
                    skipped += 1

    logger.info(
        "DLQ Processor: ingested=%d skipped=%d",
        ingested, skipped
    )
    return {"ingested": ingested, "skipped": skipped}


def _fetch_dlq_messages(queue_name: str) -> List[Dict[str, Any]]:
    """Fetch pending messages from a RabbitMQ DLQ via management API."""
    import urllib.request
    import base64

    url = (
        f"{RABBITMQ_MGMT_URL}/api/queues/%2F/{queue_name}"
        f"/get"
    )
    credentials = base64.b64encode(
        f"{RABBITMQ_USER}:{RABBITMQ_PASS}".encode()
    ).decode()
    payload = json.dumps({
        "count": 100,
        "requeue": False,
        "encoding": "auto",
        "truncate": 50000
    }).encode()

    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {credentials}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        if '404' not in str(e):
            logger.warning("Could not fetch DLQ %s: %s", queue_name, e)
        return []


def _ingest_message(
    svc: DLQService, queue_name: str, raw: Dict[str, Any]
) -> None:
    """Parse raw RabbitMQ message and ingest into DLQ service."""
    payload = raw.get('payload', {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"raw": payload}

    headers = raw.get('properties', {}).get('headers', {})
    exception_info = headers.get('x-exception-message',
                                 'Unknown error')
    exception_type = headers.get('x-exception-type', 'Exception')
    retry_count = int(headers.get('x-death', [{}])[0].get('count', 0)
                      if headers.get('x-death') else 0)

    task_name = payload.get('task', queue_name.replace('.dlq', '_task'))
    kwargs = payload.get('kwargs', {})
    job_id = (kwargs.get('job_id') or
              payload.get('args', [None])[0]
              if payload.get('args') else None)

    # Create synthetic exception for classification
    exc = Exception(exception_info)
    exc.__class__.__name__ = exception_type

    svc.process_failed_task(
        task_name=task_name,
        task_args=payload.get('args', []),
        task_kwargs=kwargs,
        exception=exc,
        task_id=payload.get('id'),
        queue=queue_name,
        retry_count=retry_count,
        job_id=str(job_id) if job_id else None,
    )
