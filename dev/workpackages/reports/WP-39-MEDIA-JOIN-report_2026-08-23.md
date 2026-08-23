# WP-39-MEDIA-JOIN — the animation stage could not report, and the watchdog ran in silence

| | |
|---|---|
| **Date** | 2026-08-23 |
| **HEAD at start** | `7cdfbf4` (1 held commit — the handoff stub this file replaces) |
| **Subject** | job `bd99fe37-0621-40da-aa30-e058cc776c23`, project `c12fa967-f989-4ed4-8e20-3ea62cb92e8f` "double digit multiplication" |
| **Ships** | `ivgs-workers` as **`v5.6.6-mediajoin`** — node-01 (default / composition / beat) + node-02 / node-03 / node-04 |
| **Untouched** | `ivgs-api` and `ivgs-frontend` stay on `v5.6.5-reviewgate`; `ivgs-scheduler` stays pinned at `v5.0.0-20260522`; every engine container (vLLM, CogVideoX, LatentSync, ComfyUI, Coqui, Kokoro, WhisperX) untouched |
| **ACTION REQUIRED** | **Job `bd99fe37` has not moved yet.** Run the one block in **§3.2.1** (or confirm the watchdog beat you to it at 18:44:54Z). Then the push block in §9. |

> This file **replaces** the handoff stub committed as `7cdfbf4`. That stub was written by a
> session that never received this brief; nothing in it was wrong, it simply had no work in it.

---

## 0. The one-line answer

**The node-03 Redis drop cost nothing.** The report that was lost belonged to the **animation**
stage, and it was lost three minutes *earlier*, to the join's own duplicate guard — because
animation and image share one Celery task and that task stamped both runs with the same stage
label. The watchdog has been running correctly every five minutes the whole time; it just never
said so.

Since the deploy it does say so, and it has been naming `animation_generation` on this job every
sweep since 17:49. **The job itself has not moved yet** — the watchdog's 2-hour deadline lands at
18:44:54Z, after this package's last check. One paste-ready block in §3.2.1 moves it now.

---

## 1. Task 1 — root cause of the lost join

### 1.1 What the join actually is

`dispatch_media_generation` (`tasks/pipeline_orchestrator_v2.py`) groups the storyboard's scenes
by `media_type`, sends **one task per media STAGE** (not per scene), and arms a single Redis
integer, `ivgs:media_tasks:{job_id}`, with the number of stages dispatched. Each media task, on
completion, sends `handle_stage_completion`, which reports against the counter through a Lua
script guarded by a per-report idempotency key, `ivgs:media_join_seen:{job_id}:{stage}` (WP-06).
When the counter reaches 0 the orchestrator dispatches Stage 4.

The join is **Redis-only**. It never reads `pipeline_checkpoints`, `render_jobs` or `assets`. So
the `video_generation` row still reading `pending` is not what the join is looking at — see
ledger (c) — and the join could not have been "waiting on the database".

### 1.2 The storyboard, and what was dispatched

```
project c12fa967 storyboard_scenes: 18 rows
  image       4   (scene_index 0, 15, 16, 17)
  animation  12   (scene_index 2-7, 9-14)
  video_clip  2   (scene_index 1, 8)
```

`media_generation_dispatched`, 16:44:20.122Z, verbatim from the node-01 default worker:

```json
{"image_scenes": 4, "video_scenes": 2, "animation_scenes": 12, "total_tasks": 3,
 "event": "media_generation_dispatched"}
```

with three task ids:

| stage | celery_task_id | scenes | task name | queue |
|---|---|---|---|---|
| `image_generation` | `985fd7f3` | 4 | `tasks.stage3_images.generate_scene_images_task` | `gpu_image` |
| `video_generation` | `c7c6a168` | 2 | `tasks.video_generation_task.generate_video_clips` | `gpu_video` |
| `animation_generation` | `602dd6dd` | 12 | **`tasks.stage3_images.generate_scene_images_task`** | `gpu_image` |

Three tasks. **Two of them are the same task**: `STAGE_TASK_MAP` maps both `image_generation`
and `animation_generation` to `tasks.stage3_images.generate_scene_images_task`.

### 1.3 The collision, in the log

```
16:45:27.761  image_generation  media_stage_completed                 remaining_tasks 2
16:46:55.529  image_generation  media_stage_duplicate_report_ignored  "already counted; join not advanced"
16:49:43.158  video_generation  media_stage_completed                 remaining_tasks 1
```

The middle line is **task `602dd6dd` — the 12-scene animation run — finishing**. It is not a
duplicate of anything. `Stage3Output.stage` defaulted to a hardcoded `PipelineStage.IMAGE_GENERATION`
and the task never knew which stage it had been dispatched as, so its completion carried
`stage: "image_generation"`, hit the already-set `ivgs:media_join_seen:{job}:image_generation`
key, and was correctly-by-its-own-rules dropped.

### 1.4 The same fact, from the result backend

`result_backend` is PostgreSQL with `result_extended`, so the three task returns survived both
the incident and the worker recreation. Decoded from `celery_taskmeta`:

```
985fd7f3  stage: image_generation  status: success  scenes:  4  ok:  4  failed: 0
602dd6dd  stage: image_generation  status: success  scenes: 12  ok: 12  failed: 0   <-- the animation run
c7c6a168  stage: video_generation  status: success  scenes:  2  ok:  2  failed: 0
```

Two rows say `image_generation`. That is the defect, in the database, in its own words.

### 1.5 Redis, as found

```
ivgs:media_tasks:bd99fe37…                       = 1        (armed at 3)
ivgs:media_join_seen:bd99fe37…:image_generation  = 1
ivgs:media_join_seen:bd99fe37…:video_generation  = 1
ivgs:media_join_seen:bd99fe37…:animation_generation  ABSENT
```

The counter is stuck at 1 and no fourth report exists to move it. The pipeline was not "waiting
for video"; it was waiting for a report the system had made structurally impossible to send.

