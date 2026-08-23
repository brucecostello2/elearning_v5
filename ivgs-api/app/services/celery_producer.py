"""Lightweight Celery producer for the API.

The API does not host pipeline task code; it only enqueues tasks by name onto the
shared broker, which the worker fleet consumes. send_task(name, ...) does not require
the task to be defined locally. Broker/backend come from the same env the workers use.
"""
import os

from celery import Celery

_broker = (
    os.environ.get("IVGS_CELERY_BROKER_URL")
    or os.environ.get("REDIS_URL")
    or "redis://redis:6379/0"
)
_backend = os.environ.get("IVGS_CELERY_RESULT_BACKEND") or None

# WP-05 / ledger P0.1. This used to be a literal 3600 while the worker fleet also
# defaulted to 3600 against a 3900 s hard time_limit - the two copies of the number
# drifted apart the moment either side moved. Read the same env var the workers read,
# with the same default, so "must match the worker fleet" below is enforced by
# construction rather than by a comment.
_visibility_timeout = int(
    os.environ.get("IVGS_BROKER_VISIBILITY_TIMEOUT") or 7200
)

# Producer only — this app never starts a worker / consumes a queue.
celery_app = Celery("ivgs_api_producer", broker=_broker, backend=_backend)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_default_queue="default",
    broker_connection_retry_on_startup=True,
    # Must match the worker fleet's transport options so produced messages land in
    # the keyspace the workers actually consume (critically: global_keyprefix).
    broker_transport_options={
        "visibility_timeout": _visibility_timeout,
        "queue_order_strategy": "priority",
        "sep": ":",
        "priority_steps": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        "fanout_prefix": True,
        "fanout_patterns": True,
        "global_keyprefix": "ivgs_workers_",
    },
)
