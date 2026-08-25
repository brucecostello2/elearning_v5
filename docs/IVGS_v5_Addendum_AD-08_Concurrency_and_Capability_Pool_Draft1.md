# IVGS v5 — Functional Specification Addendum AD-08 (Draft 1)

## Multi-Job Concurrency and the Flexible Capability Pool

| | |
|---|---|
| **Addendum** | AD-08 — **Draft 1 (2026-08-24)** |
| **Status** | **DRAFT — PARKED.** Not for implementation. Recorded now so the design is not re-derived later; to be finalised once the open model questions (§AD-08.13) are answered. |
| **Classification** | Internal Working Document |
| **Change-control status** | Draft for review (per §18 change-control process) |
| **Depends on** | AD-05 Orchestration Migration (Temporal) — **hard prerequisite**; AD-02 Draft 3 (node specialization); AD-01 (Model Management, availability poller, `dynamically_loadable`); spec §12 (GPU Scheduler), §4.2 (operational tables), §6 (task routing), §8 (UI) |
| **Supersedes** | Nothing. Additive. |
| **Scope of change** | Removes the single-job, all-nodes-online execution model. Replaces fixed node roles with a capability pool. Adds capability-gated admission, cross-project fairness, and multi-project operator surfaces. |

---

## AD-08.1 Purpose

IVGS v5 as built executes **one project at a time**. A run starts only when every node is online and idle; node roles are fixed at deployment; the operator surfaces assume a single active pipeline. This was correct for bring-up and is the wrong shape for production.

This addendum defines the target: **multiple projects in flight simultaneously across a pool of nodes whose capabilities are discovered rather than declared**, with the pool tolerating absent nodes, and with dispatch decisions that protect the progress of earlier in-flight work.

It is written as a design record, not a work plan. It is deliberately parked behind M1 (happy-path closure), M2 (orchestration correctness defects) and M3 (Temporal migration) — see §AD-08.12 for why that ordering is load-bearing rather than merely convenient.

## AD-08.2 Scope and non-goals

**In scope:** the node capability model and its telemetry; capability-gated admission; the reconfiguration event as a first-class scheduled action; cross-project scheduling policy; the concurrency-safety surface of the existing stage code; multi-project operator views.

**Explicitly not in scope:**

- **Stage bodies.** No change to generation logic in any of the eight stages. The AD-05 §8 scope boundary applies unchanged.
- **The stage sequence, the two human gates, or the logical model-to-stage assignment.**
- **Per-scene video dispatch** (AD-02.6/AD-02.12) — orthogonal, still deferred.
- **Cluster autoscaling or dynamic node provisioning.** The pool is the physical fleet.
- **Preemption of running GPU work.** See §AD-08.8.

## AD-08.3 Design principles

1. **Capability is observed, never declared.** A node's capability is what it currently demonstrates, not what a config file says it is. This follows directly from the node-01 RAM errata: an unmeasured figure propagated across six documents.
2. **Absent capability is a wait state, not an error.** A job whose Stage-6 capability is offline should block visibly, not fail.
3. **Scheduling is deterministic and explainable.** Every dispatch decision must be reconstructible after the fact from recorded inputs.
4. **Concurrency exposes fail-open paths as data loss.** Every silent-skip in the resource layer must become fatal before concurrency is enabled.
5. **Reconfiguration is an event with a cost and a hazard**, not a lookup.

## AD-08.4 Node capability model

### AD-08.4.1 Registration — push with lease, not IP sweep

An IP-range sweep of `192.168.1.90+` is **rejected as the discovery mechanism.** ICMP or port reachability establishes that a machine answers; it does not establish that a healthy worker with CUDA, the correct driver, mounted shared storage and resident weights is present. The failure modes that actually occur in this fleet — a worker container down while the host is up, an NFS mount stale, weights absent — are all invisible to a sweep and all visible to a worker that reports itself.

Nodes therefore **self-register and renew a lease**. The existing `worker_heartbeats` table (spec Table 14) and the `gpu_nodes` registry (Table 11) are the substrate; the change is to the payload and to lease semantics. A node whose lease expires leaves the pool for scheduling purposes without being marked failed.

