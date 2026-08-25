# IVGS v5 — Functional Specification Addendum AD-09 (Draft 1)

## Production Content Libraries, Branding, and Authoring UX

| | |
|---|---|
| **Addendum** | AD-09 — **Draft 1 (2026-08-24)** |
| **Status** | **DRAFT for review.** Not for implementation until §AD-09.14 questions are settled. |
| **Classification** | Internal Working Document |
| **Change-control status** | Draft for review (per §18 change-control process) |
| **Verified against** | `elearning_v5-main` snapshot supplied 2026-08-24 (post-WP-39; `talking_head_task.py` now resolves via `build_provider` — **ORCH-6 confirmed closed in this snapshot**) |
| **Depends on** | AD-01 (Model Management / provider binding); AD-03 (Composition Fidelity, Pillar-1 audio-anchored durations); AD-04 / MBCP (certification); AD-07 (Brief & Scene Contract) |
| **Related** | AD-05 (Temporal) — the Stage-5/6 topology change in §AD-09.6 must land in the workflow definition, not the Celery map, if it follows M3 |
| **Supersedes** | Nothing. Additive. |
| **Theme** | Moves IVGS from one-off course production to repeatable, branded, multi-course production. |

---

## AD-09.1 Purpose

IVGS v5 produces a course from a transcript and a presenter clip, with every input supplied per project and every setting chosen per project. Nothing is reusable between courses: branding is re-uploaded, model choices are re-made, presenter identity is not guaranteed consistent, and a finished course cannot be re-derived with one element changed.

This addendum introduces four persistent libraries — **Assets**, **Presets**, **Intro/Outro Templates**, **Finished Courses** — and the authoring-surface changes that consume them. It also specifies per-scene presenter control, logo overlay, typography tokens, and a voice/video coupling model that keeps engine choice free.

## AD-09.2 Scope and non-goals

**In scope:** new persistent entities and their lifecycle; the storyboard structural-scene model; per-scene presenter and overlay controls; the voice/video coupling contract; the authoring and media-panel UX that consumes all of the above.

**Not in scope:**

- Generation logic inside any stage.
- The MBCP certification process itself. New engines still certify through AD-04.
- Node power configuration. *The 450 W GPU power-limit change is a node configuration item and does not belong in a functional specification addendum — it is recorded as an ops errata alongside the AD-08 RAM and node↔card items.*
- Multi-job concurrency (AD-08).

## AD-09.3 Precondition — the Phase-5 stub family

**A blocking finding from the code review, wider than the single defect reported.**

`storyboard_service.regenerate_scene()` creates a `RenderJob` row, logs "Scene regeneration queued", and returns it. The dispatch is a comment (`storyboard_service.py:174-175`). The endpoint returns success with a job id; nothing executes. This is why single-scene regeneration "doesn't work".

It is **not an isolated defect.** The same pattern — create a job row, return 202, never dispatch — is present at:

| Location | Endpoint affected | Consequence |
|---|---|---|
| `storyboard_service.py:174` | `POST /projects/{id}/scenes/{sid}/regenerate` | Scene regeneration silently does nothing |
| `assets.py:180-191` | `POST /assets/{id}/regenerate` | Asset regeneration silently does nothing |
| `job_service.py:58,78` | `POST /jobs/{id}/cancel` | **Cancel marks the row cancelled and never revokes the task — work continues on the GPU** |
| `dlq_service.py:96,123,207` | DLQ replay (single and bulk) | **Replay reports success and replays nothing** |
| `language_service.py:130` | `POST /projects/{id}/languages/{lid}/retry` | Localisation retry does nothing |
| `quality_service.py:226` | Quality-review reject → regenerate | Rejection does not trigger regeneration |
| `checkpoint_service.py:243` | `POST /jobs/{id}/resume` | Resume dispatches nothing |
| `prompt_service.py:338-345` | `POST /prompts/test` | **Prompt Playground returns a canned string, not model output** |

Only `project_service.py` (`:334`, `:446`) dispatches for real.

