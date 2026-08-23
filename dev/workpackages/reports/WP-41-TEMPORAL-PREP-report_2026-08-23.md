# WP-41-TEMPORAL-PREP — the Temporal shadow of the pipeline

| | |
|---|---|
| **Work package** | WP-41-TEMPORAL-PREP |
| **Date** | 2026-08-23 |
| **Repo basis** | `brucecostello2/elearning_v5` @ **`898489c`** (node-01, `main` in sync with `origin/main` at session start) |
| **Authority** | AD-05 **Draft 2, APPROVED 2026-08-22** (`docs/IVGS_v5_Addendum_AD-05_Draft2_Amendment.md`); Draft 1 retained unedited; WP-31 report 2026-08-22 |
| **Nodes touched** | node-01 (repo work, dev worker process) · node-07 = 192.168.1.96 (Temporal **dev** cluster, gRPC 7233 / UI 8080) |
| **Production paths touched** | **None.** No Celery code, no fleet deploy, no `.env` edit, no API, no frontend, no database. |
| **Outcome** | **All five tasks complete.** Nothing blocked. |
| **Commits** | Authored and **HELD**. Operator pushes — §11. |

---

## 0. Executive summary

The eight-stage pipeline now exists as a Temporal workflow, ran end to end on
the node-07 dev cluster with stub activities, survived a `SIGKILL` mid-fan-out
without re-running a single completed activity, and its stage graph conforms to
the checkpoint record of the real run banked this morning.

| Task | Result |
|---|---|
| **1** workflow + activity skeletons | **Done.** 11 modules under `ivgs-workers/temporal_pipeline/`. Eight stages in spec order, both gates as signals, three media branches, retry/timeout policy read off the live Celery tasks, idempotency keys per Draft 2 §6. |
| **2** shadow run on the dev cluster | **Done.** `wp41-shadow-final`: 39 activities, **39 completed exactly once, 0 more than once**, both gates released by signal, 18 scenes across three labelled branches, 10 waves, completed. A second run exercised AD-05 §12 test 4: two forced scene failures drained and the pipeline partial-advanced to the draft with three of five scenes. |
| **3** resume + duplicate delivery | **Done.** Worker `SIGKILL`ed mid-fan-out. Stages 1 and 2 never re-ran. Activity bodies observed executing twice across the ack window; **every repeat converged on the effect that already existed.** Plus a deterministic duplicate-delivery demo and 18 executable tests. |
| **4** conformance vs the reference run | **Done.** `conforms: True` against job `bd99fe37`'s checkpoint record, with both of the record's own gaps asserted **by name and by reason** rather than smoothed over. |
| **5** cutover plan sketch | **Done.** §9, document only. |

**Four things this package found that are worth the operator's attention before
anything else in this report:**

0. **A real race in this package's own idempotency store, found by its own
   test and then measured: 140 of 400 concurrent rounds produced a delivery
   reading a half-written effect record.** Fixed by publishing the effect
   atomically (`os.link`), 0 of 400 after. It is listed first because it is the
   one defect in code this package actually shipped, and because it is the same
   shape as the ones below: a write that looked atomic and was not. §4.2.

1. **The banked reference run still carries WP-39's defect in its data, and the
   conformance test had to be built to see it.** Three media stages executed on
   `bd99fe37`; the checkpoint record holds **two**, and the surviving
   `image_generation` row reports `successful_count: 12` — the *animation*
   count, against a storyboard with 4 image scenes. A conformance test that
   demanded an exact sequence match would fail a correct workflow. §8.

2. **`composition_manifest` can never appear in a checkpoint record at all.**
   The Stage 4 task the orchestrator actually dispatches writes no checkpoint;
   the only write for that stage sits in a task `STAGE_TASK_MAP` does not
   dispatch, and uses `stage_index=4`, which `tts_audio` already occupies. This
   is not new breakage — it is a second, quieter instance of the same family as
   WP-39, and it changes what any future cutover diff can assert. §8.3.

3. **Reading Celery's documented retry default instead of `IVGSBaseTask` would
   have put a 180-second first retry on both LLM stages, where the system uses
   5.** Caught by a test that reads the constants off the live task objects.
   §4.3.

---

## 1. Boundary compliance

| Constraint | Status |
|---|---|
| No production path | **Honoured.** `git status` at commit time shows two new directories and one new file, and nothing else. No file under `ivgs-api/`, `ivgs-scheduler/`, `ivgs-frontend/`, `shared/`, `configs/`, `ivgs-infra/`, or `ivgs-workers/` outside the new module was modified. |
| No Celery code change | **Honoured.** The new package registers no Celery task and is in no `include` list. `celery_app.py` is unmodified. |
| No fleet deploy, no `.env` edit | **Honoured.** Nothing was built, pushed to a registry, or recreated on any node. |
| Shared models imported, never edited | **Honoured.** `models.task_result` is imported for its enums; `payloads.py` **mirrors** the stage models rather than importing them, and a test keeps the mirror exact (§4.4). |
| Python suite must not regress | **Honoured and measured both ways.** §10. |
| Commit and HOLD, never push | **Honoured.** §11 is a count-gated block for the operator. |

**One thing outside the module was created, and it is not in the repo.** The
Temporal SDK is not in `/opt/ivgs/.venv` and was deliberately not added to it:
that venv runs the repo's whole Python suite, and a new dependency there sits
under every existing test for the sake of a package no production path imports.
The shadow runs from **`/home/dev/.venv-ivgs-temporal`** — outside the repo
tree, so it cannot be committed by accident and cannot change what the suite
resolves. The first attempt put it at `/opt/ivgs/.venv-temporal`, which showed
up as untracked in `git status`; it was moved rather than gitignored, because
editing `.gitignore` is outside this package's boundary.

**One change was made on the node-07 cluster: the `dev` namespace was
registered.** It did not exist (only `default` and `temporal-system`), and the
brief specifies the dev namespace. Registration requires a retention period, so
one had to be chosen — see decision **D-2**, §12.

---

## 2. What was read first, and what it changed

Per the brief: AD-05 Draft 1, the Draft 2 amendment, and the WP-31 report,
before any code. Three things from that reading are load-bearing in what
follows, and are recorded because a reader who skips them will misread the
design:

- **Draft 2 §5** — execution order must be **compiled from the storyboard**,
  not hardcoded. "Retrofitting a DAG onto a hardcoded sequence is the same
  lookup-table trap this section removes, one level up."
- **Draft 2 §6** — activities execute **at least once**. WP-31 measured two
  scene bodies running twice across a `SIGKILL`. Every writing activity must be
  idempotent on `(job_id, stage, scene_index)`.
- **Draft 2 §4.5 and O-3** — GPU reservation failure was ruled fatal-with-retry
  **contingent on ledger P2.6**. P2.6 has not landed. §7.4.

---

## 3. Task 1 — module layout

`ivgs-workers/temporal_pipeline/`. Eleven modules, split on one axis that
matters: **six of them import nothing from `temporalio`.**

| Module | Lines | Needs SDK | What |
|---|---:|---|---|
| `dag.py` | 445 | no | `DagNode`, `build_pipeline_dag(storyboard)`, `topological_waves`, `stage_sequence`, `gate_positions` |
| `policies.py` | 358 | no | Retry / timeout / heartbeat per activity, carrying today's Celery constants beside AD-05's targets |
| `idempotency.py` | 337 | no | `(job_id, stage, scene_index)` keys and the effect store |
| `payloads.py` | 818 | no | Activity I/O shapes, mirroring the live stage models |
| `reference_storyboard.py` | 62 | no | The banked 2026-08-23 storyboard as data |
| `conformance.py` | 457 | no | Reference-run loader and comparison |
| `activities.py` | 578 | **yes** | Stub activity bodies |
| `workflow.py` | 647 | **yes** | `VideoPipelineWorkflow` |
| `worker.py` | 134 | **yes** | Dev worker: one worker per AD-05 §4.2 queue, one process |
| `client.py` | 303 | **yes** | start / signal / state / result / history / evidence / export |
| `__init__.py` | 47 | no | The layout, as a docstring |
| `demos/` | 389 | **yes** | Three demonstrations plus shared settings (§6, §7) |
| `README.md` | 92 | — | How to run it |

