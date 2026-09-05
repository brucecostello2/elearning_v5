# WP-74 — CI BASELINE report

**Date:** 2026-09-05 · **Branch:** `wp-74-ci-baseline` from `origin/main` `9c406e8` (checked after `git fetch`); commit and HOLD, not pushed · **Executor:** coding agent, node-01, one session · **Tier:** B (observable) · **Scope kept:** tests, test configuration, the CI workflow and tracked docs only; no product code; no formatting pass; no file deleted; nothing under `ivgs-workers/tasks/` or `ivgs-workers/temporal_pipeline/`; `ivgs-infra/.env.node01` never staged. **The one permitted deletion** — the test database `ivgs_reconciliation_test` — was made (§1.3 of the inventory); production `ivgs` was never named in any command.

## STATE AT SESSION END

**Done.** The inventory `dev/audit/test_baseline_2026-09-05.md` (committed first, `9fac417`), two environment/test-side fix commits, the CI change, this report, the board row. **Mid-way through:** nothing.

**Ways the WP-74 order is stale (premises checked against the machine, `dev/CLAUDE.md` §0 rule 5):**
1. *"passlib/bcrypt incompatibility in the venv taking down every user-needing fixture"* — **not true on `9c406e8`.** WP-52 removed passlib from `ivgs-api/requirements.txt` and `app/core/security.py` calls `bcrypt` directly; no tracked source imports passlib (it is merely still installed in the venv). `ivgs-api` is **1870 passed, 0 failed** with every user fixture exercised. Nothing to pin.
2. *"`tests_system` hardcoding `localhost` against services published on 192.168.1.90"* — **already parameterised** by WP-52's `tests_system/service_urls.py` (`IVGS_TEST_HOST` default `192.168.1.90`, per-URL overrides, `E2E_BASE_URL` alias); the only `localhost` left is prose in `test_wp60_scripts.py:85`. Nothing to parameterise; default unchanged by construction.
3. *"`test_stage3.py` drifted from the provider-factory rewrite (WP-44 §8.4)"* — **repaired by WP-52** the day before WP-44's diagnosis was written down (`83c0ee2`, *"test_stage3 rewritten against the signature that exists"*). **8 passed.** Not an inherited failure.
4. *"the pytest `-p no:warnings` collection error (filterwarnings marker) if it is configuration"* — it is **not configuration**: the flag disables the plugin that registers the `filterwarnings` marker, and `ivgs-api/tests/test_wp57_service_token.py:131` uses that marker under `--strict-markers`. Measured: with the flag 0 items / 1 error; without it 5 collected. Registering the marker by hand would make `@pytest.mark.filterwarnings` silently inert whenever the plugin is off. Left as is; documented in the inventory §1.2 and in the memory of this session's harness notes.
5. *"the documented frontend command `npm test`"* — the only tracked file that documented it was the WP-70 v1 order (`dev/workpackages/WP-70-CONSUMER-FIXES-1_order_2026-09-05.md:33`), already bannered by WP-70; its line now reads `npm run test:logic` with the correction marked. `ivgs-frontend/package.json` was never wrong. No other tracked doc says `npm test` (`git grep`).
6. The test database was at **0055**, one migration past the tree (held 12j) — the reason WP-70's three full runs each carried one failure. Rebuilt at **0054** (inventory §1.3); that failure is gone.

**Learned, not written elsewhere:** the venv is Python **3.12.3** while every Dockerfile pins **3.12.8**; `pytest-asyncio` is 0.24.0 against a 0.25.2 pin; the dev packages `pytest-celery`, `pytest-mock`, `pytest-cov`, `pytest-timeout`, `factory-boy`, `freezegun` are declared and absent; lint tools are absent (measured in a throwaway venv). No baseline run needed any of them. Full drift list: inventory §1.1.

