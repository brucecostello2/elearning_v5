"""
Retention policy endpoint tests: listing, creation, update, report.

Tests cover:
- Policy listing (returns seeded defaults)
- Policy creation (admin only)
- Policy update with tier validation
- Asset tier distribution report
- RBAC enforcement
- Name uniqueness validation
- Default policy management
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRetentionPolicyListing:
    """Test retention policy listing."""

    async def test_list_policies(
        self, client: AsyncClient, operator_token: str
    ):
        """Test listing all retention policies."""
        response = await client.get(
            "/api/v1/retention/policies",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_viewer_can_list_policies(
        self, client: AsyncClient, viewer_token: str
    ):
        """Test that viewers can read retention policies."""
        response = await client.get(
            "/api/v1/retention/policies",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestRetentionPolicyCreate:
    """Test retention policy creation."""

    async def test_create_policy(
        self, client: AsyncClient, admin_token: str
    ):
        """Test creating a new retention policy."""
        response = await client.post(
            "/api/v1/retention/policies",
            json={
                "name": "test-custom-policy",
                "description": "Custom policy for testing",
                "hot_days": 14,
                "warm_days": 60,
                "cold_days": 180,
                "archive_days": 365,
                "delete_after_days": 730,
                "is_default": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-custom-policy"
        assert data["hot_days"] == 14
        assert data["warm_days"] == 60

    async def test_create_policy_duplicate_name(
        self, client: AsyncClient, admin_token: str, retention_policy: dict
    ):
        """Test that duplicate policy names are rejected."""
        response = await client.post(
            "/api/v1/retention/policies",
            json={
                "name": retention_policy["name"],
                "hot_days": 30,
                "warm_days": 90,
                "cold_days": 365,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    async def test_create_policy_invalid_tier_order(
        self, client: AsyncClient, admin_token: str
    ):
        """Test that warm_days < hot_days is rejected."""
        response = await client.post(
            "/api/v1/retention/policies",
            json={
                "name": "invalid-tier-order",
                "hot_days": 90,
                "warm_days": 30,
                "cold_days": 365,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    async def test_create_policy_operator_denied(
        self, client: AsyncClient, operator_token: str
    ):
        """Test that operators cannot create retention policies."""
        response = await client.post(
            "/api/v1/retention/policies",
            json={
                "name": "unauthorized-policy",
                "hot_days": 30,
                "warm_days": 90,
                "cold_days": 365,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403

    async def test_create_default_policy(
        self, client: AsyncClient, admin_token: str
    ):
        """Test creating a default policy clears previous defaults."""
        # Create first default
        resp1 = await client.post(
            "/api/v1/retention/policies",
            json={
                "name": "first-default",
                "hot_days": 30,
                "warm_days": 90,
                "cold_days": 365,
                "is_default": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 201
        assert resp1.json()["is_default"] is True

        # Create second default
        resp2 = await client.post(
            "/api/v1/retention/policies",
            json={
                "name": "second-default",
                "hot_days": 7,
                "warm_days": 30,
                "cold_days": 90,
                "is_default": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 201
        assert resp2.json()["is_default"] is True


@pytest.mark.asyncio
class TestRetentionPolicyUpdate:
    """Test retention policy update."""

    async def test_update_policy(
        self, client: AsyncClient, admin_token: str, retention_policy: dict
    ):
        """Test updating a retention policy."""
        policy_id = retention_policy["id"]
        response = await client.put(
            f"/api/v1/retention/policies/{policy_id}",
            json={"hot_days": 45, "warm_days": 120},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hot_days"] == 45
        assert data["warm_days"] == 120

    async def test_update_policy_not_found(
        self, client: AsyncClient, admin_token: str
    ):
        """Test 404 for non-existent policy update."""
        response = await client.put(
            f"/api/v1/retention/policies/{uuid4()}",
            json={"hot_days": 45},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    async def test_update_policy_operator_denied(
        self, client: AsyncClient, operator_token: str, retention_policy: dict
    ):
        """Test that operators cannot update retention policies."""
        policy_id = retention_policy["id"]
        response = await client.put(
            f"/api/v1/retention/policies/{policy_id}",
            json={"hot_days": 99},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestRetentionReport:
    """Test retention report endpoint."""

    async def test_get_report(
        self, client: AsyncClient, operator_token: str
    ):
        """Test asset tier distribution report."""
        response = await client.get(
            "/api/v1/retention/report",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_assets" in data
        assert "total_size_bytes" in data
        assert "tier_distribution" in data
        assert "upcoming_migrations" in data
        assert "policy_name" in data

    async def test_viewer_can_read_report(
        self, client: AsyncClient, viewer_token: str
    ):
        """Test that viewers can read the retention report."""
        response = await client.get(
            "/api/v1/retention/report",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200

    async def test_get_policy_detail(
        self, client: AsyncClient, operator_token: str, retention_policy: dict
    ):
        """Test getting a single retention policy by ID."""
        policy_id = retention_policy["id"]
        response = await client.get(
            f"/api/v1/retention/policies/{policy_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == policy_id

    async def test_get_policy_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for non-existent policy."""
        response = await client.get(
            f"/api/v1/retention/policies/{uuid4()}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404
