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
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# WP-45 Task 4(b), D-2 RULED: the GPU endpoints read through to the scheduler.
#
# gpu_nodes has always had zero rows - workers register with the SCHEDULER
# (POST /register), and nothing in ivgs-workers has ever called
# POST /api/v1/gpu/nodes. These endpoints read the registry the workers
# actually write to, so the tests below stub THAT rather than seeding a table
# nothing reads. `registered_gpu_node` is still used where it is genuinely the
# subject (registration, reservations, RBAC).
# ---------------------------------------------------------------------------

def _fleet_node(node_id="node-04:gpu0", alive=True, draining=False, used=0):
    return {
        "node_id": node_id, "gpu_index": 0,
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887, "used_vram_mb": used,
        "available_vram_mb": 97887 - used, "gpu_utilization_pct": 0.0,
        "current_jobs": [], "last_heartbeat": "2026-08-25T13:00:00+00:00",
        "is_alive": alive, "is_draining": draining,
        "loaded_models": [], "circuit_breaker_state": "closed",
    }


def _fleet(*nodes):
    nodes = list(nodes) or [_fleet_node()]
    total = sum(n["total_vram_mb"] for n in nodes)
    used = sum(n["used_vram_mb"] for n in nodes)
    return {
        "total_nodes": len(nodes),
        "alive_nodes": sum(1 for n in nodes if n["is_alive"]),
        "draining_nodes": sum(1 for n in nodes if n["is_draining"]),
        "total_vram_mb": total, "used_vram_mb": used,
        "available_vram_mb": total - used,
        "fleet_utilization_pct": 0.0,
        "queue_depth": {"urgent": 0, "normal": 0, "batch": 0},
        "nodes": nodes,
    }


@pytest.fixture
def scheduler_fleet():
    """Patch the scheduler read-through with a small, known fleet."""
    with patch(
        "app.services.gpu_service.fetch_fleet",
        AsyncMock(return_value=_fleet(_fleet_node())),
    ):
        yield


@pytest.fixture
def empty_scheduler_fleet():
    with patch(
        "app.services.gpu_service.fetch_fleet",
        AsyncMock(return_value=_fleet(*[])),
    ) as f:
        f.return_value = {
            "total_nodes": 0, "alive_nodes": 0, "draining_nodes": 0,
            "total_vram_mb": 0, "used_vram_mb": 0, "available_vram_mb": 0,
            "fleet_utilization_pct": 0.0,
            "queue_depth": {"urgent": 0, "normal": 0, "batch": 0},
            "nodes": [],
        }
        yield
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

    async def test_list_nodes_empty(
        self, client: AsyncClient, admin_token: str, empty_scheduler_fleet,
    ):
        """Test listing GPU nodes when the scheduler registry is empty."""
        response = await client.get(
            "/api/v1/gpu/nodes",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    async def test_list_nodes_with_filter(
        self, client: AsyncClient, admin_token: str, scheduler_fleet,
    ):
        """Test filtering nodes by status."""
        response = await client.get(
            "/api/v1/gpu/nodes?status=online",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_get_node_detail(
        self, client: AsyncClient, admin_token: str, scheduler_fleet,
    ):
        """Test getting single node detail, by its derived id."""
        listing = await client.get(
            "/api/v1/gpu/nodes",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        node_id = listing.json()["data"][0]["id"]
        response = await client.get(
            f"/api/v1/gpu/nodes/{node_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == node_id
        assert "used_vram_mb" in data
        assert "available_vram_mb" in data

    async def test_get_node_not_found(
        self, client: AsyncClient, admin_token: str, scheduler_fleet,
    ):
        """Test 404 for a node the scheduler does not know."""
        response = await client.get(
            f"/api/v1/gpu/nodes/{uuid4()}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestGpuNodeDrain:
    """Test GPU node drain operation."""

    async def test_drain_node(self, client: AsyncClient, admin_token: str):
        """Draining goes to the scheduler, which is what placement consults.

        WP-45 Task 4(b): this used to set gpu_nodes.status='draining' on a table
        the scheduler does not read, so a drained node kept receiving work.
        """
        drained = _fleet_node(draining=True)
        calls = []

        async def fake_fleet(*_a, **_k):
            return _fleet(drained if calls else _fleet_node())

        with patch("app.services.gpu_service.fetch_fleet", side_effect=fake_fleet):
            listing = await client.get(
                "/api/v1/gpu/nodes",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            node_id = listing.json()["data"][0]["id"]

            scheduler_response = MagicMock()
            scheduler_response.status_code = 200
            scheduler_response.json.return_value = {
                "node_id": "node-04:gpu0", "status": "draining",
                "active_jobs": 0, "message": "draining",
            }
            posting = MagicMock()
            posting.post = AsyncMock(return_value=scheduler_response)
            posting.__aenter__ = AsyncMock(return_value=posting)
            posting.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=posting):
                calls.append(1)
                response = await client.post(
                    f"/api/v1/gpu/nodes/{node_id}/drain",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )

        assert response.status_code == 200
        # The scheduler was actually asked, rather than a row being flipped.
        posting.post.assert_awaited_once()
        assert response.json()["status"] == "draining"

    async def test_drain_unknown_node_is_404(
        self, client: AsyncClient, admin_token: str, scheduler_fleet,
    ):
        response = await client.post(
            f"/api/v1/gpu/nodes/{uuid4()}/drain",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

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

    async def test_get_utilization(
        self, client: AsyncClient, admin_token: str, scheduler_fleet,
    ):
        """Test fleet utilization summary, read through from the scheduler."""
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
        self, client: AsyncClient, viewer_token: str, scheduler_fleet,
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

    async def test_update_node_is_refused_and_names_the_alternative(
        self, client: AsyncClient, admin_token: str, registered_gpu_node: dict
    ):
        """WP-45 Task 4(b): node facts are owned by the scheduler's registry.

        This route still wrote gpu_nodes, a table nothing reads any more, so a
        200 here would report a change nobody will ever see. It answers 409 and
        names what to do instead: drain through the scheduler, or set the
        node's own IVGS_GPU_* environment.
        """
        node_id = registered_gpu_node["id"]
        response = await client.patch(
            f"/api/v1/gpu/nodes/{node_id}",
            json={"gpu_model": "NVIDIA RTX 6000", "total_vram_mb": 49152},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409
        assert "drain" in response.text

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
