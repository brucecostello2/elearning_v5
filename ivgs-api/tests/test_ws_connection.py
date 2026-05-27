"""
Phase 2: WebSocket connection lifecycle tests.

Tests connection establishment, invalid node handling,
authentication gaps, and disconnect cleanup for:
  - /api/v1/ws/jobs/{job_id}/status
  - /api/v1/ws/nodes/{node_id}/logs
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient


@pytest.fixture
def sync_client():
    """Synchronous TestClient for WebSocket testing.

    httpx AsyncClient does not support WebSocket — must use
    starlette's TestClient which wraps the ASGI app synchronously.
    """
    from main import app
    with TestClient(app) as c:
        yield c


# ===================================================================
# Basic connection
# ===================================================================


def test_ws_connect_job_status(sync_client):
    """WebSocket /ws/jobs/{job_id}/status should accept connection."""
    # Mock redis.asyncio so we don't need a real Redis server.
    # redis.asyncio.from_url() and client.pubsub() are *synchronous* —
    # use MagicMock, not AsyncMock, for those.
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()

    call_count = 0

    async def limited_get_message(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise Exception("test done")
        return None

    mock_pubsub.get_message = limited_get_message

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        with sync_client.websocket_connect("/api/v1/ws/jobs/test-job-123/status") as ws:
            # Should receive heartbeat
            data = ws.receive_json()
            assert data["type"] == "heartbeat"
            assert data["job_id"] == "test-job-123"


def test_ws_connect_node_logs_valid_node(sync_client):
    """WebSocket /ws/nodes/{node_id}/logs should accept for valid node."""
    # Mock subprocess to avoid real SSH
    mock_process = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.returncode = 0

    # readline returns one line then empty (EOF)
    mock_process.stdout.readline = AsyncMock(
        side_effect=[b"2026-05-27 log line 1\n", b""]
    )

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            data = ws.receive_json()
            assert data["node_id"] == "node-01"
            assert "log line 1" in data["log"]
            assert "timestamp" in data


def test_ws_connect_node_logs_invalid_node(sync_client):
    """WebSocket /ws/nodes/{invalid}/logs should send error and close(1008)."""
    with sync_client.websocket_connect("/api/v1/ws/nodes/node-99/logs") as ws:
        data = ws.receive_json()
        assert "error" in data
        assert "Unknown node" in data["error"]
        assert "node-99" in data["error"]


# ===================================================================
# Authentication gap (BUG-012)
# ===================================================================


@pytest.mark.xfail(
    reason="BUG-012: WebSocket endpoints accept connections without authentication",
    strict=True,
)
def test_ws_connect_no_auth_rejected(sync_client):
    """WebSocket connection should require authentication token.

    BUG-012: Both WS endpoints call websocket.accept() immediately
    without any token validation. Any client can connect and receive
    job status updates or node logs without authentication.

    Expected: Connection should be rejected (close code 1008 or similar)
    if no valid Bearer token is provided.

    Actual: Connection is accepted for all clients.
    """
    # Connect without any authentication token
    # This SHOULD fail — but it doesn't (BUG-012)
    try:
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            # If we get here, connection was accepted without auth
            # This is the bug — should have been rejected
            pytest.fail(
                "WebSocket accepted connection without authentication — "
                "BUG-012: Missing auth check in ws_logs.py"
            )
    except Exception:
        # Expected: connection should be rejected
        pass


# ===================================================================
# Disconnect cleanup
# ===================================================================


def test_ws_disconnect_cleanup_node_logs(sync_client):
    """Process should be terminated when client disconnects."""
    mock_process = AsyncMock()
    mock_process.returncode = None  # Still running
    mock_process.terminate = MagicMock()

    # readline blocks forever → simulate by raising on second call
    call_count = 0

    async def slow_readline():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return b"first line\n"
        # Simulate slow stream — return empty to end
        return b""

    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = slow_readline

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            data = ws.receive_json()
            assert "first line" in data["log"]
        # After context manager exits, process should be terminated
        # The finally block calls process.terminate() if returncode is None
        mock_process.terminate.assert_called_once()
