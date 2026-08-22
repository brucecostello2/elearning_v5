# AD-07 — The Brief and the Scene Contract
## Joint Functional Specification Amendment: IVGS v5 + MBCP
### Summary form, sufficient to derive implementation plans for both codebases · Draft for operator ratification · 2026-08-21

---

## §1 Authority and scope

This amendment amends **both** governing documents at once and is subordinate to each:

- **IVGS v5 Functional Specification** — as Addendum AD-07. Where AD-07 conflicts with the current pipeline implementation, AD-07 governs; the implementation is defect.
- **MBCP Master Functional Specification SSOT v3.4** — as the contract source for the stage I/O contracts (Appendix A) of `transcript_refinement`, `storyboard`, `translation`, `tts`, `video_generation`, `animation_generation`, `talking_head`, `composition`, and for new scorers. **The frozen seams are untouched:** the six-check gate (§12.2), the quality-gate conjunction, and the export factory (§12.4) do not change. `request_constraints` (Appendix G D-19) is *extended*, not altered.

**The principle this amendment exists to enforce:** the user's stated intent — what the video teaches, who it is for, and how long it may run — MUST reach, in machine-readable form, every stage that makes a creative decision; and every stage's output MUST be directly consumable by the next stage without re-derivation. MBCP benchmarks models **against exactly these contracts** — never against a looser private version.

**Grounding.** This amendment resolves the measured dead-ends of the 2026-08-21 gap analysis (`MBCP_IVGS_Stage_Contract_Gap_Analysis.md`): the runtime target that never leaves the API (`project_service.py:290-299` → default 600), the description dropped after Stage 1 (`pipeline_orchestrator_v2.py:805-814`), the audience field with no write path, the five-field storyboard, the unbenchmarked prompt-writer, the animation stage that renders stills, the unbuilt translation stage, and the absence of any duration reconciliation.

---

## §2 Two new normative objects

### §2.1 The **Brief** — one JSON object, authored at project creation, immutable per project version

| Field | Type | Req | Notes |
|---|---|---|---|
| `title` | string ≤255 | ✔ | the video's name |
| `objective` | string ≤500 | ✔ | what the viewer will be able to do afterwards — *"teaches viewers how to press a shirt"* |
| `audience` | string ≤255 | ✔ | who it is for, in plain words |
| `description` | string ≤1000 | ○ | free context |
| `runtime_target_seconds` | int 60–7200 | ✔ | THE duration budget |
| `runtime_tolerance_pct` | int, default 10 | ○ | acceptable deviation of the finished video |
| `source_language` | BCP-47 | ✔ | language of the supplied script |
| `target_languages[]` | BCP-47 | ○ | additional audio tracks to produce |
| `tone` | enum: `neutral · friendly · formal` | ○ | default neutral |
| `visual_style` | string ≤255 | ○ | e.g. "clean studio photography, no text overlays" |

**IVGS:** carried whole on `PipelineJobContext`; every stage dispatch includes it verbatim; the orchestrator MUST NOT reconstruct context from a prior stage's output (kills `_extract_context()` as a context source). Persisted on `projects` (new JSONB column `brief`; legacy columns become a view of it).
**MBCP:** new fixture kind **`brief`** (JSON, schema-validated on upload, excerpt-rendered like text). New required input slot `brief` on `transcript_refinement` and `storyboard`; optional on `translation` and `tts`.

### §2.2 The **Scene Contract v2** — the storyboard's output, the pipeline's backbone

Document level: `{ brief_ref, scenes[], total_duration_seconds }` — where `total_duration_seconds` MUST equal the sum of scene durations and MUST be within `runtime_tolerance_pct` of `runtime_target_seconds`. **This check is a validator with a body**, in both systems (it replaces IVGS's hollow `_validate_storyboard_json(max_duration)` and MBCP's shot-count-only scorer).

Per scene — every field persisted, every field with a named consumer:

| Field | Type | Req | Consumer |
|---|---|---|---|
| `scene_index` | int | ✔ | ordering, manifest |
| `scene_title` | string | ✔ | review UI, captions |
| `narration_text` | string | ✔ | TTS (§4.5), translation (§4.3), captions |
| `duration_seconds` | float 3–120 | ✔ | manifest timeline; TTS word budget; video frame count |
| `media_type` | enum: `image · video_clip · motion_graphic · talking_head` | ✔ | fan-out router |
| `visual.image_prompt` | string | ✔ if image/motion_graphic | the image engine — **directly**; the hidden Stage-3 prompt-writer LLM is retired (§4.4) |
| `visual.negative_prompt` | string | ○ | image engine |
| `visual.style` | string | ○ | image engine; defaults from `brief.visual_style` |
| `video.prompt` | string | ✔ if video_clip | video engine — directly |
| `video.target_duration_seconds` | float | ✔ if video_clip | video engine; MUST respect the model's declared clip cap (§5.2) — no silent truncation |
| `motion.kind` | enum: `ken_burns · pan_zoom · slide · component` | ✔ if motion_graphic | the motion renderer (§4.6) |
| `motion.params` | object (per-kind schema) | ✔ if motion_graphic | motion renderer |
| `transition.type` | enum: `cut · fade · dissolve` | ✔ | composition |
| `transition.duration_ms` | int 0–2000 | ✔ | composition (booked inside the scene's duration) |
| `notes` | string | ○ | human review only |

**One schema, two consumers.** The Scene Contract and the Brief are defined once as JSON Schema files in a versioned `contract/` directory that **both repos vendor byte-identically**; each repo's gate (MBCP battery G-check; IVGS CI) pins the schema files' hash, so drift fails a build rather than a video (§6.3).

---

## §3 The duration law (both systems)

1. The budget originates in the Brief and reaches Stage 1 and Stage 2 prompts **with the project's real value** — the literal-600 path is a defect (IVGS-0.1, §5.1).
2. The storyboard validator enforces the sum-vs-target tolerance; over/under budget is a **stage failure with a sentence**, not a note.
3. TTS is asked for the scene's duration and its **produced duration is measured against it**; deviation beyond ±20% per scene is recorded per scene and surfaced at review (fail-soft: recorded always, gating configurable).
4. After TTS, the manifest is **re-timed from measured audio** before lock; the pre-TTS lock order is reversed. `total_duration_ms` becomes a measurement, not a guess.
5. Video clips are requested at `video.target_duration_seconds`; a request beyond a model's declared cap is **refused at planning time** (the cap travels in MBCP's `request_constraints`, §5.2) — never truncated silently at render.
6. The finished video's measured duration vs `runtime_target_seconds` is recorded on the project. Within tolerance = the product's headline promise, kept and shown.

---

## §4 Stage-by-stage requirements

Each row states: **I** = IVGS change · **M** = MBCP change (contract, params, scorers). Scorers marked ⚙ are deterministic; ⚖ are rubric-scored by the self-hosted judge (§4.9).

### §4.1 Transcript refinement
- **In:** Brief + raw transcripts. **Out:** refined narration text + `estimated_spoken_seconds` (words ÷ stated WPM).
- **I:** thread the real Brief (kills the 600-default and the empty description); fix binding bypass (IVGS-0.2).
- **M:** add `brief` slot; params gain `wpm` (default 150). Scorers: ⚙ **length-fit** (estimated vs budget, ±10%), ⚙ reading level (Flesch-Kincaid band), ⚙ fact-preservation floor (no numeral/named-entity lost vs source), ⚖ objective-fit. WER-vs-gold is demoted to advisory — a model that improves on the gold must not score worse.

