# IVGS v5 Functional Specification — Amendment to v5.1

| | |
|---|---|
| **Document** | Formal amendment to the IVGS v5.0 Functional Specification (18 May 2026) |
| **Target version** | **v5.1 — 2026-08-14** |
| **Change-control status** | **Approved.** AD-05 accepted by the review board 2026-08-14; ADR-005 and ADR-006 accepted the same date. Per §18, this amendment is applied to the specification **before** the corresponding code changes. |
| **Applies to** | `docs/ivgs_v5_functional_spec.md` @ `e613e844` |
| **Authority** | AD-05 (orchestration migration); AD-02 Draft 3 (node-06 hardware); ADR-003 (stage-count errata); ADR-005 (engine decision); ADR-006 (supersedes ADR-004) |
| **How to apply** | Each amendment below gives the **exact current text** and its **complete replacement**. Apply in order, verify the line anchors before each edit, and commit as a single change with message `spec(v5.1): orchestration migration, node-06 CUDA, stage-count errata`. |
| **Scope note** | This amendment touches six sections and the glossary. The remaining ~8,000 lines are unchanged and must not be regenerated. |

---

## Summary of amendments

| # | Section | Change | Authority |
|---|---|---|---|
| **A1** | §2.1 Architectural Pattern | Orchestration layer: Celery/Redis → Temporal durable execution | AD-05 §4 |
| **A2** | Table 2-1 Architectural Layers | Orchestration row rewritten | AD-05 §4 |
| **A3** | §2.2 / Tables 2-2, 2-3, 3-1, 3-2, §3.2 | node-06: Intel B70 Pro → RTX 6000 Blackwell 96 GB (CUDA) | AD-02 Draft 3 |
| **A4** | §2.4 Docker Compose Stacks | node-06 service list; node-01 gains Temporal | AD-02 Draft 3, AD-05 §4.1 |
| **A5** | §2.5 Microservices Overview | Remove `ivgs-celery-beat`; add Temporal server/UI and workers | AD-05 §4.1 |
| **A6** | §4.2 Table 14 | `pipeline_checkpoints` retained as historical, not the recovery mechanism | AD-05 §10 |
| **A7** | §6.1 header | "Seven-Stage" → "Eight-Stage" | ADR-003 |
| **A8** | §6.2 Operational Layer | Checkpoints, retries, timeouts, heartbeats, idempotency rewritten | AD-05 §9, §10 |
| **A9** | §6.4 | **Replaced in full** — "Celery Task Orchestration" → "Workflow Orchestration" | AD-05 §5 |
| **A10** | Appendix E Glossary | Celery entries revised; Temporal terms added | AD-05 |

> **Transitional status.** Amendments A1, A2, A4 (Temporal), A5, A6, A8 and A9 describe the **target architecture approved under AD-05**. They are marked in the specification as *effective at M3 cutover*. Until cutover the Celery implementation remains live and is described in the transitional note at A9. This follows §18's requirement that the specification be amended before code, while keeping the document truthful about what is running.

---

## A1 — §2.1 Architectural Pattern *(line ~541)*

**Current text:**

> IVGS v5 uses a microservices architecture with a distributed task queue for pipeline execution. All services run as Docker containers orchestrated via Docker Compose, with one Compose file per physical node. The frontend communicates with the FastAPI backend via Nginx on node-01; the backend dispatches pipeline jobs to Celery workers on GPU nodes via Redis. Binary assets are stored in SeaweedFS on node-01; metadata, prompts, and operational state are stored in PostgreSQL 17 on node-01.

**Replacement text:**

