# WP-06-MEDIA-JOIN - report

| | |
|---|---|
| **Package** | WP-06-MEDIA-JOIN (Track S #7, Tier A) |
| **HEAD SHA at session start** | `9af5a485dfbd732bd9f0ce2519523f3fb267936f` |
| **HEAD at package start** | `e1f582f` (WP-05, committed and held earlier this session) |
| **Date** | 2026-08-23 |
| **Session** | Overnight unattended batch, Track S, sequential (package 3 of 5) |
| **Ledger** | **P1.1** - M2 |

---

## Pass 1 - findings

### Brief line references, re-verified at `9af5a48`

| Brief says | At `9af5a48` | Verdict |
|---|---|---|
| `pipeline_orchestrator_v2.py:869-880` `_decrement_media_task_count` | `:974-984` | **drifted ~105 lines** |
| `pipeline_orchestrator_v2.py:856-866` `_store_media_task_count` | `:961-971` | **drifted ~105 lines** |
| caller at `:672` treats `remaining <= 0` as complete | `:680` and `:697` | **drifted 8 lines** |
| `stage3_images.py:736-741` callback before ack | `:757-761` | **drifted ~21 lines** |
| `video_generation_task.py:574-580` callback before ack | `:576-580` | **near-exact** |

All five sites exist and behave as the brief describes. The arithmetic of the defect
is unchanged.

### The brief is wrong about the join's granularity - and it matters

The brief prescribes a **per-`(job_id, scene_id)`** SETNX guard. **The join does not
count scenes.** `dispatch_media_generation` (`:461-513`) increments
`total_media_tasks` once per *media stage dispatched* - image, video, animation - and
stores that count at `:516`:

    if image_scenes:      ... total_media_tasks += 1     # :471
    if video_scenes:      ... total_media_tasks += 1     # :491
    if animation_scenes:  ... total_media_tasks += 1     # :512
    _store_media_task_count(job_id, total_media_tasks, config)   # :516

The counter's maximum value is **3**, not the scene count. Each media stage renders
all its scenes and then sends exactly one `handle_stage_completion`
(`stage3_images.py:757`, `video_generation_task.py:576`) carrying a whole-stage
output. There is no per-scene callback anywhere, and `stage_output` carries no
`scene_id` to key on.

The correct idempotency key is **`(job_id, completed_stage)`**. Common rule 4: the
repo is right, the brief is a defect. Recorded, and the fix uses the real key.

### Evidence basis: INFERRED FROM READING CODE

**Finding 1 - unknown reads as complete (the headline defect).**

`:974-984`:

    def _decrement_media_task_count(job_id, config) -> int:
        try:
            r = redis.Redis.from_url(config.redis_url)
            remaining = r.decr(f"ivgs:media_tasks:{job_id}")
            return max(0, remaining)
        except Exception as e:
            logger.warning("redis_decrement_media_count_failed", error=str(e))
            return 0                      # <-- "I don't know" spelled "0"

and the caller at `:680` / `:697`:

    remaining = _decrement_media_task_count(job_id, config)
    ...
    if remaining <= 0:
        # All media generation complete -> dispatch Stage 4

One transient Redis error - a failover, a timeout, a dropped connection - and Stage 4
is dispatched over whatever footage happens to exist. The `max(0, remaining)` is
doing double duty: it clamps a legitimately negative counter AND it is the value the
exception path returns, so the caller cannot tell the two apart.

**Finding 2 - the missing-key case reads as complete too.**

`redis.decr` on a key that does not exist creates it at `-1` and returns `-1`.
`max(0, -1) == 0`. So if `_store_media_task_count` never wrote the key, the very
first media stage to report collapses the join and advances.

**Finding 3 - and `_store_media_task_count` can fail to write it silently.**

`:961-971`:

    def _store_media_task_count(job_id, count, config) -> None:
        try:
            r.set(f"ivgs:media_tasks:{job_id}", count, ex=MEDIA_JOIN_TTL_SECONDS)
            r.delete(f"ivgs:media_failures:{job_id}")
        except Exception as e:
            logger.warning("redis_store_media_count_failed", error=str(e))

Returns `None` either way. `dispatch_media_generation` calls it at `:516` and does
not check. Findings 2 and 3 compose: the store fails, nothing notices, and the first
of three media stages to finish advances the pipeline on one third of the footage.

**Finding 4 - no idempotency; the callback fires before the ack.**

`stage3_images.py:757-761` and `video_generation_task.py:576-580` both
`celery_app.send_task(...handle_stage_completion...)` and *then* `return output_dict`.
The ack happens after the return, because `task_acks_late = True`
(`celery_app.py:288`) and `task_reject_on_worker_lost = True` (`:290`). A worker
death in that window requeues the media task, it re-executes, and it sends a second
completion for the same `(job_id, stage)`. The counter decrements twice for one
stage. With 3 stages expected, two double-decrements advance Stage 4 with a stage
still running.

**Finding 5 - two more "unknown = 0" helpers, lower severity.**

`_record_media_failure` (`:988-998`) returns `0` on error and `_get_media_failure_count`
(`:1001-1011`) returns `0` on error. Neither gates advancement - they only make
`failed_count` under-report, so a partial-advance is logged as clean. Same shape,
different blast radius. In scope as "the join helpers"; fixed by surfacing, not by
raising, because raising here would strand a job over a cosmetic counter.

**Finding 6 - watchdog interaction, must not be broken.**

`media_join_watchdog` (`:1072-1180`) claims a stalled job by **deleting** the counter
key (`:1123-1127`) and advancing with `failed_count`. After a claim, a genuinely late
callback finds no key. Under the current code that is `decr` -> `-1` -> `0` ->
**Stage 4 dispatched a second time**. Under the fix it is "unknown" -> retry -> DLQ
after `max_retries=3`. Louder and correct; a behaviour change worth naming.

**Finding 7 - partial-advance must survive (commit `35d9226`).**

`:271` deliberately routes FAILED media stages into the join rather than fail-fasting,
and `:697-704` advances with `failed_count`. `_handle_media_generation_completion`'s
docstring (`:668-672`) says so explicitly. The fix must not convert this to fail-fast.
Preserved: the guard and the unknown-detection sit around the counter, not around the
success/failure decision.

### Proposed fix

**One Lua script, evaluated server-side, doing the guard and the decrement atomically.**
The two-step alternative (SETNX, then DECR, then undo the SETNX if the DECR fails) has
a hole: if the undo also fails, the guard is stuck set, the retry looks like a
duplicate, and the join stalls. Atomic means a Redis failure leaves *nothing* done and
the retry is clean.

    if redis.call('SETNX', KEYS[2], '1') == 0 then return {1, 0} end   -- duplicate
    redis.call('EXPIRE', KEYS[2], ARGV[1])
    if redis.call('EXISTS', KEYS[1]) == 0 then return {2, 0} end       -- unknown
    return {0, redis.call('DECR', KEYS[1])}                            -- decremented

`KEYS[1]` = `ivgs:media_tasks:{job_id}`, `KEYS[2]` =
`ivgs:media_join_seen:{job_id}:{stage}`.

1. `_decrement_media_task_count(job_id, stage, config)` returns a small result object
   carrying one of `DECREMENTED` / `DUPLICATE` / `UNKNOWN`, never a bare int the
   caller can misread as completion. On a Redis exception: `UNKNOWN`.
2. `_handle_media_generation_completion` acts on the outcome:
   - `DECREMENTED` - as today, including partial-advance.
   - `DUPLICATE` - log and return `action: "duplicate_ignored"`. No decrement, no
     dispatch.
   - `UNKNOWN` - raise `MediaJoinUnknownError` so `handle_stage_completion`
     (`bind=True`, `max_retries=3`, `:233-239`) retries. Never advances.
3. `_store_media_task_count` raises `MediaJoinStoreError` on failure; the caller at
   `:516` lets it propagate so `dispatch_media_generation` retries rather than arming
   a join that was never armed. It also clears any stale `media_join_seen:*` guards
   for the job, so a re-dispatch re-arms cleanly.
4. `_record_media_failure` / `_get_media_failure_count` keep returning an int but log
   at `error` with an explicit `unknown=True`, and the advance log says the failure
   count is unreliable rather than reporting a confident 0.

**Out, and left alone:** the stage task bodies beyond nothing at all (the callback
sites are NOT edited - the guard is entirely orchestrator-side, keyed on data the
callback already sends, so no stage body changes); the watchdog; any broker or config
change.

### Decisions requested

| # | Decision |
|---|---|
| D-1 | The brief's `(job_id, scene_id)` key does not exist in the code. Implemented as `(job_id, completed_stage)`, the real granularity. Confirm. |
| D-2 | A callback arriving after the watchdog has claimed the job now retries and lands in the DLQ instead of silently re-dispatching Stage 4. Confirm the louder behaviour is wanted. |

Neither blocks: both are recorded, implemented the way the repo's own structure
dictates, and reversible.

---

## Pass 2 - what changed

### Touched files, complete list

| File | Change |
|---|---|
| `ivgs-workers/tasks/pipeline_orchestrator_v2.py` | `MediaJoinStoreError`, `MediaJoinUnknownError`, the `JOIN_*` outcomes, `_MEDIA_JOIN_REPORT_LUA`, `_media_join_seen_key()`; `_store_media_task_count` now raises; `_decrement_media_task_count` returns `(outcome, remaining)`; the caller handles all three outcomes; a retry hook in `handle_stage_completion`; `unknown=True` logging on the two failure-count helpers |
| `ivgs-workers/tests/test_wp06_media_join.py` | new, 19 tests |
| `dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | register entry 2 closed with evidence (common rule 7) |

**No stage task body was edited.** The brief allows "the minimal callback-side
guard", but none was needed: the guard keys on `(job_id, completed_stage)`, and
`completed_stage` is already in the payload every callback sends. The whole fix is
orchestrator-side. `stage3_images.py` and `video_generation_task.py` are untouched.

### The change

One Lua script does the guard and the decrement in a single server-side step:

    if redis.call('SETNX', KEYS[2], '1') == 0 then return {1, 0} end   -- duplicate
    redis.call('EXPIRE', KEYS[2], ARGV[1])
    if redis.call('EXISTS', KEYS[1]) == 0 then return {2, 0} end       -- unknown
    return {0, redis.call('DECR', KEYS[1])}                            -- decremented

The two-step alternative (SETNX, DECR, undo the SETNX on failure) was rejected: if
the undo also fails the guard is stuck set, the retry reads as a duplicate, and the
join stalls permanently. Atomic means a Redis failure leaves nothing done, so the
retry is clean.

The caller now branches on the outcome, not on a number:

- `decremented` - as before, including partial-advance.
- `duplicate` - log, return `action: "duplicate_ignored"`, dispatch nothing.
- `unknown` - raise `MediaJoinUnknownError`; `handle_stage_completion` retries
  (`bind=True`, `max_retries=3`); after exhaustion it goes to the DLQ.

### Verification - OBSERVED

    $ docker run -d --rm --name wp06-redis -p 127.0.0.1:16380:6379 redis:7.4
    $ IVGS_TEST_REDIS_URL=redis://127.0.0.1:16380/0 \
        .venv/bin/python -m pytest ivgs-workers/tests/test_wp06_media_join.py -q
    19 passed, 5 warnings in 0.45s

Against a **real** Redis, not a mock - the fix is a server-side Lua script and a mock
cannot prove one is atomic or even syntactically valid. The "unknown" cases use a
genuinely unreachable Redis (`redis://127.0.0.1:16399/0`), not a patched exception.

**Exit-gate clause 1 - a simulated Redis error does NOT advance the pipeline:**
`test_connection_failure_reports_unknown_not_complete`,
`test_the_caller_raises_rather_than_dispatching_stage_4` (asserts `send_task` was
**not called**), `test_a_failed_media_stage_also_reports_unknown_not_complete`.

**Exit-gate clause 2 - a duplicate callback decrements exactly once:**
`test_duplicate_report_for_same_stage_decrements_once` - three deliveries of one
stage's completion against a counter of 3 leave it at 2, and outcomes are
`decremented, duplicate, duplicate`. `test_duplicate_does_not_dispatch_stage_4`
asserts `send_task.call_count == 1` across a genuine report and its duplicate.

**Exit-gate clause 3 - the missing-key case cannot read as complete:**
`test_unarmed_counter_reports_unknown`, `test_watchdog_claim_leaves_unknown_not_complete`.

**Tests fail against the pre-fix code - demonstrated executably, not narrated.**
Two tests carry the old expression verbatim and assert the defect:

- `test_pre_fix_arithmetic_would_have_read_it_as_complete` - runs
  `max(0, r.decr(key))` on a missing key, asserts it yields `0` ("all complete"),
  then runs the new function on the same state and asserts `unknown`.
- `test_pre_fix_would_have_double_decremented` - two `DECR`s for one stage against a
  counter of 3 leave it at 1, i.e. one stage consumed two of three slots.

**Partial-advance preserved (commit `35d9226`):**
`test_failed_stage_still_decrements_and_advances` (a wholly failed stage still
dispatches Stage 4 with `failed_count: 1`), `test_partial_failure_advances_with_a_failed_count`,
`test_all_success_advances_with_zero_failures`. Not converted to fail-fast.

### INCIDENT - these tests published to the production broker on their first run

Recorded in full because it happened and because the report is the record.

**What happened.** The first draft of the dispatch-path tests called
`_handle_media_generation_completion` for real. That function ends in
`celery_app.send_task(...)`. `WorkerConfig.celery_broker_url` defaults to
`redis://node-01:6379/0`; `node-01` resolves from `/etc/hosts`
(`127.0.1.1` and `192.168.1.90`) and `ivgs-redis` publishes `6379/tcp ->
192.168.1.90:6379`. The send succeeded. **Four genuine
`tasks.stage4_manifest.build_composition_manifest` messages were published to the
live broker** with fabricated job ids (`wp06-<uuid>`).

The running `ivgs-celery-default` consumed all four, called
`GET /api/v1/jobs/wp06-.../manifest`, got HTTP 500 (no such job), and entered its
retry loop at 30 s intervals.

**Containment**, 2026-08-23 00:45:

    docker exec ivgs-celery-default python -c "
    from celery_app import celery_app
    celery_app.control.revoke([...4 ids...], terminate=True)"

    [00:45:21,933] Discarding revoked task: ...build_composition_manifest[1ff4eeaa-...]
    [00:45:22,006] Discarding revoked task: ...build_composition_manifest[4f21f913-...]
    [00:45:22,019] Discarding revoked task: ...build_composition_manifest[19cc5408-...]
    [00:45:22,032] Discarding revoked task: ...build_composition_manifest[fa1ae943-...]

**State after containment, verified:**

    llen ivgs_workers_default   -> 0
    hlen ivgs_workers_unacked   -> 0
    select count(*) from render_jobs         where id::text like 'wp06%'  -> 0
    select count(*) from pipeline_checkpoints where job_id::text like 'wp06%' -> 0

No rows were created; no real job was touched; every task failed on lookup before
reaching any write. The blast radius was ~90 seconds of failed retries by the
node-01 default worker. Nothing on node-02/03/04 was involved -
`build_composition_manifest` runs on the `default` queue.

**Cure, in the tests.** An `autouse` fixture now patches
`celery_app.send_task` for **every** test in the module, so no test in it can reach
a broker whatever it calls. The fixture docstring records why. It also made the
tests stronger: `send_task.call_count` is now asserted, which a live send cannot do.

**Re-run after the fix, verified clean:** 19 passed;
`llen ivgs_workers_default = 0`, `hlen ivgs_workers_unacked = 0`, and no new
`build_composition_manifest` lines in the worker log (the only four in the window
are the historical discards above).

**The general lesson, for whoever writes the next orchestrator test:** anything that
calls an orchestrator helper transitively calls `celery_app.send_task`, and the
worker default broker URL resolves from a sandbox on node-01. Patch `send_task`
before calling any `_handle_*` helper.

### Verification - NOT OBSERVED

- No end-to-end run. A real duplicate delivery needs a worker to die between
  `send_task` and the ack; that was not staged.
- The retry path through `handle_stage_completion` was exercised at the helper
  level (`MediaJoinUnknownError` raised) but not through a live Celery retry, which
  would need a worker running the changed code - a deploy.
- Nothing deployed. `ivgs-celery-default` still runs `v5.5.4-metrics`.

### Discrepancies recorded (common rule 4)

1. Every brief line reference drifted (~105 lines for the helpers, 8 for the caller,
   ~21 for the stage3 callback). All five sites verified present.
2. **The brief's `(job_id, scene_id)` key does not exist.** The join counts media
   *stages*, max 3, incremented at `:471/:491/:512`. No callback carries a
   `scene_id`. Implemented as `(job_id, completed_stage)` - decision D-1.
3. Behaviour change worth naming: a callback arriving after the watchdog has claimed
   the job now retries and lands in the DLQ. The old code decremented a missing key
   to `-1`, clamped to `0`, and **dispatched Stage 4 a second time** - decision D-2.

### Swallowed-failure register

Register entry **2 CLOSED with evidence** (common rule 7), citing the three tests
that demonstrate the failure now surfaces. Two sibling helpers in the same file
(`_record_media_failure`, `_get_media_failure_count`) are explicitly left returning
`0` on error - they cannot advance the pipeline, only under-report `failed_count` -
and are recorded as a lower-severity variant that remains open.

No new instance was found in this package's file set.

---

## Exit-gate verdict

| Gate clause | Status |
|---|---|
| A simulated Redis error does NOT advance the pipeline; join reports unknown and retries | **MET** - 3 tests, real unreachable Redis, `send_task` asserted not called |
| A duplicate completion callback for the same key decrements exactly once | **MET** - 2 tests, real Redis, counter observed at 2 after three deliveries |
| The missing-key case cannot read as "complete" | **MET** - 2 tests, including the watchdog-claim path |
| Tests fail against the pre-fix code (demonstrate) | **MET** - the pre-fix expression is executed inside 2 tests and asserted to produce the defect |

**MET.** All four clauses demonstrated against a real Redis.

Commit-and-HOLD. Nothing pushed, nothing deployed.

---

## Operator rulings, 2026-08-23 — applied

| # | Ruling | Applied as |
|---|---|---|
| **D-1** | **CONFIRMED — `(job_id, completed_stage)` is correct; the brief was wrong.** | No code change; the shipped guard already keys on `(job_id, completed_stage)`. Ledger **P1.1** amended to correct its own scope line, which specified `(job_id, scene_id)`, with the evidence: `dispatch_media_generation` increments once per media **stage** at `:471`/`:491`/`:512`, max 3, and no callback carries a `scene_id`. |
| **D-2** | **CONFIRMED — the louder watchdog behaviour is wanted.** | No code change. Ledger **P1.1** now records the before/after explicitly: a post-claim callback used to decrement a missing key to `-1`, clamp to `0`, and **dispatch Stage 4 a second time**; it now reports `unknown`, retries, and lands in the DLQ. |

Ledger **P1.1** status moved from OPEN to **FIXED 2026-08-23, pending deploy**.
Swallow-register entry 2 already carries the same disposition.

**No code changed under these rulings** — both confirmed what shipped. `git diff` against
`148125d` for this package's files is empty.
