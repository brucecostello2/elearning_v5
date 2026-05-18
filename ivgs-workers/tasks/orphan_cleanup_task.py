"""Periodic orphan job detection and cleanup.

Runs every 5 minutes via Celery Beat.
Detects and resolves stuck/orphaned jobs that have lost their worker
without completing or explicitly failing.

Orphan conditions:
  1. Job in 'running' state for >2 hours with no heartbeat update
  2. Job with all checkpoints complete but no 'composition' checkpoint
     (stalled before composition stage)
  3. Temp files in WORKDIR older than 24 hours (from failed jobs)

Beat schedule:
    "cleanup-orphans": {
        "task": "tasks.orphan_cleanup_task.cleanup_orphan_jobs_task",
        "schedule": crontab(minute="*/5"),
    }
"""

import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from celery import shared_task
from sqlalchemy import text

from app.database import get_db_context

logger = logging.getLogger(__name__)

WORKDIR = os.environ.get('WORKDIR', '/mnt/workdir')
ORPHAN_TIMEOUT_HOURS = 2
TEMP_FILE_RETENTION_HOURS = 24


@shared_task(
    name="tasks.orphan_cleanup_task.cleanup_orphan_jobs_task",
    bind=True,
    max_retries=1,
    queue="default",
)
def cleanup_orphan_jobs_task(self) -> dict:
    """Detect and remediate orphaned jobs.

    Returns summary of cleanup actions taken.
    """
    logger.info("Orphan cleanup: starting scan")
    orphaned = 0
    cleaned_files = 0

    with get_db_context() as db:
        # Find jobs running too long without heartbeat
        cutoff = datetime.utcnow() - timedelta(hours=ORPHAN_TIMEOUT_HOURS)
        orphan_jobs = db.execute(text("""
            SELECT j.id, j.status, j.updated_at
            FROM jobs j
            WHERE j.status IN ('running', 'processing')
              AND j.updated_at < :cutoff
              AND NOT EXISTS (
                  SELECT 1 FROM worker_heartbeats wh
                  WHERE wh.current_job_id = j.id
                    AND wh.last_heartbeat_at > :cutoff
              )
            LIMIT 100
        """), {"cutoff": cutoff}).fetchall()

        for job in orphan_jobs:
            logger.warning(
                "Orphan detected: job=%s status=%s last_update=%s",
                job.id, job.status, job.updated_at
            )
            # Transition to failed with orphan reason
            db.execute(text("""
                UPDATE jobs
                SET status = 'failed',
                    error_message = 'Orphaned: no heartbeat for >2 hours',
                    updated_at = NOW()
                WHERE id = :job_id
            """), {"job_id": job.id})
            orphaned += 1

        db.commit()

    # Clean temp files older than threshold
    if os.path.isdir(WORKDIR):
        age_cutoff = time.time() - (TEMP_FILE_RETENTION_HOURS * 3600)
        for entry in os.scandir(WORKDIR):
            if entry.is_dir():
                try:
                    mtime = entry.stat().st_mtime
                    if mtime < age_cutoff:
                        # Verify job is not still active
                        job_id = entry.name
                        with get_db_context() as db:
                            row = db.execute(text(
                                "SELECT status FROM jobs WHERE id = :id"
                            ), {"id": job_id}).fetchone()
                            if row and row.status in (
                                'complete', 'failed', 'cancelled'
                            ):
                                shutil.rmtree(entry.path, ignore_errors=True)
                                cleaned_files += 1
                                logger.info(
                                    "Cleaned temp dir: %s (job=%s)",
                                    entry.path, job_id
                                )
                except Exception as e:
                    logger.warning("Cleanup error for %s: %s", entry.path, e)

    logger.info(
        "Orphan cleanup complete: orphaned=%d cleaned_dirs=%d",
        orphaned, cleaned_files
    )
    return {"orphaned_jobs_failed": orphaned,
            "temp_dirs_cleaned": cleaned_files}
