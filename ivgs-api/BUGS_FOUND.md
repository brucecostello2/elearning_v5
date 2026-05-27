# BUGS_FOUND.md — Phase 0a/0b/0c Bug Inventory

**Project:** IVGS v5 API  
**Discovery Phase:** Phase 0a (Schema Audit)  
**Documentation Date:** 2026-05-27

This document tracks all bugs discovered during the test suite restoration project.

---

## Bug Status Summary

| Bug ID | Severity | File | Status | Resolution |
|--------|----------|------|--------|------------|
| BUG-001 | HIGH | backup.py:299 | 🟡 Test Written | Code fix (Phase 0c) |
| BUG-002 | LOW | manifests.py:85-92 | 🟡 Documented | Code deletion (Phase 0c) |
| BUG-003 | HIGH | manifests.py | 🟡 Test Written | Code fix (Phase 0c) |
| BUG-004 | HIGH | manifests.py | 🟡 Test Written | Code fix (Phase 0c) |
| BUG-005 | HIGH | backup.py | 🟡 Test Written | Code fix (Phase 0c) |
| BUG-006 | HIGH | backup.py | ⏳ Operator Decision | Add column or remove from API |
| BUG-007 | MEDIUM | quality_service.py | ⏳ Operator Decision | Add column or remove from service |
| BUG-008 | HIGH | migrations/ | ✅ RESOLVED | 5 migrations created (Phase 0b) |
| BUG-009 | HIGH | quotas.py | 🟡 Test Written | Code fix (Phase 0c) |
| BUG-010 | HIGH | quotas.py | 🟡 Test Written | Code fix (Phase 0c) |

**Total:** 10 bugs found, 1 resolved in Phase 0b, 7 with tests written, 2 awaiting operator decision

---

## BUG-001: NameError in Backup Error Handler

**Severity:** HIGH  
**Location:** `app/api/v1/backup.py`, line 299  
**Test:** `tests/test_bug_001_backup_error_handler.py`

### Description

Exception handler catches exception as `_exc` but references undefined variable `exc` in the error string.

### Evidence

```python
# backup.py line 292-299
except Exception as _exc:  # noqa: F841       ← caught as _exc
    logger.exception("Backup task failed", extra={"backup_id": backup_id})
    await db.execute(
        sa_text(
            "UPDATE backup_records SET status = 'failed', "
            "error_message = :error WHERE id = :id"
        ),
        {"id": backup_id, "error": str(exc)[:2000]},   # ← NameError: exc undefined
    )
```

### Impact

- When `_run_backup()` fails, the error handler itself crashes with `NameError`
- The backup record is never updated to "failed" status
- Error message never recorded
- Backup remains stuck in "running" state forever
- **Affected endpoint:** Background task from `POST /api/v1/backup/trigger`

### Proposed Fix

```python
{"id": backup_id, "error": str(_exc)[:2000]},  # ✅ Use _exc
```

---

## BUG-002: Dead Code in Manifests Endpoint

**Severity:** LOW  
**Location:** `app/api/v1/manifests.py`, lines 85-92  
**Test:** None required (dead code)  
**Operator Approval:** ✅ Approved for deletion (Q5 decision)

### Description

Lines 85-92 contain an unused SQLAlchemy `select()` call result assigned to `_result` that is never used. The code immediately follows with raw SQL that does the real work.

### Evidence

```python
# manifests.py lines 85-92
_result = await db.execute(  # noqa: F841
    select("*").select_from(
        __import__("sqlalchemy").text("composition_manifests")
    ).where(
        __import__("sqlalchemy").text("job_id = :job_id")
    ),
    {"job_id": job_id},
)
# Use SQLAlchemy ORM model in production:
```

### Impact

- No runtime impact (result assigned to `_result` and ignored)
- Code clutter; confusing to maintainers
- May perform an unnecessary DB query

### Proposed Fix

Delete the unused query block entirely.

---

## BUG-003: Wrong Column Names in Manifests Raw SQL

**Severity:** HIGH  
**Location:** `app/api/v1/manifests.py`, lines 99-100, 119-121, 215-236, 246-248  
**Test:** `tests/test_bug_003_manifest_field_names.py`

