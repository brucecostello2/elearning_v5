"""Task: nightly NAS backup — pg_dump + rsync to /mnt/backup."""
import logging
from celery import shared_task
from app.db.session import get_db_context
from app.services.backup_service import BackupService

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.backup_snapshot.run_backup",
             bind=True, max_retries=1, time_limit=7200)
def run_backup(self, backup_type: str = "incremental") -> dict:
    """7200s time limit — incremental rsync completes well within 2h."""
    try:
        with get_db_context() as db:
            svc = BackupService(db)
            snap = svc.run_backup(backup_type=backup_type)
            return {
                "snapshot": snap.snapshot_name,
                "status": snap.status,
                "bytes_transferred": snap.bytes_transferred,
            }
    except Exception as exc:
        logger.error("Backup task failed: %s", exc)
        raise self.retry(exc=exc)