A discovery sweep may be retained as an **operator diagnostic** — "this host answers but is not in the pool" is a useful alert — but it is not an input to dispatch.

### AD-08.4.2 The capability descriptor

The heartbeat payload today carries GPU telemetry. It must carry enough to schedule against. Draft descriptor:

| Field group | Contents | Source |
|---|---|---|
| Identity | node id, worker id, image tag, driver/CUDA version | worker |
| GPU | model, total VRAM, **free VRAM**, utilisation, temperature, power | measured |
| Host | free RAM, free local disk, free NVMe on the weight volume, CPU load | measured |
| Storage | shared-mount reachability and write-check result | measured |
| Residency | models currently **served** (vLLM), models present on disk and loadable (ComfyUI, Ollama), adapter set | AD-01 poller, extended |
| Load | active reservations, queue subscriptions, in-flight activity count and their job ids | scheduler + worker |
| Reconfiguration | profile-gated service definitions available on this node, and the weight sets present locally for each | node compose + disk scan |

**The measured-not-declared requirement bites immediately.** Nodes currently register via static env identity (`IVGS_GPU_MODEL`, `IVGS_GPU_VRAM_MB`, `IVGS_COMPUTE_CAP`) because the worker containers lack `nvidia-smi` — the WP-38 fix that first made registration work at all. That is a correct expedient and an unacceptable foundation for a capability pool: it cannot report *free* VRAM, and it will confidently misreport a card that has been physically swapped. Exposing real GPU telemetry inside the worker container is a prerequisite for this addendum, not a detail of it.

### AD-08.4.3 Node ↔ card mapping is unverified

**This draft deliberately does not assert which node holds which card.** The documentation set is not self-consistent: AD-02 Draft 3 describes node-02/03 as 96 GB peers; the 2026-06-06 record documents a node-03↔04 GPU swap leaving node-04 at 96 GB and node-03 at 48 GB; the 2026-08-23 first-E2E record states that node-02, node-03 and node-04 all registered as RTX PRO 6000 96 GB. These cannot all be true.

The fleet is understood to comprise **three RTX PRO 6000 Blackwell 96 GB cards and one RTX PRO 5000 Blackwell 48 GB card** across the GPU nodes, plus node-05's RTX 5080 16 GB. The mapping must be established on-box and the affected documents corrected before AD-08 is finalised. Recorded here as an errata candidate.

## AD-08.5 Model residency and the reconfiguration event

### AD-08.5.1 What is actually fixed

A running vLLM process serves exactly one base model; weights, KV pool and captured CUDA graphs are allocated against that model's config at init. This is architectural, not a flag. AD-01's `dynamically_loadable = false` correctly records it.

**It does not follow that a node's capability is immutable.** Three mechanisms change it:

| Mechanism | Granularity | Cost | Notes |
|---|---|---|---|
| **Container swap** — stop the vLLM service, start a profile-gated sibling pointed at different weights | Whole base model | Minutes; dominated by weight load from local NVMe | Already the AD-02.5a mechanism for node-06's on-demand fp8-70B failover. Generalise it; do not invent it. |
| **Multiple vLLM containers**, VRAM-partitioned via `--gpu-memory-utilization` | Concurrent multi-model on one card | None at dispatch | Static partition. **No compute isolation** — see AD-08.5.3. |
| **LoRA adapters** (`--enable-lora`) | Adapter only, within one base model | Seconds | Runtime add/remove exists; treat production-grade runtime mutation as unverified until tested. |

ComfyUI and Ollama load per request and remain genuinely dynamic; they are unaffected by this section.

### AD-08.5.2 Residency becomes a reservable resource

Under single-job operation, model residency is an attribute the AD-01 poller *observes*. Under concurrency it must become a resource the scheduler *holds*, because a reconfiguration performed while another in-flight project has queued work for the outgoing model **silently strands that project**. This is exactly the class of defect that one-job-at-a-time operation has never been able to expose.

Requirements:

- A dispatch decision acquires a **residency lease** on (node, model) for the duration of the activity, alongside the existing VRAM reservation.
- A reconfiguration request is **admission-controlled against the in-flight pipeline**, not merely against free VRAM. It must be refused, or queued, while any live lease or any queued activity depends on the outgoing model.
- Reconfiguration is recorded in `audit_log` with the affected job set, the outgoing and incoming models, and the measured duration.

