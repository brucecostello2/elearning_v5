"""
Phase 3: Node API endpoint tests.

Tests stub endpoints:
  GET /api/v1/nodes — list all 6 nodes
  GET /api/v1/nodes/{node_id} — single node detail
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestListNodes:
    """GET /api/v1/nodes"""

    async def test_list_nodes_success(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/nodes",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 6
        node_ids = {n["node_id"] for n in data}
        assert node_ids == {
            "node-01", "node-02", "node-03", "node-04", "node-05", "node-06"
        }

    async def test_list_nodes_has_expected_fields(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/nodes",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        node = r.json()[0]
        for field in ("node_id", "role", "hostname", "status"):
            assert field in node, f"Missing field '{field}' in node response"

    async def test_list_nodes_unauthenticated(self, client: AsyncClient):
        r = await client.get("/api/v1/nodes")
        assert r.status_code in (401, 403)

    async def test_list_nodes_viewer_allowed(
        self, client: AsyncClient, viewer_token: str
    ):
        r = await client.get(
            "/api/v1/nodes",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 200


@pytest.mark.asyncio
class TestGetNode:
    """GET /api/v1/nodes/{node_id}"""

    async def test_get_node_success(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/nodes/node-01",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["node_id"] == "node-01"

    async def test_get_node_all_valid_ids(
        self, client: AsyncClient, operator_token: str
    ):
        for i in range(1, 7):
            nid = f"node-0{i}"
            r = await client.get(
                f"/api/v1/nodes/{nid}",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            assert r.status_code == 200, f"Failed for {nid}"
            assert r.json()["node_id"] == nid

    async def test_get_node_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        r = await client.get(
            "/api/v1/nodes/node-99",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 404

    async def test_get_node_unauthenticated(self, client: AsyncClient):
        r = await client.get("/api/v1/nodes/node-01")
        assert r.status_code in (401, 403)