The split is not tidiness. It means the DAG compiler, the policy table, the key
scheme and the conformance check are **unit-testable in the repo's own venv**,
which has no Temporal SDK in it — so 162 of the 178 new tests run as part of the
ordinary `pytest` invocation and only 16 need the shadow venv.

> **On AD-05's size estimate.** Draft 1 §8 estimates "600–900 lines of workflow
> + activity definitions". `workflow.py` + `activities.py` are **1,225 lines**,
> of which a large fraction is comment: the file that replaces
> `pipeline_orchestrator_v2.py` explains, at each decision, which defect it
> closes. The estimate is not revised here — this is a shadow with stub bodies,
> and the real wrappers will add stage-body calls while `payloads.py` (818
> lines of mirrors) largely disappears in favour of the models themselves.
> Recorded so the number is not quietly discovered later.

### 3.1 The workflow body names no stage

```python
while True:
    nodes   = build_pipeline_dag(scenes, include_final_render=...)
    pending = [w for w in topological_waves(nodes) if w not yet completed]
    if not pending: break
    await asyncio.gather(*[self._execute(inp, node) for node in pending[0]])
    if "s2_storyboard" in this wave:
        scenes = the storyboard Stage 2 produced      # <- THE recompile
```

`_execute` dispatches on `DagNode.kind`: `gate` → `wait_condition`, `fanout` →
`asyncio.gather` over per-scene activities, `activity` → one activity. Adding a
node kind does not change the walker.

The **recompile** is the part worth reading twice. The workflow starts with no
storyboard, so the first compile yields stages 1 and 2 and gate 1 and nothing
else. When Stage 2 returns, the graph is recompiled and the media branches
appear — one per media type the storyboard actually contains. Verified live: in
`wp41-shadow-final` the six-branch-free prelude became a three-branch graph the
moment `generate_storyboard` completed. When AD-07 v2.x carries per-scene
`depends_on`, the change lands in `dag.py` and the workflow body is untouched,
which is Draft 2 §5.3's constraint.

`build_pipeline_dag` is pure: no I/O, no clock, no randomness, no database
(AD-05 §7.1). Every side effect is in `activities.py`.

### 3.2 Three media labels, and the branch table

```python
MEDIA_BRANCHES = (
  MediaBranch("image",      "s3_image",     "image_generation",     "gpu_image", "s3"),
  MediaBranch("video_clip", "s3_video",     "video_generation",     "gpu_video", "s3v"),
  MediaBranch("animation",  "s3_animation", "animation_generation", "gpu_image", "s3a"),
)
```

Order matches `dispatch_media_generation`'s plan loop after the WP-39 fix, so a
printed wave reads the same way a `media_generation_dispatched` log line does.
A branch exists **only if the storyboard contains that media type**, mirroring
the real dispatcher, which sent exactly three tasks for `bd99fe37` because that
storyboard held all three.

### 3.3 Stage numbering is not one thing

`DagNode` carries **two** numbers, because the spec and the database disagree:

| stage | AD-05 §5.1 `spec_stage` | live `pipeline_checkpoints.stage_index` |
|---|---:|---:|
| transcript_refinement | 1 | 1 |
| storyboard_generation | 2 | 2 |
| image / video / animation | 3 | 3 |
| composition_manifest | 4 | **never written** |
| tts_audio | 5 | **4** |
| talking_head_render | 6 | 5 |
| prototype_draft | 7 | 6 |
| final_render | 8 | 7 |

Read off the `save_checkpoint` call sites at HEAD (`stage5_voiceover.py:619,668`
is `stage_index=4`, not 5), not off the spec. The conformance check compares
against a real checkpoint record, so it needs the second column to be true
rather than tidy.

---

## 4. Task 1 — activities, shapes and policy

### 4.1 Twelve activities, eleven of them stubs with real shapes

| Activity | Queue | Idempotency key |
|---|---|---|
| `refine_transcript` | `gpu_llm` | `(job, s1)` |
| `generate_storyboard` | `gpu_llm` | `(job, s2)` |
| `render_scene_image` | `gpu_image` | `(job, s3, scene)` |
| `render_scene_video` | `gpu_video` | `(job, s3v, scene)` |
| `render_scene_animation` | `gpu_image` | `(job, s3a, scene)` |
| `build_composition_manifest` | `default` | `(job, s4)` |
| `generate_voiceover` | `gpu_tts` | `(job, s5)` |
| `render_talking_head` | `gpu_talking_head` | `(job, s6)` |
| `assemble_prototype_draft` | `composition` | `(job, s7)` |
| `render_final` | `composition` | `(job, s8)` |
| `acquire_gpu_reservation` / `release_gpu_reservation` | `default` | `(job, <stage>-gpu)` |

`render_scene_image` and `render_scene_animation` are **two registered activity
names over one implementation**. They genuinely are one Celery task, one queue
and one engine — pretending otherwise would be a lie about the system. What they
no longer share is *identity*: `ActivityContext.label` and
`ActivityContext.idempotency_key` arrive from the `DagNode`, and an activity is
never asked what stage it is. Two names also mean the question "which stage ran"
is answerable from the event history alone, without decoding a payload — the
question WP-39's investigation could not answer for three hours.

Stage 8 is one activity here. AD-05 §5.4's per-segment child workflows are M5
work; Appendix C's "60 m **per segment**" is a per-segment budget and is not
invented early — the whole-stage ceiling applies while the stage is one
activity, and the report says so rather than quietly using the larger number.

### 4.2 The idempotency binding is code, not a paragraph

Every writing activity routes its effect through one function:

```python
def _run_once(ctx, produce):
    outcome = store_for(ctx.job_id).apply(ctx.idempotency_key, produce, attempt=ctx.attempt)
    record_body(ctx.job_id, ctx.idempotency_key, "effect", ctx.attempt,
                created=outcome.created, deliveries=outcome.deliveries, label=ctx.label)
    return outcome.record
```

No wrapper calls `produce` directly. The store's create is
`O_CREAT | O_EXCL`, and delivery counts live in a separate append-only file, so
**"how many times was this delivered" and "how many artifacts exist" are two
independently readable numbers**. WP-31's first evidence script reported a false
PASS over an empty table; a pair of counts cannot be trivially true the way one
can.

**What the store guarantees, precisely, and what it does not.** At most one
effect record per key, and every delivery reads that same record. It does *not*
guarantee the work runs once: under a genuine race two deliveries can both do
the work before either claims the key, and claiming before doing the work would
leave a poisoned claim behind every crash. Duplicated **work** is the
at-least-once property and is unavoidable. Duplicated **artifacts** are the
defect, and are what this prevents. The concurrency test asserts exactly that
and no more.

> **A real bug in that store, found by its own test, and measured.** The first
> write path was the obvious one: `O_CREAT | O_EXCL` on the effect file, then
> write into it. A second delivery arriving between the create and the write
> reads an **empty** file, gets `None` from the JSON decode, tries its own
> create, loses the race, and returns `{}` as "the record that already
> existed". Two deliveries then disagree about what the artifact is — precisely
> the property the class exists to provide.
>
> It surfaced as an intermittent test failure, so it was measured rather than
> reasoned about: 8 concurrent deliveries per key, 400 keys, old path against
> new.
>
> | write path | rounds | two winners | a delivery read an empty record | deliveries disagreed |
> |---|---:|---:|---:|---:|
> | `O_CREAT\|O_EXCL` then write | 400 | 0 | **140** | **140** |
> | temp file → fsync → `os.link` | 400 | 0 | **0** | **0** |
>
> 35% of rounds, on a quiet machine, with an in-memory-cached tmpfs-like path.
> Under a real worker the window is a disk write wide. The fix is atomic
> publication: write a private temp file, fsync it, then `os.link` it into
> place — `link` is atomic and fails if the target exists, so the effect path
> never exists half-written. The test now runs 25 rounds rather than one,
> because a single round on a fast machine may never race.

