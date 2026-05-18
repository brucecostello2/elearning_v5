"""
ArchiveService — manages the ARCHIVE SeaweedFS collection (/mnt/archive).
Replaces Glacier API. No restore delays — ARCHIVE is local HDD/tape mount.
On-demand restore promotes a file back to HOT in minutes.
"""
import logging
from sqlalchemy.orm import Session
from app.models.render_output import RenderOutput
from app.services.tier_migration_service import TierMigrationService

logger = logging.getLogger(__name__)


class ArchiveService:

    def __init__(self, db: Session):
        self.db = db
        self.migrator = TierMigrationService(db)

    def archive_output(self, output_id: int,
                       reason: str = "manual") -> bool:
        """Move a render output to the ARCHIVE collection."""
        output = self.db.query(RenderOutput).get(output_id)
        if not output or not output.seaweedfs_fid:
            return False
        if output.storage_tier == "archive":
            logger.info("Output %d already archived", output_id)
            return True
        self.migrator.migrate(output, "archive",
                              triggered_by=f"archive_service:{reason}")
        self.db.commit()
        return True

    def restore_output(self, output_id: int) -> bool:
        """
        Restore an archived output back to the HOT tier.
        Unlike Glacier (hours of restore delay), this completes in seconds
        since ARCHIVE is a local /mnt/archive mount.
        """
        output = self.db.query(RenderOutput).get(output_id)
        if not output or not output.seaweedfs_fid:
            return False
        if output.storage_tier != "archive":
            logger.info("Output %d is not archived (current tier: %s)",
                        output_id, output.storage_tier)
            return True
        self.migrator.migrate(output, "hot",
                              triggered_by="archive_service:restore")
        self.db.commit()
        logger.info("Restored output %d from archive to HOT", output_id)
        return True

    def list_archived(self, project_id: int) -> list[dict]:
        outputs = (
            self.db.query(RenderOutput)
            .filter(RenderOutput.project_id == project_id)
            .filter(RenderOutput.storage_tier == "archive")
            .order_by(RenderOutput.tier_transition_date.desc())
            .all()
        )
        return [
            {
                "id": o.id,
                "filename": o.filename,
                "file_size_bytes": o.file_size_bytes,
                "seaweedfs_fid": o.seaweedfs_fid,
                "archived_at": o.tier_transition_date.isoformat()
                if o.tier_transition_date else None,
            }
            for o in outputs
        ]