### 1.6 Why the Redis drop is not the cause

node-03's worker did hit `redis.exceptions.ConnectionError "Connection closed by server"` at
16:49:43 and reconnect. But the video completion was **already delivered and processed** at
16:49:43.158 — the `media_stage_completed` line above, with `remaining_tasks: 1`, is that
report landing. Had it been lost, the counter would read 2, not 1. The timestamps coincide
because both happened at the second the video task ended; the causation does not.

### 1.7 The fix

`join_stage` travels with each dispatch and comes back on the completion:

- `dispatch_media_generation` is now one plan loop over
  `((image_generation, gpu_image, …), (video_generation, gpu_video, …), (animation_generation, gpu_image, …))`
  instead of three near-identical blocks, and stamps `join_stage` into every task input.
- `Stage3Input.join_stage` / `VideoGenerationInput.join_stage` accept it (without the model field
  pydantic silently drops the key — there is a test for exactly that).
- `Stage3Output.stage` and `VideoGenerationOutput.stage` are set from it, defaulting to the old
  hardcoded value, so a caller that does not set it behaves exactly as before.
- Stage 3's **checkpoint** now keys on `join_stage` too. `pipeline_checkpoints` upserts on
  `(job_id, stage_name)`, so the animation run had been overwriting the image run's row: 18
  scenes of work, one checkpoint.
- `dispatch_media_generation` records the labels it dispatched in the join context
  (`expected_stages`), which is what lets the watchdog **name** a missing stage rather than only
  count it.

Two runs of one task now report under two labels. The WP-06 redelivery guard is unchanged and
still fires on a genuine redelivery of the same label — tested.

---

## 2. Task 2 — the watchdog

### 2.1 It was never broken. It was inaudible.

`media_join_watchdog` is routed to `default` (both by its own `queue="default"` and by the
`tasks.pipeline_orchestrator_v2.*` route), beat sends it every 5 minutes at priority 4, and
`default-worker@node01` consumes `default`. All three were already true. It is registered
(`celery inspect registered`), it is received, and it succeeds in ~60 ms. From the log, before
any change:

```
16:47:20  Task …media_join_watchdog[4ebd0567] received
16:47:20  Task …media_join_watchdog[4ebd0567] succeeded in 0.0515s:
          {'status': 'ok', 'swept': 1, 'advanced': 0, 'failed': 0, 'skipped_recent': 1}
```

Every five minutes, all afternoon. The earlier finding of "no execution in any worker log" came
from grepping for the task's **structlog events** — of which, on a sweep that finds nothing, it
emitted **none**. The only trace was Celery's own generic `succeeded in …` line.

`swept: 1, skipped_recent: 1` is the watchdog looking straight at job `bd99fe37`, correctly
deciding it was inside the 2-hour deadline, and saying nothing about it.

### 2.2 Swallow register — instance 22

Written into the standing register at
`dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` (CLAUDE.md §12), as
**instance 22**, and closed there on live evidence.

> **22 · `media_join_watchdog` reported nothing on a sweep that found nothing.** Nothing returns
> a wrong value here; the swallow is one level up — the mechanism's correctness was
> **unobservable**. "The recovery never ran" and "the recovery ran and found nothing" produced
> byte-identical logs, so a job could sit half-joined for the full two-hour deadline with no line
> in any log naming it. That is not a hypothetical: this investigation opened on exactly that
> false premise and lost its first hour to it. **CLOSED** on the observation in §2.4 — a live
> sweep, on the deployed image, naming a real stranded join and the exact stage responsible.

### 2.3 What changed

| line | when | carries |
|---|---|---|
| `media_join_watchdog_sweep` (info) | **every run, always** | `swept`, `advanced`, `failed`, `skipped_recent`, `deadline_seconds` |
| `media_join_watchdog_join_outstanding` (info) | every sweep, per outstanding join | `job_id`, `remaining_tasks`, `age_seconds`, `deadline_seconds`, `outstanding_stages` |
| `media_join_watchdog_stranded_job` (warning) | on a claim | + `age_seconds`, `outstanding_stages` |
| `media_join_watchdog_advanced_with_failures` (warning) | on a recovery | + `outstanding_stages` |
| `media_join_watchdog_redis_unavailable` | raised **warning → error** | it is the recovery path; unreachable Redis means no recovery |

`_outstanding_media_stages()` computes the naming: `expected_stages` from the join context minus
the stages that left a `media_join_seen` key. It returns **`None` for "could not tell"** and an
**empty list for "everything reported"** — deliberately not the same value, in a package named
after exactly that confusion.

### 2.4 Observed live, on the real job

First sweep after deploy — the job named for the first time in its life:

```json
17:44:54  {"event": "media_join_watchdog_join_outstanding",
           "job_id": "bd99fe37-0621-40da-aa30-e058cc776c23", "remaining_tasks": 1,
           "age_seconds": 3635, "deadline_seconds": 7200, "outstanding_stages": null}
17:44:54  {"event": "media_join_watchdog_sweep", "swept": 1, "advanced": 0,
           "failed": 0, "skipped_recent": 1, "deadline_seconds": 7200}
```

`outstanding_stages: null` is correct and is the new semantics working: this job's join context
was written by the *old* image, which had no `expected_stages`, so the watchdog says "could not
tell" rather than "nothing missing". After annotating that context with what the 16:44:20
dispatch log records it sent (§3.1), the next sweep names the defect outright:

```json
17:49:54  {"event": "media_join_watchdog_join_outstanding",
           "job_id": "bd99fe37-0621-40da-aa30-e058cc776c23", "remaining_tasks": 1,
           "age_seconds": 3935, "outstanding_stages": ["animation_generation"]}
```

**`["animation_generation"]`** — the watchdog, unprompted, pointing at the stage §1 identified.

The recovery path itself was exercised end-to-end **inside the built image** before deploy,
against a scratch Redis DB (db 9, flushed before and after; production is db 0):

