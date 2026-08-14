# WP-00 — Swallowed-failure pattern ledger

**Date opened:** 2026-08-14
**Node:** node-01 (192.168.1.90)
**Repo:** brucecostello2/elearning_v5 @ `e1f4c58`
**Status:** LEDGER — open. No code proposed here.

No WP-00 report existed under `/home/dev/workpackages/reports/`, so this file
opens it. It is a register of one recurring defect class, not a work plan.
Instances are added as they are found; each carries its own evidence and its own
disposition.

**The pattern:** a function or task detects a failure, converts it into an
ordinary return value — `{'status': 'failed'}`, `0`, `False`, a logged warning —
and returns normally. No caller checks. The system reports success.

**Why it is tracked separately:** every instance is individually defensible
("don't let bookkeeping break the pipeline"), and collectively they removed the
ability to tell a working system from a broken one. WP-BACKUP-REPORTING is the
proof: three independent notification paths were silent at once, two of them
because of this pattern.

---

## Register

| # | Site | Swallows | Disposition |
|---|---|---|---|
| 1 | `ivgs-backup-worker/tasks/backup_tasks.py` — 4 tasks, 10 return sites | Script exit codes | **Fixed**, pending deploy — WP-BACKUP-REPORTING |
| 2 | `ivgs-workers/tasks/pipeline_orchestrator_v2.py:869` | Redis errors → `0` | Open |
| 3 | `ivgs-workers/utils/error_handler.py:395` | Checkpoint write failure → `False` | Open |
| 4 | `ivgs-workers/tasks/*.py` call sites of `acquire_gpu_reservation` | GPU reservation failure → warning | Open — **scope-blocked** |
| 5 | `ivgs-workers/tasks/pipeline_orchestrator.py:620` | Manufactures a success | Open |

---

### 1. Backup tasks return failure as a value — FIXED (pending deploy)

| Task | Return site at `e1f4c58` |
|---|---|
| `run_full_database_backup` | `backup_tasks.py:305` |
| `run_asset_backup` | `backup_tasks.py:340` |
| `run_config_backup` | `backup_tasks.py:375` |
| `run_verification` | `backup_tasks.py:435, 450, 466, 476, 488, 499, 515` |
| DB-write failures | `backup_tasks.py:262, 280` (`status: "error"`) |

**Verified live.** Worker log, 2026-08-14 19:20:01:

```
Task tasks.backup_tasks.run_verification[a65c7a99…] succeeded in 2.051688333000129s:
  {'backup_id': 'eb55a9f0…', 'status': 'failed', 'returncode': 1, 'stderr_tail': 'gpg: …'}
```

Celery state SUCCESS for a failed verification.

**Consequence, measured:** contributed to a 75-day database backup gap going
unnoticed. See `WP-BACKUP-REPORTING_2026-08-14.md` §3.1.

**Disposition:** fixed by `BackupTaskError` + raise on every failure path. **Not
yet deployed** — `ivgs-backup-worker/tasks/` is baked into the image, and
`grep -c BackupTaskError /app/tasks/backup_tasks.py` in the running container
returns 0. The fix has never executed.

---

### 2. `_decrement_media_task_count` returns 0 on Redis error — OPEN

```
ivgs-workers/tasks/pipeline_orchestrator_v2.py:869   def _decrement_media_task_count(
                                            :878       except Exception as e:
                                            :879           logger.warning("redis_decrement_media_count_failed", …)
                                            :880           return 0
                                            :891       except Exception as e:
                                            :892           logger.warning("redis_record_media_failure_failed", …)
                                            :893           return 0
```

Two swallow sites in one function. `0` is also the legitimate "no tasks
remaining" value, so a Redis outage is indistinguishable from a completed fan-in.
Given the name, `0` plausibly triggers a join/completion path.

**Inferred from reading code.** Not reproduced; the downstream consequence of a
spurious `0` was not traced. That tracing is the first task if this instance is
picked up.

---

### 3. `save_checkpoint` returns `False`, unchecked at every call site — OPEN

```
ivgs-workers/utils/error_handler.py:395   def save_checkpoint(
                                   :442       return False
                                   :443     except Exception as e:
                                   :450       return False
```

Call sites, all discarding the return value:

```
ivgs-workers/tasks/stage5_voiceover.py:584, :633
ivgs-workers/tasks/pipeline_orchestrator_v2.py:582
ivgs-workers/tasks/stage6_talking_head.py:621, :673
```

