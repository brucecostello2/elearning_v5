# IVGS v5 — Functional Specification Addendum AD-02

## Node-02 / Node-03 Workload Specialization (fp8 LLM ⁄ Dedicated Video) and Resolution of Gap N23-4

**Addendum to:** IVGS v5.0 Functional Specification (18 May 2026)
**Addendum version:** AD-02, Draft 1
**Classification:** Internal Working Document
**Change-control status:** Draft for review (per §18 change-control process)
**Depends on:** Node topology & model matrix (§6, Table 6-1), GPU scheduler & VRAM matrix (§12, Appendix B), Celery task routing (§6), provider abstraction (§19.1), self-hosted mandate (§1.3)
**Resolves:** Gap **N23-4** — the unresolved node-02/03 LLM-vs-video contention, explicitly deferred for joint design in AD-01.9
**Supersedes (in part):** §6 / Table 6-1 node-02/03 *physical* model assignment (tensor-parallel Llama-3.3-70B across the pair with co-resident CogVideoX/Wan2.1). The *logical* assignment is preserved — see AD-02.5.

---

## AD-02.1 Purpose

The v5 base specification (§6, Table 6-1) assigns nodes 02 and 03 an identical, symmetric role: a single **Llama 3.3 70B** instance served **tensor-parallel across the pair** (2 × 96 GB, 128K context) for `transcript_refinement` and `storyboard_generation`, **and** co-resident **CogVideoX 5B / Wan2.1** for `video_generation`. In practice this topology was never realized, and as built it cannot be: the LLM and video working sets do not fit together on a 96 GB card (AD-02.4), and the nodes are in fact running a 1.5 B model that is too weak for the storyboard stage (AD-02.3).

This addendum records the as-built drift, establishes why the spec-literal topology is physically infeasible on the current hardware, and defines the chosen remediation: **workload specialization** — node-02 becomes a dedicated **fp8 Llama-3.3-70B** LLM node (no video), and node-03 becomes a dedicated **CogVideoX/Wan2.1** video node (no LLM). It is a topology change, not a re-architecture: the logical model-to-stage mapping the spec intends is preserved, and the change is delivered as a change-controlled addendum so that a future handoff sees a *planned, justified* deviation rather than unexplained drift.

## AD-02.2 Scope and non-goals

In scope: the physical placement, precision, and serving topology of the LLM and video engines on node-02 and node-03; the Celery queue subscriptions that make each node serve its workload; the worker model-name configuration; the reliability consequences (per-stage single points of failure) and their mitigation; and the resolution of gap N23-4.

Explicitly out of scope — **not** changed by this addendum:

- **The logical model assignment.** LLM stages still target a Llama-3.3-70B-class model; video stages still target CogVideoX/Wan2.1. Only the *realization* (single-card fp8 vs bf16 tensor-parallel pair, and the separation of the two workloads) changes.
- **Other nodes.** node-01 (CPU host: Postgres, API, Redis, SeaweedFS, scheduler, Celery beat) and node-04 (Mistral-24B image-prompt LLM + image/TTS), node-05/06 are unchanged by this addendum, except as future elastic capacity (AD-02.6).
- **Weight acquisition mechanics.** Provisioning weights remains the responsibility of the `ivgs-models` tooling and operations (§14.1, AD-01.7); this addendum states the *target* weights, not the procedure.
- **Single-job video latency.** Parallelizing one job's scenes across multiple video nodes requires a per-scene dispatch change (AD-02.6); that is a separate, deferred item and is **not** delivered here.
- **The AD-01 Model Management subsystem.** This addendum fixes the per-node *served set*; it does not implement model selection. Compatibility with AD-01 is addressed in AD-02.9.

## AD-02.3 As-built state versus specification (the drift)

