"""
IVGS v5 — Backup Worker Celery Application
==========================================

Lightweight Celery factory for the Phase 14 backup worker.

Listens only on the `backup` queue.  Tasks are defined in tasks/backup_tasks.py
and registered via the include= parameter below.

Broker:        Redis (shared with all other workers, separate logical DB)
Result store:  PostgreSQL (durable; results survive worker restarts)
Queue:         backup  (dedicated; not consumed by GPU workers)

Environment variables:
    IVGS_CELERY_BROKER_URL    — Redis broker URL
    IVGS_CELERY_RESULT_BACKEND — Postgres result backend
    BACKUP_TASK_TIME_LIMIT     — Hard timeout per task (seconds, default 3600)
    BACKUP_TASK_SOFT_TIME_LIMIT — Soft warning timeout (default 3300)

Spec ref: §14.1 backup architecture, §6.4 Celery task queues.
"""
from __future__ import annotations

import os
from celery import Celery
from kombu import Exchange, Queue

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------

BROKER_URL = os.environ.get(
    "IVGS_CELERY_BROKER_URL",
    "redis://redis:6379/0",
)
RESULT_BACKEND = os.environ.get(
    "IVGS_CELERY_RESULT_BACKEND",
    "db+postgresql+psycopg2://ivgs:Costello0359@postgres:5432/ivgs",
)

# Task hard timeout — full DB backup should complete in well under this on
# the small DB we have today.  Tunable via env for larger DBs in future.
TASK_TIME_LIMIT = int(os.environ.get("BACKUP_TASK_TIME_LIMIT", "3600"))
TASK_SOFT_TIME_LIMIT = int(os.environ.get("BACKUP_TASK_SOFT_TIME_LIMIT", "3300"))


# ---------------------------------------------------------------------------
# Queue definition
# ---------------------------------------------------------------------------
# `backup` queue is separate from `default` to keep backup tasks isolated
# from GPU/orchestration tasks.  Only this worker consumes from `backup`.
# ---------------------------------------------------------------------------
backup_exchange = Exchange("backup", type="direct")

TASK_QUEUES = (
    Queue(
        "backup",
        exchange=backup_exchange,
        routing_key="backup",
        # Backup tasks are infrequent (4/day from cron + ad-hoc API triggers).
        # No need for priority levels here.
    ),
)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
celery_app = Celery(
    "ivgs_backup_worker",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["tasks.backup_tasks"],   # task modules to auto-import
)

celery_app.conf.update(
    # Queue routing — only the `backup` queue
    task_queues=TASK_QUEUES,
    task_default_queue="backup",
    task_default_exchange="backup",
    task_default_routing_key="backup",
    # Routes — explicitly map every backup task to the backup queue
    task_routes={
        "tasks.backup_tasks.run_full_database_backup": {"queue": "backup"},
        "tasks.backup_tasks.run_asset_backup":         {"queue": "backup"},
        "tasks.backup_tasks.run_config_backup":        {"queue": "backup"},
        "tasks.backup_tasks.run_verification":         {"queue": "backup"},
    },
    # Reliability — backups must not be lost.  acks_late + reject_on_worker_lost
    # means if the worker dies mid-task, the message is re-delivered.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Prefetch one task at a time — backups are heavy operations.
    worker_prefetch_multiplier=1,
    # Timeouts
    task_time_limit=TASK_TIME_LIMIT,
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
    # Result expiration — keep last 24 hours of results for debugging
    result_expires=86400,
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Logging — JSON via python-json-logger configured by the worker process
    worker_log_format=(
        "%(asctime)s [%(levelname)s] %(processName)s %(name)s: %(message)s"
    ),
    worker_task_log_format=(
        "%(asctime)s [%(levelname)s] %(task_name)s[%(task_id)s]: %(message)s"
    ),
    # Broker transport options — required for kombu 5.4+ when using Redis as
    # broker.  Without fanout_prefix and fanout_patterns, pidbox control
    # commands (used by `celery inspect ping` and the healthcheck) crash
    # with "ValueError: not enough values to unpack (expected 3, got 1)" in
    # kombu/transport/virtual/exchange.py lookup().
    #
    # The global_keyprefix isolates our Redis keyspace from the other Celery
    # apps (ivgs-celery-default) sharing this Redis instance.  Different
    # prefixes = different visibility scopes; one worker's pidbox doesn't
    # interfere with another's.
    broker_transport_options={
        "fanout_prefix": True,
        "fanout_patterns": True,
        "global_keyprefix": "ivgs_backup_",
    },
    # Same for result backend (postgres URLs ignore this, harmless to set)
    result_backend_transport_options={
        "global_keyprefix": "ivgs_backup_",
    },
    # Quiet the deprecation warning about broker_connection_retry_on_startup
    broker_connection_retry_on_startup=True,
)


if __name__ == "__main__":
    # Allow direct invocation for debugging:  python celery_app.py
    celery_app.start()
