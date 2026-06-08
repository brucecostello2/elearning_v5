# IVGS v5 — Functional Specification Addendum AD-01

## Model Management Subsystem & Content-Aware Model Selection

**Addendum to:** IVGS v5.0 Functional Specification (18 May 2026)
**Addendum version:** AD-01, Draft 1
**Classification:** Internal Working Document
**Change-control status:** Draft for review (per §18 change-control process)
**Depends on:** Provider abstraction layer (§19.1), pipeline orchestration (§5–§6), GPU scheduler (§12), prompt-management inheritance model (§9)

---

## AD-01.1 Purpose

The v5 base specification assigns exactly one engine per pipeline stage, fixed by node role, and steers output entirely through prompts (§9). It has no concept of a model as a managed, selectable asset. There is no way to (a) add or retire a model without editing serving configs, environment files, the VRAM matrix, and redeploying; or (b) choose a different model for a given job based on what the video actually needs — for example, a flat vector / stick-figure explainer versus a photorealistic, cinematic piece with human presenters. The result is that two projects with radically different visual intent are processed by identical models, and the only lever available to differentiate them is prompt wording.

This addendum defines a **Model Management Subsystem**: a curated, admin-governed **Model Store** of pre-approved, self-hostable models, plus a **content-aware selection** mechanism that binds the optimum prototype and production models to each job at planning time. It is an additive subsystem in the same spirit as the prompt-management subsystem of §9; it does **not** alter node topology, storage, the self-hosted mandate, or the fundamental pipeline. It is therefore delivered as an addendum, not a v6 re-architecture.

## AD-01.2 Scope and non-goals

In scope: a model registry (the Model Store) and its admin surface; capability tagging and prototype/production tiering; a selection/planning step that chooses models per stage (and, where applicable, per scene); the binding of selections into execution via the provider abstraction; and the scheduler integration required to make selected models resident.

Explicitly out of scope — these are **not** functions of this subsystem and are performed outside the system (see AD-01.7):

- **Hardware-compatibility validation.** The subsystem does not benchmark a model, measure its real VRAM footprint, or verify CUDA/driver/quantization/engine compatibility. It assumes every model in the store has already passed an external acceptance process.
- **Weight acquisition.** Downloading and placing model weights remains the responsibility of the `ivgs-models` repository tooling and operations (§14.1). The store references weights; it does not fetch them.
- **Inference quality benchmarking.** Strength/weakness descriptions are human-authored editorial guidance, not measured scores.
- **Cloud or API-backed models.** Per the self-hosted mandate (§1.3), only locally servable models may be registered. The store must reject any entry whose engine implies an external API.

## AD-01.3 Concepts and definitions

| Term | Definition |
|---|---|
| **Model** | A specific, versioned set of weights servable by a known engine for a known stage (e.g., `FLUX.1-dev` on ComfyUI for `image_generation`). The atomic unit of the store. |
| **Engine** | The runtime that serves a model (vLLM, Ollama, ComfyUI, Coqui, Kokoro, LatentSync, SadTalker, CogVideoX, Wan2.1, AnimateDiff, Remotion). Mapped to the provider interfaces of §19.1. |
| **Stage** | A pipeline stage that consumes a model (transcript_refinement, storyboard, image_generation, video_generation, animation_generation, tts, talking_head, composition, translation). |
| **Tier** | Whether a model is intended for the fast, low-cost **prototype** path (Stage 6 draft) or the high-fidelity **production** path (Stage 7 final), or **both**. |
| **Capability tags** | Structured descriptors of what a model is good at (visual style, subject affinity, motion profile, voice profile, language coverage) used by the selector to match a model to a job's intent. |
| **Model Store** | The curated registry of **approved** models. An allow-list; only pre-vetted models appear. |
| **Selection** | The persisted binding, for a specific job/project/scene and stage, of the chosen model, recorded with a rationale and reproducible for audit. |
| **Production profile** | The project-level statement of intent (target style, audience, quality bias) that seeds selection. |

## AD-01.4 Relationship to existing v5 structures

