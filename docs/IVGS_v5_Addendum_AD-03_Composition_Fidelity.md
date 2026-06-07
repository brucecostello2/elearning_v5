# IVGS v5 - Addendum AD-03: Composition Fidelity and Talking-Head Synchronization

- **Version:** v0.3 (2026-06-07 - Pillar 1 implemented; reconciled with functional spec)
- **Date:** 2026-06-07
- **Status:** Pillar 1 CORE implemented and verified (S11). Reconciled against `ivgs_v5_functional_spec.md` (S12): composition tier = node-06/05, Pillar 3 = the spec's L2/L3 media fallback (Remotion/ffmpeg), captions = Remotion. Pillars 2-3 + frame-align still to build. Open questions in S7.
- **Owner:** Bruce Costello (architect/operator)
- **Related:** `IVGS_v5_Master_Sequence_Plan_to_Production.md` (M1, M3), `IVGS_v5_Addendum_AD-01_Model_Management.md`, `IVGS_v5_Addendum_AD-02_Node_Specialization.md`, `OUTSTANDING_WORK.md`
- **Code touched:** `ivgs-workers/clients/ffmpeg_client.py` (`compose_scene`), `ivgs-workers/tasks/stage7_prototype_draft.py`, `ivgs-workers/tasks/stage8_final_render.py`, `ivgs-workers/tasks/talking_head_task.py`, Stage 4 manifest builder (TBD)

---

## 1. Purpose and scope

M1 quality QA of the Stage-6B talking head uncovered that the rendered video is not merely cosmetically off - the composition has two structural defects, and the talking-head feature is not actually synchronized beyond the first scene. This addendum captures (a) the root cause, (b) the target architecture that fixes it correctly rather than patching symptoms, (c) the interim stopgap already in flight, and (d) the optimum implementation sequencing.

In scope: per-scene timeline duration model, talking-head synchronization, scene-length-aware visual fill, and segment-split frame alignment.

Out of scope: GPU heartbeat / reservation (`total_nodes:0`), fleet tag consistency, and other M2 robustness items. Those are a separate concern; AD-03 only notes where its work sequences relative to them.

---

## 2. Background - the defect cluster (verified)

> **Figures in S2-S3 and S5 are partly superseded by the implementation - see S11.** In particular the timeline is ~214.88s of real speech vs a 115s manifest estimate (a ~2x UNDERSHOOT), not the ~227s / ~12s-overshoot stated below; and the S5(a) "permanently correct" claim about the `-t` clamp was wrong (its operand had to change from `scene.duration` to the probed audio length).

Observed on test project `3814f845-4668-496b-a88a-53fea95897c2`, scenes of duration `10 / 15 / 31.4 / 75.35 / 57.11 / 38.37 = 227.23s`.

- **Base video shortfall.** ffprobe of both the head draft (`8e0c8531`) and the head-LESS draft (`0a83f6f2`) is identical: video stream `203.87s` (6116 frames) but audio `227.26s`. The video ends ~23.4s before the audio. Because the head-less draft shows the same shortfall, **this is base composition, not the head.** It is almost certainly the cause of `corruption_check_passed: False (5/6)` (a video-vs-audio duration mismatch) on every draft, including prior "green" ones.
- **Mechanism.** In `compose_scene`, **image** backgrounds are extended (`loop ... trim=duration={scene.duration}`), but **video/animation** backgrounds are only scaled - never extended to `scene.duration`. Separately, the scene output has **no `-t` and no `-shortest` when audio is present** (the `-t {scene.duration}` only exists in the silent-audio branch). So a scene backed by a short clip ends at the clip length while the full timeline audio plays on.
- **Head desync.** The head is passed whole to every scene (`talking_head_path`) and overlaid with `overlay=...:shortest=1` from input with **no per-scene seek**. Every scene therefore overlays the head **from 0:00** - only scene 0 is synced; every later scene replays the opening narration in the corner. Per-scene head sync was never implemented.
- **Audio mismatch.** The head was driven by `214.88s` of raw concatenated speech, but the timeline plays `227.26s`. The scenes carry ~12s of non-speech time beyond the speech, and the head was rendered from a different (shorter) audio than the video plays.
- **A/V drift in the head.** The head render is `215.5s` video vs `214.88s` audio (~0.62s). Source: the segment splitter rounds each piece with `ceil(slice_s * 30)`, accumulating sub-second drift. The lipsync validator flagged `lipsync_duration_mismatch` but still approved at `0.9971`.

