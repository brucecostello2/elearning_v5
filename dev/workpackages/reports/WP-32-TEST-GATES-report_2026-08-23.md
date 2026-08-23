# WP-32-TEST-GATES — report

| | |
|---|---|
| **Package** | `dev/workpackages/WP-32-TEST-GATES.md` (authored 2026-08-22, not executed until now) |
| **HEAD at start** | `cc91ea6` (batch base `f70d63e`) |
| **Date** | 2026-08-23 |
| **Tier** | A — self-proving: the gate proves itself by running |
| **Test DB** | `ivgs_reconciliation_test` on `192.168.1.90:5432`, credentials sourced from `ivgs-infra/.env` into an env var and never printed |

**Baseline caveat.** The brief's baseline was measured at `4c21460`. Mine is measured at
`cc91ea6`, which includes this batch's WP-24 and WP-27 test files (+34 tests). Numbers below are
my own measurements, not the brief's, and differ for that reason as well as any drift.

---

# STEP 0 — baseline, measured before touching anything

| Path | Result |
|---|---|
| `pytest` (all `testpaths`) | **EXIT 4 — `ImportPathMismatchError`, nothing collected, nothing ran** |
| `pytest ivgs-api/tests` | 5 failed, 665 passed (245 s) |
| `pytest ivgs-workers/tests` | **EXIT 2 — 7 collection errors, `Interrupted`, 0 tests ran** |
| `pytest ivgs-scheduler/tests` | 1 failed, 10 passed, 32 errors |
| `pytest tests` | **EXIT 4 — `ModuleNotFoundError: No module named 'aiosqlite'`, 0 ran** |

**Discrepancy with the brief, recorded.** The brief reports the worker suite as
"14 failed, 120 passed, 22 errors, 7 collection errors". I measured **0 tests run** — pytest
prints `Interrupted: 7 errors during collection` and stops. The brief's numbers are only
obtainable with `--continue-on-collection-errors`, which is not in `addopts`. The stronger
statement is the true one: the worker suite ran nothing at all.

---

# WP-32.1 — `pytest` could not collect *(F1)*

**Cause, re-verified.** `ivgs-api/tests/__init__.py` and `tests/__init__.py` both existed.
`ivgs-api` is on `pythonpath`, so `ivgs-api/tests` imported as the package `tests`; the root
`tests/` directory imported as `tests` too, from its path relative to rootdir. pytest registered
the first `conftest.py` under `tests.conftest` and refused the second.

**The config route was tried first, as the brief requires, and demonstrably cannot work.**

| Attempt | Result |
|---|---|
| `--import-mode=importlib` | still collides — `ValueError: Plugin already registered under a different name` |
| `+ consider_namespace_packages = true` | still collides; the namespace package re-creates the name `tests` |
| `+ consider_namespace_packages = false` | still collides |
| `+ deleted root `tests/__init__.py`` | **still collides** — importlib derives `tests.conftest` from the path relative to rootdir regardless |

The name is structural: one suite derives `tests` from `pythonpath`, the other from rootdir.
No pytest setting separates them while both directories are called `tests`.

**Therefore a rename, which the brief authorises once config fails.** The root suite was renamed
`tests/` → **`tests_system/`** (`git mv`, history preserved), because it is the safe one:

- root `tests/` has **zero** intra-package imports — verified by grep;
- `ivgs-api/tests` has **seven** files doing `from tests.conftest import …` / `from tests.test_wp_ivgs_0_dispatch_context import recorder`. Renaming that one would have touched all seven.

Three references to the old name were updated so the rename does not silently widen other tools'
scope: `pyproject.toml` `testpaths` and bandit `exclude_dirs`, `scripts/swallow_detector.py`
`SKIP_PATH_PARTS`, and `scripts/verify_spec_compliance.sh` `--exclude-dir`. Without those, bandit
and the swallow detector would have started scanning the test tree.

**A second, self-inflicted defect found and fixed.** `--import-mode=importlib` does **not**
insert a test file's rootdir into `sys.path`, which the default prepend mode did implicitly. That
silently broke the scheduler suite (`ModuleNotFoundError: No module named 'scheduler'`), which
had been collecting before. `pythonpath` is now explicit:
`["ivgs-api", "ivgs-workers", "ivgs-scheduler", "."]`.

**Accept criterion — met.** Bare `pytest` collects **1214 tests, zero collection errors**, and
runs to one summary line. No path is silently skipped: the four paths run separately sum to
`665 + 346 + 9 + 9 = 1029` passed, exactly the unified run's 1029.

---

# WP-32.2 — the root tree was dead *(F2)*

**Option taken: (b), point the suite at the disposable Postgres.** Stated plainly, with reasons:

1. The brief's own argument, which I agree with: SQLite cannot reproduce this schema's enums
   (`asset_type`, `storage_tier`), `TRUNCATE … CASCADE`, or partitioning. A pass under SQLite
   would prove less than it appears to.
