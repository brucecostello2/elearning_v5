"""
Quality Assurance endpoint tests: job scores, flagged assets, approve, reject.

Tests cover:
- Job quality score retrieval
- Flagged asset listing
- Approve flagged asset (admin only)
- Reject flagged asset with regeneration
- RBAC enforcement
- Invalid state transition handling
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestJobQuality:
    """Test job quality score retrieval."""

    async def test_get_job_quality(
        self, client: AsyncClient, operator_token: str, job_with_quality_scores: dict
    ):
        """Test getting all quality scores for a job."""
        job_id = job_with_quality_scores["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/quality",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "total_assets" in data
        assert "approved_count" in data
        assert "flagged_count" in data
        assert "rejected_count" in data
        assert "scores" in data

    async def test_get_job_quality_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for non-existent job."""
        response = await client.get(
            f"/api/v1/jobs/{uuid4()}/quality",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404

    async def test_viewer_can_read_quality(
        self, client: AsyncClient, viewer_token: str, job_with_quality_scores: dict
    ):
        """Test that viewers can read quality scores."""
        job_id = job_with_quality_scores["job_id"]
        response = await client.get(
            f"/api/v1/jobs/{job_id}/quality",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestFlaggedAssets:
    """Test flagged asset listing."""

    async def test_list_flagged_empty(
        self, client: AsyncClient, operator_token: str
    ):
        """Test listing flagged assets when none exist."""
        response = await client.get(
            "/api/v1/quality/flagged",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    async def test_list_flagged_with_data(
        self, client: AsyncClient, operator_token: str, flagged_quality_scores: list
    ):
        """Test listing flagged assets returns enriched data."""
        response = await client.get(
            "/api/v1/quality/flagged",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for item in data["data"]:
            assert item["decision"] == "flagged"


@pytest.mark.asyncio
class TestQualityApprove:
    """Test quality score approval."""

    async def test_approve_flagged(
        self, client: AsyncClient, admin_token: str, flagged_quality_scores: list
    ):
        """Test approving a flagged asset."""
        score_id = flagged_quality_scores[0]["id"]
        response = await client.post(
            f"/api/v1/quality/{score_id}/approve",
            json={"notes": "Reviewed manually, asset is acceptable"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "approved"
        assert data["reviewed_by"] is not None

    async def test_approve_already_approved(
        self, client: AsyncClient, admin_token: str, approved_quality_score: dict
    ):
        """Test that approving an already-approved score returns 409."""
        score_id = approved_quality_score["id"]
        response = await client.post(
            f"/api/v1/quality/{score_id}/approve",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    async def test_approve_operator_denied(
        self, client: AsyncClient, operator_token: str, flagged_quality_scores: list
    ):
        """Test that operators cannot approve quality scores."""
        score_id = flagged_quality_scores[0]["id"]
        response = await client.post(
            f"/api/v1/quality/{score_id}/approve",
            json={},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403

    async def test_approve_not_found(
        self, client: AsyncClient, admin_token: str
    ):
        """Test 404 for non-existent quality score."""
        response = await client.post(
            f"/api/v1/quality/{uuid4()}/approve",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestQualityReject:
    """Test quality score rejection."""

    async def test_reject_flagged(
        self, client: AsyncClient, admin_token: str, flagged_quality_scores: list
    ):
        """Test rejecting a flagged asset triggers regeneration."""
        score_id = flagged_quality_scores[0]["id"]
        response = await client.post(
            f"/api/v1/quality/{score_id}/reject",
            json={
                "notes": "Quality too low, background artifacts visible",
                "regenerate": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "rejected"

    async def test_reject_without_regeneration(
        self, client: AsyncClient, admin_token: str, flagged_quality_scores: list
    ):
        """Test rejecting without triggering regeneration."""
        score_id = flagged_quality_scores[0]["id"]
        response = await client.post(
            f"/api/v1/quality/{score_id}/reject",
            json={"notes": "Not needed, project cancelled", "regenerate": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["decision"] == "rejected"
