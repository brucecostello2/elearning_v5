# Assessment — External "Master Orchestrator Prompt" vs IVGS Architecture

| | |
|---|---|
| **Date** | 2026-08-22 (code-verified same day against operator-supplied snapshot of `elearning_v5` main) |
| **Trigger** | Operator posed a green-field design question to an outside agent (multi-node instructional-video system); the agent produced a master storyboard-generation prompt + architectural recommendations. Operator asked: how far does it differ from IVGS, and does it expose gaps? |
| **Source** | `Master_Orchestrator_Prompt_Instructional_Video.docx` (operator upload; node references in it are wrong — its node-02 is the 48GB card, etc.) |
| **Compared against** | ivgs_v5_functional_spec (§8.1.2 inputs, §9.2 storyboard prompt), AD-01 (model bindings), AD-02 (node specialization), AD-03 (composition fidelity), AD-05 (Temporal), AD-07 (Brief & Scene Contract v2), MBCP SSOT v3.3 (storyboard stage contract, Appendix A.5); **code claims verified against the repo snapshot — see §5** |

## 1. Verdict in one paragraph

The external design converges on the same core thesis AD-07 already ratified: the storyboard is the canonical, machine-executable production contract; downstream workers execute it without reinterpreting the course. No architectural conflict. The difference is contract richness — IVGS's scene contract is ~5 core fields (scene_index, narration_text, visual_description, media_type, duration_seconds, plus AD-07's brief fields); the external schema is ~10x richer. Some of that richness names genuine IVGS gaps; some of it is weaker than what IVGS already learned the hard way. Recommendation: harvest fields into AD-07 v2.x and AD-05, do not adopt the monolithic-prompt shape.

## 2. Genuine gaps exposed in IVGS

**G1 — Cross-scene visual continuity (highest value).** IVGS has no persistent character IDs (CHAR001), environment IDs (ENV001), reusable-asset IDs, or per-project style bible consumed by generation stages. Each scene's visuals generate independently from that scene's visual_description; only prompt-level phrases ("consistent color palette") resist style drift. Masked today because the presenter is real footage (talking-head PiP), not generated. Becomes acute when generated visuals dominate or the certified head model (WS-H) lands. **Candidate: AD-07 contract extension — style_bible block + continuity ID namespaces, threaded into stage-3 prompt compilation.**

**G2 — PowerPoint ingestion.** Absent entirely from IVGS (§8.1.2 inputs: transcripts, optional storyboard doc, head clip). The external per-slide triage taxonomy (REUSE / RESTYLE / REBUILD / EXTRACT / REFERENCE_ONLY / OMIT), with speaker notes evaluated separately from slide content, is a sound design for it. **Candidate: new scoped addendum, only when PPT input becomes a real requirement. A new input pathway (stage-0 feature), not a tweak.**

**G3 — Explicit dependency graph in the storyboard.** IVGS parallelism is implicit in Celery fan-out; the storyboard declares no dependencies or parallel groups. The external design has the storyboard declare depends_on + parallel_group, compiled by the orchestrator into a DAG. This is exactly the natural shape for Temporal workflows. **Candidate: absorb into AD-05 design at M3 — design the DAG-from-storyboard in from the start rather than retrofitting.**

**G4 — Source traceability.** No IVGS linkage from a storyboard scene back to which uploaded transcript (or which portion) it derives from; no marking of inferred vs sourced content. The external SRC-* reference scheme + source_type:"inferred" is cheap to add at storyboard time. Matters most for regulated/safety content. **Candidate: optional source_refs field in the scene contract.**

**G5 — Plan-time duration budgeting.** IVGS discovers real duration at Stage 5 (TTS) and anchors the timeline on measured audio (AD-03 Pillar 1). The external design budgets at storyboard time (135-155 wpm, per-scene estimates, +/-3% tolerance, QC gate before production). The estimate is strictly weaker than measurement but catches gross over/under-scoping before GPU spend. **Candidate: cheap advisory check in stage 2 — never allowed to override the measured-audio anchor.**

**G6 — Localization-aware visual rule.** "Avoid text embedded in generated images; composite text separately so it can be localized." IVGS's image prompt bans watermarks and its video prompt bans text-in-video, but the rationale (per-language re-render avoidance) is not systematized. Cheap prompt-level adoption.

**G7 — Accessibility marking (minor).** Captions exist (SRT/VTT, burned-in). No per-scene marking of visual-only information needing audio description. Low priority for current use.

## 3. Where IVGS is ahead — do not regress toward the document

