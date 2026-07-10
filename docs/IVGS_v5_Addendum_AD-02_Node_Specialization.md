# IVGS v5 — Functional Specification Addendum AD-02 (Draft 3)

## Node-02 / Node-03 Workload Specialization (fp8 LLM ⁄ Dedicated Video), node-06 promotion to a CUDA video + compositor + LLM-failover node, and Resolution of Gap N23-4

**Addendum to:** IVGS v5.0 Functional Specification (18 May 2026)
**Addendum version:** AD-02, **Draft 3 (2026-07-07)** — node-06 hardware changed from Intel B70 Pro (no CUDA) to a second **RTX 6000 Blackwell 96 GB (CUDA)**; node-06 role redesignated per **Option C**. Supersedes Draft 2's node-06 characterization (Intel/no-CUDA, Remotion + FFmpeg only).
**Classification:** Internal Working Document
**Change-control status:** Draft for review (per §18 change-control process)
**Depends on:** Node topology & model matrix (§6, Table 6-1), GPU scheduler & VRAM matrix (§12, Appendix B), Celery task routing (§6), provider abstraction (§19.1), self-hosted mandate (§1.3)
**Resolves:** Gap **N23-4** (node-02/03 LLM-vs-video contention, deferred from AD-01.9); and the **concurrent-video-recovery gap** Draft 2 flagged as "requires additional CUDA video-capable nodes beyond the six."
**Supersedes (in part):** §6 / Table 6-1 node-02/03 *physical* model assignment (bf16 Llama-3.3-70B tensor-parallel pair with co-resident CogVideoX/Wan2.1); and Draft 2's node-06 role. The *logical* model-to-stage assignment is preserved (AD-02.5).

---

## AD-02.1 Purpose

The v5 base spec (§6, Table 6-1) assigns node-02 and node-03 an identical symmetric role: one **Llama 3.3 70B** served **tensor-parallel across the pair** (2 × 96 GB, 128K) for `transcript_refinement`/`storyboard_generation`, **and** co-resident **CogVideoX 5B / Wan2.1** for `video_generation`. That topology was never realized and cannot be: the LLM and video working sets do not fit together on a 96 GB card (AD-02.4).

This addendum defines **workload specialization** — node-02 a dedicated **fp8 Llama-3.3-70B** LLM node, node-03 a dedicated **CogVideoX/Wan2.1** video node — and, in Draft 3, promotes **node-06** (now a second CUDA 96 GB card) to a **second video node + primary compositor + on-demand LLM failover** for node-02. It is a topology change, not a re-architecture: the logical model-to-stage mapping is preserved; the change is delivered under §18 change control so a future handoff sees planned, justified deviation.

## AD-02.2 Scope and non-goals

In scope: physical placement, precision and serving topology of the LLM and video engines on node-02/03; node-06's promotion to CUDA video + compositor + LLM standby; the Celery queue subscriptions that confer each node's workload; worker model-name config; reliability consequences and mitigation; resolution of N23-4 and the video-recovery gap.

Explicitly **not** changed:

- **The logical model assignment.** LLM stages still target a Llama-3.3-70B-class model; video stages still target CogVideoX/Wan2.1. Only the *realization* changes.
- **node-01 and node-04.** node-01 (CPU host: Postgres, API, Redis, SeaweedFS, scheduler, Celery beat, ARCH-1 seam) and node-04 (Mistral-24B image-prompt LLM + image/TTS + talking-head) are unchanged.
- **node-05.** NVIDIA RTX 5080, 16 GB — ComfyUI SDXL/SD3.5 **image fallback** (behind node-04 FLUX), **Ollama** small-model **LLM fallback** (behind node-02 vLLM, via `OllamaProvider`), and FFmpeg composition **overflow**. Unchanged.
- **Weight acquisition mechanics** (`ivgs-models` / ops, §14.1 / AD-01.7) — this addendum states target weights, not procedure.
- **Single-job video latency.** Improves only via per-scene dispatch (AD-02.6), separate and deferred.

## AD-02.3 As-built drift (unchanged from Draft 2)

| Aspect | Spec (§6, Table 6-1) | As built |
|---|---|---|
| LLM model | Llama 3.3 70B | `Qwen/Qwen2.5-1.5B-Instruct` |
| Topology | Tensor-parallel node-02 + node-03 | Two independent TP=1 single-card instances |
| Context | 128K | `--max-model-len 8192` |
| Served name | (Llama) | `qwen-1.5b` |
| Weights | Llama-3.3-70B (NFS store) | Only Qwen2.5-1.5B local; no 70B/72B; NFS model store never populated |