### Description

Raw SQL in manifests.py references three column names that do not exist in the `composition_manifests` table:

| API Code Uses | Actual DB Column | Exists? |
|---------------|------------------|---------|
| `timeline_json` | `timeline` | ❌ Column named `timeline` |
| `scene_count` | — | ❌ No such column |
| `created_at` | — | ❌ No such column in composition_manifests |

### Evidence

```sql
-- manifests.py line 99-100 (GET endpoint)
SELECT id, job_id, status, timeline_json, total_duration_ms,
       scene_count, created_at, locked_at
FROM composition_manifests WHERE job_id = :job_id
-- ❌ Fails: column "timeline_json" does not exist

-- manifests.py line 227-229 (POST/generate endpoint)
INSERT INTO composition_manifests
(id, job_id, status, timeline_json, total_duration_ms, scene_count, created_at)
VALUES (...)
-- ❌ Fails: column "timeline_json" does not exist
```

### Actual table schema (from model + migration):

```
composition_manifests: id, job_id, manifest_version, total_duration_ms,
  resolution_width, resolution_height, framerate, audio_sample_rate,
  timeline (JSONB), status, locked_at, rendered_at, checksum
```

### Impact

- **ALL manifest endpoints fail** with `UndefinedColumn` error
- GET manifest: 500 error
- Generate manifest: 500 error
- Lock manifest: 500 error (also references these columns)
- Validate manifest: Partially affected
- **Affected endpoints:**
  - `GET /api/v1/manifests/{job_id}/manifest`
  - `POST /api/v1/manifests/{job_id}/manifest/generate`
  - `POST /api/v1/manifests/{job_id}/manifest/lock`

### Proposed Fix (per Q1: fix API to match model)

```python
# Change timeline_json → timeline in all SELECT/INSERT statements
# Remove scene_count from queries (not a real column — compute from timeline JSON)
# Remove created_at from INSERT (not in composition_manifests table)
```

---

## BUG-004: Wrong Column Name in Asset Query (sha256_hash → content_hash)

**Severity:** HIGH  
**Location:** `app/api/v1/manifests.py`, lines 176, 201, 345, 354, 359  
**Test:** `tests/test_bug_004_manifest_asset_checksum.py`

### Description

Manifest generation and validation query assets with `sha256_hash` but the actual column is `content_hash`.

### Evidence

```python
# manifests.py line 176 (generate endpoint - asset fetch)
"SELECT id, scene_id, asset_type, seaweedfs_fid, sha256_hash "
"FROM assets WHERE project_id = :project_id"
# ❌ Fails: column "sha256_hash" does not exist

# manifests.py line 201
"checksum": asset.sha256_hash,  # ❌ Wrong attribute

# manifests.py line 345 (validate endpoint)
"SELECT id, sha256_hash, seaweedfs_fid FROM assets WHERE id = :id"
# ❌ Fails: column "sha256_hash" does not exist

# manifests.py lines 354, 359
asset_row.sha256_hash  # ❌ Wrong attribute
```

### Actual column (from model `app/models/asset.py:81`):

```python
content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

### Impact

- Manifest generation fails when fetching assets
- Manifest validation fails when checking checksums
- **Affected endpoints:**
  - `POST /api/v1/manifests/{job_id}/manifest/generate` (asset fetch step)
  - `POST /api/v1/manifests/{job_id}/manifest/validate`

### Proposed Fix

```python
# Change all sha256_hash → content_hash in SQL queries and attribute access
```

---

## BUG-005: Wrong Column Name in Backup (storage_path → backup_path)

**Severity:** HIGH  
**Location:** `app/api/v1/backup.py`, lines 42, 141, 227, 263-274, 304, 312  
**Test:** `tests/test_bug_005_backup_field_names.py`

### Description

Backup API code uses `storage_path` throughout but the model column is `backup_path`.

### Evidence

```python
# backup.py Pydantic schema (line 42)
storage_path: Optional[str] = None  # ❌ Pydantic model uses wrong name

# backup.py line 141 (list endpoint)
storage_path=r.storage_path,  # ❌ DB column is backup_path

