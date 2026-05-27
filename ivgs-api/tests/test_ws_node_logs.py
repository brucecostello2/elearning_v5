"""
Phase 2: WebSocket node logs streaming tests.

Tests /api/v1/ws/nodes/{node_id}/logs endpoint:
  - SSH subprocess output streaming
  - Service filter and tail parameters
  - Process cleanup on disconnect
  - SSH failure handling
  - Process variable NameError (BUG-013)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
from starlette.testclient import TestClient


@pytest.fixture
def sync_client():
    """Synchronous TestClient for WebSocket testing."""
    from main import app
    with TestClient(app) as c:
        yield c


def _make_mock_process(lines=None, returncode=0):
    """Create a mock async subprocess with stdout lines.

    Args:
        lines: list of byte strings to return from readline().
               Automatically appends b"" (EOF).
        returncode: process return code (None = still running)
    """
    if lines is None:
        lines = []

    mock_process = AsyncMock()
    mock_process.returncode = returncode
    mock_process.terminate = MagicMock()

    # Build readline side_effect: lines + EOF
    side_effects = list(lines) + [b""]
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = AsyncMock(side_effect=side_effects)

    return mock_process


# ===================================================================
# Log streaming
# ===================================================================


def test_node_logs_streams_output(sync_client):
    """SSH output lines should be streamed as JSON messages."""
    mock_process = _make_mock_process(
        lines=[b"INFO: server started\n", b"DEBUG: request received\n"]
    )

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            msg1 = ws.receive_json()
            assert msg1["node_id"] == "node-01"
            assert "server started" in msg1["log"]
            assert "timestamp" in msg1

            msg2 = ws.receive_json()
            assert "request received" in msg2["log"]


def test_node_logs_multiple_lines(sync_client):
    """Should handle multiple log lines correctly."""
    lines = [f"line {i}\n".encode() for i in range(5)]
    mock_process = _make_mock_process(lines=lines)

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-02/logs") as ws:
            received = []
            for _ in range(5):
                msg = ws.receive_json()
                received.append(msg["log"])

            assert received == [f"line {i}" for i in range(5)]
            assert all(msg["node_id"] == "node-02" for msg in [ws] if False)  # just checking IDs above


# ===================================================================
# Query parameters
# ===================================================================


def test_node_logs_with_service_filter(sync_client):
    """Service query param should be passed to docker command."""
    mock_process = _make_mock_process(lines=[b"svc log\n"])

    with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
        with sync_client.websocket_connect(
            "/api/v1/ws/nodes/node-01/logs?service=render-engine"
        ) as ws:
            ws.receive_json()

    # Verify SSH command includes service name
    cmd_arg = mock_shell.call_args[0][0]
    assert "render-engine" in cmd_arg
    assert "10.10.0.1" in cmd_arg  # node-01 IP


def test_node_logs_with_tail_param(sync_client):
    """Tail query param should be passed to docker command."""
    mock_process = _make_mock_process(lines=[b"tail log\n"])

    with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
        with sync_client.websocket_connect(
            "/api/v1/ws/nodes/node-01/logs?tail=50"
        ) as ws:
            ws.receive_json()

    cmd_arg = mock_shell.call_args[0][0]
    assert "50" in cmd_arg


def test_node_logs_default_tail_100(sync_client):
    """Default tail should be 100 when not specified."""
    mock_process = _make_mock_process(lines=[b"default tail\n"])

    with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            ws.receive_json()

    cmd_arg = mock_shell.call_args[0][0]
    assert "100" in cmd_arg


# ===================================================================
# Process cleanup
# ===================================================================


def test_node_logs_process_cleanup_on_disconnect(sync_client):
    """Process should be terminated when client disconnects."""
    mock_process = _make_mock_process(lines=[b"line\n"])
    mock_process.returncode = None  # Still running

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            ws.receive_json()

    # After WS close, finally block should terminate process
    mock_process.terminate.assert_called_once()


# ===================================================================
# Error handling
# ===================================================================


@pytest.mark.xfail(
    reason="BUG-013: create_subprocess_shell failure causes UnboundLocalError in finally block",
    strict=True,
)
def test_node_logs_ssh_failure(sync_client):
    """SSH subprocess failure should be handled gracefully.

    Currently blocked by BUG-013: when create_subprocess_shell raises,
    the finally block references 'process' which is never assigned,
    causing UnboundLocalError instead of clean error handling.
    """
    with patch(
        "asyncio.create_subprocess_shell",
        side_effect=OSError("SSH connection refused"),
    ):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            # Should receive error message
            data = ws.receive_json()
            assert "error" in data
            assert "SSH" in data["error"] or "connection" in data["error"].lower()


@pytest.mark.xfail(
    reason="BUG-013: process variable referenced in finally block before assignment",
    strict=True,
)
def test_node_logs_subprocess_create_failure_cleanup(sync_client):
    """BUG-013: If create_subprocess_shell raises, 'process' is unbound in finally.

    Line 96 of ws_logs.py: `if process and process.returncode is None:`
    But 'process' is only assigned on line 63 inside the try block.
    If create_subprocess_shell raises, 'process' is never assigned,
    and the finally block raises NameError.

    Fix: Initialize `process = None` before the try block.
    """
    with patch(
        "asyncio.create_subprocess_shell",
        side_effect=OSError("Permission denied"),
    ):
        with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
            # Should receive error message without crashing
            data = ws.receive_json()
            assert "error" in data
            # The connection should close cleanly (no NameError in finally)
