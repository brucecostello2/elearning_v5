# IVGS v5 — Functional Specification Addendum AD-05: Orchestration Migration

| | |
|---|---|
| **Addendum to** | IVGS v5.0 Functional Specification (§2.1 Architectural Pattern, §6.2 Operational Layer, §6.4 Celery Task Orchestration) |
| **Addendum version** | **AD-05, Draft 1 — 2026-08-14** |
| **Classification** | Internal Working Document |
| **Change-control status** | **Draft for review (per §18).** Replacing the orchestration layer is an architectural amendment. Review-board approval is required **before any migration code is written.** |
| **Decision** | Replace the hand-rolled Celery coordination layer with **Temporal** durable execution. Engine rationale and rejected alternatives: **ADR-005**. |
| **Depends on** | Master Sequence Plan **v0.4** (M3); `OUTSTANDING_WORK.md` **v4.0** (P0.1, P1.1–P1.3, P2.1–P2.3); AD-01 (model binding); AD-02 Draft 3 (fleet topology); AD-03 (composition fidelity) |
| **Authoritative code basis** | `brucecostello2/elearning_v5` @ **`e613e844`** — node-01 and `origin/main` in exact sync. All file:line references audited 2026-08-14. |
| **Supersedes** | Functional spec §6.4 in full; §6.2 in part (checkpoints, retries, timeouts, heartbeat supervision, idempotency); §2.1's orchestration layer |

---

## 1. Purpose and scope

This addendum specifies the replacement of IVGS's pipeline coordination layer. It defines what is replaced, what is preserved, the target workflow design, the migration and rollback procedure, and the verification gate.

**In scope.** Stage sequencing and dispatch; the media fan-out and join; user gates; checkpointing and resume; retry, timeout and liveness policy; dead-letter handling; pipeline state truthfulness; periodic operational tasks.

**Explicitly out of scope.** The eight stage bodies and their engine clients; `ivgs-scheduler` (VRAM-aware admission control); the API; the frontend; the database schema; the MBCP seam; the Model Store. §8 makes this boundary binding.

**This addendum does not address pipeline output quality.** M1's items (ORCH-6 head-model binding, Stage-8 validation, frame-aligned splitting) are unaffected and must close first.

---

## 2. Why — the structural case

### 2.1 Four live correctness defects

Verified at `e613e844` (ledger P0.1, P1.1–P1.3):

| # | Defect | Evidence |
|---|---|---|
| **D1** | `broker_visibility_timeout = 3600` sits below `time_limit = 3900` on two tasks. With `task_acks_late = True`, Redis redelivers while the original still runs. `gpu_video` is consumed by node-02 **and** node-03, so the duplicate can execute **concurrently on the other node**. | `config.py:214-215`; `talking_head_task.py:284`; `video_generation_task.py:445`; `celery_app.py:293` |
| **D2** | `_decrement_media_task_count` returns `0` on any Redis exception; the caller reads `remaining <= 0` as "all media reported." A single transient error advances the pipeline with incomplete footage. No idempotency: the completion callback fires before the ack, so a requeue double-decrements. | `pipeline_orchestrator_v2.py:869-880`, `:672`; `stage3_images.py:736-741`; `video_generation_task.py:574-580` |
| **D3** | No `POST /jobs/{id}/checkpoints` route exists. `save_checkpoint` returns `False`; no call site checks it. Nothing is ever written, so `POST /resume` resumes from an empty table. | `error_handler.py:409,435-441`; `checkpoints.py:79,106,137,175` |
| **D4** | `release_gpu_reservation(reservation_id)` takes one parameter; all three call sites pass two → `TypeError`. Eight acquire sites against three release attempts; all acquires fail open. | `gpu_utils.py:211`; `talking_head_task.py:543,699`; `video_generation_task.py:540` |

D1–D4 are fixed under Master Plan **M2**, independently of this migration — a working system is required *while* migrating. They are recorded here because they are **instances**, and §2.2 explains why instances will keep recurring.

### 2.2 Three limits that cannot be fixed in place

1. **No liveness signal.** Redis-as-broker offers only a pre-guessed visibility timeout. D1 is fixed by raising a number; the next workload that exceeds the new number reintroduces it. At M5's 30-minute target this is a permanent tuning exercise against durations not yet run.
2. **At-least-once delivery, hand-guarded.** Every fan-out needs its own idempotency guard, written correctly, forever. D2 is one instance; Stage 8's segment render and M5's parallel talking-head fan-out will each need their own.
3. **Per-stage crash recovery.** Checkpointing is eight separate designs kept in sync as stages change. D3 shows the decay mode: the entire subsystem has been silently dead for months without detection.

