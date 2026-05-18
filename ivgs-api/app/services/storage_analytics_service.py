"""
StorageAnalyticsService — capacity metrics per SeaweedFS tier.
Replaces cloud cost analytics. Reports GB used/available per tier,
dedup efficiency, orphan rate.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.services.seaweedfs_client import seaweedfs
from app.core.prometheus import (
    gauge_tier_used_bytes,
    gauge_tier_free_bytes,
    gauge_dedup_ratio,
)

logger = logging.getLogger(__name__)

TIER_COLLECTIONS = ["hot", "warm", "cold", "archive"]


class StorageAnalyticsService:

    def __init__(self, db: Session):
        self.db = db

    def aggregate(self) -> dict:
        """Called nightly. Collects per-tier stats and writes to DB + Prometheus."""
        report = {"timestamp": datetime.now(timezone.utc).isoformat(), "tiers": {}}

        for tier in TIER_COLLECTIONS:
            try:
                info = seaweedfs.collection_status(tier)
                used  = info.get("DiskSize", 0)
                free  = info.get("FreeDiskSize", 0)
                files = info.get("FileCount", 0)
                report["tiers"][tier] = {
                    "used_bytes": used,
                    "free_bytes": free,
                    "file_count": files,
                    "utilisation_pct": round(used / (used + free) * 100, 1)
                    if (used + free) > 0 else 0,
                }
                # Prometheus gauges
                gauge_tier_used_bytes.labels(tier=tier).set(used)
                gauge_tier_free_bytes.labels(tier=tier).set(free)
            except Exception as exc:
                logger.warning("Failed to collect stats for tier %s: %s", tier, exc)
                report["tiers"][tier] = {"error": str(exc)}

        # Deduplication ratio
        dedup_stats = self._dedup_ratio()
        report["dedup_ratio"] = dedup_stats
        gauge_dedup_ratio.set(dedup_stats.get("ratio", 0))

        # Persist summary to DB
        self._persist_capacity_log(report)
        logger.info("Capacity analytics complete: %s", report)
        return report

    def get_dashboard_data(self) -> dict:
        """Real-time snapshot for frontend StorageCapacityDashboard."""
        return self.aggregate()

    def _dedup_ratio(self) -> dict:
        from sqlalchemy import func
        from app.models.dedup import DedupEntry
        total_refs = self.db.query(
            func.sum(DedupEntry.reference_count)).scalar() or 1
        unique_files = self.db.query(func.count(DedupEntry.id)).scalar() or 1
        total_logical_bytes = self.db.query(
            func.sum(DedupEntry.file_size_bytes *
                     DedupEntry.reference_count)).scalar() or 0
        total_physical_bytes = self.db.query(
            func.sum(DedupEntry.file_size_bytes)).scalar() or 0
        saved = total_logical_bytes - total_physical_bytes
        ratio = saved / total_logical_bytes * 100 if total_logical_bytes > 0 else 0
        return {
            "total_references": int(total_refs),
            "unique_files": int(unique_files),
            "logical_bytes": int(total_logical_bytes),
            "physical_bytes": int(total_physical_bytes),
            "saved_bytes": int(saved),
            "ratio": round(ratio, 2),
        }

    def _persist_capacity_log(self, report: dict) -> None:
        from sqlalchemy import text
        for tier, data in report["tiers"].items():
            if "error" not in data:
                self.db.execute(
                    text("""
                        INSERT INTO storage_capacity_log
                            (tier, used_bytes, free_bytes, file_count, recorded_at)
                        VALUES (:tier, :used, :free, :files, NOW())
                        ON CONFLICT DO NOTHING
                    """),
                    {"tier": tier, "used": data["used_bytes"],
                     "free": data["free_bytes"], "files": data["file_count"]},
                )
        self.db.commit()