This subsystem deliberately reuses three existing patterns rather than inventing new ones:

**Provider abstraction (§19.1) is the execution seam.** The selector's only job is to decide *which* model; the provider factory is *how* that decision reaches execution. A GPU task no longer instantiates a concrete client; it calls `get_provider(stage, job_id, scene_id?)`, which reads the selection and returns a provider bound to the chosen engine, model, and node. **This subsystem is non-functional until the §19.1 abstraction is implemented as a selection-aware factory** (currently outstanding — gap ARCH-1). The Model Store is, in effect, the product surface of the provider layer.

**Three-tier inheritance mirrors §9 prompt management.** Model selection resolves in the same order prompts do: **System default** (the store's designated default model per stage and tier) → **Project selection** (the planner's choice, or an operator override, for this project) → **Scene selection** (a per-scene override for image/video/animation stages). The pipeline resolves the effective model by taking the first match found, exactly as it resolves the effective prompt.

**Prototype/production tiers map onto existing pipeline stages.** The pipeline already distinguishes `PROTOTYPE_DRAFT` (720p, fast review) from `FINAL_RENDER` (1080p/4K). The tier tag therefore needs no new pipeline concept: prototype-tier models drive the draft, production-tier models drive the final render. The existing video `preferred_model` field (gap N23-3) becomes a special case of a scene-level selection.

## AD-01.5 The Model Store (registry)

### AD-01.5.1 Lifecycle states

Every model moves through a controlled lifecycle. Only **APPROVED** models are selectable by the planner or for production jobs.

| State | Meaning | Who sets it |
|---|---|---|
| `CANDIDATE` | Registered for review; **not** selectable. Used to stage metadata while external vetting (AD-01.7) is in progress. | Admin |
| `APPROVED` | Passed external acceptance; selectable. Requires a recorded attestation. | Admin |
| `DEPRECATED` | Still loadable for existing jobs but not chosen for new ones. | Admin |
| `RETIRED` | No longer servable; retained for audit/reproducibility only. | Admin |

A transition to `APPROVED` is rejected unless a complete attestation record (AD-01.7.2) is attached.

### AD-01.5.2 Data model — new PostgreSQL tables

All tables follow v5 conventions: UUID PKs, `TIMESTAMPTZ` audit columns, `jsonb` for structured detail, Alembic-managed migrations run on API container startup.

**`models`**

| Column | Type | Description |
|---|---|---|
| id | UUID PK | Model identifier |
| name | VARCHAR(128) | Canonical model name (e.g., `flux1-dev`) |
| display_name | VARCHAR(255) | Human-readable name for the UI |
| stage | ENUM | Pipeline stage this model serves (see AD-01.3) |
| engine | ENUM | Serving engine (vllm / ollama / comfyui / coqui / kokoro / cogvideox / wan21 / animatediff / latentsync / sadtalker / remotion) |
| tier | ENUM | prototype / production / both |
| state | ENUM | candidate / approved / deprecated / retired |
| description | TEXT | Editorial overview |
| strengths | JSONB | Human-authored strengths (free-form bullets) |
| weaknesses | JSONB | Human-authored weaknesses / cautions |
| source_url | VARCHAR | Upstream model card / repository URL |
| weights_ref | VARCHAR | Reference to the weights as provisioned by `ivgs-models` (path or registry key) |
| weights_checksum | VARCHAR | SHA-256 of the provisioned weights (provenance) |
| license | VARCHAR | License identifier (must be self-host-compatible) |
| vram_gb | NUMERIC | Declared VRAM requirement (from Appendix B / external vetting) — advisory, not measured here |
| dynamically_loadable | BOOLEAN | True if the engine can load/unload this model on demand (ComfyUI checkpoint, Ollama). False for vLLM-served models (see AD-01.9) |
| default_params | JSONB | Default generation parameters for this model |
| is_default | BOOLEAN | Whether this is the system-default model for its (stage, tier) — at most one true per (stage, tier) |
| enabled | BOOLEAN | Soft on/off switch independent of lifecycle state |
| created_by / created_at | VARCHAR / TIMESTAMPTZ | Audit |
| updated_at | TIMESTAMPTZ | Audit |