This is the same class as the checkpoint no-op and the backup-success-on-failure defect: **a green surface over an empty action.** Two of these are worse than the reported one — a cancel that doesn't cancel wastes GPU time and, under AD-08 concurrency, holds a reservation another project is waiting on; a DLQ replay that doesn't replay silently discards recovery attempts.

**AD-09 requirements below assume these are fixed.** Building preset-driven regeneration and course re-derivation on top of a dispatch layer that returns success without acting would multiply the failure surface. Recommend raising the family as a single ledger item ahead of AD-09 work, with a test that asserts a broker message is produced — not that a 202 is returned.

## AD-09.4 Asset Library

### AD-09.4.1 Why a new table, not `project_id NULL`

The existing `assets` table is project-scoped by construction: `project_id` is `NOT NULL` with `ON DELETE CASCADE`, and the storage-tier, quota and retention machinery all key on project ownership. Relaxing `project_id` to nullable would put library assets inside a cascade path and inside per-project quota accounting, where they do not belong.

**Specify a separate `library_assets` table** with its own lifecycle, plus a reference from project assets to their library origin.

### AD-09.4.2 `library_assets`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `kind` | ENUM | `logo` / `video_clip` / `audio_clip` / `music_bed` / `reference_clip` / `reference_image` / `font` / `document` |
| `name`, `description` | VARCHAR / TEXT | |
| `seaweedfs_fid`, `seaweedfs_path`, `mime_type`, `file_size_bytes`, `duration_seconds` | as `assets` | Same storage path; different ownership |
| `tags` | JSONB | Free-form retrieval |
| `owner_scope` | ENUM | `global` / `user` — global mutable by admin only |
| `created_by`, `created_at`, `updated_at` | | |
| `superseded_by` | UUID FK, nullable | Library assets are never hard-deleted while referenced |

**Reference, don't copy.** A project consuming a library asset records `library_asset_id` on its `assets` row rather than duplicating the binary. This is what makes §AD-09.7 course re-derivation possible: swapping a logo becomes a reference change, not a re-upload. It also addresses the B3 duplicate-asset accumulation already in the ledger.

**Upload-on-use.** Per the requirement: any media uploaded during project creation is written to the library as well as to the project, with `owner_scope = user` by default and a promote-to-global admin action.

### AD-09.4.3 Actors — presenter identity as a first-class entity

"Same actor with the same voice" is not expressible as a file. Specify an **`actors`** entity:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | VARCHAR | Operator-facing identity, e.g. "Sarah — corporate" |
| `reference_clip_id` / `reference_image_id` | FK → `library_assets` | Whichever the bound engine requires |
| `voice_profile` | JSONB | Engine-scoped: TTS voice id / speaker embedding ref / seed / joint-engine voice params |
| `engine_bindings` | JSONB | Per-engine parameter sets required to reproduce this identity (see §AD-09.6.3) |
| `default_orientation` | ENUM | `landscape` / `portrait` |
| `certified_model_id` | FK, nullable | The AD-01 model this identity was established against |

The `engine_bindings` field is the mechanism that answers "MagiHuman needs certain configurations set up, and keeping the same actor and voice needs other settings." Those settings are recorded against the actor, not rediscovered per project.

**Constraint to record:** an actor's identity is only reproducible on the engine it was established against. Changing the bound engine is an identity change, and the UI must say so rather than silently producing a different-sounding presenter.

## AD-09.5 Presets

A **preset** is a named, versioned bundle of choices applied at project creation:

- Asset selections — logo, intro/outro templates, music bed
- Actor selection, default presenter placement (position, scale, orientation), lipsync mode
- Model selections per stage/tier (references AD-01 `project_model_selections` shape)
- Media defaults — default `media_type`, resolution tier, framerate
- Typography tokens (§AD-09.10) and brand colours
- Logo policy — always-on / off / per-scene default

Stored as `presets(id, name, description, payload JSONB, version, is_active, created_by, ...)`, versioned rather than mutated so a course records which preset **version** produced it.

