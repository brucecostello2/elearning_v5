"""
TierMigrationService — physical file move between SeaweedFS collections.
Algorithm:
  1. Download file data from source collection via volume server
  2. Assign new FID in destination collection (different volume type)
  3. Upload to destination volume server
  4. Delete original FID
  5. Atomically update DB (render_output + tier_transition_log)
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.render_output import RenderOutput
from app.services.seaweedfs_client import seaweedfs

logger = logging.getLogger(__name__)

COLLECTION_MAP = {
    "hot":     "hot",
    "warm":    "warm",
    "cold":    "cold",
    "archive": "archive",
}


class TierMigrationService:

    def __init__(self, db: Session):
        self.db = db

    def migrate(self, output: RenderOutput, target_tier: str,
                triggered_by: str = "manual") -> bool:
        if not output.seaweedfs_fid:
            raise ValueError(f"Output {output.id} has no seaweedfs_fid")
        if output.storage_tier == target_tier:
            return True  # already at target

        source_fid = output.seaweedfs_fid
        source_tier = output.storage_tier

        try:
            # Step 1: Download from source
            data = seaweedfs.download(source_fid, source_tier)

            # Step 2+3: Assign and upload to destination
            dest_collection = COLLECTION_MAP[target_tier]
            assignment = seaweedfs.upload(
                dest_collection, data,
                filename=getattr(output, "filename", "file"),
                mime=getattr(output, "mime_type", "application/octet-stream"),
            )
            new_fid = assignment["fid"]
            new_volume_id = int(new_fid.split(",")[0])

            # Step 4: Delete source
            seaweedfs.delete(source_fid)

            # Step 5: Update DB
            now = datetime.now(timezone.utc)
            self._write_transition_log(
                output.id, source_tier, target_tier,
                source_fid, new_fid, output.file_size_bytes, triggered_by, now
            )
            output.seaweedfs_fid = new_fid
            output.seaweedfs_volume_id = new_volume_id
            output.seaweedfs_collection = dest_collection
            output.storage_tier = target_tier
            output.tier_transition_date = now

            logger.info("Migrated output %d: %s→%s fid=%s→%s",
                        output.id, source_tier, target_tier,
                        source_fid[:12], new_fid[:12])
            return True

        except Exception as exc:
            logger.error("Migration failed for output %d (%s→%s): %s",
                         output.id, source_tier, target_tier, exc)
            raise

    def bulk_migrate(self, output_ids: list[int],
                     target_tier: str,
                     triggered_by: str = "bulk_manual") -> dict:
        results = {"success": 0, "errors": 0}
        for oid in output_ids:
            output = self.db.query(RenderOutput).get(oid)
            if not output:
                results["errors"] += 1
                continue
            try:
                self.migrate(output, target_tier, triggered_by)
                results["success"] += 1
            except Exception:
                results["errors"] += 1
        self.db.commit()
        return results

    def _write_transition_log(
        self, output_id: int, from_tier: str, to_tier: str,
        old_fid: str, new_fid: str, size: int, by: str, ts: datetime
    ) -> None:
        from sqlalchemy import text
        self.db.execute(
            text("""
                INSERT INTO tier_transition_log
                    (render_output_id, from_tier, to_tier, old_fid,
                     new_fid, file_size_bytes, migrated_by, created_at)
                VALUES
                    (:oid, :from_t, :to_t, :old_fid,
                     :new_fid, :size, :by, :ts)
            """),
            {
                "oid": output_id, "from_t": from_tier, "to_t": to_tier,
                "old_fid": old_fid, "new_fid": new_fid,
                "size": size or 0, "by": by, "ts": ts,
            }
        )
