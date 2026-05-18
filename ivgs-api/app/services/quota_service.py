"""
QuotaService — per-project SeaweedFS capacity enforcement.
Called before every job submission and by hourly Celery Beat task.
"""
import logging
from sqlalchemy.orm import Session
from app.models.quota import StorageQuota, StorageUsageLog
from app.core.config import settings

logger = logging.getLogger(__name__)

# Default quota tiers (bytes) — also in config/quota_limits.yml
QUOTA_TIERS = {
    "free":       50  * 1024**3,   # 50 GB
    "standard":  500  * 1024**3,   # 500 GB
    "enterprise": 5   * 1024**4,   # 5 TB
}


class QuotaExceededError(Exception):
    def __init__(self, project_id: int, used: int, limit: int):
        self.project_id = project_id
        self.used = used
        self.limit = limit
        super().__init__(
            f"Project {project_id}: used {used/1024**3:.1f} GB "
            f"of {limit/1024**3:.1f} GB quota"
        )


class QuotaService:

    def __init__(self, db: Session):
        self.db = db

    def check_and_enforce(self, project_id: int,
                          estimated_bytes: int = 0) -> None:
        """Raise QuotaExceededError if project is at or above limit."""
        quota = self._get_or_create_quota(project_id)
        projected = quota.used_bytes + estimated_bytes
        if not quota.soft_limit_active and projected > quota.max_bytes:
            raise QuotaExceededError(project_id, projected, quota.max_bytes)
        if projected > quota.max_bytes * quota.warning_threshold:
            logger.warning(
                "Project %d at %.0f%% capacity (%s / %s GB)",
                project_id,
                projected / quota.max_bytes * 100,
                projected // 1024**3,
                quota.max_bytes // 1024**3,
            )

    def record_usage(self, project_id: int, delta_bytes: int,
                     tier: str, event: str = "file_added") -> None:
        quota = self._get_or_create_quota(project_id)
        quota.used_bytes = max(0, quota.used_bytes + delta_bytes)
        tier_col = f"{tier}_bytes"
        if hasattr(quota, tier_col):
            current = getattr(quota, tier_col)
            setattr(quota, tier_col, max(0, current + delta_bytes))
        log = StorageUsageLog(
            project_id=project_id,
            event=event,
            delta_bytes=delta_bytes,
            resulting_used_bytes=quota.used_bytes,
            tier=tier,
        )
        self.db.add(log)
        self.db.flush()

    def get_usage_summary(self, project_id: int) -> dict:
        quota = self._get_or_create_quota(project_id)
        return {
            "project_id": project_id,
            "quota_tier": quota.quota_tier,
            "max_bytes": quota.max_bytes,
            "used_bytes": quota.used_bytes,
            "utilisation_pct": round(quota.used_bytes / quota.max_bytes * 100, 1),
            "tiers": {
                "hot": quota.hot_bytes,
                "warm": quota.warm_bytes,
                "cold": quota.cold_bytes,
                "archive": quota.archive_bytes,
            },
        }

    def set_quota_tier(self, project_id: int, tier: str,
                       custom_bytes: int = None) -> None:
        quota = self._get_or_create_quota(project_id)
        quota.quota_tier = tier
        quota.max_bytes = custom_bytes or QUOTA_TIERS.get(tier, QUOTA_TIERS["free"])
        self.db.flush()

    def _get_or_create_quota(self, project_id: int) -> StorageQuota:
        quota = (
            self.db.query(StorageQuota)
            .filter(StorageQuota.project_id == project_id)
            .first()
        )
        if quota is None:
            quota = StorageQuota(
                project_id=project_id,
                quota_tier="free",
                max_bytes=QUOTA_TIERS["free"],
                used_bytes=0,
            )
            self.db.add(quota)
            self.db.flush()
        return quota
