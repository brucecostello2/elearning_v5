"""
Phase 3 — Cross-cutting Pagination Edge-Case Tests.

Validates pagination query-parameter handling across multiple list endpoints:
  • page/per_page defaults
  • Invalid page/per_page values (0, negative, beyond max)
  • Page beyond total → empty data
  • per_page=1 (minimum)
  • Response envelope correctness (total, pages, has_more)
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ── Helper ────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── /api/v1/projects pagination ──────────────────────────────────────

class TestProjectsPagination:
    """Pagination edge cases on GET /api/v1/projects."""

    async def test_default_pagination(self, client: AsyncClient, operator_token: str):
        """Default page=1, per_page=50 returns valid envelope."""
        r = await client.get("/api/v1/projects", headers=_auth(operator_token))
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["per_page"] == 50
        assert isinstance(body["data"], list)
        assert "total" in body
        assert "pages" in body
        assert "has_more" in body

    async def test_page_zero_rejected(self, client: AsyncClient, operator_token: str):
        """page=0 should be rejected (ge=1 constraint)."""
        r = await client.get(
            "/api/v1/projects", params={"page": 0}, headers=_auth(operator_token)
        )
        assert r.status_code == 422

    async def test_per_page_zero_rejected(self, client: AsyncClient, operator_token: str):
        """per_page=0 should be rejected (ge=1 constraint)."""
        r = await client.get(
            "/api/v1/projects", params={"per_page": 0}, headers=_auth(operator_token)
        )
        assert r.status_code == 422

    async def test_per_page_exceeds_max(self, client: AsyncClient, operator_token: str):
        """per_page=101 should be rejected (le=100 constraint)."""
        r = await client.get(
            "/api/v1/projects", params={"per_page": 101}, headers=_auth(operator_token)
        )
        assert r.status_code == 422

    async def test_negative_page(self, client: AsyncClient, operator_token: str):
        """Negative page number rejected."""
        r = await client.get(
            "/api/v1/projects", params={"page": -1}, headers=_auth(operator_token)
        )
        assert r.status_code == 422

    async def test_page_beyond_total(self, client: AsyncClient, operator_token: str):
        """Requesting page far beyond total returns empty data list."""
        r = await client.get(
            "/api/v1/projects",
            params={"page": 99999},
            headers=_auth(operator_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["has_more"] is False

    async def test_per_page_one(self, client: AsyncClient, operator_token: str, project_id: str):
        """per_page=1 returns at most 1 record."""
        r = await client.get(
            "/api/v1/projects", params={"per_page": 1}, headers=_auth(operator_token)
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) <= 1
        assert body["per_page"] == 1

    async def test_envelope_math(self, client: AsyncClient, operator_token: str, project_id: str):
        """pages = ceil(total / per_page); has_more correct."""
        r = await client.get(
            "/api/v1/projects", params={"per_page": 1}, headers=_auth(operator_token)
        )
        body = r.json()
        total = body["total"]
        assert body["pages"] == total  # ceil(total/1) == total
        if total > 1:
            assert body["has_more"] is True
        else:
            assert body["has_more"] is False


# ── /api/v1/users pagination (admin-only) ────────────────────────────

class TestUsersPagination:
    """Pagination on GET /api/v1/users (admin required)."""

    async def test_default_envelope(self, client: AsyncClient, admin_token: str):
        r = await client.get("/api/v1/users", headers=_auth(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "total" in body

    async def test_per_page_exceeds_max(self, client: AsyncClient, admin_token: str):
        r = await client.get(
            "/api/v1/users", params={"per_page": 101}, headers=_auth(admin_token)
        )
        assert r.status_code == 422

    async def test_page_zero(self, client: AsyncClient, admin_token: str):
        r = await client.get(
            "/api/v1/users", params={"page": 0}, headers=_auth(admin_token)
        )
        assert r.status_code == 422


# ── /api/v1/projects/{id}/jobs pagination ─────────────────────────────

class TestJobsPagination:
    """Pagination on jobs list endpoint."""

    async def test_page_beyond_total(self, client: AsyncClient, operator_token: str, project_id: str):
        r = await client.get(
            f"/api/v1/projects/{project_id}/jobs",
            params={"page": 99999},
            headers=_auth(operator_token),
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    async def test_per_page_zero(self, client: AsyncClient, operator_token: str, project_id: str):
        r = await client.get(
            f"/api/v1/projects/{project_id}/jobs",
            params={"per_page": 0},
            headers=_auth(operator_token),
        )
        assert r.status_code == 422


# ── /api/v1/gpu/nodes pagination ──────────────────────────────────────

class TestGpuNodesPagination:
    """Pagination on GPU nodes list."""

    async def test_default(self, client: AsyncClient, admin_token: str):
        r = await client.get("/api/v1/gpu/nodes", headers=_auth(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["page"] == 1

    async def test_invalid_per_page(self, client: AsyncClient, admin_token: str):
        r = await client.get(
            "/api/v1/gpu/nodes", params={"per_page": 200}, headers=_auth(admin_token)
        )
        assert r.status_code == 422