**Presets are defaults, not constraints.** Applying a preset writes concrete values into the project; subsequent per-project edits do not mutate the preset. A project records `preset_id` + `preset_version` for provenance and a `preset_drift` indicator where values diverge.

## AD-09.6 Voice/video coupling — the lipsync question

### AD-09.6.1 The operator's proposal is the right architecture

Recorded verbatim as the design decision: **audio and video are always persisted as separate assets and reassembled downstream, regardless of which engine produced them.**

This is correct and should be normative, because it preserves four things that currently work:

1. **AD-03 Pillar-1 audio-anchored durations.** Stage 7 anchors scene duration on measured audio length. That requires an audio artefact with a real duration, independent of the video.
2. **The presenter-video toggle.** "Head video off, audio always on" (§AD-09.9) is free if they are separate assets, and requires a demux at render time if they are not.
3. **Caption and alignment work.** WhisperX alignment and the B2 caption-clock fix consume audio directly.
4. **Engine freedom.** A future engine that separates them, or one that joins them, both land in the same downstream contract.

### AD-09.6.2 Two coupling modes, one contract

Specify a `voice_video_coupling` mode on the presenter binding:

| Mode | Stage 5 | Stage 6 | Downstream |
|---|---|---|---|
| **`decoupled`** (current) | TTS produces `audio` asset | Lipsync engine consumes audio + reference → `talking_head` asset | unchanged |
| **`joint`** (MagiHuman-class) | **Skipped** | Engine generates speech and face together from narration text + actor binding; output is **demuxed** into an `audio` asset and a `talking_head` asset, both registered with real durations | unchanged |

**The invariant:** by the time Stage 7 runs, the database state is identical in both modes — one audio asset and one talking-head asset per scene, scene-linked, with measured durations. Stage 7 and Stage 8 require no knowledge of which mode produced them.

The "toggle lipsync on/off" in the UI is therefore a **presenter-mode selector**, not a pipeline branch the operator has to reason about: `decoupled` / `joint` / `audio-only` (no presenter video generated at all).

### AD-09.6.3 MBCP implications

The MBCP `talking_head` stage contract (SSOT Appendix A.1) takes `audio` as an **input**. A joint engine does not fit that contract — its input is text plus an actor binding, and its output includes audio. This needs either a new stage contract or a declared variant, with its own scorers (the existing `lse_c`/`lse_d`/`sync_offset_ms` still apply; voice-identity consistency does not yet have a metric). **Owned by the MBCP SSOT, not by this addendum** — flagged here so it is not discovered at certification time.

## AD-09.7 Structural scenes — intro and outro

### AD-09.7.1 Model

Every generated storyboard receives an intro scene at index 0 and an outro scene at the tail, defaulting to a **blank template** — present in the timeline, visible in the storyboard, generating nothing.

Implementing this by manipulating `scene_index` alone would be a mistake: everything downstream keys on scene ordering (manifest layers, segment planning, per-scene assets, the `ix_storyboard_scenes_project_index` index). Instead:

- Add **`scene_kind` ENUM** to `storyboard_scenes`: `content` / `intro` / `outro`. Default `content`; existing rows backfill to `content`.
- Structural scenes participate in ordering normally but are excluded from narration-derived operations (transcript mapping, TTS of narration, AD-07 brief fields).
- Add **`template_instance_id`** FK, nullable — the applied intro/outro template and its per-project overrides.
- A structural scene with no template resolves to zero duration and contributes no layers to the manifest.

### AD-09.7.2 Intro/outro templates

`intro_outro_templates(id, name, kind, definition JSONB, preview_asset_id, version, ...)` where `definition` carries: logo asset ref and placement, background (colour / image / clip ref), title text and position, subtitle/description, optional learning-objectives block, typography token refs, audio bed ref, animation description, and duration.

**Render path:** Remotion on the node-06 compositor, which already renders lower-thirds and animated titles per AD-02.5a. No new engine.

**Per-project override:** a template instance holds the template reference plus a sparse override map, so a project can change the title text without forking the template. Editable from the project media panel per the requirement.

