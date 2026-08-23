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
| 2 | `ivgs-workers/tasks/pipeline_orchestrator_v2.py:869` | Redis errors → `0` | **FIXED 2026-08-23, pending deploy** — WP-06-MEDIA-JOIN, with evidence. See below. |
| 3 | `ivgs-workers/utils/error_handler.py:395` | Checkpoint write failure → `False` | **FIXED 2026-08-23, pending deploy** — WP-07-CHECKPOINTS, with evidence. See below. |
| 4 | `ivgs-workers/tasks/*.py` call sites of `acquire_gpu_reservation` | GPU reservation failure → warning | Open — **scope-blocked** |
| 5 | `ivgs-workers/tasks/pipeline_orchestrator.py:620` | Manufactures a success | Open |
| 6 | `ivgs-workers/tasks/pipeline_orchestrator.py` — 5 sites in 3 scheduled tasks + `dispatch_pipeline` | Celery task returns `{'status':'error'}` | Open — **added 2026-08-14 by WP-00-DETECTOR** |
| 7 | `ivgs-workers/tasks/pipeline_orchestrator.py:601, :612` | Two more scheduled stubs manufacturing success | Open — **added 2026-08-14 by WP-00-DETECTOR** |
| 8 | `ivgs-workers/utils/error_handler.py:313, :383` | DLQ routing and job-status write failures → `False` | Open — **added 2026-08-14 by WP-00-DETECTOR** |
| 9 | `shared/redis_client.py` — 8 methods | Every Redis error → `None` / `False` | Open — **added 2026-08-14 by WP-00-DETECTOR** |
| 10 | `shared/seaweedfs_client.py` — 4 methods, 8 sites | Every asset-store error → `None` / `False` | Open — **added 2026-08-14 by WP-00-DETECTOR** |
| 11 | `ivgs-workers/utils/gpu_utils.py:230, :274` | `release_gpu_reservation` / `send_heartbeat` → `False` | Open — **added 2026-08-14 by WP-00-DETECTOR** |
| 16 | `.github/workflows/compliance-check.yml`, `cd-deploy.yml` — `runs-on: self-hosted` with no runner | A gate that **queues** instead of running or failing | **CLOSED 2026-08-22** — the gate observably executed and failed loudly. Evidence below. **Variant instance, see note** |

**A detector now exists.** `scripts/swallow_detector.py` (WP-00-DETECTOR, 2026-08-14)
makes this class machine-detectable. Instances 6–11 below were found by running it
rather than by review. It is **not** wired into CI — see that package's report.

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

### 2. `_decrement_media_task_count` returns 0 on Redis error — **FIXED 2026-08-23, pending deploy**

> **Fixed by WP-06-MEDIA-JOIN**, report
> `dev/workpackages/reports/WP-06-MEDIA-JOIN-report_2026-08-23.md`, commit on `main`
> the same day. Sites were `pipeline_orchestrator_v2.py:974-984` at `9af5a48` (the
> `:869` below is the `e1f4c58` line number).
>
> **What changed.** The function no longer returns an int at all. It returns
> `(outcome, remaining)` where `outcome` is one of `decremented` / `duplicate` /
> `unknown`, so "Redis is down" and "all media reported" are no longer the same
> value. On the unknown path `_handle_media_generation_completion` raises
> `MediaJoinUnknownError` and `handle_stage_completion` retries; it cannot advance.
> `_store_media_task_count` now raises `MediaJoinStoreError` instead of logging and
> returning `None`.
>
> **Evidence the failure now surfaces** (the register's bar for closing an entry -
> not "the code looks right"). Against a real Redis, with `config.redis_url` pointed
> at a port with nothing listening, so the connection genuinely fails:
>
> - `test_connection_failure_reports_unknown_not_complete` - outcome is `unknown`,
>   never `decremented`.
> - `test_the_caller_raises_rather_than_dispatching_stage_4` - the caller raises and
>   `celery_app.send_task` is asserted **not called**. Under the old code this same
>   input dispatched Stage 4.
> - `test_pre_fix_arithmetic_would_have_read_it_as_complete` - runs the old
>   expression `max(0, r.decr(key))` on a missing key, asserts it yields `0`, then
>   runs the new function on the same state and asserts `unknown`. The defect and
>   its fix are both executable in one test.
>
> **Not yet deployed.** `ivgs-celery-default` runs `v5.5.4-metrics`; the fix has
> never executed in production. Same disposition as entry 1, and for the same
> reason - the code is in the image, or it is not.
>
> 19 tests, all passing. Two sibling helpers in the same file
> (`_record_media_failure`, `_get_media_failure_count`) still return `0` on error by
> deliberate choice - they only make `failed_count` under-report and cannot advance
> the pipeline - but they now log at `error` with `unknown=True` rather than at
> `warning`. **Those two remain open as a lower-severity variant of this entry.**



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