### §4.2 Storyboard
- **In:** Brief + refined transcript (+ optional user storyboard as a *seed*, finally consumed). **Out:** Scene Contract v2.
- **I:** generate to v2; persist ALL fields (today `scene_title/transition/notes` are dropped at `stage2_storyboard.py:391-397`); validator body per §3.2.
- **M:** contract replaced by Scene Contract v2. Scorers: ⚙ schema-valid, ⚙ duration-sum fit, ⚙ narration coverage (transcript text accounted for across scenes), ⚙ **directive completeness** (every scene carries the specs its `media_type` requires — the "description=`x` scores 1.0" hole closes), ⚖ visual-brief quality.

### §4.3 Translation — becomes a real stage
- **In:** Scene Contract narration (per scene) + Brief + target language. **Out:** translated narration per scene, length-aware.
- **I:** build the missing worker task + queue; wire `LanguageVariant` rows to it.
- **M:** scorers add ⚙ language identification (output is IN the requested language), ⚙ per-scene length ratio (dubbing fit), ⚙ term consistency across scenes; chrF stays advisory.

### §4.4 Image generation
- **In:** `visual.image_prompt` from the scene — **directly**. The Stage-3 prompt-writer LLM is retired; prompt authorship moves into the storyboard stage where it is benchmarked (§4.2). **M:** unchanged scorers (CLIP/FID) now measure against the scene's own prompt.

### §4.5 TTS
- **In:** per-scene narration + `duration_seconds` (+ voice per the WP-F54 model). **M:** new ⚙ **duration-fit scorer** (measured `duration_seconds` vs requested, per scene) joins SNR/clipping/round-trip-WER; it is the metric that keeps the whole timeline honest.

### §4.6 Animation → split into two honest capabilities
- **`motion_graphic`** (new, deterministic): executes `motion.kind/params` over a scene image — Ken Burns, pan/zoom, slide, component. IVGS builds it as a render service (adopting the orphaned `motion_graphics.py`); MBCP benchmarks it as an `engine_only` adapter (like ffmpeg-composition) with ⚙ structural checks. This is what instructional videos actually need per scene.
- **`animation_generation`** (existing pose-guided image+pose→video capability) is unchanged in MBCP and remains available to IVGS for reenactment scenes — but IVGS stops pretending its animation scenes use it. The current behaviour (animation scene → still image) is defect IVGS-0.5.

### §4.7 Talking head
- **I:** unchanged flow (one render per project, 30 s segments). **M:** add a **long-form suite**: concatenated multi-scene audio, segmented render, ⚙ identity/quality stability across segment boundaries, per the repo's own open AD-01.13 note.

### §4.8 Composition
- **I:** the richer manifest (`services/manifest_builder.py` — transitions, caption timestamps, render profiles) is promoted from dead code to THE manifest; multi-language audio tracks attach per `target_languages`. **M:** the structural-diff scorer grows to assert transitions and track counts against that manifest schema.

### §4.9 The rubric judge (new MBCP scorer class)
⚖ scorers (objective-fit, visual-brief quality) run on the **self-hosted authoring LLM (.53)** with a pinned model + pinned rubric prompt, INV-5/INV-6 compliant, versioned in `scorer_versions`, **advisory-only until calibrated against ≥30 human judgments** (Appendix G row on creation). No external API, ever.

---

## §5 Preconditions

### §5.1 IVGS defect fixes (WP-IVGS-0 — before any contract work lands)
1. Thread `max_runtime_seconds` + Brief into every dispatch (`project_service.py:290-299`); stop context reconstruction.
2. **Binding bypass:** Stages 1, 3-prompt-writer, 5-optimiser call env-config models while *reporting* the AD-01 binding (`stage1_transcript.py:339-347` vs `:658`). Fix to Stage 2's correct pattern. Until fixed, no certification is meaningful.
3. **Tier dispatch:** `tier` is never set; production-tier selections are unreachable. Thread it.
4. **Prompt resolution:** the all-ten-prompts / substring-"system" / last-wins path can make `translation.j2` Stage 1's prompt with the transcript vanishing. Fix endpoint + classifier.
5. New Project form: multipart-vs-JSON mismatch, language-code mismatch, unconsumed uploads.

