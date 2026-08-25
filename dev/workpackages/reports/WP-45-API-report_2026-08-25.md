# WP-45-API — the eight green buttons, the gate with no corridor, and a dedup probe that never ran

| | |
|---|---|
| **Date** | 2026-08-25 |
| **Built from** | `d76b355` (clean tree, `HEAD == origin/main` at start) |
| **Version** | **`v5.11.0-apibatch`** — api, frontend, workers, as one coherent set |
| **Deployed** | node-01 (5 services). **Nodes 02–05 NOT deployed — no SSH access from this session.** Paste blocks in `dev/workpackages/WP-45-operator-blocks.md` |
| **Schema** | migration **0028** applied to `ivgs` and `ivgs_reconciliation_test`. Pre-migration dump banked |
| **Repo state** | **Commit-and-HOLD. 8 commits, not pushed.** Count-gated push block in §12 |
| **Suite** | 68 failed / 1578 passed / 63 skipped / 77 errors. **ZERO NEW FAILURES**, by before/after diff against `d76b355` over every module (§10.3) |

---

## 0. The one paragraph worth reading first

Six tasks, and five of them turned out to be the same defect wearing different
clothes: **a surface that answered confidently about something it had not
done.** The dedup probe called a route that was never built and read the 404 as
"no duplicate". Eight endpoints created a job row, returned 202, and dispatched
nothing. The state machine was fully implemented and had no caller, so five of
its thirteen states could not occur and the draft-review gate had a door with no
corridor behind it. Two timestamp columns were declared, read, and written by
nothing. The GPU tiles read 0/0 off a table no component has ever written, while
three GPUs worked. In every case the honest answer and the confident-but-empty
answer were the *same value* — `None`, `0`, `202`, `pending` — which is why none
of them ever showed up as an error.

The through-line in the fixes is therefore narrow: **give "I don't know" a value
of its own.** `DuplicateCheckError` instead of `None`. A 503 instead of an empty
fleet. `null` instead of `0%`. "not recorded" instead of "Unassigned". And a
test suite that asserts a broker message rather than a status code, because the
status code was already right.

Verified live on the reference project: the project state advanced
`MEDIA_GENERATION → MANIFEST_GENERATION → AUDIO_GENERATION` at 15:20 today —
the first time either of those states has appeared on any project in this
system.

---

## 1. Per-task verdicts

| Task | Verdict | One line |
|---|---|---|
| **1** asset dedup + provenance | **DONE, live-verified** | The probe route exists and answers; upload persists content hash, params hash and a provenance JSONB; all four media branches wired; dedup hit proven on identical inputs |
| **2** gate 2 wired | **DONE, live-verified** | `PATCH /projects/{id}/state` is the caller ORCH-5 lacked; the back half advances state; Stage 8 dispatches from `USER_REVIEW`; P1.4q returns a failed project to `DRAFT` |
| **3** the eight stub sites | **DONE, 8/8, tested by broker message** | Every site produces a real message to a registered task. Live: Regen replaced an asset end to end |
| **4** GPU registry read-through | **DONE (a) partially — needs one paste per node** | API reads the scheduler; tiles read 3 online / 2,055,627 MB instead of 0/0. Urgent queue investigated, proven inert, cleared. `IVGS_NODE_NAME` needs the operator's node `.env` |
| **5** job timestamps | **DONE** | Stamped at the one choke point every worker status change passes through |
| **6** smaller ruled items | **DONE (a)–(f), (g) RECORDED as required** | Thumbnails 115× smaller, measured; per-language progress derived; the five scene fields persist; attestation widened to TEXT |

---

## 2. TASK 1 — a probe that could not fail, and an upload that discarded the answer

### 2.1 Both halves, measured

WP-46's addendum A5.2 found this and scoped it. Both halves confirmed on the
tree before any change:

**The route did not exist.** `check_duplicate_asset`
(`ivgs-workers/utils/media_converter.py:498`) called `GET /api/v1/assets?sha256=`.
`asset_router` carried `/{asset_id}`, `/{asset_id}/download`,
`/{asset_id}/regenerate` and DELETE — no bare list route. FastAPI matched the
bare path to nothing and answered 404; the helper caught **every** exception and
returned `None`; all four call sites read `None` as "no duplicate exists".

**The upload discarded three fields.** `POST /projects/{id}/assets/upload`
declared five form fields. The media tasks send seven or eight. FastAPI drops
what a signature does not declare, silently, with a 201 — so `content_hash`,
`metadata` and the generation-parameters hash went nowhere, and no caller could
tell.

### 2.2 Four branches, not three — and they dedup on different things

The brief named three media branches. There are **four**, and the fourth
(`stage5_voiceover`, audio) had the same dead probe. More importantly the four
split into two groups asking genuinely different questions:

| Branch | Probes on | When | What a hit saves |
|---|---|---|---|
| `stage3_images` | content hash | **after** the render | the upload and a duplicate row |
| `stage5_voiceover` | content hash | after synthesis | the upload |
| `video_generation_task` | **params** hash | **before** the render | the GPU time |
| `animation_generation_task` | **params** hash | before the render | ~256 s of GPU time (WP-46 measured) |

The second group is the expensive one and it **could never have hit**, twice
over: the probe route did not exist, *and* `generation_params_hash` was never
stored, so even a working route would have found nothing.

### 2.3 A defect found on the way: animation put the params hash in the content field

`animation_generation_task` sent `content_hash=params_hash` and tucked the real
content hash into `metadata` as `content_sha256`. The two are different kinds of
value with different verification rules — a content hash is a claim about bytes
the server can check, a params hash is a caller-owned key over inputs the server
never sees. Under the old route it did not matter, because both were discarded.
**The moment the route began honouring `content_hash`, every animation upload
would have been rejected as corrupt.** They now travel in their own fields.

