"""
Phase 2: WebSocket connection lifecycle tests.

Tests connection establishment, invalid node handling,
authentication enforcement, and disconnect cleanup for:
  - /api/v1/ws/jobs/{job_id}/status
  - /api/v1/ws/nodes/{node_id}/logs
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient


# ── helpers ──────────────────────────────────────────────────────────

AUTH_PATCH = "app.api.v1.ws_logs._authenticate_ws"


@pytest.fixture(autouse=True)
def _node_ip_registry(monkeypatch):
    """ws_logs._node_ip resolves a node's host from NODE_<nn>_IP env vars.
    The test process doesn't carry the deploy env, so seed the six fleet
    nodes; otherwise every valid node resolves as unknown and the handler
    returns the error frame instead of a log frame."""
    for nn in ("01", "02", "03", "04", "05", "06"):
        monkeypatch.setenv(f"NODE_{nn}_IP", f"192.168.1.{int(nn)}")


@pytest.fixture
def sync_client():
    """Synchronous TestClient for WebSocket testing.

    httpx AsyncClient does not support WebSocket — must use
    starlette's TestClient which wraps the ASGI app synchronously.
    """
    from main import app
    with TestClient(app) as c:
        yield c


def _ws_token_url(base_path: str) -> str:
    """Append a dummy token param (used with auth mocked out)."""
    sep = "&" if "?" in base_path else "?"
    return f"{base_path}{sep}token=mock-jwt"


# ===================================================================
# Basic connection
# ===================================================================


def test_ws_connect_job_status(sync_client):
    """WebSocket /ws/jobs/{job_id}/status should accept connection."""
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

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/test-job-123/status") as ws:
                data = ws.receive_json()
                assert data["type"] == "heartbeat"
                assert data["job_id"] == "test-job-123"


def test_ws_connect_node_logs_valid_node(sync_client):
    """WebSocket /ws/nodes/{node_id}/logs should accept for valid node."""
    mock_process = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.returncode = 0
    mock_process.stdout.readline = AsyncMock(
        side_effect=[b"2026-05-27 log line 1\n", b""]
    )

    with patch(AUTH_PATCH, return_value=True):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
                data = ws.receive_json()
                assert data["node_id"] == "node-01"
                assert "log line 1" in data["log"]
                assert "timestamp" in data


def test_ws_connect_node_logs_invalid_node(sync_client):
    """WebSocket /ws/nodes/{invalid}/logs should send error and close(1008)."""
    with patch(AUTH_PATCH, return_value=True):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-99/logs") as ws:
            data = ws.receive_json()
            assert "error" in data
            assert "Unknown or unregistered node" in data["error"]
            assert "node-99" in data["error"]


# ===================================================================
# Authentication enforcement (BUG-012 — FIXED)
# ===================================================================


def test_ws_connect_no_auth_rejected(sync_client):
    """WebSocket connection without token should be rejected with close 1008.

    BUG-012 FIX: _authenticate_ws now validates JWT token from query parameter
    before websocket.accept(). Unauthenticated clients get close code 1008.
    """
    # Connect without any token — should be rejected
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            ws.receive_json()  # Should not get here


def test_ws_connect_invalid_token_rejected(sync_client):
    """WebSocket connection with invalid token should be rejected."""
    with pytest.raises(Exception):
        with sync_client.websocket_connect(
            "/api/v1/ws/nodes/node-01/logs?token=invalid-jwt-garbage"
        ) as ws:
            ws.receive_json()


# ===================================================================
# Disconnect cleanup
# ===================================================================


def test_ws_disconnect_cleanup_node_logs(sync_client):
    """Process should be terminated when client disconnects."""
    mock_process = AsyncMock()
    mock_process.returncode = None  # Still running
    mock_process.terminate = MagicMock()

    call_count = 0

    async def slow_readline():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return b"first line\n"
        return b""

    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = slow_readline

    with patch(AUTH_PATCH, return_value=True):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
                data = ws.receive_json()
                assert "first line" in data["log"]
    mock_process.terminate.assert_called_once()
