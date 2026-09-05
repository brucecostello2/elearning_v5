# IVGS v5 — test baseline, 2026-09-05 (WP-74 CI BASELINE)

**The inventory is the deliverable.** Every suite the repository carries was run on node-01 against `origin/main` at `9c406e8`, in the environment recorded in §1, and **every failure below is grouped by cause with its file list and a class**: *environment* (dependency, host, database), *test drift* (a test asserting behaviour the code no longer has), *product defect* (named, not fixed here), or *collection error*. Nothing was inferred from reading code; every count is from a run whose summary line is quoted. Supersedes `dev/workpackages/reference/TEST-BASELINE_2026-08-25.md` as the document to diff against.

## 0. Headline

| Suite | command (from `/opt/ivgs`, env of §1) | passed | failed | skipped | errors | vs 2026-08-30 board |
|---|---|---|---|---|---|---|
| `ivgs-api` | `.venv/bin/python -m pytest ivgs-api/tests` | **1870** | **0** | 0 | 0 | 1614 → 1870 (+256 since); the one failure WP-70 saw was the 0055-only table (§1.3), gone with the rebuilt database |
| `ivgs-workers` | `.venv/bin/python -m pytest ivgs-workers/tests` | **988** | 18 | 48 | 15 | 983/18/52/15 — same 33 red rows; +4 passed because `TEST_DATABASE_URL` lets `test_wp60_orphan_guard.py` run |
| `ivgs-scheduler` | `.venv/bin/python -m pytest ivgs-scheduler/tests` | **52** | 15 | 0 | 0 | identical |
| `ivgs-motion-renderer` | `.venv/bin/python -m pytest ivgs-motion-renderer/tests` | **24** | 0 | 2 | 0 | identical |
| `ivgs-backup-worker` | `.venv/bin/python -m pytest ivgs-backup-worker/tests` (own inifile; §1's three extra vars) | **4** | 0 | 0 | 0 | identical |
| `tests_system` | `.venv/bin/python -m pytest tests_system` (live stack) | **193** | 12 | 15 | 30 | identical |
| frontend | `cd ivgs-frontend && npm run test:logic` | **123** | 2 | — | — | 117/119 (WP-70 v2) → 123/125; the same two failures |

**Red rows in total: 45 failed + 45 errors across Python, 2 failed frontend.** Classes: test drift 55, collection/test-configuration 22 (15 + 7), environment aggravator 7, product defect 1. Both frontend failures are test drift (§2.7) and are fixed in this package (test-side); nothing else is fixed here.

## 1. Environment

### 1.1 Harness
- Host node-01 (192.168.1.90), Linux 7.0.0-30-generic. Python harness `/opt/ivgs/.venv`.
- **`.venv` Python is 3.12.3; the API, worker and scheduler Dockerfiles pin `python:3.12.8-slim-bookworm`** (`ivgs-api/Dockerfile:3,18`, `ivgs-workers/Dockerfile:3,18`, `ivgs-scheduler/Dockerfile:3,18`). Patch-level drift, recorded; the venv was not rebuilt (every baseline run started).
- Pins that match: `sqlalchemy==2.0.35`, `pydantic==2.10.4` (`pydantic-core 2.27.2`), `pytest==8.3.4`, `fastapi==0.115.6`, `starlette 0.41.3`, `httpx 0.28.1`, `celery==5.4.0`, `redis==5.2.1`, `alembic==1.14.1`, `asyncpg==0.30.0`, `python-jose==3.3.0`, `bcrypt==4.2.1`, `psycopg2-binary==2.9.10`.
- **passlib/bcrypt:** `passlib 1.7.4` is installed in the venv but **no tracked source imports it** — WP-52 removed it from `ivgs-api/requirements.txt:16-20` and `app/core/security.py` calls `bcrypt` directly. The "passlib/bcrypt incompatibility taking down every user-needing fixture" named in the order **does not exist on `9c406e8`**: `ivgs-api` is 1870/0 with every user fixture exercised. Nothing to pin. (Probe: `bcrypt.__about__` is absent in 4.2.1, which is the attribute passlib read; irrelevant now that nothing reads it.)
- **Drift against the requirements files** (`.venv` vs pin): `pytest-asyncio` installed **0.24.0**, pinned **0.25.2** (`ivgs-workers/requirements.txt:33`, `requirements-dev.txt`); `kombu` 5.6.2 vs 5.4.2; `anyio` 4.13.0 vs 4.8.0; `httpcore` 1.0.9 vs 1.0.7; `markupsafe` 3.0.3 vs 3.0.2; `python-dotenv` 1.2.2 vs 1.0.1. **Missing from the venv** though declared: `asyncio-extras`, `flower`, `tenacity`, `orjson` (workers runtime), and the dev set `pytest-celery`, `pytest-mock`, `pytest-cov`, `pytest-timeout`, `factory-boy`, `freezegun`. `pip check`: no broken requirements. No baseline run needed any of the missing packages.
- **Lint tools are not in the venv** (`black`, `ruff`, `mypy`, `bandit` all absent). Measured in a throwaway venv in scratch (black 24.10.0, ruff 0.8.4, mypy 1.14.1, bandit 1.8.0): `black --check --line-length 100` → **438 files would be reformatted, 36 unchanged**; `ruff check` → **4644 errors** (UP007 1366, UP006 1332, I001 354, UP017 325, B008 320, UP035 289, …; 3591 auto-fixable); `mypy` → stops at **1 error**: duplicate module name `server` (`ivgs-workers/servers/coqui/server.py` vs `.../cogvideox/server.py`), so nothing after it is checked; `bandit` → **3 high, 14 medium, 61 low**. This is the lint state the re-enabled lint job reports (§4 of the report).

### 1.2 Environment block the Python suites need
```bash
# node-01. The credential comes from the running API container; never print or store it.
cd /opt/ivgs
URL="$(docker exec ivgs-fastapi printenv DATABASE_URL)"
TURL="$(printf '%s' "$URL" | sed -E 's#@[^/]+/[^?]+#@192.168.1.90:5432/ivgs_reconciliation_test#')"
export DATABASE_URL="$TURL" TEST_DATABASE_URL="$TURL"
# ivgs-backup-worker only (RC-J8): sync DSN + broker + result backend, all pointed at the TEST database
SYNC="$(printf '%s' "$URL" | sed -E 's#postgresql\+asyncpg://#postgresql://#; s#@[^/]+/[^?]+#@192.168.1.90:5432/ivgs_reconciliation_test#')"
export BACKUP_TEST_DSN="$SYNC" POSTGRES_DSN_SYNC="$SYNC" IVGS_CELERY_BROKER_URL="redis://192.168.1.90:6379/15" IVGS_CELERY_RESULT_BACKEND="db+$SYNC"
.venv/bin/python -m pytest -p no:cacheprovider <suite>
```
⛔ Do not pass `-p no:warnings`: it unregisters the `filterwarnings` marker that `ivgs-api/tests/test_wp57_service_token.py:131` uses, and under `--strict-markers` (root `pyproject.toml`) that is a **collection error** (`'filterwarnings' not found in markers`). Measured: with the flag 0 items / 1 error; without it 5 collected. This is a usage error, not a configuration defect — registering `filterwarnings` by hand in `pyproject` would make the marker silently inert whenever the plugin is off. Left as is (report, Decisions).

### 1.3 Test database rebuilt (the one deletion this package permits)
`ivgs_reconciliation_test` was at alembic `0055` — a migration held by WP-IVGS-12j that does not exist on `main` (the tree ends at `0054_wp_ivgs_12i_system_corrections.py`), so alembic could not downgrade it, and its 0055-only table `project_design_interviews` failed `test_wp59_deletion.py::TestCategoryMap::test_every_project_fk_table_is_in_the_map` in every WP-70 run. Recreated, this database only; production `ivgs` untouched (still `0054`, 236 MB, never named in any command):
```
docker exec ivgs-postgres psql -U ivgs -d postgres -Atc "select pg_terminate_backend(pid) from pg_stat_activity where datname='ivgs_reconciliation_test' and pid<>pg_backend_pid()"   # 0 rows
docker exec ivgs-postgres psql -U ivgs -d postgres -c "DROP DATABASE ivgs_reconciliation_test"
docker exec ivgs-postgres psql -U ivgs -d postgres -c "CREATE DATABASE ivgs_reconciliation_test OWNER ivgs ENCODING 'UTF8' LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8' TEMPLATE template0"
cd ivgs-api && DATABASE_URL="$TURL" ../.venv/bin/python -m alembic upgrade head     # rc=0
docker exec ivgs-postgres psql -U ivgs -d ivgs_reconciliation_test -Atc "select version_num from alembic_version"   # 0054
```
(owner, encoding and collation copied from the previous database: `ivgs | UTF8 | en_US.UTF-8`.)

## 2. Per suite

### 2.1 `ivgs-api` — 1870 passed, 0 failed
`=============== 1870 passed, 2417 warnings in 355.85s (0:05:55) ================`. No failure to classify. The 2417 warnings are `DeprecationWarning`s (jose `utcnow`, asyncpg teardown), unchanged.

### 2.2 `ivgs-workers` — 988 passed, 18 failed, 48 skipped, 15 errors
`===== 18 failed, 988 passed, 48 skipped, 21 warnings, 15 errors in 37.88s ======` (with §1.2; without `TEST_DATABASE_URL` the four `test_wp60_orphan_guard.py` tests skip instead: 984/18/52/15, failure set byte-identical).

| n | class | cause (first `E` line) | files |
|---|---|---|---|
| 14 | test drift | `TypeError: 'coroutine' object does not support the asynchronous context manager protocol` — the fixture `mock_db_session_factory = AsyncMock(return_value=session)` makes `factory()` a coroutine; production does `async with factory() as session`. Ledger P2.53. | `test_dlq_service.py` (10: `TestDLQEntryCreation` ×3, `TestDLQReplay` ×2, `TestDLQPeriodicProcessing` ×2, `TestDLQResolutions` ×3), `test_orphan_cleanup.py` (`TestScanType2::test_detects_missing_seaweedfs_files`, `TestScanType3::test_detects_zero_reference_assets`), `test_retry_engine.py` (`TestAttemptRecording` ×2) |
| 15 (errors) | collection / test configuration | `ModuleNotFoundError: No module named 'test_scheduler'` at fixture setup — `test_quality_gate.py:43` imports `FakeRedis` from the SCHEDULER suite, unresolvable under `--import-mode=importlib`. | `test_quality_gate.py` — all 15 |
| 2 | test drift | `ValueError: badly formed hexadecimal UUID string` — fixtures pass `project_id="proj-aaa-bbb-ccc"`; the tasks now do `UUID(project_id)`. | `test_stage1.py::TestStage1Integration::test_full_task_execution`, `test_stage2.py::TestStage2Integration::test_full_task_execution` |
| 1 | **product defect** (named, not fixed) | `Failed: DID NOT RAISE` — `Stage6Input.scene_audio_refs` (`ivgs-workers/tasks/talking_head_task.py`) has no `min_length=1`; a render with zero audio references is accepted. Frozen tree (`ivgs-workers/tasks/`). | `test_talking_head_task.py::TestStage6Input::test_requires_at_least_one_audio_ref` |
| 1 | test drift | `AssertionError: assert 0.0 > 0` — `quality_validator.py` stores `round(elapsed, 3)`; caption validation finishes under a millisecond. | `test_quality_validator.py::TestValidatorIntegration::test_caption_full_validation` |

Skips (48): `test_wp06_media_join.py` 19 and `test_wp39_media_join.py` 15 (no Redis at `127.0.0.1:16380`, by design), `test_wp44_video_validator.py` 10 and `test_wp42_voice.py` 2 (no ffmpeg/ffprobe on the host; present in the image), `temporal/test_wp41_replay.py` and `test_wp41_workflow_shape.py` 1 each (Temporal SDK lives in `/home/dev/.venv-ivgs-temporal`).

**`test_stage3.py`: 8 passed.** The order's premise (drifted patch targets and stale signatures, WP-44 §8.4) was true on 2026-08-26 and **was repaired by WP-52 the day before** (`83c0ee2`, *"test_stage3 rewritten against the signature that exists"*). Not an inherited failure; nothing to do.

### 2.3 `ivgs-scheduler` — 52 passed, 15 failed
`======================== 15 failed, 52 passed in 1.56s =========================`

| n | class | cause | files |
|---|---|---|---|
| 7 | collection / test configuration | `ImportError: cannot import name 'NoCapacityError' from 'main' (/opt/ivgs/ivgs-api/main.py)` (and `PhaseGateError`, `ConcurrencyLimitError`, `CircuitBreakerOpenError`, `ReservationNotFoundError`) — the root `pyproject.toml` `pythonpath` lists `ivgs-api` before `ivgs-scheduler`, so `from main import …` (`scheduler.py:233,293`, `test_admission.py`) resolves to the API's `main.py`. Ledger P2.51. Same structural shape the backup-worker fixed with its own inifile. | `test_admission.py` (6: `test_no_alive_nodes_fails`, `test_insufficient_vram_fails`, `test_release_nonexistent_reservation`, `test_invalid_stage_transition`, `test_exceeds_concurrency_limit`, `test_all_circuits_open_fails`), `test_scheduler.py::TestGpuSchedulerFirstFit::test_schedule_no_capacity_error` |
| 8 | test drift | `AttributeError: 'FakeRedis' object has no attribute 'zcount'` — the fake predates the circuit breaker's sorted-set calls. Ledger P2.52. | `test_circuit_breaker.py` (all 8: `TestErrorRateCalculation` ×2, `TestCircuitBreakerStates` ×5, `TestCircuitBreakerReset` ×1) |

(The 2026-08-25 baseline also listed 4 `test_load_balancer.py` failures under P2.52; they pass now.)

### 2.4 `ivgs-motion-renderer` — 24 passed, 2 skipped
`======================== 24 passed, 2 skipped in 2.96s =========================`. Skips: `test_wp_ivgs_09_renderer.py:265,278` — ffmpeg not on the host, present in the renderer image.

### 2.5 `ivgs-backup-worker` — 4 passed
`============================== 4 passed in 0.30s ===============================` with §1.2's three extra variables. Without them the suite is 4 failed at import (RC-J8, deliberate).

### 2.6 `tests_system` — 193 passed, 12 failed, 15 skipped, 30 errors (live stack)
`====== 12 failed, 193 passed, 15 skipped, 7 warnings, 30 errors in 6.48s =======`. Hosts were **not** hard-coded: WP-52's `tests_system/service_urls.py` already parameterises every host (`IVGS_TEST_HOST` default `192.168.1.90`, plus per-URL overrides; `E2E_BASE_URL` alias). The only `localhost` left in the tree is prose in a docstring (`test_wp60_scripts.py:85`). The order's premise is stale; nothing to parameterise.

| n | class | cause | files |
|---|---|---|---|
| 21 (errors) | test drift | `admin_token` / `admin_headers` fixtures POST `{"email", "password"}` to `/auth/login`; `LoginRequest` requires `username` → 422 (`Field required … username`), then `KeyError: 'access_token'`. Same class as WP-69's S2 (a client naming a column that does not exist), on the test side. | `integration/test_auth_integration.py` (`TestRegistration` ×3), `integration/test_dlq_integration.py` (5), `integration/test_pipeline_integration.py` (6), `integration/test_projects_integration.py` (6), `e2e/test_localization.py` (1) |
| 7 (4 errors + 3 failures) | **environment aggravator** | the live API rate-limits `/auth/login` at 5 per 60 s; the drifted fixtures burn it, so later logins in the same run answer `429 RATE_LIMITED` instead of 422/200/401. Which tests land on 429 depends on ordering. | errors: `test_auth_integration.py::TestLogin::test_access_token_works_for_api`, `::TestRBAC` ×2, `test_projects_integration.py` ×1; failures: `TestLogin::test_valid_login_returns_tokens` (429≠200), `::test_invalid_password_rejected`, `::test_nonexistent_user_rejected` (429≠401) |
| 2 | test drift | `KeyError: 'refresh_token'` — same login payload. | `test_auth_integration.py::TestTokenRefresh` ×2 |
| 1 (error) | test drift | `assert 422 == 200` — same login payload, e2e. | `e2e/test_project_lifecycle.py::TestProjectLifecycle::test_full_pipeline_lifecycle` |
| 1 | test drift | `assert 404 == 401` — `POST /auth/register` does not exist; `auth.py` serves login/logout/refresh/me. | `test_auth_integration.py::TestRegistration::test_unauthenticated_register_rejected` |
| 2 | test drift | `GET /fleet` returns an object (`alive_nodes`, `available_vram_mb`, …); the test indexes a list (`assert False`, `KeyError: 0`). P2.57. | `integration/test_gpu_integration.py::TestFleetStatus` ×2 |
| 2 | test drift | `POST /schedule` → 422: the request body no longer matches the endpoint schema. P2.58. | `test_gpu_integration.py::TestJobScheduling::test_schedule_job`, `::test_schedule_exceeds_vram` |
| 1 | test drift | `assert 403 == 401` — FastAPI `HTTPBearer` answers 403 on a missing credential. | `test_projects_integration.py::TestProjectCreate::test_create_project_unauthenticated` |

Skips (15): `smoke/test_gpu_nodes.py`, all *"GPU smoke tests need the node registry env"*. Expected. ⚠ On GitHub only the four static paths WP-55 measured are run (`providers`, `spec_compliance`, `test_compliance_scanner.py`, `test_alert_rules_have_metrics.py`); the rows above are node-01-only and are listed in `.github/ci/inherited_failures.txt` under that heading so a node-01 run through the plugin is honest too.

### 2.7 frontend — 123 passed, 2 failed
`npm run test:logic` → `# tests 125 / # pass 123 / # fail 2`.

| test | class | cause |
|---|---|---|
| `ui-nav.test.mjs` T7 *every value the picker can offer is one the API accepts* | test drift | asserts `MEDIA_TYPES` is exactly `["image","video_clip","animation"]`; `src/lib/scenes.ts:59` has carried `motion_graphics` since WP-IVGS-09c (`189ac3f`, 2026-08-28), which the API accepts (`shared.models.enums.MEDIA_TYPES`). |
| `ui-nav.test.mjs` T2 *no tab is deferred, and every tab has a route segment or is Overview* | test drift | asserts `PROJECT_TABS.length === 11`; `src/lib/project-tabs.ts` has carried a twelfth tab, `models`, since WP-66 (`fa8ef6d`, 2026-08-26). Every tab has a segment and none says "soon" — the property the test exists for still holds. |

Both fixed test-side in this package (report §3).

## 3. Cause classes, totalled

| class | Python | frontend |
|---|---|---|
| test drift | 14 + 2 + 1 (workers) + 8 (scheduler) + 30 (tests_system: 21 + 2 + 1 + 1 + 2 + 2 + 1) = **55** | 2 |
| collection / test configuration | 15 (workers `test_quality_gate`) + 7 (scheduler `main`) = **22** | — |
| environment aggravator | **7** (live rate limit) | — |
| product defect | **1** (`Stage6Input.scene_audio_refs` min length) | — |
| environment: dependency / host / database | **0** failing tests. Recorded drifts: Python 3.12.3 vs 3.12.8, `pytest-asyncio` 0.24.0 vs 0.25.2, the missing dev packages; the 0055 test database (rebuilt). | — |

## 4. Reproducing on node-01
§1.2's block, then per suite the commands in §0. Output files of these runs lived in the session scratchpad (`base_api.txt`, `base_ivgs-workers_env.txt`, `base_ivgs-scheduler.txt`, `base_ivgs-motion-renderer.txt`, `base_backup.txt`, `base_tests_system.txt`, `base_frontend.txt`) and are declared lost; every figure above is quoted from them.