---

## 3. Root cause - the timeline-model mismatch

Three uncoordinated "lengths" exist per scene and no stage reconciles them:

1. **Clip length** (~6s): Stage-3 video models (CogVideoX / Wan2.1) are hard-capped at short clips. A 75s clip is not generable.
2. **Speech length** (variable): the per-scene TTS audio.
3. **Scene duration** (longer; ~12s aggregate padding of unconfirmed origin): the manifest's `scene.duration`.

Every stage band-aids the gaps between these: images get looped, the head gets rendered from raw speech, the corruption check fails silently-ish, and short clips fall short. The fix is to make the timeline deterministic and to drive the head from the exact audio the video plays - after which the symptom patches are unnecessary.

---

## 4. Target architecture

Four design elements: three pillars plus one cross-cutting fix.

### 4.1 Pillar 1 - Deterministic, speech-anchored timeline model

Establish a single authoritative per-scene timeline contract:

- Each scene `i` has an authoritative duration `D_i`. The project timeline length is `sum(D_i)`.
- `D_i = S_i + P_i`, where `S_i` is the scene's speech duration and `P_i` is an **explicit, consistent pad** (a named quantity - e.g. inter-scene breathing room), defaulting to a uniform value (possibly 0), **not** accidental drift.
- A single timeline audio track `A_timeline` is assembled deterministically from the per-scene speech placed at known offsets plus the `P_i` pads. `A_timeline` becomes the **single audio source of truth** consumed by both the head render (Pillar 2) and final composition.

Investigate and decide (see S7-Q1): the origin of the current ~12s `D_i > S_i` gap in Stage 4 / storyboard, then choose to either tighten `D_i` toward `S_i` (zero or uniform pad) or formalize the existing gap as deliberate pacing. Either way, the relationship becomes explicit.

This is the keystone. It makes total length predictable and removes accidental padding. Sync itself does not require tight durations (it requires shared audio - Pillar 2), but a clean timeline contract is the stable interface everything else builds on.

### 4.2 Pillar 2 - Single continuous talking-head overlay, driven by the final timeline audio

The actual fix for the head desync, and it is robust by construction.

- **Reorder:** assemble `A_timeline` -> render the head from `A_timeline` (the exact track the video plays) -> compose scene content per scene -> overlay the head **once** over the assembled timeline, aligned at 0:00.
- Because the head is driven by the same audio the video plays (including silences and pads), the head's mouth is closed during pauses and the lips track narration across the entire video. There is no per-scene seek and no accumulating seam math.
- `shortest` semantics become a non-issue: head length == timeline length by construction.
- **Remove the head logic from `compose_scene`.** Per-scene composition handles scene content only (background, lower-third, captions). The head is a single final overlay pass on the concatenated timeline.
- **Head presence** (whether the head appears in a given scene - e.g. omitted during a full-screen diagram) becomes an independent per-scene boolean, applied as an enable/mask on the single overlay. Presence is not sync; it layers on top cleanly.

This fixes the per-scene desync and simultaneously removes the 214-vs-227 audio mismatch (the head is now driven by the 227.26 track).

**Cost:** the head render now depends on finalized timeline audio, so it moves later in the pipeline and is re-rendered against the final track. The existing segment-based OOM strategy still applies to the (slightly longer) track.

### 4.3 Pillar 3 - Scene-length-aware visual fill (motion-treated stills)

Since clip generation is model-capped, scenes longer than the clip will always need filling - this is unavoidable.