```
EMPTY SWEEP   -> ['media_join_watchdog_sweep']
OUTSTANDING   -> {"job_id": "gate-wp39", "remaining_tasks": 1,
                  "outstanding_stages": ["animation_generation"]}
RECOVERY      -> {'status': 'ok', 'swept': 1, 'advanced': 1, 'failed': 0, 'skipped_recent': 0}
DISPATCHED    -> ['tasks.stage4_manifest.build_composition_manifest']
STRANDED LINE -> [{"event": "media_join_watchdog_stranded_job", "job_id": "gate-wp39",
                   "outstanding_stages": ["animation_generation"], "vanished_tasks": 1},
                  {"event": "media_join_watchdog_advanced_with_failures", …}]
```

---

## 3. Task 3 — recovering job `bd99fe37`

### 3.1 What was done to the live system

Exactly one thing, and it is an annotation, not a state change: the job's **join context** —
written before `expected_stages` existed — was rewritten to carry the three stage labels that
the 16:44:20 `media_generation_dispatched` log line records were actually sent, preserving the
key's remaining TTL. This changes only what the watchdog can *name*; no counter, no seen-key, no
database row, no project state was touched.

```
ivgs:media_join_ctx:bd99fe37… = {"job_id":"bd99fe37-…","project_id":"c12fa967-…",
  "project_name":"double digit multiplication","language_code":"en-US",
  "expected_stages":["image_generation","video_generation","animation_generation"]}
```

The storyboard was **not** re-approved (`approve_storyboard` correctly 409s from
`MEDIA_GENERATION`), the project was **not** re-triggered, and **no media task was re-run** — the
18 assets in SeaweedFS are the ones the continuation consumes.

### 3.2 The automatic recovery

**It has NOT fired yet, and the reason is arithmetic, not a fault.** Final check at
**18:34:05Z**:

```
pipeline_checkpoints (bd99fe37)   transcript_refinement complete 16:00:59
                                  storyboard_generation complete 16:01:37
                                  image_generation      complete 16:45:05
                                  video_generation      pending  16:47:01   <- still the newest row
composition_manifests             0 rows
projects.state                    MEDIA_GENERATION
ivgs:media_tasks:bd99fe37...      1     ttl 79814
watchdog claim lines so far       0
```

No manifest, voiceover, talking-head or draft task has started.

**Why not.** The watchdog claims a join only when it is older than
`IVGS_MEDIA_JOIN_TIMEOUT_SECONDS`, default **7200 s**, and it derives that age from the counter's
TTL: it claims when `ttl < MEDIA_JOIN_TTL_SECONDS - timeout` = `86400 - 7200` = **79200**. The
join was armed at **16:44:20**, so the earliest sweep that can claim it is **18:44:54** — the
first 5-minute tick after `16:44:20 + 2 h`. At the 18:34 check the TTL was **79814**: **614
seconds**, one sweep, short of the deadline. Every sweep in between did exactly what it should:

```
18:29:54  {"event":"media_join_watchdog_join_outstanding","job_id":"bd99fe37-...",
           "remaining_tasks":1,"age_seconds":5135,"deadline_seconds":7200,
           "outstanding_stages":["animation_generation"]}
18:29:54  {"event":"media_join_watchdog_sweep","swept":1,"advanced":0,"failed":0,
           "skipped_recent":1,"deadline_seconds":7200}
```

The watchdog is working, is watching this exact job, and has been naming the exact stage
responsible since 17:49. It is simply **not due**. Left alone it will claim and advance this job
at 18:44:54. **This package's observation window closed before that**, so the recovery is
reported as the manual path below and the operator should assume it is needed.

> **Operator: run the block in §3.2.1.** If the job has already moved by the time you read this —
> a row in `composition_manifests`, or `media_join_watchdog_advanced_with_failures` in the node-01
> default worker log — the watchdog got there first and the block is unnecessary. It is safe
> either way: the block ends by deleting the join keys, so a later sweep finds nothing to claim
> and cannot double-dispatch. But check first; there is no reason to run it twice.

### 3.2.1 The manual path — ONE block, zero edits

Dispatches Stage 4 through the orchestrator's own input builder, so the manifest is built from
exactly the input the pipeline would have used. **Consumes the 18 existing assets; re-runs no
media generation; does not touch project state; does not re-approve or re-trigger anything.**
node-01.

```bash
docker exec ivgs-celery-default sh -c 'cd /app && PYTHONPATH=/app python - <<PYEOF
JOB = "bd99fe37-0621-40da-aa30-e058cc776c23"

from config import WorkerConfig
import tasks.pipeline_orchestrator_v2 as o

cfg = WorkerConfig()
ctx = o._get_media_join_context(JOB, cfg) or {"job_id": JOB}
stage = o.PipelineStage.COMPOSITION_MANIFEST.value
task_input = o._build_stage_input(stage, None, cfg, ctx)
res = o.celery_app.send_task(
    o.STAGE_TASK_MAP[stage],
    kwargs={"task_input_dict": task_input},
    queue=o.STAGE_QUEUE_MAP.get(stage, "default"),
)
o._cleanup_media_join_keys(JOB, cfg)
print("dispatched", o.STAGE_TASK_MAP[stage], "->", res.id)
print("job_id    ", task_input.get("job_id"))
print("project_id", task_input.get("project_id"))
PYEOF'
```

Expected output:

```
dispatched tasks.stage4_manifest.build_composition_manifest -> <uuid>
job_id     bd99fe37-0621-40da-aa30-e058cc776c23
project_id c12fa967-f989-4ed4-8e20-3ea62cb92e8f
```

`_cleanup_media_join_keys` on the second-to-last line is what makes this safe against a later
sweep: with the counter gone there is nothing left for the watchdog to claim.

**Then confirm it moved** (node-01, one block):

