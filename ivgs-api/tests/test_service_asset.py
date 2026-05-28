"""
Phase 4 Gap 1: Asset Service Tests

Tests AssetService: list_assets, get_asset, upload_asset, download_asset, delete_asset.
DB+EXTERNAL service — SeaweedFS is mocked by conftest.py autouse fixture.
"""
import uuid

import pytest
from sqlalchemy import text

from app.services.asset_service import AssetService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project_with_user(db):
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, username, password_hash, role) VALUES (:uid, :u, 'x', 'admin')"),
        {"uid": str(uid), "u": f"auser-{uuid.uuid4().hex[:8]}"},
    )
    await db.execute(
        text("INSERT INTO projects (id, name, created_by) VALUES (:pid, :n, :uid)"),
        {"pid": str(pid), "n": f"Asset-Proj-{uuid.uuid4().hex[:6]}", "uid": str(uid)},
    )
    await db.commit()
    return pid


async def _upload_test_asset(svc, project_id, content=b"test image data", asset_type="image"):
    return await svc.upload_asset(
        project_id=project_id,
        file_content=content,
        filename="test.png",
        content_type="image/png",
        asset_type=asset_type,
    )


# ===========================================================================
# Upload Tests
# ===========================================================================

class TestUploadAsset:
    async def test_upload_success(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        asset = await _upload_test_asset(svc, pid)

        assert asset.project_id == pid
        assert asset.asset_type == "image"
        assert asset.file_size_bytes == len(b"test image data")
        assert asset.content_hash is not None
        assert asset.storage_tier == "hot"

    async def test_upload_deduplication(self, db_session):
        """Same content hash in same project should increment ref count."""
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        content = b"dedup test content"
        a1 = await _upload_test_asset(svc, pid, content=content)
        a2 = await _upload_test_asset(svc, pid, content=content)

        assert a1.id == a2.id  # Same asset returned
        assert a2.reference_count == 2

    async def test_upload_invalid_asset_type_raises(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        with pytest.raises(ValueError, match="Invalid asset_type"):
            await svc.upload_asset(
                project_id=pid,
                file_content=b"data",
                filename="test.bin",
                content_type="application/octet-stream",
                asset_type="invalid_type",
            )

    async def test_upload_file_too_large_raises(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        # Image max is 50MB
        big_content = b"x" * (51 * 1024 * 1024)
        with pytest.raises(ValueError, match="File too large"):
            await svc.upload_asset(
                project_id=pid,
                file_content=big_content,
                filename="huge.png",
                content_type="image/png",
                asset_type="image",
            )

    async def test_upload_with_scene_and_language(self, db_session):
        pid = await _create_project_with_user(db_session)
        # Create a scene
        sid = uuid.uuid4()
        await db_session.execute(
            text(
                "INSERT INTO storyboard_scenes (id, project_id, scene_index) "
                "VALUES (:sid, :pid, 1)"
            ),
            {"sid": str(sid), "pid": str(pid)},
        )
        await db_session.commit()

        svc = AssetService(db_session)
        asset = await svc.upload_asset(
            project_id=pid,
            file_content=b"scene asset",
            filename="scene.png",
            content_type="image/png",
            asset_type="image",
            scene_id=sid,
            language_code="en-US",
        )
        assert asset.scene_id == sid
        assert asset.language_code == "en-US"


# ===========================================================================
# List Tests
# ===========================================================================

class TestListAssets:
    async def test_list_basic(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        await _upload_test_asset(svc, pid, content=b"list1")
        await _upload_test_asset(svc, pid, content=b"list2")

        assets, total = await svc.list_assets(pid)
        assert total >= 2
        assert len(assets) >= 2

    async def test_list_filter_asset_type(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        await _upload_test_asset(svc, pid, content=b"img", asset_type="image")

        assets, _ = await svc.list_assets(pid, asset_type="image")
        assert all(a.asset_type == "image" for a in assets)

    async def test_list_empty_project(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        assets, total = await svc.list_assets(pid)
        assert total == 0
        assert assets == []

    async def test_list_pagination(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        for i in range(3):
            await _upload_test_asset(svc, pid, content=f"pg{i}".encode())

        assets, total = await svc.list_assets(pid, page=1, per_page=2)
        assert len(assets) <= 2
        assert total >= 3


# ===========================================================================
# Get / Download Tests
# ===========================================================================

class TestGetAsset:
    async def test_get_existing(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        asset = await _upload_test_asset(svc, pid)

        result = await svc.get_asset(asset.id)
        assert result is not None
        assert result.id == asset.id

    async def test_get_nonexistent(self, db_session):
        svc = AssetService(db_session)
        result = await svc.get_asset(uuid.uuid4())
        assert result is None


class TestDownloadAsset:
    async def test_download_success(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        asset = await _upload_test_asset(svc, pid, content=b"download me")

        result = await svc.download_asset(asset.id)
        assert result is not None
        content, mime, filename = result
        assert content == b"download me"
        assert mime == "image/png"

    async def test_download_nonexistent(self, db_session):
        svc = AssetService(db_session)
        result = await svc.download_asset(uuid.uuid4())
        assert result is None


# ===========================================================================
# Delete Tests
# ===========================================================================

class TestDeleteAsset:
    async def test_delete_single_ref(self, db_session):
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        asset = await _upload_test_asset(svc, pid)

        deleted = await svc.delete_asset(asset.id)
        assert deleted is True

        # Should be gone
        result = await svc.get_asset(asset.id)
        assert result is None

    async def test_delete_decrements_refcount(self, db_session):
        """Deleting deduped asset decrements ref count instead of removing."""
        pid = await _create_project_with_user(db_session)
        svc = AssetService(db_session)
        content = b"shared content"
        a1 = await _upload_test_asset(svc, pid, content=content)
        a2 = await _upload_test_asset(svc, pid, content=content)
        assert a2.reference_count == 2

        deleted = await svc.delete_asset(a2.id)
        assert deleted is True

        # Still exists but ref count decremented
        remaining = await svc.get_asset(a2.id)
        assert remaining is not None
        assert remaining.reference_count == 1

    async def test_delete_nonexistent(self, db_session):
        svc = AssetService(db_session)
        deleted = await svc.delete_asset(uuid.uuid4())
        assert deleted is False