## AD-09.8 Finished Course Library

A **course record** is the complete, re-derivable definition of a produced course: input transcripts (by reference), preset id + version, actor, model selections per stage, template instances, per-scene settings, the locked composition manifest checksum, and the final render asset refs.

The use case — *"recreate this course with a different logo and a different talking head, save as new"* — is a **fork**: clone the course record, rebind the changed elements, re-run. This only works if project inputs are references rather than embedded uploads, which is why §AD-09.4 must land first.

**Two properties worth stating explicitly:**

- **Re-derivation is not reproduction.** Generative stages are not deterministic across runs unless seeds are captured and the same model version is bound. Where exact reproduction matters, the course record must capture seeds and model version pins; where it does not, the operator should be told the visuals will differ. Do not promise reproducibility the pipeline cannot deliver.
- **Fork depth.** Changing a logo need not re-run generation at all — it is a composition-layer change, so a fork can re-run from Stage 4. Changing the actor requires re-running Stages 5/6 onward. The course record should carry a **minimum re-entry stage** computed from what changed, rather than always re-running from Stage 1. This is the single largest cost saver in the addendum.

## AD-09.9 Per-scene presenter control

`manifest_builder.py:167-172` already reads `talking_head_position` and `talking_head_scale` from scene data and builds a positioned PiP layer; `stage7_prototype_draft.py:273-285` maps five positions onto `PiPPosition`. **The consuming code exists; the columns feeding it do not.** `storyboard_scenes` has no presenter fields, so the defaults are always taken.

Add to `storyboard_scenes`:

| Column | Type | Notes |
|---|---|---|
| `presenter_enabled` | BOOLEAN, default true | **Video only.** Audio is always generated — this is the "toggle head video off, keep the audio track" requirement |
| `presenter_position` | ENUM | Existing five values, plus free placement per below |
| `presenter_x`, `presenter_y` | NUMERIC, nullable | Normalised 0–1; when set, overrides the named position |
| `presenter_scale` | NUMERIC | Existing semantic (0.25 default) |
| `presenter_orientation` | ENUM | `landscape` / `portrait` — affects the source render aspect, not just the overlay box |

**Orientation is not a crop.** A portrait presenter must be *rendered* portrait by the engine; scaling a landscape render into a portrait box gives pillarboxing or a bad crop. The orientation therefore belongs in the Stage-6 generation request and in the actor's engine binding, not only in the composition layer.

These are exposed in the scene edit modal (`SceneEditModal.tsx` currently edits four fields: narration, visual description, media type, duration) with preset-supplied defaults.

## AD-09.10 Logo overlay and typography

**Logo** is a composition layer, sibling to the existing `talking_head` and `lower_third` layer types in `manifest_builder`. Project-level policy (`always` / `never` / `per_scene`) with a per-scene `logo_enabled` override, plus placement and scale from the preset. No new render path — the compositor already places overlay layers.

**Typography** is a token set on the preset — `heading`, `body`, `lower_third`, `title_card` — each binding a font family, weight, size scale and colour. Font files live in the asset library as `kind = font`. Templates and lower-thirds reference tokens, never literal font names, so rebranding is one preset edit.

**Constraint:** the font must be present on the compositor node at render time. Font provisioning to node-06 needs an explicit mechanism; a font that exists in the library but not on the node fails silently to a fallback face, which is exactly the class of silent defect to avoid. Recommend a render-time assertion.

## AD-09.11 Authoring UX

**New Project** (`projects/new/page.tsx` today: name, description, runtime, presenter clip, transcripts, optional storyboard, languages):

- Preset selector at the top, applying defaults to every subsequent field, with each field remaining editable.
- Each media input becomes **select-from-library or upload**; uploads write through to the library (§AD-09.4.2).
- Actor selector replacing the raw presenter-clip upload, with upload-and-create-actor as the fallback path.
- Intro/outro template selectors.

**Project media panel** (`projects/[id]/assets/page.tsx`): add template instance editing, logo policy, presenter defaults, and typography — the per-project surface for everything the preset seeded.