In production the same `apply` shape takes the stage's own natural key — the
`assets` row on `(project_id, scene_id, asset_type)`, the SeaweedFS object by
`content_hash`, the `pipeline_checkpoints` upsert on `(job_id, stage_name)`.
That last one is itself the WP-39 lesson: **an upsert key is only a natural key
if the identity in it is right.** The animation run wrote under
`image_generation` and overwrote four scenes of image work with twelve scenes of
animation work — one checkpoint for two stages.

### 4.3 Retry policy, and the error the policy test caught

Each policy row carries **both** numbers: what the decorator says at HEAD, and
what the activity gets. Two translations are not identity, and both are stated
rather than smuggled:

- **Attempts.** Celery's `max_retries=N` means N retries *after* the first run.
  Temporal's `maximum_attempts` is the total. Preserving the *behaviour* means
  `maximum_attempts = max_retries + 1`; preserving the literal integer would
  silently delete one execution from every stage. Stage 1 gets **5** attempts,
  not 4.
- **Timeouts.** `start_to_close` comes from Appendix C and is in several places
  more generous than today's `time_limit` — that is §9's point, the ceiling
  relaxes because `heartbeat_timeout` now carries liveness. Today's value is
  kept in the row so the widening is reviewable, and a test asserts
  `start_to_close >= time_limit` so a future edit cannot *tighten* it by
  accident.

> **The error.** The first draft used Celery's documented
> `default_retry_delay` of 180 s for stages 1 and 2, which declare none of their
> own. They do not get 180. `IVGSBaseTask` sets **5** (`celery_app.py:694`),
> along with `retry_backoff = True` and `retry_backoff_max = 300`
> (`:695-696`). A 36× wrong first-retry interval on both LLM stages, from
> reading the docs instead of the base class. It was caught by
> `test_wp41_policies.py`, which reads `max_retries`, `default_retry_delay`,
> `soft_time_limit` and `time_limit` **off the live Celery task objects** and
> compares them to the table. `maximum_interval` is now 300 everywhere,
> preserving `retry_backoff_max`.

### 4.4 The payload mirrors, and the guard that keeps them mirrored

The live stage models are pydantic v2 and live inside modules that import
`celery_app`, `WorkerConfig` and the engine clients. Importing them into a
workflow worker would drag the coordination layer into the thing that replaces
it, and Temporal's default converter does not round-trip pydantic v2 without a
custom converter. So the payloads are plain dataclasses — which the default
converter handles natively — carrying the same field names, defaults and
nesting.

A hand copy rots, so each class declares `_MIRRORS` (`module:ClassName`) and
`_EXTRA` (fields it adds on purpose), and a test imports the real model and
compares the field sets. **29 mirrored shapes, 0 drifted.** A field added to
`SceneImageResult` next month fails a test here rather than being quietly
dropped on the wire.

Two deliberate reshapes, both asserted:

- **Stage 3 mirrors the *scene* model, not the batch.** `Stage3Input` carries
  `scenes: List[SceneImageInput]` and one Celery task renders all of them; under
  AD-05 §5.2 the activity takes one scene. WP-39's join expected three reports
  for eighteen scenes, which is why one mislabelled report stranded twelve
  scenes of finished work. Eighteen scenes are now eighteen activities.
- **`speaker_wav_data` is not `bytes` here.** The live Stage 5 input carries raw
  audio. Temporal stores every activity input in the event history, verbatim,
  for the retention period. The reference travels; the audio does not.

Four shapes have no pydantic pair to mirror and are **named** rather than
silently skipped: Stage 4 takes and returns a raw dict
(`stage4_manifest.py:105, :121-129`), and GPU reservations are a helper call,
not a task.

---

## 5. Task 1 — gates, reservations and versioning

**Both gates are signals** (AD-05 §5.3), and the two AD-05 also requires and
which "neither exists today" are declared: `storyboard_rejected` and
`cancel_job`. `storyboard_rejected` records the rejection and ends the run
rather than looping back to Stage 2 — the regeneration loop is M6 work and is
deliberately not invented here.

**Reservations bracket the node, and release lives in `finally`.** The bracket
is written once, in `_execute`, around whatever the node turns out to be — so a
new node kind cannot arrive without one, and no stage body has a release call
site it can get wrong. That is D4 closed structurally: seven acquires against
three `TypeError`-ing releases was only possible because releasing was something
eight separate files had to remember. One reservation **per node**, not per
scene, which mirrors today exactly (`dispatch_media_generation` sends one task
per media stage and that task acquires once, `stage3_images.py:630`); per-scene
VRAM admission remains `ivgs-scheduler`'s job under §4.2.

**Versioning is adopted on the first workflow written** (§7.2), not
retrofitted: the reservation bracket sits behind
`workflow.patched("wp41-gpu-reservation-bracket")`, and the replay gate §7.2
asks for exists and is proven non-vacuous — §10.2.

---

## 6. Task 2 — the shadow run

Dev worker on **node-01**, connecting to **192.168.1.96:7233**, namespace
**`dev`**. One `Worker` per AD-05 §4.2 queue inside one process — seven queues,
one pid, so the resume demonstration has a single process to kill. Queue names
are AD-05's own, unprefixed.

```
$ ./demo_shadow_run.sh wp41-shadow-final
shadow worker pid=... target=192.168.1.96:7233 namespace=dev
  queues=default,gpu_llm,gpu_image,gpu_video,gpu_tts,gpu_talking_head,composition
```

Started with the **banked 2026-08-23 storyboard**: 18 scenes, 4 image / 12
animation / 2 video_clip — the exact media mix that produced WP-39's lost join.

### 6.1 The run, in the server's own words

```
   7  22:37:04Z  ACTIVITY_TASK_SCHEDULED    acquire_gpu_reservation -> default
  13  22:37:04Z  ACTIVITY_TASK_SCHEDULED    refine_transcript       -> gpu_llm
  19  22:37:06Z  ACTIVITY_TASK_SCHEDULED    release_gpu_reservation -> default
  31  22:37:06Z  ACTIVITY_TASK_SCHEDULED    generate_storyboard     -> gpu_llm
  43  22:37:19Z  WORKFLOW_EXECUTION_SIGNALED   storyboard_approved      <- GATE 1
  47..49         ACTIVITY_TASK_SCHEDULED    acquire_gpu_reservation x3
  59..70         ACTIVITY_TASK_SCHEDULED    render_scene_animation  -> gpu_image   x12
  71..72         ACTIVITY_TASK_SCHEDULED    render_scene_video      -> gpu_video   x2
  73..76         ACTIVITY_TASK_SCHEDULED    render_scene_image      -> gpu_image   x4
 143  22:37:35Z  ACTIVITY_TASK_SCHEDULED    build_composition_manifest -> default
 155  22:37:37Z  ACTIVITY_TASK_SCHEDULED    generate_voiceover      -> gpu_tts
 173  22:37:40Z  ACTIVITY_TASK_SCHEDULED    render_talking_head     -> gpu_talking_head
 185  22:37:43Z  ACTIVITY_TASK_SCHEDULED    assemble_prototype_draft -> composition
 191  22:37:59Z  WORKFLOW_EXECUTION_SIGNALED   draft_approved           <- GATE 2
 201            WORKFLOW_EXECUTION_COMPLETED
```

All eighteen scene activities were scheduled **in one workflow task**, at the
same timestamp. That single burst is the gather.

