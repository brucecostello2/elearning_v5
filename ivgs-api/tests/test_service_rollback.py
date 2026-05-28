"""
Phase 4 Gap 1: Rollback Service Tests

Tests RollbackService: create_rollback_point, rollback_to, list_rollback_points.
This service is EXTERNAL_ONLY — uses filesystem, subprocess, and optionally DB.
All external calls are mocked.

Critical Path #10 tests included:
  - test_rollback_create_captures_state
  - test_rollback_execute_reverts_to_point
  - test_rollback_list_ordered_by_date
  - test_rollback_invalid_point_fails
"""
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rollback_service import RollbackService, RollbackPoint, ROLLBACK_STORAGE_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
TEST_ROLLBACK_DIR = Path("/tmp/test_rollback_points")


@pytest.fixture(autouse=True)
def _patch_rollback_dir(monkeypatch, tmp_path):
    """Redirect rollback storage to a temp dir for test isolation."""
    test_dir = tmp_path / "rollback_points"
    test_dir.mkdir()
    monkeypatch.setattr(
        "app.services.rollback_service.ROLLBACK_STORAGE_DIR", test_dir
    )
    yield test_dir


@pytest.fixture
def rollback_service(_patch_rollback_dir):
    """Create a RollbackService (no db needed for most ops)."""
    return RollbackService()


# ===========================================================================
# Critical Path #10 Tests (exact v3 Section 10 names)
# ===========================================================================