### AD-08.5.3 Co-residency policy

Static VRAM partitioning across multiple vLLM containers on one card is sound — vLLM preallocates, so the partition holds. **Compute is not partitioned.** MIG is unavailable on the RTX PRO line, so co-resident models time-slice the SMs and both slow unpredictably.

This matters because duration estimates underpin both the reservation TTL and the fairness policy in §AD-08.8. **Policy: co-residency is permitted for a serving model plus a small utility model; two critical-path stages of different jobs must not be co-resident on one card.** Per-worker activity concurrency of 1 on GPU queues (AD-05 §4.2) is retained and is the enforcement point.

### AD-08.5.4 Autonomous reconfiguration is deferred

An elastic pool could legitimately reason: *node-N is idle and reconfigurable to `gpu_llm` in ~4 minutes, which beats 40 minutes queued behind the dedicated LLM node.* That is a real optimisation and the model should be **expressible** — a node's capability is `(served set, reconfiguration options, cost per option, hazard per option)`, not a static tag.

**The scheduler does not act on it autonomously in the first cut.** Reconfiguration is surfaced as an operator action with the cost and the affected-job list displayed. Whether to automate is decided from measured stall frequency, not from anticipation. Re-open trigger: recorded pool stalls attributable to capability shortfall exceeding a threshold to be set at finalisation.

## AD-08.6 Capability-gated admission

The `all nodes online` and `all nodes idle` preconditions are withdrawn and replaced by a per-stage check evaluated **at dispatch time, not at job start**.

- Each stage declares a **capability requirement** (queue, VRAM floor, required model or model class, engine).
- At job submission the system performs a **satisfiability check** across the pool's *configurable* capability — including reconfiguration options, not only current residency. A job that no achievable pool configuration can complete is refused at submission with the specific unmet capability named. A job that is satisfiable but not currently servable is **admitted**.
- At each stage boundary the workflow either dispatches or blocks.

### AD-08.6.1 New project state

Blocking requires a state the machine does not have. Today `ERROR` is the only non-progressing state (spec Table 4-3), which would misrepresent a job waiting on an offline node as a failure.

**Add `WAITING_FOR_CAPABILITY`** — non-terminal, resumable without operator action, carrying the unmet capability and the elapsed wait. Transitions: from any pre-dispatch stage boundary; to the corresponding executing state when capability appears; to `ERROR` only on an explicit operator cancel or a satisfiability regression (e.g. a node permanently withdrawn). This propagates to the state badge set in §8.1.1 and to the pipeline tracker in §8.2.1.

## AD-08.7 The concurrency-safety surface

**This is the largest and least predictable body of work in AD-08, and it is not scheduling.** Every stage has only ever run with one job in flight. The following are unaudited under concurrency and are listed as the known surface, not an exhaustive one:

| Area | Concern |
|---|---|
| Shared filesystem | Path collisions on `/mnt/ivgs-shared`; per-job namespacing of intermediates and render scratch; NFS write contention under simultaneous segment renders |
| Media join | Redis counter keying per `(job_id, scene_id)`; the WP-39 defect showed two stages sharing one completion label within a single job — the same class multiplies across jobs |
| GPU reservations | 8 acquires against 3 releases, all raising `TypeError`; every acquire wrapped in a silent `except`. **Fail-open reservation is cosmetic at one job and produces OOM on a shared card at four.** Must be fatal-on-failure, with `finally` release, before concurrency is enabled |
| Postgres | Row-level contention on `render_jobs` / `projects` state transitions; whether any stage assumes it is the only writer |
| Model engines | ComfyUI checkpoint thrash when two jobs need different image models on one node; Ollama `keep_alive` eviction under interleaved requests |
| SeaweedFS | Concurrent upload behaviour; `scene_id` linkage integrity under interleaving |
| Scheduler | TTL correctness under real competition; whether expiry-driven release can race a live activity |
| node-04 | Carries `gpu_image`, `gpu_tts` and `gpu_talking_head`. Under concurrency it is the bottleneck and the contention point; a 36-minute LatentSync render blocks two other stage classes. Splitting or offloading this node is a precondition for concurrency delivering real throughput, not merely real parallelism |

