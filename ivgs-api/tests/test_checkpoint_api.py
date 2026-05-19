"""
Pipeline checkpoint endpoint tests: listing, stage detail, resume, clear.

Tests cover:
- Checkpoint listing for a job
- Stage checkpoint detail retrieval
- Pipeline resume from checkpoint
- Checkpoint clearing for full restart
- RBAC enforcement (owner + admin)
- Invalid state transitions
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestCheckpointListing:
    """Test checkpoint listing for a job."""

    async def test_list_checkpoints(
        self, client: AsyncClient, operator_token: str, job_with_checkpoints: dict
    ):
        """Test listing all checkpoints for a job."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "total_stages" in data
        assert "completed_stages" in data
        assert "failed_stages" in data
        assert "last_successful_stage" in data
        assert "checkpoints" in data

    async def test_list_checkpoints_empty_job(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        """Test listing checkpoints for a job with no checkpoints."""
        job_id = empty_job["id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_stages"] == 0
        assert data["checkpoints"] == []

    async def test_list_checkpoints_job_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for checkpoints on non-existent job."""
        response = await client.get(
            f"/api/v1/jobs/{uuid4()}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestCheckpointDetail:
    """Test stage checkpoint detail."""

    async def test_get_stage_checkpoint(
        self, client: AsyncClient, operator_token: str, job_with_checkpoints: dict
    ):
        """Test getting specific stage checkpoint data."""
        job_id = job_with_checkpoints["job_id"]
        stage_name = job_with_checkpoints["stages"][0]["stage_name"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints/{stage_name}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage_name"] == stage_name
        assert "checkpoint_data" in data
        assert "output_refs" in data

    async def test_get_stage_checkpoint_not_found(
        self, client: AsyncClient, operator_token: str, job_with_checkpoints: dict
    ):
        """Test 404 for non-existent stage checkpoint."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints/nonexistent_stage",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestPipelineResume:
    """Test pipeline resume from checkpoint."""

    async def test_resume_from_checkpoint(
        self, client: AsyncClient, operator_token: str, failed_job_with_checkpoints: dict
    ):
        """Test resuming pipeline from last successful checkpoint."""
        job_id = failed_job_with_checkpoints["job_id"]
        response = await client.post(
            f"/api/v1/jobs/{job_id}/resume",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "resume_from_stage" in data
        assert "new_job_id" in data
        assert data["new_job_id"] is not None

    async def test_resume_running_job_fails(
        self, client: AsyncClient, operator_token: str, running_job: dict
    ):
        """Test that resuming a running job returns 409."""
        job_id = running_job["id"]
        response = await client.post(
            f"/api/v1/jobs/{job_id}/resume",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 409

    async def test_resume_job_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for resuming non-existent job."""
        response = await client.post(
            f"/api/v1/jobs/{uuid4()}/resume",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404

    async def test_resume_viewer_denied(
        self, client: AsyncClient, viewer_token: str, failed_job_with_checkpoints: dict
    ):
        """Test that viewers cannot resume pipelines."""
        job_id = failed_job_with_checkpoints["job_id"]
        response = await client.post(
            f"/api/v1/jobs/{job_id}/resume",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestCheckpointClear:
    """Test checkpoint clearing."""

    async def test_clear_checkpoints(
        self, client: AsyncClient, operator_token: str, job_with_checkpoints: dict
    ):
        """Test clearing all checkpoints for a job."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.delete(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        assert data["deleted_count"] >= 0

    async def test_clear_checkpoints_job_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for clearing checkpoints on non-existent job."""
        response = await client.delete(
            f"/api/v1/jobs/{uuid4()}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404

    async def test_clear_checkpoints_viewer_denied(
        self, client: AsyncClient, viewer_token: str, job_with_checkpoints: dict
    ):
        """Test that viewers cannot clear checkpoints."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.delete(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestCheckpointRBAC:
    """Test RBAC enforcement for checkpoint endpoints."""

    async def test_admin_can_access_any_job(
        self, client: AsyncClient, admin_token: str, job_with_checkpoints: dict
    ):
        """Test that admin can access any job's checkpoints."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    async def test_operator_cannot_access_others_jobs(
        self, client: AsyncClient, other_operator_token: str, job_with_checkpoints: dict
    ):
        """Test that operators cannot access other users' job checkpoints."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {other_operator_token}"},
        )
        assert response.status_code == 403

    async def test_unauthenticated_access_denied(
        self, client: AsyncClient, job_with_checkpoints: dict
    ):
        """Test that unauthenticated requests are rejected."""
        job_id = job_with_checkpoints["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints",
        )
        assert response.status_code in (401, 403)