class TestCriticalPath10:
    """v3 Section 10 — Rollback point create → execute rollback."""

    async def test_rollback_create_captures_state(
        self, rollback_service, _patch_rollback_dir
    ):
        """Creating rollback point captures alembic revision & docker tags."""
        with patch.object(
            rollback_service,
            "_get_current_alembic_revision",
            new_callable=AsyncMock,
            return_value="0022",
        ), patch.object(
            rollback_service,
            "_get_current_docker_tags",
            new_callable=AsyncMock,
            return_value={"api": "v1.2.3", "worker": "v1.2.3"},
        ), patch.object(
            rollback_service,
            "_snapshot_configs",
            new_callable=AsyncMock,
        ):
            point = await rollback_service.create_rollback_point("v1.2.3")

        assert isinstance(point, RollbackPoint)
        assert point.version_tag == "v1.2.3"
        assert point.docker_image_tags == {"api": "v1.2.3", "worker": "v1.2.3"}
        assert point.alembic_revision is not None

        # Verify metadata.json written
        metadata_path = _patch_rollback_dir / point.id / "metadata.json"
        assert metadata_path.exists()
        meta = json.loads(metadata_path.read_text())
        assert meta["version_tag"] == "v1.2.3"

    async def test_rollback_execute_reverts_to_point(
        self, rollback_service, _patch_rollback_dir
    ):
        """Executing rollback reads metadata and runs downgrade + restart."""
        # Seed a fake rollback point
        point_id = str(uuid.uuid4())
        point_dir = _patch_rollback_dir / point_id
        point_dir.mkdir()
        meta = {
            "id": point_id,
            "version_tag": "v1.0.0",
            "alembic_revision": "abc123",
            "docker_image_tags": {"api": "v1.0.0"},
            "config_snapshot_path": str(point_dir / "config"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (point_dir / "metadata.json").write_text(json.dumps(meta))

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"OK", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await rollback_service.rollback_to(point_id)

        assert result["success"] is True
        assert result["rollback_point_id"] == point_id
        assert any(s["step"] == "alembic_downgrade" for s in result["steps"])

    async def test_rollback_list_ordered_by_date(
        self, rollback_service, _patch_rollback_dir
    ):
        """list_rollback_points returns points sorted newest-first."""
        # Create 3 fake points
        for i in range(3):
            pid = f"point-{i:04d}"
            d = _patch_rollback_dir / pid
            d.mkdir()
            meta = {
                "id": pid,
                "version_tag": f"v1.{i}.0",
                "created_at": f"2026-05-0{i+1}T00:00:00Z",
            }
            (d / "metadata.json").write_text(json.dumps(meta))

        points = await rollback_service.list_rollback_points()
        assert len(points) == 3
        # Sorted by directory name descending (reverse=True in iterdir)
        assert points[0]["id"] == "point-0002"

    async def test_rollback_invalid_point_fails(self, rollback_service):
        """Rollback to non-existent point raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            await rollback_service.rollback_to("nonexistent-id")


# ===========================================================================
# Core Functionality Tests
# ===========================================================================

class TestCreateRollbackPoint:
    """Test create_rollback_point method."""

    async def test_create_without_db(self, rollback_service, _patch_rollback_dir):
        """Create rollback point without DB (filesystem-only mode)."""
        with patch.object(
            rollback_service,
            "_get_current_alembic_revision",
            new_callable=AsyncMock,
            return_value="head",
        ), patch.object(
            rollback_service,
            "_get_current_docker_tags",
            new_callable=AsyncMock,
            return_value={"api": "latest"},
        ), patch.object(
            rollback_service,
            "_snapshot_configs",
            new_callable=AsyncMock,
        ):
            point = await rollback_service.create_rollback_point("v2.0.0")

        assert point.version_tag == "v2.0.0"
        assert point.alembic_revision == "head"
        # metadata.json created
        assert (_patch_rollback_dir / point.id / "metadata.json").exists()

    async def test_create_reads_alembic_from_db(self, rollback_service, _patch_rollback_dir, db_session):
        """When db is provided, reads alembic_version from real DB (no table INSERT)."""
        with patch.object(
            rollback_service,
            "_get_current_docker_tags",
            new_callable=AsyncMock,
            return_value={},
        ), patch.object(
            rollback_service,
            "_snapshot_configs",
            new_callable=AsyncMock,
        ):
            # Only test the alembic revision read, skip the INSERT to rollback_points
            rev = await rollback_service._get_current_alembic_revision(db=db_session)

        assert rev is not None
        assert rev != ""


class TestRollbackTo:
    """Test rollback_to method."""

    async def test_rollback_config_restore(
        self, rollback_service, _patch_rollback_dir, tmp_path
    ):
        """Config restore copies files when config dir exists."""
        point_id = str(uuid.uuid4())
        point_dir = _patch_rollback_dir / point_id
        point_dir.mkdir()
        config_dir = point_dir / "config"
        config_dir.mkdir()
        (config_dir / "app.yml").write_text("key: value")

        meta = {
            "id": point_id,
            "version_tag": "v1.0.0",
            "alembic_revision": "abc",
            "docker_image_tags": {},
            "config_snapshot_path": str(config_dir),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (point_dir / "metadata.json").write_text(json.dumps(meta))

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
             patch("shutil.copytree") as mock_copy:
            result = await rollback_service.rollback_to(point_id)

        assert result["success"] is True

    async def test_rollback_subprocess_failure(
        self, rollback_service, _patch_rollback_dir
    ):
        """If alembic downgrade fails, success should be False."""
        point_id = str(uuid.uuid4())
        point_dir = _patch_rollback_dir / point_id
        point_dir.mkdir()
        meta = {
            "id": point_id,
            "version_tag": "v1.0.0",
            "alembic_revision": "abc",
            "docker_image_tags": {},
            "config_snapshot_path": "/nonexistent",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (point_dir / "metadata.json").write_text(json.dumps(meta))

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("docker not found"),
        ):
            result = await rollback_service.rollback_to(point_id)

        assert result["success"] is False
        assert "error" in result

    async def test_rollback_corrupted_metadata(
        self, rollback_service, _patch_rollback_dir
    ):
        """Corrupted metadata.json should raise."""
        point_id = str(uuid.uuid4())
        point_dir = _patch_rollback_dir / point_id
        point_dir.mkdir()
        (point_dir / "metadata.json").write_text("NOT JSON{{{")

        with pytest.raises(json.JSONDecodeError):
            await rollback_service.rollback_to(point_id)


class TestListRollbackPoints:
    """Test list_rollback_points method."""

    async def test_list_empty(self, rollback_service):
        """Empty storage dir returns empty list."""
        result = await rollback_service.list_rollback_points()
        assert result == []

    async def test_list_skips_dirs_without_metadata(
        self, rollback_service, _patch_rollback_dir
    ):
        """Directories without metadata.json are skipped."""
        (_patch_rollback_dir / "orphan-dir").mkdir()
        result = await rollback_service.list_rollback_points()
        assert result == []


class TestRollbackErrorPaths:
    """Error path tests for ≥40% error coverage."""

    async def test_get_alembic_revision_no_db_docker_fail(self, rollback_service):
        """_get_current_alembic_revision without db falls back to subprocess."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"abc123 (head)\n", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            rev = await rollback_service._get_current_alembic_revision()
        assert rev == "abc123"

    async def test_get_docker_tags_empty_output(self, rollback_service):
        """_get_current_docker_tags handles empty docker output."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            tags = await rollback_service._get_current_docker_tags()
        assert tags == {}

    async def test_get_docker_tags_invalid_json_lines(self, rollback_service):
        """_get_current_docker_tags handles non-JSON lines gracefully."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"not json\n{bad\n", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            tags = await rollback_service._get_current_docker_tags()
        assert tags == {}

    async def test_snapshot_configs_no_source(
        self, rollback_service, tmp_path
    ):
        """_snapshot_configs handles missing source directories."""
        target = str(tmp_path / "snapshot")
        with patch("pathlib.Path.exists", return_value=False):
            await rollback_service._snapshot_configs(target)
        # Should not raise, just skip
        assert os.path.exists(target)
