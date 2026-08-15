# WP-00-DETECTOR — Make the swallowed-failure class detectable

| | |
|---|---|
| **Ledger** | Agent plan §3; register `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` |
| **Tier** | A (self-proving) · **Track S #2** |
| **Report** | `reports/WP-00-DETECTOR-report_<YYYY-MM-DD>.md` |
| **Next** | WP-02-ORCH6 (HARD STOP at pass 1) |

## Objective

Every major defect found 2026-08-14 shared one shape: *swallow the failure, return a
sentinel nobody checks*. Build a static check that fails CI when that shape appears,
so the class becomes machine-detectable instead of operator-review-detectable.

## Known instances (verify current state first — some were fixed 2026-08-14)

| Location | Shape | State at audit |
|---|---|---|
| `ivgs-backup-worker/tasks/backup_tasks.py` | returned `{'status':'failed'}`, Celery logged success | **FIXED** — now raises `BackupTaskError`. Use as the must-PASS case |
| `pipeline_orchestrator_v2.py:869-880,893` | `_decrement_media_task_count` returns `0` on error | OPEN — must FAIL |
| `utils/error_handler.py:435-450` | `save_checkpoint` returns `False`, unchecked at all call sites | OPEN — must FAIL |
| `pipeline_orchestrator.py:620-623` | `run_backup_verification` stub returns `{'status':'ok'}` having done nothing | OPEN — must FAIL |
| `acquire_gpu_reservation` call sites, e.g. `stage3_images.py:631` | `except Exception: log.warning(...)`, continue — the swallow is at the 6 call sites, NOT in `gpu_utils.py` (it raises at `:202`) | OPEN — must FAIL |

## Method

Start narrow: detect the known shapes (sentinel-return error paths; broad
`except Exception` + log + continue around a named call list; dict-returning Celery
tasks whose `status` key can be a failure value). Do NOT attempt general dataflow
analysis. A curated allowlist for legitimate cases is acceptable if every entry
carries a justification comment. Wire it as a script under `scripts/` or `dev/`
runnable standalone, plus a CI/pre-commit hook entry (propose the hook; do not
enable anything that would block the operator without his approval).

## Scope

**In:** the new check script, its config/allowlist, hook proposal, register update.
**Out:** fixing the flagged instances (WP-06/07/08 own those); any stage-task or
orchestrator edits.

## Exit gate (the proof — demonstrate all three in the report)

1. The check FAILS on the four open instances above, citing file:line.
2. The check PASSES on the fixed `backup_tasks.py`.
3. Revert one backup fix hunk in a scratch worktree (`git worktree add`, then discard)
   and show the check catches the regression. Do not touch the main tree for this.