```bash
docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
  "select stage_name, status, created_at from pipeline_checkpoints
    where job_id='bd99fe37-0621-40da-aa30-e058cc776c23' order by created_at;
   select id, locked_at from composition_manifests
    where job_id='bd99fe37-0621-40da-aa30-e058cc776c23';"
docker logs ivgs-celery-default --since 10m 2>&1 | grep -E "stage4_manifest|composition_manifest|stage_completion_received_v2" | tail -20
```

A `composition_manifests` row plus a `composition_manifest` checkpoint means Stage 4 landed; the
orchestrator then dispatches Stage 5 (TTS, `gpu_tts`) on its own and the run continues to gate 2
in §4 — where the two gaps recorded there are waiting.

**If Stage 4 fails it will say so loudly.** `tasks/stage4_manifest.py` is a thin driver over four
API endpoints and its `_check()` turns 4xx into `ValueError` and 5xx into `RuntimeError`; the
refusing endpoint will be named in the node-01 default worker log. **Do not re-run media
generation in response to any Stage 4 failure** — the 18 assets are intact in SeaweedFS and every
one of them is scene-linked in `assets`.

### 3.3 Making the watchdog do it, instead of doing it yourself

If the shipped mechanism should perform the recovery rather than a hand dispatch, age the counter
past the deadline and wait for the next 5-minute sweep. This is the *supported* lever - the
watchdog derives a join's age from the key's TTL, and this is what to reach for on any future
stranded join that must not wait two hours:

```bash
docker exec ivgs-redis redis-cli EXPIRE \
  ivgs:media_tasks:bd99fe37-0621-40da-aa30-e058cc776c23 79000
```

`79000 < 86400 - 7200`, so the counter reads as older than the deadline and the next sweep claims
it. The recovery it then performs is the one exercised end-to-end in §2.4. Use **either** this or
§3.2.1, not both.

### 3.4 One honest wrinkle in the recovery

The watchdog counts every unreported task as **vanished** and adds it to `failed_count`. For this
job that is a mislabel: the animation stage did not vanish, it rendered 12 images that are in
SeaweedFS with a `success` result in `celery_taskmeta`. The number is **log-only** — it is not
passed into the composition-manifest input (`_build_stage_input` for that stage returns
`base_input`), so the manifest is built over all 18 assets regardless. Recorded here so nobody
reads `failed_count: 1` in the recovery line as lost footage. It applies only to the §3.3 route;
the §3.2.1 manual dispatch does not go through the watchdog and produces no such number at all.
With `join_stage` deployed, a future run of this shape cannot reach the watchdog in the first
place.

---

## 4. Task 4 — the designed human stops (operator route card)

The spec is explicit and consistent: **two** gates, and only two. §4 of the AD-05 amendment —
"Stage sequence. Stages 1 → 2 → [gate] → 3 → 4 → 5 → 6 → 7 → [gate] → 8" — and §7.1 — "The two
human review gates (storyboard approval, draft approval) are implemented as workflow signals."
The orchestrator agrees: `STAGE_TRANSITIONS` maps exactly `storyboard_generation` and
`prototype_draft` to `None`, and `_determine_gate_status` returns `storyboard_review` and
`user_review` for them.

### Gate 1 — storyboard review ✅ *confirmed, and already passed by this run*