### 2.4 What was built

`GET /api/v1/assets` takes `sha256` (either column), `content_hash`,
`generation_params_hash`, an optional `project_id`, and a `limit`. Oldest first,
deliberately: the original is the canonical row, and newest-first would hand back
a copy made by an earlier dedup miss. Deleted-tier assets are excluded — a
tombstone is not a dedup target. An unfiltered probe is a 400 naming the route
that does serve a list.

The upload verifies a caller-supplied `content_hash` against the bytes rather
than trusting it. Storing bytes under a hash that is not theirs poisons every
future lookup with a row that can never be found by its real content. The params
hash is stored as given, because the server cannot check it. A dedup hit
backfills a params hash the original row lacked, so assets stored before this
fix become findable the first time they are re-uploaded rather than staying
invisible forever.

`generation_metadata` (JSONB, migration 0028) holds the provenance: engine,
model, prompt, dimensions, job id, content hash, and for animation the two input
asset ids — the four facts WP-46 called "what would let anyone reconstruct how a
given clip was made".

### 2.5 The swallow, replaced rather than removed

Fail-open is still the behaviour: dedup is an optimisation and a failed probe
should mean "generate it anyway". What changed is **where the decision is
taken**. `check_duplicate_asset` now raises `DuplicateCheckError`;
`find_duplicate_or_none` catches it and logs one greppable line —

```
dedup_check_unavailable  hash_kind=params  fail_open=True
  consequence="asset will be generated and uploaded without a dedup check"
```

— which is the WP-08 `gpu_reservation_unavailable ... fail_open=True` precedent
exactly. **Swallow register: instance 26**, opened and closed in the same
package.

A second, smaller swallow closed with it: three call sites read
`existing.get("storage_path")`, a key `AssetResponse` has never sent, so a dedup
hit set the result's path to `""` and the scene lost its file reference.
`asset_storage_path` reads the field the API actually sends.

### 2.6 Live evidence, on the deployed API

```
GET /assets?sha256=<64 zeros>                       HTTP 200   (was 404)
GET /assets?sha256=4261746cd9187bb7...              matches: 1
  id              3d89b0ef-a859-4a34-a110-b3310cbf6fa7
  seaweedfs_path  /ivgs/images/c12fa967-.../image.png
```

`generation_metadata` is `None` on that row, and correctly so: it was uploaded
in August by a worker that predates this change. New uploads carry it — and
node-04, still on `v5.10.0-quality`, will keep producing rows without it until
block B1 is applied, which is stated rather than glossed.

**Dedup hits on identical inputs** are proven in
`tests/test_wp45_dedup_and_gate.py::TestTask1DedupHitsOnIdenticalInputs`, against
the real service and a real database: identical bytes return the same asset id
with `was_deduplicated: true` and `reference_count: 2`; identical **params** with
*different bytes* also dedup, which is the case that saves the GPU and the one a
diffusion model actually produces, since it is not bit-reproducible.

### 2.7 A compatibility branch with a stated shelf life

Because nodes 02–05 update on a separate operator step, a v5.10.0 animation
worker would have had every upload rejected as corrupt by the new check. A
mismatch with **no** `generation_params_hash` is unambiguous — every WP-45
caller sends the two in their own fields — so the value is stored where it was
always meant to go, under one greppable event:

```
asset_upload_legacy_hash_field: ... a pre-WP-45 caller sent its
generation-parameters hash in the content_hash field.
```

A mismatch from a caller that *did* send a params hash stays a 400. **When that
event stops appearing in the API log, every node is on v5.11.0 and the branch is
dead code.** That is the retirement signal, and it is why the event exists.

---

## 3. TASK 2 — the gate had a door and no corridor

### 3.1 Gap A: a state machine with no caller (ORCH-5)

`ProjectService.transition_state` has been implemented since Phase 3. It
validates against `PROJECT_STATE_TRANSITIONS`. It had **no route and no caller.**
Three writers ever touched `projects.state`: `trigger_pipeline`,
`approve_storyboard`, and WP-38's scene-write edge.

So five of the thirteen declared states — `MANIFEST_GENERATION`,
`AUDIO_GENERATION`, `TALKING_HEAD_RENDER`, `PROTOTYPE_DRAFT`, `USER_REVIEW` —
were unreachable, and spec §6.1's *"post-assembly: project state transitions to
`USER_REVIEW`"* never happened. `stage7_prototype_draft.py` lists it as step 9
in its own docstring; no code performed it.

`PATCH /api/v1/projects/{id}/state` is the route. The orchestrator is the
caller, because it is the only component that knows a stage finished and which
one runs next. The map is keyed by **the stage about to run**, so the state
names what is happening rather than what has stopped happening.

The route is idempotent by construction — it is a callback and the worker
retries it — and the helper never raises: a project-state write is a record of
where the pipeline is, and the pipeline must not stop because bookkeeping
failed. But the failure is loud (`project_state_advance_failed`, carrying its
consequence) rather than a silent `False`. A 409 is a warning, not an error: it
means a human moved the project while a stage was running, which is information
about the run.

**A test asserts that every hop the map can produce is one §6.1 already
sanctions** (`test_wp45_project_state.py`), so the map cannot acquire a
transition the state machine would refuse. This adds a caller, not a new rule.

### 3.2 Gap A, closed live

At 15:20 today, on the reference project, triggered by the Task 3 Regen test:

```
15:20:33.716  Project state advanced: c12fa967 -> MANIFEST_GENERATION
                reason=media join complete after image_generation  by=svc-pipeline
15:20:34.262  Project state advanced: c12fa967 -> AUDIO_GENERATION
                reason=dispatching tts_audio after composition_manifest  by=svc-pipeline
```

