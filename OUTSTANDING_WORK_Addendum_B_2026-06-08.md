# IVGS v5 — Outstanding Work: **Addendum B** (Sessions 2026-06-07 → 2026-06-08)

| | |
|---|---|
| **Addendum version** | B1 — 2026-06-08 |
| **Extends** | `OUTSTANDING_WORK.md` v3.1 + **Addendum A** (2026-06-05) |
| **Repository / branch** | `brucecostello2/elearning_v5` — **trunk is now `main`** (the `feat/phase-h0-make-main-honest` arc merged); `origin/main` HEAD `b17397b`. |
| **Sessions covered** | 2026-06-07 (Stage-6/7 head composite into the draft; M1 A/V duration + corruption closure) → 2026-06-08 (AD-03 Pillar-2 head sync; AD-03/AD-02/Master-Plan reconciliation vs the functional spec; AD-04 / MBCP authored). |
| **Live stack (as of this addendum)** | ivgs-workers **`v5.4.23-h0`** on node-01 (`celery-worker-default` / `-composition`); node-04 `v5.4.18-h0`; **node-02/03 still `v5.4.0-h0`**; ivgs-api `v5.2.6-h0`; LatentSync `latentsync-v5.2.7-h0` on node-04. (Fleet tag drift is widening — see §C.) |
| **Purpose** | Capture every ledger-worthy item from the 06-07/08 arc not already in v3.1: closures with evidence (§B), new outstanding work (§A), status updates to tracked items (§C), and document-maintenance notes (§D). |

## How to use this addendum

Complements v3.1; does not replace it. New-item IDs here are prefixed `B#`; **assign final `P#.#` numbers when merging into the live SoT** (the live node-01 ledger's current numbering is not visible from here). Per the v2.1/v3.1 update protocol, re-snapshot top counts and note the merge in `journal.txt`.

> **Reconciliation note.** Read the **live node-01 `OUTSTANDING_WORK.md` v3.1 first** — it may already carry some 06-07/08 entries (the duration/corruption closure in particular). Diff this addendum against the live file before merging to avoid duplicates.

---

# §A — New outstanding items (to ADD)

## B1 — **[P2] Null audio `duration_seconds` (Stage-5 persistence / serializer)**
The assets list/detail API returns audio assets with `duration_seconds = None`. This forced a workaround in Stage 7, which recomputes the true timeline from each scene's **real audio via ffprobe** rather than trusting the persisted field. **Fix:** persist and serialize the audio duration at Stage 5 (TTS), so downstream stages can rely on it. *(Root of the broader "duration disease" — the manifest's Stage-4 storyboard estimates [10/15/20/25/30/15 = 115] were never reconciled against real narration [≈214.94s]; the duration+corruption closure handled the symptom in composition, this is the upstream data fix.)*

## B2 — **[P2] stage7 caption clock not audio-anchored (latent until captions enabled)**
The caption clock is independent of the audio-anchored scene durations; with captions enabled, caption timing would drift from the real timeline. Currently latent — captions render via **Remotion on node-06 (M4a)**, not yet stood up. **Fix when captions land / on the node-06 compositor:** anchor the caption clock on real audio length, same principle as the Pillar-1 timeline fix.

## B3 — **[P2] Duplicate audio assets + accumulated draft assets (no supersede/prune)**
Re-fires accumulated multiple draft assets for the one test project (`0a83f6f2`, `8e0c8531`, `4a9ce479`, `061f64eb`, `f78eb063`), and per logs duplicate per-scene audio assets exist. No dedup or supersede-and-prune of obsolete assets. **Fix:** an asset supersede/cleanup policy (mark prior drafts superseded; prune or archive). Low urgency, but it inflates SeaweedFS and muddies "current best".

## B4 — **[P1] LatentSync articulation not production-viable → certified head-model replacement (AD-04 / MBCP, WS-H)**
On operator review, the talking-head lip-sync **articulation** (mouth shapes forming words) is a **deal-breaker** for the intended use. Timing/sync is fine (alignment 0.9971); articulation is the inherent ceiling of LatentSync at PiP scale. **The production head must be a certified replacement** — candidates **Wan2.2-S2V** (open weights, ComfyUI-native, fits the 96 GB Blackwell at 720p; same Wan family node-03 runs), **daVinci-MagiHuman** (Apache-2.0, e-learning-tuned, fast), **HuMo** (license TBD) — selected and certified via the new **MBCP (AD-04)**. **This is on M1's *quality* critical path** (the structural sync/placement is done; "final reviewed correct" is not achievable on the current head). Target architecture: **two-tier** — LatentSync draft, certified model for production. See AD-04 + Master Plan **WS-H**.

## B5 — **[P2] Stage-8 final render must bind the head model via the provider factory (model-swap allowance)**
`final_render` must resolve its talking-head model through the §19.1 **provider factory / AD-01 binding**, not a hard-coded engine, so a newly certified production head (B4) is a **selection change, not a code change**. **Prerequisite:** the provider abstraction implemented as a selection-aware factory (gap **ARCH-1**, AD-01). See AD-04 §16. *(Build this in when Stage-8 is implemented; the composition/overlay path is already model-agnostic.)*