| | |
|---|---|
| **After** | Stage 2 (`storyboard_generation`) |
| **`projects.state`** | `STORYBOARD_GENERATION` — written by WP-38's edge on the first scene POST |
| **`render_jobs.status`** | `success` (the *stage's* job succeeded; the pipeline is paused, not failed) |
| **Operator reviews** | the 18 scenes — `GET /api/v1/projects/{id}/scenes` (a **bare array**, WP-38), or the storyboard tab on the project page |
| **Continue** | `POST /api/v1/projects/{id}/scenes/approve?tier=prototype`, operator-or-admin |
| **Effect** | `MEDIA_GENERATION` + `dispatch_media_generation` with all scenes |
| **Guard** | 409 `INVALID_STATE_TRANSITION` from `MEDIA_GENERATION` and later — this is the guard working, not a fault |

### Gate 2 — draft review ⚠ *designed, reachable, but its continuation is not wired*

| | |
|---|---|
| **After** | Stage 7 (`prototype_draft`) — a 720p draft, spec §6.1 |
| **`projects.state` should be** | `USER_REVIEW` (spec §6.1: "Post-assembly: Project state transitions to `USER_REVIEW`") |
| **`projects.state` will actually be** | **`MEDIA_GENERATION`** — see the two gaps below |
| **Operator reviews** | the 720p draft; lip-sync alignment, scene order, audio |
| **Continue (designed)** | `POST /api/v1/projects/{id}/trigger?tier=…` from `USER_REVIEW` → `FINAL_RENDER` |
| **Continue (today)** | the block in §4.1 |

**Gap A — nothing advances `projects.state` past `MEDIA_GENERATION`.** Only three writers exist:
`trigger_pipeline`, `approve_storyboard`, and WP-38's scene-write edge. `transition_state()` is
implemented, validates against `PROJECT_STATE_TRANSITIONS`, and **has no route and no caller**
(ORCH-5). `stage7_prototype_draft.py`'s own docstring lists "9. Transition project state to
`USER_REVIEW`" as a step; no code performs it. So `MANIFEST_GENERATION`, `AUDIO_GENERATION`,
`TALKING_HEAD_RENDER`, `PROTOTYPE_DRAFT` and `USER_REVIEW` will never appear on this project.

**Gap B — even from `USER_REVIEW`, `/trigger` dispatches nothing.** `trigger_pipeline` accepts
`USER_REVIEW → FINAL_RENDER`, flips the state and inserts a `render_jobs` row — and then only
sends a Celery task `if current_state == ProjectState.DRAFT`. The comment at
`project_service.py:311` says the other branch is "wired separately (P1.5 item 2 / Stage 3)",
which is the *storyboard* path, not this one. Stage 8 is never dispatched.

Both are **`ivgs-api` changes and were deliberately left out of this package** — WP-39 ships
`ivgs-workers` only, and widening it would have dragged the API and frontend into a deploy they
do not need. Scoped for the next package; the operator is not blocked meanwhile:

#### 4.1 Passing gate 2 by hand, until A and B are fixed

```bash
# 1. after reviewing the draft, put the project on the state the spec sanctions
docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
  "update projects set state='USER_REVIEW', updated_at=now()
   where id='c12fa967-f989-4ed4-8e20-3ea62cb92e8f';"

# 2. dispatch Stage 8 through the orchestrator's own input builder
docker exec ivgs-celery-default python - <<'PY'
JOB = "bd99fe37-0621-40da-aa30-e058cc776c23"

from config import WorkerConfig
import tasks.pipeline_orchestrator_v2 as o

cfg = WorkerConfig()
stage = o.PipelineStage.FINAL_RENDER.value
task_input = o._build_stage_input(stage, None, cfg, {"job_id": JOB})
res = o.celery_app.send_task(
    o.STAGE_TASK_MAP[stage],
    kwargs={"task_input_dict": task_input},
    queue=o.STAGE_QUEUE_MAP.get(stage, "default"),
)
print("dispatched", o.STAGE_TASK_MAP[stage], "->", res.id)
PY
```

### The rest of the route, for orientation

Between the two gates the pipeline is meant to run unattended:
Stage 4 composition manifest (`default`) → Stage 5 TTS (`gpu_tts`) → Stage 6 talking head
(`gpu_talking_head`) → Stage 7 draft (`composition`). Each hop is
`handle_stage_completion` → `STAGE_TRANSITIONS` → `send_task`. **No other stop is designed.**
Anything else that halts is a defect, and the first place to look is now the watchdog's own
`media_join_watchdog_sweep` line.

---

## 5. Task 5 — ledger

### (a) `worker_confirmed_dead` on three healthy nodes, every 30 s — **FIXED**

`supervise_worker_heartbeats` read `last_heartbeat_epoch`, `status`, `node_hostname` and `id` off
each `/fleet` node. `FleetNodeStatus` (ivgs-scheduler `main.py`) publishes **none of them**. It
publishes `node_id`, `last_heartbeat` (ISO-8601), `is_alive`, `is_draining`. The registry keeps
`last_heartbeat_epoch` internally and does not expose it.

So `node.get("last_heartbeat_epoch", 0)` was `0`, `elapsed` was the whole Unix epoch, and every
node was past every threshold on every tick:

```json
{"task":"heartbeat_supervision","node_hostname":null,"seconds_since_heartbeat":1787504720,
 "event":"worker_confirmed_dead","level":"error"}          x3, every 30s
HTTP Request: PATCH http://ivgs-scheduler:8001/nodes/None "404 Not Found"   x3, every 30s
```

`seconds_since_heartbeat: 1787504720` is the tell — that is the epoch, not an age. The masking
is the real cost: a node that had genuinely died would have produced exactly the same three lines.

**Fixed:** parse `last_heartbeat` (preferring `last_heartbeat_epoch` if a future scheduler ever
sends it); treat "no usable timestamp" as its own outcome (`worker_heartbeat_age_unknown`, with a
separate `fleet_heartbeat_timestamp_unparseable` for a malformed one) rather than as a death; let
`is_alive` — the registry's own verdict — veto a burial; log `node_id`, which exists.

**The two `client.patch("/nodes/{id}")` remediation calls are removed.** ivgs-scheduler registers
no `PATCH /nodes` route at all (`/schedule`, `/register`, `/heartbeat`, `DELETE`, `/fleet`,
`/drain/{node_id}`, `/health`, `/metrics`), and the id key they interpolated did not exist in the
payload either — every call was a literal `PATCH /nodes/None → 404`. Nothing was ever remediated,
so nothing was lost. Supervision is observation until a real "mark dead" edge exists; the
scheduler already ages nodes out of its registry via `is_alive`.
→ **Follow-up, recorded not fixed:** §6.2's remediation is unimplemented on the scheduler side.
Do not re-add the PATCH without a route to send it to. The scheduler is pinned (WP-09).

**Adjacent one-liner, same mismatch, found while fixing it:** `collect_gpu_fleet_metrics` read
`fleet.get("online_nodes")`; the field is `alive_nodes`. It reported `online_nodes: 0` with three
live nodes on every 60-second tick.

**Observed live after deploy — steady state:**

```
17:40:24  supervise_worker_heartbeats succeeded in 0.105s:
          {'status':'ok','total_nodes':3,'suspected_dead':0,'confirmed_dead':0,'unknown_heartbeat':0}
```

Zero `worker_confirmed_dead` lines. Zero `PATCH /nodes/None` 404s. Previously six log lines per
30 seconds, all wrong.

But silence is weak evidence — green is also what a broken supervisor looks like from a
distance. So a **deliberate probe inside the running `ivgs-celery-default` on the deployed
image**, feeding it one live node, one genuinely dead one, one marginal one and one carrying no
timestamp at all:

```
RESULT -> {"status":"ok","total_nodes":4,"suspected_dead":1,"confirmed_dead":1,"unknown_heartbeat":1}
   worker_confirmed_dead        -> DEAD:gpu0     900
   worker_suspected_dead        -> slow:gpu0     90
   worker_heartbeat_age_unknown -> nostamp:gpu0
PATCH calls issued: 0
```

A real death surfaces by name with a real age; the healthy node is silent; the unknowable one is
neither. **Swallow register instance 23, CLOSED** on that probe — it records both halves of this
site: the unchecked `client.patch()` response, and the far worse contract mismatch that made a
genuine death indistinguishable from three healthy nodes.

### (b) CLIP scoring absent; all 18 assets `flagged` — **RECORDED, with a correction**

The brief's account is right about the symptom and understates the cause. There are **two**
defects here, and they compound in the worst possible direction.

**b1 — the CLIP endpoint does not exist.** `stage3_images.py:434` builds
`clip_api_url = f"{config.pipeline_api.base_url}/api/v1/clip"` and `ImageValidator._compute_clip_score`
POSTs to `{that}/score`. `ivgs-api` registers 32 routers and **not one of them is a clip router**;
there is no `/api/v1/clip` path in the app. Every call 404s, logs `clip_score_api_error` at
**warning**, and returns `None`.

**b2 — `numpy` is not installed in the worker image.** Confirmed inside
`ivgs-workers:v5.6.6-mediajoin`: `import numpy → No module named 'numpy'` (Pillow 12.2.0 is
present; `numpy` is absent from `requirements.txt`). `ImageValidator.validate` catches that
`ImportError`, sets `blank_check_ok = noise_check_ok = True` **unconditionally**, and appends one
warning — and `decision = FLAGGED` fires on *any* warning.

Decoded from `celery_taskmeta` for this run — all 16 images, both tasks:

```
quality_decision : {'flagged': 16}
clip_score       : {None: 16}
quality_score    : [1.0]          <- a perfect score
errors           : []
```

A **perfect 1.0** with **no CLIP score and no blank/noise detection**, flagged. The 1.0 comes from
`_compute_quality_score`'s `else: score += 0.15  # Default pass if CLIP unavailable` plus the two
image checks that were skipped and marked passed. So the flag queue fills with assets whose
recorded score says they are flawless and whose only real finding is "the checker was missing".
Neither number means anything, and the pair of them is worse than either alone.

**Swallow register instance 24, OPEN.** This is entry 5's shape — *manufactures a success* —
applied to the one component whose entire job is to withhold approval. Written up in full in the
register.

**Scope:** not fixed here. b2 is a `requirements.txt` + image change that re-opens the blank/noise
checks on real footage and needs its own verification pass; b1 needs a CLIP scoring service that
does not exist yet, or the honest alternative — stop constructing a URL for it, drop the free
0.15, and record `clip_score: unavailable` instead of `None`. Both belong in one package about
what a quality score is allowed to claim.

Also noted: the 2 video assets carry `quality_decision: ""` and `quality_score: 0.0` — the video
path runs no validator at all. Same package.

### (c) `video_generation` checkpoint stuck at `pending` — **FIXED**

Both clips rendered and uploaded; the row still read:

```
video_generation   3   pending   2026-08-23 16:47:01Z
```

`generate_video_clips` wrote a checkpoint after every scene with `status="running"` (which the API
maps to the `pending` enum label) and then wrote **nothing at the end**. Stage 3 writes a terminal
checkpoint at exactly that point; the video stage did not, so for the whole life of the stage the
database could not distinguish "still rendering" from "finished" — which is precisely what sent
the earlier triage after the wrong thread.

**Fixed:** terminal `save_checkpoint` added at the same point, same shape, same
`enable_checkpoint_saving` guard, same loud `CheckpointWriteError` on failure, `stage_index=3`,
status from `output.status` (`success` / `partial_success` / `failed`), and it is written
**before** the completion report — the join advances on that report, so the durable record must
already exist when it fires. There is a test asserting that ordering.

Related, fixed in the same edit: Stage 3's checkpoint now keys on `join_stage`, so the animation
run no longer upserts over the image run's row.

### (d) 83 messages parked in the **unprefixed** `default*` Redis lists — **PURGED, provably inert**

Not one message — **83**, in four lists:

| list | count | task |
|---|---|---|
| `default` | 1 | `dispatch_pipeline` — job `dc5729d3-6ea8-4555-9739-459b7150b138`, project `1982b93b` "2B-E2E-smoke-195416" |
| `default:3` | 4 | `collect_gpu_fleet_metrics` |
| `default:5` | 1 | `process_dead_letter_queue` |
| `default:9` | 77 | `supervise_worker_heartbeats` |

**Why they sit unconsumed while workers subscribe to `default`:** the workers do not read those
keys. `celery_app.py` sets `broker_transport_options["global_keyprefix"] = "ivgs_workers_"`
(commit `6d1234e`, 2026-05-29, the pidbox fix), so the live queue key is `ivgs_workers_default`
and its priority sub-lists are `ivgs_workers_default:3/5/9` (`sep: ":"`, `priority_steps 0-9`).
Every message in the bare lists predates that commit. `ivgs-api`'s producer carries the same
prefix (`app/services/celery_producer.py`) and `ivgs-backup-worker` uses `ivgs_backup_`, so
nothing writes there either. The bare `default` list is a fossil of the pre-prefix keyspace.

**Proof of inertness, both directions:**
- *No producer.* `default:9` held exactly **77** messages at 17:05 and exactly **77** at 17:50,
  a window in which beat sent ~90 `supervise_worker_heartbeats` tasks, every one of which was
  received and executed by `default-worker@node01`. The list is frozen.
- *No consumer.* Those 77 have sat unread since 2026-05-29 while the worker drained its own queue
  continuously for three months. A consumer would have emptied them in milliseconds.

**Purged**, after backing up all 83 raw messages with a restore procedure to
`/opt/ivgs/rollback-storage/wp39-unprefixed-default-queue-20260823/` (`default.jsonl`,
`default_3.jsonl`, `default_5.jsonl`, `default_9.jsonl`, `README.md`). `ivgs_workers_default*`
was untouched and still reads 0. The 82 periodic-task messages are superseded many times over.
The one that references real work — job `dc5729d3`, still `pending`, project stuck at
`TRANSCRIPT_REFINEMENT` since 2026-06-01 — is the one that must **not** be blind-restored: doing
so would start Stage 1 on an 83-day-old smoke test. The backup README says so explicitly.

### (e) Build hygiene — **RECORDED**

There is **no `.dockerignore`** anywhere in the repo, so the build context carries the host's
`__pycache__` directories into the image. The first `v5.6.6-mediajoin` build shipped stale
`.pyc` files for the very modules this package changed (`v5.6.4-stage2output` has 13 of them in
`/app/tasks/__pycache__` too — this is long-standing, not new). CPython invalidates on source
mtime+size so it is unlikely ever to have executed stale bytecode, but it defeats content-gating
an image by grep and it should not be relied on. **The shipped image was rebuilt `--no-cache`
from a cleaned context and contains zero `__pycache__` directories** (verified). A repo-level
`.dockerignore` affects all three images and belongs in a package that can re-verify all three.

### (f) Swallow detector — **RECORDED, one new instance of an open class**

Detector over the four touched files: **23 → 24 findings**. The single addition is `SF004`
"`save_checkpoint()` return value discarded" at the new terminal checkpoint — deliberately
identical to the two existing sites in `stage3_images.py` that it was written to match.
`save_checkpoint` **raises** `CheckpointWriteError` since WP-07; the boolean return is vestigial
at all 15 call sites. Not allowlisted: that is a 15-site decision and a `required=` API question,
not this package's. The two `SF002` findings this work initially introduced were restructured
away rather than suppressed.

### (g) Cosmetic trap — **already documented, re-confirmed**

`ivgs-infra/.env.node01` still carries a stale `IVGS_WORKERS_TAG=v5.1.1-pidbox-fix`. This is
**already recorded in `dev/CLAUDE.md` §6** ("Never read a tag variable out of a container and
believe it", corrected 2026-08-22 under WP-DEPLOY-R2-R5-NODE04) and is re-confirmed here rather
than reported as new. It is injected into the container's environment via the service-level
`env_file:` but is **not** what selects the image — compose interpolates `${IVGS_WORKERS_TAG}`
from `.env`, which is correct at `v5.6.6-mediajoin`. Every deploy verification in §7 therefore
used `docker inspect --format '{{.Config.Image}}'` and content markers, never the container-side
tag variable. Left alone: `.env*` is never committed and editing node env is outside this
package.

---

## 6. Tests

**32 new tests, in three modules, all failing against the pre-fix code.**

| module | n | what it pins |
|---|---|---|
| `test_wp39_media_join.py` | 14 | the label collision (reproduced executably with the real 4/12/2 storyboard), three distinct join labels closing the join, `join_stage` surviving both pydantic input models, the WP-06 redelivery guard still firing, `None` ≠ `[]` in `_outstanding_media_stages`, and the watchdog logging on every sweep / naming an outstanding join / advancing past the deadline |
| `test_wp39_video_checkpoint.py` | 6 | the terminal checkpoint exists, carries the right status for success and partial-success, is honoured by `enable_checkpoint_saving`, and is written **before** the completion report |
| `test_wp39_heartbeat_schema.py` | 12 | the ISO field is read, the pre-fix epoch read is demonstrated, an explicit epoch still wins, an unparseable/missing timestamp is `unknown` not ancient, three live nodes are not buried, a genuinely stale node still is, `is_alive` vetoes, no `PATCH` is issued, and `alive_nodes` is the field that exists |

The join tests run against a **real Redis** (the WP-06 convention: the join is a server-side Lua
script and a mock cannot prove it), skipping cleanly if `IVGS_TEST_REDIS_URL` has nothing on it.
`send_task` is patched `autouse` in both Redis modules — see the Incident in the WP-06 report.

**Suite, like-for-like, same environment, same command:**

| | baseline (`7cdfbf4`) | with WP-39 |
|---|---|---|
| `ivgs-workers/tests` | 401 passed, 30 failed, 15 errors | **434 passed**, 30 failed, 15 errors |
| full suite | 514 passed, 252 failed, 1093 errors, 15 skipped | **546 passed**, 252 failed, 1093 errors, 15 skipped |

`+32` passed in both, nothing else moved. The baseline was measured by stashing this package's
changes and re-running the identical command, not quoted from an earlier report — the failure and
error counts are environment-dependent (they need `TEST_DATABASE_URL` pointed at
`ivgs_reconciliation_test`) and differ from the numbers in the WP-38 report for that reason.

---

## 7. Build and deploy — `v5.6.6-mediajoin`

Built from committed tree `36cf538`, under the WP-34 binding rules in full.

**Authority.** `dev/CLAUDE.md` §1 reserves commit and deploy to the operator. This package was
handed over explicitly: the WP-39 brief instructs "Commit and HOLD — never push. Build/deploy
what changed as v5.6.6-mediajoin under the WP-34 binding rules in full", and WP-34 itself records
"Operator authorizes autonomous execution R1–R7 **including node deploys**, per the
WP-DEPLOY-R2-R5 precedent. Commit-and-HOLD any repo changes; operator pushes." Nothing was pushed
and nothing was merged. Commands were run on node-02/03/04 under that hand-over and nowhere else.

**Only `ivgs-workers` changed, so only `ivgs-workers` was built.** `ivgs-api` and
`ivgs-frontend` remain on `v5.6.5-reviewgate` and were not rebuilt, not re-tagged and not
recreated. `ivgs-scheduler` remains pinned at `v5.0.0-20260522` (WP-09).

| | |
|---|---|
| Image id | `sha256:e662d443f090e4d1cf23e15891bd46f5dd90c2caffba6fd827fd21f51e46103d` |
| Banked **before** any push | `zstd -t` rc 0, `sha256sum -c` **OK**, exactly **1** new MANIFEST line, 257 M |
| Artifact | `/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.6.6-mediajoin.tar.zst` |
| GHCR push | **FAILED — `error from registry: unauthorized`.** No credential in this session. Per binding rule 1 this aborts nothing: the artifact is the distribution path and every node was fed from it. **Operator action: push when convenient.** |

### Content gates — all pass, inside the built image

Positive: `join_stage` present in all three task modules · `_outstanding_media_stages` ·
`media_join_watchdog_sweep` · `media_join_watchdog_join_outstanding` · `expected_stages` ·
`_heartbeat_age_seconds` · `worker_heartbeat_age_unknown` · `alive_nodes`.

Negative, checked against the **AST** rather than by grep, so a docstring quoting the old code
cannot pass or fail it: **zero** defaulted `last_heartbeat_epoch` reads and **zero** fleet
`client.patch` calls in executable code (the one remaining `.patch` is
`_update_job_celery_task_id`'s jobs-API call, unrelated). The old three-block dispatch is gone.
Image carries **0** `__pycache__` directories.

Carry-over markers from earlier packages, all still present: `_MEDIA_JOIN_REPORT_LUA` (WP-06) ·
`CheckpointWriteError` (WP-07) · `release_acquired_reservation` (WP-08) ·
`check_visibility_timeout` (WP-05) · `plan_frame_aligned_pieces` (WP-04).

**Behavioural gate** (rule 4 prefers demonstration): the full watchdog recovery cycle executed
inside the built image against scratch Redis db 9 — §2.4.

### Deploy

Registry off the deploy path. Nodes 02/03/04 fed from `/mnt/ivgs-shared` via
`zstd -d | docker load`; each verified `sha256sum -c` **OK** and `zstd -t` rc 0 on the artifact
*before* loading, was **presence-gated before any `.env` write**, had its rollback tag read from
`.Config.Image` (`v5.6.4-stage2output`, confirmed **still present** locally on every node), and
had its `.env` backed up to `.env.bak.pre-wp39-<ts>`. Compose invocations derived from container
labels, `--force-recreate --no-deps --pull never`, services named explicitly. No `.env` committed.
Only `^IVGS_[A-Z_]*TAG=` style greps used.

| node | services recreated | verified |
|---|---|---|
| node-01 | `celery-worker-default`, `celery-worker-composition`, `celery-beat` | all three healthy on the new tag; markers present in all three running containers; `IVGS_BROKER_VISIBILITY_TIMEOUT=7200` intact |
| node-02 | `celery-worker` only | healthy; markers present; **`ivgs-vllm-primary` untouched, Up 16 hours (healthy)** |
| node-03 | `cogvideox-worker` only | healthy; markers present; **`ivgs-cogvideox-server-node03` untouched, Up 18 hours (healthy)** |
| node-04 | `celery-worker` only | healthy; markers present; **rule 5 satisfied** — `IVGS_LATENTSYNC_TAG=v5.2.7-h0` identical before and after, and latentsync / comfyui-primary / kokoro / whisperx / coqui all still **Up 40 hours (healthy)**, none recreated |

```
celery inspect active_queues
->  default-worker@node01: OK      ->  composition-worker@node01: OK
->  celery-worker@node02: OK       ->  cogvideox-worker@node03: OK
->  image-worker@node04: OK
5 nodes online.
```

Queue map identical to the pre-deploy baseline. Postgres, Redis, SeaweedFS, the scheduler,
`ivgs-fastapi` and `ivgs-nextjs` untouched.

### Rollback

Per node: restore the recorded `.env` tag (`IVGS_WORKERS_TAG=v5.6.4-stage2output`) and re-run the
same label-derived compose invocation. **Verified, not assumed:** `v5.6.4-stage2output` is still
present in the local image store on node-01, node-02, node-03 and node-04, and its artifact is
still in `/mnt/ivgs-shared/image-artifacts`.

---

## 8. What is NOT verified

- **Job `bd99fe37` has NOT been observed moving past media generation.** As of 18:34:05Z the
  newest checkpoint is still `video_generation pending`, `composition_manifests` is empty, and the
  join counter still reads 1. This is not a failure of the fix: the watchdog's 2-hour deadline
  falls at **18:44:54Z**, 614 seconds after this package's last check, and every sweep up to then
  correctly reported the job as outstanding and named `animation_generation`. **The recovery
  itself is therefore unobserved on this job** — proven inside the built image (§2.4) and by test,
  not on `bd99fe37`. §3.2.1 is the operator block; §3.3 is the alternative.
- **The pipeline past Stage 4 has not been exercised at all.** Whether Stage 5 (TTS), 6 (talking
  head) and 7 (draft) then run is the next thing this job will find out, and gate 2's two gaps
  (§4) sit in front of the end of it.
- **`join_stage` has not yet been exercised by a real animation dispatch.** Job `bd99fe37` was
  dispatched by the old image. The fix is proven by test and by the mechanism the live watchdog
  now names; the first *new* run through `approve_storyboard` is what closes it observationally.
- **GHCR does not have this tag.** Every node has the image; the registry does not.
- **Ledger (b) is recorded, not fixed** — 16 assets remain `flagged` with a meaningless 1.0.

---

## 9. Held commits and the single gated push block

Nothing has been pushed. `origin/main` is unchanged.

| # | commit | |
|---|---|---|
| 1 | `7cdfbf4` | `docs(wp-39): handoff — WP-39 was never started…` (the stub this file replaces) |
| 2 | `36cf538` | `fix(media-join,watchdog): WP-39 the animation stage could not report; the watchdog ran silently` |
| 3 | *(this report)* | `docs(wp-39): record the root cause, the watchdog finding, the v5.6.6-mediajoin build and the four-node deploy` |

**Paste-ready, gated on the count so it cannot push more than it should:**

```bash
\
git fetch origin && \
AHEAD=$(git rev-list --count origin/main..HEAD) && \
BEHIND=$(git rev-list --count HEAD..origin/main) && \
echo "ahead=$AHEAD behind=$BEHIND" && \
test "$AHEAD" = "3" && test "$BEHIND" = "0" && \
test -z "$(git status --porcelain)" && \
git log --oneline origin/main..HEAD && \
git push origin main
```

If `ahead` is not 3 or `behind` is not 0, **stop and re-read** — the block deliberately refuses
rather than guessing which commits were meant.