### 3. `save_checkpoint` returns `False`, unchecked at every call site — **FIXED 2026-08-23, pending deploy**

> **Fixed by WP-07-CHECKPOINTS**, report
> `dev/workpackages/reports/WP-07-CHECKPOINTS-report_2026-08-23.md`, commit on `main`
> the same day. The site is `utils/error_handler.py:395-448` at `9af5a48`.
>
> **This is the register's most consequential entry, and this is why.** The failure
> being swallowed was not intermittent. `save_checkpoint` POSTs to
> `/api/v1/jobs/{id}/checkpoints`, and **that route did not exist**. Measured live
> 2026-08-23 against the running `ivgs-fastapi` (`v5.5.3-arch1`):
>
>     POST /api/v1/jobs/.../checkpoints  ->  405 Method Not Allowed   allow: GET
>     select count(*) from pipeline_checkpoints  ->  0
>
> So **every checkpoint write this system has ever attempted failed**, each one
> logged at warning and returned `False` to a caller that did not look. Not one row
> was ever written. Checkpoint resume has never had anything to resume from, and
> `dev/CLAUDE.md` s7's "Checkpoint resume — does not exist" is the consequence.
>
> **Also corrected:** the register, the WP-07 brief and `dev/CLAUDE.md` s7 all say
> **five** call sites. There are **fifteen** - `stage1_transcript.py:493,:625,:678`,
> `stage2_storyboard.py:511,:688`, `stage3_images.py:683,:734`,
> `stage5_voiceover.py:606,:655`, `stage7_prototype_draft.py:447,:561`,
> `stage8_final_render.py:706`, `video_generation_task.py:512`,
> `talking_head_task.py:926`, `pipeline_orchestrator_v2.py:625`. None checked.
>
> **What changed.** `save_checkpoint` raises `CheckpointWriteError` instead of
> returning `False`. All fifteen sites surface the failure without one being edited
> - the stage task bodies are out of WP-07's scope. A `required: bool = True`
> parameter restores the old behaviour for a caller that explicitly asks; a test
> asserts no call site does.
>
> **Evidence the failure now surfaces.** 20 tests in
> `ivgs-workers/tests/test_wp07_save_checkpoint_surfaces.py`, including
> `test_405_is_named_because_that_is_what_production_returned`, which drives the
> exact live condition and asserts the raised message names the status, the job and
> the stage. Eight HTTP status codes and a transport error are parameterised. The
> success path is pinned unchanged, and the payload shape is asserted against the
> route that now accepts it.
>
> **The route itself now exists**, and was proven end to end against a real Postgres
> carrying the full migration chain (19 tests,
> `ivgs-api/tests/test_wp07_checkpoint_write.py`) - see the WP-07 report.
>
> **Not yet deployed.** Both halves need a build: `ivgs-fastapi` runs
> `v5.5.3-arch1` and `ivgs-celery-default` runs `v5.5.4-metrics`. Until then the
> POST still 405s and this entry is fixed in the tree, not in the system.
>
> **Related, still open:** `error_handler.py:313, :383` (entry 8) - DLQ routing and
> job-status writes - are the same shape in the same file and were NOT touched here;
> WP-07's scope is the checkpoint path.

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

