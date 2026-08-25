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


# ---------------------------------------------------------------------------
# REMOVED 2026-08-25 (WP-48-TELEMETRY): `test_ws_message_format_node_logs`. It
# asserted the {node_id, log, timestamp} envelope of a handler that could never
# produce one -- see tests/test_ws_node_logs.py for the full account. The
# replacement envelope ({timestamp, level, message}, with a nullable level) is
# asserted in tests/test_wp48_telemetry.py against the real source.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# REMOVED 2026-08-25 (WP-48-TELEMETRY): `test_ws_unknown_node_error_format`,
# `test_ws_all_valid_node_ids`, `test_ws_invalid_node_ids_rejected` -- all three
# over the removed node-log WebSocket. What they were really testing (that an
# unknown node is named rather than silently empty, and that node-07 is not a
# pipeline node) now holds on the HTTP route and is asserted in
# tests/test_wp48_telemetry.py and tests/test_wp24_node_honesty.py.
# ---------------------------------------------------------------------------


def test_unknown_node_is_named_on_the_http_log_route(monkeypatch):
    """The property the three removed tests were reaching for, on the route that
    actually serves logs."""
    from app.core.node_logs import fetch_logs, list_containers

    for node_id in ("node-00", "node-99", "master", "NODE-01"):
        monkeypatch.delenv(f"NODE_{node_id.split('-')[-1]}_IP", raising=False)
        out = list_containers(node_id)
        assert out["available"] is False, node_id
        assert out["reason"], node_id

    logs = fetch_logs("node-99", "anything", tail=5)
    assert logs["available"] is False
    assert logs["lines"] == []


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


def test_node_logs_require_a_bearer_token_on_the_http_route(sync_client):
    """WP-48: the node-log WebSocket is gone, so `test_ws_node_logs_no_auth` was
    passing on a 404 rather than on an auth rejection. The property it wanted --
    node logs are not readable unauthenticated -- now belongs to the HTTP route,
    which sits behind `Depends(get_current_user)`."""
    r = sync_client.get("/api/v1/nodes/node-01/logs?container=x&tail=1")
    assert r.status_code in (401, 403), r.status_code