**Functional consequence.** A 1.5 B storyboard model produced coherent but **off-topic** output (photosynthesis transcript → quantum-mechanics scenes) — a model-capacity failure, not quantization or prompt defect. This is the proximate trigger.

## AD-02.4 Why the spec-literal topology is physically infeasible (unchanged)

Each node-02/03 card is **one RTX PRO 6000 Blackwell, 96 GB**. Spec-literal asks one card to hold a bf16-70B TP shard **and** the CogVideoX working set:

- bf16 Llama-3.3-70B ≈ 140 GB → ≈ 70 GB/card at TP=2; at util 0.90 vLLM commits ≈ 86 GB.
- CogVideoX-5B working set ≈ 26 GB.
- 86 + 26 ≈ **112 GB required vs 96 GB available → does not fit.**

Quantization is the only single-card path (w4a16 ≈ 40 GB, fp8 ≈ 70 GB). node-01 has no GPU and cannot absorb the LLM.

## AD-02.5 The specialization decision (LLM/video cards)

| Node | Workload | Engine / model | Precision | Notes |
|---|---|---|---|---|
| **node-02** | LLM only (`transcript_refinement`, `storyboard_generation`) | vLLM **Llama-3.3-70B** | **fp8** (≈ 70 GB) | Dedicated 96 GB card, TP=1, fp8 KV for long context (target 128K, KV-validated). No video. |
| **node-03** | Video only (`video_generation`) | CogVideoX 5B / Wan2.1 | as today | Dedicated 96 GB card (≈ 26 GB working set, large headroom). No LLM. |
| node-04 | Image-prompt LLM + image/TTS/talking-head | Mistral-24B (w4a16) + ComfyUI/TTS | as today | Unchanged. |

**Why fp8 not 4-bit:** once the card no longer shares VRAM with video, fp8 (≈ 70 GB, near-lossless on Blackwell) is preferable to w4a16, and the freed ≈ 26 GB funds KV cache for the spec's long context. Specialization is *closer* to the spec's quality intent than the co-resident 4-bit compromise.

## AD-02.5a node-06 promotion (Draft 3 — Option C)

**Hardware change.** node-06's Intel B70 Pro (32 GB, oneAPI/IPEX, no CUDA) has been physically replaced with a **second RTX 6000 Blackwell, 96 GB (CUDA)** — now a peer of node-02/03.

| Node | Workload | Engine / model | Precision | Notes |
|---|---|---|---|---|
| **node-06** | **Video (primary set) + primary compositor + on-demand LLM failover** | CogVideoX/Wan2.1 **and** FFmpeg/Remotion; standby fp8 Llama-3.3-70B | video as node-03; fp8 for standby | Second CUDA video node — HA pair with node-03 on `gpu_video`. Also runs the **primary FFmpeg compositor + Remotion** (captions/lower-thirds/animated titles/Ken-Burns L2) co-resident with video (CogVideoX ≈ 26 GB + FFmpeg/Remotion are light → fits 96 GB with wide headroom; NVENC now available). On node-02 loss, an operator **rebuilds on demand** a dormant fp8-70B `gpu_llm` worker here (not pre-staged — AD-02.12 decision). |

**Why C.** node-06's promotion directly supplies the CUDA video capacity Draft 2 said was missing, gives the **heaviest/bottleneck** workload (video) real redundancy, and provides the LLM per-stage failover AD-02 wanted but could not build — without consuming a card on the non-bottleneck LLM stage. Capability is the `-Q` subscription, so this is configuration, not re-architecture; the AD-01 availability poller and scheduler handle multi-node residency with no code change.

## AD-02.6 Throughput — video parallelism now restored (Draft 3)

Draft 2 dedicated only node-03 to video and argued the halved parallelism was tolerable at low load, while flagging that the named elastic-recovery path (node-05/06) did **not** hold (node-06 was non-CUDA; node-05 is fallback/composition). **Draft 3 closes that gap directly:** node-06 is now a CUDA `gpu_video` peer, so:

- **Concurrent-job video** distributes across node-03 **and** node-06 (competing consumers on `gpu_video`) — no code/scheduler change.
- **Per-scene dispatch** (future, AD-02.6/AD-02.12) could now spread a *single* job's scenes across two real CUDA video nodes; still out of scope here but no longer blocked by a missing node.
- Capability remains the queue subscription, not the model — reversible by config.