**`model_capability_tags`** — many tags per model, used by the selector.

| Column | Type | Description |
|---|---|---|
| id | UUID PK | |
| model_id | UUID FK | Parent model |
| dimension | ENUM | visual_style / subject_affinity / motion_profile / voice_profile / language / quality_bias |
| value | VARCHAR(64) | Tag value within the dimension (taxonomy in Appendix AD-A) |
| weight | NUMERIC | Optional relative strength of this capability (0–1) |

**`model_node_availability`** — which nodes can currently serve which models; maintained by the health poller (AD-01.6).

| Column | Type | Description |
|---|---|---|
| id | UUID PK | |
| model_id | UUID FK | |
| node_id | VARCHAR | e.g., `node-04` |
| status | ENUM | available / loading / unavailable |
| served | BOOLEAN | For non-loadable engines (vLLM): whether the model is currently served on this node |
| last_health_check | TIMESTAMPTZ | |

**`model_approvals`** — the attestation trail (AD-01.7.2).

| Column | Type | Description |
|---|---|---|
| id | UUID PK | |
| model_id | UUID FK | |
| attested_by | VARCHAR | Admin username who recorded the approval |
| vetting_reference | VARCHAR | Pointer to the external acceptance record/ticket |
| checklist | JSONB | Snapshot of the AD-01.7.1 checklist outcomes |
| attested_at | TIMESTAMPTZ | |

**`project_model_selections`** — the binding (replaces ad-hoc, code-level model choice).

| Column | Type | Description |
|---|---|---|
| id | UUID PK | |
| project_id | UUID FK | |
| scene_id | UUID FK (nullable) | Null = project-level selection; set = scene-level override |
| stage | ENUM | Pipeline stage |
| tier | ENUM | prototype / production |
| model_id | UUID FK | Chosen model |
| selected_by | ENUM | auto (planner) / manual (operator/admin override) |
| rationale | TEXT | Why this model was chosen (planner-generated or operator note) |
| created_at | TIMESTAMPTZ | |

A project-level production profile is added to the existing `projects` table (or a satellite table): `target_style` (ENUM), `target_audience` (VARCHAR), `quality_bias` (ENUM: speed / balanced / fidelity).

## AD-01.6 Model Registry Service & availability poller

A registry service (FastAPI, node-01) exposes CRUD for the store (admin-only mutations) and read endpoints for the planner and UI. A background poller — scheduled via the existing Celery Beat (§6) — periodically queries each engine to confirm what is actually loadable and updates `model_node_availability`:

- vLLM: `GET /v1/models` on the node — confirms which models are **served** (sets `served = true`).
- ComfyUI: `GET /object_info` / checkpoint listing — confirms checkpoints present on disk and loadable.
- Ollama: `GET /api/tags` — confirms pulled/loadable models.

The poller asserts **availability**, never **suitability**. A model can be approved and present yet temporarily unavailable (node down, weights not yet provisioned); the selector treats availability as a hard filter.

## AD-01.7 Pre-approval and external compatibility vetting (mandatory boundary)

This subsystem is an **allow-list of pre-vetted models, not a validation harness.** Admins may add models to the store, but a model may only reach `APPROVED` after passing an acceptance process performed **outside this system**, against the actual target hardware. This boundary is deliberate: validating a model against six heterogeneous GPU nodes (mixed NVIDIA Blackwell and Intel B70 Pro), specific CUDA/driver/quantization combinations, and engine versions is an operational, hardware-in-the-loop activity that the IVGS application is not equipped to perform safely. Registering a model is an **assertion that this external acceptance has already succeeded.**

> **Operationalized by AD-04 (2026-06-08).** This external acceptance process is now defined as a standalone platform — the **Model Benchmarking & Certification Platform (MBCP, AD-04)**. The MBCP runs the AD-01.7.1 checklist on representative content against the real target hardware, measures performance and quality, and issues a **certification record**; that record is the attestation AD-01.7.2 requires for `CANDIDATE → APPROVED`. AD-01 remains the allow-list and selection/serving layer; AD-04 is the validation layer that feeds it.

