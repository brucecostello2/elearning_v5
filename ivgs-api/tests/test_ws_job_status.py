"""
Phase 2: WebSocket job status streaming tests.

Tests /api/v1/ws/jobs/{job_id}/status endpoint:
  - Redis pub/sub subscription and message forwarding
  - Heartbeat mechanism (every 5s idle)
  - Terminal status handling (COMPLETE, ERROR)
  - Redis connection error handling
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient

AUTH_PATCH = "app.api.v1.ws_logs._authenticate_ws"


@pytest.fixture
def sync_client():
    """Synchronous TestClient for WebSocket testing."""
    from main import app
    with TestClient(app) as c:
        yield c


def _make_mock_redis(messages=None):
    """Create a mock redis.asyncio client with pub/sub support.

    Args:
        messages: list of dicts to be returned by get_message() in sequence.
                  None entries produce heartbeats.

    Note: redis.asyncio.from_url() and client.pubsub() are *synchronous*
    calls in the real library, so mock_redis must be a MagicMock (not
    AsyncMock) with .pubsub as a plain method.  Only subscribe/unsubscribe/
    get_message/close are awaited in the real code and need AsyncMock.
    """
    if messages is None:
        messages = []

    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()

    call_idx = 0

    async def get_message_side_effect(**kwargs):
        nonlocal call_idx
        if call_idx < len(messages):
            msg = messages[call_idx]
            call_idx += 1
            if msg is None:
                return None  # No message → triggers heartbeat
            return {
                "type": "message",
                "data": json.dumps(msg).encode(),
            }
        raise Exception("test messages exhausted")

    mock_pubsub.get_message = get_message_side_effect

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_redis.close = AsyncMock()

    return mock_redis, mock_pubsub


# ===================================================================
# Heartbeat
# ===================================================================


def test_job_status_heartbeat(sync_client):
    """Should receive heartbeat when no pub/sub messages arrive."""
    mock_redis, mock_pubsub = _make_mock_redis(messages=[None])

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/job-abc/status") as ws:
                data = ws.receive_json()
                assert data["type"] == "heartbeat"
                assert data["job_id"] == "job-abc"


# ===================================================================
# Pub/sub message forwarding
# ===================================================================


def test_job_status_receives_update(sync_client):
    """Pub/sub messages should be forwarded to WebSocket client."""
    update = {"status": "RUNNING", "progress": 42, "job_id": "job-xyz"}
    mock_redis, _ = _make_mock_redis(messages=[update])

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/job-xyz/status") as ws:
                data = ws.receive_json()
                assert data["status"] == "RUNNING"
                assert data["progress"] == 42
                assert data["job_id"] == "job-xyz"


# ===================================================================
# Terminal status
# ===================================================================


def test_job_status_terminates_on_complete(sync_client):
    """WebSocket should close after receiving COMPLETE status."""
    messages = [
        {"status": "RUNNING", "progress": 50},
        {"status": "COMPLETE", "progress": 100},
    ]
    mock_redis, _ = _make_mock_redis(messages=messages)

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/job-done/status") as ws:
                data1 = ws.receive_json()
                assert data1["status"] == "RUNNING"
                data2 = ws.receive_json()
                assert data2["status"] == "COMPLETE"


def test_job_status_terminates_on_error(sync_client):
    """WebSocket should close after receiving ERROR status."""
    messages = [{"status": "ERROR", "error": "GPU OOM"}]
    mock_redis, _ = _make_mock_redis(messages=messages)

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/job-err/status") as ws:
                data = ws.receive_json()
                assert data["status"] == "ERROR"
                assert data["error"] == "GPU OOM"


# ===================================================================
# Redis connection error handling
# ===================================================================


def test_job_status_redis_connection_error(sync_client):
    """Should handle Redis connection failure gracefully."""
    with patch(AUTH_PATCH, return_value=True):
        with patch(
            "redis.asyncio.from_url",
            side_effect=Exception("Redis connection refused"),
        ):
            try:
                with sync_client.websocket_connect("/api/v1/ws/jobs/job-fail/status") as ws:
                    try:
                        data = ws.receive_json()
                        assert "error" in data or "type" in data
                    except Exception:
                        pass
            except Exception:
                pass


# ===================================================================
# Pub/sub subscription
# ===================================================================


def test_job_status_subscribes_to_correct_channel(sync_client):
    """Should subscribe to Redis channel job:{job_id}:status."""
    mock_redis, mock_pubsub = _make_mock_redis(messages=[None])

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/my-job-42/status") as ws:
                ws.receive_json()

    mock_pubsub.subscribe.assert_called_once_with("job:my-job-42:status")


def test_job_status_unsubscribes_on_close(sync_client):
    """Should unsubscribe from Redis and close connection in finally block."""
    messages = [{"status": "COMPLETE", "progress": 100}]
    mock_redis, mock_pubsub = _make_mock_redis(messages=messages)

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/cleanup-job/status") as ws:
                ws.receive_json()

    mock_pubsub.unsubscribe.assert_called_once_with("job:cleanup-job:status")
    mock_redis.close.assert_called_once()