Every remaining milestone pushes on exactly these. **M4** adds five nodes; **M5** multiplies runtimes tenfold and adds two new fan-outs.

### 2.3 Dead weight and inverted assurance

- **~1,957 lines orphaned.** `RetryEngine` (461), `DLQService` (754), `FallbackChain` (742) are imported by no stage task. They cross-reference each other only in docstrings, and their lazy imports name a package that does not exist in the repo — **14 occurrences** of `from ivgs_workers…`, which would `ModuleNotFoundError` on first execution. This is why `periodic_tasks.py` is dormant: it cannot run.
- **Test coverage is inverted.** 859 lines of tests cover those three inert modules; the 1,397-line live orchestrator has **zero**.
- **Stringly-typed dispatch.** `STAGE_TASK_MAP` resolves the next stage by string. Four files register names that do not match their filenames (ledger P2.3), each a runtime-only `next_stage_task_not_registered` that no static check catches.

### 2.4 The cost comparison

The alternative is **not** "do nothing." It is finishing the bespoke layer: wiring the three orphaned services into eight stage tasks, building the checkpoint write path and resume semantics, join idempotency, orchestrator tests, plus the still-unwritten `render_segments` resume and parallel talking-head fan-out — approximately **9–13 sessions**, yielding machinery that is structurally weaker and maintained by one operator.

The migration is approximately **8–14 sessions**, deletes ~5,200 lines net, and turns the last two items into child workflows.

Midpoints are close. **Risk shapes differ:** the bespoke path's uncertainty sits at the end and is unbounded discovery work; the migration's sits at the front and is bounded, estimable work. For a single operator that difference decides it.

---

## 3. Decision

**Temporal**, self-hosted, on a dedicated node. Full rationale, alternatives (DBOS Transact, Hatchet, Prefect, Celery Canvas) and rejection reasons: **ADR-005**.

Two constraints shaped the choice and are recorded here:

- **Not on node-01.** 8 vCPU / 16 GB already runs ~13 services and is the ledger P1.9 SPOF. A dedicated node is provisioned (Master Plan M3.2). *If that becomes unavailable, DBOS Transact — library-only, no new server, durable state in the existing Postgres — is the resource-respecting fallback and requires reopening this decision.*
- **The Web UI is a deciding feature, not a bonus.** M5's central problem is observing what happened during a multi-hour run. Execution history and a run-inspection UI are the capability that collapses the test-iteration loop.

**Rejected interim:** swapping Redis for RabbitMQ to obtain a real liveness signal. Sound in isolation, but throwaway once the migration is committed, and pre-migration testing stays short enough that D1's config fix suffices. *(Redis is retained as cache and heartbeat store; it ceases to be the pipeline broker.)*

---

## 4. Target architecture

### 4.1 Topology

| Component | Host | Notes |
|---|---|---|
| Temporal server + Web UI | **new dedicated node** | Persists to a dedicated database on node-01's Postgres 17, or a local instance if event-history write load warrants — decide at M3.2 with measurement |
| Temporal workers (workflow + activity) | node-01 … node-06 | Co-resident with today's Celery workers during transition; replace them at cutover |
| `ivgs-scheduler` | node-01 | **Unchanged.** Called from an activity |
| Redis | node-01 | Retained as cache and heartbeat store; **no longer the pipeline broker** |
| Celery + Beat | node-01 | Removed at cutover; retained flag-gated until §12 verification passes |

### 4.2 Task queues

One queue per capability, mirroring today's routing (spec Table 6-7) so node specialization under AD-02 Draft 3 is preserved: `default`, `gpu_llm`, `gpu_image`, `gpu_video`, `gpu_tts`, `gpu_talking_head`, `composition`.

Per-worker activity concurrency of 1 on GPU queues preserves the current `worker_prefetch_multiplier = 1` guarantee. **This is serialization, not admission control** — VRAM-aware bin packing across heterogeneous cards remains `ivgs-scheduler`'s job.

---

## 5. Workflow design

### 5.1 One workflow per render job

`VideoPipelineWorkflow(project_id, job_id, options)` — the entire eight-stage sequence as a single durable function. It replaces `STAGE_TRANSITIONS`, `STAGE_TASK_MAP`, `STAGE_QUEUE_MAP`, `handle_stage_completion`, and the 14 `send_task` call sites.

