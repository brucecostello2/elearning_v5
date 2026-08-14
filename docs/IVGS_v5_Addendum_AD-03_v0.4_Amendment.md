# IVGS v5 — Addendum AD-03, v0.4 (Amendment)

## Composition Fidelity — Timeline, Head Sync, and Visual Fill

| | |
|---|---|
| **Amends** | AD-03 v0.3 (`docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md`, 2026-06-07) |
| **Version** | **v0.4 — 2026-08-14** |
| **Change-control status** | Draft for review (per §18) |
| **Reason for amendment** | Pillars 1 and 2 are closed with evidence. Stage 8 has since produced a full-length 1080p final, which v0.3 could not assume. Pillar 3 and the cross-cutting frame-align item remain open and are re-sequenced against Master Plan v0.4. |
| **Verified against** | `elearning_v5` @ `e613e844`; Addendum B closures; render artefacts on node-01 |
| **Application** | §1–§9 and §12 are **unchanged** and remain authoritative. This amendment replaces §10 and §11 and adds §13–§15. |

---

## §10 Definition of done — **status** *(replaces v0.3 §10)*

A full E2E (Stages 1→8) produces a draft **and** a final in which:

| # | Criterion | Status |
|---|---|---|
| 1 | Video stream length == audio length (corruption check passes) | ✅ **Closed** — Pillar 1 |
| 2 | The head's lips track narration across **every** scene, not just scene 0 | ✅ **Closed** — Pillar 2 |
| 3 | Head A/V drift < 1 frame | ❌ **Open** — ~0.62s remains; §4.4 frame-aligned splitting |
| 4 | Long scenes show intentional motion (no freeze, no visible loop) | ❌ **Open** — Pillar 3; now lands with node-06 at M4 |
| 5 | The interim hold-fill (S5b) is removed; the `-t` clamp (S5a) remains | ❌ **Open** — removal is gated on Pillar 3 |

**Two of five closed.** The two hardest — the timeline model and head sync — are the closed ones. What remains is one arithmetic fix and one visual-quality feature.

## §11 Implementation update — **superseded** *(replaces v0.3 §11)*

v0.3 §11 recorded Pillar 1 as landing and carried figure corrections. Both pillars have since closed; the definitive record is:

**Pillar 1 — A/V duration and corruption.** Closed 2026-06-08, workers `v5.4.22-h0` (stage7 `4c38240`, compose `10b2290`). Scene durations anchored on real audio end-to-end across orchestrator, `compose_scene` and stage 7. Evidence: draft `061f64eb` at **214.97s**, video == audio within 3.7 ms, corruption **6/6**.

> The earlier "215.5 vs 227.26 / 5-of-6" framing is retired. The real timeline is **214.94s**; 215.5s was the head's own length. Both figures in v0.3 §11.2 are superseded.

**Pillar 2 — continuous head overlay.** Closed 2026-06-08, workers `v5.4.23-h0` (`f0b1f9a`). The head is composited **once** as a continuous timeline overlay in a single ffmpeg pass after concat — video from the head, audio from the timeline, PiP bottom-right at 0.25 scale — rather than re-overlaid per scene from 0:00. Evidence: `num_layers` 3 → 2; `ffmpeg_timeline_head_overlay_success`; draft `f78eb063` at **214.94s** (video 214.933s / audio 214.938s, ≈5 ms), corruption 6/6, file size correctly refreshed. **Operator-confirmed visually:** the presenter tracks each scene instead of replaying the opening.

## §13 — Stage 8 evidence *(new)*

v0.3 was written when Stage 8 was unvalidated. It has since produced a full-length 1080p final.

**Artefact:** `final_1080p_9007b2cf.mp4` on node-01, dated 2026-06-08.