The video-throughput objection to specialization is therefore resolved, not merely tolerated.

## AD-02.7 Reliability — SPOFs now mitigated on both per-stage axes (Draft 3)

Specialization made node-02 the sole LLM node and node-03 the sole video node. Draft 3 mitigates **both**:

- **Video SPOF → mitigated.** node-03 and node-06 both consume `gpu_video`; loss of either leaves video serving on the other (at reduced concurrency). No manual step for continuity.
- **LLM SPOF → mitigated (on-demand).** On node-02 loss, an operator runs the documented procedure to **rebuild** an fp8-70B `gpu_llm` worker on node-06 (which has the headroom once its video/compose load is shed or reduced). Failover is **exclusive** on a single card (fp8-70B and CogVideoX cannot co-reside — the 112 GB > 96 GB constraint of AD-02.4 applies equally here), so recovery is degraded single-stage-at-a-time, not full concurrency. Chosen mode is **on-demand rebuild**, not pre-staged standby (simpler, fewer moving parts; slower recovery) — AD-02.12 resolved.
- **Residual SPOFs unchanged:** node-01 (Postgres/API/Redis/scheduler) and node-04 (image/TTS) remain single hosts, consistent with the existing topology.

## AD-02.8 Configuration changes

**node-02 (LLM):** vLLM serves **fp8 Llama-3.3-70B** (TP=1, served-name `llama-3.3-70b`, fp8 KV, `max-model-len` to KV headroom, target 128K). Worker `IVGS_VLLM_PRIMARY_MODEL`/`VLLM_SERVED_NAME`: `qwen-1.5b → llama-3.3-70b`. Remove CogVideoX + `gpu_video` from this node.

**node-03 (video):** remove vLLM + `gpu_llm`; video worker subscribes **`gpu_video` only**.

**node-06 (video + compositor + LLM standby):** deploy a CUDA video worker on **`gpu_video`** (CogVideoX/Wan2.1) **and** the primary FFmpeg/Remotion compositor (composition queue). Keep a **profile-gated, stopped** fp8-70B `gpu_llm` worker definition present for on-demand start on node-02 loss (not running in steady state). `docker-compose.node06.yml` moves from the Intel/oneAPI image set to the CUDA worker + vLLM image set (NVENC available for FFmpeg).

**Weights (ops / `ivgs-models`, §14.1 / AD-01.7):** provision fp8 Llama-3.3-70B (≈ 70 GB) to node-02 local `/data/models`; stage the same fp8 weights reachable to node-06 for the failover rebuild (node-local or NFS model store — AD-02.12 open).

**Queue-subscription delta:** Appendix AD-B.

## AD-02.9 Relationship to AD-01 and resolution of N23-4 (unchanged intent)

N23-4 is **resolved by eliminating the contention at the source** — LLM and video no longer share a card. AD-01 compatibility preserved: `dynamically_loadable = false` for vLLM holds (node-02 serves one fixed model, fp8 Llama-3.3-70B; a node-06 failover instance serves the same one model); the AD-01.6 availability poller reports `llama-3.3-70b` **served** on node-02, CogVideoX/Wan2.1 **available** on node-03 **and node-06**, with no entry implying LLM/video contend for one card. The residency manager's job on these nodes stays trivial (one served model per running process).

## AD-02.10 Rollout / implementation steps

1. **Provision** fp8 Llama-3.3-70B to node-02 `/data/models` (verify space + checksum); stage the same weights reachable to node-06.
2. **Reconfigure node-02** to fp8 Llama-3.3-70B (TP=1, fp8 KV, served-name `llama-3.3-70b`); update worker model env.
3. **Strip cross-workloads:** remove CogVideoX/`gpu_video` from node-02; remove LLM/`gpu_llm` from node-03.
4. **Provision node-06 (CUDA):** deploy the CUDA video worker on `gpu_video` + the primary FFmpeg/Remotion compositor; add a **stopped** profile-gated fp8-70B `gpu_llm` worker for failover.
5. **Recreate** affected containers per node (no `--remove-orphans`).
6. **Verify:** `GET /v1/models` on node-02 → `llama-3.3-70b`; node-03 and node-06 serve CogVideoX (no LLM in steady state); per-node VRAM shows fp8-70B on node-02, CogVideoX on node-03/06 with headroom; concurrent video distributes across node-03/06; a test completion against node-02 succeeds.
7. **Functional check:** storyboard from a representative transcript is on-topic.
8. **Failover drill:** stop node-02; run the documented on-demand rebuild of fp8-70B on node-06; confirm LLM stages resume (degraded concurrency).
9. **Record** the deviation in the SSOT / `OUTSTANDING_WORK.md`; mark **N23-4 resolved** and the **video-recovery gap resolved**.

