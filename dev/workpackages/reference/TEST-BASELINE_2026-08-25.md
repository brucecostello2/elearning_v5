# IVGS v5 — test baseline, 2026-08-25

**Produced by WP-52-TESTENV. This is the document future packages diff against
instead of re-deriving the baseline.** Every failure below has a cause and
either a ledger id or a stated reason it is expected. An unexplained entry here
is a defect in this document.

Measured on node-01 against the live stack at the commits listed in §7.
Nothing here was inferred from reading code: every count is from a run whose
output is quoted.

---

## 0. Headline

| Tree | passed | failed | skipped | errors | Was |
|---|---|---|---|---|---|
| `ivgs-api` | **833** | **0** | 0 | 0 | 2 failed / 831 passed (WP-45) |
| `ivgs-workers` | 754 | 22 | 48 | 15 | 27 failed (WP-45) |
| `ivgs-scheduler` | 22 | 21 | 0 | 0 | 9 passed / 2 failed / 32 errors |
| `ivgs-backup-worker` | **4** | **0** | 0 | 0 | 4 errors (never ran) |
| `tests_system` | 30 | 16 | 15 | 30 | 15 passed / 31 failed / 28 errors |
| **Total** | **1643** | **59** | **63** | **45** | |

`ivgs-api` and `ivgs-backup-worker` are GREEN. The other three are red for 11
distinct causes, all named below.

The scheduler's "was" column is not a regression: 32 of its 43 tests errored at
setup on one unresolvable import and never ran. WP-52 resolved that import, so
13 previously-invisible tests now pass and 19 previously-invisible failures are
now visible and diagnosed. Fewer green-looking rows, more truth.

---

## 1. The environment these numbers require

The suites do not carry the addresses of the services they talk to. node-01
publishes on its LAN address, **not** on loopback — `docker ps` shows
`192.168.1.90:5432->5432/tcp`, never `0.0.0.0`. A run without this block gets
connection-refused, not slowness.

```bash
# node-01. Password comes from ivgs-infra/.env; never paste it into a document.
cd /opt/ivgs
PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)

export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
unset PGPW PGUSER
```

`tests_system` needs nothing else: `tests_system/service_urls.py` defaults every
host to `192.168.1.90` and each URL stays individually overridable
(`IVGS_TEST_HOST`, `IVGS_TEST_API_URL`, `IVGS_TEST_SCHEDULER_URL`,
`IVGS_TEST_REDIS_URL`, `IVGS_TEST_SEAWEEDFS_*`; `E2E_BASE_URL` is still honoured
as an alias for the API URL).

**The API suite's guard is load-bearing.** `ivgs-api/tests/conftest.py:94`
refuses any database whose name does not end `_test` or contain
`reconciliation`, because the `db_session` fixture `TRUNCATE`s every table after
every test. Point it at `ivgs` and it would destroy production. Do not weaken it.

---

## 2. `ivgs-api` — 833 passed, 0 failed

```bash
.venv/bin/python -m pytest ivgs-api/tests
```

Runtime 4m06s. **No remaining failures.**

WP-45 left this tree at 2 failed / 831 passed; both were
`test_health.py::test_health_check_success` and `::test_health_check_no_auth_required`,
and both were one defect in `conftest.py`, fixed by WP-52 — see report §3.2. The
short version: the fixture patched `shared.database.check_db_connection`, but
`app/api/v1/health.py:13` binds that function by value at import time, so the
patch never reached the health route. It appeared to work only while
`app.api.v1.health` happened to be first imported inside a test. Two modules
(`test_node_topology.py:7`, `test_wp27_manifest_layers.py:14`) import sibling
route modules at COLLECTION time, which broke the accident — which is why the
file passed alone and failed in the suite. The patch is now applied where the
name is used.

---

## 3. `ivgs-workers` — 754 passed, 22 failed, 48 skipped, 15 errors

```bash
.venv/bin/python -m pytest ivgs-workers/tests
```

Runtime 20s.

### 3.1 Errors (15) — all one cause

| Test | Cause | Ledger |
|---|---|---|
| `test_quality_gate.py` — all 15 | `test_quality_gate.py:43` does `from test_scheduler import FakeRedis` — a helper that lives in the SCHEDULER's suite. Unresolvable under `--import-mode=importlib`, which does not put a test file's directory on `sys.path`. | **P2.51** |