```json
{ "activity_schedules_total": 39,
  "schedules_completed_exactly_once": 39,
  "schedules_completed_more_than_once": 0,
  "signals_received": ["storyboard_approved", "draft_approved"],
  "activities_by_type": {
      "acquire_gpu_reservation": 7, "release_gpu_reservation": 7,
      "refine_transcript": 1, "generate_storyboard": 1,
      "render_scene_image": 4, "render_scene_video": 2,
      "render_scene_animation": 12,
      "build_composition_manifest": 1, "generate_voiceover": 1,
      "render_talking_head": 1, "assemble_prototype_draft": 1, "render_final": 1 },
  "bodies_executed_total": 32, "bodies_executed_more_than_once": {},
  "effects_total": 25, "effect_keys_delivered_more_than_once": {} }
```

Final workflow state, by query: 12 nodes completed, 10 waves, **three media
labels closed** (`video_generation`, `animation_generation`,
`image_generation`), 18 scenes, 0 failed, `finished: true`.

### 6.2 Why Temporal's join makes WP-39's defect class impossible

WP-39's root cause, restated exactly: `STAGE_TASK_MAP` maps **both**
`image_generation` and `animation_generation` to
`tasks.stage3_images.generate_scene_images_task`. `dispatch_media_generation`
armed one Redis integer with the number of **stages** dispatched (3) and each
completion reported against it through a Lua script guarded by a per-report key,
`ivgs:media_join_seen:{job_id}:{stage}`. The animation run's completion carried
`stage: "image_generation"` — because `Stage3Output.stage` defaulted to a
hardcoded `PipelineStage.IMAGE_GENERATION` and the task never knew which stage
it had been dispatched as — hit the already-set image key, and was dropped as a
duplicate of something it was not. The counter stuck at 1 and no fourth report
could ever exist.

Three independent things here make that unavailable, and it is worth being
precise about which does which:

**1. The join contains no labels at all.** `_fan_out` is a list of activity
handles and one `asyncio.gather`. Completion is matched by the **server**, in
its own event history, from `ActivityTaskCompleted.scheduled_event_id` back to
the `ActivityTaskScheduled` event that created it — an integer event id the
workflow never sees and the payload never carries. Nothing consults a stage
name, so no stage name can collide. This is the structural claim: **the
identity used for the join is created by the server at schedule time and cannot
be supplied, defaulted, or got wrong by the activity.**

**2. The unit is a scene, not a stage.** WP-39's join expected three reports for
eighteen scenes, so one lost report stranded twelve scenes of finished work. In
the run above there were eighteen scene completions, each independently
tracked. A lost one would cost one scene — and cannot be lost, by (1).

**3. The counter is gone.** There is no integer to decrement, so D2's other
half — `_decrement_media_task_count` returning `0` on any Redis exception and
the caller reading `remaining <= 0` as "all media reported" — has no home either.

**What is *not* claimed.** Temporal does not make stage labels unnecessary. The
three labels still exist, in `DagNode.label`, and are still what
`pipeline_checkpoints`, `projects.state` and the UI read. They have simply
stopped being load-bearing for **coordination**. That is the whole difference:
on 2026-08-23 a wrong label lost twelve scenes; here a wrong label would be a
wrong label in a report, and the pipeline would still advance. The three
branches are separate `DagNode`s with separate labels and separate activity
names anyway — belt and braces, and because the labels have to be right for the
*record* even when they no longer gate the *flow*.

### 6.3 Partial-advance is preserved, and was run

AD-05 §5.2 is explicit that a failed scene must drain and the pipeline continue
with a count, exactly as commit `35d9226` does today, and that this must **not**
silently become fail-fast. `_fan_out` uses `return_exceptions=True`, and the
worker's `--fail-scenes` flag exists to exercise it. Run
(`wp41-partial-advance`, 5 scenes, scenes 1 and 3 forced to fail):

```
activity_schedules_total          : 25
schedules_completed_exactly_once  : 23
ACTIVITY_TASK_FAILED in history   :  2
effects_total                     :  9
```

and from the state query:

```
scenes_completed        : 3  (scene 0 image, scene 2 video, scene 4 animation)
scenes_failed           : 2
media_labels_completed  : [image_generation, animation_generation, video_generation]
completed_nodes         : ... s4_manifest, s5_voiceover, s6_talking_head, s7_draft
finished                : true
```

Two failures, not six: the stub failure is raised `non_retryable`, so the retry
policy did not burn three attempts on a deterministic error. The pipeline
advanced past the fan-out with **three of five scenes** and reached the draft —
which is today's behaviour, preserved, and visible in a query rather than
inferred from a log.

---

## 7. Task 3 — resume, and duplicate delivery

### 7.1 The demonstration

`demo_resume.sh`: worker A → start → gate 1 → **`SIGKILL` mid-fan-out** →
worker B → gate 2 → completed. Worker concurrency 2 on GPU queues so an
18-scene fan-out is genuinely in flight when the kill lands (AD-05 §4.2's
production value is 1; the worker defaults to 1 and the demo raises it).

> **A false start, recorded because it produced a plausible non-result.** The
> first run derived the worker pid with `pgrep` and killed a **leftover worker
> from the previous demonstration**. Worker A survived, the workflow finished
> normally, and the evidence would have read as a successful resume across a
> kill that never happened. `start_worker` now returns `$!` — which, thanks to
> an `exec` in the subshell, *is* the worker — and the script refuses to
> continue unless that pid matches the one the worker printed. `stop_worker`
> now waits for processes to actually exit and escalates.

### 7.2 What the server saw, and what actually ran

```json
{ "workflow_id": "wp41-resume-final",
  "activity_schedules_total": 39,
  "schedules_completed_exactly_once": 39,
  "schedules_completed_more_than_once": 0,
  "signals_received": ["storyboard_approved", "draft_approved"],
  "bodies_executed_total": 34,
  "bodies_executed_more_than_once": {
      "wp41-resume-final:s3a:scene2":  2,
      "wp41-resume-final:s3a:scene12": 2 },
  "body_pids_for_repeats": {
      "wp41-resume-final:s3a:scene2":  [2616053, 2616690],
      "wp41-resume-final:s3a:scene12": [2616053, 2616690] },
  "effects_total": 25,
  "effect_keys_delivered_more_than_once": {} }
```

The activities' own fsync'd ledger, written in the worker process and therefore
surviving the process:

```
key                            starts  completes  pids                verdict
wp41-resume-final:s1                1          1  [2616053]           ran exactly once
wp41-resume-final:s2                1          1  [2616053]           ran exactly once
...
wp41-resume-final:s3a:scene2        2          1  [2616053, 2616690]  body ran twice (killed inside the ack window)
wp41-resume-final:s3a:scene12       2          1  [2616053, 2616690]  body ran twice (killed inside the ack window)
...
wp41-resume-final:s8                1          1  [2616690]           ran exactly once
```

`2616053` is worker A; `2616690` is worker B.

The two numbers to read together:

- **Every activity schedule completed exactly once.** The workflow advanced
  exactly once per activity across a worker death. Stages 1 and 2 completed on
  worker A and were **never re-run** — the pipeline did not restart from stage
  1, which is the capability D3 was supposed to provide and never did (AD-05
  §12 test 5).
- **Activity bodies ran more than once.** Those bodies finished their work and
  wrote it to disk, but the worker died before reporting completion to the
  server; on restart the server rescheduled them and worker B ran them again.
  That is correct at-least-once behaviour and exactly what WP-31 Lane C
  measured. **Every repeat converged: `effect_keys_delivered_more_than_once` is
  empty and the effect count equals the number of stage keys.**

### 7.3 The deterministic half

A `SIGKILL` demonstration depends on the kill landing inside the ack window, so
it cannot be the only proof. `demos/demo_duplicate_delivery.py` forces the same
delivery: it calls one activity body **twice with the same `ActivityContext`** —
which is exactly what a worker sees when the server redelivers an activity whose
completion it never heard — and reads the counts back.