### 6. Orchestrator Celery tasks return failure as a value — OPEN

*Added 2026-08-14 by WP-00-DETECTOR (rule SF005), verified at `16ea217`.*

This is **instance 1's exact shape**, unfixed, in the orchestrator. Celery records
SUCCESS for every one of these:

```
ivgs-workers/tasks/pipeline_orchestrator.py:485   supervise_worker_heartbeats  {"status":"error","reason":"fleet_fetch_failed"}
                                           :531   supervise_worker_heartbeats  {"status":"error","error":str(e)}
                                           :564   process_dead_letter_queue    {"status":"error","reason":"dlq_fetch_failed"}
                                           :590   process_dead_letter_queue    {"status":"error","error":str(e)}
                                           :653   collect_gpu_fleet_metrics    {"status":"error","reason":f"HTTP {code}"}
                                           :655   collect_gpu_fleet_metrics    {"status":"error","error":str(e)}
                                           :157   dispatch_pipeline            {"status":"failed", ...}
ivgs-workers/tasks/pipeline_orchestrator_v2.py:195  dispatch_pipeline          {"status":"failed", ...}
                                              :996  media_join_watchdog        {"status":"error","reason":"redis_unavailable"}
```

The first six are on **beat schedules**. `supervise_worker_heartbeats` and
`process_dead_letter_queue` are the two tasks whose entire job is to notice that
something else is broken; when they themselves break, they report SUCCESS.

**Partial mitigation, verified:** both `dispatch_pipeline` sites call
`update_job_status(job_id, "failed", ...)` before returning, so the database row is
marked failed even though the Celery task state is SUCCESS. The scheduled six have no
such mitigation.

**Verified by reading and by detector run; not reproduced at runtime.**

### 7. Two further scheduled stubs manufacture success — OPEN

*Added 2026-08-14 by WP-00-DETECTOR (rule SF006), verified at `16ea217`.*

```
ivgs-workers/tasks/pipeline_orchestrator.py:601  run_orphan_cleanup
    return {"status": "ok", "message": "Orphan cleanup — stub (Phase 8)"}
                                           :612  run_retention_migration
    return {"status": "ok", "message": "Retention migration — stub (Phase 8)"}
```

Same shape as instance 5, same file, found by the same rule. Instance 5 was recorded
individually; these two sat beside it unrecorded. All three are on beat schedules
(`celery_app.py`), so retention migration and orphan cleanup have also reported green
daily while doing nothing.

### 8. DLQ routing and job-status writes fail silently — OPEN

*Added 2026-08-14 by WP-00-DETECTOR (rules SF001/SF002), verified at `16ea217`.*

```
ivgs-workers/utils/error_handler.py:313, :322   route_to_dead_letter_queue -> False
                                   :383, :388   update_job_status          -> False
```

Same file and same shape as instance 3. `route_to_dead_letter_queue` returning `False`
means a task that exhausted its retries was **not** recorded in the DLQ, and nothing
learns of it — the DLQ is the operator's last audit surface for lost work.
`update_job_status` returning `False` means the job row keeps its previous state; a
failed job can therefore remain displayed as running.

Call sites were **not** audited for whether they check the return. That audit is the
first task if this instance is picked up.

### 9. `RedisClient` converts every Redis error into a value — OPEN

*Added 2026-08-14 by WP-00-DETECTOR (rule SF002), verified at `16ea217`.*

Eight of the nine methods in `shared/redis_client.py` catch `Exception`, log, and
return a sentinel:

```
:39  get       -> None      :50  set       -> False    :58  delete  -> False
:66  exists    -> False     :74  incr      -> None     :82  expire  -> False
:97  get_json  -> None      :107 set_json  -> False
```

