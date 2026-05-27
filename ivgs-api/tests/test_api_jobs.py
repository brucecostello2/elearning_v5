"""
Phase 3: Job API endpoint tests.

Tests:
  GET  /api/v1/projects/{project_id}/jobs — list project jobs
  GET  /api/v1/jobs/{job_id} — job detail
  POST /api/v1/jobs/{job_id}/cancel — cancel running job
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestListJobs:
    """GET /api/v1/projects/{project_id}/jobs"""

    async def test_list_jobs_success(
        self, client: AsyncClient, operator_token: str, running_job: dict
    ):
        pid = running_job["project_id"]
        r = await client.get(
            f"/api/v1/projects/{pid}/jobs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    async def test_list_jobs_pagination_fields(
        self, client: AsyncClient, operator_token: str, running_job: dict
    ):
        pid = running_job["project_id"]
        r = await client.get(
            f"/api/v1/projects/{pid}/jobs?page=1&per_page=5",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        for key in ("total", "page", "per_page", "pages", "has_more"):
            assert key in data, f"Missing pagination field '{key}'"
        assert data["page"] == 1
        assert data["per_page"] == 5

    async def test_list_jobs_nonexistent_project(
        self, client: AsyncClient, operator_token: str
    ):
        fake_pid = str(uuid4())
        r = await client.get(
            f"/api/v1/projects/{fake_pid}/jobs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # Might return 404 or empty list depending on implementation
        assert r.status_code in (200, 404)

    async def test_list_jobs_unauthenticated(
        self, client: AsyncClient, running_job: dict
    ):
        pid = running_job["project_id"]
        r = await client.get(f"/api/v1/projects/{pid}/jobs")
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
class TestGetJob:
    """GET /api/v1/jobs/{job_id}"""

    async def test_get_job_success(
        self, client: AsyncClient, operator_token: str, running_job: dict
    ):
        jid = running_job["id"]
        r = await client.get(
            f"/api/v1/jobs/{jid}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == jid
        assert "status" in data
        assert "job_type" in data
        assert "project_id" in data

    async def test_get_job_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            f"/api/v1/jobs/{uuid4()}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 404

    async def test_get_job_invalid_uuid(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/jobs/not-a-uuid",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 422

    async def test_get_job_unauthenticated(
        self, client: AsyncClient, running_job: dict
    ):
        r = await client.get(f"/api/v1/jobs/{running_job['id']}")
        assert r.status_code in (401, 403)

    async def test_get_job_response_schema(
        self, client: AsyncClient, operator_token: str, running_job: dict
    ):
        """Verify response matches JobResponse schema."""
        r = await client.get(
            f"/api/v1/jobs/{running_job['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        expected_keys = {
            "id", "project_id", "job_type", "status", "created_at",
        }
        assert expected_keys.issubset(set(data.keys()))


@pytest.mark.asyncio
class TestCancelJob:
    """POST /api/v1/jobs/{job_id}/cancel"""

    async def test_cancel_running_job(
        self, client: AsyncClient, operator_token: str, running_job: dict
    ):
        jid = running_job["id"]
        r = await client.post(
            f"/api/v1/jobs/{jid}/cancel",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        # Service sets status to "failed" with "Cancelled by user" message
        assert data["status"] == "failed"

    async def test_cancel_nonexistent_job(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.post(
            f"/api/v1/jobs/{uuid4()}/cancel",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 404

    async def test_cancel_already_completed_job(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        """Cancelling a non-running job should fail or be idempotent."""
        jid = empty_job["id"]
        r = await client.post(
            f"/api/v1/jobs/{jid}/cancel",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # Could be 400 (can't cancel pending) or 200 (idempotent)
        assert r.status_code in (200, 400, 409)

    async def test_cancel_job_unauthenticated(
        self, client: AsyncClient, running_job: dict
    ):
        r = await client.post(f"/api/v1/jobs/{running_job['id']}/cancel")
        assert r.status_code in (401, 403)