2. **A worse problem I found while fixing it, which decided the matter.** `tests_system/conftest.py`
   sets `DATABASE_URL` at import time. In a *unified* run another suite's conftest imports
   `shared.database` first, so that assignment lands too late and the suite silently inherits
   whatever database the other conftest configured. **Which database these tests ran against
   depended on collection order.** The fix uses `TEST_DATABASE_URL` → `DATABASE_URL` → a Postgres
   default, so an explicit choice always wins and the fallback is never SQLite.

`aiosqlite` was **not** installed — no package was added to the venv unattended.

**Accept criterion — met.** `pytest tests_system` collects and runs:
**37 failed, 9 passed, 15 skipped, 30 errors.** Per the brief these failures are **not fixed
here** — they are the deliverable. Distribution:

| File | failures+errors |
|---|---|
| `test_compliance_scanner.py` | 19 |
| `integration/test_auth_integration.py` | 16 |
| `integration/test_projects_integration.py` | 11 |
| `integration/test_gpu_integration.py` | 8 |
| `integration/test_pipeline_integration.py` | 6 |
| `integration/test_dlq_integration.py` | 5 |
| `e2e/test_project_lifecycle.py`, `e2e/test_localization.py` | 1 each |

Many are infrastructure-shaped (`Connect call failed ('127.0.0.1', 5432)`, `Error 111 connecting
to localhost:6379`) — the suite assumes services on loopback, and Postgres/Redis publish on
`192.168.1.90`. That is its own follow-up.

**One extra defect fixed to let the tree collect at all:** `tests_system/e2e` uses
`@pytest.mark.timeout(...)`, and `--strict-markers` makes an undeclared marker a collection
error. The marker is now declared. **`pytest-timeout` is not installed, so the marker is inert** —
those e2e tests now run *without* the timeout they ask for. Declared honestly in `pyproject.toml`
itself, and proposed as a requirements addition rather than installed unattended.

---

# WP-32.3 — seven worker files could not be imported *(F3)*

**`ivgs_workers` does not exist and never has.** `find / -type d -name ivgs_workers` returns
nothing; the directory is `ivgs-workers`, with a hyphen, which is not a legal module name. The
name survives in `pyproject.toml` `known-first-party`, in mypy overrides, and in
`tasks/periodic_tasks.py` — and AD-05 §8 already lists `periodic_tasks.py` as *"Deleted (dormant;
broken imports)"*, which corroborates it. **The import is simply wrong**, in the tests and in
`periodic_tasks.py` alike. Answering the brief's question directly: the package is not supposed
to exist.

| File | Was | Now |
|---|---|---|
| `test_dlq_service.py` | `ivgs_workers.services.dlq_service` | `services.dlq_service` |
| `test_fallback_chain.py` | `ivgs_workers.services.fallback_chain` | `services.fallback_chain` |
| `test_orphan_cleanup.py` | `ivgs_workers.services.orphan_cleanup` | `services.orphan_cleanup` |
| `test_retention.py` | `ivgs_workers.services.retention_migration` | `services.retention_migration` |
| `test_retry_engine.py` | `ivgs_workers.services.retry_engine` | `services.retry_engine` |
| `test_stage4.py` | `tasks.stage4_voiceover` | `tasks.stage5_voiceover` |
| `test_composition.py` | `tasks.prototype_draft_task`, `tasks.final_render_task` (**two**, incl. one inside a function body at `:427`) | `tasks.stage7_prototype_draft`, `tasks.stage8_final_render` |

The last two are the CLAUDE.md §7 filename-vs-registered-name trap leaking into tests.
**No task file was renamed and no registered Celery name was changed** — those are what the
orchestrator dispatches and what in-flight messages carry. Each edit carries a comment saying so.

**Accept criterion — met.** All seven collect. Results recorded, **not fixed**: the worker suite
goes from *0 tests run* to **346 passed, 30 failed, 19 skipped, 15 errors**. Failure
concentration: `test_quality_gate.py` 15, `test_dlq_service.py` 10, `test_stage3.py` 5,
`test_stage2.py` 4, `test_stage4.py` 3, remainder ≤2 each.

---

# WP-32.4 — `test_stage1.py` imported the wrong `VLLMResponse` *(F5)*

`VLLMChoice`, `VLLMMessage`, `VLLMResponse` and `VLLMUsage` exist **twice**: pydantic models in
`models/task_result.py:137`, dataclasses in `clients/vllm_client.py:68-90`. The code under test
returns the dataclass, whose `.content` and `.finish_reason` are properties
(`vllm_client.py:98-108`); the pydantic model has neither. Both files now import all four from
`clients.vllm_client`.