```
1  refined     = await refine_transcript(...)                   # gpu_llm
2  storyboard  = await generate_storyboard(refined)             # gpu_llm
   ── GATE 1 ── await workflow.wait_condition(storyboard_approved)
3  media       = await asyncio.gather(*[                        # fan-out
                    render_scene_media(s) for s in scenes])     # gpu_image | gpu_video
4  manifest    = await build_composition_manifest(media)        # default
5  audio       = await generate_voiceover(manifest)             # gpu_tts
6  head        = await render_talking_head(audio, manifest)     # gpu_talking_head
7  draft       = await assemble_prototype_draft(head, manifest) # composition
   ── GATE 2 ── await workflow.wait_condition(draft_approved)
8  final       = await render_final(draft, manifest)            # composition
```

Stage order, queue routing and gate placement are unchanged from spec §6.1. What changes is that sequencing is **expressed as control flow** rather than as a lookup table — so a mis-referenced stage is an import-time error, eliminating ledger P2.3's entire defect class.

**Design input, added 2026-08-22 (ledger P2.32 context).** The workflow design MUST support compiling the storyboard into an **explicit dependency DAG** — per-scene `depends_on` and parallel groups — rather than hardcoding the stage sequence shown above. The listing is the *current* shape, not the contract: once scenes can declare dependencies on one another, execution order is derived from the storyboard rather than fixed in the workflow body. Design for that now; retrofitting a DAG onto a hardcoded sequence is the same lookup-table trap this section removes, one level up.

### 5.2 Media fan-out (replaces the Redis join)

`asyncio.gather()` over per-scene activity handles. This deletes:

- `_store_media_task_count`, `_decrement_media_task_count`, `_record_media_failure`, `_get_media_failure_count`, `_store_media_join_context`, `_get_media_join_context`, `_cleanup_media_join_keys` (`pipeline_orchestrator_v2.py:856-951`)
- `media_join_watchdog` and its Beat schedule (`:955-1060`) — compensating code that exists only because Celery has no durable join
- `_handle_media_generation_completion` (`:637-708`)

**D2 becomes structurally impossible:** there is no counter to mis-read and no "unknown" that can be mistaken for "complete."

**Partial-advance is preserved.** Today a failed scene drains and the pipeline continues with `failed_count` (commit `35d9226`). Equivalent: `asyncio.gather(..., return_exceptions=True)`, then apply the same policy explicitly. *This behaviour is deliberate — do not silently convert it to fail-fast.*

### 5.3 Human gates (replaces the state-machine guards)

Both gates become signals:

| Gate | Today | Target |
|---|---|---|
| Storyboard review | `POST /scenes/approve` → `dispatch_media_generation` (`project_service.py:402`) | `signal storyboard_approved(edits)` |
| Draft review | `user_review` → Stage-8 dispatch | `signal draft_approved()` |

The workflow blocks at `wait_condition` for as long as the operator takes — days is normal, not exceptional. This removes the "deliberately lenient `approve_storyboard` guard" that the e2e currently depends on (ledger P2.5), because there is no state machine to guard: the workflow is either at the gate or it is not.

**Also required:** `signal storyboard_rejected` / `regenerate` for the M6 UI flow, and `signal cancel_job` for operator abort — neither exists today.

### 5.4 Segment render as child workflows *(M5)*

Stage 8's segment render and M5's parallel talking-head fan-out become **child workflows, one per segment**, each with its own retry policy and heartbeating.

`services/segment_planner.py` (264 lines) is preserved as-is and called from an activity; only the *execution* of its plan moves. The `render_segments` table becomes an operator-facing record rather than the resume mechanism.

**This is where the migration pays for itself twice.** Both fan-outs are currently unwritten and both are specced to require bespoke durable machinery (`render_segments` resume, `/jobs/{id}/segments`, and inevitably another watchdog). Under this design they are `asyncio.gather` over child workflow handles.

---

## 6. Activity boundaries

An activity is a unit of work that may fail and be retried independently, may perform I/O, and heartbeats while running. Stage bodies become activities essentially unchanged.

