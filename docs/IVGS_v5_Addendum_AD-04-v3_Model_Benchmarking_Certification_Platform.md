# IVGS v5 — Addendum AD-04-v3: Model Benchmarking & Certification Platform (MBCP)

| | |
|---|---|
| **Document** | Implementation-grounded design specification for a standalone platform that **stores, serves, benchmarks, evaluates, and certifies** self-hostable generative models for the IVGS pipeline. |
| **Version** | **v3.1 — 2026-08-14.** Records delivered state: MBCP is built and in production use, Phases 0–4 delivered, connected mode live, the talking-head bake-off settled. §3.1–§3.18 and Appendix AD-04-v3-A are unchanged and remain authoritative; §3.19–§3.21 are replaced and §3.22–§3.24 are new. The Phase-0 framing throughout §3.18 is historical. Supersedes v3.0 — 2026-06-08, which superseded v2.0 (2026-06-08). Corrects the architecture, removes the reused scheduler, decides the open code-sharing boundary, reconciles weight-serving with reality, makes the standalone/stubbed-AD-01 strategy explicit, and adds a **Phase 0 code-level implementation-plan review gate**. |
| **Classification** | Internal Working Document |
| **Change-control status** | Draft for review (per §18 change-control process) |
| **Source of truth** | The v2 codebase evidence map (Appendix A) is carried forward unchanged except where this document explicitly corrects it. All v3 *additions* are design decisions taken in the 2026-06-08 working session; they are flagged as decisions, not as audited facts. |
| **Depends on** | AD-01 Model Management (the consumer of certifications); the provider abstraction (`shared/providers/__init__.py`, §19.1); IVGS platform conventions (FastAPI, PostgreSQL 17, Celery/Redis, SeaweedFS, Next.js 14, Prometheus/Grafana, Alembic). |
| **Relationship** | MBCP is a **separate, independently deployable companion system**, built in its **own repository**, developed **in parallel with IVGS** and usable **standalone** (not yet wired to AD-01) to make the immediate talking-head model decision. It does not alter the IVGS pipeline, node topology, or storage. |

---

## AD-04-v3.0 What changed from v2, and why

v2 was a strong, codebase-grounded design. v3 keeps the bulk of it — the purpose, the AD-01 seam analysis, the metrics, the data model, the per-stage testing surface, and the IVGS-native UI — and corrects nine specific things surfaced in review. Each correction is auditable below.

1. **Architecture replaced — three planes, not one "mini-IVGS" control plane (§3.5, was v2 §2.5).** v2 deployed everything as a single control-plane VM plus a GPU node, with weight-**serving** lumped into the control plane. v3 decomposes the system into **three logical planes — Serving, Management, Benchmark — split by lifecycle, hardware dependency, and uptime requirement**, with the Benchmark plane **stateless and floating**. *Reason:* serving is a production dependency that must outlive benchmarking and the management UI; the GPU plane is ephemeral and contends with IVGS for the card; a stateless benchmark plane is what makes the dev-time mode-switch (stop IVGS on a node, run the bench VM on that GPU) clean.

2. **VRAM-aware scheduler removed (§3.10, was v2 §2.5 / §2.10).** v2 reused `ivgs-scheduler` for GPU admission. v3 **excises it entirely**: benchmarking runs **serial and isolated** — one model on the card at a time. *Reason:* (a) concurrent residency pollutes the very VRAM and timing measurements the platform exists to produce; (b) the scheduler carries IVGS's open GPU-heartbeat defect (`total_nodes:0`), and benchmarking has no need for admission control. This also removes a "fix IVGS first" dependency.

3. **Model-engine integration named as the true long-pole; spike-first sequencing added (§3.6, §3.18, §3.19).** v2's Phase 1 listed three day-one adapters as if comparable in effort. Only **LatentSync** reuses an existing, proven engine client; **Wan2.2-S2V, daVinci-MagiHuman, and HuMo are from-scratch, research-grade containerized integrations of uncertain effort** — and they are the immediate driver. v3 makes this explicit and **leads the build with a spike** (get one new model running and manually compared against LatentSync) before widening.

4. **Code-sharing boundary decided — vendor-copy, not a shared package (closes v2 §2.19.2).** v3 **snapshots (vendor-copies)** the few stable seams — the LatentSync engine client and named frontend components — into the MBCP repo, and writes everything else fresh. *Reason:* a shared Python/JS package would re-couple the two repos' release cycles and reintroduce the "fix IVGS before lifting" dependency; an isolated own-repo is the goal. The new-model integrations are fresh code regardless.

5. **Weight-serving reconciled with reality — a new IVGS-side fetch path, not a repoint (§3.7a).** v2 implied `download_models.sh` could simply be repointed at the MBCP. In fact `huggingface-cli` targets the HF Hub and **cannot be aimed at an arbitrary origin**; consuming MBCP-served weights requires a **new fetch mechanism on the IVGS side** (in `ivgs-models`). The MBCP serving endpoint is self-contained and testable now; the IVGS-side consumption is a coordinated change **gated on AD-01 and stubbed until Phase 4**.

6. **Standalone mode and stubbed AD-01 seams made explicit (§3.14).** v2 implied standalone operation but never defined the boundaries. v3 adds a dedicated section: the two AD-01 seams (**certification export** and **weight-serve consumption**) are **typed interfaces** with a `Local` implementation (standalone — writes to a `pending_exports` table) and an `AD01` implementation (Phase 4 — real), identical contract, **config-switched binding**. The stubs are **exercised** (the export bundle is fully built and validated, just not transmitted) so they cannot rot into TODOs. Both seams live in the **Serving and Management planes only**; the Benchmark plane has **no** production coupling.

7. **"Promotes to production unchanged" reframed as a deferred (Phase 4) payoff (§3.6, §3.15).** v2 repeatedly asserted certified adapters promote into production unchanged. v3 keeps the adapter-superset shape so it stays *compatible*, but states plainly that the unchanged-promotion property is **only realized once ARCH-1 / `get_provider()` exists**. Until then, MBCP adapters run only in MBCP's own runner.

8. **Factual correction — per-stage table, Stage 6 (§3.9).** v2 listed the Stage-6 task as `tasks.stage5_talking_head.generate_talking_head_task`. The orchestrator's `STAGE_TASK_MAP` dispatches **`tasks.talking_head_task.render_talking_head`**; duplicate talking-head task modules exist (IVGS ledger item **A5**, dead-code). Corrected in the table with a footnote. Immaterial to MBCP, which wraps the engine client, not the Celery task. *(Confirm against the live `STAGE_TASK_MAP` at implementation time.)*

9. **NEW — Phase 0 review gate (§3.18).** v3 inserts a **Phase 0** ahead of Phase 1. The other agent produces a **code-level implementation plan** — repository/module layout, DDL schema, API contracts, the adapter interface, the stub boundaries, and the **load-bearing code skeletons** (adapter base class, comparison-framework skeleton, weight-store API) — for review **before any build begins**. This replaces the earlier idea of writing the *entire* system as un-implemented code and then reviewing it: the new-model integrations cannot be written correctly on paper, and reviewing thousands of never-run lines is low-leverage. Phase 0 reviews the contracts and load-bearing pieces (where on-paper review pays off); the rest is built in **incremental vertical slices**, model integrations developed iteratively against running models.

**Process framing (decisions taken this session).** IVGS and MBCP proceed on **parallel tracks**. MBCP is built **standalone** and is sufficient on its own for the LatentSync decision, which needs nothing from AD-01. Build is **incremental, spike-first**, grown in its own repository with per-slice review.

---

## AD-04-v3.1 Purpose

AD-01 defines a Model Store — a curated allow-list of approved, selectable models — but is explicit that it does **not** validate them:

- AD-01.2 (non-goals): *"The subsystem does not benchmark a model, measure its real VRAM footprint, or verify CUDA/driver/quantization/engine compatibility. It assumes every model in the store has already passed an external acceptance process."*
- AD-01.7: *"This subsystem is an allow-list of pre-vetted models, not a validation harness … a model may only reach APPROVED after passing an acceptance process performed outside this system, against the actual target hardware."*

