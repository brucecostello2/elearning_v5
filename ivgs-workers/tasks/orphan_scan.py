"""Task: daily orphan scan — walk SeaweedFS filer, quarantine unreferenced files."""
import logging
from celery import shared_task
from app.db.session import get_db_context
from app.services.orphan_cleanup_service import OrphanCleanupService

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.orphan_scan.run_orphan_scan",
             bind=True, max_retries=2, default_retry_delay=600)
def run_orphan_scan(self) -> dict:
    try:
        with get_db_context() as db:
            svc = OrphanCleanupService(db)
            return svc.run()
    except Exception as exc:
        logger.error("Orphan scan task failed: %s", exc)
        raise self.retry(exc=exc)