`get`/`get_json` returning `None` is indistinguishable from a cache miss; `incr`
returning `None` is indistinguishable from nothing. This is the same ambiguity as
instance 2, one layer down and repository-wide.

`ping()` (`:119`) is **excluded** — it is a health predicate whose contract is a bool,
and it is allowlisted in `scripts/swallow_allowlist.json` with that justification.

### 10. `SeaweedFSClient` converts every asset-store error into a value — OPEN

*Added 2026-08-14 by WP-00-DETECTOR (rules SF001/SF002), verified at `16ea217`.*

```
shared/seaweedfs_client.py:68, :82, :92   upload_file      -> None
                          :124            upload_to_filer  -> False
                          :153, :162      download_file    -> None
                          :182, :193      delete_file      -> False
```

An `upload_file` returning `None` means the binary asset was never stored. This is the
asset store for every generated image, audio file and render.

`check_health` (`:215`) is **excluded** and allowlisted, same reasoning as `ping`.

### 11. `release_gpu_reservation` and `send_heartbeat` return `False` — OPEN

*Added 2026-08-14 by WP-00-DETECTOR, verified at `16ea217`.*

```
ivgs-workers/utils/gpu_utils.py:230, :237   release_gpu_reservation -> False
                               :274         send_heartbeat          -> False
```

The companion to instance 4. `acquire_gpu_reservation` raises; **`release_` does not** —
it returns `False`. A failed release leaks the reservation until its 5-minute TTL
expires, and no caller learns of it. Four call sites discard the return value entirely
(`celery_app.py:607`, `talking_head_task.py:543`, `:699`, `video_generation_task.py:540`),
detected by rule SF004.

This also bears on the contradiction recorded in CLAUDE.md §7 about
`release_gpu_reservation` raising `TypeError`. **Still untested** — the detector reports
shape, not runtime behaviour, and resolves nothing about that contradiction.

### 12. Stage 6 cannot distinguish a fresh render from a dedup hit - OPEN

*Added 2026-08-15 during WP-02-ORCH6 check-5 verification, verified live.*

Stage 6 uploaded a 50 MB render and reported:

```
status: success   asset_id: b45b19ce-c12a-459f-bdf0-1dcae7625a4e
seaweedfs_path: /ivgs/talking-heads/3814f845-.../talking_head_en.mp4
```

That asset row was created **2026-06-07**. The upload was content-hash
deduplicated (`ivgs-api/app/services/asset_service.py:136-160`, spec S10.4):
`reference_count` went 1 -> 2, `last_accessed_at` was stamped, and **no bytes were
written**. Verified on the volume server - fid `5,5b66d602e3` still reports
`Last-Modified: Sun, 07 Jun 2026 17:56:18 GMT`.

**The dedup is correct.** The defect is that nothing downstream can tell the two
cases apart. `Stage6Output` has no `was_deduplicated` field, so a render that
produced new footage and a render whose output was discarded as redundant emit an
identical success payload. An operator reading the stage output, the job row, or
the asset id cannot answer "did this job actually render anything?".

Note the *dead* per-scene file carried `SceneTalkingHeadResult.was_deduplicated`
(`stage6_talking_head.py:124`, deleted by WP-02). The signal existed in the
architecture AD-03 Pillar 2 retired and was not carried into the live one.

**Scope/action:** add `was_deduplicated: bool` to `Stage6Output`, set it from the
upload response (the API already returns the pre-existing row, so compare the
returned `created_at` or have the endpoint report it), and log it. Same treatment
for any other stage whose upload can dedup.

### 13. `_update_job_celery_task_id` writes nothing and nobody notices - OPEN

*Added 2026-08-15 during WP-02 check-6b, verified live.*

`pipeline_orchestrator_v2.py:206` calls
`_update_job_celery_task_id(job_id, result.id, config)` immediately after dispatching
a stage. On the check-6b run - with a **valid** `job_id`, so this is not the mangled-id
artefact - the row shows:

```
id            a3d2d3fc-97aa-4920-ad89-ca1cf4e06bf6
status        running        <- update_job_status DID land
celery_task_id (null)        <- _update_job_celery_task_id did NOT
started_at    (null)
```

Both helpers write through the same Pipeline API with the same service token in the
same task, moments apart. One took effect and the other did not, and the dispatch
reported success either way. Whatever the cause - missing route, wrong verb, rejected
payload - it is invisible: the caller does not check, and the orchestrator logs
`pipeline_stage_dispatched` regardless.

**Consequence.** `render_jobs.celery_task_id` is the only link from a job row back to
the Celery task that ran it. Without it there is no way to correlate a job with its
worker logs, its retries, or its failure - exactly the correlation an operator needs
during an incident. `started_at` being null compounds it: job duration is
unmeasurable.

**Verified live; root cause NOT diagnosed.** The API-side behaviour was not traced,
and this may share a cause with ledger P2.0a (node-04 worker traffic not appearing in
`ivgs-fastapi`'s access log). Do not assume they are the same bug without evidence.

**Scope/action:** trace the call against the API route table (as P1.2 did for
checkpoints), then make the failure surface - assert on the return, or raise. Check
`update_job_status`'s sibling calls for the same gap.

### 14. Stage 7 swallows an ffmpeg failure and reports `task_succeeded` - OPEN

*Added 2026-08-15 during WP-03 Option D, verified live. Owned by WP-27-MANIFEST-BUILDER.*

Job `7980c0b9-8d9e-4d3b-955e-f2b97bf137dd`, 2026-08-15 11:25:18, on
`ivgs-celery-composition`:

```
{"cmd_head": "ffmpeg -y -i /tmp/ivgs_stage7_.../bg_8e25826c-....bin.png ...",
 "returncode": 1, "stderr": "..."}
{"error": "FFmpeg failed (rc=1): ...", "scene_count": 6}
{"event": "task_succeeded", "task_name": "tasks.prototype_draft_task.assemble_prototype_draft"}
```

The non-zero ffmpeg return is logged, and the task then returns normally and Celery
records SUCCESS. **No draft was produced.** Anything downstream - the orchestrator,
the job row, an operator reading task state - sees a successful Stage 7.

This is the register's defining shape and it is also **a detector case**: the rule that
should catch it is a stage task that logs an error-level event and then returns a
success-shaped result rather than raising. `scripts/swallow_detector.py` does not
currently model "logged an error, then returned normally without raising" at task
scope - SF005 only fires on a `status` key with a failure literal, and this task's
return carries no such key. Worth a new rule.

**Scope/action (WP-27):** raise on `rc != 0` instead of returning. Then re-check
whether a detector rule can express this shape.

### 15. Stage-4 manifest builder binds every scene asset as a background layer - OPEN

*Added 2026-08-15 during WP-03 Option D, verified live. Owned by WP-27-MANIFEST-BUILDER.*

Recorded here at the operator's instruction. **This is not itself a swallowed failure**
- it is a correctness defect. It belongs in this register because instance 14 is what
concealed it: without Stage 7 reporting a false success, this would have surfaced the
moment it occurred.

| Manifest | layers per scene | contents |
|---|---|---|
| June, job `79b90f48` | **1** | background |
| 2026-08-15, job `7980c0b9` | **4** | 2 images **and 2 audio**, all `layer_type: background` |

Scene 0's layer list, all `0-10000 ms`, all typed `background`:

```
d83c6ac7  audio   <- first, so ffmpeg receives a WAV as the background input
be4453e8  audio
7de1b630  image
ca6d7f83  image
```

The builder applies **no `asset_type` filter and no deduplication**. It appeared
correct in June only because there was one asset per scene then; AD-03 S11.5 records
duplicate audio assets accumulating from re-runs since. The duplicates exposed a filter
that never existed.

Compounding, and independent: most scenes on the reference project have **0 images and
2 audio**, so for those there is no valid background asset to select at all.

**Scope/action (WP-27):** filter background layers to image/video asset types; dedupe
to the latest per scene. The zero-image scenes are a separate media-generation gap.

---

## Proposed detector

> **Status 2026-08-14: partly delivered.** WP-00-DETECTOR built a **static** check
> (`scripts/swallow_detector.py`) instead of the runtime handler proposed below,
> because the brief asked for a CI gate and because the runtime handler cannot see
> instances 2, 3 and 4 — they are plain function returns, not task returns. The
> static check catches all of instances 2–11.
>
> The runtime `task_postrun` handler described here is **still worth building** and
> remains open. It is complementary, not superseded: it observes what actually ran,
> which no static rule can. Neither tool has been enabled in CI or deployed.

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

### 16. A CI gate that queues instead of failing - FIXED (compliance) / DISABLED (CD)

**Added 2026-08-22.** Recorded here on the operator's instruction, and marked a **variant**
rather than a plain instance, so the register does not drift into "anything that hides a
failure".

**How it fits.** The register's stated pattern is a *return value* swallow: code detects a
failure, converts it to `{'status':'failed'}` / `0` / `False`, and returns normally. This is
not that. **No code swallows anything** - the job never starts. But the consequence is the
register's consequence exactly, and instance 5 already stretches the definition the same way
(a stub that *manufactures* a success rather than swallowing a real failure). The operator's
formulation is the right one: **a gate that queues instead of failing is success manufactured
by silence.**

**How it differs, stated so the boundary stays legible.** Instances 1-15 are all in-process
and all detectable by `scripts/swallow_detector.py`. This one is in CI orchestration, is
invisible to that detector, and its "swallow" is the *absence* of an executor rather than the
mishandling of a result. A detector for this class would have to compare every `runs-on:`
label against the set of live registered runners - a different tool.

**Evidence.**

```
compliance-check.yml:23   runs-on: [self-hosted, linux, x64, ivgs-infra]
cd-deploy.yml:37,:69,:110 runs-on: [self-hosted, linux, x64, ivgs-infra]

ivgs-github-runner   started  2026-05-26T22:41:36.358Z
                     finished 2026-05-26T22:41:36.503Z   (0.145 s, exit 0, no logs)
                     restarts 0   systemd unit: none
```

**Consequence, measured.** **87 days** in which spec section F.2's "fail build on any
violation" gated nothing, while GitHub showed no failure - only a growing queue nobody read.
All five commits of 2026-08-22 landed inside that window. Discovered only because run **#341**
was noticed sitting queued; no tooling reported it.

**Why it is the purest form of the class.** Every other instance at least *runs* and returns
a wrong answer. This one produces no signal at all, and the absence of a red mark was read as
a green one - by me, in this session, when I reported "CI green" without checking which jobs
that green covered.

**Disposition: CLOSED 2026-08-22.** Compliance gate moved to `runs-on: ubuntu-latest`; CD
Deploy disabled (`workflow_dispatch` only, `if: false` on all three jobs); runner revival
deferred under **P1.4k** with two binding conditions.

**The closing evidence, which is the point of this register's closing rule.** The next push
produced a Compliance Audit run that **executed and failed RED**. That is exactly the
observation required: the gate no longer queues, it runs, and when it finds something it says
so loudly. A red run is the proof the instance is fixed - a green one would have been weaker
evidence, since green is also what silence looks like from a distance.

Note that the failure was a **false positive** - the rule fired on the prohibition comments
documenting the policy, fixed separately under **P1.4l**. That does not weaken the closure
here. This instance was about a gate that could not report; it now reports. Whether it reports
*accurately* is a different defect with its own ledger entry.

**Open sibling, not fixed here.** Nothing checks that a workflow's `runs-on` labels match a
live runner. If a future workflow targets `self-hosted` again, it will queue silently exactly
as this one did, and nothing will say so.

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
