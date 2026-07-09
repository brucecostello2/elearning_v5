"""
Phase 2: WebSocket edge cases and message format tests.

Tests message format validation, error structure, and
various edge conditions for both WS endpoints.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient

AUTH_PATCH = "app.api.v1.ws_logs._authenticate_ws"


@pytest.fixture(autouse=True)
def _node_ip_registry(monkeypatch):
    """Seed NODE_<nn>_IP so ws_logs._node_ip resolves the six fleet nodes;
    without them every valid node resolves as unknown (error frame)."""
    for nn in ("01", "02", "03", "04", "05", "06"):
        monkeypatch.setenv(f"NODE_{nn}_IP", f"192.168.1.{int(nn)}")


@pytest.fixture
def sync_client():
    """Synchronous TestClient for WebSocket testing."""
    from main import app
    with TestClient(app) as c:
        yield c


# ===================================================================
# Message format validation
# ===================================================================


def test_ws_message_format_node_logs(sync_client):
    """Node log messages should have {node_id, log, timestamp} structure."""
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.terminate = MagicMock()
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = AsyncMock(
        side_effect=[b"test log entry\n", b""]
    )

    with patch(AUTH_PATCH, return_value=True):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-03/logs") as ws:
                data = ws.receive_json()

    assert "node_id" in data, "Missing 'node_id' field"
    assert "log" in data, "Missing 'log' field"
    assert "timestamp" in data, "Missing 'timestamp' field"
    assert data["node_id"] == "node-03"
    assert isinstance(data["log"], str)
    assert len(data["timestamp"]) > 0
    expected_keys = {"node_id", "log", "timestamp"}
    assert set(data.keys()) == expected_keys, \
        f"Unexpected keys: {set(data.keys()) - expected_keys}"


def test_ws_message_format_job_heartbeat(sync_client):
    """Job heartbeat should have {type: 'heartbeat', job_id} structure."""
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()

    call_count = 0

    async def get_msg(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise Exception("done")
        return None

    mock_pubsub.get_message = get_msg

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_redis.close = AsyncMock()

    with patch(AUTH_PATCH, return_value=True):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with sync_client.websocket_connect("/api/v1/ws/jobs/fmt-job/status") as ws:
                data = ws.receive_json()

    assert "type" in data, "Missing 'type' field"
    assert "job_id" in data, "Missing 'job_id' field"
    assert data["type"] == "heartbeat"
    assert data["job_id"] == "fmt-job"


def test_ws_unknown_node_error_format(sync_client):
    """Unknown node error should have {error: 'Unknown node: ...'} structure."""
    with patch(AUTH_PATCH, return_value=True):
        with sync_client.websocket_connect("/api/v1/ws/nodes/nonexistent/logs") as ws:
            data = ws.receive_json()

    assert "error" in data
    assert "Unknown or unregistered node" in data["error"]
    assert "nonexistent" in data["error"]


# ===================================================================
# Node ID validation
# ===================================================================


def test_ws_all_valid_node_ids(sync_client):
    """All 6 valid node IDs should be accepted."""
    valid_nodes = ["node-01", "node-02", "node-03", "node-04", "node-05", "node-06"]

    for node_id in valid_nodes:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.terminate = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=[b"ok\n", b""])

        with patch(AUTH_PATCH, return_value=True):
            with patch("asyncio.create_subprocess_shell", return_value=mock_process):
                with sync_client.websocket_connect(
                    f"/api/v1/ws/nodes/{node_id}/logs"
                ) as ws:
                    data = ws.receive_json()
                    assert data["node_id"] == node_id, f"Failed for {node_id}"


def test_ws_invalid_node_ids_rejected(sync_client):
    """Various invalid node IDs should produce error."""
    invalid_nodes = ["node-00", "node-07", "master", "node-1", "NODE-01"]

    for node_id in invalid_nodes:
        with patch(AUTH_PATCH, return_value=True):
            with sync_client.websocket_connect(
                f"/api/v1/ws/nodes/{node_id}/logs"
            ) as ws:
                data = ws.receive_json()
                assert "error" in data, f"Expected error for {node_id}, got {data}"


# ===================================================================
# BUG-012 FIXED: Authentication on WebSocket endpoints
# ===================================================================


def test_ws_job_status_no_auth(sync_client):
    """BUG-012 FIX: Job status WebSocket should reject without token.

    _authenticate_ws now validates JWT before websocket.accept().
    Unauthenticated clients receive close code 1008.
    """
    # No token → should be rejected
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/api/v1/ws/jobs/secret-job/status") as ws:
            ws.receive_json()


def test_ws_node_logs_no_auth(sync_client):
    """BUG-012 FIX: Node logs WebSocket should reject without token."""
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            ws.receive_json()
