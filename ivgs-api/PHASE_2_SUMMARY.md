# Phase 2 Summary — WebSocket Tests

## Overview

Phase 2 implemented comprehensive WebSocket test coverage for the IVGS v5 API's two real-time streaming endpoints:

1. **`WS /api/v1/ws/nodes/{node_id}/logs`** — SSH subprocess streaming Docker container logs
2. **`WS /api/v1/ws/jobs/{job_id}/status`** — Redis pub/sub job status streaming with heartbeats

## Test Results

| Metric | Count |
|---|---|
| **Total tests written** | 26 (across 4 files) |
| **Passing** | 22 |
| **Expected failures (xfail)** | 4 (2 bugs × 2 tests each) |
| **Unexpected failures** | 0 |
| **Full suite (Phase 0 + 1 + 2)** | **197 passed, 4 xfailed** |

## Test Files

### `tests/test_ws_connection.py` — 5 tests
Connection lifecycle for both endpoints:
- ✅ Job status WebSocket accepts connection (with Redis mock)
- ✅ Node logs WebSocket accepts for valid node IDs
- ✅ Invalid node ID returns error and closes
- ✅ Process cleanup on client disconnect
- ❌ **xfail** BUG-012: No authentication check on connection

### `tests/test_ws_job_status.py` — 7 tests
Job status streaming via Redis pub/sub:
- ✅ Heartbeat sent when no pub/sub messages arrive
- ✅ Pub/sub messages forwarded to WebSocket client
- ✅ Connection terminates on COMPLETE status
- ✅ Connection terminates on ERROR status
- ✅ Redis connection failure handled gracefully
- ✅ Subscribes to correct channel (`job:{job_id}:status`)
- ✅ Unsubscribes and cleans up on close

### `tests/test_ws_node_logs.py` — 10 tests
Node logs streaming via SSH subprocess:
- ✅ SSH output lines streamed as JSON messages
- ✅ Multiple log lines handled correctly
- ✅ Service filter query parameter passed to docker command
- ✅ Tail parameter passed to docker command
- ✅ Default tail of 100 when not specified
- ✅ Process terminated on client disconnect
- ❌ **xfail** BUG-013: SSH failure triggers UnboundLocalError
- ❌ **xfail** BUG-013: Subprocess creation failure crashes finally block

### `tests/test_ws_edge_cases.py` — 4 tests (+ 2 validation tests in edge cases)
Message format and validation:
- ✅ Node log message format: `{node_id, log, timestamp}`
- ✅ Job heartbeat message format: `{type: "heartbeat", job_id}`
- ✅ Unknown node error format: `{error: "Unknown node: ..."}`
- ✅ All 6 valid node IDs accepted (node-01 through node-06)
- ✅ Invalid node IDs rejected with error
- ❌ **xfail** BUG-012: Job status accepts unauthenticated connections

## Bugs Discovered

### BUG-012 — WebSocket Endpoints Have No Authentication (HIGH)
- **File:** `app/api/v1/ws_logs.py`, lines 59 and 109
- **Impact:** Both endpoints call `websocket.accept()` without any token validation. Any client can stream node logs and job status updates.
- **Tests:** `test_ws_connect_no_auth_rejected`, `test_ws_job_status_no_auth`
- **Status:** OPEN — documented in BUGS_FOUND.md, awaiting operator approval

### BUG-013 — Unbound `process` Variable in Finally Block (MEDIUM)
- **File:** `app/api/v1/ws_logs.py`, lines 63/96
- **Impact:** If `create_subprocess_shell` raises (SSH failure), the `finally` block crashes with `UnboundLocalError` instead of clean cleanup.
- **Tests:** `test_node_logs_ssh_failure`, `test_node_logs_subprocess_create_failure_cleanup`
- **Status:** OPEN — documented in BUGS_FOUND.md, awaiting operator approval
- **Fix:** Add `process = None` before the try block

## Technical Notes

### WebSocket Test Strategy
- **Test client:** `starlette.testclient.TestClient` (synchronous) — httpx `AsyncClient` does not support WebSocket connections
- **Redis mocking:** `redis.asyncio.from_url` patched at module level; `client.pubsub()` is synchronous (returns PubSub directly), so `MagicMock` used instead of `AsyncMock` for the Redis client
- **Subprocess mocking:** `asyncio.create_subprocess_shell` patched to avoid real SSH connections
- **Import:** `from main import app` used directly (not through conftest async fixtures)

### Coverage Areas
| Category | Tests | Coverage |
|---|---|---|
| Connection lifecycle | 5 | Accept, reject, disconnect, auth |
| Job status streaming | 7 | Heartbeat, messages, terminal states, Redis errors, sub/unsub |
| Node logs streaming | 8 | Output, multi-line, filters, params, cleanup, SSH errors |
| Edge cases & format | 6 | Message schemas, node ID validation, error formats |

## Cumulative Progress

| Phase | Tests | Bugs Found | Bugs Fixed |
|---|---|---|---|
| Phase 0 — Smoke tests | 20 | BUG-001 to BUG-004 | ✅ All fixed |
| Phase 1 — CRUD + Auth | 155 | BUG-005 to BUG-011 | ✅ All fixed |
| **Phase 2 — WebSocket** | **26** | **BUG-012, BUG-013** | **⏳ Awaiting approval** |
| **Total** | **201** | **13** | **11 fixed, 2 open** |