> IVGS v5 uses a microservices architecture with **durable workflow execution** for pipeline orchestration. All services run as Docker containers orchestrated via Docker Compose, with one Compose file per physical node. The frontend communicates with the FastAPI backend via Nginx on node-01.
>
> Pipeline execution is coordinated by a **Temporal** server on a dedicated orchestration node. A render job is a single durable workflow spanning all eight stages; each stage executes as an **activity** on a capability-scoped task queue, dispatched to workers on the GPU nodes. Workflow state, execution history, retries and timers are persisted by the orchestration engine, so a job survives worker or node failure and resumes from its last completed step without operator intervention.
>
> The two human review gates (storyboard approval, draft approval) are implemented as workflow **signals**: the workflow blocks at the gate for an unbounded period — days are normal — and resumes when the API signals approval.
>
> Binary assets are stored in SeaweedFS on node-01; metadata, prompts, and operational state are stored in PostgreSQL 17 on node-01. **Redis is retained as a cache and worker-heartbeat store; it is not a pipeline message broker.** GPU admission control remains the responsibility of the `ivgs-scheduler` microservice (§12), which the pipeline invokes from an activity.
>
> *Engine rationale and rejected alternatives: ADR-005. Migration design, scope boundary and cutover procedure: AD-05.*

## A2 — Table 2-1 Architectural Layers

**Replace the `Orchestration` row:**

| Layer | Components | Node(s) |
|---|---|---|
| ~~Orchestration~~ | ~~Celery task graph, pipeline state machine, Redis broker, Celery Beat scheduler~~ | ~~node-01 (broker), node-02–06 (workers)~~ |
| **Orchestration** | **Temporal server + Web UI; `VideoPipelineWorkflow` (8 stages); activity workers; Temporal Schedules for periodic operations** | **node-07 (server/UI), node-01–06 (activity workers)** |

**Add a row:**

| **Cache / Heartbeat** | **Redis 7.4 — result cache, worker heartbeat registry** | **node-01** |

## A3 — node-06 hardware *(lines ~756, 854, 863, 1163, 1311, 1320)*

Per **AD-02 Draft 3 (2026-07-07)**, node-06's card was physically replaced. Every occurrence of `Intel B70 Pro` / `Intel B70 Pro 32 GB` in Tables 2-2, 2-3, 3-1 and 3-2 becomes **`NVIDIA RTX 6000 Blackwell` / `96 GB`**.

**Table 2-2 — node-06 Primary Roles.** Replace:

> ~~Remotion renderer (lower-thirds, animations), FFmpeg overflow composition, Celery overflow workers~~

with:

> **Primary FFmpeg compositor; Remotion renderer (lower-thirds, captions, animated titles, Ken-Burns L2 fill); second CUDA video generation node (`gpu_video`); on-demand fp8-70B LLM failover (profile-gated, stopped by default)**

**Table 3-2 — node-06 Primary Models Served.** Replace:

> ~~Remotion (CPU/Intel GPU), FFmpeg composition~~

with:

> **CogVideoX 5B / Wan2.1 (second video node), Remotion, FFmpeg composition, Llama-3.3-70B-FP8 (failover only)**

**§3.2 closing note.** Replace:

> ~~NVIDIA driver version 570.x or later required. CUDA 12.4+ required for Blackwell architecture GPUs. Intel oneAPI 2024.x required for node-06.~~

with:

> NVIDIA driver version 570.x or later required. CUDA 12.4+ required for Blackwell architecture GPUs. **All six GPU-bearing nodes are CUDA; the Intel oneAPI/IPEX path is withdrawn.**

**Line ~863 and ~1163.** Remove both references to node-06 using Intel oneAPI/IPEX; all GPU nodes use the NVIDIA Container Toolkit.

## A4 — §2.4 Docker Compose Stacks

**node-06.** Replace:

> ~~**node-06 (Intel GPU, Remotion, Overflow)** — Services: `remotion-renderer`, `ffmpeg-worker`, `celery-worker`, `node-exporter`, `intel-gpu-exporter`.~~

with:

> **node-06 (Composition, Motion Graphics, Second Video Node)** — Services: `remotion-renderer`, `ffmpeg-worker`, `cogvideox`, `temporal-worker`, `node-exporter`, `nvidia-gpu-exporter`, and a **profile-gated `vllm` failover service** (stopped by default; started on demand per AD-02 Draft 3, Option C).

**node-01.** Remove `celery-beat` from the service list. **Add a new stack:**

> **node-07 (Orchestration)** — Services: `temporal`, `temporal-ui`, `temporal-worker` (default queue), `node-exporter`.

**All GPU nodes.** `celery-worker` → `temporal-worker` at M3 cutover.