```json
{ "idempotency_key": "wp41-duplicate-delivery-demo:s3a:scene4",
  "deliveries": 2,
  "effects_total": 1,
  "first_delivery_artifact":  "stub://…/animation_generation/scene4",
  "second_delivery_artifact": "stub://…/animation_generation/scene4",
  "artifacts_identical": true,
  "stage_label_on_both": ["animation_generation", "animation_generation"],
  "attempt_recorded": [1, 2] }

PASS: two deliveries, one effect, identical artifact, labelled
animation_generation on both.
control: one more scene delivered once -> effects_total=2 (expected 2)
```

The control line matters: without it, `effects_total: 1` would be equally
consistent with a store that never writes anything. Scene 4 of the banked
storyboard is an **animation** scene — the branch whose completion WP-39 lost.

**And as executable tests**, 18 of them in `test_wp41_idempotency.py`, including
the concurrent-delivery case, the "restarted worker sees what the dead one
wrote" case, and the case where image and animation carry the same scene index.
That last cannot arise from one storyboard — a scene has one media type — but it
is the exact shape of WP-39's collision, and a key scheme that permitted it
would be one upstream change away from repeating it.

### 7.4 GPU reservations are fail-open, and this is a ruling being honoured

AD-05 O-3 was **ruled (a) fatal-with-retry** on 2026-08-22, explicitly
"contingent on ledger P2.6 having made the heartbeat registry real by
implementation time. If P2.6 has not landed when Step 4 of §11.2 is reached,
this decision reopens rather than shipping fatal against an empty registry
(`total_nodes:0`), which would fail every GPU stage."

**P2.6 has not landed.** `CLAUDE.md` §7 records, measured under WP-08 on
2026-08-23: the registry still reports `total_nodes:0` and `/fleet` still shows
`queue_depth.urgent:23` stranded requests. The ruling's own contingency
therefore applies, and `GPU_RESERVATION_FAILURE_IS_FATAL = False` keeps today's
deliberate fail-open — but says so out loud, in a place a query and the Web UI
can both see, which D4's version was not for months. A test asserts the flag is
`False` and carries the reason, so flipping it once P2.6 lands is one boolean
and one test edit. This is **decision D-1**, §12.

---

## 8. Task 4 — conformance against the banked reference run

`conformance.py` parses the pg_dump at
`/mnt/ivgs-shared/reference-run-2026-08-23/reference_run_tables.sql`
(`storyboard_scenes`, `assets`, `render_jobs`, `pipeline_checkpoints`), pulls
job **`bd99fe37-0621-40da-aa30-e058cc776c23`** and its project's storyboard,
compiles the workflow graph **from that storyboard**, and compares. Nothing
connects to a database.

```
job bd99fe37-0621-40da-aa30-e058cc776c23 project c12fa967-f989-4ed4-8e20-3ea62cb92e8f
storyboard media mix: {'image': 4, 'video_clip': 2, 'animation': 12}
conforms                    : True
reference stage sequence    : [transcript_refinement, storyboard_generation,
                               image_generation, video_generation,
                               tts_audio, talking_head_render, prototype_draft]
workflow stage sequence     : [transcript_refinement, storyboard_generation,
                               image_generation, video_generation, animation_generation,
                               composition_manifest, tts_audio, talking_head_render,
                               prototype_draft]
spine (media collapsed)     : MATCH
media in reference record   : ['image_generation', 'video_generation']
media in workflow graph     : ['image_generation', 'video_generation', 'animation_generation']
missing from reference      : ['animation_generation']
missing from workflow       : []
gate 1 sits after           : storyboard_generation
gate 1 sits before          : image_generation
gate 1 gap in the real run  : 2500.79 s
gate 2 sits after           : prototype_draft
reference reached final     : False
storyboard media types      : {'image': 4, 'video_clip': 2, 'animation': 12}
media types with no branch  : []
excluded (never checkpointed): ['composition_manifest']
```

### 8.1 The reference record is missing a stage that ran

`bd99fe37` executed **three** media stages. Its checkpoint record holds
**two** — and the surviving row is not the one you would guess:

| stage_index | stage_name | status | window |
|---:|---|---|---|
| 1 | transcript_refinement | complete | 16:00:59 → 16:01:37 |
| 2 | storyboard_generation | complete | 16:01:37 → 16:03:25 |
| | *…41 m 40 s of nothing…* | | **GATE 1** |
| 3 | image_generation | complete | 16:45:05 → 16:46:54 |
| 3 | video_generation | **pending** | 16:47:01 → *(never)* |
| 4 | tts_audio | complete | 18:45:02 → 18:46:19 |
| 5 | talking_head_render | complete | 19:23:07 → 19:23:07 |
| 6 | prototype_draft | complete | 19:23:10 → 19:24:15 |

`pipeline_checkpoints` upserts on `(job_id, stage_name)`. The animation run
reported under `image_generation`, so it **overwrote** the image run's row: the
surviving `image_generation` checkpoint says `"successful_count": 12` against a
storyboard with **4** image scenes and **12** animation scenes. Twelve scenes of
animation work, filed under the wrong stage, on top of four scenes of image
work. The record cannot name a stage that never had a name — and it lost the
one it did have. The `video_generation` row still reading `pending` is the same
defect from the other side: the join never closed, so nothing came back to
complete it.

`test_wp41_conformance.py` asserts all three of those facts directly, from the
dump: the missing label by name, the `successful_count: 12` against 4 image
scenes, and the never-completed video row.

### 8.2 Which means the comparison has to be two-sided

A test demanding an exact sequence match would **fail a correct workflow**. A
test comparing loosely would **bless a record that lost a stage**. So:

- the **spine** — everything outside stage 3 — must match exactly, in order;
- the **media set** must cover every media type **the storyboard contains**;
- both known absences are asserted **by name, with their reasons**, and anything
  else is a failure.

The storyboard check is not decoration. Four negative tests perturb the graph
and confirm the comparison is not vacuous, and one of them is the point: **a
graph with no animation branch at all matches the reference record perfectly** —
same spine, same media set, `missing_from_reference` empty. Only the storyboard
refuses it, because 12 of its 18 scenes are animation. Comparing against the
record alone would have passed the very defect the record is a victim of.

### 8.3 A second, quieter gap: Stage 4 leaves no trace

`composition_manifest` appears in no checkpoint record, on this run or any
other. The Stage 4 task the orchestrator dispatches —
`tasks.stage4_manifest.build_composition_manifest` — contains no `save_checkpoint`
call. The only `composition_manifest` write in the tree is
`pipeline_orchestrator_v2.py:620`, inside a task `STAGE_TASK_MAP` does not
dispatch and which WP-07 F5 records would raise `TypeError` if it ever ran; it
also uses `stage_index=4`, **which `tts_audio` already occupies**.

On this run that is visible as an eight-second hole. WP-39 records the
watchdog's deadline landing at 18:44:54Z; `tts_audio` started at 18:45:02Z. Stage
4 has to have run in that window — TTS needs a locked manifest — but the record
cannot say so.

> **Stated as inference, not measurement.** No log was read for that window in
> this package. What is *measured* is that the dispatched Stage 4 task writes no
> checkpoint, and that the reference record contains no `composition_manifest`
> row.

`UNCHECKPOINTED_STAGES = ("composition_manifest",)` excludes it from the
sequence comparison, with the reason in the module. This is **not** a workaround
for a test that would otherwise fail — including it would fail every real run
forever. It matters to the cutover: **a stage-by-stage diff of a Temporal run
against a Celery run cannot use `pipeline_checkpoints` for Stage 4.** §9.6.

### 8.4 Gate placement, evidenced by the record's own shape

`pipeline_checkpoints` has no row for a gate. The record's only evidence a human
was asked something is the hole in the timeline: **2,500.79 seconds** — 41 m
40 s — between `storyboard_generation` completing and `image_generation`
starting. The test asserts that gap is real, that no media stage started before
the storyboard finished, and that gate 1 sits in the same place in the compiled
graph.

