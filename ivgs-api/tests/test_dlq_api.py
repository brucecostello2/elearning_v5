"""
Dead Letter Queue endpoint tests: listing, detail, replay, discard, analytics, bulk replay.

Tests cover:
- Message listing with filters
- Message detail retrieval
- Replay operation
- Discard operation with reason
- Analytics aggregation
- Bulk replay by filter
- RBAC enforcement
- Idempotency (cannot replay/discard resolved messages)
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDLQListing:
    """Test DLQ message listing."""

    async def test_list_messages_empty(
        self, client: AsyncClient, operator_token: str
    ):
        """Test listing DLQ messages when queue is empty."""
        response = await client.get(
            "/api/v1/dlq/messages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] == 0

    async def test_list_messages_with_data(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test listing DLQ messages returns paginated results."""
        response = await client.get(
            "/api/v1/dlq/messages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= len(dlq_messages)
        assert len(data["data"]) > 0

    async def test_list_messages_filter_category(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test filtering DLQ messages by failure category."""
        response = await client.get(
            "/api/v1/dlq/messages?category=transient",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        for msg in data["data"]:
            assert msg["failure_category"] == "transient"

    async def test_list_messages_filter_task_name(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test filtering DLQ messages by task name."""
        response = await client.get(
            "/api/v1/dlq/messages?task_name=image_generation",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200

    async def test_list_messages_viewer_denied(
        self, client: AsyncClient, viewer_token: str
    ):
        """Test that viewers cannot access DLQ messages."""
        response = await client.get(
            "/api/v1/dlq/messages",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestDLQDetail:
    """Test DLQ message detail retrieval."""

    async def test_get_message_detail(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test getting full DLQ message detail with traceback."""
        message_id = dlq_messages[0]["id"]
        response = await client.get(
            f"/api/v1/dlq/messages/{message_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == message_id
        assert "traceback" in data
        assert "task_args" in data
        assert "task_kwargs" in data

    async def test_get_message_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for non-existent DLQ message."""
        response = await client.get(
            f"/api/v1/dlq/messages/{uuid4()}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestDLQReplay:
    """Test DLQ message replay."""

    async def test_replay_message(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test replaying a DLQ message re-enqueues the task."""
        message_id = dlq_messages[0]["id"]
        response = await client.post(
            f"/api/v1/dlq/messages/{message_id}/replay",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resolution"] == "replayed"
        assert data["reviewed_by"] is not None

    async def test_replay_already_resolved(
        self, client: AsyncClient, operator_token: str, resolved_dlq_message: dict
    ):
        """Test that replaying an already-resolved message returns 409."""
        message_id = resolved_dlq_message["id"]
        response = await client.post(
            f"/api/v1/dlq/messages/{message_id}/replay",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 409

    async def test_replay_not_found(
        self, client: AsyncClient, operator_token: str
    ):
        """Test 404 for replaying non-existent message."""
        response = await client.post(
            f"/api/v1/dlq/messages/{uuid4()}/replay",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestDLQDiscard:
    """Test DLQ message discard."""

    async def test_discard_message(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test discarding a DLQ message with reason."""
        message_id = dlq_messages[1]["id"]
        response = await client.post(
            f"/api/v1/dlq/messages/{message_id}/discard",
            json={"reason": "Known issue, configuration has been fixed"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resolution"] == "discarded"

    async def test_discard_without_reason_fails(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test that discard without reason is rejected."""
        message_id = dlq_messages[1]["id"]
        response = await client.post(
            f"/api/v1/dlq/messages/{message_id}/discard",
            json={"reason": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestDLQAnalytics:
    """Test DLQ analytics endpoint."""

    async def test_get_analytics(
        self, client: AsyncClient, operator_token: str
    ):
        """Test DLQ failure analytics aggregation."""
        response = await client.get(
            "/api/v1/dlq/analytics",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_messages" in data
        assert "unresolved_count" in data
        assert "by_category" in data
        assert "by_task" in data
        assert "by_day" in data


@pytest.mark.asyncio
class TestDLQBulkReplay:
    """Test DLQ bulk replay by filter."""

    async def test_bulk_replay_by_category(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """Test bulk replaying transient failures."""
        response = await client.post(
            "/api/v1/dlq/bulk-replay",
            json={"category": "transient"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "replayed_count" in data
        assert "message_ids" in data

    async def test_bulk_replay_empty_filter(
        self, client: AsyncClient, operator_token: str
    ):
        """Test bulk replay with no matching messages."""
        response = await client.post(
            "/api/v1/dlq/bulk-replay",
            json={"task_name": "nonexistent_task"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["replayed_count"] == 0