That external acceptance process has, until now, been undefined. **The MBCP is that process, built as a durable platform** so that choosing and validating a model for IVGS is repeatable, measurable, auditable, and comparable across candidates and over time. Two operator-driven purposes extend it: a **model origin store** that holds validated weights and serves them to AD-01 (so the production fleet does not re-download from Hugging Face), and an **isolated model sandbox** where operators run a single candidate against their own uploaded inputs for any stage.

**Immediate driver (unchanged).** The talking-head decision: LatentSync's lip-sync articulation is not viable for production (confirmed visually this session against a Stage-7 draft and a Stage-8 1080p final). Candidate replacements (Wan2.2-S2V, daVinci-MagiHuman, HuMo, MuseTalk) must be compared on real hardware, at real resolutions, on representative content, on both generation cost and output quality. This decision is on M1's *quality* critical path and is what the standalone MBCP exists to settle first.

## AD-04-v3.2 Scope and non-goals

**In scope:** a standalone benchmarking/evaluation/certification platform; a **model store + weight server** that feeds AD-01; a model **adapter framework** built on the existing provider contract; an **isolated single-model sandbox** for operator-uploaded inputs; a versioned **test corpus**; **benchmark run** orchestration across a matrix of models × fixtures × resolutions × parameter sets, executed **serially per GPU**; **performance** measurement (generation time, real VRAM, throughput, failure modes); **automated quality** metrics; **human/subjective** evaluation; a **certification** workflow with auditable records; and **export** of certifications and weight references into AD-01.

**Out of scope / non-goals:**
- **Serving production traffic.** The MBCP renders only for evaluation. Production generation remains the IVGS pipeline's job.
- **Replacing AD-01.** The MBCP feeds the Model Store; it is not the Model Store.
- **Training or fine-tuning models.** Evaluation only.
- **Editing the IVGS pipeline.** No change to the eight stages, node roles, or storage.
- **Concurrency / scheduling (new in v3).** The MBCP deliberately does **not** schedule concurrent GPU work. Benchmarks run **one model at a time** for clean measurements. It reuses no admission-control microservice.

## AD-04-v3.3 Relationship to AD-01 and the IVGS platform (verified seams)

This is the load-bearing section; the rest follows from it.

**1. The MBCP is AD-01.7's external acceptance process.** An MBCP **certification record** is the external acceptance reference that AD-01.7.2 records in `model_approvals` (`attested_by`, `vetting_reference`, `checklist` jsonb, `attested_at`). The MBCP certification ID becomes `model_approvals.vetting_reference`; the MBCP scorecard becomes the `checklist` snapshot.

**2. The provider/adapter contract is the shared seam — real but incomplete.**
- **Exists:** `shared/providers/__init__.py` defines six abstract provider interfaces — `LLMProvider`, `ImageProvider`, `TTSProvider`, `VideoProvider`, `STTProvider`, `TalkingHeadProvider` — each with `@abstractmethod` generation calls plus, for `TalkingHeadProvider`, `check_health()`, `vram_requirement_mb()`, and `provider_name()`. Parameters/results are dataclasses.
- **Does NOT exist yet:** a selection-aware `get_provider(stage, job_id, scene_id?)` factory. Task code imports concrete engine clients directly (e.g. `from clients.latentsync_client import LatentSyncClient`). **Gap ARCH-1 remains open.**

The MBCP **adapter** (§3.6) is built as a **superset of these ABCs plus the engine-client construction pattern**. Building adapters here advances ARCH-1, but — per correction #7 — the "same code runs in production unchanged" property is realized only once `get_provider()` lands (Phase 4).

