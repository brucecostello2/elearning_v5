# WP-05-VISIBILITY-TIMEOUT - report

| | |
|---|---|
| **Package** | WP-05-VISIBILITY-TIMEOUT (Track S #6, Tier A) |
| **HEAD SHA at session start** | `9af5a485dfbd732bd9f0ce2519523f3fb267936f` |
| **HEAD at package start** | `6f6e166` (WP-04, committed and held earlier this session) |
| **Date** | 2026-08-23 |
| **Session** | Overnight unattended batch, Track S, sequential (package 2 of 5) |
| **Ledger** | **P0.1** - the only P0 - M2 |

---

## Pass 1 - findings

### Brief line references, re-verified at `9af5a48`

The brief was audited at `e613e844`. Checked every reference:

| Brief says | At `9af5a48` | Verdict |
|---|---|---|
| `config.py:214-215` = `broker_visibility_timeout` 3600 | `config.py:214-215` | **exact** |
| `talking_head_task.py:284` `time_limit=3900` | `talking_head_task.py:335` | **drifted 51 lines** |
| `video_generation_task.py:445` `time_limit=3900` | `video_generation_task.py:445` | **exact** |
| `celery_app.py:293` `task_acks_late = True` | `celery_app.py:288` | **drifted 5 lines** |

(WP-04 shifted `talking_head_task.py` further this session; it is now `:398-399`.)

### Evidence basis: VERIFIED LIVE

**Finding 1 - the value in force is the CODE DEFAULT, not an env value.**

    $ docker exec ivgs-celery-default env | grep -iE "VISIBILITY|BROKER|TIME_LIMIT"
    IVGS_CELERY_BROKER_URL=redis://redis:6379/0

`IVGS_BROKER_VISIBILITY_TIMEOUT` is absent from the running container. Also absent
from every tracked compose file:

    $ grep -n "IVGS_BROKER_VISIBILITY_TIMEOUT" ivgs-infra/*.yml ivgs-workers/docker-compose.workers.yml
    (no matches)

So the effective visibility timeout is `config.py:215`'s literal `3600`. The brief asks
to "confirm where the value is sourced (env vs default)": **default**. There is no env
value to raise - the fix has to move the default AND establish the canonical name in
the tracked compose blocks, per runbook s6.2.

**Finding 2 - `gpu_video` really is bound to two nodes in tracked config, but only
one consumer is online tonight.**

Tracked config:

    ivgs-infra/docker-compose.node02.yml:126   --queues=gpu_video   -n cogvideox-worker@node02
    ivgs-infra/docker-compose.node03.yml:127   --queues=gpu_video   -n cogvideox-worker@node03

Live, from node-01 via the broker:

    $ docker exec ivgs-celery-default celery -A celery_app inspect active_queues
    ->  default-worker@node01:      default, notifications, cleanup
    ->  composition-worker@node01:  composition
    ->  cogvideox-worker@node03:    gpu_video
    ->  image-worker@node04:        gpu_image, gpu_tts, gpu_talking_head
    ->  celery-worker@node02:       gpu_llm
    5 nodes online.

**`cogvideox-worker@node02` is not registered.** node-02 currently presents only its
`gpu_llm` worker. The brief's "the duplicate can execute concurrently on the other
node" is therefore correct as a property of the tracked configuration and NOT
currently reproducible on the running fleet - a redelivered `gpu_video` message today
would go back to node-03, which is already running it. Recorded as a discrepancy per
common rule 4; the fix is unaffected either way, because concurrent duplicate
execution is not the only failure mode (see Finding 4).

### Evidence basis: INFERRED FROM READING CODE

**Finding 3 - the invariant is violated by 300 seconds.**

    visibility_timeout                       3600   config.py:214-215
    longest hard time_limit                  3900   talking_head_task.py:399
                                             3900   video_generation_task.py:445

Every registered task's hard limit, gathered by grep over `ivgs-workers/tasks/` and
`celery_app.py`:

| Limit | Where |
|---|---|
| **3900** | `talking_head_task.py:399`, `video_generation_task.py:445` |
| 3600 | `periodic_tasks.py:341,409,476`; `config.py:228` (`task_hard_time_limit`, the app default at `celery_app.py:292`) |
| 2100 | `stage3_images.py:564` |
| 1860 | `stage8_final_render.py:347` |
| 1200 | `stage5_voiceover.py:497` |
| 960 | `stage7_prototype_draft.py:316` |
| 150 | `stage1_transcript.py:433`, `stage2_storyboard.py:454`, `celery_app.py:549` (base task) |

`max = 3900 > 3600`. The invariant fails on the two GPU-render tasks and on nothing
else.

**Finding 4 - `acks_late` is what makes it bite, and it is on.**

`celery_app.py:288-290`:

    app.conf.task_acks_late = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.task_reject_on_worker_lost = True

With `acks_late`, the ack is sent after the task body returns. Kombu's Redis transport
restores an unacked message to the queue once `visibility_timeout` elapses. So at
t=3600s a still-running 3900s render has its message put back. Between t=3600 and
t=3900 the message is claimable. That is true regardless of how many nodes serve the
queue - a single-consumer queue simply re-runs it on the same node after the first
finishes, wasting a full render instead of racing one. Two consumers make it a
concurrent race. Both are defects.

**Finding 5 - a second, unlinked copy of the same number in the API.**

`ivgs-api/app/services/celery_producer.py:29` hardcodes `"visibility_timeout": 3600`
inside a block whose own comment (`:26-27`) reads:

    # Must match the worker fleet's transport options so produced messages land in
    # the keyspace the workers actually consume (critically: global_keyprefix).

It is a literal, not a read of the shared env var. Raising the worker side alone would
break the invariant that comment asserts. In scope as "the config value" - it IS the
config value, in a second place.

### Proposed fix

1. `ivgs-workers/config.py:214-215` - default `3600` -> **`7200`** (ledger's
   recommendation), with the invariant written down next to it.
2. `ivgs-workers/celery_app.py` - add `check_visibility_timeout()`, a pure function
   taking `(visibility_timeout, task_time_limits)` and raising
   `VisibilityTimeoutError` naming both values and the offending task; plus
   `assert_visibility_timeout_covers_time_limits(app)` which gathers them from a live
   app. Wire to `signals.celeryd_after_setup`, which fires after the worker has
   imported its task modules and before it consumes anything - so the registry is
   populated and a violation aborts startup rather than being logged and ignored.
3. `ivgs-infra/docker-compose.node0{1,2,3,4}.yml` - add
   `IVGS_BROKER_VISIBILITY_TIMEOUT: "7200"` to every worker service's tracked
   `environment:` block. Runbook s6.2: canonical names live in tracked compose
   `environment:`, not hand-edited env files.
4. `ivgs-api/app/services/celery_producer.py` - read the same env var, same 7200
   default, instead of the literal.
5. Tests: the assertion fails at a low value and passes at the corrected one.

**Not proposed.** No broker change (M3 removes the mechanism). No `time_limit` change.
Nothing else in `celery_app.py`.

### Decisions requested

None. The brief names the value (7200), the ledger recommends it, and the arithmetic
is unambiguous. Proceeding.

---

## Pass 2 - what changed

### Touched files, complete list

| File | Change |
|---|---|
| `ivgs-workers/config.py` | `broker_visibility_timeout` default `3600` -> `7200`, invariant documented at `:214-227` |
| `ivgs-workers/celery_app.py` | `VisibilityTimeoutError`, `check_visibility_timeout()`, `collect_task_time_limits()`, `assert_visibility_timeout_covers_time_limits()`; `celeryd_after_setup` handler; `import sys` |
| `ivgs-api/app/services/celery_producer.py` | literal `3600` -> `_visibility_timeout`, read from the same env var, default 7200 |
| `ivgs-infra/docker-compose.node01.yml` | `IVGS_BROKER_VISIBILITY_TIMEOUT: "7200"` in 4 blocks: `fastapi-backend`, `celery-worker-default`, `celery-worker-composition`, `celery-beat` |
| `ivgs-infra/docker-compose.node02.yml` | 2 blocks: `cogvideox-worker`, `celery-node02` |
| `ivgs-infra/docker-compose.node03.yml` | 2 blocks: `cogvideox-worker-node03`, `celery-node03` |
| `ivgs-infra/docker-compose.node04.yml` | 1 block: `celery-node04` |
| `ivgs-workers/tests/test_wp05_visibility_timeout.py` | new, 16 tests |

All four compose files re-parsed with `yaml.safe_load` after editing - valid.

### THE FINDING THAT CHANGED THE FIX - a signal handler is not a gate

The first implementation raised `VisibilityTimeoutError` from the
`celeryd_after_setup` handler, which is the obvious way to fail fast. **It does not
work.** Measured on a probe worker, 2026-08-23:

    [2026-08-23 00:35:39,363: ERROR/MainProcess] Signal handler
      <function on_celeryd_after_setup ...> raised: VisibilityTimeoutError(...)
    Traceback (most recent call last):
      File ".../celery/utils/dispatch/signal.py", line 276, in send
        response = receiver(signal=self, sender=sender, **named)
    ...
    celery_app.VisibilityTimeoutError: broker visibility_timeout (100s) does not cover ...
     -------------- wp05-probe@throwaway v5.4.0 (opalescent)
    ...
    [2026-08-23 00:35:41,425: ERROR/MainProcess] consumer: Cannot connect to redis://...

The worker printed the whole refusal **and then started its consumer anyway.**
`celery/utils/dispatch/signal.py:275-281` wraps every receiver in
`except Exception`, logs it, appends it to the response list, and continues.

Had this shipped as first written it would have been a **new instance of the exact
WP-00 shape this queue tracks**: an error path that surfaces a message no caller
acts on. It is recorded here because the near-miss is the useful part - the version
that "obviously" fails fast is the version that does not.

**Cure:** the handler catches its own error, logs it as `critical` via structlog,
prints `FATAL: ...` to stderr (structlog is not reliably configured that early), and
raises `SystemExit(1)`. `SystemExit` derives from `BaseException`, so Celery's
`except Exception` does not catch it and the process actually stops.

### Verification - OBSERVED LIVE

Probe worker: the deployed image `ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics`
with this session's `ivgs-workers/` source mounted at `/app`, pointed at a **dead**
broker (`redis://127.0.0.1:16399/0`) and a dead result backend, consuming a throwaway
queue `wp05_probe`. Nothing touched production Redis, production queues, or any node
other than node-01.

    docker run --rm -v $STAGED:/app:ro \
      -e IVGS_CELERY_BROKER_URL='redis://127.0.0.1:16399/0' \
      -e IVGS_BROKER_VISIBILITY_TIMEOUT=<value> ... \
      ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics \
      celery -A celery_app worker --queues=wp05_probe -n wp05-probe@throwaway

| Run | `IVGS_BROKER_VISIBILITY_TIMEOUT` | Exit | Output | Reached consumer? |
|---|---|---|---|---|
| A | `100` | **rc=1** | 3 lines, `FATAL: ...` | **no** |
| B | `3600` - the exact pre-fix value | **rc=1** | 3 lines, `FATAL: ...`, 13 offending tasks named | **no** |
| C | `7200` - corrected | killed at timeout | 63 lines | **yes** - reached `consumer: Cannot connect to redis://...` |
| D | unset - code default | killed at timeout | 63 lines | **yes** - reached `consumer: Cannot connect to redis://...` |

Run B is the demonstration the exit gate asks for: **the assertion fails at the value
this system was actually running.** Its message:

    FATAL: broker visibility_timeout (3600s) does not cover the hard time_limit of
    13 task(s): tasks.video_generation_task.generate_video_clips=3900s,
    tasks.talking_head_task.render_talking_head=3900s, ... The longest is
    tasks.video_generation_task.generate_video_clips at 3900s. With task_acks_late
    the broker will redeliver a ... message at t=3600s while the original is still
    running, up to t=3900s. Raise IVGS_BROKER_VISIBILITY_TIMEOUT above 3900s with
    margin (7200 is the ledger P0.1 recommendation), or lower the task's time_limit.
    Refusing to start.

Both values named, as the brief requires. Runs C and D prove it passes at the
corrected value and at the new default - it is not simply always-fail.

Note the registered task names differ from the file names (`render_talking_head`,
`generate_video_clips`, `tasks.final_render_task.render_final`) - runbook s6.4,
"filenames are not task identities". The gate walks the registry, so it is immune to
that trap by construction.

**A second near-miss, also caught by running it.** The first version of
`collect_task_time_limits()` walked `app.tasks` directly. In the pytest process that
registry is **empty** - the loader has not imported the task modules - so the gate
passed vacuously. Two tests failed and exposed it. Fixed by calling
`app.loader.import_default_modules()` first, and by making
`assert_visibility_timeout_covers_time_limits()` raise when the registry comes back
empty rather than pass with nothing to check.

### Verification - unit tests

    $ .venv/bin/python -m pytest ivgs-workers/tests/test_wp05_visibility_timeout.py -q
    16 passed, 5 warnings in 0.33s

Covering: the exact pre-fix configuration is rejected; equal values are rejected
(`>=`, not `>`); every offender is named, non-offenders are not; unset/zero/negative
rejected; the corrected value passes; the shipped `WorkerConfig` default covers 3900;
the real app passes its own gate; the registry walk actually finds the 3900 s tasks
(guarding against a vacuous pass); no `celery.*` internals are checked; the signal is
connected; the wrapper raises; and the API producer's value now equals the worker's.

### Verification - NOT OBSERVED

- **The production workers were not restarted.** `docker exec ivgs-celery-default env`
  will not show `IVGS_BROKER_VISIBILITY_TIMEOUT` until the operator recreates the
  services against the amended compose files. The exit gate's `docker exec` clause is
  therefore **outstanding**, by design - no deploy in this session.
- The redelivery itself was not reproduced. Doing so needs a >3600 s render.

### Deploy step, left for the operator

Per runbook s3.1, derive the `-f` set from labels; do not guess. For node-01:

    docker compose -f ivgs-infra/docker-compose.node01.yml \
                   -f ivgs-infra/docker-compose.override.node01.yml \
                   -f ivgs-infra/docker-compose.monitoring.yml \
                   --env-file ivgs-infra/.env \
                   up -d --no-deps celery-worker-default celery-worker-composition celery-beat fastapi-backend

`--no-deps` is not optional (CLAUDE.md s6). Then:

    docker exec ivgs-celery-default env | grep IVGS_BROKER_VISIBILITY_TIMEOUT
    # expect: IVGS_BROKER_VISIBILITY_TIMEOUT=7200

node-02, node-03 and node-04 need the same recreate, run by the operator on those
hosts (common rule 5 bars this session from them). **Note:** the code default is now
7200, so a worker running the new image is correct even if the env var never lands.
The compose entries make the canonical name explicit per runbook s6.2; they are not
load-bearing.

### Discrepancies recorded (common rule 4)

1. The brief's `talking_head_task.py:284` is `:335` at `9af5a48`; `celery_app.py:293`
   is `:288`. `config.py:214-215` and `video_generation_task.py:445` are exact.
2. The brief's "gpu_video is consumed by node-02 AND node-03" is true of tracked
   compose and **false of the running fleet** - `cogvideox-worker@node02` is not
   registered with the broker tonight. The defect is unaffected; the concurrency
   aggravation is currently latent.
3. `dev/CLAUDE.md` s7 "Long tasks can execute twice" says
   `broker_visibility_timeout 3600 is below time_limit 3900`. Correct, and now stale
   in the good direction. Not edited - WP-08 owns the CLAUDE.md correction step and
   editing the same table twice in one session invites a conflict. Flagged for
   whoever lands next.

### Swallowed-failure register

No new instance appended. One near-instance was created and removed inside this
package before commit (the signal handler that logged and continued) - it never
existed at HEAD, so it is not a register entry. It is written up above because the
failure mode is instructive.

---

## Exit-gate verdict

| Gate clause | Status |
|---|---|
| Assertion FAILS when the invariant is violated, demonstrated with a low value | **MET** - live, runs A and B; rc=1, consumer never reached |
| Assertion PASSES at the corrected value | **MET** - live, runs C and D |
| Worker starts clean with the new config | **MET in substance** - the probe worker passes the gate and proceeds to its (deliberately dead) broker. Not observed on a production worker: that needs a deploy |
| `docker exec <worker> env` shows the value | **NOT MET** - requires the operator's recreate. Command given above |
| Note any deploy step needed and leave it for the operator | **MET** |

**Substantially MET.** The two clauses that are the actual gate - fails when violated,
passes when corrected - were demonstrated live, at the exact value the fleet was
running. The remaining clause is a deploy, which is the operator's by rule.

Commit-and-HOLD. Nothing pushed, nothing deployed.