### §5.2 Certification linkage (extends D-19, no seam change)
`request_constraints` gains per-model **`max_clip_duration_seconds`** (video) and **`duration_fit`** measured tolerance (TTS) so IVGS's planner can refuse an impossible scene before GPU time — the same pattern as geometry.

---

## §6 Coordinating the development — recommendations

### §6.1 Should one agent operate across both codebases? **No — with one deliberate exception.**
Implementation agents stay **one per repo**, for the reasons this project already proved on MBCP: different fleets (.51/.52/.53 vs the IVGS VM), different gate batteries and deploy choreographies, different held-commit discipline — and an agent whose tree spans both can "fix" a contract mismatch by quietly bending whichever side is easier, which is precisely the failure this amendment exists to prevent. A mismatch must fail loudly at the seam, not be absorbed silently inside one session.
**The exception:** *read-only* cross-codebase work — analysis, verification, contract-drift audits (this amendment's own evidence was produced that way). Cross-repo READ, single-repo WRITE.

### §6.2 The working structure (extends the proven model)
- **Operator (Bruce)** — rulings, batteries, pushes, deploys, walks. Unchanged.
- **Orchestrator (this session)** — owns AD-07 and the contract text; writes all work orders; reviews all albums/reports; arbitrates every seam question. No agent edits `contract/` without an operator-signed order.
- **MBCP ENGINE + UX sessions** — unchanged roles.
- **New: IVGS session** — same rules MBCP agents follow today (complete work orders in `dev/workorders/`, commit-and-HOLD, operator pushes, report with evidence). Its first order is WP-IVGS-0 (§5.1) — self-contained defect fixes needing no contract.
- **New: one recurring VERIFIER task** — read-only across both repos: schema hashes identical, contracts materially implemented, bindings actually used (a re-run of the §5.1-2 check). Runs before each cross-system milestone.

### §6.3 The contract as code — how drift is made impossible
One `contract/` directory (JSON Schemas: `brief.schema.json`, `scene_contract.schema.json`, version file) vendored **byte-identically** into both repos. Each side's gate pins the SHA-256 of those files; changing the contract is: operator-approved amendment → same commit-pair lands in both repos → both gates re-pin. A one-sided edit fails that side's own battery. (Same mechanism as MBCP's pinned-image law, applied to a schema.)

### §6.4 Sequencing (each phase = implementable work packages per repo)
- **Phase 0** — WP-IVGS-0 defect fixes ∥ MBCP continues its current queue. No coupling.
- **Phase 1** — ratify AD-07 §2 schemas; land `contract/` in both repos with pinned hashes; MBCP: `brief` fixture kind + S1/S2 contracts + deterministic scorers; IVGS: Brief threading + Scene Contract v2 generation/persistence/validator. **Exit test:** one golden project's storyboard, produced by IVGS, validates byte-for-byte under MBCP's storyboard contract.
- **Phase 2** — TTS duration-fit (both sides), translation stage (IVGS) + translation scorers (MBCP), video duration caps via `request_constraints`.
- **Phase 3** — motion_graphic capability (both sides); composition manifest v2; talking-head long-form suite.
- **Phase 4** — rubric judge calibration; the end-to-end golden round trip: a fixture Brief through all IVGS stages on MBCP-certified models, finished video within runtime tolerance, every stage's model verified as the certified one.

### §6.5 What is deliberately NOT in this amendment
No change to the six-check gate, the export factory, the operating envelope, or `request_constraints` semantics beyond §5.2. No UI redesigns (WP-F54/F55 proceed independently). No model choices — this defines what stages exchange, not which models serve them.

---

*Ratification: operator sign-off converts this draft into IVGS Addendum AD-07 and the corresponding MBCP SSOT amendment (Appendix A contract revisions + new Appendix G rows: the contract-vendoring decision, the rubric-judge calibration item, and the animation capability split).*
