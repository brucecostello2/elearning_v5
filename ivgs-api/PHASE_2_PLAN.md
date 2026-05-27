# Phase 2: WebSocket Tests

**Phase:** 2 — WebSocket Connection and Streaming  
**Status:** In Progress  
**Started:** 2026-05-27

---

## Actual Implementation Found

### Endpoints (in `app/api/v1/ws_logs.py`)

1. **`WS /api/v1/ws/nodes/{node_id}/logs`** — Live docker log stream from GPU node via SSH
   - Path param: `node_id` (must be in `NODE_HOSTS`: node-01 through node-06)
   - Query params: `service` (optional), `tail` (default 100)
   - Sends: `{"node_id", "log", "timestamp"}` per line
   - Error: `{"error": "Unknown node: ..."}` then close(1008)
   - Uses `asyncio.create_subprocess_shell("ssh ...")` — cannot run in test without SSH

2. **`WS /api/v1/ws/jobs/{job_id}/status`** — Real-time job progress via Redis pub/sub
   - Path param: `job_id`
   - Subscribes to Redis channel `job:{job_id}:status`
   - Sends: pub/sub messages as JSON + heartbeat `{"type": "heartbeat", "job_id"}`
   - Terminates on `COMPLETE` or `ERROR` status
   - Creates its own `redis.asyncio` connection (NOT shared `redis_client`)

### Key Observations

1. **NO authentication** — Both endpoints call `websocket.accept()` without token validation
2. **NO authorization** — Any client can connect and receive any job/node data
3. **Separate Redis connection** — Job status creates `aioredis.from_url(settings.REDIS_URL)` per WS connection
4. **SSH dependency** — Node logs requires SSH to actual GPU nodes; must be mocked for tests
5. **Rate limiting exempt** — WebSocket connections bypass `RateLimitMiddleware`

### Testing Approach

- Use `starlette.testclient.TestClient` (synchronous) — httpx AsyncClient doesn't support WebSocket
- Mock `asyncio.create_subprocess_shell` for node log tests (no real SSH)
- Mock `redis.asyncio.from_url` for job status tests (no real Redis pub/sub)
- Test authentication gap as a bug (BUG-012)

---

## Test Coverage Plan

### 1. Connection Lifecycle (5 tests) — `test_ws_connection.py`
- `test_ws_connect_job_status` — basic connection establishment
- `test_ws_connect_node_logs_valid_node` — connect to valid node-01
- `test_ws_connect_node_logs_invalid_node` — connect to unknown node → error + close(1008)
- `test_ws_connect_no_auth_accepted` — BUG: connection accepted without authentication
- `test_ws_disconnect_cleanup` — verify process/pubsub cleaned up on disconnect

### 2. Job Status Streaming (5 tests) — `test_ws_job_status.py`
- `test_job_status_heartbeat` — receives heartbeat after 5s idle
- `test_job_status_receives_update` — pub/sub message forwarded to client
- `test_job_status_terminates_on_complete` — WS closes after COMPLETE status
- `test_job_status_terminates_on_error` — WS closes after ERROR status
- `test_job_status_redis_connection_error` — Redis unavailable handling

### 3. Node Logs Streaming (5 tests) — `test_ws_node_logs.py`
- `test_node_logs_streams_output` — SSH output streamed as JSON messages
- `test_node_logs_with_service_filter` — service param passed to docker command
- `test_node_logs_with_tail_param` — tail param passed to docker command
- `test_node_logs_process_cleanup_on_disconnect` — process terminated on client disconnect
- `test_node_logs_ssh_failure` — SSH process failure handling

### 4. Edge Cases (3-5 tests) — `test_ws_edge_cases.py`
- `test_ws_message_format_node_logs` — verify JSON structure {node_id, log, timestamp}
- `test_ws_message_format_job_heartbeat` — verify {type: "heartbeat", job_id}
- `test_ws_unknown_node_error_format` — verify error message structure
- `test_ws_no_auth_bug_exposure` — BUG-012: explicitly document missing auth

**Total:** 18-20 tests planned

---

## Expected Bugs

| Bug ID | Description | Severity |
|--------|-------------|----------|
| BUG-012 | WebSocket endpoints have no authentication — any client can connect | HIGH |
| BUG-013+ | Potential: Redis connection not properly cleaned up on errors | MEDIUM |
| BUG-014+ | Potential: `process` variable used in finally before assignment | MEDIUM |
