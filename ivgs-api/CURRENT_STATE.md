# IVGS v5 API — Current State Snapshot

**Date:** 2026-05-27T23:30Z
**Branch:** `master`
**HEAD:** `a76d90c71b892ce99c591e43ee6726c867fed484`
**Remote:** `brucecostello2/elearning_v5` → `feature/defect-8-test-restoration-sandbox`

---

## Test Suite

| Metric | Value |
|--------|-------|
| Total Tests | **513** |
| Passed | 513 |
| Failed | 0 |
| xfail | 0 |
| Duration | 200.27s |
| Test Files | 49 |

## Coverage

| Metric | Value |
|--------|-------|
| Line Coverage | **83.5%** (3516/4209 stmts) |
| Branch Coverage | **89.2%** (619/694 branches) |
| Combined (pytest-cov) | **80%** |

### Per-Service Coverage

| Service | Stmts | Miss | Branch | BrPart | Coverage |
|---------|-------|------|--------|--------|----------|
| asset_service.py | 96 | 7 | 26 | 5 | 90% |
| auth_service.py | 76 | 4 | 28 | 8 | 88% |
| checkpoint_service.py | 67 | 1 | 22 | 2 | 97% |
| dlq_service.py | 105 | 4 | 30 | 4 | 94% |
| gpu_service.py | 137 | 4 | 44 | 7 | 92% |
| job_service.py | 37 | 0 | 4 | 0 | 100% |
| language_service.py | 44 | 7 | 8 | 1 | 85% |
| project_service.py | 136 | 16 | 44 | 6 | 86% |
| **prompt_service.py** | 117 | 39 | 30 | 5 | **61%** ⚠️ |
| **quality_service.py** | 86 | 25 | 18 | 4 | **64%** ⚠️ |
| retention_service.py | 75 | 0 | 22 | 0 | 100% |
| rollback_service.py | 104 | 5 | 22 | 3 | 94% |
| storyboard_service.py | 79 | 9 | 22 | 6 | 83% |
| transcript_service.py | 118 | 19 | 30 | 1 | 82% |
| user_service.py | 48 | 0 | 8 | 0 | 100% |

## Bugs

| Bug | Summary | Status |
|-----|---------|--------|
| BUG-001 | Backup error handler NameError | ✅ Fixed |
| BUG-002 | Dead code in manifests GET | ✅ Fixed |
| BUG-003 | Manifest field name mismatch | ✅ Fixed |
| BUG-004 | Asset checksum field mismatch | ✅ Fixed |
| BUG-005 | Backup path field mismatch | ✅ Fixed |
| BUG-006 | Missing error_message column | ✅ Fixed |
| BUG-007 | Missing review_notes column | ✅ Fixed |
| BUG-008 | Quota field name mismatch | ✅ Fixed |
| BUG-009 | Quota max_bytes vs quota_bytes | ✅ Fixed |
| BUG-010 | Quota current_bytes vs used_bytes | ✅ Fixed |
| BUG-011 | Rate limiter Redis crash | ✅ Fixed |
| BUG-012 | WebSocket auth bypass | ✅ Fixed |
| BUG-013 | WebSocket UnboundLocalError | ✅ Fixed |
| BUG-014 | Backup RBAC bypass | ✅ Fixed |
| BUG-015 | Quotas RBAC bypass | ✅ Fixed |

## Migrations

22 migrations total: `0001` (initial) through `0022` (storage_quotas unique index)

New migrations added (Phases 0b/0c):
- `0015_add_users_is_active`
- `0016_add_projects_created_by`
- `0017_add_quality_scores_job_id`
- `0018_add_retention_policies_description`
- `0019_add_prompt_tags_description`
- `0020_add_backup_records_error_message`
- `0021_add_quality_scores_review_notes`
- `0022_add_storage_quotas_unique_index`

## Phase Completion History

| Phase | Commit | Tag | Tests At Completion |
|-------|--------|-----|-------------------|
| Phase 0 (Schema + Bugs) | `499131a` | `sandbox-phase-0-complete` | 160 |
| Phase 1 (Rate Limiting) | `6a93ffa` | `sandbox-phase-1-complete` | 175 |
| Phase 2 (WebSocket) | `6575664` | `sandbox-phase-2-complete` | 201 |
| Phase 3 (API Endpoints) | `d66936a` | `sandbox-phase-3-complete` | 284 |
| Phase 4 (Service Tests) | `2f44169` | `sandbox-phase-4-complete` | 376 |
| Phase 4 Gap Closure | `913c372` | `sandbox-phase-4-gap-closure` | 498 |
| Pre-Phase 6 | `a76d90c` | `sandbox-pre-phase-6` | 513 |

## v3 Section 10 Critical Paths

All 10 critical paths verified with **41/41 exact test function names** present and passing.
See `CRITICAL_PATH_EXACT_VERIFICATION.md` for complete mapping.

## Known Test-Environment Limitations

1. **`test_create_backup_success`** accepts 200/202/500 — `pg_dump` unavailable in sandbox
2. **mock_redis** TTL is no-op — rate-limit tests use unique users/IPs to avoid pollution
3. **prompt_service** (61%) and **quality_service** (64%) gaps documented — non-critical advisory services

## Phase 6 Environment (when available)

| Service | Config |
|---------|--------|
| PostgreSQL 15 | `localhost:5432/testdb` |
| Redis 7 | `localhost:6380` |
| SeaweedFS 3.80 | `localhost:9333` (master), `localhost:8080` (volume) |
| TimescaleDB 2.x | `localhost:5432/ivgs_metrics` |

## Git Commit History (Full)

```
a76d90c Pre-Phase 6: Three items complete + environment ready
913c372 Phase 4 Gap Closure: 122 new tests across 7 files
7346acb docs: Phase 4 verification report
2f44169 Phase 4: Add 92 service-layer tests
d66936a docs: Mark BUG-014/015 fixed
8f5c9a1 test: Remove xfail from BUG-014/015
fa43f79 fix: BUG-015 — quotas RBAC
7b1669d fix: BUG-014 — backup RBAC
e17d8a8 Phase 3: 81 API endpoint tests
0d16fcf docs: Phase 3 plan
6575664 fix: BUG-012+013 — WebSocket
011f679 Phase 2: 26 WebSocket tests
bc714bb docs: Phase 2 plan
6a93ffa test: Remove xfail BUG-011
00d8ae3 fix: BUG-011 — rate limiter fail-open
7a8ae4c Phase 1: 15 rate limiting tests
eb44212 migration: 0022
499131a docs: Phase 0c summary
2428791 chore: remove xfail markers
8663c1b fix: BUG-009+010
db4e3c8 fix: BUG-005
743d6f1 fix: BUG-003+004
0d0de80 fix: BUG-002
f8df1ba fix: BUG-001
cf0ae31 fix: BUG-007+migration 0021
b33e1c5 fix: BUG-006+migration 0020
472a5eb docs: BUG investigations
25ce54a docs: Phase 0c Steps 1-3
e229e1c–e770c4a: xfail tests for bugs
134060d docs: BUGS_FOUND.md
3f1d02f–7e08a57: Phase 0b migrations 0015-0019
7e98100 Phase 0a: schema gap report
d09d98a–634ec66: Foundation (plans, PG17 upgrade, initial restore)
```
