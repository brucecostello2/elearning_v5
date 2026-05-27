"""
GPU management endpoint tests: registration, listing, drain, utilization, RBAC.

Tests cover:
- Node registration (admin only)
- Node listing with filters
- Node detail retrieval
- Node update (admin only)
- Node drain operation
- Reservation listing
- Fleet utilization summary
- RBAC enforcement
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestGpuNodeRegistration:
    """Test GPU node registration (admin only)."""

    async def test_register_node(self, client: AsyncClient, admin_token: str):
        """Test registering a new GPU node."""
        response = await client.post(
            "/api/v1/gpu/nodes",
            json={
                "node_hostname": "node-04",
                "gpu_index": 0,
                "gpu_model": "NVIDIA RTX 5000 Pro Blackwell",
                "total_vram_mb": 49152,
                "compute_capability": "10.0",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["node_hostname"] == "node-04"
        assert data["gpu_index"] == 0
        assert data["gpu_model"] == "NVIDIA RTX 5000 Pro Blackwell"
        assert data["total_vram_mb"] == 49152
        assert data["status"] == "online"

    async def test_register_node_upsert(self, client: AsyncClient, admin_token: str):
        """Test re-registering an existing node updates instead of duplicating."""
        node_data = {
            "node_hostname": "node-02",
            "gpu_index": 0,
            "gpu_model": "NVIDIA H100",
            "total_vram_mb": 98304,
        }
        # First registration
        resp1 = await client.post(
            "/api/v1/gpu/nodes",
            json=node_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 201
        node_id_1 = resp1.json()["id"]

        # Second registration (upsert)
        resp2 = await client.post(
            "/api/v1/gpu/nodes",
            json={**node_data, "total_vram_mb": 98304},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 201
        node_id_2 = resp2.json()["id"]
        assert node_id_1 == node_id_2  # Same node, not a duplicate

    async def test_register_node_operator_denied(
        self, client: AsyncClient, operator_token: str
    ):
        """Test that operators cannot register GPU nodes."""
        response = await client.post(
            "/api/v1/gpu/nodes",
            json={
                "node_hostname": "rogue-node",
                "gpu_index": 0,
                "gpu_model": "RTX 4090",
                "total_vram_mb": 24576,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403

    async def test_register_node_viewer_denied(
        self, client: AsyncClient, viewer_token: str
    ):
        """Test that viewers cannot register GPU nodes."""
        response = await client.post(
            "/api/v1/gpu/nodes",
            json={
                "node_hostname": "rogue-node",
                "gpu_index": 0,
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestGpuNodeListing:
    """Test GPU node listing and filtering."""

    async def test_list_nodes_empty(self, client: AsyncClient, admin_token: str):
        """Test listing GPU nodes when none registered."""
        response = await client.get(
            "/api/v1/gpu/nodes",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    async def test_list_nodes_with_filter(
        self, client: AsyncClient, admin_token: str, registered_gpu_node: dict
    ):
        """Test filtering nodes by status."""
        response = await client.get(
            "/api/v1/gpu/nodes?status=online",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    async def test_get_node_detail(
        self, client: AsyncClient, admin_token: str, registered_gpu_node: dict
    ):
        """Test getting single node detail."""
        node_id = registered_gpu_node["id"]
        response = await client.get(
            f"/api/v1/gpu/nodes/{node_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == node_id
        assert "used_vram_mb" in data
        assert "available_vram_mb" in data

    async def test_get_node_not_found(self, client: AsyncClient, admin_token: str):
        """Test 404 for non-existent node."""
        response = await client.get(
            f"/api/v1/gpu/nodes/{uuid4()}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestGpuNodeDrain:
    """Test GPU node drain operation."""

    async def test_drain_node(
        self, client: AsyncClient, admin_token: str, registered_gpu_node: dict
    ):
        """Test draining a GPU node."""
        node_id = registered_gpu_node["id"]
        response = await client.post(
            f"/api/v1/gpu/nodes/{node_id}/drain",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "draining"

    async def test_drain_already_draining(
        self, client: AsyncClient, admin_token: str, draining_gpu_node: dict
    ):
        """Test that draining an already-draining node returns 409."""
        node_id = draining_gpu_node["id"]
        response = await client.post(
            f"/api/v1/gpu/nodes/{node_id}/drain",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    async def test_drain_operator_denied(
        self, client: AsyncClient, operator_token: str, registered_gpu_node: dict
    ):
        """Test that operators cannot drain nodes."""
        node_id = registered_gpu_node["id"]
        response = await client.post(
            f"/api/v1/gpu/nodes/{node_id}/drain",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestGpuNodeReservations:
    """Test GPU node reservation listing."""

    async def test_get_reservations(
        self, client: AsyncClient, admin_token: str, registered_gpu_node: dict
    ):
        """Test getting active reservations for a node."""
        node_id = registered_gpu_node["id"]
        response = await client.get(
            f"/api/v1/gpu/nodes/{node_id}/reservations",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_get_reservations_not_found(
        self, client: AsyncClient, admin_token: str
    ):
        """Test 404 for reservations on non-existent node."""
        response = await client.get(
            f"/api/v1/gpu/nodes/{uuid4()}/reservations",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestGpuFleetUtilization:
    """Test fleet-wide utilization endpoint."""

    async def test_get_utilization(self, client: AsyncClient, admin_token: str):
        """Test fleet utilization summary."""
        response = await client.get(
            "/api/v1/gpu/utilization",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_nodes" in data
        assert "total_vram_mb" in data
        assert "fleet_utilization_pct" in data
        assert "nodes" in data

    async def test_viewer_can_read_utilization(
        self, client: AsyncClient, viewer_token: str
    ):
        """Test that viewers can read utilization (read-only access)."""
        response = await client.get(
            "/api/v1/gpu/utilization",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestGpuNodeUpdate:
    """Test GPU node update (admin only)."""

    async def test_update_node(
        self, client: AsyncClient, admin_token: str, registered_gpu_node: dict
    ):
        """Test updating GPU node metadata."""
        node_id = registered_gpu_node["id"]
        response = await client.patch(
            f"/api/v1/gpu/nodes/{node_id}",
            json={"gpu_model": "NVIDIA RTX 6000", "total_vram_mb": 49152},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["gpu_model"] == "NVIDIA RTX 6000"

    async def test_update_node_operator_denied(
        self, client: AsyncClient, operator_token: str, registered_gpu_node: dict
    ):
        """Test that operators cannot update GPU nodes."""
        node_id = registered_gpu_node["id"]
        response = await client.patch(
            f"/api/v1/gpu/nodes/{node_id}",
            json={"gpu_model": "Hacked"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 403