and on the worker side, the same two hops under `project_state_advanced`.
`projects.state` read `AUDIO_GENERATION`. **Neither state had ever appeared on a
project in this system.**

### 3.3 Gap B: Stage 8 was never dispatched

`trigger_pipeline` from `USER_REVIEW` flipped the state to `FINAL_RENDER`,
inserted a `render_jobs` row, logged "Pipeline triggered" — and sent nothing.
The `send_task` was gated on `DRAFT`. The comment blamed a separate wiring for
"P1.5 item 2 / Stage 3", which is the *storyboard* path.

Both branches now go through `dispatch_pipeline` with `current_stage` set, so
Stage 8's manifest, talking-head asset and scene list come from the
orchestrator's own `_build_stage_input` rather than a second copy of that logic
drifting inside the API. Asserted by broker message in
`TestTask2Stage8IsDispatched`.

### 3.4 P1.4q, ruled: a terminal failure returns the project to DRAFT

Observed twice on 2026-08-23; the operator's documented recourse was
`UPDATE projects SET state='DRAFT'` by hand.

The hop runs `X → ERROR → DRAFT` through `transition_state`'s own validation
twice rather than assigning `DRAFT` directly, so the state machine stays the
single authority on what is legal instead of acquiring a back door. **Job
history is untouched** — that is where the record of the failure lives, and it
is why no new `FAILED` project state is needed.

Two guards worth naming, both tested: it fires only on the **edge into** failure,
so a retried callback cannot walk a project back after somebody has deliberately
moved it on; and a `COMPLETE` project is never undone by a late straggler.

---

## 4. TASK 3 — eight green surfaces over empty actions

All eight fixed. **The acceptance criterion was deliberately not "returns 202"**,
because all eight already returned 202 while doing nothing — a status-code test
would have passed against the defect for as long as it existed.

| # | Site | What it did instead | Now |
|---|---|---|---|
| 1 | scene regenerate | inserted a `storyboard_generation` row | dispatches that scene's media generation |
| 2 | asset regenerate | inserted a row typed from the asset | same, for the asset's scene |
| 3 | job cancel | marked the row cancelled, **left the GPU running** | revokes with `terminate=True, signal=SIGTERM` |
| 4 | DLQ replay + bulk | marked messages replayed, **replayed none** | dispatches first, resolves second |
| 5 | localisation retry | named `pipeline.localise` — registered nowhere | dispatches the back half in that language |
| 6 | quality reject | logged `(stub — Phase 8)` | dispatches, and reports which of the two happened |
| 7 | job resume | named `pipeline.execute_stage` — also not a task | dispatches `dispatch_pipeline` with `resume_from_stage` |
| 8 | Prompt Playground | returned `"[Phase 3 stub] This is a placeholder response…"` | calls the model and returns its answer |

### 4.1 Three decisions inside these fixes worth stating

**Regeneration goes through `dispatch_media_generation`, not straight to a media
task.** This is load-bearing, not tidiness. A media task's completion reports to
a media-join counter; dispatching one without arming that counter sends the
report into `JOIN_UNKNOWN`, three retries, and the DLQ (WP-06 / P1.1). The
orchestrator arms the join for exactly the stages it dispatches, so a one-scene
regeneration drains correctly and flows on into a fresh composition manifest.

**Cancel terminates.** Without `terminate=True`, revoke only prevents a task
that has not started from starting — which is exactly the case a Cancel button
is *not* for. `signal="SIGTERM"` lets `IVGSBaseTask.on_failure` run, so the GPU
reservation is released rather than leaked (WP-08). A revoke that cannot be
delivered is reported: the row is still marked cancelled, because the operator
asked for that, but *"cancelled"* and *"cancelled, and the GPU is still busy"*
are different facts and the response says which.

**DLQ replay dispatches first and resolves second.** The old order marked the row
`resolution='replayed'` and dispatched nothing — which also dropped it out of the
unresolved list. The DLQ's one job is to retain what failed, and its replay
button was quietly discarding messages it claimed to have re-run. A failed
dispatch is now a 502 with the message left unresolved.

`bulk_replay` is per-message rather than all-or-nothing, and `replayed_count`
counts messages that produced a broker message. It used to count every row the
loop touched, so the number the operator read was the size of the filter, not
the size of the action.

### 4.2 One shape found by reading what the fleet actually writes

`task_args` is JSONB and this fleet has written **three different shapes** into
it. The declared shape (`ivgs-workers/services/dlq_service.py:77`) is a list.
The **live** writer (`utils/error_handler.route_to_dlq:297`) writes
`{"args": [...], "kwargs": {...}}` — both nested inside the positional column.
Replaying that dict as positional arguments would hand the task one dict where
it expected several values. The unwrapping handles all three explicitly, and a
plain keyword object is replayed as kwargs — nothing is invented, and no
positional ordering is guessed at.

### 4.3 Site 5, stated honestly: there is no translation stage

`pipeline.localise` is registered nowhere, and **IVGS has no translation stage at
all** — eight pipeline stages, none of them translation. MBCP's taxonomy has a
`translation` capability; that is MBCP's taxonomy (dev/CLAUDE.md §11.1).

The retry dispatches what does exist: a per-language re-run of the back half
(`current_stage=tts_audio`) carrying the variant's `language_code`, so the target
language's voice is used. **The scene narration is stored once, in the source
language, and nothing translates it.** Recorded as a gap (§11, L-3) rather than
implied to be closed, and the route's docstring says so where a reader will find
it.

### 4.4 Live: Regen, end to end

