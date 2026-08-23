# =============================================================================
# IVGS v5 — Integration Tests: Project CRUD
# =============================================================================
# Spec reference: §5.1 Content CRUD — Projects
#                 §4.3 Pipeline State Machine
#                 Appendix C.1 — Pagination Format
#                 Appendix C.3 — Project Resource Schema
# =============================================================================

from typing import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

BASE_URL = "http://localhost:8001/api/v1"
ADMIN_EMAIL = "admin@ivgs.local"
ADMIN_PASSWORD = "TestAdmin!2026_secure"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest_asyncio.fixture
async def admin_headers(client: httpx.AsyncClient) -> dict:
    response = await client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_project(
    client: httpx.AsyncClient, admin_headers: dict
) -> dict:
    """Create a sample project for tests that need an existing project."""
    response = await client.post(
        "/projects",
        json={
            "name": f"Test Project {uuid4().hex[:8]}",
            "description": "Integration test project",
            "max_runtime_seconds": 1800,
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Test Suite 1: Project Creation
# ---------------------------------------------------------------------------
class TestProjectCreate:

    @pytest.mark.asyncio
    async def test_create_project_success(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """Create project with valid data returns 201 with full schema."""
        response = await client.post(
            "/projects",
            json={
                "name": "Introduction to Machine Learning",
                "description": "A comprehensive overview of ML concepts",
                "max_runtime_seconds": 1800,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        # Verify Appendix C.3 schema fields
        assert "id" in data
        assert data["name"] == "Introduction to Machine Learning"
        assert data["state"] == "DRAFT"
        assert data["scene_count"] == 0
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_project_missing_name(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """Missing required field → 400 VALIDATION_ERROR."""
        response = await client.post(
            "/projects",
            json={"description": "No name provided"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_project_unauthenticated(
        self, client: httpx.AsyncClient
    ):
        """No auth token → 401."""
        response = await client.post(
            "/projects",
            json={"name": "Should Fail", "max_runtime_seconds": 600},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test Suite 2: Project Listing with Pagination (Appendix C.1)
# ---------------------------------------------------------------------------
class TestProjectList:

    @pytest.mark.asyncio
    async def test_list_projects_pagination_format(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """List response matches Appendix C.1 pagination format."""
        response = await client.get(
            "/projects?page=1&per_page=10",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data
        assert "has_more" in data
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_list_projects_default_page_size(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """Default per_page is 50 per Appendix C.1."""
        response = await client.get("/projects", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["per_page"] == 50


# ---------------------------------------------------------------------------
# Test Suite 3: Project Get / Update / Delete
# ---------------------------------------------------------------------------
class TestProjectCRUD:

    @pytest.mark.asyncio
    async def test_get_project_by_id(
        self, client: httpx.AsyncClient, admin_headers: dict, sample_project: dict
    ):
        """GET /projects/{id} returns full project schema."""
        project_id = sample_project["id"]
        response = await client.get(
            f"/projects/{project_id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """Non-existent project → 404 RESOURCE_NOT_FOUND."""
        response = await client.get(
            f"/projects/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_update_project(
        self, client: httpx.AsyncClient, admin_headers: dict, sample_project: dict
    ):
        """Update project name and description."""
        project_id = sample_project["id"]
        response = await client.patch(
            f"/projects/{project_id}",
            json={"name": "Updated Project Name"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Project Name"

    @pytest.mark.asyncio
    async def test_delete_project(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """Delete project → 204."""
        # Create a project to delete
        create = await client.post(
            "/projects",
            json={"name": "To Delete", "max_runtime_seconds": 60},
            headers=admin_headers,
        )
        project_id = create.json()["id"]

        response = await client.delete(
            f"/projects/{project_id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

        # Verify deletion
        get_response = await client.get(
            f"/projects/{project_id}",
            headers=admin_headers,
        )
        assert get_response.status_code == 404


# ---------------------------------------------------------------------------
# Test Suite 4: State Transitions (§4.3)
# ---------------------------------------------------------------------------
class TestProjectStateTransitions:

    @pytest.mark.asyncio
    async def test_initial_state_is_draft(
        self, client: httpx.AsyncClient, admin_headers: dict, sample_project: dict
    ):
        """New project starts in DRAFT state."""
        assert sample_project["state"] == "DRAFT"

    @pytest.mark.asyncio
    async def test_invalid_state_transition(
        self, client: httpx.AsyncClient, admin_headers: dict, sample_project: dict
    ):
        """Cannot skip pipeline stages — 409 INVALID_STATE_TRANSITION."""
        project_id = sample_project["id"]
        response = await client.post(
            f"/projects/{project_id}/render",
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