## A5 — §2.5 Microservices Overview

**Remove the `ivgs-celery-beat` row.** **Replace `ivgs-workers`:**

| Microservice | Technology | Node | Purpose |
|---|---|---|---|
| `ivgs-workers` | **Temporal Python SDK** | node-01 – node-06 | **Activity workers — execute pipeline stage activities on capability-scoped task queues** |

**Add:**

| `temporal` | Temporal (Go) | node-07 | Durable workflow engine — execution history, timers, retries, signals, schedules |
| `temporal-ui` | Temporal Web | node-07 | Operator run inspection: history, inputs/outputs, retries, timings, failure detail |

Periodic operations formerly run by Celery Beat (heartbeat supervision, DLQ processing, orphan cleanup, retention migration, backup verification, GPU fleet metrics) become **Temporal Schedules**.

## A6 — §4.2 Table 14 `pipeline_checkpoints`

**Append to the table description:**

> **v5.1 note.** From M3 cutover, workflow execution history is the recovery mechanism; recovery is inherent to the orchestration engine rather than an application concern. `pipeline_checkpoints` is retained for historical rows and audit continuity. New rows are not written and `POST /api/v1/jobs/{id}/resume` is superseded by workflow reset.
>
> *(Historical note: the v5.0 checkpoint write path was never operable — no `POST /jobs/{id}/checkpoints` route existed, and the worker-side write failed silently. No checkpoint rows were ever persisted. See `OUTSTANDING_WORK.md` v4.0 P1.2.)*

## A7 — §6.1 header *(line ~3678)*

**Replace:**

> ~~6.1 Seven-Stage Content Creation Pipeline~~

with:

> 6.1 **Eight-Stage** Content Creation Pipeline

This closes **ADR-003**, whose "formal change request has been filed" was never applied. The section already defines eight stages; only the header was wrong.

**Also in §6.1 — Stage 6 amendment (AD-01 conformance):**

> Stage 6 resolves its rendering engine through the **AD-01 provider factory** using the per-(stage, tier) model selection, not a hard-coded engine client. A newly certified talking-head model enters production as a GUI selection, never a code change.

**Stage 3 dispatch wording.** Replace "Parallel Celery Tasks" with **"Parallel Scene Activities"**.

## A8 — §6.2 Operational Layer

**Replace the subsections `Checkpoint System`, `Retry Policies`, `Timeout Policies`, `Idempotency Guards` and `Worker Heartbeats` in full:**

> **Durable Execution**
> Every stage runs as an activity within a durable workflow. Workflow state and every completed step are persisted to execution history as they occur. On worker crash, node failure, or restart, the workflow resumes from its last completed step — completed stages are never re-executed. No application-level checkpointing is required.
>
> **Retry Policies**
> Retry is declared per activity and enforced by the orchestration engine. The per-stage attempt counts and backoff sequences of Table 6-4 are preserved as configured values:
>
> | Stage type | Max attempts | Backoff | On exhaustion |
> |---|---|---|---|
> | LLM (transcript, storyboard) | 4 | 5s → 15s → 45s → 135s | Workflow failure, operator-visible |
> | Image generation | 3 | 10s → 30s → 90s | Fallback chain, then workflow failure |
> | Video generation | 2 | 30s → 90s | Fallback chain, then workflow failure |
> | TTS audio | 3 | 10s → 30s → 90s | Kokoro fallback, then workflow failure |
> | Talking head | 2 | 30s → 90s | SadTalker fallback, then workflow failure |
> | Composition / FFmpeg | 2 | 30s → 90s | Workflow failure |
>
> Non-retriable failures are declared as `non_retryable_error_types` and fail immediately rather than consuming attempts. The `dead_letter_messages` table (Table 15) is retained as the operator audit record; replay is performed by workflow reset rather than by re-queueing a message.
>
> **Timeout and Liveness Policies**
> Each activity declares a `start_to_close_timeout` (the Table 6-5 per-model values) **and** a `heartbeat_timeout`. Long-running activities — video generation, talking-head render, FFmpeg segment render — heartbeat while working.
>
> Liveness is therefore reported, not inferred. An activity that is slow but progressing is not interrupted; one that has stopped progressing fails within its heartbeat timeout. **There is no message visibility timeout and no possibility of a task being redelivered while still executing.**
>
> **Idempotency**
> Deduplication is provided at two levels. Each render job runs under a deterministic workflow ID, so a duplicate trigger attaches to the running workflow rather than starting a second one. Within Stage 3, the `generation_params_hash` content check (§6.2, v5.0) is retained: if a completed asset with the same parameter hash exists, the activity returns the cached result without re-executing.
>
> **Worker Liveness**
> Workers report liveness by polling their task queues; a worker that stops polling has its in-flight activities timed out and retried on another worker of the same capability. The separate 10-second Redis heartbeat is retained for **GPU telemetry** (temperature, memory, utilisation) feeding the scheduler and dashboards — a monitoring concern, distinct from work distribution.
>
> **GPU Reservation**
> Each GPU-bearing stage brackets its work with `acquire_gpu_reservation` and `release_gpu_reservation` activities against `ivgs-scheduler` (§12), with release guaranteed in the workflow's `finally` block. **Reservation failure is fatal to the stage and retried under the stage's retry policy** — it does not soft-skip. *(v5.0 behaviour was fail-open, which concealed an empty node registry for an extended period; see `OUTSTANDING_WORK.md` v4.0 P1.3 and P2.6.)*