Every one is a bare `save_checkpoint(...)` statement — no assignment, no branch.

**Verified by grep, not by execution.** Compounding context from CLAUDE.md §7:
checkpoint *resume* does not exist — no `POST /jobs/{id}/checkpoints` route was
built. So a silently unwritten checkpoint has no read path that would reveal it.
Failure and success are observationally identical today.

---

### 4. GPU reservation failure swallowed at the call sites — OPEN, SCOPE-BLOCKED

**Correction to the task brief.** The brief states that
`acquire_gpu_reservation` "logs a warning and continues". It does not. At
`e1f4c58` the function raises:

```
ivgs-workers/utils/gpu_utils.py:202-207
    except (GpuReservationError,):
        raise
    except Exception as e:
        raise GpuReservationError(f"GPU reservation failed: {e}", job_id=job_id) from e
```

The swallow is at the **call sites**:

```
ivgs-workers/tasks/stage3_images.py:631-632
    except Exception as gpu_err:
        log.warning("gpu_reservation_failed", error=str(gpu_err))
```

Execution continues with no reservation. Other call sites:
`stage1_transcript.py:511`, `stage2_storyboard.py:537`, `stage5_voiceover.py:542`,
`talking_head_task.py:358, :545`.

This matters for remediation: the fix is not in `gpu_utils.py`. It is in six call
sites, and **five of them are inside the eight stage task bodies that CLAUDE.md
§3 places out of bounds during the orchestration migration** — wrapping allowed,
editing not.

Related, unverified: CLAUDE.md §7 records that the reservation registry is empty
(`total_nodes: 0`) and that `release_gpu_reservation` raises `TypeError` at all
three call sites, while `OUTSTANDING_WORK.md:293` records that the same
signature-drift `TypeError` does **not** reproduce on the deployed image. Those
two claims contradict each other and neither was tested here.

---

### 5. Scheduled verification manufactures a success — OPEN

```
ivgs-workers/tasks/pipeline_orchestrator.py:620-623
    def run_backup_verification() -> Dict[str, Any]:
        """Daily backup verification. Stub for Phase 5."""
        logger.info("backup_verification_started")
        return {"status": "ok", "message": "Backup verification — stub (Phase 10)"}
```

Scheduled daily at 05:00 — `ivgs-workers/celery_app.py:202-205`.

**Verified by reading; the schedule entry is verified live** (the beat schedule
was read from the running configuration).

This is the worst instance in the register, and it is not the same shape as the
others. Instances 1–4 convert a real failure into a false success. This one
reports success for work that was never attempted, on a daily schedule, under a
name that asserts the one thing nobody was checking. Any dashboard or review
keyed on "did verification run" has shown green every day.

Recorded at the operator's instruction, from `WP-BACKUP-SCHEDULE_2026-08-14.md`
§4.

---

## Proposed detector

Kept out of WP-BACKUP-REPORTING deliberately; recorded here as the register's own
first work item.

A `task_postrun` signal handler registered on each Celery app, raising or logging
at ERROR when a task returns a mapping whose `status` is not a success value.

Properties:

- Catches instances 1 and 5 immediately, and any future task-level instance.
- Requires **no** call-site audit and **no** edits to the eight stage task
  bodies — it observes return values from outside, which is the wrapping that
  CLAUDE.md §3 permits.
- Roughly fifteen lines per `celery_app.py`.

It does **not** catch instances 2, 3 and 4, which are plain function returns
rather than task returns. Those need either type-level treatment (a `Result` type
that cannot be discarded) or making the functions raise and fixing the call
sites — the latter blocked by §3 for instance 4.

Suggested order if this register is worked: the detector first (cheap, broad,
unblocked), then instance 3 (`save_checkpoint`, since checkpoint resume is being
built out anyway), then instance 2, then instance 4 once the orchestration
migration lifts the scope freeze.

---

## Evidence discipline

Per CLAUDE.md §12:

- **Verified live:** instance 1's Celery SUCCESS-on-failure (worker log);
  instance 1's non-deployment (`grep` in the running container); instance 5's
  daily schedule (running beat configuration).
- **Verified by reading only:** instances 2, 3, 4, and instance 5's stub body.
  No swallow other than instance 1's was reproduced at runtime.
- **Not tested:** the downstream consequence of any swallowed value. No instance
  in this register has had its blast radius measured. Doing so is part of taking
  each one on, not a precondition for recording it.

---

*Ledger open. Add instances as found; do not close one without observed evidence
that the failure now surfaces.*