| Aspect | Specification (§6, Table 6-1) | As built (observed live) |
|---|---|---|
| LLM model | Llama 3.3 70B (alt: Qwen2.5 72B) | `Qwen/Qwen2.5-1.5B-Instruct` |
| Serving topology | Tensor-parallel across node-02 **+** node-03 | Two **independent** single-card instances (`ivgs-vllm-primary` on node-02, `ivgs-vllm-secondary` on node-03), TP=1 each — **not** tensor-parallel |
| Context length | 128K | `--max-model-len 8192` |
| GPU memory utilization | High (pair sized for 70B) | `--gpu-memory-utilization 0.30`, `--dtype bfloat16` |
| Served name | (Llama) | `qwen-1.5b` (worker requests this served name) |
| Video engine | CogVideoX 5B / Wan2.1 co-resident | Present on both nodes (`gpu_video` queue) |
| Weights on disk | Llama-3.3-70B (NFS model store) | Only Qwen2.5-1.5B (≈ 2.9 GB) in node-local `/data/models/hub`; **no** 70B/72B weights anywhere; NFS `/mnt/ivgs-shared/models` does not exist (the model-download step never ran) |

**Functional consequence.** With the storyboard stage driven by a 1.5 B model, an end-to-end verification run on a photosynthesis transcript produced a coherent but **off-topic** storyboard (quantum-mechanics scenes). The failure is a model-capacity problem — the 1.5 B model parrots the few-shot example in the prompt rather than following the source — **not** a quantization artifact and **not** a prompt defect. This is the proximate trigger for this addendum.

**Prepared-but-unused assets.** Serving definitions already exist at `/opt/ivgs/ivgs-models/vllm/{llama-3.3-70b.yaml, qwen2.5-72b.yaml, mistral-24b.yaml}`. The Llama YAML targets `/mnt/ivgs-shared/models/llama-3.3-70b-instruct`, `tensor-parallel-size: 2`, `max-model-len: 128000`, `gpu-memory-utilization: 0.90` — i.e., the spec-literal bf16-pair config. It has never been used; node-04's working Mistral was pulled separately into its local cache, bypassing the NFS model-store flow entirely.

## AD-02.4 Why the spec-literal topology is physically infeasible

Each of node-02 and node-03 has **one** RTX PRO 6000 Blackwell, **96 GB**. The spec-literal config asks a single card to simultaneously hold a tensor-parallel shard of a bf16 70B model **and** the CogVideoX working set:

- bf16 Llama-3.3-70B weights ≈ **140 GB** total → ≈ **70 GB per card** under TP=2, before KV cache. At `gpu-memory-utilization 0.90` the vLLM process commits ≈ **86 GB** of the 96 GB card (weights + KV + activations).
- CogVideoX-5B working set ≈ **26 GB**.
- 86 GB (vLLM) + 26 GB (video) ≈ **112 GB** required versus **96 GB** available → **does not fit.**

So co-residency of bf16-70B-TP and CogVideoX on these cards is physically impossible; the symmetric spec topology cannot be deployed as written. Two facts further constrain the solution space:

1. **node-01 cannot absorb the LLM.** It has no GPU; CPU inference of a 70B model is operationally impractical for interactive pipeline stages. node-01's maintainability contribution is the **provider-abstraction seam** (§19.1 / gap ARCH-1), not relocating weights onto it.
2. **Quantization is the only way to fit a 70B on a single card.** Surveyed options in the same lineage as node-04's proven RedHatAI Mistral (compressed-tensors, vLLM-native, ungated): **w4a16** (≈ 40 GB) and **fp8** (≈ 70 GB).

A first remediation — *co-resident 4-bit*: run **w4a16** Llama (≈ 40 GB) **plus** CogVideoX (≈ 26 GB) on **each** node (≈ 76 GB/card, fits but tight, KV/context constrained to ≈ 16K) — was approved as a fallback. This addendum **supersedes** that fallback with specialization (AD-02.5), which yields a higher-fidelity LLM and removes the VRAM-contention tightrope.

## AD-02.5 The specialization decision

