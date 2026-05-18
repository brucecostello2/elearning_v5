"""Task: daily retention lifecycle — evaluate all assets, dispatch tier moves."""
import logging
from celery import shared_task
from app.db.session import get_db_context
from app.services.retention_service import RetentionService

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.retention_lifecycle.run_lifecycle",
             bind=True, max_retries=2, default_retry_delay=300)
def run_lifecycle(self) -> dict:
    try:
        with get_db_context() as db:
            svc = RetentionService(db)
            return svc.run_lifecycle()
    except Exception as exc:
        logger.error("Retention lifecycle task failed: %s", exc)
        raise self.retry(exc=exc)