### 3.2 Failures (22)

| Count | Tests | Cause | Ledger |
|---|---|---|---|
| 10 | `test_dlq_service.py` (all) | `mock_db_session_factory` is built as `AsyncMock(return_value=session)`, so `factory()` returns a **coroutine**. The production code does `async with self._db_session_factory() as session:` — a real `async_sessionmaker` is a SYNC callable returning an async context manager. `TypeError: 'coroutine' object does not support the asynchronous context manager protocol`. One-word fix per fixture (`MagicMock`). | **P2.53** |
| 2 | `test_orphan_cleanup.py::TestScanType2/TestScanType3` | Same fixture defect. | **P2.53** |
| 2 | `test_retry_engine.py::TestAttemptRecording` (both) | Same fixture defect. | **P2.53** |
| 1 | `test_fallback_chain.py::test_all_levels_fail_routes_to_dlq` | **A real production defect.** `services/fallback_chain.py:459` does `from ivgs_workers.services.dlq_service import FailureCategory`. No `ivgs_workers` package exists — the directory is `ivgs-workers` (hyphen), which is not an importable name. Confirmed unimportable INSIDE the deployed image (`ivgs-workers:v5.11.0-apibatch`), so on chain exhaustion the DLQ hand-off raises before it can send. Needs a build. | **P2.50** |
| 2 | `test_stage1.py::test_full_task_execution`, `test_stage2.py::TestStage2Integration::test_full_task_execution` | Test-side stale: the fixtures pass `project_id="proj-aaa-bbb-ccc"`, and the tasks now do `UUID(project_id)` (`stage1_transcript.py:506`, `stage2_storyboard.py:526`). `ValueError: badly formed hexadecimal UUID string`. Same class as the ids WP-52 corrected in `test_stage3.py`. | **P2.59** |
| 1 | `test_stage2.py::test_media_type_normalization` | **A real defect with pipeline consequences.** `models/task_result.py:240` declares `media_type: str = "image"` — a bare string, no enum coercion, no normalisation. An LLM that writes `"video"` gets `"video"`, and `stage3_images.py:372` branches on `scene.media_type == MediaType.VIDEO_CLIP.value`, so that scene silently takes the IMAGE path. | **P2.54** |
| 1 | `test_stage2.py::test_duration_validation` | Same model: `duration_seconds: float = 10.0` with no lower bound, so `-1` is accepted. `DID NOT RAISE`. | **P2.54** |
| 1 | `test_stage2.py::test_json_with_preamble` | `_extract_json_from_response` (`stage2_storyboard.py:348`) searches for `[` BEFORE `{`. A preambled `{"scenes": [...]}` therefore returns the inner ARRAY and the object wrapper is discarded. The fenced and bare-JSON paths are correct, which is why only this one of the three fails. | **P2.55** |
| 1 | `test_talking_head_task.py::test_requires_at_least_one_audio_ref` | `Stage6Input.scene_audio_refs` (`talking_head_task.py:126`) has no `min_length=1`, so a render with zero audio references is accepted. `DID NOT RAISE`. | **P2.56** |
| 1 | `test_quality_validator.py::test_caption_full_validation` | `quality_validator.py:299` stores `round(elapsed, 3)`. Caption validation finishes in well under a millisecond, so it records `0.0` and `assert report.validation_duration_s > 0` fails. The measurement is too coarse, not the assertion too strict — repair on the code side (more precision), not by relaxing the test. | **P2.59** |

**48 skipped** — pre-existing and expected; not introduced or changed by WP-52.

---

## 4. `ivgs-scheduler` — 22 passed, 21 failed

```bash
.venv/bin/python -m pytest ivgs-scheduler/tests
```

Runtime 1.2s. WP-52 added `ivgs-scheduler/tests/conftest.py`, which puts this
suite's own directory on `sys.path` so `from test_scheduler import FakeRedis`
resolves again (three modules do it). That converted 32 setup errors into 13
passes and 19 diagnosed failures.

