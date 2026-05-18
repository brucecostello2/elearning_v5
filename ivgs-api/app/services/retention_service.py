"""
RetentionService — evaluates retention policies and drives tier transitions.
Runs daily via Celery Beat (01:00 UTC). No AWS/cloud API calls.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
from sqlalchemy.orm import Session
from app.db.session import get_db_session
from app.models.retention import RetentionPolicy
from app.models.render_output import RenderOutput
from app.services.tier_migration_service import TierMigrationService

logger = logging.getLogger(__name__)

TIER_ORDER = ["hot", "warm", "cold", "archive"]

class RetentionService:

    def __init__(self, db: Session):
        self.db = db
        self.migrator = TierMigrationService(db)

    def run_lifecycle(self) -> dict:
        """Main entry point called by Celery Beat task."""
        now = datetime.now(timezone.utc)
        policies = {p.id: p for p in self.db.query(RetentionPolicy).all()}
        default_policy = (
            self.db.query(RetentionPolicy)
            .filter(RetentionPolicy.name == "global_default")
            .first()
        )

        stats = {"evaluated": 0, "migrated": 0, "deleted": 0, "errors": 0}

        # Only process rows that have been registered with SeaweedFS
        outputs = (
            self.db.query(RenderOutput)
            .filter(RenderOutput.seaweedfs_fid.isnot(None))
            .filter(RenderOutput.preserve_flag.is_(False))
            .all()
        )

        for output in outputs:
            stats["evaluated"] += 1
            try:
                policy = policies.get(output.retention_policy_id, default_policy)
                if policy is None:
                    continue
                action = self._determine_action(output, policy, now)
                if action == "migrate":
                    target = self._next_tier(output.storage_tier, output, policy, now)
                    if target:
                        self.migrator.migrate(output, target, triggered_by="retention_service")
                        stats["migrated"] += 1
                elif action == "delete":
                    self._schedule_deletion(output)
                    stats["deleted"] += 1
            except Exception as exc:
                logger.error("Retention error for output %d: %s", output.id, exc)
                stats["errors"] += 1

        self.db.commit()
        logger.info("Retention lifecycle complete: %s", stats)
        return stats

    def _determine_action(self, output: RenderOutput,
                          policy: RetentionPolicy, now: datetime) -> str:
        age_days = (now - output.created_at).days
        if (output.storage_tier == "archive"
                and policy.delete_after_days
                and age_days >= policy.delete_after_days):
            return "delete"
        return "migrate"

    def _next_tier(self, current: str, output: RenderOutput,
                   policy: RetentionPolicy, now: datetime) -> Optional[str]:
        """Return the next tier the file should move to, or None if unchanged."""
        age_days = (now - output.created_at).days
        thresholds = {
            "hot":  policy.hot_days,
            "warm": policy.hot_days + policy.warm_days,
            "cold": policy.hot_days + policy.warm_days + policy.cold_days,
        }
        if current == "hot" and age_days >= thresholds["hot"]:
            return "warm"
        if current == "warm" and age_days >= thresholds["warm"]:
            return "cold"
        if current == "cold" and age_days >= thresholds["cold"]:
            return "archive"
        return None

    def _schedule_deletion(self, output: RenderOutput) -> None:
        """Mark for deletion — actual filer delete happens in OrphanCleanupService."""
        output.storage_tier = "archive"
        output.preserve_flag = False
        output.seaweedfs_collection = "archive"
        logger.info("Scheduled for deletion: output_id=%d fid=%s",
                    output.id, output.seaweedfs_fid)

    def reset_to_hot_on_access(self, output_id: int) -> bool:
        """Called by download handler to reset tier when user downloads a file."""
        output = self.db.query(RenderOutput).get(output_id)
        if output and output.storage_tier != "hot":
            old_tier = output.storage_tier
            self.migrator.migrate(output, "hot", triggered_by="user_access")
            output.last_accessed_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info("Reset output %d from %s to hot on user access",
                        output_id, old_tier)
            return True
        return False