## AD-02.11 Acceptance criteria

- node-02 serves `llama-3.3-70b` (fp8) via `GET /v1/models`; no CogVideoX on node-02. ✓
- node-03 **and node-06** run CogVideoX/Wan2.1 with headroom; concurrent video distributes across both on `gpu_video` with no code change. ✓
- node-06 runs the primary FFmpeg/Remotion compositor co-resident with video. ✓
- On node-02 loss, the documented on-demand fp8-70B rebuild on node-06 restores LLM stages (degraded, single-stage-at-a-time). ✓
- `transcript_refinement`/`storyboard_generation` route to `gpu_llm` (node-02); `video_generation` routes to `gpu_video` (node-03/06). ✓
- Deviation recorded; **N23-4** and the **video-recovery gap** marked resolved. ✓

## AD-02.12 Open design decisions — resolved in Draft 3

1. **fp8 KV / `max-model-len`** — still validate achievable 128K against real VRAM (Appendix B / AD-01.7).
2. **LLM standby mode — RESOLVED: on-demand rebuild** on node-06 (not pre-staged). Simpler, fewer moving parts; accepted slower recovery.
3. **Weights location/source** — confirm the fp8 Llama-3.3-70B repo/gating; node-local vs NFS store still open; must be reachable to node-06 for failover.
4. **Per-scene video dispatch** — out of scope; now unblocked by a second CUDA video node if pursued.

---

## Appendix AD-A — Per-card VRAM budget (96 GB card)

| Configuration | LLM weights | LLM KV | Video set | Compositor | Per-card | Fits 96 GB? |
|---|---|---|---|---|---|---|
| Spec-literal bf16 70B (TP=2) + CogVideoX | ≈ 70 | +KV (constrained) | ≈ 26 | — | ≈ 112 | **No** |
| node-02 specialized: fp8 70B, no video | ≈ 70 | + fp8 KV (long ctx) | — | — | ≈ 90 | **Yes** |
| node-03 specialized: CogVideoX only | — | — | ≈ 26 | — | ≈ 26 | **Yes** (headroom) |
| **node-06: CogVideoX + FFmpeg/Remotion compositor** | — | — | ≈ 26 | light | ≈ 30–35 | **Yes** (headroom) |
| node-06 **failover mode**: fp8 70B (video shed) | ≈ 70 | + fp8 KV | — | — | ≈ 90 | **Yes** (exclusive of video) |

## Appendix AD-B — Celery queue-subscription matrix (specialized, Draft 3)

| Node | Queues | Resulting workload |
|---|---|---|
| node-02 | **`gpu_llm`** | fp8 Llama-3.3-70B (LLM stages) |
| node-03 | **`gpu_video`** | CogVideoX/Wan2.1 (video) |
| node-04 | image / TTS | Mistral-24B + image/TTS + talking-head *(unchanged)* |
| node-05 | image-fallback / `gpu_llm` (Ollama) / compose-overflow | SDXL fallback, Ollama LLM fallback, FFmpeg overflow (RTX 5080) *(unchanged)* |
| **node-06** | **`gpu_video` + composition** (+ dormant **`gpu_llm`** on-demand) | 2nd CUDA video node + primary FFmpeg/Remotion compositor; fp8-70B failover started only on node-02 loss (RTX 6000 96 GB) |

*Capability is the queue subscription, not the model loaded; adding a worker on a queue is an immediate competing consumer with no code or scheduler change.*

---

*Prepared as an additive deviation under §18 change control. Draft 3 records the node-06 hardware swap (Intel B70 Pro → second RTX 6000 Blackwell 96 GB, CUDA) and redesignates node-06 as a second video node + primary compositor + on-demand fp8-70B failover (Option C). It resolves gap N23-4 (LLM/video contention) and the concurrent-video-recovery gap Draft 2 could not close, while preserving the spec's logical model-to-stage intent. Compatible with the AD-01 Model Management subsystem: the `dynamically_loadable = false` vLLM constraint and the availability poller apply unchanged to the fixed per-node served sets defined here.*