| Count | Tests | Cause | Ledger |
|---|---|---|---|
| 6 | `test_admission.py` — `test_invalid_stage_transition`, `test_insufficient_vram_fails`, `test_no_alive_nodes_fails`, `test_exceeds_concurrency_limit`, `test_all_circuits_open_fails`, `test_release_nonexistent_reservation` | `ImportError: cannot import name 'PhaseGateError' from 'main' (/opt/ivgs/ivgs-api/main.py)`. The scheduler's PRODUCTION code does `from main import ...` at six sites (`admission_control.py:230,252,265,292,318,348`, `scheduler.py:210,260`, `gpu_registry.py:208`) to dodge a circular import. Both `ivgs-api` and `ivgs-scheduler` ship a top-level `main.py`; `pyproject.toml` lists `ivgs-api` FIRST on `pythonpath`, so `main` is the API's. `ivgs-api/tests/test_ws_job_status.py:22` genuinely needs `main` to be the API's, so path order cannot satisfy both. | **P2.51** |
| 1 | `test_scheduler.py::test_schedule_no_capacity_error` | Same import, via `scheduler.py:210`. | **P2.51** |
| 9 | `test_circuit_breaker.py` — all but `test_zero_requests_returns_zero_rate` | `AttributeError: 'FakePipeline' object has no attribute 'zremrangebyscore'`. The fake has not kept up with the production sliding-window sorted sets. | **P2.52** |
| 1 | `test_circuit_breaker.py::test_zero_requests_returns_zero_rate` | `AttributeError: 'FakeRedis' object has no attribute 'zcount'`. Same drift. | **P2.52** |
| 4 | `test_load_balancer.py` — `test_idle_gpu_has_max_weight`, `test_busy_gpu_has_low_weight`, `test_candidates_sorted_by_weight_desc`, `test_balanced_fleet_no_warning` | Same missing `zremrangebyscore`. | **P2.52** |
| 1 | `test_scheduler.py::test_reservation_extension` | `TypeError: FakePipeline.hset() takes from 2 to 3 positional arguments but 4 were given` — the fake models only the `mapping=` form. | **P2.52** |

---

## 5. `ivgs-backup-worker` — 4 passed, 0 failed

```bash
.venv/bin/python -m pytest ivgs-backup-worker/tests   # needs BACKUP_TEST_DSN, §1
```

Runtime 0.3s. **No remaining failures.**

This tree had never run. Two blockers, both fixed by WP-52:

1. `tests/conftest.py` defaults `POSTGRES_DSN_SYNC` to
   `postgresql://postgres@127.0.0.1:5432/ivgs_test` — a host node-01 does not
   publish and a database that does not exist. `BACKUP_TEST_DSN` (§1) overrides it.
2. `from tasks.backup_tasks import ...` resolved to **`ivgs-workers/tasks/`**.
   Both services ship a top-level `tasks` package; the root `pyproject.toml`
   lists `ivgs-workers` on `pythonpath` and does not list `ivgs-backup-worker`
   at all. A `PYTHONPATH=` prefix does not help — pytest inserts its own entries
   ahead of the inherited environment. WP-52 added `ivgs-backup-worker/pytest.ini`
   so the service gets its own import namespace. This MITIGATES the collision;
   it does not resolve it (**P2.51**).

The root run is unaffected: `pyproject.toml`'s `testpaths` never included this
tree, so nothing else resolves through that inifile. Verified — `pytest
ivgs-api/tests/test_health.py` still reports `configfile: pyproject.toml`.

---

## 6. `tests_system` — 30 passed, 16 failed, 15 skipped, 30 errors

```bash
.venv/bin/python -m pytest --timeout=120 tests_system
```

Runtime 1.5s. Every module now REACHES its service: the responses below are
422/429/404/200, not connection-refused. That is the WP-52 Task 2 deliverable;
what the responses say is a separate matter, ledgered here.

### 6.1 Errors (30) — one cause, one aggravator

All 30 are `admin_token` / `admin_headers` fixture setup.

