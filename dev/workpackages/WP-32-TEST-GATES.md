# WP-32-TEST-GATES — Make `pytest` run this project's tests

| | |
|---|---|
| **Ledger** | **Track P** · findings F1, F2, F3, F5 of `reports/WP-IVGS-0-report_2026-08-22.md` |
| **Tier** | A (self-proving — the gate proves itself by running) |
| **Report** | `reports/WP-32-TEST-GATES-report_<YYYY-MM-DD>.md` |
| **Authored** | 2026-08-22 by the WP-IVGS-0 session, under operator ruling of the same day. **AUTHORED ONLY — NOT EXECUTED.** |
| **Prerequisite** | None. Nothing here depends on the Model Store (P1.4m) or on any deploy. |

> ## Why this exists
> There is no single command that runs this project's tests. `pytest` at the repo
> root — with the `testpaths` the repo itself configures — **dies at collection**
> and runs nothing at all. Three of the four configured test paths cannot be
> collected. That is how 87 days of CI blindness (P1.4k) stayed invisible from the
> inside as well as from CI: the local signal CLAUDE.md calls authoritative does
> not exist as a single fact.
>
> This package does not add coverage. It makes the coverage that already exists
> **runnable**. Everything below was measured on 2026-08-22 at `4c21460`; re-verify
> before fixing, as line numbers drift and defects do not.

## The rules of this project

- One package = one commit series · **commit and HOLD — the operator pushes.**
- Delete nothing without operator sign-off to a named list.
- Every report states what was verified, HOW (command + output), and what was NOT.
- If this order conflicts with what you find in the tree, STOP on that item and
  report the conflict — do not improvise.

## STEP 0 — record the baseline before touching anything

Run each of the four paths separately and record what passes and fails **now**, so
your changes are never blamed for pre-existing failures or credited with
pre-existing passes. The API suite needs a disposable database (its conftest
TRUNCATEs and refuses any name not ending `_test`); `ivgs_reconciliation_test`
already exists on `ivgs-postgres`, which is published on **192.168.1.90:5432**, not
127.0.0.1. Source credentials from `ivgs-infra/.env` — never `ivgs-infra/.env.node01`
(CLAUDE.md §3), and never print them.

Baseline measured 2026-08-22 for comparison:

