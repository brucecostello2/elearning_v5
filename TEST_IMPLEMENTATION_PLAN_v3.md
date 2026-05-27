# Test Implementation Plan v3 — Final Corrected Plan

**Date:** 2026-05-27
**Document:** v3.0 — Incorporates 5 operator corrections + Phase 7 addition
**Baseline:** TEST_IMPLEMENTATION_PLAN_v2_REVISIONS.md
**Workspace:** `/home/ubuntu/test_workspace/`

---

## Document History

| Version | Date | Changes |
|---|---|---|
| v1 | 2026-05-27 | Initial test implementation plan |
| v2 | 2026-05-27 | Response to 22-item review (A1-K2), schema audit, 8 bugs found |
| **v3** | **2026-05-27** | **5 corrections + Phase 7 (Defect #10). Plan lock candidate.** |

### v2 → v3 Change Summary

| # | Correction | What Changed |
|---|---|---|
| C1 | Phase 4 scope criteria | Replaced 60% coverage skip rule with TWO-PART test: ≥75% branch + zero unreachable methods |
| C2 | Branch coverage gate | Added mandatory post-Phase 4 analysis; 65% is floor, not ceiling |
| C3 | Bug fix authority | Removed Open Question 4; explicit halt-and-report protocol for ALL bugs |
| C4 | Phase 6 expansion | SeaweedFS + TimescaleDB in scope; Phase 6 grows to 22-30h |
| C5 | Critical paths table | Expanded with specific test function names per path |
| +P7 | Phase 7 added | Defect #10 — Test Directory Scope Unification (8-12h) |

### What Did NOT Change From v2

The following v2 content is accepted and carried forward without modification:

- Schema audit results and 8-bug inventory (Section B1, H1)
- WebSocket testing approach (Section C1, C2)
- Service classification audit (Section D1)
- Phase 5 removal (Section F1)
- Dead code analysis (Section H2)
- Regression protection script (Section I1)
- CI runtime projections (Section J1, J2)
- Sandbox-to-production transition plan (Section K1, K2)
- Effort model per-test-category (Section A1)
- All appendix raw data

---

## Table of Contents

1. [Effort Estimates & Confidence Intervals](#1-effort-estimates--confidence-intervals)
2. [Phase 0: Schema Migrations & Bug Decisions](#2-phase-0-schema-migrations--bug-decisions)
3. [Phase 1: Rate Limiting Tests](#3-phase-1-rate-limiting-tests)
4. [Phase 2: WebSocket Tests](#4-phase-2-websocket-tests)
5. [Phase 3: Untested API Endpoints](#5-phase-3-untested-api-endpoints)
6. [Phase 4: Service Layer Tests](#6-phase-4-service-layer-tests) ← **CORRECTED (C1)**
7. [Phase 6: Integration Tests](#7-phase-6-integration-tests) ← **EXPANDED (C4)**
8. [Phase 7: Defect #10 — Test Directory Scope Unification](#8-phase-7-defect-10--test-directory-scope-unification) ← **NEW**
9. [Coverage Targets & Gates](#9-coverage-targets--gates) ← **CORRECTED (C2)**
10. [Critical Operational Paths](#10-critical-operational-paths) ← **EXPANDED (C5)**
11. [Bug Discovery & Fix Protocol](#11-bug-discovery--fix-protocol) ← **CORRECTED (C3)**
12. [Reliability Claims](#12-reliability-claims)
13. [Regression Protection](#13-regression-protection)
14. [CI Integration](#14-ci-integration)
15. [Sandbox-to-Production Transition](#15-sandbox-to-production-transition)
16. [Open Questions](#16-open-questions)
17. [Revised Timeline Summary](#17-revised-timeline-summary)
18. [Risk Register](#18-risk-register)
19. [Appendix: Audit Raw Data](#19-appendix-audit-raw-data)

---

## 1. Effort Estimates & Confidence Intervals

### Per-Test Effort Model (unchanged from v2)

| Test Category | Time per Test | Justification |
|---|---|---|
| API CRUD (happy path) | 10 min | Pattern exists, copy+adapt |
| API error paths (404, 403, 422) | 8 min | Simple variations |
| Rate limit tests | 20 min | New mock patterns needed |
| WebSocket tests | 30 min | Unproven approach, async timing |
| Service unit (pure DB) | 15 min | Direct DB, no HTTP layer |
| Service unit (external deps) | 25 min | Mock setup per external dep |
| Integration tests | 40 min | Container setup, teardown |
| First test in new file | 45 min | Fixture setup, imports, debugging |

### Phase Estimates (v3 — includes C1, C4, P7 adjustments)

| Phase | Tests | Est. Hours | Contingency | Total |
|---|---|---|---|---|
| Phase 0: Migrations + Bugs | N/A | 8h | +4-8h | **12-16h** |
| Phase 1: Rate Limiting | 15 | 5h | +3-7h | **8-12h** |
| Phase 2: WebSocket | 12 | 6h | +4-10h | **10-16h** |
| Phase 3: API Endpoints | 33 | 7h | +3-7h | **10-14h** |
| Phase 4: Services | 89-115 | 27h | +9-23h | **36-50h** |
| Phase 6: Integration | 26-34 | 16h | +6-14h | **22-30h** |
| Phase 7: Directory Unification | varies | 8h | +2-8h | **10-16h** |
| **TOTAL** | **~175-220** | **77h** | **+31-77h** | **108-154h** |

### Confidence Intervals

| Scenario | Hours | Probability |
|---|---|---|
| Best case (no surprises) | 108h | 15% |
| Expected (normal issues) | 131h | 50% |
| Worst case (major blockers) | 154h | 85% |
| Catastrophic (plan revision needed) | 180h+ | 95% |

**Calendar time:** 3-5 weeks focused agent work.

**Halt-and-report gates:** Every phase boundary. If contingency consumed,
stop and report before continuing.

---

## 2. Phase 0: Schema Migrations & Bug Decisions

**Effort:** 12-16h | **Blocks:** Phase 3 (backup, manifests)

### Phase 0a: Schema Audit (2h) — COMPLETED

Findings from v2 audit (carried forward, not repeated):
- 5 columns in models missing from migrations
- 8 production bugs discovered (6 HIGH, 1 MEDIUM, 1 LOW)
- Full evidence in Appendix A, B, C

### Phase 0b: New Alembic Migrations (4h)

```
→ 0015_add_users_is_active.py
→ 0016_add_projects_created_by.py
→ 0017_add_quality_scores_job_id.py
→ 0018_add_retention_description.py
→ 0019_add_prompt_tags_description.py
```

### Phase 0c: Bug Halt-and-Report (2-4h)

**Process (per Correction 3 — see Section 11 for full protocol):**

All 8 bugs (BUG-001 through BUG-008) require operator decisions before
fixes are applied. At Phase 0c start:

1. Present consolidated `BUGS_FOUND.md` with all 8 bugs
2. For each bug: document file, line, evidence, severity, proposed fix
3. **HALT** — wait for operator approval per bug
4. Operator approves/modifies fix direction for each
5. Agent applies approved fixes in separate `fix:` commits

**BUG-003 through BUG-006** (schema mismatches in manifests.py and backup.py)
are particularly critical: operator must decide fix-in-API vs fix-in-model
before Phase 3 tests can be written. This is Open Question 1.

### Phase 0d: Verification (2h)

```bash
alembic upgrade head            # Clean run
alembic downgrade base          # Full downgrade
alembic upgrade head            # Re-apply — must be idempotent
pytest tests/ -q --tb=short     # 153 existing tests still pass
```

### Phase 0 Exit Criteria

- [ ] All 5 new migrations created and tested
- [ ] `BUGS_FOUND.md` presented to operator
- [ ] Operator decisions received for all 8 bugs
- [ ] Approved bug fixes applied in separate commits
- [ ] 153 existing tests still pass
- [ ] `coverage_baseline.json` saved (baseline for regression checks)

---

## 3. Phase 1: Rate Limiting Tests

**Effort:** 8-12h | **Depends on:** Phase 0 complete

### Scope: 15 tests

Target file: `app/middleware/rate_limit.py` (85.7% lines → target 95%)

**Tests:**

| # | Test | What It Validates |
|---|---|---|
| 1 | `test_auth_rate_limit_enforces_5_per_minute` | 5/min tier on /auth endpoints |
| 2 | `test_write_rate_limit_enforces_10_per_minute` | 10/min tier on POST/PUT/DELETE |
| 3 | `test_read_rate_limit_enforces_60_per_minute` | 60/min tier on GET endpoints |
| 4 | `test_rate_limit_returns_429_with_retry_after` | 429 response + Retry-After header |
| 5 | `test_rate_limit_resets_after_window` | Counter resets after TTL |
| 6 | `test_login_lockout_after_10_failures` | Account lockout mechanism |
| 7 | `test_lockout_returns_403_not_429` | Lockout is 403, not rate limit 429 |
| 8 | `test_lockout_expires_after_15_minutes` | Lockout TTL |
| 9 | `test_successful_login_resets_counter` | Good login clears failure count |
| 10 | `test_rate_limit_per_ip_isolation` | Different IPs independent |
| 11 | `test_unauthenticated_inherits_read_tier` | No-token requests get read tier |
| 12 | `test_admin_exempt_from_rate_limit` | Admin role bypass |
| 13 | `test_rate_limit_header_x_ratelimit_remaining` | X-RateLimit-Remaining header |
| 14 | `test_concurrent_requests_atomic_increment` | Redis INCR atomicity |
| 15 | `test_redis_unavailable_graceful_degradation` | Redis down → requests proceed |

**Infrastructure Required:**
- Redis mock enhancement: `expire()` must track TTL (currently no-op)
- Redis mock enhancement: `incr()` must respect key creation timing

### Phase 1 Exit Criteria

- [ ] 15 tests pass
- [ ] `rate_limit.py` line coverage ≥ 95%
- [ ] `rate_limit.py` branch coverage measured and recorded
- [ ] No regressions in existing 153 tests

---

## 4. Phase 2: WebSocket Tests

**Effort:** 10-16h | **Depends on:** Phase 0 complete

### Pre-Gate: 30-Minute POC

Before writing any tests:

1. Connect to a WS endpoint using `starlette.testclient.TestClient.websocket_connect()`
2. Verify `websocket.accept()` works through ASGI transport
3. Verify `send_json/receive_json` works
4. If fails → try `httpx-ws` (install + test, 30 min)
5. If both fail → **HALT and report**

### Scope: 12 tests

Target file: `app/api/v1/ws_logs.py` (18.8% → target 75%)

**Tests:**

| # | Test | What It Validates |
|---|---|---|
| 1 | `test_ws_node_logs_connect_accept` | WebSocket handshake succeeds |
| 2 | `test_ws_node_logs_unknown_node_close_1008` | Unknown node → error + close |
| 3 | `test_ws_node_logs_receives_log_lines` | Mock subprocess stdout → JSON frames |
| 4 | `test_ws_node_logs_client_disconnect_cleanup` | Clean process termination |
| 5 | `test_ws_node_logs_subprocess_failure` | Process exit code ≠ 0 → error frame |
| 6 | `test_ws_job_status_connect_accept` | Job status WS handshake |
| 7 | `test_ws_job_status_receives_updates` | Mock Redis pub/sub → JSON frames |
| 8 | `test_ws_job_status_unknown_job` | Invalid job_id → error + close |
| 9 | `test_ws_job_status_job_complete_closes` | Terminal status → connection closed |
| 10 | `test_ws_unauthenticated_rejected` | No token → 403/close |
| 11 | `test_ws_node_logs_large_output_handling` | Large log volume doesn't hang |
| 12 | `test_ws_concurrent_connections` | Multiple simultaneous WS connections |

**Infrastructure Required:**
- `MockRedisPubSub` class (specified in v2 Section C2)
- Monkeypatch `redis.asyncio.from_url` for `ws_logs.py` pub/sub
- Monkeypatch `asyncio.create_subprocess_shell` for log streaming

### Phase 2 Exit Criteria

- [ ] POC gate passed
- [ ] 12 tests pass
- [ ] `ws_logs.py` coverage ≥ 75%
- [ ] No regressions

---

## 5. Phase 3: Untested API Endpoints

**Effort:** 10-14h | **Depends on:** Phase 0c (bug fixes for manifests.py, backup.py)

### Scope: 33 tests across 6 endpoint files

| File | Current Coverage | Tests | Target |
|---|---|---|---|
| `backup.py` | 43.3% | 8 | 80% |
| `manifests.py` | 42.0% | 8 | 80% |
| `alerts.py` | 0% | 6 | 75% |
| `nodes.py` (admin) | 0% | 4 | 75% |
| `languages.py` | 0% | 4 | 75% |
| `quotas.py` | 0% | 3 | 75% |

**BLOCKED ON Phase 0c:** `backup.py` and `manifests.py` have schema mismatches
(BUG-003 through BUG-006). Tests cannot be written until operator approves
fix direction and fixes are applied.

### Phase 3 Exit Criteria

- [ ] 33 tests pass
- [ ] All 6 endpoint files above target coverage
- [ ] No regressions
- [ ] Branch coverage snapshot saved for Phase 4 scoping decision

---

## 6. Phase 4: Service Layer Tests

**Effort:** 36-50h | **Depends on:** Phase 3 complete

> **⚠️ CORRECTION C1 APPLIED:** Phase 4 scope criteria revised.

### Service Skip Criteria (v3 — CORRECTED)

A service may be skipped from Phase 4 **only if BOTH conditions hold:**

1. **Service file has ≥75% branch coverage** after Phase 3 API tests complete
2. **Service file has zero methods unreachable via API** (every public and
   private method is exercised through at least one API endpoint test)

**Evidence requirement:** Skip decisions must be documented in the Phase 4
commit message with:
- Branch coverage percentage (from `coverage.json`)
- List of all methods and which API test exercises each
- Explicit statement: "All methods reachable — skip justified"

**If either condition is NOT met, the service gets Phase 4 tests.**

This is stricter than v2's "60% coverage" single threshold. The practical
effect: **Phase 4 may push to testing all 13+ services** rather than the
v2 estimate of 8. Effort estimate adjusted upward accordingly.

### Service Classification (unchanged from v2 audit)

| Service | Classification | External Deps | Phase 4 Required? |
|---|---|---|---|
| checkpoint_service.py | **PURE_DB** | DB only | Evaluate after Phase 3 |
| dlq_service.py | **PURE_DB** | DB only | Evaluate after Phase 3 |
| gpu_service.py | **PURE_DB** | DB only | Likely YES (`_to_response` private) |
| job_service.py | **PURE_DB** | DB only | Evaluate after Phase 3 |
| language_service.py | **PURE_DB** | DB only | Evaluate after Phase 3 |
| prompt_service.py | **PURE_DB** | DB only | Likely YES (`_resolve_single` private) |
| quality_service.py | **PURE_DB** | DB only | Likely YES (avg calculation) |
| retention_service.py | **PURE_DB** | DB only | Likely YES (report logic) |
| storyboard_service.py | **PURE_DB** | DB only | Evaluate after Phase 3 |
| asset_service.py | **DB+EXTERNAL** | DB, SeaweedFS | YES (SeaweedFS interaction) |
| transcript_service.py | **DB+EXTERNAL** | DB, SeaweedFS, filesystem | YES (filesystem) |
| project_service.py | **DB+EXTERNAL** | DB, current_user context | Likely YES (trigger_pipeline) |
| rollback_service.py | **EXTERNAL_ONLY** | Subprocess, filesystem | YES (subprocess mocking) |
| auth_service.py | **EXTERNAL_ONLY** | Redis | YES (token lifecycle) |
| user_service.py | **PURE_LOGIC** | None (static methods) | Evaluate after Phase 3 |

**Execution Order:**
1. PURE_DB services first (established fixture patterns)
2. DB+EXTERNAL services second (need mock extensions)
3. EXTERNAL_ONLY services last (heaviest mocking)

### Estimated Test Counts

**Likely scenario:** 10-13 services need Phase 4 tests

| Service Group | Services | Est. Tests Each | Total Tests |
|---|---|---|---|
| PURE_DB (needing Phase 4) | 6-9 | 8-12 | 48-108 |
| DB+EXTERNAL | 3 | 10-15 | 30-45 |
| EXTERNAL_ONLY | 2 | 8-10 | 16-20 |
| **Total** | **11-14** | — | **89-115** (v2 was 60-89) |

### Phase 4 Exit Criteria

- [ ] All in-scope services have tests
- [ ] Skip decisions documented with evidence (both conditions verified)
- [ ] Line coverage ≥ 80% overall
- [ ] Branch coverage measured → triggers Section 9 gate
- [ ] All critical path test functions exist and pass (Section 10)
- [ ] No regressions

---

## 7. Phase 6: Integration Tests

**Effort:** 22-30h | **Depends on:** Phase 4 complete

> **⚠️ CORRECTION C4 APPLIED:** SeaweedFS and TimescaleDB now in scope.
> Open Question 2 answered affirmatively.

**Phase 6 is NOT "nice to have" — it is the reliability foundation.**
Unit tests with mocks cannot prove external service integrations work.
Mock divergence from real service behavior is a demonstrated risk in this
codebase (see BUG-003 through BUG-006 for examples of API/implementation
divergence).

All Phase 6 tests marked `@pytest.mark.integration` and run separately
from the unit test suite. They do NOT count toward the §15.4 80% line
coverage target.

### 6.1: Real Redis Integration (4-6h)

**Setup:** `docker run -d --name test-redis -p 6380:6379 redis:7-alpine`

| # | Test | What It Validates |
|---|---|---|
| 1 | `test_redis_rate_limit_ttl_expires` | Key actually expires after TTL |
| 2 | `test_redis_incr_atomic_under_concurrency` | Concurrent INCR is atomic |
| 3 | `test_redis_pubsub_message_delivery` | Published message reaches subscriber |
| 4 | `test_redis_pubsub_channel_isolation` | Messages don't leak between channels |
| 5 | `test_redis_connection_pool_exhaustion` | Graceful handling of pool limits |
| 6 | `test_redis_reconnect_after_restart` | Client reconnects after Redis restart |
| 7 | `test_redis_lockout_key_persists_across_requests` | Lockout state survives |
| 8 | `test_redis_pipeline_batch_operations` | Pipeline batching works correctly |

### 6.2: Real SeaweedFS Integration (4-6h) — NEW (C4)

**Setup:** `docker run -d --name test-seaweedfs -p 9333:9333 -p 8888:8888 chrislusf/seaweedfs server -master.port=9333 -volume.port=8888 -filer`

| # | Test | What It Validates |
|---|---|---|
| 1 | `test_upload_download_roundtrip_checksums` | Upload → download → checksum match |
| 2 | `test_large_file_100mb_upload` | 100MB file upload completes without timeout |
| 3 | `test_asset_deletion_removes_file` | Delete operation removes file from storage |
| 4 | `test_concurrent_uploads` | Multiple simultaneous uploads don't conflict |
| 5 | `test_upload_to_filer_path_resolution` | Filer path is accessible after upload |
| 6 | `test_download_nonexistent_fid_404` | Missing FID returns proper error |

**Rationale:** The current SeaweedFS mock in `conftest.py` returns hardcoded
`fid` values and stores nothing. It cannot verify that checksums survive
round-trips, that large files don't timeout, or that deletion actually removes
data. These are the exact behaviors that matter for asset integrity.

### 6.3: Real TimescaleDB Integration (2-4h) — NEW (C4)

**Setup:** `testcontainers` with `timescale/timescaledb:latest-pg17`

```python
from testcontainers.postgres import PostgresContainer

timescale = PostgresContainer(
    image="timescale/timescaledb:latest-pg17",
    user="testuser",
    password="testpass",
    dbname="testdb",
)
```

| # | Test | What It Validates |
|---|---|---|
| 1 | `test_gpu_metrics_hypertable_created` | `create_hypertable()` succeeds on `gpu_metrics_history` |
| 2 | `test_metrics_compression_enabled` | TimescaleDB compression policy applies |
| 3 | `test_time_bucket_aggregation` | `time_bucket('5 minutes', ...)` returns correct aggregates |
| 4 | `test_retention_policy_deletes_old_data` | `add_retention_policy()` removes old rows |

**Rationale:** The entire GPU monitoring specification (§4.3) depends on
TimescaleDB hypertable functioning. The sandbox has no TimescaleDB installed
(identified as MEDIUM risk in v2 Section K1). These tests close that gap.
Without them, we have zero verification that the GPU metrics pipeline works
with its intended storage backend.

### 6.4: Cross-Service Workflow Integration (6-8h)

| # | Test | What It Validates |
|---|---|---|
| 1 | `test_project_create_to_job_submit_workflow` | Create project → submit render job |
| 2 | `test_job_checkpoint_resume_end_to_end` | Job fails → checkpoint → resume → complete |
| 3 | `test_asset_upload_quality_score_approve` | Upload asset → score → approve |
| 4 | `test_gpu_register_reserve_drain_lifecycle` | Register node → reserve → drain |
| 5 | `test_prompt_create_version_restore` | Create → version → restore previous |
| 6 | `test_transcript_upload_reorder_delete` | Upload → reorder → delete cascade |
| 7 | `test_retention_policy_enforcement` | Policy → report → tier migration |
| 8 | `test_dlq_message_replay_to_completion` | Dead letter → replay → succeeds |

### 6.5: Summary

| Sub-Phase | Tests | Hours |
|---|---|---|
| 6.1 Real Redis | 8 | 4-6h |
| 6.2 Real SeaweedFS | 6 | 4-6h |
| 6.3 Real TimescaleDB | 4 | 2-4h |
| 6.4 Cross-Service Workflows | 8 | 6-8h |
| **Total** | **26** | **16-24h** |

(Add 6h contingency → **22-30h** total)

### Phase 6 Exit Criteria

- [ ] All 4 Docker containers start and pass health checks
- [ ] 26 integration tests pass
- [ ] Cross-service workflows exercise all 10 critical paths (Section 10)
- [ ] No unit test regressions
- [ ] Container cleanup verified (no orphan containers after test run)

---

## 8. Phase 7: Defect #10 — Test Directory Scope Unification

**Effort:** 10-16h | **Depends on:** Phase 6 complete | **Additive to timeline**

### Context

Defect #8 restored only `ivgs-api/tests/` (13 files, expanded to ~35 after
Phases 0-6). However, the repository contains **29 additional test files**
across 3 other directories that are currently unrunnable:

| Directory | Files | Apparent Purpose |
|---|---|---|
| `tests/` (repo root) | 9 | Mixed API/integration tests |
| `ivgs-workers/tests/` | 16 | Pipeline worker tests |
| `ivgs-scheduler/tests/` | 4 | Scheduler/cron tests |

Phase 7 brings these 29 files into the unified test suite, closing Defect #10.

### Phase 7a: Investigation (2-3 hours)

**Mandatory before any code changes.**

Read all 29 files. For each file, document:

| Column | Description |
|---|---|
| Filename | Full path |
| References existing code? | Does the file import code that still exists in the repo? |
| References existing fixtures? | Does it use fixtures from any conftest.py? |
| References renamed/moved/deleted modules? | Detect import breakage |
| Apparent intent | What was this test trying to verify? |
| Disposition | (a) port as-is, (b) port with fixture migration, (c) rewrite, (d) delete |

**Deliverable:** `TESTS_DIRECTORY_AUDIT.md`

**Halt gate:** If >30% of files appear to be test rot (references deleted
code, fixtures that never existed, or completely obsolete functionality),
**halt and report**. This changes the scope estimate significantly.

### Phase 7b: Infrastructure Migration (4-6 hours)

1. **Extend `pyproject.toml` testpaths:**
   ```toml
   testpaths = [
       "ivgs-api/tests",
       "ivgs-workers/tests",
       "ivgs-scheduler/tests",
       "tests",
   ]
   ```

2. **Resolve conftest.py collision:**
   - Primary approach: set `importmode = "importlib"` in pytest config
   - Fallback: rename conftests (e.g., `conftest_workers.py`) with explicit imports
   - Verify: `pytest --collect-only` reports no `conftest.py` import errors

3. **Migrate non-ivgs-api conftests to same pattern:**
   - testcontainers + Alembic + NullPool + committed-data + TRUNCATE
   - **Do NOT duplicate fixture code** → extract common fixtures to a shared module
     (e.g., `tests/common/fixtures.py`)
   - Each test directory's `conftest.py` imports shared fixtures + adds directory-specific ones

4. **Verify existing ivgs-api/tests/ (~35 files) still pass** with broadened
   `testpaths`. This is a HARD GATE — any regression must be fixed before
   proceeding.

### Phase 7c: Test Execution & Triage (2-3 hours)

1. Run pytest against each directory individually, then all 4 together:
   ```bash
   pytest ivgs-api/tests/ -v --tb=short          # Existing (must pass)
   pytest tests/ -v --tb=short                     # Root tests
   pytest ivgs-workers/tests/ -v --tb=short        # Worker tests
   pytest ivgs-scheduler/tests/ -v --tb=short      # Scheduler tests
   pytest -v --tb=short                             # ALL directories
   ```

2. Triage every failure into one of three categories:
   - **(a) Real production bug** → follow bug protocol (BUGS_FOUND.md, xfail, halt-and-report)
   - **(b) Rotted test needing update** → fix imports/fixtures, commit as `test: port <filename>`
   - **(c) Obsolete test needing deletion** → delete with justification in commit message

3. Document all triage decisions in commit messages with evidence.

### Phase 7 Exit Criteria

- [ ] All 29 files ported, rewritten, or deleted (each with documented justification)
- [ ] `pytest` from repo root collects all 4 directories without conftest errors
- [ ] Combined test suite runs to completion (pass or documented xfail)
- [ ] `TESTS_DIRECTORY_AUDIT.md` committed
- [ ] All triage notes committed
- [ ] Existing ivgs-api/tests/ pass count unchanged (zero regressions)

### Phase 7 Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Test rot in `ivgs-workers/tests/` high (pipeline code changed) | HIGH | +4h rewrite | Halt gate at 30% rot |
| `tests/` at root duplicates `ivgs-api/tests/` | MEDIUM | +2h dedup | Flag duplicates, delete older copy |
| `ivgs-scheduler/tests/` needs different models | LOW | +3h | Separate testcontainers if needed |
| Conftest collisions don't resolve with `importmode` alone | MEDIUM | +4h | Fallback to renamed conftests |

### Phase 7 Scope Boundaries

- 80% coverage target applies to `ivgs-api/` only (per spec §15.4)
- Phase 7 tests count toward overall test count but NOT toward ivgs-api coverage gate
- Phase 7 is required for Defect #10 closure — it is not optional
- Phase 7 may reveal additional production bugs → follow same bug protocol (Section 11)

---

## 9. Coverage Targets & Gates

> **⚠️ CORRECTION C2 APPLIED:** Added post-Phase 4 re-evaluation gate.

### Coverage Thresholds

| Metric | Threshold | Gate Type | Applied To |
|---|---|---|---|
| Line coverage (overall) | ≥ 80% | Hard gate (§15.4) | ivgs-api/ only |
| Branch coverage (overall) | ≥ 65% | **Floor** (see re-evaluation) | ivgs-api/ only |
| Branch coverage (critical services) | ≥ 70% | Hard gate | See list below |

**Critical services for branch coverage:**
`rate_limit.py`, `gpu_service.py`, `rollback_service.py`, `quality_service.py`,
`checkpoint_service.py`

### Coverage Command (all phases)

```bash
pytest tests/ \
    --cov=app \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=json \
    --cov-report=html
```

### Post-Phase 4: Branch Coverage Re-Evaluation Gate (C2)

**After Phase 4 completes, produce a 1-page analysis covering:**

1. **Which branches remain uncovered?**
   - List by file: uncovered branch count and percentage
   - Group into: error handling branches, validation branches, main logic branches

2. **Critical vs. non-critical classification:**
   - Critical: branches in services listed above + rate_limit.py + auth logic
   - Non-critical: branches in scripts, admin utilities, logging formatters

3. **Error paths vs. main paths:**
   - What fraction of uncovered branches are error/exception handlers?
   - What fraction are main business logic conditionals?

4. **Feasibility assessment:**
   - For each uncovered critical branch: effort to close (LOW/MEDIUM/HIGH)
   - Dependencies: does closing require new mocks, fixtures, or external systems?

**Decision Rules:**

| Finding | Action |
|---|---|
| Uncovered branches concentrated in **critical services** | **Raise target to 70%**, add targeted tests |
| Uncovered branches spread across **non-critical files** | **65% stands** — document and accept |
| Uncovered branches are all **error handlers** requiring external system failures | Accept — integration tests (Phase 6) cover these |
| Mix of critical and non-critical | Raise to 70% for critical files only, 65% overall stands |

**65% is the floor, not the ceiling.** The re-evaluation may raise it.
The intent is to prevent "we hit 65%, stop" when critical paths remain
untested. The analysis ensures we make an evidence-based decision.

---

## 10. Critical Operational Paths

> **⚠️ CORRECTION C5 APPLIED:** Test function names added per path.

### 10 Critical Paths with Test Function Mapping

| # | Critical Path | Phase | Test Functions |
|---|---|---|---|
| 1 | POST /auth/login → token → authenticated request | Existing | `test_login_success`, `test_login_wrong_password`, `test_token_refresh`, `test_authenticated_endpoint_requires_token` |
| 2 | Rate limit enforcement (60/10/5 tiers) | Phase 1 | `test_auth_rate_limit_enforces_5_per_minute`, `test_write_rate_limit_enforces_10_per_minute`, `test_read_rate_limit_enforces_60_per_minute`, `test_rate_limit_returns_429_with_retry_after` |
| 3 | Login lockout after 10 failures → 15-min block | Phase 1 | `test_login_lockout_after_10_failures`, `test_lockout_returns_403_not_429`, `test_lockout_expires_after_15_minutes`, `test_successful_login_resets_counter` |
| 4 | WebSocket job status → real-time updates | Phase 2 | `test_ws_job_status_connect_accept`, `test_ws_job_status_receives_updates`, `test_ws_job_status_job_complete_closes`, `test_ws_unauthenticated_rejected` |
| 5 | Backup create → verify → checksum validation | Phase 0+3 | `test_create_backup_success`, `test_backup_verify_checksum_match`, `test_backup_verify_checksum_mismatch_fails`, `test_backup_status_lifecycle` |
| 6 | Manifest generate → lock → validate checksums | Phase 0+3 | `test_create_manifest_success`, `test_lock_manifest_becomes_immutable`, `test_manifest_checksum_validation`, `test_manifest_timeline_json_schema` |
| 7 | GPU node register → reserve → drain lifecycle | Phase 4 | `test_gpu_register_node_success`, `test_gpu_reserve_vram_allocation`, `test_gpu_reserve_insufficient_vram_fails`, `test_gpu_drain_node_releases_reservations`, `test_gpu_fleet_utilization_aggregation` |
| 8 | Pipeline checkpoint → resume from failure | Phase 4 | `test_checkpoint_create_at_stage`, `test_checkpoint_resume_from_latest`, `test_checkpoint_resume_skips_completed_stages`, `test_checkpoint_clear_removes_all` |
| 9 | Retention policy → tier migration report | Phase 4 | `test_retention_create_policy_validates_tiers`, `test_retention_report_calculates_tier_sizes`, `test_retention_report_no_data_returns_empty`, `test_retention_default_policy_enforcement` |
| 10 | Rollback point create → execute rollback | Phase 4 | `test_rollback_create_captures_state`, `test_rollback_execute_reverts_to_point`, `test_rollback_list_ordered_by_date`, `test_rollback_invalid_point_fails` |

### Verification Protocol (Phase 4 Exit Criterion)

After Phase 4 completes, for each of the 10 paths above:

```bash
# For each test function listed:
pytest tests/ -k "test_function_name" -v --tb=short
# Must: PASS or xfail with documented bug
```

**If any test function does not exist:** Create it before marking Phase 4 complete.
**If any test function fails (not xfail):** Fix before marking Phase 4 complete.

**This verification is more important than the 80% coverage number.** A suite
that hits 80% but misses critical path #7 (GPU scheduling) is less valuable
than one at 78% that covers all 10 paths.

---

## 11. Bug Discovery & Fix Protocol

> **⚠️ CORRECTION C3 APPLIED:** Open Question 4 removed. Explicit
> halt-and-report protocol established. No bug fixed without operator approval.

### Protocol

For **every** discovered bug, regardless of severity (HIGH, MEDIUM, or LOW):

#### Step (a): Document

Add entry to `BUGS_FOUND.md` with:
- Bug ID (sequential: BUG-001, BUG-002, ...)
- File and line number
- Evidence (code snippet, error output)
- Severity (HIGH / MEDIUM / LOW)
- Proposed fix (specific: "rename `_exc` to `exc`" not "fix the bug")

#### Step (b): Write Exposing Test

```python
@pytest.mark.xfail(reason="BUG-001: NameError — _exc bound but exc referenced")
async def test_backup_error_handler_name_error(client, admin_token):
    """Trigger backup error path — currently crashes with NameError."""
    # ... test that exercises the buggy code path
```

#### Step (c): Commit Test

```
test: add backup error handler test (exposes BUG-001)
```

Test commit is separate from fix commit. This preserves evidence that the
bug existed and that the test catches it.

#### Step (d): Halt and Report

**Present to operator:**
- Bug ID and description
- File, line, evidence
- Proposed fix (from step a)
- Impact if not fixed (blocks Phase X, or cosmetic)
- Effort estimate for fix

**Wait for operator response.** Do not proceed with fix.

#### Step (e): Operator Approves

Operator reviews proposed fix and either:
- Approves as-is
- Modifies fix direction
- Defers to later phase

#### Step (f): Apply Fix

```
fix: BUG-001 — rename _exc to exc in backup.py error handler

Approved by operator on [date].
Test: test_backup_error_handler_name_error now passes.
```

Remove `@pytest.mark.xfail` from the test. Test must pass with the fix.

### Currently Known Bugs (BUG-001 through BUG-008)

All 8 bugs documented in v2 Section H1 require operator decisions before
fixes are applied. The halt-and-report checkpoint is at the start of
**Phase 0c**.

| Bug ID | Severity | Status | Operator Decision Needed |
|---|---|---|---|
| BUG-001 | HIGH | Documented | Approve `_exc` → `exc` rename |
| BUG-002 | LOW | Documented | Approve dead code removal (lines 85-92) |
| BUG-003 | HIGH | Documented | Fix API or fix model? (Q1) |
| BUG-004 | HIGH | Documented | Fix API or fix model? (Q1) |
| BUG-005 | HIGH | Documented | Fix API or fix model? (Q1) |
| BUG-006 | HIGH | Documented | Fix API or fix model? (Q1) |
| BUG-007 | MEDIUM | Documented | Add column to model, or remove from service? |
| BUG-008 | HIGH | Documented | Approve 5 new Alembic migrations |

### What This Means in Practice

- Agent discovers bug → documents → writes test → **stops and waits**
- Agent does NOT apply fix without explicit approval
- Even "obvious" fixes (like BUG-001 `_exc` → `exc`) require approval
- This prevents well-intentioned changes from introducing new issues
- This creates an audit trail of every production code change

---

## 12. Reliability Claims

After all phases (0-7) complete:

| Claim | Confidence | Evidence |
|---|---|---|
| Unit logic correct | HIGH | 80%+ line coverage, 65%+ branch |
| API contracts work | HIGH | All endpoints tested with happy + error paths |
| RBAC enforcement | HIGH | Existing + new tests cover all role tiers |
| Rate limiting enforced | HIGH | Phase 1 unit + Phase 6 real Redis |
| WebSocket streaming works | MEDIUM | Depends on mock fidelity (Phase 2) |
| External system integration | **HIGH** | Phase 6 real Redis + SeaweedFS + TimescaleDB |
| Production deployment safe | MEDIUM | Migrations verified, but env differences remain |
| All test directories unified | HIGH | Phase 7 covers 4 directories |
| Performance acceptable | LOW | No load tests planned |
| Concurrent access safe | LOW | Serial test execution only |

**v2 → v3 change:** "External system integration" upgraded from MEDIUM to HIGH
due to Correction C4 adding SeaweedFS and TimescaleDB integration tests.

---

## 13. Regression Protection

### Baseline

Save `coverage_baseline.json` after Phase 0 completes:

```bash
pytest tests/ --cov=app --cov-branch --cov-report=json
cp coverage.json coverage_baseline.json
```

### Verification Script

```python
# scripts/verify_regression.py
"""Compare coverage before/after fixture changes."""
import json, sys

baseline = json.load(open("coverage_baseline.json"))
current = json.load(open("coverage.json"))

regressions = []
for file in baseline["files"]:
    if file not in current["files"]:
        regressions.append(f"FILE REMOVED: {file}")
        continue
    
    base_pct = baseline["files"][file]["summary"]["percent_covered"]
    curr_pct = current["files"][file]["summary"]["percent_covered"]
    
    if curr_pct < base_pct - 0.5:  # Allow 0.5% noise
        regressions.append(
            f"REGRESSION: {file}: {base_pct:.1f}% → {curr_pct:.1f}%"
        )

if regressions:
    print("❌ REGRESSIONS DETECTED:")
    for r in regressions:
        print(f"  {r}")
    sys.exit(1)
else:
    print("✅ No coverage regressions")
```

### When to Run

1. After adding new fixtures to conftest.py (fixture leak detection)
2. After each phase completion
3. Before any git commit that modifies existing test files
4. Regression detected → investigate and resolve before continuing

---

## 14. CI Integration

### Expected Runtime

| Category | Tests | Est. Time |
|---|---|---|
| Existing (Phase 0 baseline) | 153 | 57s |
| Phase 1 (rate limiting) | 15 | 8s |
| Phase 2 (WebSocket) | 12 | 15s |
| Phase 3 (API endpoints) | 33 | 15s |
| Phase 4 (service tests) | 89-115 | 40-55s |
| **Unit total** | **302-328** | **~135-150s (2.3-2.5 min)** |
| Phase 6 (integration) | 26 | ~180s (container overhead) |
| Phase 7 (directory unification) | varies | ~60s |
| **Full total** | **~340-370** | **~375-390s (6.3-6.5 min)** |

### CI Configuration

```yaml
# .github/workflows/test.yml
test:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:17.2
      env:
        POSTGRES_USER: testuser
        POSTGRES_PASSWORD: testpass
        POSTGRES_DB: testdb
    redis:
      image: redis:7-alpine

  steps:
    - name: Run unit tests
      run: |
        pytest tests/ \
          -m "not integration" \
          --cov=app \
          --cov-branch \
          --cov-report=term \
          --cov-report=xml \
          --cov-fail-under=80

    - name: Run integration tests
      if: github.ref == 'refs/heads/main'
      run: |
        pytest tests/ -m integration -v

    - name: Verify no regressions
      run: python scripts/verify_regression.py
```

**Parallel execution:** Not safe with TRUNCATE-and-commit pattern. Serial
execution under 7 minutes is acceptable for CI.

---

## 15. Sandbox-to-Production Transition

### Known Environment Differences

| Aspect | Sandbox | Production (node-01) | Risk |
|---|---|---|---|
| Python | 3.11.6 | 3.12.8 | LOW |
| PostgreSQL | 17.10 | 17.2 (Docker) | NEGLIGIBLE |
| TimescaleDB | Not installed | Installed | **CLOSED** (Phase 6.3) |
| Redis | Mock (dict) / Docker | Real (Docker) | **CLOSED** (Phase 6.1) |
| SeaweedFS | Mock / Docker | Real (Docker) | **CLOSED** (Phase 6.2) |
| `/ivgs/rollback_points` | `chmod 777` | Proper UID/GID | LOW |

**v2 → v3 change:** TimescaleDB, Redis, and SeaweedFS risks now marked
CLOSED because Phase 6 integration tests explicitly validate them.

### Sandbox Exit Checklist

```bash
# 1. All unit tests pass
pytest tests/ -m "not integration" -v
# Expected: 302+ passed

# 2. Coverage meets threshold
pytest tests/ --cov=app --cov-branch --cov-fail-under=80
# Expected: ≥80% line, ≥65% branch (may be higher per Section 9 gate)

# 3. No regressions
python scripts/verify_regression.py

# 4. Integration tests pass
pytest tests/ -m integration -v
# Expected: 26+ passed

# 5. Phase 7 combined run
pytest -v --tb=short
# Expected: All directories collected and passing

# 6. No flaky tests (run 3x)
for i in 1 2 3; do pytest tests/ -q --tb=no || echo "FLAKY on run $i"; done

# 7. Clean git state
git status && git log --oneline -10
```

### node-01 Verification

```bash
git pull origin main
pip install -r requirements.txt -r requirements-test.txt
alembic upgrade head
pytest tests/ -m "not integration" -v
pytest tests/ -m integration -v
pytest tests/ --cov=app --cov-branch --cov-report=term
```

### Discrepancy Diagnostic

If tests pass in sandbox but fail on node-01:
1. Compare Python versions: `python --version`
2. Compare installed packages: `pip freeze > deps.txt && diff`
3. Check database: `psql -c "SELECT version()"`
4. Check Redis: `redis-cli ping`
5. Run single failing test verbose: `pytest tests/test_foo.py::test_bar -vvs`

---

## 16. Open Questions

### Resolved

| # | Question | Resolution |
|---|---|---|
| Q2 | Phase 6 scope: include SeaweedFS? | **YES** — Answered affirmatively per Correction C4. SeaweedFS + TimescaleDB both in scope. |
| Q4 | Bug fix authority: immediate or per-approval? | **REMOVED** — Per Correction C3: all bugs require explicit operator approval before fix. No exceptions. Protocol in Section 11. |

### Pending Operator Decision (Required Before Phase 0c)

| # | Question | Impact | Default if No Answer |
|---|---|---|---|
| Q1 | **BUG-003 through BUG-006:** Fix column names in API (align to model) or add columns to model (align to API)? | Blocks Phase 3 | Cannot proceed — **must have answer** |
| Q3 | **Branch coverage target:** 65% overall acceptable as floor, or start at 70%? | Affects Phase 4 scope | 65% floor with post-Phase 4 re-evaluation (Section 9) |
| Q5 | **Dead code (BUG-002):** Remove manifests.py lines 85-92, or leave? | Cosmetic | Remove (low risk, clear dead code) |

**Q1 is the only true blocker.** Q3 and Q5 have safe defaults.

---

## 17. Revised Timeline Summary

### Phase Sequence

```
Phase 0: Migrations + Bug Decisions        [12-16h]  ← BLOCKS Phase 3
    ↓
Phase 1: Rate Limiting Tests               [8-12h]   ← Parallel-safe with Phase 2
Phase 2: WebSocket Tests                   [10-16h]  ← Parallel-safe with Phase 1
    ↓
Phase 3: API Endpoint Tests                [10-14h]  ← REQUIRES Phase 0c complete
    ↓
Phase 4: Service Layer Tests               [36-50h]  ← REQUIRES Phase 3 coverage data
    ↓
Phase 6: Integration Tests                 [22-30h]  ← REQUIRES Phase 4 complete
    ↓
Phase 7: Directory Scope Unification       [10-16h]  ← REQUIRES Phase 6 complete
```

### Total Effort

| Metric | Hours |
|---|---|
| **Best case** | 108h |
| **Expected** | 131h |
| **Worst case** | 154h |

**Calendar time:** 3-5 weeks of focused agent work.

### Comparison to Previous Versions

| Version | Estimated Hours | Phases | Key Difference |
|---|---|---|---|
| v1 | 46h | 5 | Naïve — no migrations, no integration, scripts as padding |
| v2 | 58-94h | 6 | Added Phase 0, Phase 6; removed Phase 5 |
| **v3** | **108-154h** | **7** | Stricter Phase 4, expanded Phase 6, added Phase 7 |

The increase from v2 to v3 is driven by:
- Correction C1: Phase 4 may require all 13 services (not 8) → +14h
- Correction C4: Phase 6 adds SeaweedFS + TimescaleDB → +6-10h
- Phase 7 addition: Defect #10 scope → +10-16h

---

## 18. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| More schema bugs discovered during testing | HIGH | +8h | Phase 0 audit reduces surprise; bug protocol handles rest |
| WebSocket POC fails both approaches | MEDIUM | +8h | Fallback sequence documented (Section 4) |
| Phase 4 scope expands to all 13 services (C1) | **HIGH** | +14h | Realistic — effort estimate already includes this |
| Integration test containers fail in sandbox | LOW | +4h | Docker already working; testcontainers fallback |
| Coverage 80% line unachievable | LOW | Plan revision | Phase 4 is largest contributor |
| Branch coverage 65% unachievable | MEDIUM | Documented | Re-evaluation gate (Section 9) adjusts target |
| Phase 7 test rot >30% | MEDIUM | +4-8h | Halt gate triggers scope reassessment |
| Conftest collisions across 4 directories | MEDIUM | +4h | Fallback: renamed conftests |
| TimescaleDB container unavailable in sandbox | LOW | Skip 6.3 | Mark tests `@pytest.mark.skip(reason="no timescale")` |
| Operator slow to approve bug fixes (Q1 blocker) | MEDIUM | Calendar slip | Q1 is pre-Phase 0c; escalate if no response in 24h |

---

## 19. Appendix: Audit Raw Data

### A. Migration Files (14 migrations, 26 tables)

```
0001_initial_core.py         → users, projects, transcripts, storyboard_scenes,
                               assets, prompts, prompt_tags, prompt_tag_associations,
                               render_jobs, language_variants, audit_log, rollback_points
0002_pipeline_checkpoints.py → pipeline_checkpoints
0003_gpu_registry.py         → gpu_nodes, gpu_reservations
0004_retry_tracking.py       → task_retries
0005_worker_heartbeats.py    → worker_heartbeats
0006_dead_letter_queue.py    → dead_letter_messages
0007_composition_manifests.py→ composition_manifests
0008_quality_scores.py       → asset_quality_scores
0009_render_segments.py      → render_segments
0010_gpu_metrics.py          → gpu_metrics_history
0011_retention_policies.py   → retention_policies
0012_storage_quotas.py       → storage_quotas
0013_backup_records.py       → backup_records
0014_fallback_policies.py    → fallback_policies
```

### B. Column Gap Evidence

**users.is_active:**
- Model: `is_active: Mapped[bool] = mapped_column(Boolean, ...)`
- Migration 0001: Columns are `id, username, password_hash, role, created_at, last_login_at`
- `is_active` NOT present in any migration

**projects.created_by:**
- Model: `created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID, ForeignKey("users.id"))`
- Migration 0001: Columns are `id, name, description, max_runtime_seconds, state, hero_image_asset_id, talking_head_asset_id, target_audience, created_at, updated_at`
- `created_by` NOT present in any migration

**asset_quality_scores.job_id:**
- Model: `job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID, ForeignKey("render_jobs.id"))`
- Migration 0008: Columns are `id, asset_id, quality_score, safety_score, scoring_details, decision, reviewed_by, reviewed_at, created_at`
- `job_id` NOT present in any migration

**retention_policies.description:**
- Model: `description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)`
- Migration 0011: Columns are `id, name, hot_days, warm_days, cold_days, archive_days, delete_after_days, applies_to, is_default, created_at, updated_at`
- `description` NOT present in any migration

**prompt_tags.description:**
- Model: `description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)`
- Migration 0001 prompt_tags: Columns are `id, name, created_at`
- `description` NOT present in any migration

### C. Service Classification Raw Data

```
checkpoint_service   → __init__(self, db: AsyncSession)           → PURE_DB
dlq_service          → __init__(self, db: AsyncSession)           → PURE_DB
gpu_service          → __init__(self, db: AsyncSession)           → PURE_DB
job_service          → __init__(self, db: AsyncSession)           → PURE_DB
language_service     → __init__(self, db: AsyncSession)           → PURE_DB
prompt_service       → __init__(self, db: AsyncSession)           → PURE_DB
quality_service      → __init__(self, db: AsyncSession)           → PURE_DB
retention_service    → __init__(self, db: AsyncSession)           → PURE_DB
storyboard_service   → __init__(self, db: AsyncSession)           → PURE_DB
asset_service        → __init__(self, db: AsyncSession) + seaweedfs → DB+EXTERNAL
transcript_service   → __init__(self, db: AsyncSession) + seaweedfs → DB+EXTERNAL
project_service      → __init__(self, db: AsyncSession) + current_user → DB+EXTERNAL
rollback_service     → __init__(self) + subprocess + filesystem    → EXTERNAL_ONLY
auth_service         → uses redis_client (module-level)            → EXTERNAL_ONLY
user_service         → static/class methods, no __init__           → PURE_LOGIC
```

### D. Known Bugs (v2 Section H1 — carried forward)

| ID | File | Severity | Type | Description |
|---|---|---|---|---|
| BUG-001 | backup.py:292/299 | **HIGH** | NameError | `_exc` bound but `exc` referenced → crash in error handler |
| BUG-002 | manifests.py:85-92 | LOW | Dead Code | Unreachable `select("*")` call, result unused |
| BUG-003 | manifests.py:99+ | **HIGH** | Schema Mismatch | API uses `timeline_json`, `scene_count`, `created_at` — model has `timeline`, no `scene_count`, no `created_at` |
| BUG-004 | manifests.py:176+ | **HIGH** | Column Mismatch | API uses `sha256_hash` — model column is `content_hash` |
| BUG-005 | backup.py:42+ | **HIGH** | Column Mismatch | API uses `storage_path` — model column is `backup_path` |
| BUG-006 | backup.py:43+ | **HIGH** | Missing Column | API uses `error_message` — model has no such column |
| BUG-007 | quality_service.py:172 | MEDIUM | Missing Attr | Service sets `score.review_notes` — model has no `review_notes` |
| BUG-008 | migrations/ | **HIGH** | Migration Gap | 5 model columns missing from Alembic migrations |

---

*End of TEST_IMPLEMENTATION_PLAN_v3.md. Addresses all 5 corrections and
Phase 7 addition. Three pending operator decisions (Q1 blocker, Q3, Q5)
must be resolved before Phase 0c can proceed.*