| Stage | Activity | Queue | External I/O |
|---|---|---|---|
| 1 | `refine_transcript` | `gpu_llm` | vLLM; Pipeline API |
| 2 | `generate_storyboard` | `gpu_llm` | vLLM; Pipeline API |
| 3 | `render_scene_image` / `render_scene_animation` | `gpu_image` | FLUX/ComfyUI; vLLM; SeaweedFS via API |
| 3 | `render_scene_video` | `gpu_video` | CogVideoX / Wan2.1; vLLM |
| 4 | `build_composition_manifest` | `default` | Pipeline API (server-side build) |
| 5 | `generate_voiceover` | `gpu_tts` | Coqui XTTS / Kokoro; vLLM |
| 6 | `render_talking_head` | `gpu_talking_head` | **Provider-resolved engine** (post-ORCH-6); ffmpeg |
| 7 | `assemble_prototype_draft` | `composition` | ffmpeg; Remotion; CaptionService |
| 8 | `plan_segments` → `render_segment`* → `concat_and_finalize` | `composition` | SegmentPlanner; ffmpeg; Remotion |
| — | `acquire_gpu_reservation` / `release_gpu_reservation` | per stage | `ivgs-scheduler` |

*\* one child workflow per segment.*

**Stage 6 must be migrated post-ORCH-6.** Migrating the current hardcoded-LatentSync implementation would carry ledger P1.0 into the new architecture. Sequence: close ORCH-6 under M1, then migrate.

**GPU reservations** become explicit acquire/release activities bracketing each GPU stage, with release in the workflow's `finally` — which structurally fixes D4's 8-acquire/3-release asymmetry. Whether reservation failure is fatal is an open decision (§15, O-3).

---

## 7. Determinism and versioning

**This is the principal new engineering discipline and the most common way teams are hurt.**

### 7.1 Determinism

Workflow code must be replayable. It may not perform I/O, read the clock, use randomness, or query the database. Concretely, the following must move from orchestrator code into activities:

- `_build_stage_input` (`pipeline_orchestrator_v2.py`) — reads config and prior stage output
- AD-03 Pillar-1 duration anchoring — derives scene durations from real audio
- `fallback_policies` lookups — a database read

The workflow reduces to pure control flow. **This is a refactor, not an annotation.**

### 7.2 Versioning

Multi-hour renders plus multi-day human gates mean workflows will **always** be in flight during a deploy. Versioning is therefore mandatory from day one, not an eventual concern.

- Every workflow-logic change ships behind `workflow.patched()` / worker versioning.
- Deploys never assume an empty workflow set.
- A replay test runs against captured histories in CI before any worker deploy.

**Adopt this on the first workflow written**, not retrofitted. Retrofitting versioning after in-flight jobs exist is the failure mode.

---

## 8. Scope boundary *(binding)*

**Replace** — the coordination layer only:

| Module | Lines | Disposition |
|---|---:|---|
| `tasks/pipeline_orchestrator_v2.py` | 1,397 | Replaced by workflow definitions |
| `tasks/pipeline_orchestrator.py` | 655 | Removed (periodic tasks → Temporal Schedules) |
| `tasks/periodic_tasks.py` | 763 | Deleted (dormant; broken imports) |
| `services/dlq_service.py` | 754 | Deleted |
| `services/retry_engine.py` | 461 | Deleted (retry becomes declarative) |
| `utils/error_handler.py` | 450 | Reduced — checkpoint machinery deleted |
| `celery_app.py` | 648 | Removed at cutover |
| `api/v1/checkpoints.py` + `services/checkpoint_service.py` | 413 | Replaced by workflow queries |
| **Total** | **~5,541** | **→ est. 600–900 lines of workflow + activity definitions** |

**Preserve, effectively untouched** — the eight stage bodies and their supporting services (~25,000 lines). This is June's hard-won domain knowledge: the reconstructed Jinja templates, `WAVE_FORMAT_EXTENSIBLE` handling, scene linkage, AD-03 duration anchoring and Pillar-2 overlay, the ffmpeg composition logic, `quality_validator`, `segment_planner`, all engine clients. Each gets a thin activity wrapper.

**Keep entirely** — `ivgs-scheduler`, the API, the frontend, the database schema, the MBCP seam, the Model Store.

**`services/fallback_chain.py` (742 lines)** is a special case: its L1→L4 *strategy selection* is domain logic and must be extracted and wired in regardless of engine choice; only its retry/DLQ plumbing is displaced.

> **If a migration session finds itself editing stage internals, stop.** Scope control has been lost. This is the difference between a ten-session migration and a six-month sinkhole.

---

