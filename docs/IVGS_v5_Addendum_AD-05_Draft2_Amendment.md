# IVGS v5 — AD-05 Amendment: Orchestration Migration, Draft 2

| | |
|---|---|
| **Amends** | `IVGS_v5_Addendum_AD-05_Orchestration_Migration.md` (AD-05, Draft 1 — 2026-08-14) |
| **Addendum version** | **AD-05, Draft 2 — 2026-08-22** |
| **Classification** | Internal Working Document |
| **Change-control status** | **Draft for review (per §18).** Review-board approval is still required before any migration code is written. This amendment exists to make that approval possible, not to grant it. |
| **Authoritative code basis** | `brucecostello2/elearning_v5` @ **`8092cd8`** (node-01 working tree, 36 commits after Draft 1's `e613e844`). Every file:line below re-audited 2026-08-22. |
| **Produced by** | WP-31-TEMPORAL-GROUNDWORK, Lane A. Evidence: `dev/workpackages/reports/WP-31-TEMPORAL-GROUNDWORK-report_2026-08-22.md` |
| **Status of Draft 1** | Retained unchanged alongside this file. Draft 1 is not edited; this amendment carries the corrections. |

---

## 1. Why this amendment exists

Draft 1 was written against `e613e844` and asserted a large number of specific,
checkable facts about the repository: line counts, line numbers, call-site
counts, and claims about which code is reachable. The review board is being
asked to approve an architectural replacement on the strength of those facts.

Lane A of WP-31 checked **every one of them** against HEAD. The result:

| Outcome | Count |
|---|---|
| Confirmed exactly, including line numbers | 9 |
| Confirmed in substance, line references drifted | 11 |
| **Materially wrong — corrected below** | **4** |
| Could not be verified | **0** — the last open item, D1's two-node premise, was measured 2026-08-22 and is §4.5 |

**The architectural case in Draft 1 survives verification.** D1–D4 are all real
at HEAD, the orphaned-code numbers are exact, and the structural argument in
§2.2 is unaffected. The four material corrections do not weaken the case;
one of them (§4.3) strengthens it, and two (§4.2, §4.5) remove arguments the
board should not rely on. **§4.5 is the one that changes a severity rating**:
D1's headline consequence — a duplicate executing concurrently on a second
node — does not hold in the deployed fleet.

Draft 2 also adds two things Draft 1 lacked and the board needs: an explicit
**DAG compilation design** (§5), and a **statement of the idempotency
obligation** the migration creates (§6) — a consequence measured live during
WP-31 Lane C, not inferred.

---

## 2. Change log

| # | Change |
|---|---|
| C-1 | Authoritative basis moved `e613e844` → `8092cd8`; all references re-audited |
| C-2 | §8 line-count table corrected to HEAD; total `~5,541` → **`~5,640`** |
| C-3 | §2.3's "`periodic_tasks.py` … cannot run" claim **withdrawn and replaced** — see §4.2 |
| C-4 | §5.1's "14 `send_task` call sites" corrected to **23** live pipeline-dispatch sites — see §4.3 |
| C-5 | D1–D4 line references updated; D4's third call site corrected |
| C-6 | New §5: DAG compilation design (satisfies the 2026-08-22 design-input line) |
| C-7 | New §6: activity idempotency is now a **binding requirement**, not a note |
| C-8 | New §7: O-1 and O-4 answered with measurement; O-3 restated for decision |
| C-9 | Appendix B: Celery touchpoint census. Appendix C: activity-boundary table |
| C-10 | §4.5 **D1's "node-02 *and* node-03" premise measured and corrected** — it is false as deployed; D1's severity is downgraded accordingly |

---

## 3. Confirmed exactly (no change required)

These Draft 1 claims are correct at HEAD, **including their line numbers**.
The board may rely on them as written.

| Claim | Location at HEAD | Status |
|---|---|---|
| `broker_visibility_timeout = 3600` | `ivgs-workers/config.py:214-215` | exact |
| `time_limit = 3900` on video generation | `ivgs-workers/tasks/video_generation_task.py:445` | exact |
| No `POST /jobs/{id}/checkpoints` write route | `ivgs-api/app/api/v1/checkpoints.py:79,106,137,175` | **all four exact**; the only POST (`:137`) is `resume_pipeline` |
| `release_gpu_reservation` takes one parameter | `ivgs-workers/utils/gpu_utils.py:211` | exact |
| `acquire_gpu_reservation` entry point | `ivgs-workers/utils/gpu_utils.py:126` | exact |
| ~1,957 orphaned lines | 461 + 754 + 742 = **1,957** | exact |
| 14 occurrences of `from ivgs_workers…` | 14 found; **no `ivgs_workers` package exists in the repo** | exact |
| 859 lines of tests over the three inert modules | 236 + 379 + 244 = **859** | exact |
| The live orchestrator has zero tests | no `test_*orchestrator*` file exists | exact |

Two further Draft 1 claims are confirmed in substance and worth recording:

- **`save_checkpoint` is never checked.** `error_handler.py:395` returns `False`
  at `:442` and `:450`. There are **15** call sites across 9 stage files; **not
  one** captures the return value. *(Note: `CLAUDE.md` §7 records "all 5 call
  sites". That figure is wrong — it is 15. Corrected here for the register.)*
- **P2.3's stringly-typed dispatch.** Exactly **four** files register Celery
  names that do not match their filename: `stage5_voiceover.py` →
  `tasks.stage4_voiceover.*` (also the wrong stage number),
  `stage7_prototype_draft.py` → `tasks.prototype_draft_task.*`,
  `stage8_final_render.py` → `tasks.final_render_task.*`, and
  `periodic_tasks.py` → `ivgs_workers.tasks.periodic_tasks.*`.

---

## 4. Material corrections

### 4.1 §8 line counts have drifted (C-2)

Draft 1's arithmetic was internally correct; the code has since grown.

| Module | Draft 1 | HEAD (`8092cd8`) | Δ |
|---|---:|---:|---:|
| `tasks/pipeline_orchestrator_v2.py` | 1,397 | **1,502** | +105 |
| `tasks/pipeline_orchestrator.py` | 655 | 655 | — |
| `tasks/periodic_tasks.py` | 763 | 763 | — |
| `services/dlq_service.py` | 754 | 754 | — |
| `services/retry_engine.py` | 461 | 461 | — |
| `utils/error_handler.py` | 450 | 450 | — |
| `celery_app.py` | 648 | **642** | −6 |
| `checkpoints.py` + `checkpoint_service.py` | 413 | 413 (199 + 214) | — |
| **Total** | **5,541** | **5,640** | **+99** |

The estimate of 600–900 lines of replacement workflow/activity code is
unchanged; Draft 2 does not revise it, because nothing measured in WP-31
bears on it. **It remains an estimate and the board should treat it as one.**

### 4.2 WITHDRAWN: "`periodic_tasks.py` … cannot run" (C-3)

> Draft 1 §2.3: *"This is why `periodic_tasks.py` is dormant: it cannot run."*

**This is wrong, and the board should not rely on it.** Measured at HEAD:

- `periodic_tasks` **is** in the Celery include list (`celery_app.py:330`), so
  it is imported at worker boot.
- Its module-level imports are clean (`structlog`, `celery`, `celery.schedules`
  — `periodic_tasks.py:29-38`). The broken `from ivgs_workers…` imports are
  **lazy**, inside task bodies.
- One of its tasks **is** live: `poll_model_node_availability` is beat-scheduled
  every 30 s (`celery_app.py:208-212`) and its body imports only `httpx` and
  the local `config` module. It runs.
- All **eight** beat entries resolve to registered task names. None is a dead
  dispatch today.

**Replacement text.** `periodic_tasks.py` is a *duplicate* implementation of
six operational tasks. The beat schedule dispatches five of them via
`pipeline_orchestrator.py`'s copies instead; those five `periodic_tasks`
variants are unscheduled and would raise `ModuleNotFoundError` on first
execution if anything ever dispatched them. It is latent dead weight, not
unreachable code.

**Why this matters to the decision.** The disposition is unchanged —
`periodic_tasks.py` is still deleted, and O-5 (Schedules, not a minimal Beat)
is still right. But the board is being told a subsystem is provably dead when
part of it is in production every 30 seconds. That distinction matters at
cutover: **deleting `periodic_tasks.py` without first re-homing
`poll_model_node_availability` removes a live 30-second poll.** Draft 1 would
have let that pass unnoticed. It is added to §11.2 step 5 as an explicit item.

### 4.3 UNDERCOUNT: "the 14 `send_task` call sites" (C-4)

Draft 1 §5.1 says `VideoPipelineWorkflow` replaces "the 14 `send_task` call
sites." At HEAD there are **23** live pipeline-dispatch sites:

| File | Sites | Lines |
|---|---:|---|
| `tasks/pipeline_orchestrator_v2.py` | 8 | 204, 332, 461, 482, 503, 634, 712, 1167 |
| `tasks/pipeline_orchestrator.py` | 2 | 167, 294 |
| `tasks/talking_head_task.py` | 3 | 378, 755, 891 |
| `tasks/stage4_manifest.py` | 2 | 128, 156 |
| `tasks/stage7_prototype_draft.py` | 2 | 474, 585 |
| `tasks/stage1_transcript.py` | 1 | 724 |
| `tasks/stage2_storyboard.py` | 1 | 735 |
| `tasks/stage3_images.py` | 1 | 757 |
| `tasks/stage5_voiceover.py` | 1 | 676 |
| `tasks/stage8_final_render.py` | 1 | 761 |
| `tasks/video_generation_task.py` | 1 | 576 |
| **Total** | **23** | |

Excluded: 2 backup-dispatch sites in `ivgs-api/app/api/v1/backup.py` (out of
scope), 1 DLQ replay site (`services/dlq_service.py:324`, orphaned), all test
doubles, and all commented-out sites.

**Why this matters.** Only 10 of the 23 are in the orchestrator modules. The
other **13 sit inside the eight stage bodies** — the code §8 declares
"preserved, effectively untouched." Each is a stage task reaching directly
into the coordination layer to dispatch its own successor. Every one must be
removed for the workflow to own sequencing, which means the migration **does**
edit stage files, at 13 sites, in direct tension with §8's stop-rule.

This is not a reason to reject the migration. It is a reason to state the
boundary precisely, so that a migration session hitting the eleventh of these
does not read §8's "if you find yourself editing stage internals, stop" and
either stop wrongly or quietly widen scope. **§8 is amended** to read
(wording **accepted by the operator 2026-08-22**, WP-31 ruling D-6; pre-ruled
as checklist item A-4):

> Removing a stage body's trailing `send_task` dispatch (23 sites, enumerated
> in AD-05 Draft 2 §4.3) is **in scope** and is the only permitted edit to a
> stage file. Any other change to stage internals means scope control has been
> lost — stop.

### 4.4 Drifted line references (C-5)

Substance confirmed; locations moved. Corrected for the board's use:

| Draft 1 reference | Corrected at HEAD |
|---|---|
| `talking_head_task.py:284` (`time_limit`) | `:335` (`:334` soft) |
| `celery_app.py:293` (`task_acks_late`) | `:288` (`:293` is `task_soft_time_limit`) |
| `pipeline_orchestrator_v2.py:869-880` (`_decrement_media_task_count`) | `:974` |
| `pipeline_orchestrator_v2.py:856-951` (Redis join helpers) | `:961-1058` |
| `pipeline_orchestrator_v2.py:955-1060` (join watchdog) | `:1060-1191` |
| `pipeline_orchestrator_v2.py:637-708` (`_handle_media_generation_completion`) | `:661` |
| `pipeline_orchestrator_v2.py:231-350` (`handle_stage_completion`) | `:236` (decorator) / `:241` (def) |
| `pipeline_orchestrator_v2.py:355-400` (`dispatch_media_generation`) | `:363` / `:368` |
| `error_handler.py:409,435-441` (`save_checkpoint`) | def `:395`; `return False` at `:442`, `:450` |
| `celery_app.py:182-220` (beat schedule) | `:176-216` |
| `project_service.py:402` (Gate 1 dispatch) | `:446` |
| `project_service.py:300-309` (pipeline trigger) | `:244` (def) / `:334` (dispatch) |
| **D4:** `talking_head_task.py:543` | **`:884`** — `:543` is not a release site |

**D4 detail.** `release_gpu_reservation(reservation_id)` takes one parameter
(`gpu_utils.py:211`). Three call sites pass two and would raise `TypeError`:
`video_generation_task.py:540`, `talking_head_task.py:699`,
`talking_head_task.py:884`. A **fourth** site Draft 1 does not mention —
`celery_app.py:601` — passes one argument and is correct. Acquire sites number
**seven**, not eight: `stage1_transcript.py:517`, `stage2_storyboard.py:537`,
`stage3_images.py:630`, `stage5_voiceover.py:551`,
`video_generation_task.py:478`, `talking_head_task.py:449`, `:701`.

So the asymmetry is **7 acquires against 3 broken releases and 1 working one**,
not 8 against 3. The defect is real and the argument is unchanged.

> **This resolves a standing contradiction.** `CLAUDE.md` §7 records the D4
> signature drift as "UNVERIFIED and contradictory", against
> `OUTSTANDING_WORK.md:293`'s note that it does not reproduce on the deployed
> image. Both can be true: **it reproduces in source at HEAD** — verified
> above, by reading the signature and all four call sites. Whether the
> *deployed image* differs from HEAD is a separate question and is **not**
> resolved here. No call site was executed.

### 4.5 CORRECTED: D1's "node-02 **and** node-03" premise is false as deployed (C-10)

> Draft 1 D1: *"`gpu_video` is consumed by node-02 **and** node-03, so the
> duplicate can execute **concurrently on the other node**."*

**Measured 2026-08-22**, fleet-wide, from the running workers' own
`celery inspect active_queues` self-report against the live broker — five
workers online:

| Worker | Queues actually consumed |
|---|---|
| `default-worker@node01` | `default`, `notifications`, `cleanup` |
| `composition-worker@node01` | `composition` |
| `celery-worker@node02` | **`gpu_llm`** |
| `cogvideox-worker@node03` | **`gpu_video`** |
| `image-worker@node04` | `gpu_image`, `gpu_tts`, `gpu_talking_head` |

**Exactly one worker consumes `gpu_video`, and it is node-03. Node-02 does
not.**

Confirmed **three independent ways**, which is why this correction is stated
flatly rather than hedged:

1. **Repo configuration.** Node-02 defines a `gpu_video` worker
   (`ivgs-infra/docker-compose.node02.yml:126`, `-n cogvideox-worker@node02`)
   but it carries `profiles: ["standby"]` (`:95`). Symmetrically, node-03's
   `gpu_llm` worker is the standby half (`docker-compose.node03.yml:160`).
2. **Broker self-report.** The `active_queues` table above — the workers'
   own answer, not an inference.
3. **The running containers, read on the nodes themselves** (read-only,
   `root@192.168.1.91` / `.92`, 2026-08-22):

```
node-02  ivgs-celery-node02             Up (healthy)
         celery -A celery_app worker --queues=gpu_llm   --concurrency=2 -n celery-worker@node02
         ivgs-cogvideox-worker          Exited (0) 2 months ago      <- the gpu_video worker

node-03  ivgs-cogvideox-worker-node03   Up (healthy)
         celery -A celery_app worker --queues=gpu_video --concurrency=1 -n cogvideox-worker@node03
         ivgs-celery-node03             Exited (0) 2 months ago      <- the gpu_llm worker
```

The pair is **active/standby, not two concurrent consumers**, and the standby
halves have been down for two months.

**What survives, and what does not:**

- **Survives.** The redelivery defect is real and unchanged:
  `broker_visibility_timeout = 3600` (`config.py:214-215`) sits below
  `time_limit = 3900` (`video_generation_task.py:445`) with
  `task_acks_late = True` (`celery_app.py:288`). A video task running past
  3600 s **is** redelivered and **will** execute twice.
- **Does not survive.** The *concurrency* claim. With one active consumer at
  `--concurrency=1`, the duplicate is serialised behind the original on the
  same worker — bad, but not two GPUs rendering the same scene at once.

**D1's severity is therefore lower than Draft 1 states**, and the board should
be told so before approving on the strength of it. The defect remains
correctness-critical; its blast radius does not include cross-node concurrent
execution **in the current configuration**.

> **The premise becomes true the moment anyone starts node-02's `standby`
> profile.** Two workers would then consume `gpu_video`, and D1 would read
> exactly as written. This is a live latent hazard, not a retired one, and it
> is one `--profile standby` away. It is precisely the class of failure §2.2(1)
> describes: correctness resting on a pre-guessed timeout plus a deployment
> detail nobody re-checks.

---

## 5. DAG compilation design *(new — satisfies the 2026-08-22 design input)*

Draft 1 §5.1 carries the design-input line requiring that the workflow support
compiling the storyboard into an explicit dependency DAG rather than
hardcoding the stage sequence. This section is that design. It was built and
executed as a working spike during WP-31 Lane C
(`dev/spikes/temporal/pipeline_dag.py`, `workflow.py`).

### 5.1 The shape

Execution order is **data**, not control flow. A node declares its
dependencies; a pure function compiles nodes into ordered parallel groups; the
workflow body walks the groups. The workflow body names no stage.

```
DagNode(id, label, kind, queue, depends_on, ...)
    kind ∈ { activity, fanout, gate }

topological_waves(nodes) -> [[DagNode]]     # pure, deterministic, testable
    wave N contains every node whose dependencies are satisfied by waves < N
    raises on a cycle rather than deadlocking at await time

for wave in waves:
    await asyncio.gather(*[execute(node) for node in wave])
```

`execute` dispatches on `kind`: `activity` → one activity; `fanout` → one
activity per scene under `asyncio.gather`; `gate` → `workflow.wait_condition`
on a signal. Adding a node kind does not change the walker.

### 5.2 What this buys, concretely

- **Cycles are caught at compile time**, before any activity is scheduled — a
  `ValueError` naming the offending nodes, not a workflow hung on an await.
- **Parallelism is discovered, not declared.** Any two nodes without a
  dependency path between them land in the same wave and run concurrently. No
  one has to remember to parallelise them.
- **The v2.x extension is a data change.** When AD-07 v2.x carries per-scene
  `depends_on`, the storyboard compiles to `DagNode`s and
  `topological_waves` consumes them. **The workflow body does not change.**
- **It is testable without Temporal.** `topological_waves` is pure. Wave
  structure gets unit tests; the 1,502-line orchestrator has none today.

### 5.3 The constraint Draft 1 imposed is met

> *"The design must not require the v2.x fields to exist yet."*

It does not. The current flat scene list compiles to a single `fanout` node
whose scenes have no dependencies on each other — which is exactly today's
behaviour. Per-scene `depends_on` fields, when they arrive, expand that one
node into several waves. **Nothing in the workflow body is conditional on
which contract version produced the graph.**

Verified live: the spike's DAG compiles to 10 waves, executed end to end on
the node-07 cluster, including both gates and a six-scene fan-out.

---

## 6. Activity idempotency is a binding requirement *(new)*

Draft 1 §5.2 states that D2 "becomes structurally impossible" under Temporal.
That is true of D2 *as written* — the Redis counter is gone. It is important
that the board not read it as "idempotency stops being our problem."

**Measured on node-07, 2026-08-22** (WP-31 Lane C, ledger + event history):

> A worker was SIGKILLed during the scene fan-out. Two scene activities had
> finished their work and written their completion to disk, but the worker died
> before reporting completion to the server. On restart, **the server
> rescheduled both, and both bodies executed a second time.** Every activity
> whose completion had reached the server was **not** re-run, and the workflow
> did not restart from stage 1.

This is correct, documented Temporal behaviour. The guarantee is that the
**workflow** advances exactly once; **activities execute at least once.** The
window is small and it is real, and it is exactly the window in which a
non-idempotent activity does its damage twice.

**Therefore, binding on the migration:**

1. Every activity that writes — SeaweedFS objects, database rows, rendered
   files — MUST be idempotent on `(job_id, stage, scene_index)`. Rendering
   the same scene twice must converge, not duplicate.
2. Activity wrappers MUST NOT assume single execution. Any "increment",
   "append", or "insert" is suspect and needs a natural key or an upsert.
3. The §12 verification gate gains a test: **kill a worker mid-fan-out and
   assert the artifact set is identical to the uninterrupted run.** Test 5 as
   written proves resume; it does not prove the resume produced clean output.

This obligation is smaller than today's — one property, provable per activity,
rather than a bespoke join guard per fan-out — but it is not zero, and Draft 1
does not say so.

---

## 7. Open decisions revisited

| # | Draft 1 status | Draft 2 |
|---|---|---|
| **O-1** | persistence: node-01 Postgres or local? | **Answered: local.** Provisioned and running on node-07 with its own `postgres:17.11-alpine` and its own volume. Node-01's Postgres is untouched, and the ledger P1.9 SPOF is not extended. Recommend the board ratify this as decided. |
| **O-2** | one workflow, or parent + per-stage children? | **Unchanged: single workflow**, children only for segment fan-out. The Lane C spike ran the whole eight-stage graph as one workflow; final history was 71 events / 10,683 bytes for a 6-scene run — well inside comfortable bounds. |
| **O-3** | should GPU reservation failure be fatal? | **RULED 2026-08-22 (operator): (a) fatal-with-retry** — explicitly **contingent on ledger P2.6 having made the heartbeat registry real by implementation time.** If P2.6 has not landed when Step 4 of §11.2 is reached, this decision reopens rather than shipping fatal against an empty registry (`total_nodes:0`), which would fail every GPU stage. Pre-ruled as checklist item A-8. |
| **O-4** | event-history retention period | **RULED 2026-08-22 (operator): 90 days.** Applied as configuration at **M3.3, not now** — the node-07 dev cluster is deliberately left at its default. Measurement supporting the choice: a 6-scene shadow run with two gates produced 71 events / ~10.4 KB, i.e. kilobytes per job. 90 days is comfortably affordable. |
| **O-5** | Schedules, or a minimal Beat? | **Unchanged: Schedules.** §4.2 adds the migration item this implies: re-home `poll_model_node_availability` before deleting `periodic_tasks.py`. |

---

## Appendix B — Celery touchpoint census

Every place the orchestration layer touches Celery/Redis semantics, at
`8092cd8`, with its Temporal replacement.

| # | Touchpoint | file:line | Replaced by |
|---|---|---|---|
| 1 | Broker URL (Redis) | `config.py:209-210` | Temporal service address; Redis ceases to be the broker |
| 2 | `broker_visibility_timeout = 3600` (**D1**) | `config.py:214-215` | **Deleted** — `heartbeat_timeout` on each activity |
| 3 | `broker_transport_options` | `celery_app.py:247-252` | Deleted |
| 4 | Result backend (Postgres) | `celery_app.py:274-275` | Deleted — activity results live in event history |
| 5 | `task_acks_late = True` | `celery_app.py:288` | Deleted — server-side task ownership |
| 6 | `worker_prefetch_multiplier = 1` | `celery_app.py:289` | `max_concurrent_activities=1` on GPU queues |
| 7 | `task_reject_on_worker_lost = True` | `celery_app.py:290` | Deleted — native, non-optional |
| 8 | `task_time_limit` / `task_soft_time_limit` | `celery_app.py:292-293` | `start_to_close_timeout` per activity |
| 9 | 7 `Queue()` definitions | `celery_app.py:52-103` | 7 Temporal task queues (§4.2), names preserved |
| 10 | `TASK_ROUTES` (name-glob routing) | `celery_app.py:118-175` | Deleted — queue is an argument at call site |
| 11 | `CELERY_BEAT_SCHEDULE`, 8 entries | `celery_app.py:176-216` | Temporal Schedules (O-5) |
| 12 | Celery include list | `celery_app.py:318-331` | Worker registration lists |
| 13 | `STAGE_TRANSITIONS` | `pipeline_orchestrator_v2.py:57` | **Deleted** — `depends_on` in the DAG (§5) |
| 14 | `STAGE_TASK_MAP` (**P2.3**) | `pipeline_orchestrator_v2.py:90` | **Deleted** — direct function references |
| 15 | `STAGE_QUEUE_MAP` | `pipeline_orchestrator_v2.py:124` | `DagNode.queue` |
| 16 | `dispatch_pipeline` | `pipeline_orchestrator_v2.py:152` | `client.start_workflow` |
| 17 | `handle_stage_completion` | `pipeline_orchestrator_v2.py:236-241` | **Deleted** — control flow returns |
| 18 | `dispatch_media_generation` (fan-out) | `pipeline_orchestrator_v2.py:363-368` | `asyncio.gather` over activity handles |
| 19 | 3 media-type dispatch branches | `pipeline_orchestrator_v2.py:461,482,503` | `fanout` node kind |
| 20 | `_handle_media_generation_completion` | `pipeline_orchestrator_v2.py:661` | **Deleted** — the gather returns |
| 21 | `_store_media_task_count` | `pipeline_orchestrator_v2.py:961` | **Deleted** |
| 22 | `_decrement_media_task_count` (**D2**) | `pipeline_orchestrator_v2.py:974` | **Deleted** |
| 23 | `_record_media_failure` | `pipeline_orchestrator_v2.py:988` | `return_exceptions=True` |
| 24 | `_get_media_failure_count` | `pipeline_orchestrator_v2.py:1001` | `len([e for e in settled if isinstance(e, Exception)])` |
| 25 | `_store_media_join_context` | `pipeline_orchestrator_v2.py:1013` | **Deleted** — context is a local variable |
| 26 | `_get_media_join_context` | `pipeline_orchestrator_v2.py:1030` | **Deleted** |
| 27 | `_cleanup_media_join_keys` | `pipeline_orchestrator_v2.py:1045` | **Deleted** — no keys to clean |
| 28 | `media_join_watchdog` + its beat entry | `pipeline_orchestrator_v2.py:1060-1191`; `celery_app.py:213-216` | **Deleted** — compensating code for a missing durable join |
| 29 | `save_checkpoint` (**D3**, 15 unchecked call sites) | `error_handler.py:395-450` | **Deleted** — event history |
| 30 | Checkpoint API (no write route) | `checkpoints.py:79,106,137,175` | `@workflow.query` |
| 31 | `RetryEngine` (orphaned) | `services/retry_engine.py` (461) | `RetryPolicy` |
| 32 | `DLQService` (orphaned) | `services/dlq_service.py` (754) | Failed workflow, resettable |
| 33 | `FallbackChain` (orphaned) | `services/fallback_chain.py` (742) | L1→L4 selection extracted; plumbing deleted |
| 34 | Per-task retry decorator constants | 8 stage files (see Appendix C) | `RetryPolicy` per activity, values preserved |
| 35 | `acquire`/`release_gpu_reservation` (**D4**) | `gpu_utils.py:126,211`; 7 + 4 call sites | Bracketing activities, release in `finally` |
| 36 | 23 in-stage `send_task` dispatches | §4.3 table | **Deleted** — see amended §8 |
| 37 | Gate 1 dispatch | `project_service.py:446` | `signal storyboard_approved` |
| 38 | Pipeline trigger | `project_service.py:334` | `client.start_workflow` |
| 39 | `run_backup_verification` stub (`{'status':'ok'}`) | `pipeline_orchestrator.py:616-622` | Schedule + a real check, or delete |
| 40 | `poll_model_node_availability` (**live**, 30 s) | `periodic_tasks.py:718`; `celery_app.py:208-212` | Temporal Schedule — **must be re-homed before deletion (§4.2)** |

---

## Appendix C — Activity boundaries, stage by stage

Real signatures at `8092cd8`. Every stage task has the identical shape
`(self: IVGSBaseTask, task_input_dict: Dict[str, Any]) -> Dict[str, Any]`,
with the typed dataclass reconstructed inside the body — so the activity
wrapper is mechanical and the typed input can move to the signature where it
belongs.

| Stage | Registered name (file:line) | Queue | Today's limits | Proposed activity | Timeouts / heartbeat | Idempotency key |
|---|---|---|---|---|---|---|
| 1 | `tasks.stage1_transcript.refine_transcript_task` (`stage1_transcript.py:430`) | `gpu_llm` | retries 4, soft 120, hard 150 | `refine_transcript(TranscriptRefinementInput) -> RefinedTranscript` | s2c 5 m, hb 30 s | `(job_id, "s1")` |
| 2 | `tasks.stage2_storyboard.generate_storyboard_task` (`stage2_storyboard.py:451`) | `gpu_llm` | retries 4, soft 120, hard 150 | `generate_storyboard(StoryboardGenerationInput) -> Storyboard` | s2c 5 m, hb 30 s | `(job_id, "s2")` |
| 3 | `tasks.stage3_images.generate_scene_images_task` (`stage3_images.py:560`) | `gpu_image` | retries 2, soft 1800, hard 2100 | `render_scene_image(Stage3Input, scene_index) -> SceneMedia` | s2c 45 m, hb 60 s | `(job_id, "s3", scene_index)` |
| 3 | `tasks.video_generation_task.generate_video_clips` (`video_generation_task.py:440`) | `gpu_video` | retries 2, soft 3600, hard **3900** (**D1**) | `render_scene_video(VideoGenerationInput, scene_index) -> SceneMedia` | s2c 90 m, hb 60 s | `(job_id, "s3v", scene_index)` |
| 4 | `tasks.stage4_manifest.build_composition_manifest` (`stage4_manifest.py:83`) | `default` | retries 2, delay 30 | `build_composition_manifest(job_id, project_id) -> Manifest` | s2c 10 m, hb 30 s | `(job_id, "s4")` — manifest is locked server-side |
| 5 | `tasks.stage4_voiceover.generate_voiceover_task` ⚠ **name/file mismatch** (`stage5_voiceover.py:493`) | `gpu_tts` | retries 3, delay 10, soft 900, hard 1200 | `generate_voiceover(Stage4Input) -> VoiceoverBundle` | s2c 30 m, hb 60 s | `(job_id, "s5")` |
| 6 | `tasks.talking_head_task.render_talking_head` (`talking_head_task.py:330`) | `gpu_talking_head` | retries 2, delay 30, soft 3600, hard **3900** (**D1**) | `render_talking_head(Stage6Input) -> HeadRender` | s2c 90 m, hb 60 s | `(job_id, "s6")` |
| 7 | `tasks.prototype_draft_task.assemble_prototype_draft` ⚠ **mismatch** (`stage7_prototype_draft.py:311`) | `composition` | retries 2, delay 30, soft 900, hard 960 | `assemble_prototype_draft(Stage7Input) -> Draft` | s2c 30 m, hb 60 s | `(job_id, "s7")` |
| 8 | `tasks.final_render_task.render_final` ⚠ **mismatch** (`stage8_final_render.py:342`) | `composition` | retries 2 | `plan_segments` → `render_segment`* → `concat_and_finalize` | s2c 60 m/segment, hb 60 s | `(job_id, "s8", segment_index)` |
| — | `gpu_utils.acquire_gpu_reservation` (`:126`) / `release_gpu_reservation` (`:211`) | per stage | — | bracketing activities, release in `finally` | s2c 60 s, no hb | reservation id |

*\* one child workflow per segment (§5.4). `services/segment_planner.py` (264
lines) is preserved as-is and called from `plan_segments`.*

**Stage 6 remains gated on ORCH-6** (ledger P1.0), unchanged from Draft 1.

**The three ⚠ mismatches disappear at migration**, because the workflow holds
a direct function reference. That is P2.3's entire defect class, closed
structurally rather than by renaming files.

---

*AD-05 Draft 2 — 2026-08-22 (revised same day with operator rulings D-1…D-6;
§4.5 rewritten from measurement, O-3 and O-4 ruled, §8 amendment accepted).
Status: **awaiting review-board approval per §18.**
No migration code may be written before approval. WP-31 wrote none: its spike
code lives in `dev/spikes/temporal/`, imports nothing from IVGS, and is
evidence rather than foundation.*
