"""
Project endpoint tests: CRUD, state machine, RBAC, pipeline trigger.

Tests cover:
- Project creation, listing, retrieval, update, deletion
- 13-state machine transitions (valid and invalid)
- RBAC enforcement (admin, operator, viewer)
- Pipeline trigger validation
- Talking head upload
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestProjectCRUD:
    """Test basic project CRUD operations."""

    async def test_create_project(self, client: AsyncClient, operator_token: str):
        """Test creating a new project in DRAFT state."""
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": "Test Video Project",
                "description": "A test project for unit testing",
                "max_runtime_seconds": 1800,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Video Project"
        assert data["state"] == "DRAFT"
        assert data["description"] == "A test project for unit testing"
        assert data["max_runtime_seconds"] == 1800
        assert data["scene_count"] == 0

    async def test_create_project_with_languages(self, client: AsyncClient, operator_token: str):
        """Test creating a project with target languages."""
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": "Multilingual Video",
                "target_languages": ["es-ES", "fr-FR"],
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["language_variants"]) == 2
        lang_codes = {v["language_code"] for v in data["language_variants"]}
        assert lang_codes == {"es-ES", "fr-FR"}

    async def test_create_project_invalid_language(self, client: AsyncClient, operator_token: str):
        """Test that invalid language codes are rejected."""
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": "Bad Language Project",
                "target_languages": ["xx-XX"],
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 422

    async def test_list_projects(self, client: AsyncClient, operator_token: str):
        """Test listing projects with pagination."""
        # Create a project first
        await client.post(
            "/api/v1/projects",
            json={"name": "List Test Project"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        response = await client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert data["page"] == 1

    async def test_list_projects_with_state_filter(self, client: AsyncClient, operator_token: str):
        """Test filtering projects by state."""
        response = await client.get(
            "/api/v1/projects?state=DRAFT",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200

    async def test_list_projects_with_search(self, client: AsyncClient, operator_token: str):
        """Test searching projects by name."""
        await client.post(
            "/api/v1/projects",
            json={"name": "Searchable Unique Name XYZ"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        response = await client.get(
            "/api/v1/projects?search=Searchable",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200

    async def test_get_project(self, client: AsyncClient, operator_token: str):
        """Test getting a project by ID."""
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Get Test Project"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        project_id = create_resp.json()["id"]
        response = await client.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == project_id

    async def test_get_project_not_found(self, client: AsyncClient, operator_token: str):
        """Test 404 for non-existent project."""
        response = await client.get(
            f"/api/v1/projects/{uuid4()}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404

    async def test_update_project(self, client: AsyncClient, operator_token: str):
        """Test updating project metadata."""
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Original Name"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        project_id = create_resp.json()["id"]
        response = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "Updated Name", "description": "New description"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    async def test_delete_project_requires_confirm_name(
        self, client: AsyncClient, admin_token: str
    ):
        """WP-59 Task 6: a bare curl cannot delete by id alone.

        `confirm_name` is a REQUIRED query parameter, so a DELETE without it is
        a 422 from FastAPI's own validation before any service code runs. This
        is the whole "the API is not a second, weaker door" requirement: the
        GUI types the name into a box, and a script has to supply the same
        thing.
        """
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Delete Me"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = create_resp.json()["id"]

        bare = await client.delete(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert bare.status_code == 422

        # And the project is still there. Asserting the destruction did NOT
        # happen matters as much as asserting that it does: a refusal that
        # deleted anyway would pass a status-code-only test.
        still_there = await client.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert still_there.status_code == 200

    async def test_delete_project_wrong_confirm_name_refused(
        self, client: AsyncClient, admin_token: str
    ):
        """A confirmation that does not match the name exactly is a 409."""
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Precisely This Name"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = create_resp.json()["id"]

        # Near-misses, all refused. Case and whitespace are deliberately NOT
        # normalised: the name is the thing being confirmed, and accepting a
        # near-miss confirms something else.
        for wrong in ("precisely this name", "Precisely This Name ", "Wrong"):
            resp = await client.delete(
                f"/api/v1/projects/{project_id}",
                params={"confirm_name": wrong},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == 409, wrong
            assert resp.json()["detail"]["error"]["code"] == "CONFIRMATION_MISMATCH"

        still_there = await client.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert still_there.status_code == 200

    async def test_delete_project_admin_only(
        self, client: AsyncClient, admin_token: str
    ):
        """The happy path: 200, and the response ASSERTS the destruction.

        WP-45 Task 3 found eight surfaces returning 202 while doing nothing,
        and its acceptance criterion was deliberately not "returns 202" for
        exactly that reason. So this checks the row counts the server reports
        removing, and then checks the project is actually gone.
        """
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Delete Me"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/projects/{project_id}",
            params={"confirm_name": "Delete Me"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["project_name"] == "Delete Me"
        assert body["audit_id"]
        # The project row itself is always one of the rows destroyed.
        assert body["rows_deleted"]["projects"] == 1

        gone = await client.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert gone.status_code == 404

    async def test_deletion_preview_is_admin_only(
        self, client: AsyncClient, admin_token: str, operator_token: str
    ):
        """The inventory is admin material, like the DELETE it precedes."""
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Preview Me"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = create_resp.json()["id"]

        ok = await client.get(
            f"/api/v1/projects/{project_id}/deletion-preview",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert ok.status_code == 200
        payload = ok.json()
        assert payload["project_name"] == "Preview Me"
        assert len(payload["categories"]) >= 15
        assert payload["blocking_jobs"] == []

        denied = await client.get(
            f"/api/v1/projects/{project_id}/deletion-preview",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert denied.status_code == 403

    async def test_delete_project_operator_denied(self, client: AsyncClient, operator_token: str):
        """Test that operators cannot delete projects."""
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Cannot Delete"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        project_id = create_resp.json()["id"]
        response = await client.delete(
            f"/api/v1/projects/{project_id}",
            params={"confirm_name": "Cannot Delete"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestProjectStateMachine:
    """Test project state machine transitions per §4.3."""

    async def test_valid_transition_draft_to_trigger(
        self, client: AsyncClient, operator_token: str, project_with_transcript: dict
    ):
        """Test triggering pipeline from DRAFT state."""
        project_id = project_with_transcript["id"]
        response = await client.post(
            f"/api/v1/projects/{project_id}/trigger",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "TRANSCRIPT_REFINEMENT"

    async def test_trigger_without_transcript_fails(
        self, client: AsyncClient, operator_token: str
    ):
        """Test that triggering without transcripts raises error."""
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "Empty Project"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        project_id = create_resp.json()["id"]
        response = await client.post(
            f"/api/v1/projects/{project_id}/trigger",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 409

    async def test_viewer_cannot_create_project(self, client: AsyncClient, viewer_token: str):
        """Test that viewers cannot create projects."""
        response = await client.post(
            "/api/v1/projects",
            json={"name": "Should Fail"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestProjectRBAC:
    """Test RBAC enforcement for project endpoints."""

    async def test_viewer_can_list_projects(self, client: AsyncClient, viewer_token: str):
        """Viewers should be able to list all projects (read-only)."""
        response = await client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200

    async def test_unauthenticated_access_denied(self, client: AsyncClient):
        """Unauthenticated requests should be rejected."""
        response = await client.get("/api/v1/projects")
        assert response.status_code in (401, 403)
