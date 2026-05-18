"""
OrphanCleanupService — identifies SeaweedFS files with no DB reference.
Files are quarantined for 7 days, then hard-deleted from the filer.
No S3 API. No boto3.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.services.seaweedfs_client import seaweedfs
from app.models.render_output import RenderOutput
from app.models.dedup import DedupEntry

logger = logging.getLogger(__name__)
QUARANTINE_PATH = "/quarantine"
QUARANTINE_TTL_DAYS = 7


class OrphanCleanupService:

    def __init__(self, db: Session):
        self.db = db

    def run(self) -> dict:
        stats = {"scanned": 0, "orphans_found": 0, "quarantined": 0,
                 "deleted": 0, "errors": 0}

        # --- Phase 1: Walk filer and identify orphans ---
        fids_in_db = self._get_known_fids()
        fids_on_filer = self._walk_filer("/renders")
        stats["scanned"] = len(fids_on_filer)

        orphan_fids = fids_on_filer - fids_in_db
        stats["orphans_found"] = len(orphan_fids)

        for fid, filer_path in orphan_fids:
            try:
                self._quarantine_file(fid, filer_path)
                stats["quarantined"] += 1
            except Exception as exc:
                logger.error("Quarantine failed for %s: %s", fid, exc)
                stats["errors"] += 1

        # --- Phase 2: Hard-delete expired quarantine files ---
        deleted = self._purge_expired_quarantine()
        stats["deleted"] = deleted

        self.db.commit()
        logger.info("Orphan cleanup complete: %s", stats)
        return stats

    def _get_known_fids(self) -> set:
        fids = set()
        for (fid,) in self.db.query(RenderOutput.seaweedfs_fid).filter(
            RenderOutput.seaweedfs_fid.isnot(None)
        ).all():
            fids.add(fid)
        for (fid,) in self.db.query(DedupEntry.canonical_fid).all():
            fids.add(fid)
        return fids

    def _walk_filer(self, root_path: str) -> set:
        """Recursively walk the filer and collect (fid, path) tuples."""
        result = set()
        try:
            entries = seaweedfs.filer_list(root_path)
        except Exception:
            return result

        for entry in entries:
            if entry.get("IsDirectory"):
                sub = self._walk_filer(f"{root_path}/{entry['FullPath'].split('/')[-1]}")
                result |= sub
            else:
                fid = entry.get("Fid", {}).get("FileId")
                if fid:
                    result.add((fid, entry.get("FullPath", "")))
        return result

    def _quarantine_file(self, fid: str, filer_path: str) -> None:
        now = datetime.now(timezone.utc)
        quarantine_path = f"{QUARANTINE_PATH}/{fid}"
        # Move via filer: read + write + delete original
        data = seaweedfs.filer_get(filer_path)
        seaweedfs.filer_put(quarantine_path, data)
        seaweedfs.filer_delete(filer_path)
        from app.models.dedup import AssetInvalidationLog  # lazy import
        log = AssetInvalidationLog(
            seaweedfs_fid=fid,
            filer_path=filer_path,
            action="quarantined",
            reason="no_db_reference",
            quarantine_expires_at=now + timedelta(days=QUARANTINE_TTL_DAYS),
        )
        self.db.add(log)

    def _purge_expired_quarantine(self) -> int:
        from app.models.dedup import AssetInvalidationLog
        now = datetime.now(timezone.utc)
        expired = (
            self.db.query(AssetInvalidationLog)
            .filter(AssetInvalidationLog.action == "quarantined")
            .filter(AssetInvalidationLog.quarantine_expires_at <= now)
            .all()
        )
        deleted = 0
        for log in expired:
            try:
                seaweedfs.filer_delete(f"{QUARANTINE_PATH}/{log.seaweedfs_fid}")
                log.action = "deleted"
                deleted += 1
            except Exception as exc:
                logger.error("Purge failed for %s: %s", log.seaweedfs_fid, exc)
        return deleted
