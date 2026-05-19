# =============================================================================
# IVGS v5 — Integration Tests: Dead Letter Queue (DLQ)
# =============================================================================
# Spec reference: §5.2 DLQ Operations
#                 §6.2 Operational Layer — DLQ routing
# =============================================================================

from typing import AsyncGenerator

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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Test Suite 1: DLQ Listing
# ---------------------------------------------------------------------------
class TestDLQListing:

    @pytest.mark.asyncio
    async def test_list_dlq_messages(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """GET /dlq returns paginated DLQ messages."""
        response = await client.get("/dlq", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_dlq_message_schema(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """DLQ messages include required fields: job_id, error, attempts, age."""
        response = await client.get("/dlq", headers=admin_headers)
        data = response.json()
        if data["data"]:
            msg = data["data"][0]
            assert "id" in msg
            assert "job_id" in msg
            assert "error_message" in msg
            assert "retry_count" in msg
            assert "created_at" in msg


# ---------------------------------------------------------------------------
# Test Suite 2: DLQ Operations (Admin-only per §5.2)
# ---------------------------------------------------------------------------
class TestDLQOperations:

    @pytest.mark.asyncio
    async def test_replay_dlq_message(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """POST /dlq/{id}/replay re-queues a DLQ message for processing."""
        # First get a DLQ message if any
        listing = await client.get("/dlq", headers=admin_headers)
        messages = listing.json()["data"]
        if messages:
            msg_id = messages[0]["id"]
            response = await client.post(
                f"/dlq/{msg_id}/replay",
                headers=admin_headers,
            )
            assert response.status_code in (200, 202)

    @pytest.mark.asyncio
    async def test_discard_dlq_message(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """DELETE /dlq/{id} permanently discards a DLQ message."""
        listing = await client.get("/dlq", headers=admin_headers)
        messages = listing.json()["data"]
        if messages:
            msg_id = messages[0]["id"]
            response = await client.delete(
                f"/dlq/{msg_id}",
                headers=admin_headers,
            )
            assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_dlq_count(
        self, client: httpx.AsyncClient, admin_headers: dict
    ):
        """GET /dlq/count returns current DLQ depth."""
        response = await client.get("/dlq/count", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)