Gate 2 is evidenced by where the run **stopped**:
`render_jobs.resume_from_stage = 'prototype_draft'`, no `final_render`
checkpoint, `prototype_draft` last in the sequence. That is gate 2 holding, and
the graph puts the gate in the same place. Gate positions are computed from the
**full** graph so gate 2 is asserted even on a run that never passed it, while
the sequence comparison uses the truncated graph so an unrun stage is not
counted as a mismatch.

---

## 9. Task 5 — attended M3.3 cutover, sketched (document only)

**Nothing in this section was implemented, and nothing in it should be run
today.** AD-05 §11.1's preconditions still gate it and §12 gates it separately.
This is the shape the attended cutover takes, per §11.2–11.4.

### 9.1 What is true about the fleet, and what it implies

Measured under WP-31 on 2026-08-22, three independent ways (compose profiles, `celery inspect active_queues`, and the running containers read on the nodes). **Not re-measured in this session** — no node other than 01 and 07 was touched:

| Node | Worker | Queues actually consumed |
|---|---|---|
| node-01 | `default-worker@node01` | `default`, `notifications`, `cleanup` |
| node-01 | `composition-worker@node01` | `composition` |
| node-02 | `celery-worker@node02` | `gpu_llm` |
| node-03 | `cogvideox-worker@node03` | `gpu_video` |
| node-04 | `image-worker@node04` | `gpu_image`, `gpu_tts`, `gpu_talking_head` |

Node-02's `gpu_video` worker and node-03's `gpu_llm` worker exist but carry
`profiles: ["standby"]` and have been stopped for two months. **This is the
active/standby pair D1's severity downgrade rests on, and it is one
`--profile standby` away from being wrong.** At cutover, the standby halves must
be brought over too, or explicitly left dead — leaving a *Celery* standby able
to start after Celery is gone is how a half-migration acquires a second
orchestrator.

### 9.2 Rollout order across nodes 02 / 03 / 04

Order is **least-coupled first, and never two GPU capabilities at once**:

| # | Node | Queues | Why here |
|---:|---|---|---|
| 1 | node-01 | `default`, `composition` | No GPU. Stages 4, 7, 8 and the workflow task. If the workflow worker cannot run, nothing else matters — find that out first, on the node you are sitting on. |
| 2 | node-02 | `gpu_llm` | Stages 1 and 2. Shortest activities (soft 120 s), so a mistake surfaces in two minutes, not ninety. Exercises the first gate. |
| 3 | node-04 | `gpu_image`, `gpu_tts`, `gpu_talking_head` | Three capabilities on one host — the widest single step, taken while nodes 01 and 02 are already known good. Exercises the fan-out. |
| 4 | node-03 | `gpu_video` | Last, alone. Longest activity (`start_to_close` 90 m), single active consumer, and the queue D1 lives on. |

Each step: start the Temporal worker, confirm it polls (`temporal task-queue
describe`), stop the corresponding Celery worker, verify with `docker exec … env`
and `docker inspect --format '{{.Config.Image}}'` — **not** by reading a tag
variable out of a container (CLAUDE.md §6).

The standby halves (node-02 `gpu_video`, node-03 `gpu_llm`) are brought up as
Temporal workers in the same step as their active twin, or left down with a
recorded decision. They are **not** left as startable Celery services.

### 9.3 How a Celery-started job drains while Temporal-started jobs begin

**It does not, and that is the design.** AD-05 §11.3: cutover happens in a quiet
window with no in-flight render jobs, and "any job parked at a human gate is
either completed or cancelled before cutover." There is no state transfer
between the two orchestrators and none is being built — a job's position lives
in `render_jobs.stage` plus Redis join keys on one side and in an event history
on the other, and nothing maps between them.

So the concrete drain procedure is the operator's, before the switch:

1. **Stop Beat first.** While Beat runs, `media_join_watchdog` can *advance* a
   stranded job — turning "no in-flight jobs" into "no in-flight jobs, probably".
2. **Let every running stage finish**, or fail it deliberately. The longest
   single stage is 90 minutes (`gpu_video`, `gpu_talking_head`); budget for it.
3. **Resolve every parked gate.** A project in `USER_REVIEW`, or one sitting
   after storyboard generation waiting for approval, is a Celery-shaped job with
   no way home. Approve it through to completion, or cancel it.
4. **Then** flip the flag and start Temporal workers. The first Temporal-started
   job is a *new* job.

The one genuinely dual-path period is **within** §9.2's rollout: between step 2
and step 3, `gpu_llm` is served by Temporal and `gpu_image` still by Celery.
Nothing may be started during that window — the rollout is not a canary, it is a
sequence performed inside the quiet window, and the whole of §9.2 sits between
"quiet window opens" and "first job started".

### 9.4 What "quiet window" concretely requires

Not "no jobs running" by eye. Six checks, all of which must be true, and all of
which are things this package's investigation found can disagree:

1. `SELECT count(*) FROM render_jobs WHERE status IN ('running','pending')` → **0**.
2. No project in a mid-pipeline state: `projects.state` not in
   `TRANSCRIPT_REFINEMENT … PROTOTYPE_DRAFT`, and none in `USER_REVIEW` the
   operator intends to resume. *(`projects.state` is one of the three competing
   truths ledger P2.5 records, and it can be stale in either direction. Treat a
   clean result here as corroboration of check 1, never as proof on its own.)*
3. **No Redis join state**: `ivgs:media_tasks:*` and `ivgs:media_join_seen:*`
   both empty. This is the check WP-39 would have wanted. A surviving
   `media_tasks` key is a half-joined job whose `render_jobs` row may well say
   nothing is wrong — `bd99fe37` sat with `remaining_tasks: 1` for hours while
   its job row looked ordinary.
4. **Celery queues drained**: `celery inspect active` and `reserved` empty on all
   five workers, and the Redis list lengths for all seven queues at 0. Both,
   because `active` says nothing about what is still queued.
5. **Beat stopped**, and confirmed stopped — see §9.3(1).
6. **No `pipeline_checkpoints` row with `status = 'pending'`** for a job you
   think is finished. `bd99fe37` has one right now.

Additionally, and separately from "quiet": **nodes 02/03/04 → node-07:7233 must
be reachable**, which the brief records as verified today (all OPEN). WP-31 left
this untested and flagged it as a pre-step-1 check; it is now met.

### 9.5 Rollback

Rollback is **a flag flip plus a worker restart**, and it stays valid until
§11.2 step 8 — the deletion step. Concretely:

1. Stop the Temporal workers on 01/02/03/04. In-flight Temporal workflows do not
   die; they park, and their event history is intact.
2. Flip the flag back and start the Celery workers and Beat.
3. Any job **started under Temporal** is abandoned, not migrated. Same reason as
   §9.3: there is no mapping. It is re-run from the beginning under Celery.

For this to remain true, **nothing is deleted until §12 passes**: the Celery
coordinator, `celery_app.py`, all stage task registrations, `STAGE_TASK_MAP`,
and the 23 in-stage `send_task` sites stay deployable throughout steps 1–7. The
23 sites are the awkward part — removing them is what makes the workflow own
sequencing, and AD-05 §8 as amended permits exactly those edits and nothing
else. **Rollback therefore requires a build in which those 23 lines still
exist**, i.e. the previous image tag, kept pinned and named in the runbook
before the cutover starts.

Two items that must not be forgotten at step 8, both from Draft 2:

- **Re-home `poll_model_node_availability` before deleting
  `periodic_tasks.py`** (Draft 2 §4.2). It is beat-scheduled every 30 seconds
  and it runs. Deleting the file removes a live poll.
- **`dead_letter_messages` is retained** as the operator audit record (§9);
  only the replay mechanism is replaced.

### 9.6 What the cutover diff can and cannot assert

From §8, and this is the reason that section exists:

- **Can**: the spine, in order, from `pipeline_checkpoints`, plus both gate
  positions from the run's own shape.
