# Phase 4: Service Layer Tests — Plan & Results

## Objective
Write comprehensive unit tests for all service-layer modules in `app/services/`,
exercising business logic, validation, RBAC, state machines, and error paths
**without going through the HTTP/API layer**.

## Scope
| Service Module | Test File | Tests | Status |
|---|---|---|---|
| `user_service.py` | `tests/test_service_user.py` | 15 | ✅ PASS |
| `job_service.py` | `tests/test_service_job.py` | 11 | ✅ PASS |
| `auth_service.py` | `tests/test_service_auth.py` | 11 | ✅ PASS |
| `project_service.py` | `tests/test_service_project.py` | 15 | ✅ PASS |
| `prompt_service.py` | `tests/test_service_prompt.py` | 10 | ✅ PASS |
| `language_service.py` | `tests/test_service_language.py` | 10 | ✅ PASS |
| `storyboard_service.py` | `tests/test_service_storyboard.py` | 10 | ✅ PASS |
| `quality_service.py` | `tests/test_service_quality.py` | 5 | ✅ PASS |
| `retention_service.py` | `tests/test_service_retention.py` | 4 | ✅ PASS |
| **TOTAL** | **9 files** | **92** | **✅ ALL PASS** |

## Test Approach
- **Direct service calls** — instantiate service classes (or call module functions)
  with a real `AsyncSession` against the test PostgreSQL database.
- **No HTTP layer** — tests bypass FastAPI routing, auth middleware, and serialization.
- **Shared fixtures** — reuse `db_session`, `test_user`, `admin_user` from `conftest.py`.
- **Isolation** — each test creates its own entities; database is rolled back per test.

## Key Patterns Tested
1. **CRUD** — create, read, list (with pagination/filtering), update, delete
2. **State machines** — valid/invalid transitions for projects (13 states) and jobs
3. **RBAC at service level** — operators see only own projects; admins see all
4. **Validation / error paths** — duplicate names, missing entities, invalid states
5. **Auth flows** — login, logout, token refresh, bad credentials, expired tokens
6. **Hierarchy resolution** — prompt template scene → project → global fallback
7. **Versioning** — prompt version deactivation on new version creation
8. **Business rules** — pipeline trigger requirements, job cancellation constraints,
   retention policy uniqueness, scene reorder integrity

## Bugs Found During Phase 4
None — all service-layer code behaved correctly. Three **test-side** fixes were needed:
- UUID-to-string comparison in project RBAC assertions
- `SceneReorderItem` Pydantic model required (not raw dicts) for reorder endpoint
- `RetentionPolicyCreate` schema requires `cold_days` field

## Metrics
- **Phase 4 tests:** 92 passed, 0 failed
- **Full suite (Phase 1–4):** 376 passed, 0 failed, 0 xfailed
- **Runtime:** ~156s for full suite

## Date Completed
2026-05-27
