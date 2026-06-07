# IVGS v5 - Addendum AD-03: Composition Fidelity and Talking-Head Synchronization

- **Version:** v0.1 (draft)
- **Date:** 2026-06-07
- **Status:** Proposed (design accepted in principle; open questions in S7 to resolve per phase)
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

*End AD-03 v0.1.*
