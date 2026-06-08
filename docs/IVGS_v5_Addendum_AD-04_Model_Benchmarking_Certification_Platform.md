# IVGS v5 — Addendum AD-04: Model Benchmarking & Certification Platform (MBCP)

| | |
|---|---|
| **Document** | Design specification for a standalone platform that benchmarks, evaluates, and certifies self-hostable generative models for the IVGS pipeline. |
| **Version** | v0.1 — 2026-06-07 (first draft) |
| **Classification** | Internal Working Document |
| **Change-control status** | Draft for review (per §18 change-control process) |
| **Depends on** | AD-01 Model Management (the consumer of certifications); provider abstraction (§19.1); IVGS platform conventions (FastAPI, PostgreSQL 17, Celery/Redis, SeaweedFS, Next.js, Prometheus/Grafana, Alembic) |
| **Relationship** | MBCP is a **separate, deployable system** (its own VM, database, and UI). It does **not** alter the IVGS pipeline, node topology, or storage. It operationalizes the **external acceptance process** that AD-01.7 deliberately places outside IVGS, and it is the data-producing front end for AD-01's Model Store. |

---

## AD-04.1 Purpose

AD-01 defines a Model Store — a curated allow-list of approved, selectable models — but is explicit that it does **not** validate them. Two passages fix this boundary:

- AD-01.2 (non-goals): *"The subsystem does not benchmark a model, measure its real VRAM footprint, or verify CUDA/driver/quantization/engine compatibility. It assumes every model in the store has already passed an external acceptance process."*
- AD-01.7: *"This subsystem is an allow-list of pre-vetted models, not a validation harness … a model may only reach APPROVED after passing an acceptance process performed outside this system, against the actual target hardware. … Registering a model is an assertion that this external acceptance has already succeeded."*

That external acceptance process has, until now, been undefined — a manual, ad-hoc, hardware-in-the-loop activity. **The MBCP is that process, built as a durable platform rather than a one-off harness.** It exists so that choosing and validating a model for IVGS is repeatable, measurable, auditable, and comparable across candidates and over time, instead of a subjective eyeball test that is redone from scratch every time.

**Immediate driver.** The talking-head decision: LatentSync's lip-sync articulation is not viable for production, and candidate replacements (Wan2.2-S2V, daVinci-MagiHuman, HuMo, MuseTalk) must be compared on real hardware, at real resolutions, on representative content, on both generation cost and output quality. The MBCP answers this with data rather than impressions.

**Strategic role.** The MBCP is the certification engine behind AD-01. Every model that AD-01 serves should have passed through it. Its certification record is the attestation AD-01.7.2 requires for `CANDIDATE → APPROVED`, and the real VRAM and engine/quantization figures it measures are the ground truth that AD-01 (and the §12 Appendix B VRAM matrix) currently treat as merely "declared, advisory."

## AD-04.2 Scope and non-goals

**In scope:** a standalone benchmarking/evaluation/certification platform; a model **adapter framework**; a versioned **test corpus**; **benchmark run** orchestration across a matrix of models × fixtures × resolutions × parameter sets; **performance** measurement (generation time, real VRAM, throughput, failure modes); **automated quality** metrics; **human/subjective** evaluation; a **certification** workflow with auditable records; and **export** of certifications into AD-01.

**Out of scope / non-goals:**
- **Serving production traffic.** The MBCP renders only for evaluation. Production generation remains the IVGS pipeline's job. (Where MBCP and IVGS share code, it is the adapter/provider contract — see AD-04.3.)
- **Replacing AD-01.** The MBCP feeds the Model Store; it is not the Model Store. Selection, residency, and serving stay in AD-01.
- **Training or fine-tuning models.** Evaluation only (a fine-tuning harness is a possible later sibling, not this).
- **Editing the IVGS pipeline.** No change to the eight stages, node roles, or storage.

## AD-04.3 Relationship to AD-01 and the IVGS platform

This is the load-bearing section; the rest follows from it.

**1. The MBCP is AD-01.7's external acceptance process.** AD-01.7.1 lists the acceptance checklist performed "outside IVGS": hardware fit within real VRAM headroom (used to correct the Appendix B matrix), engine/runtime compatibility on the pinned engine version and CUDA/driver/quantization stack, and so on. The MBCP **is the system that runs and records that checklist**. AD-01.7.2 says the outcome is recorded in `model_approvals` (who attested, an external acceptance reference, a checklist snapshot, a timestamp). An MBCP **certification record is exactly that reference**: the external acceptance ticket becomes an MBCP certification ID, and the checklist snapshot is the MBCP scorecard.