## A9 — §6.4 *(replaced in full)*

**Replace the section title** "6.4 Celery Task Orchestration" with **"6.4 Workflow Orchestration"**, and the body with:

> A render job executes as a single durable workflow, `VideoPipelineWorkflow`, spanning all eight stages. Sequencing is expressed as ordinary control flow — each stage is an awaited activity call — rather than as a lookup table of task names. A reference to a non-existent stage is therefore a load-time error, not a runtime dispatch failure.
>
> **Stage sequence.** Stages 1 → 2 → *[gate]* → 3 → 4 → 5 → 6 → 7 → *[gate]* → 8, as defined in §6.1.
>
> **Fan-out and join.** Stage 3 fans out one activity per scene and joins by awaiting all handles. There is no counter, no join watchdog, and no compensating sweeper. A failed scene is drained and recorded; the workflow advances to Stage 4 with a `failed_count` and whatever media rendered (partial advance), preserving v5.0 behaviour.
>
> **Human gates.** Both review gates are workflow signals. The workflow blocks at `wait_condition` until the API signals approval; the API's approval endpoints signal the running workflow rather than dispatching a task. Gates additionally accept `reject` / `regenerate` signals, and every workflow accepts `cancel_job`.
>
> **Segment rendering.** Stage 8's segment render, and the parallel talking-head render, execute as **child workflows — one per segment** — each with its own retry policy and heartbeating. Segment planning remains application logic (`segment_planner`); the `render_segments` table is an operator-facing record, not the resume mechanism.
>
> **Progress and state.** Pipeline state is exposed by workflow query and is truthful by construction. `projects.state` is retained as a denormalised read model for the dashboard, written from the workflow; it is not the source of truth.
>
> **Table 6-7 Task Queue Routing** *(unchanged from v5.0 — Celery queues become Temporal task queues; node specialization per AD-02 Draft 3 is preserved):*
>
> | Queue | Workers | Activity types |
> |---|---|---|
> | `default` | node-01, node-07 | Orchestration, admin, scheduled operations |
> | `gpu_llm` | node-02, node-04 (node-06 failover) | vLLM inference — transcript refinement, storyboard |
> | `gpu_image` | node-04, node-05 | ComfyUI image and animation generation |
> | `gpu_video` | node-03, node-06 | CogVideoX / Wan2.1 video generation |
> | `gpu_tts` | node-04 | Coqui XTTS v2, Kokoro TTS, WhisperX alignment |
> | `gpu_talking_head` | node-04 | Provider-resolved lip-sync rendering |
> | `composition` | node-06, node-05 | FFmpeg composition, Remotion rendering |
>
> **Key configuration.** Activity concurrency of 1 per worker on GPU queues prevents VRAM contention. Workflow code is deterministic and performs no I/O; all external interaction occurs in activities. Workflow logic changes ship behind version gates, and a replay test runs against captured histories before any worker deployment — a requirement, not a convention, because multi-hour renders and multi-day review gates mean workflows are always in flight during a deployment.
>
> **Scheduled operations** (heartbeat supervision, DLQ processing, orphan cleanup, retention migration, backup verification, GPU fleet metrics) run as Temporal Schedules. Celery Beat is withdrawn.
>
> > **Transitional note (v5.1, until M3 cutover).** The implementation at the time of this amendment uses Celery with a Redis broker and event-driven `handle_stage_completion` callbacks, per v5.0 §6.4. That implementation carries four recorded correctness defects (`OUTSTANDING_WORK.md` v4.0 P0.1, P1.1–P1.3), remediated under Master Plan M2. This section describes the architecture approved under AD-05 and takes effect at M3 cutover. Migration sequence, scope boundary, verification gate and rollback: AD-05 §11–§12.