```
POST /projects/c12fa967/scenes/6c9b010e/regenerate    HTTP 202
  job_type        image_generation   (was storyboard_generation)
  status          running            (was pending, forever)
  celery_task_id  4d2f28e5-d428-4e20-ba5e-6b20cf7ae8ed
```

The orchestrator consumed exactly that task id, fanned out one scene to
`gpu_image` as task `4a3d9554`, and armed the join for 1:

```
media_generation_dispatched  job_id=b3df6eb6 total_scenes=1 image_scenes=1
                             total_tasks=1 expected_stages=['image_generation']
```

node-04 rendered it. **The asset was replaced:**

| asset | bytes | created |
|---|---|---|
| `737238b0` (the old one) | 1,110,642 | 2026-08-23 16:45 |
| **`73c09ab1` (the new one)** | **1,003,507** | **2026-08-25 15:20:33** |

and the join then drained into Stage 4 and Stage 5 exactly as designed — which
is what produced the state advances in §3.2. **The cascade is the ruled
behaviour, not a surprise:** a regenerated scene flows into a fresh manifest and
a fresh draft. Worth knowing before pressing Regen on a live project.

### 4.5 The stranded rows, swept

| Rows | Evidence | Action |
|---|---|---|
| 9 × `storyboard_generation` `pending` | 0 checkpoints, 0 `celery_task_id`, no consumer ever existed | **`failed`**, `completed_at` stamped, `error_message` naming the pre-WP-45 endpoint that created them |
| 1 × `animation_generation` `running` | checkpoint **complete** at 03:45:09; asset `3bc54e58` exists, 796,500 bytes | **`success`** |

**Nothing was deleted.** Every row keeps its id, type, project and `created_at`.

The second row is the one worth pausing on: the brief said "mark
failed/cancelled", and marking it failed would have been a **false record of a
render that succeeded**. WP-46's animation run finished; nothing wrote the
terminal status back, which is precisely what Task 2 fixed. `success` is the
honest status and the `error_message` records why it was set by hand.

---

## 5. TASK 4 — three registries that disagreed

### 5.1 The structural cause, not a bug in either component

`gpu_nodes` has always had zero rows because `register_node`
(`ivgs-workers/utils/gpu_utils.py:418`) posts to **`POST /register` on the
scheduler**, and nothing in `ivgs-workers` has ever called
`POST /api/v1/gpu/nodes`. "GPU Nodes Online" read 0/0 while three GPUs were
alive and working — a faithful read of an empty table.

**Ruled read-through, no sync job.** A periodic copy would give the fleet a
*fourth* registry and a staleness window, in a system that already had three
disagreeing. Two shapes are bridged: a stable UUID5 derived from the scheduler's
node id (so `/gpu/nodes/{uuid}` resolves without anything being stored), and node
names mapped through.

Drain now goes to the scheduler too. It used to set `gpu_nodes.status='draining'`
on a table placement does not read, so **a drained node kept receiving work.**

An unreachable scheduler is a **503 with the reason**, never an empty fleet. That
conflation is the whole reason the old 0/0 looked trustworthy.

### 5.2 Live, on the deployed API

```
GET /api/v1/gpu/utilization
  total_nodes    21          (was 0)
  online_nodes    3
  offline_nodes  18
  total_vram_mb  2,055,627   (was 0)
  used_vram_mb      24,576
  named nodes     0
  unnamed (hex)  21   <- awaiting IVGS_NODE_NAME on each node
```

**The tiles come alive and tell the truth at the same time.** All 21 read
`unnamed (…)` because no node has `IVGS_NODE_NAME` yet, and that is deliberate:
prettifying a hex id would conceal exactly the thing the operator needs to
see — which nodes have had block B1 applied.

### 5.3 (a) The stable node name

The scheduler keys nodes as `{node_hostname}:gpu{index}`, and `node_hostname`
defaulted to the **container's** hostname — a hex id that changes on every
recreate. Hence one registry entry per container the fleet has ever run:
**21 "nodes" on three GPUs.**

`config.py` reads `IVGS_NODE_NAME` first, `IVGS_NODE_HOSTNAME` as a fallback so
an un-updated node does not change identity on upgrade. Blank-safe: `_env`
returns `""` for a set-but-empty variable, which for a node identity is worse
than unset.

**The node `.env` files were NOT edited — I have no SSH to nodes 02–05**
(`Permission denied (publickey,password)` on all four). Block **B1** in
`WP-45-operator-blocks.md` is the whole change, per node, self-gating.

### 5.4 The urgent queue: investigated, proven inert, cleared

Backup first: `dev/workpackages/WP-45-scheduler-queue-backup_20260825-140436.txt`
holds the depths hash, both sorted sets with scores, and every `pq:job:*` hash.

**The queue held 20 entries, not 24 — and the 24 came from a broken counter.**
`get_queue_depths` (`priority_queue.py:302`) reads a `pq:depths` hash maintained
separately from the sorted sets, incremented under `base_priority` and
decremented under `effective_priority`. It had drifted to:

```
pq:depths      urgent 28   normal -6      <- a NEGATIVE count of a thing that cannot be negative
zcard          urgent 20   normal  1
```

and `max(0, …)` in `get_queue_depths` hides the negative from the API. So the
"24 stale entries" in the brief was itself a reading from a broken counter.

**Proof of inertness**, all four independent:

| Check | Result |
|---|---|
| Ages | oldest entry 85 days, newest 10 hours |
| Job status of the 18 that still exist | 4 `success`, 6 `failed`, 8 `running` |
| The 8 "running" | 6 created 2026-06-01/04; **none has an active task** |
| `celery inspect active`, all five workers | **empty on every one** |

Nothing was executing. Cleared: both sorted sets deleted, `pq:depths` reset to
zero. `/fleet` now reports `queue_depth {urgent: 0, normal: 0, batch: 0}`.