**2. The adapter contract is the shared seam.** AD-01.4 names the provider abstraction (§19.1) as "the execution seam" — a GPU task calls `get_provider(stage, job_id, scene_id?)` rather than instantiating a concrete client. The MBCP's **model adapter** (AD-04.6) is built to the **same interface**, so a model wrapped for benchmarking is wrapped *once*: a certified MBCP adapter is the same code path that becomes an IVGS provider. This avoids the trap of validating one implementation and shipping another. (It also means investing in the adapter contract here directly advances ARCH-1, AD-01's "fix once, the right way" item.)

**3. Measured, not declared.** AD-01.5.2 records `vram_gb` as "Declared … advisory, not measured here," and `dynamically_loadable` as a hard engine fact. The MBCP measures real peak VRAM, confirms loadability/quantization behavior, and emits these as ground truth — correcting both the Model Store entry and the §12 Appendix B matrix.

**4. Representative by construction.** Because results must transfer to production, the MBCP mirrors the IVGS platform stack (same engines, same NVIDIA Blackwell + CUDA/driver profile, same resolutions and content types). A number measured on the MBCP must mean the same thing on the IVGS fleet.

**Handoff, end to end:** MBCP registers a candidate → runs the benchmark/checklist on representative fixtures and hardware → scores it (automated + human) → a certification decision produces a **certification record** (scoped to stage, tier, resolution, hardware/engine/quantization profile, with measured VRAM and the scorecard) → that record is exported to AD-01, where an admin registers the model `CANDIDATE` and uses the certification as the attestation that satisfies AD-01.7.2 for promotion to `APPROVED`. AD-01 then selects/serves it via the (now shared) provider factory.

## AD-04.4 Design principles

1. **Representative over convenient.** Mirror the IVGS stack and hardware so measurements transfer. A benchmark on non-representative hardware is worse than no benchmark — it produces false confidence.
2. **Isolated from production.** The MBCP runs in its own VM with its own GPU worker node(s), network-segmented from the IVGS render path, so experimental or unstable model loads (a new engine OOMing a card, a bad driver) cannot destabilize production renders.
3. **Durable and extensible, not a script.** Models plug in through an adapter framework; metrics, fixtures, and certifications are first-class persisted entities. Adding the *next* model is configuration, not a rewrite.
4. **Reproducible and auditable.** Every run is tagged with adapter version, engine/driver/CUDA versions, hardware profile, fixture version, parameters, and (where supported) seed. Every score and certification is recorded with provenance.
5. **Adapter-first.** The adapter/provider contract (shared with §19.1) is the single most important reusable artifact; everything else is scaffolding around it.
6. **Quality is multi-signal.** No single automated metric decides "realistic." Performance, automated quality proxies, and blind human evaluation are captured together; certification thresholds combine them.

## AD-04.5 System architecture

The MBCP is a small "mini-IVGS": the same shape, a different purpose.

**Control-plane VM** (mirrors the IVGS node-01 stack):
- **FastAPI backend** — REST surface for the registry, fixtures, runs, results, scoring, and certification; admin-gated mutations; the export-to-AD-01 endpoint.
- **PostgreSQL 17** — the MBCP's own database (AD-04.11). Alembic migrations on API startup, per IVGS convention.
- **Redis + Celery (Beat + workers)** — run orchestration and scheduling, exactly as the IVGS pipeline uses them.
- **Object store** — SeaweedFS (to mirror IVGS) or MinIO, holding generated clips and evaluation artifacts.
- **Next.js UI** — the operator surface (AD-04.13).
- **Prometheus + Grafana + GPU/DCGM exporter** — capture GPU/VRAM/timing telemetry, mirroring IVGS monitoring.

**Benchmark GPU worker node(s)** — one or more **dedicated RTX PRO 6000 Blackwell** cards (added to the estate per operator note), running the engine stack (ComfyUI, vLLM, Coqui/Kokoro, LatentSync/SadTalker, Wan2.x, MagiHuman, HuMo, MuseTalk, …) and the MBCP Celery GPU worker. These are **isolated** from the IVGS production fleet so benchmark load never contends with production renders, but may reach the shared weight store (`ivgs-models` tooling / NFS) so weight provisioning is not duplicated.