## A10 — Appendix E Glossary

**Revise:**

> **Celery** — Distributed task queue for Python. Used for pipeline stage execution in v5.0; **withdrawn at M3 cutover in favour of Temporal (AD-05)**.
>
> **Celery Beat** — Celery's periodic task scheduler. **Withdrawn at M3 cutover; replaced by Temporal Schedules.**

**Add:**

> **Temporal** — Open-source (MIT) durable execution engine. Persists workflow state and execution history so long-running, multi-step processes survive process and host failure. IVGS's pipeline orchestrator from M3 (ADR-005).
>
> **Workflow** — A durable, resumable function defining a job's control flow. Must be deterministic and perform no I/O directly.
>
> **Activity** — A single unit of work invoked by a workflow. May perform I/O, may fail and be retried independently, and heartbeats while running. Each IVGS pipeline stage is an activity.
>
> **Signal** — An asynchronous message delivered to a running workflow. IVGS's two human review gates are implemented as signals.
>
> **Child workflow** — A workflow started by another workflow, with independent retry and history. IVGS uses one per render segment.
>
> **Activity heartbeat** — A progress report from a running activity. Distinguishes a slow activity from a stalled one, replacing statically guessed timeouts.
>
> **Event history** — The persisted, replayable record of every step in a workflow execution. The recovery mechanism and the operator's primary diagnostic record.
>
> **Replay** — Reconstructing workflow state by re-executing deterministic workflow code against event history. The reason workflow code must be deterministic and versioned.

---

## Verification checklist

Before committing:

- [ ] All six section anchors located and text matched before replacement
- [ ] No occurrence of `Intel B70` or `oneAPI` remains
- [ ] `ivgs-celery-beat` removed from §2.5; Temporal rows added
- [ ] §6.1 header reads "Eight-Stage"; **ADR-003 status → Resolved by spec v5.1**
- [ ] §6.4 transitional note present — the document must not claim Temporal is live before cutover
- [ ] Glossary retains Celery entries marked as withdrawn (do not delete — historical rows and archived docs reference them)
- [ ] Document version header updated to **v5.1 — 2026-08-14**, applicable-documents table amended
- [ ] ADR-004 status → **Superseded by ADR-006** (separate file, same commit)

## Sections deliberately unchanged

§4.3 Pipeline State Machine (the `projects.state` ENUM is retained as a read model); §7 AI Model Specifications; §8 UI; §9 Prompt Management; §10 DAM; §11 QA Pipeline; §12 GPU Scheduler (unaffected by AD-05); §13 Monitoring; §14 Backup/DR; §15 Deployment; §16 Auth; §17 Localisation; §18 Change Control; §19 Development Standards.

**§6.3 Fallback Chains is unchanged in policy**, but note that `FallbackChain`'s L1→L4 strategy selection is not currently wired into any stage (`OUTSTANDING_WORK.md` v4.0 P2.1). The specification describes intended behaviour; the gap is a ledger item, not a specification change.

---

*Amendment prepared 2026-08-14 against `e613e844`. Apply, verify, and commit before beginning M3 implementation, per §18.*
