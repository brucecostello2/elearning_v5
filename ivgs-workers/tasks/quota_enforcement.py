"""Task: hourly quota enforcement — recalculate used_bytes, fire alerts."""
import logging
from sqlalchemy import func
from celery import shared_task
from app.db.session import get_db_context
from app.models.quota import StorageQuota
from app.models.render_output import RenderOutput
from app.core.alerts import send_alert

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.quota_enforcement.run_enforcement",
             bind=True, max_retries=3)
def run_enforcement(self) -> dict:
    """Re-aggregate actual DB usage per project, update storage_quotas,
    fire alerts for projects at or above warning/critical thresholds."""
    try:
        with get_db_context() as db:
            # Re-aggregate actual bytes from render_outputs
            usage_rows = (
                db.query(
                    RenderOutput.project_id,
                    func.sum(RenderOutput.file_size_bytes).label("total"),
                    func.sum(
                        func.case(
                            (RenderOutput.storage_tier == "hot",
                             RenderOutput.file_size_bytes), else_=0
                        )
                    ).label("hot"),
                    func.sum(
                        func.case(
                            (RenderOutput.storage_tier == "warm",
                             RenderOutput.file_size_bytes), else_=0
                        )
                    ).label("warm"),
                )
                .filter(RenderOutput.seaweedfs_fid.isnot(None))
                .group_by(RenderOutput.project_id)
                .all()
            )

            alerts_fired = 0
            for row in usage_rows:
                quota = (
                    db.query(StorageQuota)
                    .filter(StorageQuota.project_id == row.project_id)
                    .first()
                )
                if not quota:
                    continue
                quota.used_bytes = row.total or 0
                quota.hot_bytes  = row.hot  or 0
                quota.warm_bytes = row.warm or 0
                ratio = quota.used_bytes / quota.max_bytes if quota.max_bytes else 0
                if ratio >= quota.critical_threshold:
                    send_alert("CRITICAL", f"Project {row.project_id} at "
                               f"{ratio*100:.0f}% storage capacity")
                    alerts_fired += 1
                elif ratio >= quota.warning_threshold:
                    send_alert("WARNING", f"Project {row.project_id} at "
                               f"{ratio*100:.0f}% storage capacity")
                    alerts_fired += 1

            db.commit()
            return {"projects_checked": len(usage_rows), "alerts_fired": alerts_fired}

    except Exception as exc:
        logger.error("Quota enforcement task failed: %s", exc)
        raise self.retry(exc=exc)