| Path | Result |
|---|---|
| `pytest` (all `testpaths`) | **EXIT 4, nothing runs** |
| `pytest ivgs-api/tests` | 1 failed, 578 passed |
| `pytest ivgs-workers/tests` | 14 failed, 120 passed, 22 errors, 7 collection errors *(after WP-IVGS-0's conftest fix; before it: 0 collected, 15 collection errors)* |
| `pytest tests` | **EXIT 4, nothing runs** |

---

## THE FOUR DEFECTS — fix in this order; one commit each

### WP-32.1 — `pytest` cannot collect at all *(F1)*

**Evidence:** with `testpaths = ["ivgs-api/tests", "ivgs-workers/tests",
"ivgs-scheduler/tests", "tests"]` (`pyproject.toml`), collection dies:

```
_pytest.pathlib.ImportPathMismatchError:
  ('tests.conftest', '/opt/ivgs/ivgs-api/tests/conftest.py',
   PosixPath('/opt/ivgs/tests/conftest.py'))
```

`ivgs-api/tests/__init__.py` and `tests/__init__.py` both exist, so both directories
claim the module name `tests` and the second import collides with the first.

**Fix:** give the two suites distinct import identities. The least invasive route is
`consider_namespace_packages` / `importmode=importlib` in `pyproject.toml`; the
explicit route is to drop one `__init__.py` or rename one package. **Try the config
route first and only rename if it genuinely cannot work** — a rename touches every
intra-suite import, and `ivgs-api/tests/test_wp_ivgs_0_tier_dispatch.py` already
imports a fixture across files (`from tests.test_wp_ivgs_0_dispatch_context import
recorder`), so intra-package imports are load-bearing.

**Accept:** bare `pytest` from the repo root collects **all four** paths and runs to
a summary line. The number of collected tests is at least the sum of the four paths
run separately. No path is silently skipped — prove it by comparing collected counts.

---

### WP-32.2 — the whole root `tests/` tree is dead *(F2)*

**Evidence:** `pytest tests` exits 4 before any test runs.

```
tests/conftest.py:34: from shared.database import Base
shared/database.py:38: engine = create_async_engine(settings.DATABASE_URL, ...)
E   ModuleNotFoundError: No module named 'aiosqlite'
```

`tests/conftest.py:23-33` sets `DATABASE_URL=sqlite+aiosqlite:///./test.db` at import
time; `aiosqlite` is not installed in `.venv`. Every test under `tests/e2e`,
`tests/integration`, `tests/smoke`, `tests/providers` and `tests/spec_compliance` has
therefore never run.

**Fix:** decide **and state which** — (a) add `aiosqlite` to the test requirements,
or (b) point this suite at the same disposable Postgres the API suite uses. (b) is
the more honest option if these tests are meant to exercise Postgres behaviour:
SQLite will not reproduce the enums, `TRUNCATE ... CASCADE`, or the partitioning this
schema relies on, so passing under SQLite would prove less than it appears to.
Whichever is chosen, say why in the report.

**Accept:** `pytest tests` collects and runs. **Report the pass/fail result honestly
— do not fix the tests themselves in this package.** A tree that has never run will
almost certainly fail; that failure list is a deliverable, not a defeat, and becomes
its own follow-up.

---

### WP-32.3 — seven worker test files cannot be imported *(F3)*

**Evidence:** three missing modules, seven files:

| Missing module | Files |
|---|---|
| `ivgs_workers` | `test_dlq_service.py`, `test_fallback_chain.py`, `test_orphan_cleanup.py`, `test_retention.py`, `test_retry_engine.py` |
| `tasks.prototype_draft_task` | `test_composition.py` |
| `tasks.stage4_voiceover` | `test_stage4.py` |

*(Measured file-by-file on 2026-08-22, one `pytest` run per file — not collapsed from a
`--continue-on-collection-errors` summary.)*

The last two are the filename-vs-registered-name trap (CLAUDE.md §7) leaking into the
tests: `STAGE_TASK_MAP` registers `tasks.stage4_voiceover.generate_voiceover_task` and
`tasks.prototype_draft_task.assemble_prototype_draft`, but the files on disk are
`stage5_voiceover.py` and `stage7_prototype_draft.py`. The tests import by filename;
the orchestrator dispatches by registered name.

**Fix:** point each test at the module that exists. **Do NOT rename the task files or
change any registered Celery name to make the imports line up** — the registered names
are what the orchestrator dispatches and what any in-flight message carries; renaming
them is an AD-05 concern, not a test-gate concern. `ivgs_workers` is a separate
question: establish whether that package is supposed to exist (`pyproject.toml`
`known-first-party` names it, and `mypy` overrides reference `ivgs_workers.tests.*`)
or whether the import is simply wrong, and say which.

**Accept:** all seven collect. Their pass/fail results are recorded, **not fixed** —
same discipline as WP-32.2.

---

### WP-32.4 — `test_stage1.py` imports the wrong `VLLMResponse` *(F5)*

**Evidence:** two long-standing failures with nothing to do with Stage 1:

```
assert 'Empty' in "'VLLMResponse' object has no attribute 'content'"
```

`test_stage1.py` imports `VLLMResponse` from `models.task_result` — the **pydantic**
model, which has no `.content` or `.finish_reason` — instead of
`clients.vllm_client`, the **dataclass**, which defines both as properties
(`vllm_client.py:98-108`). Affects
`TestVLLMInteraction::test_refine_single_transcript` and
`::test_refine_handles_empty_response`. Left failing by WP-IVGS-0 on purpose so its
baseline comparison stayed honest.

**Fix:** import from `clients.vllm_client`. Check whether `test_stage2.py`,
`test_stage3.py` and `test_talking_head_task.py` carry the same mistake — several of
their failures look similar and were not diagnosed.

**Accept:** both tests pass, and every other test's result is unchanged.

---

## Scope

**In:** `pyproject.toml` pytest configuration, `conftest.py` files, test-only imports,
test requirements. **Out:** production code of any kind; renaming task modules or
registered Celery names; fixing tests that fail once they start running (that is the
follow-up this package creates); CI runner revival (P1.4k, deferred).

## Exit gate

`pytest` from the repo root, one command, collects and runs all four paths and prints
one summary line. The report carries the baseline table above, the same table after,
and an explicit list of every test that **newly runs** — split into newly passing and
newly failing — because a suite that has never executed will surface real failures and
those are the point, not a regression. State plainly which of WP-32.2's two options
was taken and why.
