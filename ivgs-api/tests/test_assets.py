"""
Asset endpoint tests: upload, download, metadata, deduplication.
"""
import io
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAssetUpload:
    """Test asset upload to SeaweedFS."""

    async def test_upload_image_asset(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test uploading an image asset."""
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Minimal PNG-like content
        response = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("test.png", io.BytesIO(content), "image/png")},
            data={"asset_type": "image"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["asset_type"] == "image"
        assert data["mime_type"] == "image/png"
        assert data["content_hash"] is not None

    async def test_upload_invalid_asset_type(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test that invalid asset types are rejected."""
        response = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("test.dat", io.BytesIO(b"data"), "application/octet-stream")},
            data={"asset_type": "invalid_type"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 400

    async def test_deduplication(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test SHA-256 deduplication — same content not re-uploaded."""
        content = b"identical content for dedup test"
        # Upload first
        resp1 = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("file1.txt", io.BytesIO(content), "text/plain")},
            data={"asset_type": "document"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp1.status_code == 201
        # Upload same content again
        resp2 = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("file2.txt", io.BytesIO(content), "text/plain")},
            data={"asset_type": "document"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp2.status_code == 201
        # Should reference the same asset (dedup)
        assert resp1.json()["content_hash"] == resp2.json()["content_hash"]


@pytest.mark.asyncio
class TestAssetRetrieval:
    """Test asset metadata and download."""

    async def test_list_assets(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test listing project assets."""
        response = await client.get(
            f"/api/v1/projects/{project_id}/assets",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert "data" in response.json()

    async def test_list_assets_with_filters(self, client: AsyncClient, operator_token: str, project_id: str):
        """Test filtering assets by type."""
        response = await client.get(
            f"/api/v1/projects/{project_id}/assets?asset_type=image",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200

    async def test_get_asset_metadata(self, client: AsyncClient, operator_token: str, asset_id: str):
        """Test getting asset metadata."""
        response = await client.get(
            f"/api/v1/assets/{asset_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "storage_tier" in data
        assert "content_hash" in data

    async def test_get_nonexistent_asset(self, client: AsyncClient, operator_token: str):
        """Test 404 for non-existent asset."""
        response = await client.get(
            f"/api/v1/assets/{uuid4()}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestAssetDelete:
    """Test asset deletion."""

    async def test_delete_asset(self, client: AsyncClient, operator_token: str, asset_id: str):
        """Test deleting an asset."""
        response = await client.delete(
            f"/api/v1/assets/{asset_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 204

    async def test_delete_nonexistent_asset(self, client: AsyncClient, operator_token: str):
        """Test 404 when deleting non-existent asset."""
        response = await client.delete(
            f"/api/v1/assets/{uuid4()}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404
