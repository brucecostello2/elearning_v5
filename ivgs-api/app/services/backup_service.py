"""
BackupService — pg_dump + rsync to NAS /mnt/backup.
Replaces all S3 backup bucket operations.
NAS mount: /mnt/backup (SMB/NFS mount, available on all cluster nodes)
"""
import hashlib
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.backup import BackupSnapshot
from app.core.config import settings

logger = logging.getLogger(__name__)

BACKUP_ROOT    = Path("/mnt/backup/ivgs")
WORKDIR        = Path("/mnt/workdir")
DB_URL         = settings.DATABASE_URL
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))


class BackupService:

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # FULL BACKUP FLOW
    # ------------------------------------------------------------------
    def run_backup(self, backup_type: str = "incremental") -> BackupSnapshot:
        now = datetime.now(timezone.utc)
        name = f"ivgs_{now.strftime('%Y_%m_%dT%H%M%SZ')}"
        dest = BACKUP_ROOT / name
        dest.mkdir(parents=True, exist_ok=True)

        snapshot = BackupSnapshot(
            snapshot_name=name,
            backup_type=backup_type,
            source_path=str(WORKDIR),
            dest_path=str(dest),
            status="running",
            started_at=now,
        )
        self.db.add(snapshot)
        self.db.flush()

        try:
            # Step 1: pg_dump
            dump_path = dest / "postgres.sql.gz"
            self._pg_dump(dump_path)
            snapshot.db_dump_path = str(dump_path)
            snapshot.verify_hash = self._sha256_file(dump_path)

            # Step 2: rsync workdir to NAS
            rsync_stats = self._rsync_workdir(dest, backup_type)
            snapshot.bytes_transferred = rsync_stats.get("bytes_transferred", 0)
            snapshot.files_transferred = rsync_stats.get("files_transferred", 0)
            snapshot.rsync_exit_code = rsync_stats.get("exit_code", 0)

            if snapshot.rsync_exit_code not in (0, 24):  # 24 = partial (vanished files)
                raise RuntimeError(f"rsync failed with code {snapshot.rsync_exit_code}")

            snapshot.status = "success"
            snapshot.completed_at = datetime.now(timezone.utc)
            snapshot.expires_at = now + timedelta(days=RETENTION_DAYS)
            logger.info("Backup complete: %s (%s bytes)", name,
                        snapshot.bytes_transferred)

        except Exception as exc:
            snapshot.status = "failed"
            snapshot.error_message = str(exc)
            snapshot.completed_at = datetime.now(timezone.utc)
            logger.error("Backup failed: %s — %s", name, exc)

        self.db.commit()
        self._rotate_old_snapshots()
        return snapshot

    # ------------------------------------------------------------------
    # RESTORE
    # ------------------------------------------------------------------
    def restore_snapshot(self, snapshot_name: str,
                         restore_db: bool = True,
                         restore_files: bool = True) -> bool:
        snapshot = (
            self.db.query(BackupSnapshot)
            .filter(BackupSnapshot.snapshot_name == snapshot_name)
            .first()
        )
        if not snapshot or snapshot.status != "success":
            raise ValueError(f"Snapshot {snapshot_name!r} not found or not successful")

        dest = Path(snapshot.dest_path)

        if restore_db and snapshot.db_dump_path:
            dump = Path(snapshot.db_dump_path)
            if not dump.exists():
                raise FileNotFoundError(f"DB dump missing: {dump}")
            # Verify hash before restore
            if snapshot.verify_hash:
                actual = self._sha256_file(dump)
                if actual != snapshot.verify_hash:
                    raise ValueError("pg_dump integrity check failed — hash mismatch")
            self._pg_restore(dump)

        if restore_files:
            self._rsync_restore(dest, WORKDIR)

        snapshot.status = "restored"
        self.db.commit()
        logger.info("Restore complete from snapshot: %s", snapshot_name)
        return True

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------
    def _pg_dump(self, out_path: Path) -> None:
        cmd = [
            "pg_dump",
            "--format=custom",
            "--compress=9",
            f"--file={out_path}",
            DB_URL,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump error: {result.stderr}")

    def _pg_restore(self, dump_path: Path) -> None:
        cmd = [
            "pg_restore",
            "--clean",
            "--if-exists",
            f"--dbname={DB_URL}",
            str(dump_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pg_restore error: {result.stderr}")

    def _rsync_workdir(self, dest: Path,
                       backup_type: str) -> dict:
        flags = ["-az", "--delete", "--stats"]
        if backup_type == "incremental":
            # Link to last successful backup for hard-link dedup
            last = self._last_successful_snapshot()
            if last:
                link_dest = Path(last.dest_path) / "workdir"
                if link_dest.exists():
                    flags.append(f"--link-dest={link_dest}")
        target_dir = dest / "workdir"
        target_dir.mkdir(exist_ok=True)
        cmd = ["rsync"] + flags + [str(WORKDIR) + "/", str(target_dir) + "/"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        stats = self._parse_rsync_stats(result.stdout)
        stats["exit_code"] = result.returncode
        return stats

    def _rsync_restore(self, src_dest: Path, target: Path) -> None:
        src = src_dest / "workdir"
        cmd = ["rsync", "-az", "--delete", str(src) + "/", str(target) + "/"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in (0, 24):
            raise RuntimeError(f"Restore rsync failed: {result.stderr}")

    def _rotate_old_snapshots(self) -> None:
        now = datetime.now(timezone.utc)
        expired = (
            self.db.query(BackupSnapshot)
            .filter(BackupSnapshot.expires_at <= now)
            .filter(BackupSnapshot.status == "success")
            .all()
        )
        for snap in expired:
            path = Path(snap.dest_path)
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
                logger.info("Rotated expired snapshot: %s", snap.snapshot_name)
            snap.status = "rotated"
        self.db.flush()

    def _last_successful_snapshot(self) -> BackupSnapshot:
        return (
            self.db.query(BackupSnapshot)
            .filter(BackupSnapshot.status == "success")
            .order_by(BackupSnapshot.completed_at.desc())
            .first()
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _parse_rsync_stats(stdout: str) -> dict:
        stats = {}
        for line in stdout.splitlines():
            if "Total transferred file size" in line:
                parts = line.split()
                try:
                    stats["bytes_transferred"] = int(parts[-2].replace(",", ""))
                except Exception:
                    pass
            if "Number of regular files transferred" in line:
                parts = line.split()
                try:
                    stats["files_transferred"] = int(parts[-1].replace(",", ""))
                except Exception:
                    pass
        return stats