**The counter bug itself is NOT fixed.** It lives in `ivgs-scheduler`, pinned at
`v5.0.0-20260522` and outside this package's version set. Ledgered as **P2.46**
with the diagnosis and the one-line fix (read `zcard`, not the hash).

### 5.5 A live observation the read-through exposed

`worker_confirmed_dead` is firing again — 144 times in four minutes — but **this
is not WP-39's bug returning.** That one reported `seconds_since_heartbeat:
1787504720`, the whole Unix epoch. Today it reports `164319` — 1.9 days, a real
age. The supervisor is correctly identifying 18 genuinely-dead registry entries.
The noise is a symptom of the accumulated hex registrations, and block **B2**
retires them. Recorded so it is not misread as a regression.

---

## 6. TASK 5 — two dead columns

`render_jobs.started_at` / `.completed_at` were NULL on all 23 rows on the fleet,
and a grep for either identifier across `ivgs-api`, `ivgs-workers` and `shared/`
found only reads and schema declarations. Nothing had ever written them.

Stamped in **one place** — `JobService.stamp_status_timestamps`, called from
`PATCH /jobs/{id}`, the choke point every worker status change already passes
through — rather than at each of the four sites that move a job.

Three behaviours, each tested:

* `started_at` is not overwritten by a second `running`. A retry re-announces
  it; the duration must be measured from the first start.
* A job that goes straight to terminal keeps a **NULL** start. Recording
  `created_at` as the start would be an invention; NULL says "not measured".
* Cancel stamps a completion.

**Checkpoint-derived duration remains the fallback, as ruled.** These columns
answer the coarser question checkpoints cannot: how long the job took including
the time before the first stage checkpointed. Live: `started_at
2026-08-25T15:18:20.490918Z` on the regeneration job, the first non-NULL value
this column has ever held.

---

## 7. TASK 6 — the riders

### 7(a) `GET /api/v1/jobs`
Live: `total: 32` across all projects, one request. The tracker made 1 + N — 17
per 15-second poll — and sent its state, search and date filters to the
*projects* route, which ignores every one of them, so no filter control did
anything. RBAC matches the project routes: operators see their own projects'
jobs.

### 7(b) `GET /assets/{id}/thumbnail?w=`
Measured on a real asset from the reference project:

```
full-size download :   533,399 bytes
thumbnail   w=320  :     4,635 bytes   (115.1x smaller)
JPEG, 320x180
cache-control: private, max-age=86400
etag: "4261746cd9187bb7c9d217060c49c7a9-w320"
```

Images only; video is a **415 naming the reason** — the API image has no
decoder, and a placeholder that looks like a decoded frame is a lie. PNG out for
sources with alpha, because flattening transparency onto an assumed white
background silently changes what the operator is looking at. The ETag is where
most of the saving is on a re-render. The preview modal deliberately does *not*
request a thumbnail: a preview shows the asset, and a thumbnail is not the asset.

### 7(c) Per-language progress — derived, never stored (D-1)
Computed on every request from that variant's own `pipeline_checkpoints`.

One thing had to exist first: **nothing recorded which language a job was
rendering**, so there was no join from a variant to its checkpoints and the
derivation was impossible for any language. `render_jobs.language_code` is that
attribution — *not* the measure. NULL means the project's source language, which
is what every pre-0028 row is.

The figure collapses worker-granularity checkpoints onto the eight spec stages,
the same collapse the Pipeline Tracker applies: three complete media checkpoints
are **one** complete stage, not three. `progress_percent` is `null` — never `0` —
when there is nothing to measure, and `progress_source` says in words where the
number came from. `0` now means "measured, and nothing has completed", which is
the distinction WP-43 found being conflated beside a language with a finished
720p draft on disk.

### 7(d) `SceneUpdate` extended (D-2, ruled EXTEND)
The five fields the Edit Scene modal has always sent now have columns, a schema
and a route that writes them. The frontend's "Not saved to the server" notices
are **deleted**, because the statement they made stopped being true.

`exclude_unset` is what makes this correct: an omitted key leaves the stored
value alone; an explicit `null` clears it. Under the old fixed signature, "clear
this" and "I did not mention it" both arrived as `None` and neither could be
told from the other. Bounds are inline and worded as the server words its other
refusals (`At most 32 effects per scene`, `An effect identifier cannot be blank`).

### 7(e) Attestation evidence length
`VARCHAR(512) → TEXT`; `attested_by` 128 → 256; schema cap 8192 with an inline
message. WP-46 §A8's vetting reference is **1,912 characters and is a short
one** — it names the certification, the run, the result, the hardware profile,
the measured VRAM and generation time, the engine digest, the graph SHA, the
nine weight bundles and the report that verified them. The old cap forced
whoever pasted it to choose which provenance to delete. `downgrade` **refuses**
rather than truncating if any row exceeds 512.

### 7(f) Project Jobs tab
`RenderJob` declared seven "computed fields added by the API" and the API added
**one**. `current_stage`, `has_checkpoint`, `checkpoint_data`, `assigned_node`,
`assigned_gpu` and `duration_seconds` are not sent by `JobResponse` and never
were — so every row read "—" for stage, "Unassigned" for node and "N/A" for GPU,
and the Resume button could not appear on any job because `has_checkpoint` was
always `undefined`.

They are **deleted from the type**, not guarded. That is WP-40 addendum A6's
established fix: a declared field nothing sends will be read by the next person
who writes a component. Deleting them made the compiler list all nine reads,
which is the point. The tab now shows job id, type, created-at, a real duration
from the columns Task 5 made live, and **"not recorded"** in words where nothing
records the value — "N/A" reads as *"this job used no GPU"* rather than *"nobody
measures this"*.

### 7(g) `storage_quotas` provisioning — RECORDED, not built
`dev/workpackages/WP-45-AD-storage-quota-provisioning_DRAFT.md`. Separates the
two questions that have been discussed as one (who creates the row; who keeps
`current_bytes` true) and recommends **admin-set quotas with derived usage**, for
the reason this package kept meeting: a stored counter drifts, and the
scheduler's own `pq:depths` — found at `urgent 28` against 20 real entries and
`normal −6` — is the cautionary tale sitting in the same repository. Nothing
built, per the brief.

---

## 8. Deploy — `v5.11.0-apibatch`, WP-34 binding rules

### 8.1 Rule by rule

| Rule | Compliance |
|---|---|
| **1** Registry off the deploy path; bank first | Followed. Three artifacts banked, `sha256sum -c` **OK** and `zstd -t` **OK** on all three. **Nothing pushed to GHCR.** |
| **2** Gate image presence before any `.env` write; record rollback tag | Followed. All three image ids confirmed present before the `.env` edit; rollback tags recorded (`v5.10.0-quality`, `v5.9.0-telemetry`, `v5.10.0-quality`); `.env` backed up as `.env.bak-wp45-<ts>`. |
| **3** Label-derived compose, `--force-recreate --no-deps --pull never`, services named | Followed. Compose files and service names read from each container's own `com.docker.compose.*` labels, not guessed. |
| **4** Verify by CONTENT in running containers, never by tag | Followed. §8.3. |
| **5** node-04 `IVGS_LATENTSYNC_TAG` unchanged; engines not recreated | **N/A this session — node-04 was not touched** (no SSH). The check is built into block B1. |
| **6** Never `env \| grep IVGS_`; narrow greps only | Followed (`^IVGS_GPU_SCHEDULER_URL=`, `^IVGS_NODE_(NAME\|HOSTNAME)=`, `^IVGS_(API\|FRONTEND\|WORKERS)_TAG=`). |
| **7** `ivgs-infra/.env*` never committed | Followed. `git status` clean of it throughout; no secret printed in this report or in the session. |

### 8.2 Artifacts banked

| Image | Local id | Artifact sha256 | Size |
|---|---|---|---|
| `ivgs-api:v5.11.0-apibatch` | `d1a1230f2be2` | `ed6f662be0e7094a80dd5bd157809d6fcb821bd5d01e09642930a195fb3486f9` | 120 M |
| `ivgs-frontend:v5.11.0-apibatch` | `f52d00c95794` | `0162fdecba1ec67baa7a633eff4107c4f06698b2cd1102af5fc06b2470102c65` | 56 M |
| `ivgs-workers:v5.11.0-apibatch` | `7e6fc711e977` | `4b3d87acc0a2ff995d26ea65d90643a379190561ea90a6e37b36d0c5fbaf804f` | 313 M |

### 8.3 Content gates — every one a grep INSIDE the image

The API image lays the app out at **`/app/app/`**, not `/app/` — a gate written
against the shorter path returns 0 for every marker and looks exactly like a
missing fix (WP-34 §2.1). Gates written accordingly; all pass.

```
ivgs-api      find_assets_by_hash 1 | claimed_content_hash 1 | find_by_hash 1
              generation_metadata 1 | asset_upload_legacy_hash_field 1
              transition_project_state 1 | _start_stage 3 | reset_after_terminal_failure 1
              regeneration.py present | terminate=True 2 | _send_replay 1
              run_completion 3 | scheduler_fleet.py present | stamp_status_timestamps 2
              list_all_jobs 1 | build_thumbnail 1 | variant_progress 1
              timing_offset_ms 4 | MAX_VETTING_REFERENCE 4 | migration 0028 present
              Pillow 12.2.0 importable