- For scenes where `D_i` exceeds the available clip length, replace freeze/loop with a **motion-treated still**: a slow pan/zoom (Ken Burns) over a high-quality still keyframe, with parameters (pan direction, zoom rate, focal framing, face-safe crop) chosen for tasteful, intentional motion.
- Where a generated clip's motion is desirable and the gap is small, a single tasteful loop or boomerang may suffice. Policy: prefer still + Ken Burns for large gaps; clip + gentle treatment for small gaps.
- Fully decoupled from sync and audio. Pure visual quality, with its own iteration loop.

### 4.4 Cross-cutting - Frame-aligned segment splitting

The head's segment splitter currently uses `ceil(slice_s * 30)` per piece, accumulating ~0.62s of drift over the head. Fix: compute piece boundaries in integer frames at the target fps so piece durations sum exactly to the source with no per-piece rounding. Result: head A/V drift -> sub-frame.

---

## 5. Interim stopgap (Phase 0 - already in flight)

To get a correct-length E2E and clear the corruption check today, without waiting for the architecture above, `compose_scene` gets two changes:

- **(a) `-t {scene.duration}` on the output always** (moved out of the silent-audio branch). This clamps each scene to its manifest duration. **This is permanently correct** and stays regardless of later work.
- **(b) Hold-last-frame fill** (`tpad=stop_mode=clone`) for non-image backgrounds so short clips reach `scene.duration` before the clamp. **This is interim** - replaced by Pillar 3.

**Effect:** per-scene video == audio -> total video matches the 227.26 audio -> corruption check passes; Stage 8 becomes validatable on a correct-length input.

**Migration path:** the `-t` clamp is permanent. The hold-last-frame fill is removed when Pillar 3 lands. The head logic in `compose_scene` is removed when Pillar 2 lands.

**Known limitation:** the stopgap does NOT fix head sync. The head remains desynced (opening narration replayed per scene) until Pillar 2. This is intentional - it isolates head sync as the single remaining known defect.

---

## 6. Implementation sequencing (optimum)

Each phase is independently validatable (one variable at a time). Correctness precedes quality; permanent/cheap changes come first; the scope-monster (Ken Burns) comes last because it is separable polish.

**Phase 0 - Stopgap (now).**
Apply S5(a) + S5(b) to `compose_scene`; commit; build worker; redeploy node-01 composition (+ consistency); re-fire stage completion.
*Acceptance:* a draft where video length == audio length (227.26) and corruption check passes; confirm Stage 8 runs on a correct-length input and surfaces no further masked defects.

**Phase 1 - Deterministic timeline model (Pillar 1).**
Resolve S7-Q1 (Stage 4 gap origin); define the per-scene contract `D_i = S_i + P_i`; build the single assembled `A_timeline`.
*Acceptance:* total length and per-scene boundaries are deterministic and match across the manifest, `A_timeline`, and the rendered draft.

**Phase 2 - Continuous head overlay from timeline audio (Pillar 2).**
Reorder pipeline (finalize audio -> head render from `A_timeline` -> per-scene compose without head -> single overlay); remove head logic from `compose_scene`; add the per-scene presence toggle.
*Acceptance (validated alone):* the head lips track narration across ALL scenes, not just scene 0; head A/V aligned; presence toggle honored.

**Phase 3 - Frame-aligned splitting (cross-cutting).**
Fold integer-frame boundaries into the head render's segment splitter.
*Acceptance:* head A/V drift < 1 frame (the 0.62s gone).

**Phase 4 - Scene-length-aware visual fill (Pillar 3).**
Replace the hold-last-frame stopgap with motion-treated stills / Ken Burns. Timeboxed quality loop. Then remove the S5(b) interim fill.
*Acceptance:* long scenes show intentional motion with no freeze or visible loop artifacts; `-t` clamp remains, interim fill removed.

**Ordering rationale:** Phase 0 unblocks the happy path with permanent + throwaway-minimal code and isolates head sync. Phases 1-2 fix correctness (length + sync) before Phase 4 touches quality. Phase 3 is small and slots wherever the head render is being worked. Phase 4 is last because it is the only piece that never needs the architecture and whose absence the cheap fill already covers.

---

## 7. Open questions to resolve (research, do not guess)

