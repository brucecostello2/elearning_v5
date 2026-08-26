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
from celery.schedules import crontab
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

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------
# The schedule lives HERE, in the backup worker's own app, not in
# ivgs-workers/celery_app.py.  That is not a style preference: this app sets
# broker_transport_options.global_keyprefix = "ivgs_backup_" (below) and the
# ivgs-workers app sets no prefix at all, so the two occupy different Redis
# keyspaces.  A beat entry added to ivgs-workers would publish into a keyspace
# this worker never reads, and the task would silently never run.  The API
# works around the same split by building its own producer with a matching
# prefix (ivgs-api/app/api/v1/backup.py:55-68).
#
# Entries pass NO arguments.  The tasks take backup_id optionally; omitted, the
# shell script mints its own UUID and owns its backup_records row, so a
# scheduled run is as visible in the GUI as an API-triggered one.  Beat cannot
# mint a UUID per firing, which is why that convention exists.
#
# Times match spec §14.1 Table 14-1 and the host crontab these replace.
# config_backup is deliberately NOT scheduled here: it still runs from host
# cron at 04:00, and scheduling it in both places would double-fire, with the
# loser hitting the lock file and recording a spurious failure.
#
# asset-backup is deliberately ABSENT, pending an operator decision.
# asset_backup.sh reads four host paths that are NOT mounted into this
# container — verified 2026-08-14:
#     /var/lib/docker/volumes/ivgs-infra_seaweedfs-{volume,filer,master}-data/_data
#     /mnt/ivgs-shared
# All four report MISSING from inside ivgs-backup-worker.  A beat entry here
# would therefore fail every night at 03:00, manufacturing exactly the false
# failures this work exists to remove.  See WP-BACKUP-SCHEDULE pass 2 §D1.
BEAT_SCHEDULE = {
    "full-database-backup": {
        "task": "tasks.backup_tasks.run_full_database_backup",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "backup"},
    },
    # WP-59 Task 8 (WP-57 D-2, RULED: implement PITR).
    #
    # WEEKLY, Sunday 01:00 UTC. Three constraints put it there and they are all
    # about not colliding with something else on this node:
    #
    #   * BEFORE the 02:00 logical dump, not after. If both were to fail on the
    #     same night the operator should find out from the one that runs every
    #     night, and a 01:00 start gives the base backup an hour of headroom
    #     before pg_dump wants the same I/O.
    #   * Sunday, because a base backup reads the whole data directory and this
    #     is a 16 GB node that has been OOM-killed by its host before
    #     (dev/CLAUDE.md §7). The quietest night is the right one.
    #   * Weekly rather than daily because the WAL archive is what covers the
    #     interval between bases -- that is the entire point of having one.
    #     Taking a base every night would store the same cluster seven times to
    #     shorten a replay that already takes seconds on a 670 KB-dump database.
    #
    # THE WINDOW IS RECONCILED, NOT INHERITED. WAL retention must cover the
    # interval back to the oldest base it must replay onto. Base retention is
    # 35 days and WAL retention is 7 (BACKUP_RETENTION_WAL_DAYS), so the WAL
    # window is SHORTER than the base window -- deliberately, and the runbook
    # states the resulting promise rather than pretending the longer number
    # governs. See docs/runbooks/point-in-time-recovery.md §"The window".
    "physical-base-backup": {
        "task": "tasks.backup_tasks.run_base_backup",
        "schedule": crontab(day_of_week=0, hour=1, minute=0),
        "options": {"queue": "backup"},
    },
}


celery_app.conf.update(
    # Scheduled backups — see BEAT_SCHEDULE above
    beat_schedule=BEAT_SCHEDULE,
    # Keep beat's state off the image's read-only-ish /app and out of the way
    # of the worker's cwd.  Mirrors ivgs-workers/celery_app.py:316.
    beat_schedule_filename="/tmp/ivgs-backup-celerybeat-schedule",
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
        "tasks.backup_tasks.run_base_backup":          {"queue": "backup"},
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