# backup.py line 268 (_run_backup)
"size_bytes = :size, storage_path = :path, "  # ❌ Wrong column name
```

### Actual column (from model `app/models/backup_record.py:41`):

```python
backup_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
```

### Impact

- List backup records: fails with `AttributeError` on `r.storage_path`
- Background backup task: fails with `UndefinedColumn` on `storage_path`
- Verify endpoint: passes wrong column value to `_run_verification`
- **Affected endpoints:**
  - `GET /api/v1/backup/records`
  - `POST /api/v1/backup/trigger` (background task)
  - `POST /api/v1/backup/{id}/verify`

### Proposed Fix

```python
# Change all storage_path → backup_path in SQL queries and Pydantic schemas
```

---

## BUG-006: Non-existent Column in Backup SQL (error_message)

**Severity:** HIGH  
**Location:** `app/api/v1/backup.py`, lines 43, 142, 282, 297, 331  
**Test:** Awaiting operator decision  
**Status:** ⏳ Operator decision needed

### Description

Raw SQL references `error_message` column that does not exist in the `backup_records` table or ORM model.

### Evidence

```python
# backup.py line 43 (Pydantic schema)
error_message: Optional[str] = None

# backup.py line 282 (_run_backup - failure update)
"error_message = :error, completed_at = :completed_at "

# backup.py line 297 (_run_backup - exception handler)
"error_message = :error WHERE id = :id"
```

### Actual model (`app/models/backup_record.py`): No `error_message` column defined.

### Impact

- All UPDATE statements that set `error_message` fail with `UndefinedColumn`
- Backup failure states never recorded
- Combined with BUG-001, backup error handling is completely broken

### Operator Decision Required

**Option A (recommended):** Add `error_message` column to BackupRecord model + create migration  
**Option B:** Remove all `error_message` references from backup.py

---

## BUG-007: Non-existent Attribute in Quality Service (review_notes)

**Severity:** MEDIUM  
**Location:** `app/api/v1/quality.py` (quality service code)  
**Test:** Awaiting operator decision  
**Status:** ⏳ Operator decision needed

### Description

Quality service code references `review_notes` attribute that doesn't exist in the `AssetQualityScore` model.

### Operator Decision Required

**Option A (recommended):** Add `review_notes` column to AssetQualityScore model + migration  
**Option B:** Remove `review_notes` references from quality service

---

## BUG-008: Missing Columns in Migrations ✅ RESOLVED

**Severity:** HIGH  
**Location:** `migrations/versions/`  
**Status:** ✅ RESOLVED in Phase 0b

### Resolution

5 migrations created in Phase 0b:

| Migration | Column | Table |
|-----------|--------|-------|
| 0015 | `is_active` | `users` |
| 0016 | `created_by` | `projects` |
| 0017 | `job_id` | `asset_quality_scores` |
| 0018 | `description` | `retention_policies` |
| 0019 | `description` | `prompt_tags` |

All tested with upgrade/downgrade cycles. 153 existing tests pass.

---

## BUG-009: Wrong Column Name in Quotas (quota_bytes → max_bytes)

**Severity:** HIGH  
**Location:** `app/api/v1/quotas.py`, lines 61, 62, 67, 96  
**Test:** `tests/test_bug_009_quota_field_names.py`

### Description

Quotas API uses `quota_bytes` in raw SQL but the actual DB column is `max_bytes`.

### Evidence

```python
# quotas.py line 61 (GET endpoint - reading row)
used = row.used_bytes or 0     # ❌ Actual column: current_bytes (see BUG-010)
quota = row.quota_bytes or 0   # ❌ Actual column: max_bytes

# quotas.py line 96 (PUT endpoint - INSERT/UPSERT)
"INSERT INTO storage_quotas (entity_type, entity_id, quota_bytes, alert_threshold_pct) "
# ❌ Fails: column "quota_bytes" does not exist
```

### Actual column (from model `app/models/storage_quota.py`):

```python
max_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

### Impact

- GET quota: row attribute access fails (`AttributeError` on `row.quota_bytes`)
- PUT quota (upsert): SQL fails with `UndefinedColumn`
- **Affected endpoints:**
  - `GET /api/v1/quotas/{entity_type}/{entity_id}`
  - `PUT /api/v1/quotas/{entity_type}/{entity_id}`