**Tree at close (§0 rule 5.5):** commits `9fac417` inventory, `8979e56` frontend T7/T2, `1a4ef5e` backup-worker inifile, `6e62f7c` CI, then the close-out (this report, board row, the corrected v1 order, the operator's orders file tracked as instructed). **HELD** — count in the push block, measured after `git fetch`. Dirty at close: nothing. Not mine: nothing left untracked (the orders file is tracked at the operator's instruction, unedited). Evidence in scratch, declared lost by name: `run.sh` (text in inventory §1.2), `base_api.txt`, `base_ivgs-workers.txt`, `base_ivgs-workers_env.txt`, `base_ivgs-scheduler.txt`, `base_ivgs-motion-renderer.txt`, `base_backup.txt`, `base_tests_system.txt`, `base_frontend.txt`, `lintenv/`, `stale_allowlist.txt`. Every figure is quoted from them in the inventory.

---

## 1. Environment record
Inventory §1. Summary: node-01, `/opt/ivgs/.venv` Python 3.12.3 (Dockerfiles pin 3.12.8); SQLAlchemy 2.0.35, Pydantic 2.10.4, pytest 8.3.4, bcrypt 4.2.1 — all at pin; passlib 1.7.4 installed, unreferenced; `pytest-asyncio` 0.24.0 ≠ 0.25.2 pin; lint tools absent. The venv was **not rebuilt** — every baseline run started. Test database rebuilt at 0054 (commands and resulting `alembic_version` in inventory §1.3).

## 2. Inventory summary

| Suite | passed | failed | skipped | errors | inherited (allowlisted) |
|---|---|---|---|---|---|
| `ivgs-api` | 1870 | 0 | 0 | 0 | **0** |
| `ivgs-workers` | 988 | 18 | 48 | 15 | **33** (14 fixture-drift P2.53, 15 `test_quality_gate` import, 2 non-UUID fixture ids, 1 sub-millisecond timing, **1 product defect**: `Stage6Input.scene_audio_refs` has no minimum) |
| `ivgs-scheduler` | 52 | 15 | 0 | 0 | **15** (7 `main` name collision P2.51, 8 `FakeRedis` drift P2.52) |
| `ivgs-motion-renderer` | 24 | 0 | 2 | 0 | **0** |
| `ivgs-backup-worker` | 4 | 0 | 0 | 0 | **0** |
| `tests_system` (node-01 live stack) | 193 | 12 | 15 | 30 | **42** (35 login-payload drift incl. 2 refresh + 1 e2e, 7 rate-limit aggravator, 1 missing register route, 2 fleet shape, 2 schedule body, 1 403-vs-401) — **not run on GitHub**; the static subset CI runs is 48 passed |
| frontend `test:logic` | 123 → **125** | 2 → **0** | — | — | **0** after the test-side fix |

Classes across Python: test drift 55, collection / test configuration 22, live rate-limit aggravator 7, product defect 1. Full per-test lists with first `E` lines: inventory §2.

## 3. Fixes made (one commit each, with the run that shows the cause gone)

| Commit | Class | What | Before → after |
|---|---|---|---|
| `8979e56` | test drift (frontend, test-side) | `ui-nav.test.mjs` T7 re-pinned to the four-member `MEDIA_TYPES` (`motion_graphics` since WP-IVGS-09c; API accepts it); T2 re-pinned to 12 `PROJECT_TABS` (Models since WP-66). The properties the tests exist for are still asserted. | `npm run test:logic`: 125 tests, 123 pass, 2 fail → **125 pass, 0 fail** |
| `1a4ef5e` | environment (test configuration) | `ivgs-backup-worker/pytest.ini` `pythonpath` was the absolute `/opt/ivgs/...`; now `. ..`, resolved relative to the inifile, so CI's checkout path works. | from the repo root via `-c`: **4 passed**; from `/tmp` with absolute paths: **4 passed** |

**Not fixed, by finding:** passlib (nothing to pin), `tests_system` hosts (already done), `-p no:warnings` (not configuration), `test_stage3.py` (passes). **Not fixed, by scope:** every other inherited row — they are test drift, test-configuration collisions or one product defect, none of them environment-class; each is on the allowlist with its cause.

## 4. CI (`6e62f7c`)