### AD-01.7.1 External acceptance checklist (performed outside IVGS)

Before an admin marks a model `APPROVED`, the operations team must independently confirm and record:

1. **Hardware fit** — the model loads and runs on its intended node(s) within real VRAM headroom (validated against, and used to correct, the Appendix B VRAM matrix), not merely the declared figure.
2. **Engine/runtime compatibility** — confirmed working on the pinned engine version, CUDA/driver stack, and quantization actually deployed (e.g., FP8 vs INT4 behavior).
3. **Throughput sanity** — generation completes within the stage timeout budgets (§6) on representative inputs.
4. **License compatibility** — license permits self-hosted, on-prem use for the intended purpose; recorded in `models.license`.
5. **Provenance & security** — weights obtained from a trusted source, checksum recorded, scanned for known supply-chain risks; no external API dependency (self-hosted mandate).
6. **Output safety** — the model does not introduce content-safety regressions relative to existing approved models for the same stage.

### AD-01.7.2 In-system attestation

The outcome of the external process is recorded in `model_approvals` (AD-01.5.2): who attested, a reference to the external acceptance ticket, a checklist snapshot, and the timestamp. The system enforces only that this record **exists and is complete** before allowing `CANDIDATE → APPROVED`. It does not — and is not intended to — reproduce or re-verify the checks. The attestation makes the approval auditable; the verification itself remains a human, hardware-in-the-loop responsibility.

## AD-01.8 Model selection / planning

### AD-01.8.1 The MODEL_PLANNING stage

