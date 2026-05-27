"""
IVGS v5 — RollbackService
===========================

Implements §14.3 Application Rollback Procedure:
  - create_rollback_point(version_tag) — called by deploy-node.sh before deployment
  - rollback_to(rollback_point_id) — reverts migrations, restarts containers, restores configs
  - Target: rollback in under 15 minutes
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text as sa_text

logger = logging.getLogger("ivgs.rollback")

ROLLBACK_STORAGE_DIR = Path("/ivgs/rollback_points")


class RollbackPoint:
    def __init__(
        self,
        id: str,
        version_tag: str,
        alembic_revision: str,
        docker_image_tags: dict[str, str],
        config_snapshot_path: str,
        created_at: datetime,
    ):
        self.id = id
        self.version_tag = version_tag
        self.alembic_revision = alembic_revision
        self.docker_image_tags = docker_image_tags
        self.config_snapshot_path = config_snapshot_path
        self.created_at = created_at


class RollbackService:
    """Manages application rollback points and rollback operations."""

    def __init__(self):
        ROLLBACK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    async def create_rollback_point(self, version_tag: str, db=None) -> RollbackPoint:
        """
        Create a rollback point before deployment.
        Called automatically by deploy-node.sh.
        """
        rollback_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # 1. Capture current Alembic revision
        alembic_revision = await self._get_current_alembic_revision(db)

        # 2. Capture current Docker image tags
        docker_tags = await self._get_current_docker_tags()

        # 3. Snapshot configuration files
        snapshot_dir = ROLLBACK_STORAGE_DIR / rollback_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        config_snapshot_path = str(snapshot_dir / "config")
        await self._snapshot_configs(config_snapshot_path)

        # 4. Save rollback point metadata
        point = RollbackPoint(
            id=rollback_id,
            version_tag=version_tag,
            alembic_revision=alembic_revision,
            docker_image_tags=docker_tags,
            config_snapshot_path=config_snapshot_path,
            created_at=now,
        )

        metadata_path = snapshot_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(
                {
                    "id": point.id,
                    "version_tag": point.version_tag,
                    "alembic_revision": point.alembic_revision,
                    "docker_image_tags": point.docker_image_tags,
                    "config_snapshot_path": point.config_snapshot_path,
                    "created_at": point.created_at.isoformat(),
                },
                f,
                indent=2,
            )

        # 5. Store in database
        if db:
            await db.execute(
                sa_text(
                    "INSERT INTO rollback_points "
                    "(id, version_tag, alembic_revision, docker_image_tags, "
                    "config_snapshot_path, created_at) "
                    "VALUES (:id, :tag, :rev, :tags, :path, :created)"
                ),
                {
                    "id": rollback_id,
                    "tag": version_tag,
                    "rev": alembic_revision,
                    "tags": json.dumps(docker_tags),
                    "path": config_snapshot_path,
                    "created": now,
                },
            )
            await db.commit()

        logger.info(
            f"Rollback point created: {rollback_id} (version={version_tag}, "
            f"alembic={alembic_revision})"
        )
        return point

    async def rollback_to(self, rollback_point_id: str, db=None) -> dict:
        """
        Rollback to a specific rollback point.
        1. Revert Alembic migrations
        2. Restart containers with previous image tags
        3. Restore config files
        """
        # Load rollback point metadata
        metadata_path = ROLLBACK_STORAGE_DIR / rollback_point_id / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Rollback point {rollback_point_id} not found"
            )

        with open(metadata_path) as f:
            metadata = json.load(f)

        results = {"steps": [], "success": True, "rollback_point_id": rollback_point_id}

        try:
            # Step 1: Revert Alembic migrations
            target_revision = metadata["alembic_revision"]
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", "docker-compose.node01.yml",
                "run", "--rm", "api", "alembic", "downgrade", target_revision,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            results["steps"].append({
                "step": "alembic_downgrade",
                "target": target_revision,
                "success": proc.returncode == 0,
                "output": stdout.decode()[:500],
            })

            # Step 2: Restore config files
            config_path = metadata["config_snapshot_path"]
            if os.path.exists(config_path):
                shutil.copytree(
                    config_path, "/ivgs/ivgs-api/config", dirs_exist_ok=True
                )
                results["steps"].append({
                    "step": "config_restore",
                    "success": True,
                })

            # Step 3: Restart containers with previous image tags
            docker_tags = metadata["docker_image_tags"]
            for service, tag in docker_tags.items():
                env_var = f"{service.upper().replace('-', '_')}_TAG"
                os.environ[env_var] = tag

            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", "docker-compose.node01.yml",
                "up", "-d", "--pull", "always",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            results["steps"].append({
                "step": "container_restart",
                "success": proc.returncode == 0,
                "image_tags": docker_tags,
            })

        except Exception as exc:
            results["success"] = False
            results["error"] = str(exc)
            logger.exception(f"Rollback failed: {exc}")

        return results

    async def list_rollback_points(self) -> list[dict]:
        """List all available rollback points."""
        points = []
        for item in sorted(ROLLBACK_STORAGE_DIR.iterdir(), reverse=True):
            metadata_path = item / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path) as f:
                    points.append(json.load(f))
        return points

    async def _get_current_alembic_revision(self, db=None) -> str:
        if db:
            row = (
                await db.execute(sa_text("SELECT version_num FROM alembic_version LIMIT 1"))
            ).fetchone()
            return row.version_num if row else "head"

        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", "docker-compose.node01.yml",
            "run", "--rm", "api", "alembic", "current",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip().split(" ")[0] or "head"

    async def _get_current_docker_tags(self) -> dict[str, str]:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", "docker-compose.node01.yml",
            "images", "--format", "json",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        tags = {}
        for line in stdout.decode().strip().split("\n"):
            if line.strip():
                try:
                    data = json.loads(line)
                    tags[data.get("Service", "")] = data.get("Tag", "latest")
                except json.JSONDecodeError:
                    pass
        return tags

    async def _snapshot_configs(self, target_dir: str) -> None:
        os.makedirs(target_dir, exist_ok=True)
        config_source = Path("/ivgs/ivgs-api/config")
        if config_source.exists():
            shutil.copytree(str(config_source), target_dir, dirs_exist_ok=True)
        env_file = Path("/ivgs/.env")
        if env_file.exists():
            shutil.copy2(str(env_file), os.path.join(target_dir, ".env"))
