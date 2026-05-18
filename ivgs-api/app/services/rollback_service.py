"""
RollbackService — deployment snapshot and state revert pipeline.
Stores rollback points in the DB; actual revert uses Alembic downgrade
and git-based config restore. No cloud API calls.
"""
import logging
import subprocess
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.config import settings

logger = logging.getLogger(__name__)


class RollbackService:

    def __init__(self, db: Session):
        self.db = db

    def create_rollback_point(self, label: str,
                               migration_revision: str,
                               deployed_by: str = "ci") -> dict:
        now = datetime.now(timezone.utc)
        point = {
            "label": label,
            "migration_revision": migration_revision,
            "git_sha": self._get_git_sha(),
            "created_at": now.isoformat(),
            "created_by": deployed_by,
        }
        from sqlalchemy import text
        self.db.execute(
            text("""
                INSERT INTO rollback_points
                    (label, migration_revision, git_sha, created_at, created_by)
                VALUES
                    (:label, :rev, :sha, :ts, :by)
            """),
            {"label": label, "rev": migration_revision,
             "sha": point["git_sha"], "ts": now, "by": deployed_by},
        )
        self.db.commit()
        logger.info("Rollback point created: %s @ %s", label, point["git_sha"])
        return point

    def rollback_to(self, label: str) -> bool:
        from sqlalchemy import text
        row = self.db.execute(
            text("SELECT * FROM rollback_points WHERE label = :label "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"label": label}
        ).fetchone()
        if not row:
            raise ValueError(f"Rollback point {label!r} not found")

        revision = row["migration_revision"]
        git_sha  = row["git_sha"]
        logger.info("Rolling back to: label=%s rev=%s sha=%s",
                    label, revision, git_sha)

        # Alembic downgrade
        result = subprocess.run(
            ["alembic", "downgrade", revision],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Alembic downgrade failed: {result.stderr}")

        # Git checkout (config files only — no code rollback in prod)
        subprocess.run(
            ["git", "checkout", git_sha, "--", "config/"],
            capture_output=True,
        )
        logger.info("Rollback complete to label=%s", label)
        return True

    @staticmethod
    def _get_git_sha() -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True
            )
            return r.stdout.strip()
        except Exception:
            return "unknown"