### Proposed Fix

```python
# Change all quota_bytes → max_bytes in SQL and attribute access
```

---

## BUG-010: Wrong Column Name in Quotas (used_bytes → current_bytes)

**Severity:** HIGH  
**Location:** `app/api/v1/quotas.py`, line 60  
**Test:** `tests/test_bug_009_quota_field_names.py` (combined with BUG-009)

### Description

Quotas API uses `used_bytes` in row attribute access but the actual DB column is `current_bytes`.

### Evidence

```python
# quotas.py line 60
used = row.used_bytes or 0   # ❌ Actual column: current_bytes
```

### Actual column (from model `app/models/storage_quota.py`):

```python
current_bytes: Mapped[int] = mapped_column(
    BigInteger, nullable=False, server_default=text("0"),
)
```

### Impact

- GET quota fails with `AttributeError` — `used_bytes` not in row
- Combined with BUG-009, the entire quota API is non-functional
- **Affected endpoint:** `GET /api/v1/quotas/{entity_type}/{entity_id}`

### Proposed Fix

```python
# Change used_bytes → current_bytes in attribute access
```

---

## Summary Statistics

**By Severity:**
- HIGH: 9 bugs (1 resolved, 6 test-ready, 2 awaiting decision)
- MEDIUM: 1 bug (awaiting decision)
- LOW: 1 bug (approved for deletion)

**Production Impact:**
- Before Phase 0b: 🔴 BLOCKED (10 bugs)
- After Phase 0b: 🟡 PARTIALLY BLOCKED (9 code bugs remaining)
- After Phase 0c: 🟢 READY (all bugs fixed)

**Broken Endpoints:**
1. `GET /api/v1/manifests/{job_id}/manifest` — BUG-003
2. `POST /api/v1/manifests/{job_id}/manifest/generate` — BUG-003, BUG-004
3. `POST /api/v1/manifests/{job_id}/manifest/lock` — BUG-003
4. `POST /api/v1/manifests/{job_id}/manifest/validate` — BUG-004
5. `GET /api/v1/backup/records` — BUG-005, BUG-006
6. `POST /api/v1/backup/trigger` — BUG-001, BUG-005, BUG-006
7. `POST /api/v1/backup/{id}/verify` — BUG-005
8. `GET /api/v1/quotas/{et}/{eid}` — BUG-009, BUG-010
9. `PUT /api/v1/quotas/{et}/{eid}` — BUG-009

---

## Testing Protocol (per TEST_IMPLEMENTATION_PLAN_v3.md)

1. ✅ Write test exposing bug
2. ✅ Mark with `@pytest.mark.xfail(reason="BUG-XXX: description")`
3. ✅ Commit test separately
4. 🛑 HALT — present proposed fixes to operator
5. ⏳ After approval, apply fix in separate commit
6. ⏳ Remove xfail marker
7. ⏳ Verify test passes

---

## Phase 1 Bug Discoveries

### BUG-011: Rate limiter does not handle Redis failures gracefully

| Field | Value |
|-------|-------|
| **Severity** | HIGH |
| **Location** | `app/middleware/rate_limit.py:67-147` (dispatch method) |
| **Test File** | `tests/test_rate_limiting_edge_cases.py::test_rate_limit_redis_incr_failure` |
| **Status** | ✅ FIXED — Option A (Fail Open) applied 2026-05-27 |

**Description:**  
The `RateLimitMiddleware.dispatch()` method makes several `await redis_client.*()` calls (`.exists()`, `.incr()`, `.expire()`, `.set()`, `.delete()`) without any try/except error handling. When Redis is unavailable (connection refused, timeout, etc.), the exception propagates unhandled through the middleware stack, crashing the request.

**Evidence:**  
```python
# rate_limit.py:83 — no error handling
if await redis_client.exists(lockout_key):  # crashes if Redis down
    ...
current_count = await redis_client.incr(rate_key)  # crashes if Redis down
```

**Impact:**  
- All non-GET API requests crash with unhandled exception when Redis is down
- Effectively a full API outage caused by a Redis dependency failure
- No graceful degradation — should either fail-open (allow requests) or return structured 503