ivgs-workers  find_duplicate_or_none 1 | DuplicateCheckError 1 | asset_storage_path 1
              stage3 params-hash 3 | video params-hash 7 | animation split 1
              audio content_hash 1 | advance_project_state 1
              STAGE_PROJECT_STATE 4 | GATE_PROJECT_STATE 2
              IVGS_NODE_NAME 3 | _first_set 1
```

**Negative gates — the old shapes must be gone.** All three return 0, and none
needed interpretation:

```
= check_duplicate_asset(  in /app/tasks/    0
get("storage_path"        in /app/tasks/    0
"sha256":                 in /app/tasks/    0
```

**Frontend** is a Next.js standalone build, so the gates run against the
compiled bundle:

```
thumbnail?w=            2 files    (present)
api/v1/jobs?per_page    2 files    (present)
"Not saved to the server"  0       (negative, gone)
"not tracked yet"          0       (negative, gone)
"Unassigned"               0       (negative, gone)
```

### 8.4 The deploy, and verification by content in RUNNING containers

Five services recreated on node-01. Postgres, Redis and SeaweedFS untouched
(19 h uptime, confirmed after).

```
ivgs-fastapi              ivgs-api:v5.11.0-apibatch        Up (healthy)
ivgs-nextjs               ivgs-frontend:v5.11.0-apibatch   Up (healthy)
ivgs-celery-default       ivgs-workers:v5.11.0-apibatch    Up (healthy)
ivgs-celery-composition   ivgs-workers:v5.11.0-apibatch    Up (healthy)
ivgs-celery-beat          ivgs-workers:v5.11.0-apibatch    Up (healthy)
```

Routes listed from the **running** API — the four that did not exist:

```
/assets                        ['GET']
/assets/{asset_id}/thumbnail   ['GET']
/jobs                          ['GET']
/projects/{project_id}/state   ['PATCH']
```

### 8.5 Migration 0028, on the live database

Pre-migration `pg_dump -Fc` banked at
`/mnt/ivgs-shared/db-backups/pre-wp45-0028-20260825-151437.dump` (68.8 MB) with
a sha256 beside it. Applied; `alembic_version` reads `0028`; every column
verified present by `\d` on the live database.

**A rollback of the code does not require a rollback of the schema.** 0028 only
adds nullable columns and widens one, and `v5.10.0-quality` neither reads nor
writes any of them.

### 8.6 What was NOT deployed, and why

**Nodes 02, 03, 04, 05 are still on `v5.10.0-quality`.** SSH from this session is
refused on all four (`Permission denied (publickey,password)`), so I could not
reach them. This brief did not carry the explicit per-node hand-over WP-34's did
(its report records an Authorization section naming R1–R7 including the node
deploys), and dev/CLAUDE.md §1 requires that hand-over to be explicit.

**The mixed state is safe, deliberately** — see §2.7 — but it is degraded:
those nodes store no provenance and no params hash, so **dedup cannot hit for
the image, video or animation branches until block B1 is applied.** That is the
single highest-value follow-up in this package.

---

## 9. What is NOT verified

Stated plainly, because an exit code is not proof.

1. **Nodes 02–05 running `v5.11.0-apibatch`.** Not deployed. §8.6.
2. **`IVGS_NODE_NAME` taking effect.** The code path is unit-tested and the
   display mapping is tested, but no node has the variable, so no node has yet
   registered under a real name. Block B1.
3. **Cancel revoking a live GPU task.** The revoke call, its `terminate=True`
   and its `SIGTERM` are asserted against a captured broker control channel, and
   the no-task path is verified live. **A revoke of a genuinely running GPU task
   was not exercised**, because the only running task at the time was the
   operator's own reference-project render and aborting it to make a point was
   not worth the cost. Named as owed rather than implied.
4. **The full back half reaching `USER_REVIEW`.** The regeneration run advanced
   to `AUDIO_GENERATION` and was still in TTS when this report was written. The
   two hops that had never happened before *are* observed (§3.2); the remaining
   three (`TALKING_HEAD_RENDER`, `PROTOTYPE_DRAFT`, `USER_REVIEW`) use the same
   code path and the same map, and are covered by tests, but were not watched to
   completion.
5. **Stage 8 running from the GUI button.** The dispatch is asserted by broker
   message; the button was not pressed in a browser.
6. **Localisation actually producing a translated variant.** It cannot — there
   is no translation stage. §4.3.

---

## 10. Tests

### 10.1 What was added

| Module | Tests | What it pins |
|---|---|---|
| `ivgs-api/tests/test_wp45_dispatch.py` | **31** | a broker message for each of the eight sites; the payload carries the scene's *current* fields; a failed DLQ dispatch leaves the message unresolved; a Jinja error costs no GPU call |
| `ivgs-api/tests/test_wp45_dedup_and_gate.py` | **61** | the probe route is not a 404; hash lookups by both columns; a mismatched hash is refused and the legacy shape is not; dedup hits on identical bytes *and* identical params; the five unreachable states, reached; P1.4q's four guards; timestamps; the fleet read-through and its 503; derived progress; the five scene fields; attestation length |
| `ivgs-workers/tests/test_wp45_dedup_probe.py` | **20** | the three-way answer — hit, clean miss, `DuplicateCheckError`; the fail-open is logged; the two hash kinds ask different questions |
| `ivgs-workers/tests/test_wp45_project_state.py` | **14** | every stage maps to a state; **every hop the map produces is one §6.1 sanctions**; the helper is loud but never fatal |
| `ivgs-frontend/src/lib/__tests__/wp45-scene-fields.test.mjs` | **12** | omitted vs cleared on the wire; the client mirrors the server's bounds; thumbnail width clamped |

**138 new tests, all green.** `npm run test:logic`: **110 passing, 0 failing**
(98 before). Type check and production build both clean.

### 10.2 Six existing tests changed, each because the behaviour changed

Named rather than quietly edited: `test_storyboard` (job_type and status),
`test_service_job` (the cancel message), `test_gpu_api` + `test_service_gpu`
(14 tests reading a table nothing reads any more), `test_video_gen` (patched the
helper by its old name — **and its fixture said `storage_path`, which is the
defect itself sitting in a fixture**).

Three **autouse** conftest fixtures stub the producer, the scheduler and the
model endpoint. Autouse deliberately: opt-in stubbing means the next endpoint
that learns to dispatch silently starts depending on a live broker, and the
failure reads as flakiness rather than a missing stub.

### 10.3 ZERO NEW FAILURES — the before/after diff

The suite is red on `main` independently of this work. Rather than assert a
delta from the headline number, it was established by targeted before/after
comparison against **`d76b355`** in a clean git worktree — WP-44 §8.3's method.

| Sub-tree | `d76b355` | WP-45 tree | Delta |
|---|---|---|---|
| `ivgs-workers` + `ivgs-scheduler` + `tests_system` | **66 failed** | **66 failed** | **0 new.** `comm` over the sorted `FAILED` lists is **empty in both directions** |
| `ivgs-api/tests` | **3 failed**, 719 passed | **2 failed**, 812 passed | **0 new, 1 fixed** |

The one fixed is `test_projects::TestProjectStateMachine::test_valid_transition_draft_to_trigger`,
red on `main` and green here — the autouse producer stub removed its dependency
on a reachable broker.

The two that remain are `test_health.py::test_health_check_success` and
`::test_health_check_no_auth_required`. **Both are red at `d76b355` too**, and
both pass in isolation on both trees — a full-tree ordering artifact, not this
package's.

**Full suite, run 2 of the 2 budgeted:**

```
68 failed, 1578 passed, 63 skipped, 77 errors  (267.68s)
```

Run 1 (`98 failed, 1547 passed`) was taken before the six behaviour-changed
tests were updated; the 26-failure difference between the runs is exactly those
plus the GPU set, and each is accounted for in §10.2.

### 10.4 Environment notes

* The API suite needs `TEST_DATABASE_URL` pointed at `ivgs_reconciliation_test`;
  its guard refuses anything else, correctly. Migration 0028 was applied there
  before the runs.
* Unchanged from WP-32/WP-44: `pytest-timeout` is declared in
  `requirements-dev.txt` and not installed in `.venv`.
* `Pillow==12.2.0` added to `ivgs-api/requirements.txt` for the thumbnail route
  — same pin as `ivgs-workers`, already vetted.

---

## 11. Ledger

**P2.46 — the scheduler's queue depth is not the queue.** `get_queue_depths`
reads a `pq:depths` counter hash maintained independently of the sorted sets it
claims to describe. Measured 2026-08-25: `urgent 28` against a `zcard` of 20, and
`normal −6` — a negative count of a thing that cannot be negative, hidden from
the API by a `max(0, …)`. The one-line fix is to read `zcard` on the three
queues. Lives in `ivgs-scheduler`, pinned at `v5.0.0-20260522` and outside this
package's version set. Data reset; the code is not.

**L-1 — 18 dead node registrations in the scheduler registry.** One per container
the fleet has ever run. Not cleared by this package, deliberately: until block B1
is applied they include the live workers, and the `unnamed (…)` labels are how
the operator sees which nodes still need it. Block B2 retires them afterwards.

**L-2 — `POST /api/v1/gpu/nodes` writes a table nothing reads.** Kept because
`gpu_reservations` still references `gpu_nodes.id`; the route now logs a warning
saying a row written there will not appear on the fleet page.

**L-3 — IVGS has no translation stage.** A localisation retry re-renders the
*source* narration in the target language's voice. §4.3.

**L-4 — the legacy hash-field branch is removable.** When
`asset_upload_legacy_hash_field` stops appearing in the API log, every node is on
`v5.11.0` and the branch is dead code. §2.7.

**WP-00 swallowed-failures register — instance 26**, opened and CLOSED:
`check_duplicate_asset` caught every exception and returned `None`, which its
four call sites read as "no duplicate exists". Closed on observed evidence: the
probe now raises `DuplicateCheckError`, the fail-open is a named decision at one
call site under one greppable event, and the route it calls returns 200 live.

---

## 12. Push block — count-gated, for ALL held commits

**HELD: 8 commits.** Nothing has been pushed.

```
c8214ed  fix(wp-45): a worker still on v5.10.0 must not have its uploads rejected as corrupt
292119c  test(wp-45): a broker message for every one of the eight sites, and what a hash lookup may claim
7a35df5  feat(wp-45): the frontend stops labelling fields as unsaved, and stops reading six that were never sent
80996b9  feat(wp-45): the GPU fleet stops being read from an empty table, and six ruled riders
64e3595  fix(wp-45): eight endpoints that returned 202 and dispatched nothing
33dae3f  feat(wp-45): gate 2 gets its corridor - the state machine gets a caller, and stage 8 gets dispatched
a301dbe  feat(wp-45): dedup was calling a route that was never built, and upload threw the answer away
<this>   docs(wp-45): the report, the operator blocks, and the quota design decision
```

```bash
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs || exit 1
  git fetch origin main && \
  EXPECTED=8 && \
  ACTUAL=$(git rev-list --count origin/main..HEAD) && \
  if [ "$ACTUAL" != "$EXPECTED" ]; then
    echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
    git log --oneline origin/main..HEAD
  else
    git log --oneline origin/main..HEAD && \
    git status --short && \
    git push origin main && \
    echo "PUSHED $ACTUAL commit(s)"
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

If it reports any other number, stop and find out what else is held before
pushing.

---

## 13. Decisions you own

| # | Decision | Recommendation |
|---|---|---|
| **D-1** | **Deploy the workers to nodes 02–05.** Block B1. Until then dedup cannot hit for image, video or animation, and no node registers under a real name. | **Do it.** This is the highest-value follow-up in the package, and it is one self-gating paste per node. Note node-03's service is `cogvideox-worker`, not `celery-worker` (WP-44 §6.3). |
| **D-2** | **Retire the 18 dead scheduler registrations.** Block B2, after B1. | Yes, after B1. It also silences `worker_confirmed_dead`, which is currently firing ~36×/minute on entries that are genuinely dead (§5.5). |
| **D-3** | **P2.46, the scheduler's drifted queue counter.** The data is reset; the code that drifted is in the pinned scheduler image. Fix now, or leave until the scheduler is next rebuilt? | Leave it, and take it with the next scheduler build. It is a one-line change (`zcard`, not the hash) and the data is currently correct. But do not read `queue_depth` as authoritative in the meantime. |
| **D-4** | **`storage_quotas` provisioning.** Design recorded, nothing built, per the brief. Ruling goes in §7 of the draft. | **A + W**: admin-set quotas, derived usage. Reasoning in the document — a stored `current_bytes` is `pq:depths` again, with a bigger blast radius. |
| **D-5** | **The regeneration cascade.** Pressing Regen on one scene re-runs the media join and flows on into a fresh manifest, TTS, talking head and draft. That is the ruled semantics and it is what happened live today. Keep it, or should Regen stop at the media stage? | Keep it. A regenerated scene that never reaches a new draft is a change the operator cannot see. But it is worth a confirmation dialog saying so — the current one says only "Existing generated assets will be replaced". |
| **D-6** | **GHCR push** for `v5.11.0-apibatch`. Banked and deployed, not pushed. | Optional. Rule 1 keeps the registry off the deploy path and the artifacts are verified. |
