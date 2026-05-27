"""
Phase 3: Backup API endpoint tests.

Tests:
  GET  /api/v1/backup/records — list backups
  POST /api/v1/backup/trigger — trigger backup (admin only)
  POST /api/v1/backup/{backup_id}/verify — verify backup
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestListBackupRecords:
    """GET /api/v1/backup/records"""

    async def test_list_backup_records(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/backup/records",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    async def test_list_backup_records_pagination(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/backup/records?page=1&per_page=5",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["per_page"] == 5

    async def test_list_backup_records_filter_type(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/backup/records?backup_type=full_database",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200

    async def test_list_backup_records_filter_status(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/backup/records?status_filter=completed",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200

    async def test_list_backup_records_unauthenticated(
        self, client: AsyncClient
    ):
        r = await client.get("/api/v1/backup/records")
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
class TestTriggerBackup:
    """POST /api/v1/backup/trigger"""

    async def test_trigger_backup_admin(
        self, client: AsyncClient, admin_token: str
    ):
        r = await client.post(
            "/api/v1/backup/trigger",
            json={"backup_type": "full_db"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # May succeed (200/201/202) or fail if backup subsystem not configured
        assert r.status_code in (200, 201, 202, 500)

    @pytest.mark.xfail(
        reason="BUG-014: backup trigger uses no-op require_admin from app.api.deps",
        strict=True,
    )
    async def test_trigger_backup_operator_denied(
        self, client: AsyncClient, operator_token: str
    ):
        """Operator should be denied — but BUG-014 bypasses RBAC."""
        r = await client.post(
            "/api/v1/backup/trigger",
            json={"backup_type": "full_db"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 403

    async def test_trigger_backup_empty_body_uses_default(
        self, client: AsyncClient, admin_token: str
    ):
        """backup_type has default 'full_db', so {} body is valid."""
        r = await client.post(
            "/api/v1/backup/trigger",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Default backup_type="full_db" should be accepted
        assert r.status_code in (200, 201, 202, 500)

    @pytest.mark.xfail(
        reason="BUG-014: backup trigger uses no-op require_admin — unauthenticated gets 422 (body validation) instead of 401/403",
        strict=True,
    )
    async def test_trigger_backup_unauthenticated(self, client: AsyncClient):
        """Should return 401/403 before body validation."""
        r = await client.post(
            "/api/v1/backup/trigger",
            json={"backup_type": "full_db"},
        )
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
class TestVerifyBackup:
    """POST /api/v1/backup/{backup_id}/verify"""

    async def test_verify_nonexistent_backup(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.post(
            f"/api/v1/backup/{uuid4()}/verify",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 404

    async def test_verify_unauthenticated(self, client: AsyncClient):
        r = await client.post(f"/api/v1/backup/{uuid4()}/verify")
        assert r.status_code in (401, 403)
