"""
Phase 2: WebSocket node logs streaming tests.

Tests /api/v1/ws/nodes/{node_id}/logs endpoint:
  - SSH subprocess output streaming
  - Service filter and tail parameters
  - Process cleanup on disconnect
  - SSH failure handling (BUG-013 — FIXED)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
from starlette.testclient import TestClient

AUTH_PATCH = "app.api.v1.ws_logs._authenticate_ws"


@pytest.fixture(autouse=True)
def _registry_env(monkeypatch):
    """Populate node registry env so ws_logs._node_ip resolves test targets."""
    _reg = {"01": "192.168.1.90", "02": "192.168.1.91", "03": "192.168.1.92",
            "04": "192.168.1.93", "05": "192.168.1.94", "06": "192.168.1.95"}
    for _n, _ip in _reg.items():
        monkeypatch.setenv(f"NODE_{_n}_IP", _ip)


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

    with patch(AUTH_PATCH, return_value=True):
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

    with patch(AUTH_PATCH, return_value=True):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-02/logs") as ws:
                received = []
                for _ in range(5):
                    msg = ws.receive_json()
                    received.append(msg["log"])
                assert received == [f"line {i}" for i in range(5)]


# ===================================================================
# Query parameters
# ===================================================================


def test_node_logs_with_service_filter(sync_client):
    """Service query param should be passed to docker command."""
    mock_process = _make_mock_process(lines=[b"svc log\n"])

    with patch(AUTH_PATCH, return_value=True):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
            with sync_client.websocket_connect(
                "/api/v1/ws/nodes/node-01/logs?service=render-engine"
            ) as ws:
                ws.receive_json()

    cmd_arg = mock_shell.call_args[0][0]
    assert "render-engine" in cmd_arg
    assert "192.168.1.90" in cmd_arg


def test_node_logs_with_tail_param(sync_client):
    """Tail query param should be passed to docker command."""
    mock_process = _make_mock_process(lines=[b"tail log\n"])

    with patch(AUTH_PATCH, return_value=True):
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

    with patch(AUTH_PATCH, return_value=True):
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

    with patch(AUTH_PATCH, return_value=True):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
                ws.receive_json()

    mock_process.terminate.assert_called_once()


# ===================================================================
# Error handling — BUG-013 FIXED
# ===================================================================


def test_node_logs_ssh_failure(sync_client):
    """SSH subprocess failure should be handled gracefully.

    BUG-013 FIX: process = None initialised before try block, so the
    finally block no longer raises UnboundLocalError when subprocess
    creation fails.
    """
    with patch(AUTH_PATCH, return_value=True):
        with patch(
            "asyncio.create_subprocess_shell",
            side_effect=OSError("SSH connection refused"),
        ):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
                data = ws.receive_json()
                assert "error" in data


def test_node_logs_subprocess_create_failure_cleanup(sync_client):
    """BUG-013 FIX: process = None before try prevents NameError in finally.

    When create_subprocess_shell raises, the finally block should
    safely skip termination (process is None) and not crash.
    """
    with patch(AUTH_PATCH, return_value=True):
        with patch(
            "asyncio.create_subprocess_shell",
            side_effect=OSError("Permission denied"),
        ):
            with sync_client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
                data = ws.receive_json()
                assert "error" in data