**Storyboard** (`StoryboardEditor` / `SceneEditModal` / `SceneTimeline`): structural scenes rendered distinctly from content scenes; per-scene presenter controls; per-scene logo toggle; working single-scene regeneration (§AD-09.3).

**Course library**: a new top-level view listing finished courses with fork-to-new-project, showing the minimum re-entry stage for the proposed changes.

## AD-09.12 Data model summary

| Change | Type |
|---|---|
| `library_assets` | New table |
| `actors` | New table |
| `presets` | New table (versioned) |
| `intro_outro_templates` + `template_instances` | New tables |
| `courses` (finished-course records) | New table |
| `assets.library_asset_id` | New nullable FK |
| `storyboard_scenes.scene_kind` | New ENUM column |
| `storyboard_scenes.template_instance_id` | New nullable FK |
| `storyboard_scenes` presenter columns (5) | New columns |
| `storyboard_scenes.logo_enabled` | New nullable column |
| `projects.preset_id`, `preset_version` | New columns |
| Presenter/coupling mode on the AD-01 binding | Extension |

Alembic head is `0027` in the reviewed snapshot; this is a substantial migration set and should be sequenced, not landed as one revision.

## AD-09.13 Sequencing

1. **§AD-09.3 stub family** — precondition, independent of everything else here.
2. **Asset library + actors** — everything else references them.
3. **Presenter columns + logo layer** — smallest change, consuming code already exists, immediate operator value.
4. **Presets** — needs the library to point at.
5. **Structural scenes + intro/outro templates** — the data-model change with the widest downstream reach; do it while the storyboard is still being actively debugged rather than after.
6. **Voice/video coupling** — gated on the MBCP contract question (§AD-09.6.3) and on MagiHuman certification.
7. **Course library** — depends on 2–6 being reference-based.

**Interaction with AD-05.** If the Temporal migration lands first, the Stage-5/6 coupling change is a workflow-definition edit rather than a change to `STAGE_TRANSITIONS` / `STAGE_TASK_MAP`. That argues for taking items 1–5 now and holding item 6 until after M3 — items 1–5 are almost entirely API, schema and frontend, and are orthogonal to the orchestrator.

## AD-09.14 Open questions

1. **MagiHuman engine bindings** — the concrete parameter set for (a) working generation and (b) actor/voice consistency, which determines the `actors.engine_bindings` schema. Currently held as operator knowledge; needs recording.
2. **MBCP contract for joint audio+video** — new stage contract or declared variant of `talking_head`? Owned by the MBCP SSOT. Blocks §AD-09.6.
3. **Voice-identity metric** — is there a scorer for "same voice across runs", or is this human-eval only?
4. **Reproducibility policy** — are seeds and model-version pins captured in course records, and is exact re-derivation promised or explicitly not promised?
5. **Portrait presenter support** — which certified engines can render portrait natively at usable resolution.
6. **Font provisioning** to the compositor node — mechanism and render-time assertion.
7. **Library retention and quota** — library assets sit outside per-project quota; what governs their growth and tiering?
8. **Preset drift** — surface divergence between a project and its preset, or ignore it?

## AD-09.15 Draft acceptance criteria

- A preset applied at creation populates branding, actor, model selections and media defaults; the project renders with them without further operator input.
- The same actor produces a subjectively identical presenter and voice across two separately created projects.
- Every storyboard shows an intro and an outro scene; with no template applied, the rendered output is byte-comparable to the same project without structural scenes.
- A scene with `presenter_enabled = false` renders with full audio and no presenter overlay.
- Single-scene regeneration dispatches a task, and the assertion is on the broker message, not the HTTP status.
- A finished course forked with a new logo re-renders from Stage 4 without re-running generation.
- All operations available in the GUI; no CLI step.

---

*Prepared as an additive draft under §18 change control. §AD-09.3 is a blocking precondition and is recommended for immediate ledger entry independently of this addendum. The 450 W GPU power-limit change is recorded as an ops errata item, not part of this specification.*