```
                          MBCP control-plane VM
  Next.js UI ── FastAPI ── PostgreSQL(own) ── Redis ── Celery Beat
                  │             │                        │
              Prometheus/Grafana(+DCGM)            Celery dispatch
                                                         │
                                          ┌──────────────┴───────────────┐
                                   Benchmark GPU node A          (Benchmark GPU node B…)
                                   [RTX 6000 Blackwell]          [added as needed]
                                   engines + MBCP GPU worker     model × hardware matrix
                                   adapters ── artifacts → object store
                                                         │
                                       (export certifications) ──► AD-01 Model Store (IVGS)
```

## AD-04.6 Model adapter framework (the core)

Each model is wrapped in an **adapter** implementing a standard interface, intentionally a superset of the §19.1 provider contract so a certified adapter promotes into IVGS unchanged:

- `describe()` → static manifest: engine + pinned version, model/version, weights_ref, input modalities (image / audio / text / pose), supported stages (talking_head, image, scene_video, tts, llm…), supported resolutions, declared VRAM, quantization, license.
- `prepare(hardware_profile)` / `load()` → provision/load weights onto the target engine; report load success and resident VRAM.
- `generate(inputs, params) -> (artifact, telemetry)` → run one generation; return the output artifact plus measured telemetry (wall time, GPU compute time, peak VRAM, util, exit status).
- `unload()` → release for the next candidate (`dynamically_loadable` engines) or note fixed-process serving (vLLM).

Day-one engine adapters target the talking-head decision (LatentSync, Wan2.2-S2V, MagiHuman; HuMo and MuseTalk as comparators). The framework generalizes to every IVGS engine class so the platform serves all of AD-01 over time (AD-04.15, Phase 5).

## AD-04.7 Test corpus (fixtures)

A **versioned** library of standardized, representative inputs, so runs are comparable across models and over time:

- **Reference media** — source images spanning the intended range (photoreal human presenters, stylized/illustrated, varied lighting and framing) and, for video-edit models, source clips.
- **Audio** — narration clips at representative lengths (≈5 s, 30 s, 75 s, multi-minute), multiple voices/prosody, and the IVGS languages, including a known transcript so ASR round-trip WER can be computed.
- **Prompts** — paired text for text-conditioned models.
- **Target resolutions** — 480p / 720p / 1080p / 4K tiers, matching IVGS draft/final profiles.
- **Categories** — talking-head, scene-fill video, image generation, TTS, organized so a test suite can target a stage.

Fixtures are immutable and versioned; a "golden suite" pins the canonical comparison set so leaderboards are apples-to-apples.

## AD-04.8 Benchmark run orchestration

A **run** is a matrix: `{ adapter(s) × test suite (fixtures × resolutions × parameter sets) × hardware profile }`. The API records the run; Celery Beat/queues dispatch each cell to a GPU worker; the worker loads the adapter, generates, captures artifact + telemetry, and persists results. Runs are **re-runnable** as regression checks — re-certify on an engine, driver, CUDA, or model-version change, and diff against the prior scorecard. Partial failure of one cell never discards completed cells (mirroring the IVGS segment-render philosophy).

## AD-04.9 Metrics

**Performance / cost** (per cell): generation wall-time, GPU compute time, **real peak VRAM**, GPU utilization, throughput (output-seconds of video per compute-second), real-time factor, and failure/OOM rate. These feed AD-01's advisory `vram_gb` and the Appendix B matrix.

