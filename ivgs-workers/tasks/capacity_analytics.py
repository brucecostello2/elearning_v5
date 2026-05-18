"""Task: nightly capacity analytics — collect per-tier metrics, emit Prometheus."""
import logging
from celery import shared_task
from app.db.session import get_db_context
from app.services.storage_analytics_service import StorageAnalyticsService

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.capacity_analytics.run_analytics",
             bind=True, max_retries=2)
def run_analytics(self) -> dict:
    try:
        with get_db_context() as db:
            svc = StorageAnalyticsService(db)
            return svc.aggregate()
    except Exception as exc:
        logger.error("Capacity analytics task failed: %s", exc)
        raise self.retry(exc=exc)
