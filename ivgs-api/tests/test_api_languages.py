"""
Phase 3: Language Variant API endpoint tests.

Tests:
  GET  /api/v1/projects/{project_id}/languages — list variants
  POST /api/v1/projects/{project_id}/languages — create variant
  POST /api/v1/projects/{project_id}/languages/{variant_id}/retry — retry
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestListLanguageVariants:
    """GET /api/v1/projects/{project_id}/languages"""

    async def test_list_empty(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.get(
            f"/api/v1/projects/{project_id}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    async def test_list_after_create(
        self, client: AsyncClient, operator_token: str
    ):
        # Create project with target languages
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "Lang Test", "target_languages": ["es-ES", "fr-FR"]},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 201
        pid = resp.json()["id"]

        r = await client.get(
            f"/api/v1/projects/{pid}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        codes = {v["language_code"] for v in data}
        assert codes == {"es-ES", "fr-FR"}

    async def test_list_nonexistent_project(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            f"/api/v1/projects/{uuid4()}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code in (200, 404)

    async def test_list_unauthenticated(
        self, client: AsyncClient, project_id: str
    ):
        r = await client.get(f"/api/v1/projects/{project_id}/languages")
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
class TestCreateLanguageVariant:
    """POST /api/v1/projects/{project_id}/languages"""

    async def test_create_variant_success(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages",
            json={"language_code": "de-DE"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["language_code"] == "de-DE"
        assert data["state"] == "pending"
        assert "id" in data

    async def test_create_variant_with_prompt_override(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages",
            json={
                "language_code": "ja-JP",
                "translation_prompt_override": "Translate with formal Japanese tone",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["language_code"] == "ja-JP"

    async def test_create_variant_invalid_language(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages",
            json={"language_code": "xx-XX"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 422

    async def test_create_variant_missing_code(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages",
            json={},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 422

    async def test_create_variant_duplicate(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        body = {"language_code": "ar-SA"}
        headers = {"Authorization": f"Bearer {operator_token}"}
        r1 = await client.post(
            f"/api/v1/projects/{project_id}/languages", json=body, headers=headers
        )
        assert r1.status_code == 201

        r2 = await client.post(
            f"/api/v1/projects/{project_id}/languages", json=body, headers=headers
        )
        # Should reject duplicate — 400, 409, or 422
        assert r2.status_code in (400, 409, 422)

    async def test_create_variant_unauthenticated(
        self, client: AsyncClient, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages",
            json={"language_code": "fr-FR"},
        )
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
class TestRetryLanguageVariant:
    """POST /api/v1/projects/{project_id}/languages/{variant_id}/retry"""

    async def test_retry_nonexistent_variant(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages/{uuid4()}/retry",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 404

    async def test_retry_unauthenticated(
        self, client: AsyncClient, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/languages/{uuid4()}/retry"
        )
        assert r.status_code in (401, 403)