**Recommended de-risking action, ahead of any AD-08 implementation:** once M2 closes, run two projects simultaneously on the then-current system and record what breaks. This converts the above from a speculative list into a measured one, at negligible cost.

## AD-08.8 Scheduling policy

### AD-08.8.1 Priority keys on readiness age, not submission age

The requirement "give priority to earlier in-flight projects" cannot key on submission time, because the two human gates decouple submission from readiness: a project parked at Gate 1 for two days is chronologically earliest and is not waiting on the fleet. **Priority is computed from the age of the current ready-to-dispatch condition**, not from job creation. Time spent blocked at a gate does not accrue priority.

Spec §12.1's `PriorityQueueManager` levels (urgent / normal / batch) and its anti-starvation aging (+1 per 30 minutes waiting) are retained and now operate on this corrected key.

### AD-08.8.2 No preemption

A running 36-minute LatentSync render or a multi-hour video generation is not interrupted for an older project. Checkpointing is not granular enough to make preemption cheap, and the sunk GPU time is real.

**Consequence, stated plainly:** priority therefore binds only at dispatch. Its practical effect on a fleet with long activities is weaker than the requirement implies — an older project can still wait behind a newer job's in-progress render. This is accepted deliberately rather than discovered later. If measured head-of-line blocking proves unacceptable, the lever is finer-grained activities (per-scene dispatch), not preemption.

### AD-08.8.3 Selection function

Deterministic scoring over the descriptor: hard filters first (capability, VRAM floor, residency or achievable reconfiguration, circuit-breaker state, drain flag), then rank by residency match (avoid reconfiguration), then free VRAM, then inverse load. Spec §12.1's `LoadBalancer` weight formula is the starting point. Every decision records its inputs and the chosen node so it can be explained.

### AD-08.8.4 LLM-based scheduling is rejected

The proposal to hand pipeline control to node-05's RTX 5080 with a small LLM is **not adopted.** Reasons:

1. Node selection is deterministic constraint satisfaction. A scoring function of a few dozen lines solves it correctly and is unit-testable.
2. Non-determinism in the dispatch path is unauditable — "why did job B get node-03?" must have an answer.
3. It collides with AD-05: Temporal workflow code must be deterministic and replay-safe. An LLM could only live in an activity, and a deterministic fallback would still be required for its unavailability — at which point it is redundant.
4. Latency and an additional failure mode are added to the hot path.
5. Placement is wrong regardless: node-05 is the image fallback, Ollama fallback and composition-overflow node. The control plane belongs on node-01, where `ivgs-scheduler` already runs; the workflow engine on the AD-05 orchestration node.

**Adopted instead:** an *advisory* role. A small model may explain scheduling decisions to the operator, summarise fleet state, and flag capacity shortfalls. It has no authority over dispatch.

## AD-08.9 Operator surfaces

Current UI assumes one active pipeline. Required additions:

- **Fleet activity view** — what is running where, across all projects, with per-activity job attribution and elapsed time.
- **Cross-project queue view** — pending dispatches ordered by effective priority, with the computed priority key visible and each wait reason named.
- **Project list** — extend existing `?state=&search=` filtering with the new `WAITING_FOR_CAPABILITY` state and an "active only" filter.
- **Node Monitor** — §8.1.5's singular *current active job* becomes plural; add the capability descriptor, residency set, lease status, and the reconfiguration action (with cost and affected-job list per AD-08.5.4).
- **Per-project controls** — cancel, priority override, hold. All GUI-only per the zero-CLI-for-admin rule.
- **Streams** — the per-job status WebSocket (§5.1.7) does not scale to a dashboard watching N jobs. Either multiplex or fall back to polling; decide with measurement.

## AD-08.10 Observability

Job-scoped correlation identifiers must be threaded through every stage's structured logging and propagated into activity context. A log tail is sufficient for one job and useless for five. The AD-05 execution history covers workflow-level attribution; stage-internal logs are not covered by it and are the gap.