A new pipeline stage, `MODEL_PLANNING`, is inserted **after `STORYBOARD_GENERATION`** and before media generation. Storyboard completion is the earliest point at which the system knows, scene by scene, what the video depicts (via each scene's `visual_description`), so it is the natural place to choose media models. Stage-level selections that don't depend on scene content (e.g., the LLM for translation, the TTS voice) may also be resolved here using the project production profile alone.

### AD-01.8.2 Intent sources

Selection is driven by a **capability profile** assembled from two sources:

- **Explicit (project production profile):** `target_style`, `target_audience`, `quality_bias`, captured on the New Project form. Sets stage-level defaults and biases.
- **Inferred (per scene):** an LLM classification call (an existing vLLM stage, prompt-governed under §9) reads each scene's `visual_description` and emits a per-scene capability vector (e.g., `visual_style=line_art`, `subject_affinity=abstract`, `motion_profile=static`). This refines image/video/animation choice per scene.

The two combine through the §9-style hierarchy: project profile sets the baseline; inferred per-scene vectors may override for that scene only.

### AD-01.8.3 Selection algorithm

For each (stage, tier) — and for media stages, each scene:

1. **Candidate set** = `models` WHERE `stage` matches AND `tier` ∈ {requested} AND `state = approved` AND `enabled` AND available on ≥1 node (`model_node_availability`). For non-loadable engines, restrict to models with `served = true`.
2. **Score** each candidate by matching its `model_capability_tags` against the job/scene capability profile, weighted per dimension. Tie-break by node VRAM headroom (from the scheduler) and a configured preference order.
3. **Persist** the top candidate to `project_model_selections` with a human-readable `rationale` (e.g., "selected FLUX.1-dev: visual_style=photorealistic match; production tier; available node-04").
4. If the candidate set is empty, fall back to the `is_default` model for that (stage, tier); if none, raise a planning error surfaced to the operator.

### AD-01.8.4 Manual override

Admins (any project) and operators (own projects) may override any auto-selection at project or scene level via the UI, writing a `selected_by = manual` row with their own rationale. This is the generalization of the dormant `preferred_model` field (gap N23-3).

## AD-01.9 Execution wiring & scheduler integration

**Provider resolution.** Each GPU task resolves its model through the provider factory: `get_provider(stage, job_id, scene_id?)` reads the effective selection (scene → project → default) and returns a provider bound to the selected engine/model/node. No model identity is hard-coded in task code. This is the concrete payoff of implementing §19.1 correctly.

**Residency.** The GPU scheduler reservation request (§12) is extended to carry `model_id`. The scheduler's model-concurrency manager then ensures the selected model is resident on the target node before the task runs, preferring nodes where it is already loaded and evicting by LRU as today.

**Engine constraint (important).** The `dynamically_loadable` flag encodes a hard reality: ComfyUI checkpoints and Ollama models can be loaded/unloaded on demand, but **vLLM serves a fixed model per process** and cannot hot-swap arbitrary large models at request time. For vLLM-backed stages (transcript_refinement, storyboard, translation, mid-size image-prompt generation), the planner is restricted to the set of models **currently served** on the LLM nodes; operations decides, out of band, which LLMs are served per node. The store records this so the planner never selects a vLLM model that isn't actually being served. This also intersects with the unresolved node-02/03 LLM-vs-video contention (gap N23-4): the residency policy and that contention policy should be designed together.

## AD-01.10 User interface

**Model Management page (admin, node-01).** Mirrors the existing Prompt Library admin pattern. A tabbed view by stage; per model: lifecycle state, tier, capability tags, strengths/weaknesses, source URL, license, declared VRAM, node-availability badges (live from the poller), and the attestation record. Actions: register (`CANDIDATE`), edit metadata/tags, approve (requires attestation), deprecate, retire, set default, enable/disable, and a "test" action that runs a minimal generation against an available node. Mutations are admin-only and audit-logged (§13.5).

**Project model panel (operator, project-scoped).** Within Project Detail, a panel showing, per stage and tier, the effective model with an `AUTO` / `OVERRIDE` badge and the planner's rationale; "Override" and "Reset to auto" actions. Scene-level overrides appear in the Storyboard view, consistent with §9 scene-prompt overrides.

## AD-01.11 Security & access control

- Store mutations (register, approve, deprecate, retire, set default, tag edits) are **Admin only**.
- Operators may set project- and scene-level overrides on their own projects; Viewers (v5 role) are read-only.
- Every store mutation and every model approval writes to `audit_log` (§13.5) with before/after snapshots.
- The self-hosted mandate is enforced at registration: any engine implying an external API is rejected.
- Provenance fields (`weights_checksum`, `source_url`, `license`) are required for `APPROVED`.

## AD-01.12 Rollout plan and relationship to outstanding gaps

This feature has hard prerequisites among the current gap set; it must not be built ahead of them.

**Prerequisites (fix first, shaped toward this addendum):**

- **ARCH-1 — provider abstraction.** Must be implemented as a **selection-aware factory**, not static per-engine config. Building it any other way forces a rebuild later. This is the single most important "fix once, the right way" item.
- **ORCH-1 / ORCH-2 — runnable pipeline.** There must be an executing pipeline with a working storyboard→media transition for selections to attach to and for `MODEL_PLANNING` to slot into.

**Fold into the foundation work (avoid double effort):**

- **N23-1/2/3 — video selection, `scene_type`, `preferred_model`.** These are a degenerate special case of this subsystem. Persist `scene_type` as part of the capability-inference input; expose `preferred_model` as a scene-level manual selection.
- **N04-1 / N05-1 — Kokoro and Ollama fallbacks.** These are simply additional approved store entries with appropriate tiers; building them as providers behind §19.1 directly serves the registry.

**Delivery phases (each backward-compatible):**

1. **Phase A — Registry.** Schema, registry service, poller, admin CRUD. No effect on execution: with no selections present, tasks fall back to current static defaults. Fully backward compatible.
2. **Phase B — Binding.** `MODEL_PLANNING` stage, project production profile, provider factory reads selections, scheduler carries `model_id`. Auto-selection becomes live; absence of a selection still falls back to defaults.
3. **Phase C — Intelligence & UX.** Per-scene capability inference, scene-level overrides, full admin/operator UI, test action.

**Backward-compatibility guarantee:** if no `project_model_selections` row exists for a (stage, tier), the provider factory uses the `is_default` model, which is configured to today's static choice. Existing projects continue to run unchanged.

## AD-01.13 Acceptance criteria

- An admin can register a model as `CANDIDATE`, attach capability tags, strengths/weaknesses, source URL, license, and declared VRAM, and the model is **not** selectable until approved. ✓
- A model cannot transition to `APPROVED` without a complete attestation record (`model_approvals`); the system records but does not perform the external checks. ✓
- The Model Management page shows all models by stage with live per-node availability badges sourced from the poller. ✓
- On a new project with a stated production profile, the `MODEL_PLANNING` stage produces a persisted selection per stage (and per scene for media stages) with a human-readable rationale. ✓
- A prototype-tier and a production-tier model are selected and applied to the draft and final render respectively, for at least one project. ✓
- Two projects with contrasting production profiles (e.g., flat vector explainer vs photorealistic cinematic) demonstrably resolve to different image/video models for comparable scenes. ✓
- An operator can override a selection at project and scene level; the override is honored at execution and recorded with rationale. ✓
- A vLLM model that is not currently served is never selected; selection respects the `dynamically_loadable` / `served` constraint. ✓
- With no selection present, execution falls back to the configured default model (existing behavior); no existing project is broken. ✓
- All store mutations and approvals appear in `audit_log`. ✓

## AD-01.14 Open design decisions (for review)

1. **Capability inference cost.** Per-scene LLM classification adds an LLM pass before media generation. Acceptable, or restrict inference to project-level with scene-level only on explicit operator request?
2. **vLLM served set management.** Should the store *drive* which LLMs vLLM serves (triggering ops action / scheduler-managed multi-server), or only *reflect* the served set decided by ops? Draft assumes "reflect."
3. **Default taxonomy.** Appendix AD-A proposes a starter taxonomy; the dimension/value set should be ratified before Phase A schema freeze, as it shapes the tags table and the inference prompt.
4. **Scoring transparency.** Should the planner's score breakdown (not just the rationale string) be persisted for tuning?

---

## Appendix AD-A — Starter capability taxonomy (for ratification)

| Dimension | Candidate values | Applies to stages |
|---|---|---|
| visual_style | photorealistic, cinematic, illustrative, flat_vector, line_art, 3d_render, painterly, diagrammatic | image, video, animation |
| subject_affinity | human_faces, full_body_people, objects, environments, abstract, text_heavy | image, video |
| motion_profile | static, subtle, dynamic | video, animation |
| voice_profile | neutral_professional, warm, expressive, narration | tts |
| language | BCP-47 codes (en-US, es-ES, …) | tts, translation |
| quality_bias | speed, balanced, fidelity | all |

## Appendix AD-B — Illustrative store entries

| name | stage | engine | tier | key tags |
|---|---|---|---|---|
| flux1-dev | image_generation | comfyui | production | visual_style=photorealistic; subject_affinity=human_faces; quality_bias=fidelity |
| flux1-schnell | image_generation | comfyui | prototype | quality_bias=speed |
| sdxl-1.0 | image_generation | comfyui | both | visual_style=illustrative |
| cogvideox-5b | video_generation | cogvideox | production | motion_profile=dynamic; quality_bias=fidelity |
| wan2.1 | video_generation | wan21 | prototype | motion_profile=subtle; quality_bias=speed |
| coqui-xtts-v2 | tts | coqui | production | voice_profile=expressive; language=multi |
| kokoro | tts | kokoro | prototype | voice_profile=neutral_professional; language=en |
| llama-3.3-70b | storyboard | vllm | production | quality_bias=fidelity (dynamically_loadable=false) |

*Entries are illustrative; declared VRAM, checksums, licenses, and attestations are populated through the external acceptance process (AD-01.7).*

---

*Prepared as an additive addendum under the §18 change-control process. This subsystem is non-functional until the §19.1 provider abstraction is implemented as a selection-aware factory (gap ARCH-1) and the pipeline runs end to end (gaps ORCH-1/2). It does not perform hardware-compatibility validation; the Model Store is an allow-list of externally pre-vetted, self-hostable models.*