**3. Measured, not declared.** AD-01.5.2 records `vram_gb` as "Declared … advisory, not measured here." The MBCP measures **real peak VRAM** (DCGM/`nvidia-gpu-exporter`) under **isolated, single-model** load and emits it as ground truth, correcting the Model Store entry and the `ivgs-models/README.md` Appendix B matrix. (Isolation matters precisely so the figure is the model's own footprint, not a contended total.)

**4. Representative by construction.** Because results must transfer to production, the MBCP mirrors the IVGS stack: the same engine clients where they already exist (`ivgs-workers/clients/`), the same NVIDIA Blackwell + CUDA ≥ 12.4 / driver ≥ 570.x profile, the same resolutions (480p draft → 1080p/4K final), the same content types.

**Handoff, end to end (Phase-4 wiring; stubbed in standalone mode — §3.14):**
```
MBCP registers candidate → ingests/verifies weights (checksum) → runs benchmark/checklist
SERIALLY on representative fixtures + hardware → scores (automated + human) → certification
→ CERTIFICATION RECORD (stage, tier, resolution, hardware/engine/quantization, measured VRAM,
  scorecard) + WEIGHT REFERENCE → export:
    standalone:  written to pending_exports (Local seam)        ← today
    Phase 4:     certification ID → model_approvals.vetting_reference (CANDIDATE→APPROVED)
                 measured VRAM    → corrects models.vram_gb + Appendix B
                 weight_ref       → models.weights_ref / weights_checksum (served from MBCP origin)
                 → AD-01 selects/serves via the (now shared) provider factory.
```

## AD-04-v3.4 Design principles

1. **Representative over convenient.** Mirror the IVGS stack and hardware so measurements transfer.
2. **Isolated from production.** Own deployment, own GPU; the Benchmark plane never touches the IVGS render path.
3. **Serial and clean (new).** Benchmarks run one model at a time. Uncontended measurement is worth more than throughput here.
4. **Durable and extensible, not a script.** Models, metrics, fixtures, certifications, and stored weights are first-class persisted entities.
5. **Reproducible and auditable.** Every run is tagged with adapter version, engine/driver/CUDA versions, hardware profile, fixture version, parameters, and (where supported) seed.
6. **Adapter-first.** The adapter/provider contract is the single most important reusable artifact.
7. **Quality is multi-signal.** Performance, automated quality proxies, and blind human evaluation are captured together; thresholds combine them.
8. **Vendor-copy, don't couple (new).** Lift only stable, proven seams as snapshots into the MBCP repo; write everything else fresh; never lift half-finished code; no shared package between the repos.
9. **Stateless benchmarking (new).** The Benchmark plane persists nothing locally — weights are a pulled cache, fixtures come from Management, artifacts and results are pushed back. This is what lets it float, swap hardware, and toggle off.
10. **Visually native.** The UI is built from the *same* design system as IVGS (§3.16).
11. **Self-hosted mandate preserved.** All inference on-prem. The only outbound dependency is the initial, operator-initiated weight acquisition; thereafter the MBCP is the origin.

## AD-04-v3.5 System architecture — three planes (replaces v2 §2.5)

The MBCP is decomposed into **three logical planes**, separated by what they depend on and how available they must be. The decomposition is logical; physical placement varies between dev and prod (below) but the boundaries do not.

### Serving plane — always-on, GPU-free, production-critical
The on-prem **weight origin**. The simplest, most stable, least-changing component, because once AD-01 pulls from it, it is a production dependency.
- **Weight store** — versioned, checksummed weight+config bundles on an NFS/large volume.
- **Read-only fetch surface** — what the Benchmark plane and (Phase 4) AD-01's `ivgs-models` tooling pull from. Serves **certified** bundles to production; **candidate** bundles to the Benchmark plane.
- **Authenticated ingest/publish endpoint** — the *only* writer is the Management plane (ingest a candidate; publish/promote to certified at certification time). Defined as an API call, not a shared mount, so it works whether Serving is co-located with Management (dev) or peeled onto its own VM (prod).
- No GPU. No model code. Must survive Management and Benchmark being down.

### Management plane — operator-facing, durable state, always-on-ish
The registry, the results, the certifications, the GUI, and run orchestration.
- **FastAPI backend** — `/api/v1/*`, 1-hour JWT + refresh, RBAC (`admin`/`operator`/`viewer`), `PaginatedResponse[...]`, audit middleware, Alembic migrations on startup.
- **PostgreSQL 17** — the durable registry/results/certification store (§3.13). IVGS ORM conventions.
- **SeaweedFS** — generated evaluation artifacts and uploaded fixtures (`hot/warm/cold/archive`).
- **Redis + Celery Beat** — the broker and the dispatcher of benchmark cells to the Benchmark plane.
- **Next.js 14 UI + Nginx + Prometheus/Grafana** — the operator surface and telemetry.
- Can take maintenance/upgrades without breaking production weight serving.

### Benchmark plane — ephemeral, RTX-dependent, stateless, floating
Pure compute. Spun up on whatever RTX PRO 6000 Blackwell node is free; torn down when idle.
- **Celery GPU worker (concurrency 1, prefetch 1)** + the **engine stack** (ComfyUI, vLLM, Coqui/Kokoro, LatentSync, Wan2.x, MagiHuman, HuMo, MuseTalk, CogVideoX, FFmpeg/Remotion as needed per phase).
- **Holds no durable state**: pulls weights from Serving (cache), pulls fixtures from Management's SeaweedFS, runs `prepare()→generate()→unload()` **serially**, pushes artifacts to Management's SeaweedFS and results to Management's API/Postgres.
- No admission control, no scheduler. One model resident at a time.

### The network contract between planes
```
                ┌──────────────────── Management plane ────────────────────┐
   operator ──▶ │ Next.js UI ─ Nginx ─ FastAPI(/api/v1, JWT+RBAC) ─ PG17    │
                │                         │            │                    │
                │           Redis(broker)/Celery-Beat  SeaweedFS(artifacts, │
                │                         │            fixtures) + monitoring│
                └─────────────┬───────────┬────────────┬───────────────────┘
                  ingest/publish│   dispatch│    push artifacts + results
                  (auth, write) │  (broker) │            ▲
                                ▼           ▼            │
                ┌─ Serving plane ─┐   ┌──── Benchmark plane (ephemeral) ────┐
                │ Weight store    │   │ Celery GPU worker (concurrency 1)   │
                │ read-only fetch ─┼──▶│ engines + adapters (serial)         │
                │ (certified→prod,│pull│ weights=cache, fixtures pulled,     │
                │  candidate→bench)│wts │ artifacts/results pushed back       │
                │ auth ingest ◀───┘   └─────────────────────────────────────┘
                └────────┬────────┘                 [floats to any free RTX 6000]
                         │ (Phase 4) read-only certified-weight fetch
                         ▼
                   AD-01 / IVGS production fleet   (never touches the Benchmark plane)
```
Production only ever touches the **Serving** plane (weight pulls) and, asynchronously, a **certification export** from **Management**. It never touches the Benchmark plane. The two stubbed AD-01 seams (§3.14) therefore live in Serving and Management only.

### Deployment flexibility — same architecture, dev → prod
- **Dev:** Serving + Management **co-located** as separate containers in one node-01-class VM (Serving writes via the localhost ingest endpoint); the **Benchmark plane floats** — run it on, e.g., node-03 after stopping IVGS there, point it at Management/Serving over the LAN, tear it down afterward.
- **Prod:** **Serving peels** onto its own always-on VM (or the dedicated box); the **Benchmark plane** gets dedicated hardware. Management stays as is.
- Because the planes are **independently deployable from day one** (three compose files, three env templates), the prod peel is a configuration change, not a rewrite.

### Operational caution — GPU release on the dev mode-switch
When you stop IVGS on a node to run the Benchmark plane on that GPU, **fully release the card first**: stop IVGS's GPU containers and confirm VRAM is actually freed (`nvidia-smi`) before the bench VM claims it via Proxmox passthrough. A lingering IVGS process holding VRAM is the obvious foot-gun on shared dev hardware.

## AD-04-v3.6 Model adapter framework (the core)

Each model is wrapped in an **adapter** implementing a standard interface that is a **superset of the `shared/providers/` ABCs**, wrapping the same engine-client construction the workers use (async context managers in `ivgs-workers/clients/`).

| Method | Maps to existing contract | Function |
|---|---|---|
| `describe() -> AdapterManifest` | (new, superset) | Static manifest: engine + pinned version, model/version, `weights_ref`, input modalities (image/audio/text/pose), supported stages, supported resolutions, **declared** VRAM, quantization, license. |
| `prepare(hardware_profile)` / `load()` | analogous to engine-client `__aenter__` | Load weights onto the target engine from the Serving plane; report load success and **resident VRAM**. |
| `generate(inputs, params) -> (artifact, telemetry)` | superset of `*.generate()` / `synthesize()` / `render()` | Run **one** generation; return the artifact plus measured telemetry (wall time, GPU compute time, **peak VRAM**, GPU util, exit status). |
| `unload()` | analogous to engine-client `__aexit__` | Release for the next candidate (`dynamically_loadable` engines) or note fixed-process serving (vLLM cannot hot-swap — per `llama-3.3-70b.yaml` single-`served-model-name` config and AD-01.9). |
| `check_health() -> bool` | from `TalkingHeadProvider.check_health()` | Liveness probe before a run. |
| `vram_requirement_mb() -> int` | from `TalkingHeadProvider.vram_requirement_mb()` | **Declared** hint, used for a pre-run headroom sanity check only — **not** for admission/scheduling (no scheduler in v3). Ground-truth VRAM comes from `generate()` telemetry. |

**Reference data shapes already in the codebase** (so production parity is exact): `TalkingHeadParams` (`scene_image_path` 1920×1080 PNG, `voiceover_audio_path` WAV 48 kHz mono, `reference_clip_path` MP4/MOV, `output_width/height/fps` 1920/1080/30, `alignment_threshold` 0.85) → `TalkingHeadResult` (`video_data`, `duration_seconds`, `alignment_score`, `model`); `TTSParams`/`AudioResult` (`speaker_wav`, `speed`, `sample_rate` 48000); `ImageParams`/`ImageResult`; `VideoParams`/`VideoResult`; `LLMParams`/`LLMResponse` and `STTParams`/`STTResult` (large-v3, word timestamps) for the generalization phase.

**Day-one adapters target the talking-head decision — with honest effort labels (correction #3):**
- **LatentSync** — *reuses* the existing, proven `latentsync_client.py` (vendor-copied). Low risk; this is the worked reference adapter in Phase 0.
- **Wan2.2-S2V** and **daVinci-MagiHuman** — **from-scratch containerized integrations.** No existing client. Research-grade; effort uncertain. These are **spike work**, developed iteratively against the running models, not written on paper.
- **HuMo, MuseTalk** — comparators, same from-scratch caveat.

The framework generalizes to every IVGS engine class in Phase 5.

## AD-04-v3.7 Model store, serving, and the upload sandbox

### AD-04-v3.7a Weight store and serving (lives in the Serving plane; correction #5)

**Problem.** IVGS provisions weights with `huggingface-cli download …` to `/mnt/ivgs-shared/models` (`ivgs-models/download_models.sh`), verified with `sha256sum -c checksums.sha256`. This couples the fleet to HF availability, gated-repo tokens, and upstream drift.

**Solution.** The MBCP Serving plane is the **on-prem origin** for validated weights:
- **Ingest (Management → Serving).** On candidate registration, an operator-initiated job pulls weights once (HF or operator upload), records a **SHA-256 checksum**, source URL, engine + pinned version, and quantization, and writes the bundle into the Serving store as a **candidate** bundle. Mirrors AD-01's `models.weights_ref` / `models.weights_checksum`.
- **Serve (read-only).** The Serving plane exposes a read-only fetch surface: the **Benchmark plane** pulls **candidate** bundles to benchmark; (Phase 4) AD-01 pulls **certified** bundles to production.
- **Honest IVGS-side consumption (the v2 correction).** `download_models.sh` **cannot simply be repointed** — `huggingface-cli` only speaks to the HF Hub. Consuming MBCP-served weights requires a **new fetch mechanism in `ivgs-models`** (an HTTP/rsync/filer client against the Serving endpoint, with `checksums.sha256` generated by the MBCP at certification time). That IVGS-side change is a **coordinated, AD-01-gated** piece of work and is **stubbed until Phase 4** (§3.14). The MBCP serving endpoint itself is self-contained and testable now.
- **Per-engine layouts preserved.** vLLM serve YAML, ComfyUI workflow JSON, TTS YAML, Ollama `Modelfile` — stored as a *config + weights* pair in one versioned bundle.
- **Provenance guarantee.** The benchmark runs against the stored bytes and the certification embeds that checksum, so "the model that was certified" and "the model production serves" are byte-identical.

**Isolation vs serving (reconciled).** The Serving plane is the **one deliberate, controlled outbound bridge**. It is read-only to consumers, holds no GPU, and is the only plane production ever contacts. The Benchmark plane — where unstable, experimental model loads happen — remains fully isolated and is never reachable from production. Serving the fleet and isolating experimentation are therefore not in tension: they are split across two planes by design.

### AD-04-v3.7b User-upload isolated testing sandbox (operator requirement #4)

Operators upload their own representative inputs and test a **single model in isolation**, outside any full pipeline run, reusing the existing IVGS upload machinery:
- **Component reuse (vendor-copied):** the `AssetUploader` React component (drag-and-drop, multi-file, validation, progress).
- **Storage reuse:** uploads land in SeaweedFS as MBCP `fixtures` with SHA-256 `content_hash` dedup.
- **Accepted input types by stage output type:** **video clips** (reference/source clips — `reference_clip` asset type and `TalkingHeadParams.reference_clip_path` exist); **text** (transcripts, narration); **storyboard JSON** (Stage-2-shaped scene arrays driving Stage 3/5/6 directly); **audio** (narration, speaker reference for TTS cloning via `TTSParams.speaker_wav`).
- **Isolated run:** targets exactly one adapter and one (or a few) inputs, runs `prepare()→generate()→unload()`, captures artifact + telemetry, and shows the output immediately in the per-stage comparison surface (§3.16). No certification implied; sandbox artifacts are `ephemeral`.

## AD-04-v3.8 Test corpus (fixtures)

A **versioned, immutable** library of standardized inputs so runs are comparable across models and over time, stored like assets (SeaweedFS + `content_hash` dedup) and indexed in `fixtures`:
- **Reference media** — presenter images spanning photoreal/stylized, varied lighting/framing; source clips for video-edit models.
- **Audio** — narration at representative lengths (≈5 s, 30 s, 75 s, multi-minute), multiple voices/prosody, IVGS languages, each with a **known transcript** so ASR round-trip WER is computable.
- **Prompts** — paired text for text-conditioned models.
- **Target resolutions** — 480p / 720p / 1080p / 4K, matching IVGS draft/final profiles.
- **Categories** — talking-head, scene-fill video, image, TTS — organized so a suite targets a single stage.

A **"golden suite"** pins the canonical comparison set. Operator sandbox uploads may be **promoted** to a versioned fixture by an admin.

## AD-04-v3.9 The eight pipeline stages — what the MBCP tests, per stage

Carried from the v2 audit, with the Stage-6 task name corrected (#8). The MBCP provides an isolated testing suite and a side-by-side comparison surface for **each** stage's output type.

| IVGS Stage | Engine(s) / model(s) | Celery task | Queue | Input → Output | MBCP output type compared |
|---|---|---|---|---|---|
| 1. Transcript Refinement | vLLM Llama 3.3 70B | `tasks.stage1_transcript.refine_transcript_task` | `gpu_llm` | `TranscriptRefinementInput` → `…Output` | Text diff |
| 2. Storyboard Generation | vLLM Llama 3.3 70B (JSON) | `tasks.stage2_storyboard.generate_storyboard_task` | `gpu_llm` | `StoryboardGenerationInput` → `…Output` | Structured JSON scenes |
| 3. Media Generation | FLUX.1 (ComfyUI) + CogVideoX; vLLM Mistral 24B prompts | `tasks.stage3_images.generate_scene_images_task` | `gpu_image` | `Stage3Input` → `Stage3Output` (`clip_score`) | Image / video clip |
| 4. Composition Manifest | API-driven (no GPU) | `tasks.stage4_manifest.build_composition_manifest` | `default` | `job_id/project_id` → `manifest_id` | Timeline manifest (JSON) — non-model |
| 5. Audio / TTS | Coqui XTTS v2 (Kokoro fallback) | `tasks.stage4_voiceover.generate_voiceover_task` *(historical name; matches dispatch)* | `gpu_tts` | `Stage4Input` → `Stage4Output` (`snr_db`, `clipping_pct`) | Audio waveform |
| 6. Talking Head | LatentSync (SadTalker fallback) | **`tasks.talking_head_task.render_talking_head`** *(corrected — see note)* | `gpu_talking_head` | `Stage5Input` → `Stage5Output` (`alignment_score`, `render_mode`) | Lip-synced video |
| 7. Prototype Draft | FFmpeg + Remotion (720p) | `tasks.prototype_draft_task.assemble_prototype_draft` | `composition` | `Stage7Input` → `Stage7Output` | Composed 720p — non-model |
| 8. Final Render | FFmpeg segment-based (1080p+4K) | `tasks.final_render_task.render_final` | `composition` | `Stage8Input` → `Stage8Output` | Composed 1080p/4K — non-model |

> **Stage-6 note (#8).** v2 listed `tasks.stage5_talking_head.generate_talking_head_task`. The orchestrator's `STAGE_TASK_MAP` dispatches `tasks.talking_head_task.render_talking_head`; the `stage5_talking_head`/`stage6_talking_head` modules are duplicate dead-code (IVGS ledger **A5**). The MBCP wraps the LatentSync **engine client**, not the task, so this does not affect the adapter — but the spec should be correct. Confirm against the live `STAGE_TASK_MAP` when implementing.

Stages 4, 7, 8 are deterministic composition/manifest steps, exposed for regression (e.g. encoder settings); the model-certification metrics (§3.11) apply to stages 1–3, 5, 6. The talking-head bake-off targets **Stage 6**.

## AD-04-v3.10 Benchmark run orchestration (scheduler removed — correction #2)

A **run** is a matrix `{ adapter(s) × suite (fixtures × resolutions × parameter sets) × hardware profile }`. The Management FastAPI records the run; Celery Beat/queues dispatch each cell to the Benchmark plane; the worker loads the adapter, generates, captures artifact + telemetry, and persists results to Management.

**Execution discipline (v3):**
- **Serial, single-model.** The Benchmark worker runs at **concurrency 1, prefetch 1**: one cell, one resident model at a time. A matrix is a *sequence* of cells on a card. *This is deliberate* — uncontended VRAM and timing are the product; concurrency would corrupt them.
- **No admission control.** `ivgs-scheduler` and `acquire_gpu_reservation(...)` are **not used**. (They exist for production concurrency and carry the open heartbeat defect.) A simple pre-run headroom check against `vram_requirement_mb()` is sufficient.
- **Per-cell checkpointing** so partial failure of one cell never discards completed cells (the Stage-8 independent-retry philosophy, applied per cell).
- **Idempotency** via request hashing (`compute_request_hash()` / SHA-256), so an identical cell re-run is a cache hit.
- **Re-runnable as regression** — re-certify on an engine/driver/CUDA/model-version change and diff against the prior scorecard.

Multiple Benchmark nodes may run in parallel for true model × hardware-profile matrices, but **each node stays serial** internally; cross-node parallelism never shares a card.

## AD-04-v3.11 Metrics

**Performance / cost** (per cell): generation wall-time, GPU compute time, **real peak VRAM** (DCGM/`nvidia-gpu-exporter`, measured under isolated load), GPU utilization, throughput (output-seconds per compute-second), real-time factor, failure/OOM rate. These feed AD-01's advisory `vram_gb` and the Appendix B matrix.

**Automated quality** (per model class):
- *Lip-sync (Stage 6):* LSE-C / LSE-D (SyncNet-style) and audio-video sync offset (complements LatentSync's existing `alignment_score` / 0.85 threshold).
- *Articulation proxy (Stage 6):* **ASR round-trip WER** — re-transcribe generated speech with the IVGS WhisperX `STTProvider` (large-v3) and compare to the known fixture transcript. A direct, automatable signal for the exact failure LatentSync exhibits.
- *Visual fidelity (Stage 3/6):* FID / FVD against reference distributions.
- *Identity preservation (Stage 6):* ArcFace cosine similarity vs the reference image.
- *Text alignment (Stage 3):* CLIP similarity (Stage 3 already computes `clip_score`).
- *Audio quality (Stage 5):* SNR and clipping % (Stage 5 emits `snr_db`/`clipping_pct`; thresholds SNR > 20 dB, clipping < 1%).
- *Temporal:* flicker/consistency.

**Human / subjective** (decisive for "realistic"): blind **pairwise A/B** (Elo / Bradley-Terry) and **Likert** across sync, naturalness, identity, artifacts; multi-rater.

**Compatibility / robustness:** the AD-01.7.1 checklist captured as structured `jsonb` — engine/CUDA/driver/quantization fit (Blackwell, driver ≥ 570.x / CUDA ≥ 12.4), real headroom, determinism across repeats.

## AD-04-v3.12 Scoring and certification workflow

Per-cell metrics aggregate into a **model scorecard** (per stage × resolution tier × hardware profile). A **certification decision** applies stage/tier-appropriate thresholds — a *production talking-head* might require LSE-C ≥ floor, ASR WER ≤ ceiling, human pairwise win-rate ≥ bar vs the incumbent, measured VRAM within node-04's real headroom; a *prototype/draft* tier optimizes for speed within a looser floor (the two-tier draft/production split, mapping to `PROTOTYPE_DRAFT` 720p vs `FINAL_RENDER` 1080p/4K).

**Lifecycle:** `REGISTERED → BENCHMARKING → SCORED → CERTIFIED | REJECTED`. A **CERTIFIED** record is scoped (stage, tier, resolution, hardware + engine + quantization), carries **measured VRAM**, the **weight checksum**, and a scorecard reference, and is **expirable/revocable**. It is the unit that exports as the AD-01 attestation (§3.14, §3.15).

## AD-04-v3.13 Data model (own PostgreSQL 17)

IVGS conventions throughout: `UUID` PKs (`uuid_generate_v4()`), `DateTime(timezone=True)` audit columns (`now()`), PG `ENUM` types in Alembic migrations, `jsonb` detail.

| Table | Purpose (key fields) | Plane |
|---|---|---|
| `models` | Candidate registry — `name`, `family`, `version`, `engine`+version, `weights_ref`, `weights_checksum`, modalities, supported stages, `license`, `declared_vram_gb`, `quantization`, `status` ENUM | Mgmt |
| `adapters` | Adapter impl ref + version, `model_id`, param schema (`jsonb`) | Mgmt |
| `stored_weights` | On-prem weight bundle — `model_id`, NFS/filer ref, `sha256`, `engine_config_ref`, `source_url`, `size_bytes`, `tier` (`candidate`/`certified`), `ingested_at` | **Serving** |
| `fixtures` | Versioned inputs — `kind`, media ref, `transcript`, `category` (stage), `content_hash`, metadata | Mgmt |
| `test_suites` | Named fixture sets + resolution tiers + parameter grids | Mgmt |
| `hardware_profiles` | GPU model, count, VRAM, driver, CUDA, engine versions | Mgmt |
| `benchmark_runs` | Run config (suite, adapters, params, hw profile), `mode` (`matrix`/`sandbox`), status | Mgmt |
| `run_results` | Per cell — `artifact_ref`, `gen_time_s`, `gpu_time_s`, `vram_peak_gb`, `gpu_util`, status, error (`jsonb`) | Mgmt |
| `quality_metrics` | `lse_c`, `lse_d`, `sync_offset_ms`, `wer`, `fid`, `fvd`, `arcface_id`, `clip_sim`, `snr_db`, `clipping_pct`, … | Mgmt |
| `human_evaluations` | Rater, mode, target result(s), scores, comments | Mgmt |
| `certifications` | `model_id`, `ivgs_stage`, `tier`, `resolution`, `hardware_profile`, `thresholds_met` (`jsonb`), `measured_vram_gb`, `weights_checksum`, `scorecard_ref`, `certified_by/at`, `expires_at`, `revoked` — **the export unit** | Mgmt |
| `pending_exports` *(new — standalone stub, §3.14)* | The export bundle held locally when running standalone — `certification_id`, `bundle` (`jsonb`), `created_at`, `transmitted` (bool), `transmitted_at` | Mgmt |
| `artifacts` | Generated outputs in SeaweedFS + metadata (`storage_tier`, `content_hash`, `reference_count`) | Mgmt |
| `audit_log` | Before/after snapshots of every store mutation, approval, certification | Mgmt |

At Phase 4 the `certifications` row maps onto AD-01's `model_approvals` and corrects `models.vram_gb`/`quantization`; `stored_weights` (certified tier) populates AD-01 `models.weights_ref`/`weights_checksum`.

## AD-04-v3.14 Standalone mode and stubbed AD-01 seams (NEW — correction #6)

The MBCP runs **standalone** today and connects to AD-01 at **Phase 4**. There are exactly **two** seams between MBCP and AD-01, both in the Serving/Management planes; the Benchmark plane has none.

**Seam 1 — Certification export (Management).** When a model is CERTIFIED, MBCP builds the **export bundle** and hands it across a typed interface:
```
class CertificationExporter(Protocol):
    def export(self, bundle: ExportBundle) -> ExportReceipt: ...

# ExportBundle (typed): model metadata, measured_vram_gb, engine/quantization profile,
#   capability tags (AD-A: visual_style, subject_affinity, motion_profile, voice_profile,
#   language, quality_bias), scorecard_ref, certification_id, weight_ref + checksum.
```
- `LocalPendingExport` (standalone, **today**): validates the bundle, writes it to `pending_exports`, returns a receipt. The bundle is **fully built and validated** — the boundary is *exercised*, not a TODO.
- `AD01Export` (**Phase 4**): POSTs the bundle to AD-01 — certification ID → `model_approvals.vetting_reference`, scorecard → `model_approvals.checklist`, measured VRAM → `models.vram_gb`, weight bundle → `models.weights_ref`/`weights_checksum`.

**Seam 2 — Weight-serve consumption (Serving).** The Serving plane's read-only fetch endpoint and bundle layout exist now and are testable now (the Benchmark plane already pulls from it). The **IVGS-side consumer** — the new fetch mechanism in `ivgs-models` (§3.7a) — is the stubbed half: in standalone mode there is no production consumer; at Phase 4 AD-01's tooling pulls certified bundles and verifies checksums.

**Binding switch.** Which implementation is active is a single configuration flag (`MBCP_AD01_MODE=local|connected`). No code path changes; only the bound implementation does. This keeps the stubs honest (the same call site runs in both modes) and makes Phase 4 an implementation of a *defined* contract, not a retrofit.

## AD-04-v3.15 Integration & export to AD-01 (Phase 4 activation of §3.14)

A CERTIFIED model produces the §3.14 **export bundle**. At Phase 4, `AD01Export` ingests it as a `CANDIDATE` registration whose attestation (AD-01.7.2) is the MBCP certification; `stored_weights` (certified tier) becomes the served origin. Because the adapter is built to the `shared/providers/` contract, the certified adapter is the same code the IVGS provider factory (`get_provider()`, once ARCH-1 lands) will use — **but that "unchanged promotion" property is realized only when ARCH-1 exists** (correction #7). Re-certification re-issues the attestation, re-corrects the VRAM matrix, and re-publishes the weight checksum.

## AD-04-v3.16 User interface (Next.js 14) — matched to IVGS

Built from the **same design system** as IVGS (vendor-copied tokens/primitives) so it is visually native.

**Stack & theme (from `ivgs-frontend/`):** Next.js 14.2.15, React 18.3.1, TypeScript, App Router; Tailwind 3.4.13 `darkMode:"class"`, body `bg-gray-950 text-gray-100`; brand **`ivgs`** indigo (primary `#4c6ef5`, active nav `bg-ivgs-600/20 text-ivgs-300`); state badges (`draft #868e96`, `progress #4c6ef5`, `review #f59f00`, `complete #40c057`, `error #fa5252`); GPU-temp colors; Inter + JetBrains Mono; `lucide-react`, SWR, Chart.js + react-chartjs-2, react-beautiful-dnd, `clsx`, zod; `fade-in`/`slide-up`/`pulse-soft`/`spin-slow` animations.

**Layout primitives to reuse (vendor-copied):** `Header` (sticky, role-gated nav via `ROLE_LEVEL`), context-aware `Sidebar` (`w-56`, section→items with `minRole`), `Footer`, `Toast`/`ToastProvider`, `LoadingSpinner`, `StateBadge`, `ErrorBoundary`, `ProtectedRoute`, `AuthContext`/`useAuth`, and the typed `api-client.ts` (Bearer injection, 401→refresh→retry, `PaginatedResponse<T>`).

**Navigation — a `bench` Sidebar context (operator requirement #6):**
```
Testing Suites (by stage)        Evaluation                 Platform
  • Stage 1 — Transcript           • Run Builder              • Model Registry
  • Stage 2 — Storyboard           • Leaderboards             • Weight Store
  • Stage 3 — Media (Image/Video)  • Scorecards               • Fixtures & Suites
  • Stage 5 — Audio / TTS          • Human-Eval Queue         • Hardware Profiles
  • Stage 6 — Talking Head ★       • Certifications & Export   • Audit Log
  • Stage 7/8 — Composition (regression)
```
Each "Testing Suites" item routes to a stage-scoped workspace (`/bench/stages/[stage]`) combining the upload sandbox (§3.7b), a run trigger, and the side-by-side comparison surface for that stage.

**Side-by-side comparison, per stage output type (operator requirement #5).** A single comparison framework renders **N-up** outputs from different models for the same fixture/input, specialized by output type:

| Stage output type | Comparison renderer (built on vendor-copied components) |
|---|---|
| **Lip-synced video** (Stage 6) | **Synchronized N-up `VideoPlayer`** — multiple instances with a shared transport (play/seek/scrub drives all panes), native-resolution playback, per-pane overlays of `alignment_score`, LSE-C/D, ASR-WER. **The decisive surface for the LatentSync decision.** |
| **Image / video clip** (Stage 3) | Side-by-side grid with per-pane `clip_score`, FID/FVD, synchronized zoom/pan. |
| **Audio waveform** (Stage 5) | Stacked synchronized players with waveform, per-pane `snr_db`/`clipping_pct`/WER, A/B blind toggle. |
| **Structured text/JSON** (Stages 1–2) | Two/three-column diff with token counts and schema-validity badges. |
| **Composed video** (Stages 7–8) | Synchronized N-up `VideoPlayer` with a 720p/1080p/4K quality selector for encoder regression. |

Every pane carries model name, adapter version, hardware profile, and measured VRAM/time, so a side-by-side judgment is always traceable to a `run_result`. The comparison framework's data contract and the synchronized-`VideoPlayer` skeleton are **load-bearing Phase 0 deliverables** (§3.18.F).

## AD-04-v3.17 Hardware & deployment (three planes, Dockerized)

Same Docker conventions as the IVGS monorepo: multi-stage Dockerfiles (backend/workers on `python:3.12.8-slim-bookworm`, UI on `node:20.18-alpine3.20`), non-root `ivgs` user, `HEALTHCHECK`s, pinned image SHA digests via `*_TAG` env vars, the `x-common-*` / `x-gpu-resources` YAML anchors, Nginx modeled on `configs/nginx/nginx.conf`, Celery `broker=redis://…/0`, `result_backend=db+postgresql+psycopg2://…`, queues `bench_llm`/`bench_image`/`bench_video`/`bench_tts`/`bench_talking_head`/`eval`/`default`.

**Three independently deployable units (one compose file + one env template each):**
- **Serving** — weight store + read-only fetch + auth ingest. CPU only. Always-on. Smallest, most stable image.
- **Management** — FastAPI/Postgres17/SeaweedFS/Redis/Celery-Beat/Next.js/Nginx/monitoring (Prometheus + `nvidia-gpu-exporter :9400` + `node-exporter :9100`, 15s scrape, 30d retention). CPU only.
- **Benchmark** — GPU compose modeled on `docker-compose.node04.yml` (the multi-engine node), `deploy.resources.reservations.devices` (`driver:nvidia`, `capabilities:[gpu]`), `CUDA_VISIBLE_DEVICES`, `shm_size: 8g–16g`. Stateless; floats to any free RTX 6000 Blackwell.

**Placement:** dev = Serving+Management co-located in one node-01-class VM, Benchmark floats (mode-switch onto node-03 etc., with the GPU-release caution in §3.5); prod = Serving peeled to its own always-on VM, Benchmark on dedicated hardware.

## AD-04-v3.18 Phase 0 — code-level implementation plan (review gate) (NEW)

**Purpose.** Before any code is built, the other agent produces a single reviewable **MBCP Implementation Plan**. This is the highest-leverage thing for Claude to review: contracts, schema, and load-bearing code are where on-paper review catches real errors cheaply. It deliberately does **not** attempt to pre-write the whole system (see §3.18.I). On approval, the incremental build (§3.19) begins.

**Deliverables (the Implementation Plan must contain all of A–H):**

**A. Repository & module layout.** The directory tree of the new standalone repo, every module's responsibility, and **which of the three planes it belongs to** (Serving / Management / Benchmark). The three compose files and three `.env.*.template` files. Each module flagged **vendor-copied** (with its IVGS source path) or **written-fresh**.

**B. DDL schema.** Actual `CREATE TABLE` / Alembic migration definitions for every table in §3.13 (including `stored_weights.tier` and `pending_exports`): column types, ENUMs, FKs, indexes, the UUID/TIMESTAMPTZ conventions. *(High review value — schema is expensive to change later and easy to review on paper.)*

**C. API contracts.** The full FastAPI route table — method, path, request/response Pydantic models (field-level), auth/RBAC level — for every surface: registry, **weight-store ingest + read-only serve** (specified precisely — these are what the Benchmark plane and, later, AD-01 call), fixtures, suites, runs, results, scoring, human-eval, certification, and the §3.14 export. OpenAPI-style request/response shapes.

**D. Adapter interface (the load-bearing contract).** The actual Python `ModelAdapter` ABC with full signatures (§3.6), the `AdapterManifest` dataclass, the input/output/telemetry dataclasses, the explicit mapping to each `shared/providers/` ABC, the lifecycle (`describe/prepare/generate/unload/check_health`), and the adapter registration mechanism. **Plus one concrete worked adapter written out in full: the LatentSync adapter** (it wraps the one stable, vendor-copied client), as the proof that the contract closes. The new-model adapters (Wan2.2-S2V / MagiHuman / HuMo) appear here only as **signatures + an integration checklist** — not implementations (§3.18.I).

**E. Stub boundaries (standalone mode).** The two §3.14 seams as typed interfaces, each with **both** implementations sketched: `LocalPendingExport` / `AD01Export`, and the Serving read-only fetch vs the (deferred) IVGS-side consumer. The `ExportBundle` / `ExportReceipt` typed payloads in full. The `MBCP_AD01_MODE` switch and how the same call site binds either implementation.

**F. Load-bearing code skeletons.** Actual code (skeletons, not full implementations) for:
- the **adapter base class** (from D);
- the **comparison-framework skeleton** — the data contract behind the per-stage N-up surface (what a "comparison set" is, how `run_results` are grouped, the API that feeds it) **and** the React skeleton extending the vendor-copied `VideoPlayer` with a shared transport;
- the **weight-store API** — the Serving plane: the ingest job interface, the read-only fetch endpoints, checksum verification, the versioned `candidate`/`certified` bundle layout, and the bundle manifest format AD-01 will consume.

**G. Three-plane deployment manifests.** The three compose files and env templates, plus the **network contract** between planes (broker, weight-fetch, fixture pull, artifact push, results push), shown for co-located dev placement and peeled prod placement.

**H. Build sequencing (the vertical-slice plan).** The slice list with acceptance criteria, **spike first**: Slice 1 = LatentSync + **one** new model (Wan2.2-S2V or MagiHuman) running end-to-end through the Benchmark worker → artifact stored in Management → rendered in the synchronized N-up comparison surface → **manual side-by-side judgment**. Then widen (more models, automated metrics, certification, AD-01 wiring) per §3.19.

**I. Explicit non-contents.** The Plan must **not** contain full implementations of the from-scratch model-engine integrations (Wan2.2-S2V / MagiHuman / HuMo). These cannot be written correctly on paper and are developed **iteratively against the running models** during the spike. The Plan includes only their adapter signatures and integration checklists.

**Review gate.** Claude reviews A–H against this spec — contract completeness, schema correctness, the stub boundaries, and the load-bearing skeletons. Approval unblocks the build; no build precedes the review.

## AD-04-v3.19 Phased build — **delivered status** *(replaces v3.0 §3.19)*

| Phase | Scope | Status |
|---|---|---|
| **0** | Code-level implementation plan + review gate | ✅ **Complete.** Gate served its purpose and is closed; the Phase-0 framing throughout this document (§3.18 in particular) is now historical |
| **1** | Spike + MVP / talking-head bake-off | ✅ **Complete.** Adapter contract proven; HF-free weight serving working; synchronized N-up comparison player delivered |
| **2** | Automated quality metrics | ✅ **Substantially complete.** Scoring, aggregates and scorecards live |
| **3** | Human evaluation + certification | ✅ **Complete.** Human-eval queue, aggregates, certification records, revocation with reason, lifecycle |
| **4** | AD-01 integration + ops | ✅ **Complete on the MBCP side** — connected mode live. 🟡 **The IVGS-side weight-fetch pull has never been exercised** (ledger P2.10) |
| **5** | Generalise to all model classes and all 8 stages | 🟡 **Partial.** Adapters exist across stages; **the CogVideoX adapter is broken** (§3.23) |

**The headline outcome is achieved.** The talking-head production model decision — the reason MBCP was built and the M1 quality blocker — is settled on data.

> **ERRATUM 2026-08-15 — the bake-off has NOT been run.** This section states or
> implies that the talking-head comparison is complete and settled. **The platform is
> complete; the comparison is not.** Evidence:
>
> - MBCP's weight store holds three talking-head models — davinci-magihuman (171 GB),
>   humo-17B (130 GB) and latentsync (4 GB) — but **all four talking-head certificates
>   are LatentSync**, because MagiHuman and HuMo have **no adapters** (MBCP work
>   package **R-11**, still open). A model without an adapter cannot be benchmarked,
>   so it cannot be certified or exported.
> - LatentSync therefore "won" a field of one — and it is the model already judged
>   non-viable for articulation on 2026-06-08
>   (`docs/archive/OUTSTANDING_WORK_Addendum_B_2026-06-08.md:32`, "a deal-breaker").
> - The two LatentSync certificates IVGS holds (`9e0fc3cd`, `7b26811f`) are
>   **unsupported**: MBCP's lip-sync gate was scored against a fixture whose
>   `audio_matched.wav` is the presenter clip's own soundtrack (RMS difference
>   -135.4 dB, 102 dB below baseline). It could not fail.
> - No IVGS or MBCP metric measures lip-sync **articulation** — the defect that
>   matters. Ledger **P1.4e**.
>
> **The blocker is MBCP R-11**: adapters for MagiHuman and HuMo. Until those exist
> there is no comparison, no winner, and nothing for IVGS to consume. A win by either
> would additionally need an IVGS provider builder that does not exist
> (`registered_engines()` lists only cogvideox, comfyui, coqui, kokoro, latentsync,
> sadtalker, vllm).
>
> Amended, not rewritten: "bake-off complete" was a genuine belief on the information
> then available, and the record of that belief is part of the evidence. Ledger P1.4d.


## AD-04-v3.20 Relationship to the Master Sequence Plan *(replaces v3.0 §3.20)*

Against **Master Plan v0.4**:

- **WS-H's Phase-1 driver is CLOSED.** v0.3's M1 quality gate ("depends on a certified replacement head model") is satisfied.
- **WS-H continues as platform work** — the RuntimeClass refactor and the CogVideoX adapter rebuild (§3.23), running independently of the IVGS milestone track.
- **AD-01's approval path is now functional.** v3.0 correctly stated AD-01 is non-operable without an external acceptance process; that process exists and is connected.

**One carried allowance requires correction.** v3.0 §3.20 states *"Stage-8 final rendering must resolve its talking-head model through the provider factory / AD-01 binding."* **That placement is wrong.** Stage 8 overlays a **pre-rendered** head asset by `asset_id`; it does not render the head. The binding belongs at **Stage 6**.

More seriously, the binding **is not present in the live Stage-6 task**: `talking_head_task.py` imports `LatentSyncClient` directly, while the provider-factory implementation sits in the dead duplicate `stage6_talking_head.py`.

**Consequence for MBCP: the certification chain terminates at a wall.** Certified models flow MBCP → Model Store → approved → and cannot be selected. **MBCP's entire output is currently unconsumable by the pipeline stage it was built to serve.** Tracked as ledger **P1.0 / ORCH-6**; AD-01 Draft 2 §AD-01.15; Master Plan **M1**.

*This does not diminish MBCP's delivery — the platform works and the decision is made. It is one wiring defect on the IVGS side, and it is the highest-priority item in the programme.*

## AD-04-v3.21 Open design decisions — **status** *(replaces v3.0 §3.21)*

**Closed by implementation:**

| # | Decision | Resolution |
|---|---|---|
| 5 | ARCH-1 sequencing — MBCP delivers `get_provider()`, or IVGS does | **IVGS delivered it.** `shared/providers/factory.py` + `binding.py`; the MBCP adapter shape stayed compatible as the leaning anticipated |
| 2 | Weight-serving transport | **HTTP** — `ivgs-models/mbcp_fetch.py` against `{serving_url}/weights/{model}/manifest`, with checksum verification. **Direction is pull: IVGS pulls, MBCP does not push.** Not yet exercised end-to-end (ledger P2.10) |

Also closed in v3.0 and unchanged: the code-sharing boundary (vendor-copy, §3.4.8), GPU node dedication (float in dev, dedicate in prod, §3.5), and scheduler removal (§3.10).

**Still open:**

| # | Decision | Note |
|---|---|---|
| 1 | Decisive vs advisory metrics; production talking-head thresholds | Still open, but **less urgent** — the bake-off was settled with human evaluation in the loop. Needed before certification is delegated or automated |
| 3 | Fixture curation and sandbox→fixture promotion policy | Open |
| 4 | Certification expiry policy — what forces re-certification | Open, and **increasingly load-bearing**: the M4 fleet rollout changes driver/CUDA/hardware context across five nodes. Settle before M4, or every existing certification silently becomes of uncertain validity |

**New decision.** *(D-6)* Should MBCP certification records carry the **IVGS Model Store model ID** after a successful export, giving a bidirectional link? Currently the receiver dedups by `certification_id` but MBCP holds no reference back. Would make "which certification is running in production?" answerable from either side.

## AD-04-v3.22 — Delivered integration state *(new in v3.1)*

**Connected mode, live since 2026-07-09.**

- **Seam:** IVGS receiver `/ad01/v1`, `X-Service-Token` authenticated. `MBCP_AD01_MODE=connected`.
- **Certify ≠ export.** Export is a distinct admin action, `POST /api/v1/exports {certification_id}`. The receiver dedups by `certification_id`, so re-export is safe.
- **Drain:** `drain-pending-exports` every 5 minutes retries parked rows.
- **Backfill complete:** 21 exports plus 2 composition transmitted; all non-revoked certifications landed in IVGS as CANDIDATEs (including FFmpeg-composition, engine `ffmpeg`); 24 revoked correctly skipped.
- **Schema changes both sides:** IVGS migration 0027 added `ffmpeg` to `ModelEngine`; MBCP added `ExportBundle.engine`. AD-01 rejections surface as `502 AD01_REJECTED` rather than a raw 500.
- **Export-to-IVGS GUI button** delivered 2026-07-12 (`docs/MBCP_Delivery_20260712_ExportButton_WSTEST.md`), closing v3.0's "no GUI button" gap.

**Boundary, restated.** MBCP certifies; AD-01 governs lifecycle and selection. A certification is **evidence, not an approval** — approval remains a deliberate in-IVGS act with attestation. **AD-01 must never auto-approve on certification receipt.**

## AD-04-v3.23 — Adapter framework defects *(new in v3.1)*

The RuntimeClass audit (Task A, complete, no code changed) found:

**Fragmentation is narrower than assumed.** vLLM is already a single runtime class; TTS is a single adapter. **Only ComfyUI is fragmented** — three per-model adapters each embedding a full workflow graph.

**The CogVideoX adapter is broken.** Its embedded graph references **four node types that do not exist** in the installed `CogVideoXWrapper`:

| Embedded | Reality |
|---|---|
| `CogVideoXTextEncoderLoader` | Does not exist — T5 loads via core `CLIPLoader` with `type="sd3"` |
| `CogVideoXTextEncode` | Real node is `CogVideoTextEncode` (no "X") |
| `CogVideoXSampler` | Real node is `CogVideoSampler`; adapter also wrongly injects width/height |
| `CogVideoXDecode` | Real node is `CogVideoDecode` |

Plus wrong parameter keys on two loaders that do exist. The correct graph shape has been derived from the wrapper's source and the pinned example workflow; the adapter must be **rebuilt, not extracted**.

**Consequence:** the video stage has **no working benchmark path**. CogVideoX is IVGS's video engine on nodes 02/03 (and node-06 after the AD-02 Draft-3 redesignation), so no video model can be certified before those nodes roll at M4.

`engines/comfyui/CUSTOM_NODES.txt` compounds this — it lists the same non-existent X-prefixed names.

**Approved resolution (2026-08-14): split into two PRs.**

1. **PR 1** — extract FLUX and AnimateDiff graphs to JSON. Both validated as matching installed nodes; low risk; mergeable without GPU access.
2. **PR 2** — rebuild the CogVideoX graph against installed nodes; correct `CUSTOM_NODES.txt`. **Validatable only at a real GPU smoke test — treat that smoke as a gate, not a formality**, since the rebuild is derived from source reading rather than from a working render.

Rationale for splitting: the two pieces carry different risk profiles and should not share a fate. Tracked as ledger **P2.8** and **P2.9**.

*These findings are MBCP-side and live in the MBCP repository on `.51`; they are recorded here because they gate the IVGS video stage's certification path.*

## AD-04-v3.24 — Open operational items *(new in v3.1)*

| Item | Status |
|---|---|
| `serving-authoring-loop-1` **unhealthy** on `.51` | Pre-existing; undiagnosed (ledger P2.7) |
| Weight-fetch pull path | Never exercised. Needs the fleet (M4) plus `MBCP_SERVING_TOKEN` and `MBCP_WEIGHT_SIGNING_KEY` handoff (ledger P2.10) |
| `docs/MBCP_Dev_VM_Setup_verified.md` | 214 lines, verified 2026-06-08. **CLOSED** — committed to `elearning_v5` at `b09b70f`; the amendment recorded it as untracked, which was true when drafted |
| MBCP SSOT v3.3 | Requires reconciliation to v3.4 against 2026-08-05 state |
| MBCP `docs/` set (~20 files) | Per-slice requirements and run reports; most should move to `docs/archive/` |

**Note on MBCP's own orchestration.** MBCP shares IVGS's hand-rolled pattern — Postgres status-column ledgers, monolithic Celery tasks with guarded transitions, a `sweep_stuck_runs` zombie reaper, a bespoke `export_drain` retry queue with poison-row parking, and a custom DB-polling Beat subclass. AD-05 addresses **IVGS only**.

MBCP is a materially better candidate for a later migration than IVGS was — it has no in-flight state to preserve at cutover — but **it is explicitly out of scope for now**. Recorded here so the question is deferred deliberately rather than forgotten. Re-open after IVGS's M3 completes and the migration's real cost is known rather than estimated.

---

## Appendix AD-04-v3-A — Codebase evidence map

Carried from the v2 read-only audit (`brucecostello2/elearning_v5`, 2026-06-08). Unchanged except the two annotated rows.

| Claim | Evidence (path) |
|---|---|
| Provider ABCs exist (6 interfaces) | `shared/providers/__init__.py` |
| `get_provider()` factory does NOT exist (ARCH-1 open) | No factory/registry in `shared/` or `ivgs-workers/`; tasks import concrete clients |
| Talking-head reference-clip upload param | `TalkingHeadParams.reference_clip_path`, `alignment_threshold=0.85` |
| `reference_clip` asset type in schema | `ivgs-api/app/models/asset.py` (`asset_type` PG_ENUM) |
| Engine clients (async context managers) | `ivgs-workers/clients/{vllm,flux,coqui,latentsync,ffmpeg,cogvideox}_client.py` |
| 8 stages, task names, queues, I/O | `ivgs-workers/tasks/stage{1..8}*.py`, `shared/models/enums.py` — **Stage-6 dispatch corrected to `tasks.talking_head_task.render_talking_head`; duplicate modules = A5 (§3.9)** |
| Weight provisioning via huggingface-cli | `ivgs-models/download_models.sh`, `checksums.sha256`, `README.md` (Table B-1) — **consuming MBCP-served weights requires a new fetch mechanism, not a repoint (§3.7a)** |
| Per-engine model configs | `ivgs-models/vllm/*.yaml`, `comfyui/*.json`, `tts/*.yaml`, `ollama/Modelfile` |
| Frontend stack & theme | `ivgs-frontend/package.json`, `tailwind.config.js`, `src/app/layout.tsx` |
| Header / Sidebar / nav | `ivgs-frontend/src/components/{Header,Sidebar}.tsx` |
| Upload / video components | `ivgs-frontend/src/components/{AssetUploader,VideoPlayer}.tsx` |
| API client (JWT, refresh, pagination) | `ivgs-frontend/src/lib/api-client.ts` |
| FastAPI patterns (RBAC, pagination, service token) | `ivgs-api/app/api/v1/{assets,prompts}.py`, `app/core/{auth,rbac}.py` |
| ORM conventions (UUID/TIMESTAMPTZ/PG_ENUM) | `ivgs-api/app/models/asset.py` |
| SeaweedFS client | `shared/seaweedfs_client.py` |
| VRAM-aware scheduler | `ivgs-scheduler/{admission_control,model_concurrency,gpu_registry}.py` — **exists in IVGS; deliberately NOT used by MBCP (§3.10); carries the open heartbeat defect** |
| Docker / per-node compose / monitoring | `ivgs-infra/docker-compose.node0{1..6}.yml`, `docker-compose.monitoring.yml`, `*/Dockerfile`, `configs/nginx/nginx.conf`, `.env.node0*.template` |

---

*Prepared as an additive design under the §18 change-control process. v3 corrects v2's architecture (three planes), removes the reused scheduler in favour of serial isolated benchmarking, decides the code-sharing boundary (vendor-copy), reconciles weight-serving with the reality that `huggingface-cli` cannot be repointed, makes the standalone/stubbed-AD-01 strategy explicit, and adds a Phase 0 code-level implementation-plan review gate. The MBCP remains a standalone, Dockerized companion system that operationalizes the external acceptance process AD-01.7 places outside IVGS, stores and serves validated weights to AD-01, and provides an isolated, GUI-native, per-stage model testing and comparison platform. It does not serve production traffic, replace the Model Store, or alter the IVGS pipeline.*

*End AD-04 v3.0.*