- **`test-python` enabled.** Postgres + Redis services; `alembic upgrade head` before the API suite (its conftest expects a migrated database named `*_test` and refuses others); `DATABASE_URL` **and** `TEST_DATABASE_URL`; RC-J8's three backup-worker variables; `requirements-dev.txt` for the worker tests' Pillow/numpy/onnxruntime. Six steps: api, workers, scheduler, motion-renderer, backup-worker (`-c` its inifile), the static `tests_system` subset WP-55 measured.
- **Inherited failures are a named allowlist**, `.github/ci/inherited_failures.txt` (90 entries with causes), enforced by `.github/scripts/inherited_failures_plugin.py`: every failing test is printed under **INHERITED** (with its cause) or **UNEXPECTED**, and any allowlisted test that now passes under **STALE**; the sections also go to the GitHub step summary. Exit 0 only when every failure is inherited and nothing is stale — **never counted as passes, the job is green only when every non-inherited test passes.** Proven on node-01 in all three directions (scheduler suite: 15 inherited → OK; one entry removed → UNEXPECTED 1, exit 1; a passing test added → STALE 1, exit 1).
- **`lint-python` enabled**, every step `continue-on-error` with its count written to the step summary. ⛔ **Inherited lint state, not a green lint job:** black 438 files, ruff 4644, mypy blocked at one duplicate module name, bandit 3/14/61. A wholesale formatting pass is out of this package's scope.
- **`lint-frontend`** gains a blocking `npm run test:logic` step.
- ⚠ **What was not verified:** a GitHub run. Node-01 cannot trigger one (the branch is held). The exit test §5's "CI run on the branch" is the operator's, after push. Risks a first run may surface: the worker suite's import-time defaults on a runner without `.env` (its conftest sets the `VLLM_*` defaults; nothing else was needed on node-01 in a plain shell), and install time for `onnxruntime`.

## 5. Reproducing the baseline on node-01
Inventory §1.2 (environment block) and §0 (per-suite commands). Through the plugin, from `/opt/ivgs`:
```
export PYTHONPATH=.github/scripts IVGS_INHERITED_ALLOWLIST=.github/ci/inherited_failures.txt
.venv/bin/python -m pytest -p inherited_failures_plugin ivgs-workers/tests -q       # INHERITED 33, VERDICT OK
.venv/bin/python -m pytest -p inherited_failures_plugin ivgs-scheduler/tests -q     # INHERITED 15, VERDICT OK
```

## 6. Decisions

- **D-1 — the product defect.** `Stage6Input.scene_audio_refs` accepts an empty list (`ivgs-workers/tasks/talking_head_task.py`); `test_talking_head_task.py::TestStage6Input::test_requires_at_least_one_audio_ref` pins the intended contract and is inherited. The frozen tree; a freeze ruling or the Temporal activity rewrite owns it.
- **D-2 — test-drift rows (55) and the two collisions (22)** are diagnosed and allowlisted, not fixed: outside "environment-class fixes only". The two collisions have a known one-file shape each (`ivgs-scheduler/pytest.ini` with its own `pythonpath`, as the backup-worker has; moving `FakeRedis` into a shared conftest). One package.
- **D-3 — `tests_system` on the live stack burns the login rate limit** (5/60 s) once the drifted fixtures fail, so 7 of its 42 rows are ordering-dependent 429s. Fixing the login payload (D-2 class) removes the aggravator too.
- **D-4 — venv drift**: Python 3.12.3 vs 3.12.8 and the `pytest-asyncio` pin. Rebuild is the operator's call; no run needed it.
- **D-5 — the allowlist is a contract**: an inherited test that starts passing fails CI until its line is removed. That is the xfail(strict=True) discipline the order asked for; say so to whoever fixes one.

## Push block (operator; §1 — Claude never pushes)

Measured at close, after `git fetch`: `git rev-list --count origin/main..HEAD` = **5** (inventory, two fixes, CI, close-out). The operator's block:

```
# node-01 (192.168.1.90), operator only
( git fetch origin && n=$(git rev-list --count origin/main..wp-74-ci-baseline) && if [ "$n" -eq 5 ]; then git push origin wp-74-ci-baseline; else echo "REFUSED: held count is $n, expected 5"; fi ) 2>&1 | tr -cd '\11\12\15\40-\176'
```