- **Cannot, for Stage 4**: `composition_manifest` leaves no checkpoint row on
  either path unless the Temporal wrapper starts writing one. Either the diff
  excludes Stage 4, or the wrapper writes the row the Celery task never did —
  and that is a **new** behaviour, not a preserved one, so it is a decision
  rather than an implementation detail. **D-3**, §12.
- **Cannot, for the 2026-08-23 reference specifically**: the animation branch,
  because the record lost it. A cutover diff against *this* reference must
  compare the Temporal run's three media labels to the **storyboard**, not to
  the record's two.

---

## 10. Tests

### 10.1 New tests

`ivgs-workers/tests/temporal/`, **178 tests in seven files**:

| File | Tests | What it pins |
|---|---:|---|
| `test_wp41_dag.py` | 25 | Ten waves; stage order; three distinct media labels; branches only for media types present; scene indexes partitioned; both gates' placement; cycle / dangling-dep / duplicate-id raise at compile time; the checkpoint `stage_index` map including `tts_audio == 4` |
| `test_wp41_policies.py` | 35 | Every constant against the **live Celery task objects**; attempts = retries + 1; `maximum_interval` = `retry_backoff_max`; `start_to_close` never below today's `time_limit`; every stage heartbeats; queues against `TASK_ROUTES`; the O-3 flag and its reason |
| `test_wp41_idempotency.py` | 18 | Key format and tokens; two deliveries → one effect; deliveries and effects counted separately; **25 rounds of 8 concurrent deliveries converging on one fully-written record**; effect survives a worker restart; image and animation on the same scene index do not collide |
| `test_wp41_payload_shapes.py` | 65 | 29 mirrored shapes, field for field, against the live pydantic models; declared extras exist; the four unmirrored shapes named; the Stage-3 reshape; no `bytes` in an event history |
| `test_wp41_conformance.py` | 19 | The whole of §8, including four negative tests |
| `test_wp41_workflow_shape.py` | 12 | *(SDK)* activity registration; signals and query; retry-policy construction; activity options |
| `test_wp41_replay.py` | 4 | *(SDK)* AD-05 §7.2's replay gate, plus a **divergent workflow that must fail replay** |

**162 run in `/opt/ivgs/.venv`** with no new dependency, as part of the ordinary
`pytest` invocation. **16 need the Temporal SDK** and live in two files that
`pytest.importorskip` it — reported as skips, never as passes, with the reason
naming the venv. Symmetrically, the two files that read the live Celery task
objects skip in the shadow venv, so a whole-directory run is clean in **either**
interpreter. The numbers are in §10.3.

A failure that only means "wrong interpreter" is noise that hides real ones.

### 10.2 The replay gate is real, and proven non-vacuous

AD-05 §7.2 asks for "a replay test against captured histories in CI before any
worker deploy". The captured history of `wp41-shadow-final` (208 KB, 201 events,
both gates, all three media branches) is committed at
`tests/temporal/histories/wp41-shadow-final.json` and replayed against the
current workflow code.

A passing replay test proves nothing if the Replayer is lenient, so the file
also defines a **decoy workflow registered under the same name** that issues one
extra activity before anything else — the ordinary careless edit, "just add a
validation step at the top" — and asserts it raises `NondeterminismError`. It
does. A further test asserts the captured history is a *complete* run worth
replaying: it ends in `WORKFLOW_EXECUTION_COMPLETED`, carries exactly two
signals, and scheduled 4 / 2 / 12 image / video / animation activities.

### 10.3 The new tests, run on their own

Recorded first, because it is the unambiguous number and it needed no database:

| interpreter | command | result |
|---|---|---|
| `/opt/ivgs/.venv` | `pytest ivgs-workers/tests/temporal/` | **162 passed, 2 skipped** — the two files needing the Temporal SDK |
| `/home/dev/.venv-ivgs-temporal` | same | **78 passed, 2 skipped** — the two files needing the live Celery task objects |

**178 distinct tests, every one of them passing in the interpreter it belongs
to.** Neither run touches Postgres, Redis, an engine, or the network beyond the
node-07 history file already on disk.

### 10.4 The repo suite does not regress

Every run below: `TEST_DATABASE_URL` → `ivgs_reconciliation_test` on
`192.168.1.90:5432` (credentials sourced from `ivgs-infra/.env` into an env var,
never printed), `pytest` from the repo root, all four `testpaths`, exit code 0.

| run | tree | failed | passed | skipped | errors | wall |
|---|---|---:|---:|---:|---:|---:|
| **baseline** | `898489c` — **before any file of this package existed** | 74 | 1147 | 15 | 77 | 218.9 s |
| **with the package** | new module + tests present | 74 | **1309** | **17** | 77 | 215.6 s |
| **at HEAD** | after the atomic-write fix and the import cleanup | 74 | 1308 | 17 | **78** | 217.0 s |

**Failures: 74 in all three. Errors: 77 in the first two.** The delta the
package accounts for is `+162 passed, +2 skipped` — exactly the two rows in
§10.3, the 162 that run in the repo venv and the 2 files that skip there.

> **The one discrepancy, run down rather than rounded off.** The third run shows
> **78** errors and one fewer pass. The extra error is
> `ivgs-api/tests/test_api_backup.py::TestListBackupRecords::test_list_backup_records`,
> and it is `asyncpg.exceptions.UniqueViolationError: duplicate key value
> violates unique constraint "users_username_key" — Key
> (username)=(operator_token_user) already exists` **at setup**.
>
> That is a leftover row in the shared test database, not a code change. Two
> full-suite runs briefly overlapped in this session — the suite `TRUNCATE`s
> every table after every test, so two concurrent runs interleave their
> truncations, and one that is stopped mid-test leaves a row behind. Checked
> afterwards: `SELECT count(*) FROM users WHERE username='operator_token_user'`
> in `ivgs_reconciliation_test` returns **0**, so a later test's teardown had
> already cleared it. The test is not in this package, imports nothing from it,
> and passed in the run immediately before.
>
> **This is stated rather than re-measured.** Further full-suite attempts in
> this session were stopped at their timeout; a timeout is not a verdict, and
> repeating a 3.5-minute run to re-observe a database artefact would add
> nothing. The three completed runs above are the evidence.

> **On the 74/77 baseline itself.** Those failures and errors are the
> pre-existing state of this environment, not this package's doing —
> `tests_system/integration` hardcodes `http://localhost:8001` while
> `ivgs-fastapi` publishes only on `192.168.1.90:8001`, so every integration
> fixture errors (WP-40 recorded the same shape, from the same cause). The
> number that matters is the **delta**, and it is measured against a baseline
> taken before any file in this package existed.

---

## 11. Push block — count-gated, for ALL held commits

**Nothing has been pushed.** `main` was in sync with `origin/main` at
`898489c` when this session began, so the two commits below are the only held
ones on this branch.

| # | commit | what |
|---:|---|---|
| 1 | `351ca3f` | `feat(wp-41): the Temporal shadow of the pipeline - workflow, activities, tests` |
| 2 | *this file* | `docs(wp-41): the shadow run, the resume and idempotency proofs, the conformance baseline and the cutover sketch` — its sha is deliberately not quoted here, because a commit cannot contain its own hash |

The block gates on the **count**, so it refuses if another session has committed
to `main` in the meantime rather than pushing that session's work as part of
this one. Plain ASCII, single block, self-gating, no `exit` — a failed gate must
not kill an interactive login shell (CLAUDE.md §5).

```bash
# node-01
cd /opt/ivgs
git fetch origin
BRANCH=$(git rev-parse --abbrev-ref HEAD)
HELD=$(git rev-list --count origin/main..HEAD)
DIRTY=$(git status --porcelain | wc -l)
echo "branch=$BRANCH held=$HELD dirty=$DIRTY"
git log --oneline origin/main..HEAD
if [ "$BRANCH" != "main" ]; then
  echo "REFUSING: on $BRANCH, expected main"
elif [ "$HELD" -ne 2 ]; then
  echo "REFUSING: expected 2 held commits, found $HELD - read the list above before pushing"
elif [ "$DIRTY" -ne 0 ]; then
  echo "REFUSING: working tree is not clean"
  git status --short
else
  git push origin main
fi
```