| Node | Workload | Engine / model | Precision | Notes |
|---|---|---|---|---|
| **node-02** | LLM only (`transcript_refinement`, `storyboard_generation`) | vLLM, **Llama-3.3-70B** | **fp8** (≈ 70 GB) | Dedicated 96 GB card. No CogVideoX/Wan2.1. Freed headroom funds an fp8 KV cache for long context (target up to the spec's 128K, subject to KV-headroom validation per Appendix B / AD-01.7). |
| **node-03** | Video only (`video_generation`) | CogVideoX 5B / Wan2.1 | as today | Dedicated 96 GB card (≈ 26 GB working set → large headroom). No LLM served. |
| node-04 | Image-prompt LLM + image/TTS | Mistral-24B (w4a16) + ComfyUI/TTS | as today | **Unchanged.** |

**Why fp8 rather than the 4-bit fallback.** Once the card no longer shares VRAM with video, there is no need to compress to 4-bit. fp8 on Blackwell is near-lossless (typically < 1% degradation versus bf16, versus ~1–3% for w4a16), and the ≈ 26 GB no longer spent on CogVideoX becomes KV-cache budget — enabling the long context the spec calls for. **Specialization is therefore closer to the spec's quality intent (a high-fidelity 70B for the LLM stages) than the co-resident 4-bit compromise, even though the topology differs.**

**What is preserved.** The spec's logical intent is intact: a Llama-3.3-70B-class model drives the LLM stages; CogVideoX/Wan2.1 drives video. What changes is the *physical realization* — single-card fp8 instead of a bf16 tensor-parallel pair, and the two workloads separated onto dedicated nodes rather than co-resident on both.

## AD-02.6 Throughput analysis — why halved video parallelism is acceptable

The obvious objection is that dedicating only node-03 to video halves potential video parallelism (was: both nodes). Analysis of the actual dispatch pattern shows this loss is largely theoretical at current and near-term load:

- **Video is dispatched batched-per-job.** `dispatch_media_generation` packs **all** of a job's video scenes into a **single** `generate_video_clips` task, which runs on **one** node, rendering scenes **sequentially**. A single job's video therefore already uses only one node; the second node never accelerated an individual job.
- **Two video nodes only help two cases:** (a) **concurrent jobs** — each job's video task lands on a different node; or (b) a future **per-scene dispatch** change that lets one job's scenes spread across nodes. Under the current batched-per-job dispatch at low/dev concurrency, the second video node is idle capacity.
- **Celery makes the lost capacity elastically recoverable.** Task routing is broker-based competing-consumers (Redis). A worker subscribed to the `gpu_video` queue becomes an additional consumer the instant it starts — **no code change, no scheduler change, no central registration**. Concurrent-video capacity is restored simply by bringing up additional video-capable nodes (node-05/06/…); Celery distributes per-job video tasks across them automatically. **Capability is the `-Q` queue subscription a worker holds, not the model loaded** — so specialization is a *soft*, reversible configuration choice, not a one-way architectural commitment.
- **Pipeline assembly-line benefit.** Under a stream of jobs, specialization lets node-02 continuously process LLM stages while node-03 continuously processes video for *different* concurrent jobs — clean cross-job pipelining, with each node's hardware matched to its stage.
- **Single-job video latency is unchanged by node count.** It improves only via per-scene dispatch, which is independent of how many nodes exist and is explicitly out of scope here (AD-02.2).

**Conclusion.** For the system's present reality (verification/dev, short and infrequent LLM calls, batched-per-job video, low concurrency) the dedicated single video node is sufficient, and the higher-fidelity fp8 LLM plus elimination of VRAM contention outweigh a parallelism loss that does not bind at current load and is elastically recoverable by adding nodes.

## AD-02.7 Reliability — single points of failure and failover

Specialization makes **node-02 the sole LLM node** and **node-03 the sole video node**. Each becomes a per-stage single point of failure: node-02 down → the pipeline cannot refine or storyboard; node-03 down → it cannot generate video. The superseded symmetric design degraded more gracefully (either node could cover both workloads, if at reduced fidelity).

This is mitigated and, in context, acceptable:

- **It is not a new class of risk.** The fleet is already SPOF-dense by design: node-01 is the only Postgres/API/Redis/scheduler host, and node-04 is the only image/TTS node. Per-stage GPU SPOFs are consistent with the existing topology.
- **Documented manual failover.** The opposite-workload container may be kept **present but profile-gated (stopped)** on each node — a dormant CogVideoX worker on node-02, a dormant vLLM+LLM worker on node-03. On a node loss, an operator runs a documented procedure to stop the live workload on the surviving node and start the opposite one. Failover is **exclusive, not additive** (a single 96 GB card cannot run both fp8-70B and CogVideoX at once), so this restores function in a degraded single-stage-at-a-time mode, not full concurrency.
- **Open decision (AD-02.12):** whether to pre-stage these standby containers now or treat failover as an on-demand rebuild.

## AD-02.8 Configuration changes

At the level of *what changes* (exact file mechanics — gitignored `.env.node0X` versus tracked `docker-compose.node0X.yml` — are settled during implementation):

**node-02 (LLM node):**
- vLLM serves **fp8 Llama-3.3-70B**: TP=1, served-name `llama-3.3-70b`, `gpu-memory-utilization` tuned for a single 96 GB card, fp8 KV cache, `max-model-len` set as high as KV headroom permits (target up to 128K). Derived from the prepared `ivgs-models/vllm/llama-3.3-70b.yaml`, edited from the bf16-pair config (TP=2 → 1; bf16 → fp8; weights path → the fp8 weights).
- Worker model config: `IVGS_VLLM_PRIMARY_MODEL` and `VLLM_SERVED_NAME` change `qwen-1.5b` → `llama-3.3-70b`. `VLLM_PRIMARY_URL` stays `http://vllm:8000` (local).
- **Remove** the CogVideoX container and the `gpu_video` queue subscription from this node.

**node-03 (video node):**
- **Remove/disable** the vLLM LLM serving and the `gpu_llm` queue subscription.
- Video worker subscribes to **`gpu_video` only**; CogVideoX/Wan2.1 unchanged otherwise.

**Weights provisioning (ops / `ivgs-models`, per §14.1 / AD-01.7):**
- Provision an **fp8 Llama-3.3-70B** variant (≈ 70 GB) to node-02 local `/data/models` (194 GB volume, ≈ 87 GB free → fits). Candidate source: a RedHatAI/neuralmagic fp8 Llama-3.3-70B (compressed-tensors), to be confirmed for exact repo and gating at provision time; node-04's working RedHatAI pull confirms the fleet has Hugging Face egress, and the RedHatAI quantized variants are typically ungated. Whether weights remain node-local or move to the NFS model store is an open decision (AD-02.12).

**Queue-subscription delta:** see Appendix AD-B.

## AD-02.9 Relationship to AD-01 and resolution of gap N23-4

AD-01.9 explicitly deferred the interaction between the model-residency policy and the node-02/03 LLM-vs-video contention, naming it **gap N23-4** and stating that "the residency policy and that contention policy should be designed together." This addendum **resolves N23-4 by eliminating the contention at the source**: the LLM and video workloads no longer share a card, so there is no residency arbitration to perform between them on these nodes.

Compatibility with the (future, non-functional) AD-01 Model Management subsystem is preserved:

- The `dynamically_loadable = false` constraint for vLLM still holds (AD-01.5.2 / AD-01.9): node-02 serves **one fixed model per process** — now fp8 Llama-3.3-70B. The planner's vLLM candidate set on the LLM node is exactly the served model.
- The AD-01.6 availability poller will report `llama-3.3-70b` **served** on node-02 and CogVideoX/Wan2.1 **available** on node-03, with no entries implying the two contend for one card.
- AD-01's residency manager (AD-01.9) no longer needs an LLM-vs-video eviction policy for nodes 02/03; its remaining job there is trivial (one served model per node). The selection layer remains free to choose among served models once additional LLM nodes/models exist.

## AD-02.10 Rollout / implementation steps

1. **Provision** the fp8 Llama-3.3-70B weights to node-02 local `/data/models` (verify free space and checksum).
2. **Reconfigure node-02 serving** to fp8 Llama-3.3-70B (TP=1, single-card util, fp8 KV) with served-name `llama-3.3-70b`; update worker `IVGS_VLLM_PRIMARY_MODEL` / `VLLM_SERVED_NAME`.
3. **Strip cross-workloads:** remove CogVideoX + `gpu_video` from node-02; remove the LLM + `gpu_llm` from node-03.
4. **Recreate** the affected containers on each node (no `--remove-orphans`).
5. **Verify:** `GET /v1/models` on node-02 returns `llama-3.3-70b`; node-03 serves no LLM; per-node VRAM shows the fp8 70B resident on node-02 with headroom and CogVideoX-only on node-03; a test completion against node-02 succeeds.
6. **Functional check:** re-run a storyboard from a representative transcript and confirm the scenes are **on-topic** (the photosynthesis → quantum failure no longer reproduces).
7. **Record** the deviation in the SSOT / `OUTSTANDING_WORK.md` ledger and mark **gap N23-4 resolved**.

## AD-02.11 Acceptance criteria

- node-02 vLLM serves `llama-3.3-70b` (fp8), confirmed via `GET /v1/models`; node-03 serves no LLM. ✓
- node-02 VRAM shows the fp8 70B resident with headroom; **no** CogVideoX process on node-02. ✓
- node-03 runs CogVideoX/Wan2.1 with full-card headroom; **no** vLLM LLM process on node-03. ✓
- A storyboard generated from a representative transcript is **on-topic**; the 1.5 B off-topic failure does not reproduce. ✓
- `transcript_refinement` and `storyboard_generation` tasks route to node-02 (`gpu_llm`); `video_generation` tasks route to node-03 (`gpu_video`). ✓
- Bringing up an additional video-capable worker subscribed to `gpu_video` causes concurrent video tasks to distribute across nodes with **no code change** (elasticity check; may be deferred to when a node is added). ✓
- A documented manual failover procedure exists for each per-stage SPOF. ✓
- The deviation is recorded in the SSOT/ledger and **gap N23-4** is marked resolved. ✓

## AD-02.12 Open design decisions (for review)

1. **fp8 KV cache and `max-model-len`.** The full 128K context depends on fp8-KV headroom on the single card; confirm the achievable context against real VRAM (Appendix B / AD-01.7 external acceptance) and set `max-model-len` accordingly.
2. **Standby containers.** Pre-stage the profile-gated opposite-workload containers on each node now (faster failover, more moving parts), or treat failover as an on-demand rebuild (simpler, slower recovery)?
3. **Weights location and source.** Confirm the exact fp8 Llama-3.3-70B repo and gating; decide whether the weights remain node-local (`/data`) or are placed in the NFS model store per the `ivgs-models` flow (§14.1).
4. **Per-scene video dispatch.** Out of scope here; recorded as the separate, independent lever for single-job video latency, to be addressed on its own merits if/when single-job wall-clock becomes a concern.

---

## Appendix AD-A — Per-card VRAM budget comparison (96 GB card)

| Configuration | LLM weights | LLM KV / context | Video working set | Per-card total | Fits 96 GB? |
|---|---|---|---|---|---|
| Spec-literal: bf16 70B (TP=2) **+** CogVideoX | ≈ 70 GB | + KV (constrained) | ≈ 26 GB | ≈ 112 GB | **No** |
| Fallback (superseded): w4a16 70B **+** CogVideoX | ≈ 40 GB | + KV (≈ 16K) | ≈ 26 GB | ≈ 76 GB | Yes (tight) |
| **node-02 specialized: fp8 70B, no video** | ≈ 70 GB | + fp8 KV (long ctx) | — | ≈ 90 GB | **Yes** |
| **node-03 specialized: CogVideoX only** | — | — | ≈ 26 GB | ≈ 26 GB | **Yes** (large headroom) |

*Weight figures are budgetary; KV-cache size depends on context length and is validated against real VRAM through the external acceptance process (AD-01.7) and the Appendix B matrix, not asserted here.*

## Appendix AD-B — Celery queue-subscription matrix (current → specialized)

| Node | Queues — before | Queues — after | Resulting workload |
|---|---|---|---|
| node-02 | `gpu_llm`, `gpu_video` | **`gpu_llm`** | fp8 Llama-3.3-70B (LLM stages) |
| node-03 | `gpu_llm`, `gpu_video` | **`gpu_video`** | CogVideoX/Wan2.1 (video) |
| node-04 | image / TTS queues | *unchanged* | Mistral-24B + image/TTS |
| node-05/06 (future) | — | `gpu_video` and/or `gpu_llm` | elastic capacity; auto-joins on worker start |

*Capability is conferred by the queue subscription, not the model loaded; adding a worker on a queue makes it an immediate competing consumer with no code or scheduler change.*

---

*Prepared as an additive deviation under the §18 change-control process. It resolves gap N23-4 by separating the node-02/03 LLM and video workloads onto dedicated cards, and supersedes the §6 / Table 6-1 node-02/03 physical assignment (bf16 70B tensor-parallel pair with co-resident video) while preserving the spec's logical model-to-stage intent. It is compatible with the AD-01 Model Management subsystem, which it leaves non-functional; AD-01's vLLM `dynamically_loadable = false` constraint and availability poller apply unchanged to the fixed per-node served set defined here.*