- **Q1 (blocks Phase 1's final shape, not Phase 0/2 sync):** What sets `scene.duration` in Stage 4, and why ~12s over speech in aggregate - deliberate pacing or accidental? Read the manifest builder + the storyboard duration source.
- **Q2:** The exact per-scene speech durations `S_i`, and where/how Stage 7 currently assembles the 227.26 timeline audio (concatenate + pad?). Needed to define `A_timeline` assembly cleanly.
- **Q3:** Head presence policy - is the head present for the entire video by default (continuous narrator), or are there intended head-off scenes? Determines whether the presence-mask layer ships in Pillar 2 v1 or is deferred.
- **Q4:** Ken Burns parameterization - derive pan/zoom from image saliency / face detection, or fixed templates? Bounds Pillar 3 scope.
- **Q5:** Authoritative target fps per render profile (30 assumed) for frame-aligned splitting.

---

## 8. Risks and trade-offs

- **R1 - lost pacing.** Pillar 1 may eliminate intended pauses. Mitigation: the explicit `P_i` pad preserves deliberate pacing as a named quantity.
- **R2 - pipeline latency.** Pillar 2's reorder puts the head render after audio finalization and re-renders it. Acceptable; the render is already segment-bounded.
- **R3 - open-ended quality loop.** Ken Burns can absorb unbounded effort. Mitigation: timebox; ship the "clip-fill acceptable" threshold first, polish later.
- **R4 - moving substrate.** The manifest/storyboard is still evolving (M2/M3). Mitigation: treat the Pillar 1 timeline contract as the stable interface to minimize churn.
- **R5 - bundling temptation.** Doing all pillars at once destroys failure attribution. Mitigation: enforce the one-variable phases in S6.

---

## 9. Mapping to Master Plan and the ledger

**Master Sequence Plan:**
- Phase 0 -> **M1** (close happy path at quality).
- Pillars 1-3 + frame-align -> **M3** (talking-head completeness + 30-min videos).
- **M2** robustness (GPU heartbeat/reservations, fleet consistency, NTP, API healthcheck, etc.) sits between M1 and M3 on the roadmap and is NOT part of AD-03. Whether M3/AD-03 work runs before or after M2 is a prioritization call recorded in the Master Plan, not here.

**OUTSTANDING_WORK.md:** AD-03 becomes the design source of truth for the composition-fidelity cluster; the ledger tracks task status and points here.
- BUG A (base video-fill / 23s shortfall / corruption 5/6) -> resolved by Phase 0 (`-t`) for length, Pillar 3 for fill quality.
- BUG B (head per-scene desync) -> Pillar 2.
- 0.62s head A/V drift -> frame-aligned splitting (Phase 3).
- Talking-head asset metadata loss, duplicate drafts, `_upload_asset` unused params - remain their own ledger items, referenced but not solved by AD-03.

---

## 10. Definition of done (AD-03 overall)

A full E2E (Stages 1->8) produces a draft AND a final in which:

1. Video stream length == audio length (corruption check passes).
2. The talking head's lips track the narration across **every** scene, not just scene 0.
3. Head A/V drift < 1 frame.
4. Long scenes show intentional motion (no freeze, no visible loop).
5. The interim hold-fill (S5b) is removed; the `-t` clamp (S5a) remains.

---

## 11. Implementation update - 2026-06-07 (Pillar 1 core landed; figure corrections)

The duration half of this addendum was implemented this session, ahead of the M3 schedule, because the real mismatch turned out to be far larger than S2/S3 assumed and was blocking M1. This section records what shipped, what the earlier sections got wrong, and what remains.

### 11.1 What landed (worker images v5.4.19 -> v5.4.22 on node-01)

- **v5.4.19** `compose_scene`: moved `-t` out of the silent-audio branch (applies always) and added `tpad=stop_mode=clone` hold-last-frame fill for non-image backgrounds. This was the Phase-0 stopgap as written in S5 - and it REGRESSED (see 11.2).
- **v5.4.20** orchestrator `_build_manifest_scenes`: best-effort read of the audio asset `duration_seconds` to set scene duration. Did NOT work (see 11.3); left in as a forward-compatible fallback.
- **v5.4.21** `compose_scene`: probe the downloaded audio FILE with ffprobe -> `effective_duration`; use it for the image trim, the video tpad `stop_duration`, and the output `-t`. This is the working duration fix.
- **v5.4.22** `stage7_prototype_draft`: anchor `cumulative_time` (the value handed to the corruption check as `expected_duration`) on the same probed audio length instead of the manifest sum. This is what cleared corruption 5/6 -> 6/6.

Both `celery-worker-default` (orchestrator) and `celery-worker-composition` (stage7/8) run `v5.4.22-h0`. node-02/03/04 worker tags are unchanged (fleet-tag gap, tracked in the ledger).

### 11.2 Correction: the mismatch is ~2x, not ~12s; the `-t` clamp target was wrong

S2/S3 state the timeline is ~227.26s with a ~12s pad over speech. That is wrong. Verified per-scene:

- Manifest `scene.duration_seconds`: 10 / 15 / 20 / 25 / 30 / 15 = **115s**. This is a Stage-4 storyboard ESTIMATE set before TTS exists and never reconciled to the spoken length.
- Real per-scene narration (audio file durations): 7.09 / 5.57 / 31.40 / 75.37 / 57.13 / 38.37 = **214.88s**.

So the manifest UNDERSHOOTS the real audio by ~100s (about 2x); it does not overshoot by 12s. The 227.26 figure in S2 was itself an artifact of an early mis-assembled audio. Consequence: S5(a)'s claim that `-t {scene.duration}` is permanently correct is FALSE - clamping to the 115s manifest CLIPPED ~100s of narration in v5.4.19. The permanently-correct clamp target is the real audio length (the probed `effective_duration`), which is what v5.4.21 does. The `-t` mechanism stays; its operand changed from `scene.duration` to the probed audio length.

### 11.3 Correction: the audio asset `duration_seconds` field is NULL

The v5.4.20 orchestrator approach failed because the assets list/detail API returns `duration_seconds = None` for every audio asset. The talking head obtained 214.88s by concatenating the audio FILES and probing the result, not by reading the field. Stage 5 (`stage5_voiceover.py`) is supposed to persist `actual_duration_seconds`, and/or the asset serializer drops it - either way the field cannot be trusted today. The robust fix probes the file directly (v5.4.21 compose, v5.4.22 stage7). This is a real upstream data gap - new ledger item (see 11.5).

### 11.4 Pillar-1 status and what remains

The CORE of Pillar 1 is implemented: scene duration is now anchored on the real speech length end to end (orchestrator best-effort + compose probe + stage7 probe), and the timeline and the talking-head full_audio now share the same ~214.88 / 214.97 clock - the shared interface Pillar 2 needs. What remains of Pillar 1 as designed: the explicit, named pad `P_i` is currently 0 (pure speech length); formalizing a deliberate inter-scene pad and deciding the Stage-4 estimate's fate (S7-Q1) is still open and now lower-stakes. The clean end state is still to make Stage 4 / TTS write a reconciled duration so downstream stages need not probe files - file-probing is the robust stopgap, not the destination.

### 11.5 Confirmation and new follow-ups

- **Confirmed** (draft asset `061f64eb-ed33-4354-9558-42bc262feddc`, stream-level ffprobe): video 214.9667s / 6449 frames at 30fps, audio 214.963s, format 214.967s, corruption 6/6. Video vs audio = 3.7 ms. M1 happy-path duration + corruption: DONE.
- **New ledger items** opened by this work: (i) audio asset `duration_seconds` persistence/serialization (Stage 5 / assets endpoint) - the null-field gap; (ii) the stage7 caption-offset loop still advances on the stale `scene.duration_seconds` (`cumulative_offset += scene.duration_seconds`) - deliberately not fixed because captions are off for the draft, needs the same audio anchoring when captions are enabled; (iii) duplicate audio assets (2 per scene from re-runs) and duplicate drafts accumulating; (iv) the checkpoint POST 405 still fires per scene (non-fatal, already tracked).
- **Unchanged by this work** (still open): head per-scene desync (Pillar 2 - the next item); long-scene frozen-frame fill (Pillar 3); the 0.62s head A/V drift (frame-align); Stage-8 final-render-with-head not yet exercised.

---

## 12. Reconciliation with the functional spec (composition tier, Remotion, fallback chain)

A review of `ivgs_v5_functional_spec.md` (prompted 2026-06-07) shows this addendum was written in node-01 / ffmpeg-only terms and must be reconciled with the spec's composition architecture. The duration work (Pillar 1) is unaffected - it is engine- and node-agnostic - but the composition engine, the node it runs on, and the long-scene fill strategy all differ from how S4-S6 framed them.

### 12.1 Composition runs on node-06/05, not node-01

Spec section 2.2 + the Stage-7/8 spec: the FFmpeg compositor is specified on **node-06 (primary), node-05 (overflow)** - not node-01. The `celery-worker-composition` we run on node-01 today is a bootstrap. Pillars 1-2 are portable FFmpeg and stay valid; their target home is the node-06/05 composition tier once those nodes are online. No rework of the logic is implied - it is a relocation.

### 12.2 Pillar 3 (Ken Burns) is the spec's L2/L3 media fallback, on Remotion/node-06

S4.3 introduced "scene-length-aware visual fill / Ken Burns" as if new. It is not - it is the existing media fallback chain (spec section 6.3, Table 6-6):

- **L1 - AI Video** (CogVideoX / Wan2.1) - marked **Phase 2+** (enabled after maturity proven).
- **L2 - Animated Still** - **Ken Burns pan/zoom on a generated image, via MotionGraphicsService = Remotion on node-06**. Read as the **Phase-1 default primary** visual.
- **L3 - Static Pan/Zoom** - simple FFmpeg zoom/pan on a static image (no Remotion; runs on the ffmpeg compositor).
- **L4 - Static Image** - no motion, last resort before the DLQ.

Two consequences:

- **The current approach is off the Phase-1 plan.** We generate ~6s CogVideoX clips (L1) and hold/stretch them to scene length (the frozen frame on scene 3 - 75s over a ~6s clip). The Phase-1 spec says long scenes should be **Ken Burns stills (L2)**, not stretched clips. The hold-last-frame stopgap (S5b) is therefore a stopgap for a strategy that should not be the Phase-1 primary at all.
- **Pillar 3 splits and moves earlier.** A Ken-Burns-lite **L3 (ffmpeg `zoompan`) can run on the current node-01 bootstrap now**, replacing the frozen-frame fill without waiting for node-06. The full **L2 (Remotion Ken Burns) lands with node-06**. So S6's "Phase 4, last/cosmetic" placement for Ken Burns is retracted: it is the Phase-1 primary visual, and part of it (L3) is available immediately.

### 12.3 Captions and lower-thirds are Remotion, not ffmpeg drawtext

Spec section 7.1.8 + Stage-7: lower-thirds and captions are rendered by **Remotion on node-06**, overlaid by the compositor. The stage7 caption-offset clock noted in S11.5 (still on the stale `scene.duration_seconds`) is an interim ffmpeg-path concern; the durable home for captions is Remotion, and the same audio-anchored offsets must be carried there. Until node-06 is online, captions stay off for the draft (as today).

### 12.4 Net effect on the AD-03 phasing

- **Pillar 1 (timeline)** - done, engine-agnostic, unchanged.
- **Pillar 2 (single head overlay)** - FFmpeg compositor; relocate to node-06 when online; logic unchanged.
- **Pillar 3** - reframed as the L2/L3 media fallback: ship **L3 ffmpeg `zoompan` on node-01 now** (kills the frozen frame, Phase-1-aligned); **L2 Remotion Ken Burns with node-06**.
- **Captions** - Remotion/node-06; the audio-anchored caption clock carries forward there.
- The S6 phase numbering stands as a logical order, but Pillar 3's "last/cosmetic" framing is retracted (12.2) and the node-06 dependency is now explicit. Cross-milestone ordering is governed by the Master Plan's M4 split / node-06 pull-forward note.

---

*End AD-03 v0.3.*