## 9. Retry, timeout and liveness *(replaces §6.2 and Tables 6-4, 6-5)*

Retry policy becomes declarative per activity, enforced by the server, visible in the UI. Spec Table 6-4's per-stage attempts and backoff sequences map directly and are **preserved as values**, not redesigned.

| Concept | Today | Target |
|---|---|---|
| Max attempts + backoff | Decorator constants across 8 files + unwired `RetryEngine` | `RetryPolicy(initial_interval, backoff_coefficient, maximum_attempts)` per activity |
| Per-model timeouts (Table 6-5) | Static `soft_time_limit` / `time_limit` | `start_to_close_timeout` |
| **Liveness** | Guessed `visibility_timeout` (**D1**) | `heartbeat_timeout` + activity heartbeats |
| Non-retriable failures | Ad-hoc `isinstance` checks | `non_retryable_error_types` |
| Exhaustion → DLQ | `DLQService` (unwired) | Failed workflow, visible in UI, resettable to any point |

**Heartbeating is the key change.** A long render is *long*, not suspicious; a hung one fails fast. This removes the permanent tuning exercise described in §2.2(1). Long-running activities (CogVideoX, LatentSync, ffmpeg segments) must heartbeat — this is a requirement on the activity wrapper, not optional.

**The `dead_letter_messages` table is retained** as the operator audit record. Only the replay *mechanism* is replaced.

---

## 10. State and observability

| Concern | Today | Target |
|---|---|---|
| Pipeline state | Three competing truths: `projects.state` (stale — ledger P2.5), `render_jobs.stage`, live task inspection | `@workflow.query` — the workflow's own state, truthful by construction |
| Crash recovery | `pipeline_checkpoints` + resume (**D3: never written**) | Event history — recovery is the default, not a feature |
| Run inspection | Log files | Temporal Web UI: full event history, inputs/outputs, retries, timings |
| Progress for UI | Polling `render_jobs` | Query + signal; live progress without polling |

`projects.state` is **retained** as a denormalized read model for the dashboard, written from the workflow — not as the source of truth. This closes ledger P2.5 without fixing it twice; the guard tightening happens here.

---

## 11. Migration plan

### 11.1 Preconditions (all mandatory)

1. **M1 closed** — ORCH-6 done, Stage 8 validated, reference output banked (§12).
2. **M2 closed** — D1–D4 fixed; a working system exists to migrate *from*.
3. **AD-05 approved** by the review board (§18).
4. **Temporal node provisioned** and reachable from all fleet nodes.

### 11.2 Sequence — one arc, all eight stages

| Step | Work |
|---|---|
| 1 | Stand up Temporal server + UI + Postgres schema; verify from every node |
| 2 | Author `VideoPipelineWorkflow` + activity wrappers for all 8 stages; replay test in CI |
| 3 | Wire the two gate signals; API approval endpoints signal the workflow instead of `send_task` |
| 4 | Wire `ivgs-scheduler` acquire/release as bracketing activities with `finally` release |
| 5 | Convert Beat schedules → Temporal Schedules (heartbeat supervision, orphan cleanup, retention, backup verification) |
| 6 | Run the full pipeline on a short job behind the flag; diff against the §12 reference |
| 7 | Cut over: Temporal path default, Celery path flag-gated |
| 8 | After a clean verified run, delete the Celery coordinator and the ~1,957 orphaned lines; retire ledger P0.1, P1.1–P1.2, P2.1–P2.3 together |

**No long-term coexistence.** Per Master Plan principle #7, the flag exists for rollback during verification, not as an architecture. The v1→v2 orchestrator migration — half-done since June (ledger P2.3) — is the precedent being avoided.

### 11.3 In-flight jobs at cutover

Cutover occurs during a **quiet window with no in-flight render jobs.** IVGS is single-operator with no external traffic, so this is arranged, not engineered — which removes the dual-path complexity a live-traffic system would require. Any job parked at a human gate is either completed or cancelled before cutover.

### 11.4 Rollback

Rollback is a flag flip plus a worker restart, valid until step 8. The Celery coordinator, `celery_app.py`, and all stage task registrations remain intact and deployable throughout steps 1–7. **Do not delete anything until §12 passes.**

---

## 12. Verification gate

The migration is verified against a **known-good reference output** captured under M1:

