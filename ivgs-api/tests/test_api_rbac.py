"""
Phase 3 — RBAC Enforcement Tests.

Verifies that admin-only and operator-or-admin endpoints correctly reject
lower-privileged roles with 403 PERMISSION_DENIED.

Admin-only endpoints (viewer AND operator must get 403):
  - POST/GET/PUT/DELETE /api/v1/users
  - POST /api/v1/backup/trigger (BUG-014: bypassed — xfail)
  - POST/PUT /api/v1/retention/policies
  - POST/PUT /api/v1/gpu/nodes, POST /api/v1/gpu/nodes/{id}/drain
  - POST /api/v1/quality/{score_id}/approve|reject
  - PUT /api/v1/quotas/{entity_type}/{entity_id}
  - POST /api/v1/rollback/{job_id}

Operator-or-admin endpoints (viewer must get 403):
  - POST /api/v1/projects
  - POST /api/v1/jobs/{id}/cancel
  - POST /api/v1/projects/{id}/languages
  - POST /api/v1/projects/{id}/assets/upload
"""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ── Helpers ───────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

FAKE_UUID = str(uuid.uuid4())


# ── Admin-only: Users CRUD ────────────────────────────────────────────

class TestRbacUsers:
    """Viewer and operator must be denied on /api/v1/users."""

    async def test_viewer_cannot_list_users(self, client: AsyncClient, viewer_token: str):
        r = await client.get("/api/v1/users", headers=_auth(viewer_token))
        assert r.status_code == 403

    async def test_operator_cannot_list_users(self, client: AsyncClient, operator_token: str):
        r = await client.get("/api/v1/users", headers=_auth(operator_token))
        assert r.status_code == 403

    async def test_viewer_cannot_create_user(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            "/api/v1/users",
            json={"username": "rbac_test", "password": "Str0ngP@ss1", "role": "viewer"},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    async def test_operator_cannot_delete_user(self, client: AsyncClient, operator_token: str):
        r = await client.delete(
            f"/api/v1/users/{FAKE_UUID}", headers=_auth(operator_token)
        )
        assert r.status_code == 403


# ── Admin-only: Backup Trigger (BUG-014) ─────────────────────────────

class TestRbacBackup:
    @pytest.mark.xfail(
        reason="BUG-014: backup trigger uses no-op require_admin from app.api.deps",
        strict=True,
    )
    async def test_viewer_cannot_trigger_backup(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            "/api/v1/backup/trigger",
            json={"backup_type": "full_db"},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    @pytest.mark.xfail(
        reason="BUG-014: backup trigger uses no-op require_admin from app.api.deps",
        strict=True,
    )
    async def test_operator_cannot_trigger_backup(self, client: AsyncClient, operator_token: str):
        r = await client.post(
            "/api/v1/backup/trigger",
            json={"backup_type": "full_db"},
            headers=_auth(operator_token),
        )
        assert r.status_code == 403


# ── Admin-only: Retention Policies ────────────────────────────────────

class TestRbacRetention:
    async def test_viewer_cannot_create_policy(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            "/api/v1/retention/policies",
            json={"name": "rbac_test", "retention_days": 30},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    async def test_operator_cannot_create_policy(self, client: AsyncClient, operator_token: str):
        r = await client.post(
            "/api/v1/retention/policies",
            json={"name": "rbac_test", "retention_days": 30},
            headers=_auth(operator_token),
        )
        assert r.status_code == 403


# ── Admin-only: GPU Node Management ──────────────────────────────────

class TestRbacGpu:
    async def test_viewer_cannot_register_gpu(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            "/api/v1/gpu/nodes",
            json={"hostname": "rbac-node", "gpu_model": "A100", "vram_mb": 40960},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    async def test_operator_cannot_register_gpu(self, client: AsyncClient, operator_token: str):
        r = await client.post(
            "/api/v1/gpu/nodes",
            json={"hostname": "rbac-node", "gpu_model": "A100", "vram_mb": 40960},
            headers=_auth(operator_token),
        )
        assert r.status_code == 403

    async def test_operator_cannot_drain_gpu(self, client: AsyncClient, operator_token: str):
        r = await client.post(
            f"/api/v1/gpu/nodes/{FAKE_UUID}/drain", headers=_auth(operator_token)
        )
        assert r.status_code == 403


# ── Admin-only: Quality Approve/Reject ────────────────────────────────

class TestRbacQuality:
    """Quality approve/reject at /api/v1/quality/{score_id}/approve|reject."""

    async def test_viewer_cannot_approve(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            f"/api/v1/quality/{FAKE_UUID}/approve",
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    async def test_operator_cannot_reject(self, client: AsyncClient, operator_token: str):
        r = await client.post(
            f"/api/v1/quality/{FAKE_UUID}/reject",
            headers=_auth(operator_token),
        )
        assert r.status_code == 403


# ── Admin-only: Quotas ────────────────────────────────────────────────

class TestRbacQuotas:
    """Quotas at /api/v1/quotas/{entity_type}/{entity_id}.
    
    NOTE: BUG-015 — quotas also imports no-op require_admin from app.api.deps.
    """

    @pytest.mark.xfail(
        reason="BUG-015: quotas uses no-op require_admin from app.api.deps",
        strict=True,
    )
    async def test_operator_cannot_set_quota(self, client: AsyncClient, operator_token: str):
        r = await client.put(
            f"/api/v1/quotas/project/{FAKE_UUID}",
            json={"quota_bytes": 1073741824, "alert_threshold_pct": 80.0},
            headers=_auth(operator_token),
        )
        assert r.status_code == 403

    @pytest.mark.xfail(
        reason="BUG-015: quotas uses no-op require_admin from app.api.deps",
        strict=True,
    )
    async def test_viewer_cannot_set_quota(self, client: AsyncClient, viewer_token: str):
        r = await client.put(
            f"/api/v1/quotas/project/{FAKE_UUID}",
            json={"quota_bytes": 1073741824, "alert_threshold_pct": 80.0},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403


# ── Operator-or-Admin: Viewer denied ─────────────────────────────────

class TestRbacViewerDenied:
    """Viewer should be denied on operator-or-admin endpoints."""

    async def test_viewer_cannot_create_project(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            "/api/v1/projects",
            json={"name": "rbac_test_proj", "description": "test"},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    async def test_viewer_cannot_cancel_job(self, client: AsyncClient, viewer_token: str):
        r = await client.post(
            f"/api/v1/jobs/{FAKE_UUID}/cancel", headers=_auth(viewer_token)
        )
        assert r.status_code == 403

    async def test_viewer_cannot_create_language(self, client: AsyncClient, viewer_token: str, project_id: str):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages",
            json={"language_code": "fr-FR"},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    async def test_viewer_cannot_upload_asset(self, client: AsyncClient, viewer_token: str, project_id: str):
        r = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("test.mp4", b"fake", "video/mp4")},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403


# ── Unauthenticated access ───────────────────────────────────────────

class TestRbacUnauthenticated:
    """Requests without token should get 401 or 403."""

    async def test_no_token_projects(self, client: AsyncClient):
        r = await client.get("/api/v1/projects")
        assert r.status_code in (401, 403)

    async def test_no_token_users(self, client: AsyncClient):
        r = await client.get("/api/v1/users")
        assert r.status_code in (401, 403)

    async def test_invalid_token(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer totally.invalid.token"},
        )
        assert r.status_code in (401, 403)