**Timing model.** The document trusts plan-time estimates end-to-end. AD-03's core lesson: only measured audio length anchors the timeline (durations from real TTS output; single A_timeline; head driven by the exact final track). IVGS's model is strictly stronger. Adopt G5 as an early-warning only.

**Model management.** The document says "capability classes" and stops. AD-01 + MBCP make this concrete: registry, attestation, certification metrics (storyboard stage: schema-validity + task score), tiers, bindings resolved via the provider factory. The document has no answer to model quality or provenance.

**Prompt architecture.** The document is one monolithic mega-prompt asking one model to be instructional designer, director, cameraman, localization planner, accessibility reviewer, and scheduler at once. IVGS splits refinement (stage 1) from storyboard (stage 2), versions every prompt (3-tier Jinja hierarchy, full history, rollback), supports scene-level overrides and per-scene regeneration via GUI. Monolithic output cannot be partially regenerated and is harder to certify. Harvest the document's fields, not its shape.

**Failure discipline.** The document: "retrying failed tasks" (one line). IVGS: swallow-failure register + static detector, checkpoints, corruption detector, metric honesty (alignment_gate_non_functional, av_drift_seconds), evidence rules. The operational hard part is entirely absent from the document.

**Scheduling reality.** The document's "orchestrator assigns workers by availability/VRAM/queue depth" describes a scheduler IVGS deliberately deferred: AD-02 pins stages to nodes today; dynamic capability-based scheduling is the M3/Temporal era. The document's model matches where IVGS is going, not a gap in where it is.

## 4. Disposition summary

| Item | Disposition |
|---|---|
| Storyboard-as-contract philosophy | Already ratified (AD-07). No action. |
| G1 continuity IDs + style bible | Propose as AD-07 v2.x extension (pre-work for WS-H / generated-visual era) |
| G3 dependency graph / parallel groups | Fold into AD-05 Temporal design at M3 |
| G2 PowerPoint ingestion | New addendum candidate; only when the input is actually required |
| G4 source refs, G5 plan-time duration check, G6 no-text-in-images rule | Cheap adds; batch into the next contract/prompt revision |
| Monolithic mega-prompt, estimate-anchored timing | Rejected — IVGS's existing design is stronger |

Nothing in the external document invalidates the current build sequence (M-plan v0.4) or any in-flight work package.

## 5. Code verification (operator-supplied repo snapshot, 2026-08-22)

The gap claims above were checked against the actual codebase, not just the docs.

**Scene contract is exactly five fields — G1/G3/G4 confirmed.** `ivgs-api/app/models/storyboard_scene.py` (table `storyboard_scenes`, migration 0001) carries scene_index, narration_text, visual_description, media_type (image/video_clip/animation), duration_seconds — nothing else. `ivgs-api/app/schemas/storyboard.py` mirrors it. No continuity IDs, no source refs, no style bible, no dependency fields anywhere in the schema. The AD-07 `contract/` vendoring is **not present in this snapshot** — consistent with WP-IVGS-0 being held, not yet executed.

**Duration target is a prompt suggestion, not a gate — G5 confirmed.** In `ivgs-workers/tasks/stage2_storyboard.py`, the baked template says "Total duration across all scenes should be approximately {{ max_duration_seconds }} seconds" (~line 792). The parser clamps each scene to 3-120s and sums `total_duration` for logging (~lines 288, 320, 661), but **no code compares the total against max_runtime_seconds** — no tolerance check, no warning, no gate. A storyboard 2x over target proceeds silently to GPU spend.

**Style mechanism is a single hardcoded string — G1 sharpened.** `stage3_images.py` reads `project_context.get("visual_style", "professional, clean, modern")` (~lines 100, 179), and `visual_style` appears **nowhere in ivgs-api** — the API never populates it, so every project always generates with the hardcoded default. This is the defect-0.1 pattern again (a field the pipeline reads but nothing upstream supplies) — worth folding into the WP-IVGS-0 defect class when the contract is extended.

**Brief plumbing defaults confirm defect 0.1's shape.** `stage2_storyboard.py` reads `context.get("project_description", "")` and `context.get("max_runtime_seconds", 600)` (~lines 128-131) — silent defaults if the caller doesn't populate, exactly the failure mode WP-IVGS-0 defect 0.1 addresses.

Net effect of verification: G1 and G5 are stronger than the doc-based assessment stated — the style knob exists but is dead (always default), and duration is entirely unenforced at plan time. Both are the same defect family WP-IVGS-0 is about to fix (fields read by the pipeline that nothing supplies or checks), which argues for handling G1/G5's plumbing in the same architectural style as WP-IVGS-0 when the AD-07 v2.x extension is drafted.