Scheduler metrics (spec Table 12-3) gain per-job and per-capability dimensions; add pool-stall duration and reconfiguration count/duration.

## AD-08.11 What Temporal already provides

Recorded so it is not rebuilt: concurrent execution of N workflows is native; per-job isolation and per-job history come free; capability task queues are already competing-consumer by design (AD-05 §4.2), so multiple nodes serving one capability is configuration, not code; the fan-out/join under concurrency is handled by the engine rather than by Redis counters, which retires the P1.1 defect class rather than hardening it.

**The single-job property is an artefact of the hand-rolled orchestrator, not a designed constraint.** Roughly the execution half of AD-08 arrives with AD-05. What remains genuinely new is discovery, capability-gated admission, fairness policy, the concurrency audit, and the operator surfaces.

## AD-08.12 Sequencing rationale

AD-08 sits behind M1, M2 and M3, in that order, for reasons that are not scheduling convenience:

- **Behind M2** because the four orchestration correctness defects *change severity class* under concurrency. Fail-open GPU reservations and a join that advances on a Redis error are tolerable with one job in flight and are data-loss defects with four.
- **Behind M3** because building concurrency on the Celery orchestrator means building it twice, and the compensating machinery (counters, watchdogs, sweepers) would have to be made concurrency-safe only to be deleted at cutover.
- **Ahead of M5** (long videos) is arguable and left open: long renders make head-of-line blocking worse, which strengthens the case for concurrency first; but long-video work also produces the duration data that AD-08.8 needs.

## AD-08.13 Open questions blocking finalisation

1. **Model substitution.** Exact repository identifier for the candidate ~27B-class Qwen model; dense or MoE (VRAM footprint is unchanged either way, throughput is not); quantisation per card class. *Bruce reports a Qwen3 27B released after the assistant's knowledge cutoff and demonstrated on a 32 GB RTX 5090; unverified in this draft.*
2. **Achievable `max-model-len`** at the chosen quantisation on **both** the 96 GB and 48 GB cards, measured. A weight set that fits 32 GB does not imply long context; the storyboard stage is a long-context job — WP-37 raised its cap to 8192 after 2048 silently truncated an 18-scene project. This also settles the AD-02.12 open item on node-02's fp8 KV; measure both in one pass.
3. **Quality.** MBCP certification bake-off against the banked reference run (`/mnt/ivgs-shared/reference-run-2026-08-23/`), not eyeball comparison. Precedent: Qwen2.5-1.5B produced coherent but off-topic storyboards — a capacity failure visible only functionally.
4. **Whether the substitution succeeds at all.** If a ~27B-class model serves the LLM stages acceptably, LLM capability extends from one node to four, which does more for concurrency than any scheduler sophistication and simultaneously retires the AD-02.7 LLM SPOF and the on-demand-rebuild failover procedure. If it fails, AD-08 proceeds with a single LLM-capable node and the pool is correspondingly less flexible. **This is the highest-leverage open question in the addendum.**
5. **Measured reconfiguration cost** per node and per model, from local NVMe and from the NFS model store.
6. **Node ↔ card mapping**, established on-box (§AD-08.4.3).
7. **node-04 workload split** — whether `gpu_image` moves to node-05 in steady state, and whether that is sufficient.

## AD-08.14 Draft acceptance criteria

To be firmed at finalisation. Indicative:

- Two projects complete end-to-end concurrently, with outputs matching the single-job reference run.
- A job submitted while a required capability is offline enters `WAITING_FOR_CAPABILITY`, is visible as such, and resumes without operator action when the node returns.
- A job requiring a capability no pool configuration can provide is refused at submission, naming the unmet capability.
- No GPU reservation is acquired without a matching release; reservation failure fails the stage.
- A dispatch decision can be reconstructed from recorded inputs.
- A reconfiguration attempt that would strand an in-flight job is refused, with the affected jobs named.
- All operator actions available in the GUI; no CLI step required.

---

*Prepared as an additive draft under §18 change control. **Parked pending §AD-08.13.** Node↔card mapping in §AD-08.4.3 and the model identity in §AD-08.13.1 are explicitly unverified and must be established from ground truth, not from this document, before finalisation.*