| Property | Measured | Spec (Table 6-2) |
|---|---|---|
| Duration | 215.07s | — (draft: 214.94s, Δ 0.13s) |
| Resolution | 1920×1080 | 1920×1080 ✅ |
| Video codec | h264 (High) | H.264 libx264 ✅ |
| Framerate | 30 fps | 30 ✅ |
| Audio | AAC LC, 48 kHz stereo, 172 kb/s | AAC 192 kbps, 48 kHz stereo ✅ |
| Video bitrate | **506 kb/s** | CRF 18, VBV 8 Mbps — see §14 |

**What this establishes.** Segment planning, parallel segment render, concat, A/V alignment and head carry-through all work end-to-end at 1080p. The final was good enough to serve as evidence in the AD-04 head-model viability judgment. The 0.13s draft-to-final delta is consistent with criterion 3 remaining open.

**The 4K profile has never been exercised.** Table 6-2's H.265 / CRF 20 / VBV 20 Mbps path is unvalidated.

## §14 — Encoder bitrate: open question, not a defect *(new)*

The measured 506 kb/s video stream (draft: 153 kb/s at 720p) is far below what a naive reading of "CRF 18, VBV 8 Mbps" suggests. **It is not yet established as a defect.**

**The profile constants are correct.** `ffmpeg_client.py:144-148` defines the 1080p profile as `crf=18, vbv_maxrate="8M", vbv_bufsize="16M"`, applied at `:560-567` and `:834-842`.

**CRF targets quality, not bitrate.** It lets bitrate fall where content complexity allows. The current material is predominantly static stills with slow Ken Burns pan and a 0.25-scale PiP head — content that x264 encodes at genuinely low bitrates without visible loss. The VBV maxrate is a **ceiling**, not a floor.

**Resolution is by inspection, not by the number.** Operator visual QA at full screen. If clean, close the question. If soft or blocking is visible on motion, investigate whether `-crf` reaches the executed command.

**Regardless of outcome, add a bitrate/quality assertion to the corruption checks.** This should have been measured rather than eyeballed, and Pillar 3 will change the content-complexity profile substantially — pushing bitrate up and invalidating any baseline set now. Tracked as ledger **P1.4(c)**.

## §15 — Re-sequencing against Master Plan v0.4 *(new; supersedes v0.3 §9 mapping)*

| Item | v0.3 placement | v0.4 placement | Why |
|---|---|---|---|
| Pillar 1 | M1 | ✅ Closed | — |
| Pillar 2 | M1 | ✅ Closed | — |
| §4.4 frame-aligned splitting | M1 | **M1** — unchanged | Small arithmetic fix; closes criterion 3 |
| Pillar 3 — Ken Burns visual fill | "with M4a" | **M4** | Remotion lives on node-06; M4a/M4b merged and now sits post-migration |
| Interim hold-fill removal (S5b) | with Pillar 3 | **M4** | Gated on Pillar 3 |
| `-t` clamp (S5a) | permanent | **permanent** — unchanged | Correct regardless |
| Caption clock audio-anchoring | latent | **M4** (ledger P2.19) | Latent until captions render on node-06 |

**Material change to Pillar 3's context.** v0.3 §12.2 reframed Pillar 3 as the spec's L2/L3 media fallback on Remotion/node-06, and noted node-06 as Intel with no CUDA. **Per AD-02 Draft 3, node-06's card was replaced with an RTX 6000 Blackwell 96 GB.** node-06 is now a CUDA node — primary compositor, Remotion host, *and* a second video-generation node. This does not change Pillar 3's design, but it removes the Intel/oneAPI constraint that shaped v0.3's caution about node-06's rendering capability, and it makes the spec's L1 (AI video) tier viable on the same host.

**Open questions from v0.3 §7.** Q1 (what sets `scene.duration`) and Q2 (per-scene speech durations, timeline audio assembly) are **answered by Pillar 1's closure** — durations are anchored on real audio end-to-end. Q3 (head presence policy), Q4 (Ken Burns parameterisation) and Q5 (authoritative target fps per profile) remain **open**; Q5 blocks the frame-align fix and should be settled first, as it is a single value.

---

*AD-03 v0.4 amendment prepared 2026-08-14 against `e613e844`. Apply over v0.3; §1–§9 and §12 unchanged.*