---

# §B — Closures (evidence) — *for the v3.1 Items-closed table*

## ✔ A/V duration mismatch + corruption check (AD-03 **Pillar 1**)
Scene durations are now anchored on **real audio length end-to-end** (orchestrator + `compose_scene` + `stage7`). **`v5.4.22-h0`** (stage7 commit `4c38240`, compose `10b2290`). Evidence: draft **`061f64eb`** at **214.97s** with video==audio (3.7 ms) and corruption **6/6**. Supersedes the "215.5 vs 227.26 / 5-of-6" framing (215.5 was the head's own length). AD-03 §11.

## ✔ Talking-head per-scene desync (AD-03 **Pillar 2**)
The head is now composited **once** as a **continuous timeline overlay** (single ffmpeg pass after concat, video from head + audio from timeline, PiP bottom-right @ 0.25), **not** re-overlaid per scene from 0:00. **`v5.4.23-h0`** (commit `f0b1f9a`). Evidence: `num_layers` **3 → 2**; `ffmpeg_timeline_head_overlay_success` fired; draft **`f78eb063`** at **214.94s** (video 214.933s / audio 214.938s, ≈5 ms), corruption **6/6**, file_size correctly refreshed to the overlaid bytes (7,476,242). Operator-confirmed visually: the presenter now tracks each scene instead of replaying the opening. AD-03 §4.2 / Pillar 2.

> *These may map onto existing v3.1 spine items (M1 / WS-A); reconcile IDs on merge.*

---

# §C — Status updates to tracked items

- **Documents reconciled this arc** (all committed): **AD-03 → v0.3** (Pillar 1 §11; **§12** functional-spec reconciliation — composition tier is node-06/05, captions = Remotion, Pillar-3 reframed as the spec's **L2/L3 fallback** rather than cosmetic-last); **AD-02 → Draft 2** (capacity-elasticity framing corrected vs spec); **Master Plan → v0.3** (M4 split into **M4a** node-06 / **M4b** node-05, M4a pulled forward; **WS-H** added; M1 head-model quality gate; Stage-8 model-swap allowance). Commits `16ac574`, `90ffb0f`, `e773594`. **AD-04 → v0.1 authored** (MBCP) — commit `b17397b`. **AD-01 → AD-04 pointer added** in AD-01.7 *(this session — pending WinSCP/commit)*.
- **Fleet image consistency** (extends Addendum A / M2): node-01 worker now `v5.4.23-h0`, node-04 `v5.4.18-h0`, **node-02/03 still `v5.4.0-h0`** — drift is widening across the head-composite arc. Align the fleet and adopt the tag-bump discipline in **M2**.
- **A6 — checkpoint POST `405`** (Addendum A): **still open, still non-fatal.** Fires on every scene during `prototype_draft` and again at stage7 complete (observed throughout this session). No behavioral impact; clean up with the M2 4xx cluster.
- **A1 — image-generation regression** (Addendum A, P0): **no longer reproducing** in the `v5.4.18+` worker line — the pipeline generated images and advanced cleanly through Stage 7 across this arc. *Verify the L2 ~10s swallow root cause is genuinely resolved (vs masked) before formally closing A1.*
- **New visual-fill direction** (from the spec reconciliation): the current "6 s clip stretched to a frozen 75 s frame" is **off the Phase-1 plan** — Table 6-6 makes the **Ken-Burns still (L2)** the Phase-1 default. Near-term quick win: an **ffmpeg `zoompan` (L3)** on the node-01 bootstrap to replace the frozen frame (no node-06 needed); full L2 Remotion lands with **M4a**. Tracked in AD-03 §12 / Master Plan §6.

---

# §D — Document-maintenance notes

- **Trunk moved to `main`.** The `feat/phase-h0-make-main-honest` arc merged; `origin/main` HEAD is `b17397b`. The v3.1 header "branch" line is stale — update on merge.
- **Commit chain this arc (newest first):** `b17397b` (AD-04 draft) ← `f0b1f9a` (Pillar 2, v5.4.23) ← `e773594` (Master Plan M4) ← `90ffb0f` (AD-02/AD-03 reconcile) ← `16ac574` (AD-03 §11) ← `4c38240` (stage7 v5.4.22) ← `10b2290` (compose v5.4.21).
- **Pending WinSCP + commit** (this housekeeping pass): Master Plan v0.3 cross-refs, AD-01 AD-04 pointer, and **this Addendum B** (to `docs/` alongside Addendum A, or repo ROOT to match `OUTSTANDING_WORK.md` — match the live Addendum-A location).
- **Untracked binary** at `/opt/ivgs` root: `presenter.mp4` (and the WinSCP draft copies `draft_pillar2_*.mp4`) — leave out of git.

---

*Addendum B. Prepared under the §18 change-control / ledger-update process. Assign final `P#.#` IDs and re-snapshot v3.1 counts on merge; record in `journal.txt`.*
