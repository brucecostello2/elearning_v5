"""
DeduplicationService — SHA-256 content-addressable storage.
Replaces S3 server-side dedup heuristics with exact-match deduplication.
Saves storage by maintaining a single canonical file copy per content hash.
"""
import logging
from sqlalchemy.orm import Session
from app.models.dedup import DedupEntry
from app.models.render_output import RenderOutput
from app.services.seaweedfs_client import seaweedfs

logger = logging.getLogger(__name__)


class DeduplicationService:

    def __init__(self, db: Session):
        self.db = db

    def register_asset(self, data: bytes, project_id: int,
                       output_id: int, mime: str = "application/octet-stream",
                       filename: str = "file") -> dict:
        """
        Register a new asset.
        If SHA-256 hash already exists → increment reference_count only.
        If new → upload to SeaweedFS HOT collection, create index entry.
        Returns dict with fid, is_duplicate, bytes_saved.
        """
        sha256 = seaweedfs.sha256(data)
        existing = (
            self.db.query(DedupEntry)
            .filter(DedupEntry.sha256_hash == sha256)
            .first()
        )

        if existing:
            # Duplicate — reuse canonical copy
            existing.reference_count += 1
            from sqlalchemy import text
            self.db.execute(
                text("UPDATE deduplication_index SET last_referenced_at = NOW() "
                     "WHERE id = :id"),
                {"id": existing.id}
            )
            # Link render_output to dedup entry
            self._link_output(output_id, existing.canonical_fid,
                              existing.canonical_collection, sha256, existing.id)
            self.db.commit()
            logger.info("Dedup hit: sha256=%s refcount=%d",
                        sha256[:12], existing.reference_count)
            return {
                "fid": existing.canonical_fid,
                "collection": existing.canonical_collection,
                "is_duplicate": True,
                "bytes_saved": existing.file_size_bytes,
            }

        # New content — upload to HOT collection
        assignment = seaweedfs.upload("hot", data, filename=filename, mime=mime)
        fid = assignment["fid"]

        entry = DedupEntry(
            sha256_hash=sha256,
            canonical_fid=fid,
            canonical_collection="hot",
            file_size_bytes=len(data),
            mime_type=mime,
            reference_count=1,
        )
        self.db.add(entry)
        self.db.flush()

        self._link_output(output_id, fid, "hot", sha256, entry.id)
        self.db.commit()
        logger.info("New asset registered: sha256=%s size=%d bytes",
                    sha256[:12], len(data))
        return {
            "fid": fid,
            "collection": "hot",
            "is_duplicate": False,
            "bytes_saved": 0,
        }

    def release_asset(self, output_id: int) -> None:
        """Decrement reference_count. If count reaches 0, delete canonical copy."""
        output = self.db.query(RenderOutput).get(output_id)
        if not output or not output.dedup_index_id:
            return
        entry = self.db.query(DedupEntry).get(output.dedup_index_id)
        if not entry:
            return
        entry.reference_count = max(0, entry.reference_count - 1)
        if entry.reference_count == 0:
            seaweedfs.delete(entry.canonical_fid)
            self.db.delete(entry)
            logger.info("Deleted canonical file (refcount=0): fid=%s",
                        entry.canonical_fid)
        self.db.commit()

    def _link_output(self, output_id: int, fid: str,
                     collection: str, sha256: str, dedup_id: int) -> None:
        output = self.db.query(RenderOutput).get(output_id)
        if output:
            output.seaweedfs_fid = fid
            output.seaweedfs_collection = collection
            output.sha256_hash = sha256
            output.dedup_index_id = dedup_id
            output.storage_tier = "hot"