**Automated quality** (per model class):
- *Lip-sync:* LSE-C / LSE-D (SyncNet-style confidence/distance) and audio-video sync offset.
- *Articulation proxy:* **ASR round-trip WER** — re-transcribe the generated speech and compare to the known fixture transcript; a direct, automatable signal for the very failure LatentSync exhibits (mouth motion that doesn't represent the words).
- *Visual fidelity:* FID / FVD against reference distributions.
- *Identity preservation:* ArcFace cosine similarity vs the reference image.
- *Text alignment:* CLIP similarity for text-conditioned generation.
- *Temporal:* artifact/flicker and consistency measures.

**Human / subjective** (the decisive signal for "realistic," AD-04.13): blind **pairwise A/B** (Elo / Bradley-Terry ranking) and **Likert** ratings across sync, naturalness, identity, and artifacts, multi-rater.

**Compatibility / robustness:** the AD-01.7.1 checklist captured as structured results — engine/CUDA/driver/quantization fit, real headroom, determinism across repeats.

## AD-04.10 Scoring and certification workflow

Per-cell metrics aggregate into a **model scorecard** (per stage × resolution tier × hardware profile). A **certification decision** applies thresholds appropriate to the IVGS stage and tier — e.g., a *production talking-head* might require LSE-C ≥ a floor, ASR WER ≤ a ceiling, a human pairwise win-rate ≥ a bar versus the incumbent, and measured VRAM within the target node's headroom — while a *prototype/draft* tier optimizes for speed within a much looser quality floor (this is exactly the two-tier draft/production split the talking-head work motivated).

**MBCP model lifecycle:** `REGISTERED → BENCHMARKING → SCORED → CERTIFIED | REJECTED`. A **CERTIFIED** record is scoped (stage, tier, resolution, hardware + engine + quantization profile), carries the measured VRAM and a reference to the scorecard, and is **expirable/revocable** — re-certification is required when the engine, driver, or model version changes. A CERTIFIED record is what exports as the AD-01 attestation.

## AD-04.11 Data model (own PostgreSQL)

All tables follow IVGS conventions: UUID PKs, `TIMESTAMPTZ` audit columns, `jsonb` for structured detail, Alembic migrations on API startup.

| Table | Purpose (key fields) |
|---|---|
| `models` | Candidate registry — name, family, version, engine + pinned version, `weights_ref`, modalities, supported stages, license, `declared_vram_gb`, quantization, status |
| `adapters` | Adapter implementation ref + version, `model_id`, config/param schema (`jsonb`) |
| `fixtures` | Versioned test inputs — kind (image/audio/clip/prompt), media ref, transcript (for WER), category, metadata |
| `test_suites` | Named fixture sets + resolution tiers + parameter grids |
| `hardware_profiles` | GPU model, count, VRAM, driver, CUDA, engine versions — every result is tagged with one |
| `benchmark_runs` | Run config (suite, adapters, params, hardware profile), status, timestamps |
| `run_results` | Per cell — `artifact_ref`, `gen_time_s`, `gpu_time_s`, `vram_peak_gb`, `gpu_util`, status, error (`jsonb`) |
| `quality_metrics` | Automated scores per result — `lse_c`, `lse_d`, `sync_offset_ms`, `wer`, `fid`, `fvd`, `arcface_id`, `clip_sim`, … |
| `human_evaluations` | Rater, mode (pairwise/Likert), target result(s), scores, comments |
| `certifications` | `model_id`, `ivgs_stage`, `tier`, `resolution`, `hardware_profile`, `thresholds_met` (`jsonb`), `measured_vram_gb`, `scorecard_ref`, `certified_by`, `certified_at`, `expires_at`, `revoked` — **the export unit** |
| `artifacts` | Generated outputs in the object store + metadata |

The `certifications` row maps directly onto AD-01's `model_approvals` (attestation) and corrects AD-01 `models.vram_gb` / `quantization`.

## AD-04.12 Integration & export to AD-01

A CERTIFIED model produces an **export bundle**: model metadata, measured VRAM, engine/quantization profile, suggested capability tags (from the scorecard), the scorecard reference, and the certification ID. AD-01 ingests it as a `CANDIDATE` registration whose attestation (AD-01.7.2) is the MBCP certification. Because the adapter is built to the §19.1 contract, the certified adapter is the same code the IVGS provider factory uses — no re-implementation between "validated" and "served." Re-certification (on engine/driver/model change) re-issues the attestation and re-corrects the VRAM matrix.

## AD-04.13 User interface (Next.js)

Mirrors IVGS frontend patterns and extends AD-01.10's Model Management page (whose "test action that runs a minimal generation" is, in effect, the MBCP in miniature):

- **Model registry / admin** — register candidates, attach engine/license/declared-VRAM metadata, manage adapter versions.
- **Fixtures & test suites** — manage the corpus, compose suites (fixtures × resolutions × params).
- **Run builder** — define and launch a benchmark matrix; live progress from Celery/telemetry.
- **Results & leaderboards** — per-model scorecards, sortable leaderboards per stage/resolution/hardware, performance vs quality plots.
- **Side-by-side comparison player** — synchronized A/B (and N-up) video playback at native resolution — the decisive surface for judging articulation, since the failure is visual and small in automated metrics.
- **Human-eval queue** — blind pairwise / Likert rating, multi-rater, feeding the Elo/Likert aggregates.
- **Certification review & export** — review the scorecard, set/confirm thresholds, record the certification, and export to AD-01.

## AD-04.14 Hardware & deployment

- **Control-plane VM** — a standard Proxmox VM (CPU) hosting the FastAPI/Postgres/Redis/Celery/UI/monitoring stack, like IVGS node-01 in miniature.
- **Benchmark GPU node(s)** — one or more dedicated RTX PRO 6000 Blackwell cards (added per operator note), with engine stack + MBCP GPU worker, **network-isolated from the IVGS production render path**. Adding a second GPU node enables true model × hardware-profile matrices (e.g., a model on one card vs sharded across two) and parallel candidate evaluation.
- **Shared weights** — may reuse the IVGS `ivgs-models` provisioning tooling / NFS weight store to avoid duplicate downloads, while keeping compute isolated.
- **Monitoring** — Prometheus/Grafana with a GPU/DCGM exporter (also closes the kind of telemetry gap currently open on the IVGS Blackwell exporter, on a clean surface).

## AD-04.15 Phased build

1. **Phase 1 — MVP / talking-head bake-off.** Adapter framework on the §19.1-compatible contract; adapters for **LatentSync + Wan2.2-S2V + daVinci-MagiHuman**; Celery + one GPU worker; Postgres schema (models/fixtures/suites/runs/results/hardware_profiles); **performance metrics** (time, real VRAM, throughput); artifact store; minimal UI (run builder + results table + **side-by-side player**). *Outcome:* the talking-head decision made on data, and the adapter contract proven.
2. **Phase 2 — Automated quality.** LSE-C/D + sync offset, ASR round-trip WER, FID/FVD, ArcFace identity, CLIP alignment; leaderboards and scorecard dashboards.
3. **Phase 3 — Human evaluation + certification.** Blind pairwise/Likert UI and Elo aggregation; the certification workflow, records, thresholds, and lifecycle.
4. **Phase 4 — AD-01 integration + ops.** Export bundle / attestation handoff, VRAM-matrix correction, shared adapter contract wired to §19.1; full monitoring; regression re-benchmarking on engine/driver/model change.
5. **Phase 5 — Generalize.** Adapters and metric profiles for all IVGS model classes (image: FLUX/SDXL/SD3.5; scene video: CogVideoX/Wan; TTS: Coqui/Kokoro; LLM: vLLM/Ollama) — the full certification platform AD-01 consumes for every stage.

## AD-04.16 Relationship to the Master Sequence Plan

The MBCP is a **new workstream** (proposed **WS-H — Model evaluation & certification**). Its **Phase 1** is pulled forward now to settle the talking-head production model; the **full platform** is a companion/prerequisite to **M5 (AD-01 model management)**, since AD-01's approval path is non-functional without the external acceptance process the MBCP provides. The Master Plan otherwise continues as-is, with one recorded allowance: **Stage-8 final rendering must be built to accommodate model changes** — i.e., the final render resolves its talking-head (and, later, other) model through the provider factory / AD-01 binding rather than a hard-coded engine, so a newly certified production model is a selection change, not a code change. (Cross-references to add when convenient: AD-01.7 → "operationalized by AD-04/MBCP"; Master Plan WS-H + the M5/Stage-8 allowance.)

## AD-04.17 Open design decisions (for review)

1. **Decisive vs advisory metrics.** Which automated metrics gate certification versus inform it — and the exact production talking-head thresholds (LSE-C floor, WER ceiling, human win-rate bar).
2. **Code sharing boundary.** How much MBCP shares with IVGS beyond the adapter contract (ideally only the contract; the rest stays standalone for isolation).
3. **GPU node dedication.** Permanently MBCP-dedicated GPU node(s), or a shared pool borrowed from IVGS during idle windows (dedication is cleaner for isolation and reproducibility; sharing is cheaper).
4. **Fixture curation.** Who curates and ratifies the golden suite, and how the IVGS content categories map onto it.
5. **Certification expiry policy.** What changes force re-certification, and the default expiry window.

---

*Prepared as an additive design under the §18 change-control process. The MBCP is a standalone system that operationalizes the external acceptance process AD-01.7 places outside IVGS; its certification records are the attestations AD-01.7.2 requires. It does not serve production traffic, replace the Model Store, or alter the IVGS pipeline.*

*End AD-04 v0.1.*