1. Same project, same inputs, same model selections.
2. The new path produces a final render matching the reference on: total duration (±1 frame), resolution, framerate, audio sample rate and channels, scene count, corruption checks, and head placement/sync.
3. Both human gates block and release correctly.
4. A deliberately failed scene drains and partial-advances, matching current `failed_count` behaviour.
5. A deliberately killed worker mid-stage resumes without re-running completed stages — **the capability D3 was supposed to provide and never did.**

Test 5 is the one that proves the migration was worth doing.

---

## 13. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Half-migration | **High** | §11.2 one arc; flag-gate for rollback only; §12 before any deletion |
| Scope creep into stage bodies | **High** | §8 binding boundary; stop-rule |
| Determinism / replay bugs | Medium | §7.2 replay test in CI from day one; versioning on the first workflow |
| node-01 capacity | Medium | Dedicated node (M3.2); DBOS fallback reopens §3 |
| New operator surface for one person | Medium | Web UI reduces net operational load; RUNBOOK updated at M7 |
| Displacing M1 quality work | Medium | Preconditions §11.1 make M1 a hard gate |
| Event-history growth | Low | Retention policy set at M3.1; archival configured before M5's long runs |

---

## 14. Functional specification amendments required

On approval, spec **v5.1** carries:

| Section | Change |
|---|---|
| §2.1 Architectural Pattern | Orchestration layer: Celery/Redis → Temporal; Redis retained as cache/heartbeat store |
| §2.5 Microservices | Remove `ivgs-celery-beat`; add Temporal server/UI and workers |
| §6.2 Operational Layer | Checkpoints → event history; retry/timeout tables → declarative policies; heartbeat supervision → native; idempotency → workflow IDs |
| §6.4 Celery Task Orchestration | **Replaced in full** by workflow orchestration; Table 6-7 queue routing preserved |
| §6.1 | Header errata "Seven-Stage" → "Eight-Stage" (closes ADR-003) |
| §4.2 | `pipeline_checkpoints` retained as historical; no longer the recovery mechanism |

---

## 15. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| **O-1** | Temporal persistence: shared node-01 Postgres, or local to the Temporal node? | Measure event-history write load at M3.1. Lean local — it keeps the SPOF node unencumbered |
| **O-2** | One workflow for all 8 stages, or a parent with per-stage children? | Single workflow; children only for segment fan-out (§5.4). Simpler history, easier replay |
| **O-3** | Should GPU reservation failure be fatal? | **Decide explicitly.** Today it fails open silently (D4), which is why `total_nodes:0` went unnoticed for months. Recommend fatal-with-retry once ledger P2.6 makes the registry real |
| **O-4** | Event-history retention period | Set at M3.1 before M5's long runs generate large histories |
| **O-5** | Do periodic ops tasks migrate to Schedules, or stay on a minimal Beat? | Schedules — otherwise Celery survives as a second orchestrator, violating §11.2 |

---

## Appendix A — Current-state evidence map

All references audited against `e613e844`, 2026-08-14.

| Concern | Location |
|---|---|
| Stage transitions / task map / queue map | `ivgs-workers/tasks/pipeline_orchestrator_v2.py:56-130` |
| Completion callback | `:231-350` |
| Media fan-out dispatch | `:355-400` |
| Media join completion | `:637-708` |
| Redis join helpers | `:856-951` |
| Join watchdog | `:955-1060` |
| Broker + task execution config | `ivgs-workers/celery_app.py:250-300` |
| Beat schedule | `:182-220` |
| Visibility timeout / time limits | `ivgs-workers/config.py:214-215, 228-229` |
| Checkpoint write (no-op) | `ivgs-workers/utils/error_handler.py:395-450` |
| Checkpoint API (no POST route) | `ivgs-api/app/api/v1/checkpoints.py:79,106,137,175` |
| GPU reservation | `ivgs-workers/utils/gpu_utils.py:126-238` |
| Gate 1 dispatch | `ivgs-api/app/services/project_service.py:402` |
| Pipeline trigger | `:300-309` |
| Segment planner (preserved) | `ivgs-workers/services/segment_planner.py` |
| Orphaned services | `services/{retry_engine,dlq_service,fallback_chain}.py` |
| Provider factory (ARCH-1) | `shared/providers/{factory,binding}.py`; `ivgs-api/app/services/model_selection.py` |

---

*AD-05 Draft 1 — 2026-08-14. Status: **awaiting review-board approval per §18.** No migration code may be written before approval. Next documents: ADR-005 (engine decision), functional spec v5.1.*