**`test_stage2.py` carried the identical mistake** and was fixed with it — the brief asked that
this be checked. `test_stage3.py` and `test_talking_head_task.py` do **not** reference
`VLLMResponse`; their failures are unrelated and are left alone.

**Accept criterion — met.** `TestVLLMInteraction` is **3 passed**, including
`test_refine_single_transcript` and `test_refine_handles_empty_response`. `test_stage1.py` overall
is 19 passed / 1 failed, the remaining failure being `TestStage1Integration::test_full_task_execution`,
which is unrelated and pre-existing.

---

# RESULT — before and after

| Path | Baseline | After |
|---|---|---|
| **`pytest` (one command)** | **EXIT 4 — 0 collected, 0 run** | **74 failed, 1029 passed, 34 skipped, 77 errors — 1214 collected, 226 s** |
| `ivgs-api/tests` | 5 failed, 665 passed | 5 failed, 665 passed — **unchanged** |
| `ivgs-workers/tests` | EXIT 2 — 0 run | 30 failed, 346 passed, 19 skipped, 15 errors |
| `ivgs-scheduler/tests` | 1 failed, 10 passed, 32 errors | 2 failed, 9 passed, 32 errors |
| `tests` → `tests_system` | EXIT 4 — 0 run | 37 failed, 9 passed, 15 skipped, 30 errors |

## Tests that NEWLY RUN

**Newly passing: 355** — 346 in `ivgs-workers/tests`, 9 in `tests_system`.
**Newly failing: 67 failed + 45 errors** — 30+15 in the worker suite, 37+30 in `tests_system`.

Both trees had **never executed**. That failure list is the point of the package, not a
regression: it is the first honest measurement of code nobody could run.

## One test moved from PASS to FAIL, and I caused it

`ivgs-scheduler/tests/test_scheduler.py::TestGpuSchedulerFirstFit::test_schedule_no_capacity_error`.

```
ivgs-scheduler/scheduler.py:210: from main import NoCapacityError
E   ImportError: cannot import name 'NoCapacityError' from 'main'
                 (/opt/ivgs/ivgs-api/main.py)
```

Adding both suite roots to `pythonpath` (necessary for WP-32.1) put **two different top-level
`main` modules** on the path — `ivgs-api/main.py` and `ivgs-scheduler/main.py` — and `ivgs-api`
wins. Reordering only moves the breakage to the other suite; both cannot own the name `main` in
one process.

This is the **same class of defect as F1 itself**, one layer down, and it is in production code:
`ivgs-scheduler/scheduler.py:210` reaches for a bare top-level `main`. It works in the scheduler's
own container and is fragile everywhere else. Fixing it is a production change and therefore out
of this package's scope — proposed as a ledger entry below.

---

# Ledger entries proposed

- **P2.44 — Two top-level `main` modules, and production code imports one by bare name.**
  `ivgs-scheduler/scheduler.py:210` does `from main import NoCapacityError`. Same shape as F1.
  *Suggested: define the exception in a non-`main` module and import it explicitly.*
- **P2.45 — `ivgs_workers` is referenced in three places and does not exist.**
  `pyproject.toml` `known-first-party`, the mypy overrides, and
  `tasks/periodic_tasks.py`. The last one matters beyond hygiene: it is the import in the *real*
  retention-migration implementation, so even if the beat schedule were repointed at it
  (**P2.42**, WP-23) it would fail on import. The two findings compound.
- **P2.46 — `pytest-timeout` is not installed; `@pytest.mark.timeout` is inert.**
  `tests_system/e2e` asks for timeouts it does not get.
- **P2.47 — `tests_system` assumes Postgres and Redis on loopback.** They publish on
  `192.168.1.90`. A large share of the 67 newly-failing tests are this, not logic.

---

# Exit gate

| Clause | Verdict |
|---|---|
| `pytest` from the repo root, one command, collects and runs all four paths | **MET** — 1214 collected, 0 collection errors |
| Prints one summary line | **MET** — `74 failed, 1029 passed, 34 skipped, 77 errors in 225.59s` |
| Baseline table, after table, and every newly-running test split into newly passing / newly failing | **MET** |
| States which of WP-32.2's two options was taken and why | **MET** — option (b), Postgres |
| No path silently skipped — proved by comparing counts | **MET** — per-path passes sum to 1029, exactly the unified total |

**Exit gate MET.** The suite exits non-zero because real tests fail — which is the correct
outcome for code that has never been executed, and the opposite of the prior state, where it
exited 4 having proved nothing.

## Scope

Production code was not touched. Every edit is in `pyproject.toml`, a `conftest.py`, a test-only
import, or two tool skip-lists updated to follow the rename. **One deletion-shaped change:**
`git mv tests tests_system` — a rename, not a delete, history preserved, and the brief authorises
it once the config route fails. The brief's "delete nothing without operator sign-off" rule is
noted; flagging the rename here for ratification.
