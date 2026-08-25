"""
Phase 2: WebSocket connection lifecycle tests.

Tests connection establishment, invalid node handling,
authentication enforcement, and disconnect cleanup for:
  - /api/v1/ws/jobs/{job_id}/status
  - /api/v1/ws/jobs/{job_id}/status
    (the node-log WebSocket was removed by WP-48 -- see test_ws_node_logs.py)
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


# ---------------------------------------------------------------------------
# REMOVED 2026-08-25 (WP-48-TELEMETRY): three tests over
# `WS /api/v1/ws/nodes/{node_id}/logs` -- valid node, invalid node, and process
# cleanup on disconnect. All three patched `asyncio.create_subprocess_shell`, so
# all three passed while the endpoint could not emit a line in production: it
# shelled out to `ssh` from a container with no ssh binary, no key and no docker
# CLI. The route is gone; its removal is pinned in tests/test_ws_node_logs.py,
# and the working replacement is covered by tests/test_wp48_telemetry.py.
# ---------------------------------------------------------------------------


def test_node_log_websocket_route_is_gone():
    """WP-48: node logs are GET /api/v1/nodes/{id}/logs, not a WebSocket."""
    from app.api.v1 import ws_logs

    paths = [getattr(r, "path", "") for r in ws_logs.router.routes]
    assert not any("nodes" in p and "logs" in p for p in paths), paths


# ===================================================================
# Authentication enforcement (BUG-012 — FIXED)
# ===================================================================


def test_ws_connect_no_auth_rejected(sync_client):
    """WebSocket connection without token should be rejected with close 1008.

    BUG-012 FIX: _authenticate_ws validates the JWT from the query parameter
    before websocket.accept(). Unauthenticated clients get close code 1008.

    WP-48: retargeted from the removed node-log route to `/ws/jobs/{id}/status`.
    Pointed at a route that no longer exists, this test passed for the wrong
    reason -- a 404 raises exactly like a 1008 does through TestClient -- so it
    asserted nothing about authentication at all.
    """
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/api/v1/ws/jobs/test-job-123/status") as ws:
            ws.receive_json()  # Should not get here


def test_ws_connect_invalid_token_rejected(sync_client):
    """WebSocket connection with an invalid token should be rejected. WP-48:
    retargeted from the removed node-log route, same reason as above."""
    with pytest.raises(Exception):
        with sync_client.websocket_connect(
            "/api/v1/ws/jobs/test-job-123/status?token=invalid-jwt-garbage"
        ) as ws:
            ws.receive_json()


# ===================================================================
# Disconnect cleanup
# ===================================================================


# REMOVED 2026-08-25 (WP-48-TELEMETRY): `test_ws_disconnect_cleanup_node_logs`.
# It asserted `process.terminate()` on disconnect for a subprocess that, in
# production, had already exited before the first read -- `ssh` is not installed
# in this container. See tests/test_ws_node_logs.py.