**Fix Applied:**  
Wrapped all Redis calls in `dispatch()` with two `try/except Exception` blocks:
1. **Pre-request block** (lockout check + rate limit counter): on Redis failure, logs warning and allows request through
2. **Post-request block** (login failure tracking): on Redis failure, logs warning but does not crash response

Commit: see git log for `fix: BUG-011`

---

## BUG-012 — WebSocket Endpoints Have No Authentication

| Field | Value |
|---|---|
| **ID** | BUG-012 |
| **Severity** | HIGH |
| **Phase** | Phase 2 — WebSocket Tests |
| **Status** | ✅ FIXED |
| **File** | `app/api/v1/ws_logs.py` |
| **Lines** | 59 (`stream_node_logs`), 109 (`stream_job_status`) |
| **Test(s)** | `test_ws_connect_no_auth_rejected`, `test_ws_job_status_no_auth` |

**Description:**  
Both WebSocket endpoints (`/ws/nodes/{node_id}/logs` and `/ws/jobs/{job_id}/status`) call `websocket.accept()` immediately without any authentication or authorization check. Any client can connect and:
- Stream real-time Docker logs from any infrastructure node (contains sensitive system data)
- Receive real-time job status updates for any job ID (may contain project details)

**Reproduction:**
```python
# No auth headers, no token — connection is accepted
with TestClient(app) as client:
    with client.websocket_connect("/api/v1/ws/jobs/any-job/status") as ws:
        data = ws.receive_json()  # Receives heartbeat — fully functional
```

**Expected Behavior:**  
WebSocket connections should validate a Bearer token (e.g., via `?token=JWT` query parameter or `Sec-WebSocket-Protocol` header) before calling `websocket.accept()`. Unauthenticated clients should receive close code 1008 (Policy Violation).

**Fix Applied:**  
Added `_authenticate_ws()` helper function that validates JWT token from `?token=<JWT>` query
parameter before `websocket.accept()`. The helper:
1. Extracts token from query params
2. Decodes and validates JWT (type=access, valid signature)
3. Verifies user exists in DB and is active
4. Closes with code 1008 (Policy Violation) on any failure

Both `stream_node_logs` and `stream_job_status` now call `_authenticate_ws()` before accepting.

Commit: see git log for `fix: BUG-012`

---

## BUG-013 — Unbound `process` Variable in Node Logs Finally Block

| Field | Value |
|---|---|
| **ID** | BUG-013 |
| **Severity** | MEDIUM |
| **Phase** | Phase 2 — WebSocket Tests |
| **Status** | ✅ FIXED |
| **File** | `app/api/v1/ws_logs.py` |
| **Lines** | 63 (assignment), 96 (finally reference) |
| **Test(s)** | `test_node_logs_ssh_failure`, `test_node_logs_subprocess_create_failure_cleanup` |

**Description:**  
In `stream_node_logs()`, the `process` variable is assigned on line 63 inside the `try` block:
```python
try:
    process = await asyncio.create_subprocess_shell(...)  # line 63
    ...
finally:
    if process and process.returncode is None:  # line 96 — NameError!
        process.terminate()
```

If `create_subprocess_shell` raises an exception (e.g., SSH failure, permission denied), `process` is never assigned, and the `finally` block raises `UnboundLocalError: cannot access local variable 'process' before assignment`.

**Reproduction:**
```python
with patch("asyncio.create_subprocess_shell", side_effect=OSError("SSH failed")):
    with client.websocket_connect("/api/v1/ws/nodes/node-01/logs") as ws:
        # Raises UnboundLocalError instead of sending error message
```

**Expected Behavior:**  
The error should be caught and an error message sent to the client. The `finally` block should not crash.

**Fix Applied:**  
Initialized `process = None` before the `try` block:
```python
process = None  # Initialize before try block (BUG-013 fix)
try:
    process = await asyncio.create_subprocess_shell(...)
    ...
finally:
    if process and process.returncode is None:
        process.terminate()
```

Commit: see git log for `fix: BUG-013`

---

## BUG-014: Backup Trigger RBAC Bypass — No-Op `require_admin` in `app/api/deps.py`