**What this pushes, and what it does not.** Two commits, all of whose files are
new, under `ivgs-workers/temporal_pipeline/`, `ivgs-workers/tests/temporal/` and
`dev/workpackages/reports/`. No existing file is modified, so there is nothing
to deploy and nothing that changes the behaviour of any running container.
`ivgs-workers` is **not** rebuilt or re-tagged by this package — the new module
would be copied into the image on the next ordinary build and imported by
nothing.

---

## 12. Decisions needed

| # | Decision | What was done, and why | What the operator may want to change |
|---|---|---|---|
| **D-1** | **GPU reservation failure: fatal, or fail-open?** | Kept **fail-open** (`GPU_RESERVATION_FAILURE_IS_FATAL = False`). O-3 was ruled fatal-with-retry *contingent on ledger P2.6*; P2.6 has not landed (`total_nodes:0`, 23 stranded urgent requests, CLAUDE.md §7 as of 2026-08-23). The ruling's own contingency applies. | Nothing, unless P2.6 lands — at which point the flip is one boolean and one test. Flagged so it is not discovered at §11.2 step 4. |
| **D-2** | **Retention on the new `dev` namespace.** | The `dev` namespace did not exist and had to be registered; registration **requires** a retention period. Set to **7 days**. O-4 ruled **90 days**, applied **at M3.3, not now**, with the node-07 cluster "deliberately left at its default" — the `default` namespace **was** left untouched, but a namespace that did not exist has no default to leave. | Ratify 7 days for `dev`, or name a different figure. It is one CLI call to change and holds only shadow-run histories. |
| **D-3** | **Does the Temporal Stage 4 wrapper write a `pipeline_checkpoints` row?** | Not decided here; the shadow writes nothing. Today's Stage 4 writes no checkpoint (§8.3), so preserving behaviour means the cutover diff cannot see Stage 4, and writing one is **new** behaviour. | Decide before §11.2 step 6, because it changes what the verification diff can assert. |
| **D-4** | **Animation's idempotency token.** | Appendix C gives stage 3 one token, `s3`, covering `render_scene_image` / `render_scene_animation` together. Animation was given **`s3a`**. Uniqueness did not require it — a scene has one media type — but a key that cannot say *which* stage produced an artifact is precisely the fact WP-39 destroyed. | Ratify, or fold animation back under `s3`. Ratifying is recommended and costs nothing. |
| **D-5** | **Stage 8's `start_to_close`.** | Appendix C says "60 m **per segment**", which is a budget for the M5 child workflows. Stage 8 is one activity in this shadow, so the **whole-stage** ceiling (60 m) is used and the per-segment figure is not invented early. | Confirm at M5 when the child workflows land. |
| **D-6** | **Where does `temporalio` live when the real wrappers land?** | For this package: a venv **outside the repo** (`/home/dev/.venv-ivgs-temporal`), so the repo suite gains no dependency and nothing can be committed by accident. That does not scale — §11.2 step 2's activity wrappers run inside the `ivgs-workers` image, which means `temporalio` in `ivgs-workers/requirements.txt` and a rebuilt image on nodes 01–04. | Decide when the wrappers are written, not now. Recorded because it is the first item in the next package that is a **deploy**, and this package deliberately contains none. |
| **D-7** | **Delete `dev/spikes/temporal/`?** | Untouched by this package. `dev/CLAUDE.md` §12 (operator ruling 2026-08-22): a spike is "throwaway evidence that proves a property before a design is approved… **Delete it once the design it evidences is built.**" The design it evidenced is what this package builds — DAG compilation, signal gates, resume, at-least-once — all of it now under `temporal_pipeline/` with tests. | The spike is 1,135 lines that now duplicates working code and will drift. Deleting it is the operator's call and outside this package's boundary, so it was not touched. |

---

## 13. Verified live vs inferred

**Verified live** — observed on a running system in this session:

- node-07 reachable from node-01: gRPC `7233` **open**, UI `8080` **HTTP 200**.
- The `dev` namespace did not exist (`describe_namespace` → `Namespace dev is
  not found`) and was registered.
- `wp41-shadow-final`: the complete run, its 201-event history, its 39/39
  exactly-once activity accounting, both signals, and the final query state.
- `wp41-resume-final`: worker A `SIGKILL`ed with the pid it printed, zero
  workers alive afterwards, worker B started, the run completed; the event
  history, the body ledger and the effect store, all three.
- `wp41-partial-advance`: two forced scene failures, 2 `ACTIVITY_TASK_FAILED`
  in the history (not 6 — the failure is non-retryable), 3 of 5 scenes
  completed, and the pipeline running on to the draft.
- The duplicate-delivery demonstration, including its control line.
- Every Celery constant in `policies.py` — read off the live task objects, in
  the test, not copied from a document.
- The reference run's checkpoint record, storyboard, and `render_jobs` row —
  parsed from the banked dump in this session.
- The full Python suite, twice: before any file of this package existed, and
  after.
- The replay gate, both directions: current code replays; a divergent workflow
  raises `NondeterminismError`.

**Inferred, or not verified** — stated as such:

- **That Stage 4 ran on `bd99fe37` in the 18:44:54 → 18:45:02 window.** TTS
  needs a locked manifest, so it must have. No log was read for that window in
  this package. What is *measured* is that the dispatched Stage 4 task writes no
  checkpoint and that the record contains no `composition_manifest` row.
- **Everything about the real stage bodies.** No engine, GPU, API, SeaweedFS or
  pipeline database was touched. Activities are stubs. This package proves the
  *shape* of the workflow, not that any stage still produces the right video.
- **Timings.** Stub activities sleep for seconds. Nothing here measures how the
  design behaves under a 90-minute CogVideoX render, and the heartbeat cadence
  is exercised but not stress-tested.
- **Nodes 02/03/04 → node-07 reachability.** Recorded by the brief as verified
  today (all OPEN). It was **not** re-measured in this session; only node-01 →
  node-07 was.
- **AD-05's 8–14 session and 600–900 line estimates.** Nothing here measures
  them. §3 notes the line count this package actually produced and why it is not
  a revision of the estimate.
- **The Celery touchpoint census (Draft 2 Appendix B, 40 rows).** Used as the
  design input it is. Not re-audited here.

---

## 14. Exit gate

| Requirement | Status |
|---|---|
| Workflow + activity skeletons, 8 stages in spec order, 2 signal gates, AD-05 module layout | **Met** — §3, §4, §5 |
| Activities are stubs carrying real I/O shapes and the WP-31 idempotency scheme | **Met** — §4.1, §4.2, §4.4; 29 mirrors, 0 drifted |
| Retry policies per AD-05 | **Met** — §4.3, verified against the live task objects |
| Shadow run end to end on the dev cluster, with evidence | **Met** — §6 |
| Media fan-out models the three-label join, and the report states how Temporal makes WP-39's class impossible | **Met** — §6.2 |
| Partial-advance preserved (AD-05 §5.2, §12 test 4) | **Met** — §6.3, run live |
| Resume without re-running completed activities | **Met** — §7.2 |
| Duplicate delivery producing one effect | **Met** — §7.2 live, §7.3 deterministic, 18 tests |
| Conformance test against the banked reference run | **Met** — §8, 19 tests |
| Cutover plan sketch | **Met** — §9, document only |
| New tests pass | **Met** — §10.3: 162 in the repo venv, 78 in the shadow venv, 178 distinct, 0 failures |
| Python suite does not regress | **Met** — §10.4: failures 74 → 74, and `+162 passed / +2 skipped` against a baseline taken before any file of this package existed |
| Nothing outside the new module modified | **Met** — §1 |
| Commit and HOLD | **Met** — §11 |

*End of report.*