| Count | Modules | Cause | Ledger |
|---|---|---|---|
| 28 | `test_auth_integration` (7), `test_dlq_integration` (5), `test_pipeline_integration` (6), `test_projects_integration` (10) | The fixtures POST `{"email": ..., "password": ...}` to `/auth/login`. `LoginRequest` (`ivgs-api/app/schemas/auth.py:12`) takes **`username`**, and the `users` table has no `email` column at all — verified against the live schema. Result: `422 {"loc":["body","username"],"msg":"Field required"}`. After five such attempts the API's own 5/min login rate limit turns the rest into `429 RATE_LIMITED`, so the visible error changes partway down the run. Both are the same stale-contract defect; the 429 is its shadow. | **P2.57** |
| 2 | `test_localization`, `test_project_lifecycle` (e2e) | Same login payload. The e2e modules stop at the login and never dispatch a pipeline — confirmed: zero rows added to `projects` or `render_jobs` during these runs. | **P2.57** |

### 6.2 Failures (16)

| Count | Tests | Cause | Ledger |
|---|---|---|---|
| 6 | `test_auth_integration` — `test_valid_login_returns_tokens`, `test_invalid_password_rejected`, `test_nonexistent_user_rejected`, `test_refresh_returns_new_tokens`, `test_used_refresh_token_rejected`, `test_logout_invalidates_refresh_token` | The same `email`-for-`username` payload, in the test bodies rather than the fixtures. `422 != 200`. | **P2.57** |
| 1 | `test_auth_integration::test_unauthenticated_register_rejected` | `POST /auth/register` returns **404** — the route does not exist. `ivgs-api/app/api/v1/auth.py` registers only `/login`, `/logout`, `/refresh` and a GET; user creation is `POST /users` (`users.py:54`). The test targets an API that is not there. | **P2.57** |
| 2 | `test_gpu_integration::test_fleet_returns_all_nodes`, `::test_fleet_node_schema` | The scheduler's `GET /fleet` returns an OBJECT (`{'alive_nodes': 3, 'available_vram_mb': 293661, 'fleet_utilization_pct': 0.0, ...}`); the tests expect a LIST of node rows. `assert isinstance(data, list)` / `KeyError: 0`. Contract drift between the scheduler and its tests. | **P2.58** |
| 2 | `test_gpu_integration::test_schedule_job`, `::test_schedule_exceeds_vram` | `POST /schedule` returns 422 — the request body the tests send no longer matches the endpoint's schema. | **P2.58** |
| 1 | `test_projects_integration::test_create_project_unauthenticated` | Unauthenticated `POST /projects` returns **403**, the test expects **401**. FastAPI's `HTTPBearer` returns 403 on a missing credential. One of the two is wrong and it is worth deciding which; §16 of the spec says 401. | **P2.58** |
| 4 | `test_compliance_scanner::test_scanner_detects_pip_packages[*]` | **A real defect in the code under test, and these four tests are RIGHT to fail.** `scripts/compliance_scanner.py`'s `match_glob` handles only `*`-prefixed globs and exact filenames, so `"requirements*.txt"` matches nothing and §F.2 **Rule 2 has never been enforced**. Anyone can add `openai==1.0.0` to a requirements file and the CI compliance gate passes. Measured: all four prohibited packages score `rc=0` (clean). Fixing the glob would NOT turn the repo red — no tracked requirements file carries a prohibited package today. | **P2.49** |

**15 skipped** — `smoke/test_gpu_nodes.py`, all with the reason *"GPU smoke tests
need the node registry env (configured node / live fleet)"*. Expected; this
package touches no GPU node.

---

## 7. Provenance

* Measured 2026-08-25 on node-01 (192.168.1.90) against the running stack:
  `ivgs-api:v5.11.0-apibatch`, `ivgs-workers:v5.11.0-apibatch`,
  `ivgs-scheduler:latest`, `ivgs-backup-worker:v5.1.0-stream-b`,
  `postgres:17.2`, `redis:7.4`.
* Python 3.12.3, pytest 8.3.4, pytest-asyncio 0.24.0, pytest-timeout 2.3.1
  (installed by WP-52).
* Test database `ivgs_reconciliation_test`, migration 0028 (applied by WP-45).
* Every count in §0 is the tail line of a real run. No number here was carried
  forward from an earlier package without being re-measured.

## 8. How to use this document

Diff against it. A package that touches module X re-runs X's tree and compares
to the table for that tree. A NEW failure is a regression and must be fixed or
argued. A failure already listed here with its ledger id is not that package's
problem — cite the row and move on.

If a package fixes one of the ledgered causes, update the affected rows here in
the same commit. This document going stale is the one way it becomes worse than
having no baseline at all.