| Field | Value |
|---|---|
| **Severity** | CRITICAL |
| **Phase Found** | Phase 3 — API Endpoint Tests |
| **Status** | ✅ FIXED (2026-05-27) |
| **Affected Endpoint** | `POST /api/v1/backup/trigger` |
| **Root Cause** | `app/api/v1/backup.py` imports `require_admin` from `app.api.deps` which contains a no-op stub (`async def require_admin(user=None): pass`) instead of the real RBAC dependency in `app.core.rbac` |

**Description:**  
The backup trigger endpoint is annotated with `Depends(require_admin)` but the import resolves to a placeholder in `app/api/deps.py` that performs no role check. As a result, **any authenticated user** (operator, viewer) — and even unauthenticated requests that pass body validation — can trigger a full database backup.

**Reproduction:**
```python
# Operator should be denied but gets 200
r = await client.post(
    "/api/v1/backup/trigger",
    json={"backup_type": "full_db"},
    headers={"Authorization": f"Bearer {operator_token}"},
)
assert r.status_code == 200  # BUG: should be 403
```

**Expected Behavior:**  
Only admin users should be able to trigger backups. Operators and viewers should receive 403 PERMISSION_DENIED.

**Proposed Fix:**  
Change the import in `app/api/v1/backup.py` line 22:
```python
# Before (broken):
from app.api.deps import get_current_user, get_db, require_admin

# After (fixed):
from app.api.deps import get_current_user, get_db
from app.core.rbac import require_admin
```

**Fix Applied:**  
Changed import in `app/api/v1/backup.py` line 22 from `app.api.deps` to `app.core.rbac`.
Commit: see git log for `fix: BUG-014`

**Verification Tests (all passing):**
- `tests/test_api_backup.py::TestTriggerBackup::test_trigger_backup_operator_denied`
- `tests/test_api_backup.py::TestTriggerBackup::test_trigger_backup_unauthenticated`
- `tests/test_api_rbac.py::TestRbacBackup::test_viewer_cannot_trigger_backup`
- `tests/test_api_rbac.py::TestRbacBackup::test_operator_cannot_trigger_backup`

---

## BUG-015: Quotas RBAC Bypass — Same No-Op `require_admin` Issue

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Phase Found** | Phase 3 — API Endpoint Tests |
| **Status** | ✅ FIXED (2026-05-27) |
| **Affected Endpoint** | `PUT /api/v1/quotas/{entity_type}/{entity_id}` |
| **Root Cause** | `app/api/v1/quotas.py` imports `require_admin` from `app.api.deps` (same no-op stub as BUG-014) |

**Description:**  
The quota-setting endpoint is annotated with `Depends(require_admin)` but uses the no-op placeholder, allowing any authenticated user to modify storage quotas.

**Reproduction:**
```python
# Operator should be denied but gets 200/500
r = await client.put(
    "/api/v1/quotas/project/{project_id}",
    json={"quota_bytes": 1073741824, "alert_threshold_pct": 80.0},
    headers={"Authorization": f"Bearer {operator_token}"},
)
# BUG: should be 403 PERMISSION_DENIED
```

**Expected Behavior:**  
Only admin users should be able to set quotas. Operators and viewers should receive 403 PERMISSION_DENIED.

**Proposed Fix:**  
Change the import in `app/api/v1/quotas.py`:
```python
# Before (broken):
from app.api.deps import get_current_user, get_db, require_admin

# After (fixed):
from app.api.deps import get_current_user, get_db
from app.core.rbac import require_admin
```

**Note:** The root cause for both BUG-014 and BUG-015 is the `require_admin` stub in `app/api/deps.py`. A comprehensive fix should either (a) remove the stub entirely and audit all imports, or (b) replace the stub with a proper re-export of `app.core.rbac.require_admin`.

**Fix Applied:**  
Changed import in `app/api/v1/quotas.py` from `app.api.deps` to `app.core.rbac`.
Commit: see git log for `fix: BUG-015`

**Verification Tests (all passing):**
- `tests/test_api_rbac.py::TestRbacQuotas::test_operator_cannot_set_quota`
- `tests/test_api_rbac.py::TestRbacQuotas::test_viewer_cannot_set_quota`

---

**End of Document**
