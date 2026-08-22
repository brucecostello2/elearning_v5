# Handoff — talking-head metric honesty, 2026-08-15

**Read this before touching Stage 6, the quality gates, or the talking-head model.**

| | |
|---|---|
| Session | IVGS-2, IVGS-5, TH8, P1.4d/e/f, documentation errata |
| Ledger | P1.4d (scope), P1.4e (the four metrics), P1.4f (store hygiene) |
| Deferred | IVGS-3, IVGS-4 — `server.py`, digest/provenance coupling |
| Withdrawn | IVGS-1 — its premise was refuted, see below |

---

## 1. THE MODEL IS NOT BEING SWAPPED

Operator, 2026-08-15: the talking-head model is **not** being swapped out. Substantial
IVGS development continues on the current model. Everything in this session is
**diagnostic and metric-honesty work, which stands regardless of which model runs.**
If LatentSync later proves unsuitable that is a separate decision at a later date.

**Do not scope, plan or prepare a model swap.** Earlier wording in P1.4d implied one;
it has been superseded in the ledger. This section is the authority.

## 2. What was found — four metrics, none measuring articulation

The defect that matters is **articulation** — mouth shapes forming words. It was judged
"a deal-breaker" by human review on 2026-06-08
(`docs/archive/OUTSTANDING_WORK_Addendum_B_2026-06-08.md:32`). **That human verdict is
the only real measurement of articulation that has ever been taken.** Four automated
metrics existed; none can detect it.

| # | Metric | Where | Why it cannot fail |
|---|---|---|---|
| 1 | `alignment_score = 0.90` | `servers/latentsync/server.py:39,120` | A constant (`DEFAULT_ALIGNMENT`, env-overridable), emitted with `"scored": False`. Gated at 0.85 — 0.90 always passes |
| 2 | `lip_sync_score = 0.9971` | `validators/lipsync_validator.py` | Measures **A/V duration agreement only**: `1 - (drift / audio_duration)`. `base_score` saturates at 1.0 via `min(1.0, (frame+energy)/2 + 0.2)` |
| 3 | `lse_c 6.58 / 6.68` | MBCP, on `.52` | **TH1**: the fixture's `audio_matched.wav` IS the presenter clip's own soundtrack. RMS difference -135.4 dB, 102 dB below baseline |
| 4 | Segment gate | `talking_head_task.py` | Compared metric 1 against 0.85. Structurally unfailable |

**The arithmetic on metric 2**, verified against a real run:
`0.618667 / 214.881333 = 0.00287911` (logged exactly), `1.0 - 0.00287911 = 0.9971`.
It read 0.9971 on 2026-06-08 **and** 2026-08-15 because the durations did not change —
it is unmoved by any articulation change whatsoever. The module docstring advertises
"Audio-visual correlation analysis" and "Phoneme-to-viseme timing verification";
**neither is implemented.**

**Also established:** the talking-head bake-off was never run. MBCP holds three
talking-head models but **all four certificates are LatentSync**, because MagiHuman and
HuMo have no adapters (MBCP **R-11**, open). LatentSync "won" a field of one. Four
IVGS documents claiming the bake-off is "complete and settled" now carry errata.

**TH8:** IVGS holds 26 attestations, 22 with certificate UUIDs, 0 orphans. MBCP's
`pending_exports` is empty and its serving DB has zero certifications — **the export
landed; MBCP lost its own record.** Routed to MBCP as an integrity defect.

## 3. What was changed

**`ivgs-api/config/quality_thresholds.yaml`**
- `lip_sync_score` → **`av_duration_agreement`**, `weight: 0.0`, `status: non_functional`.
  Renamed because the old name was a lie. **Retained, not deleted**, so the number stays
  visible and its history legible.
- **New `av_drift_seconds`** — the first genuinely working check at this stage. Promoted
  from the `duration_penalty` term buried inside metric 2. Approve ≤ 0.0334 s (1 frame
  at 30 fps, the AD-03 §10 criterion-3 target), flag ≤ 1.0 s, reject above.
  **`comparison: lower_is_better` — it inverts every other entry in the file.** Read the
  direction before editing.
  Measured 2026-08-15: **0.6187 s → FLAGGED.** Correct and expected; WP-04 closes it.
  **Do not relax these thresholds to make it pass.**

**`ivgs-workers/tasks/talking_head_task.py`**
- Segment gate replaced with an `alignment_gate_non_functional` log recording the engine
  value and `scored: False`.
- `Stage6Output` gains `alignment_scored: bool = False` and `av_drift_seconds: float`,
  plus a `talking_head_quality_summary` log.
- **IVGS-5**: face-detection failure is now non-retriable and aborts immediately with a
  user-facing message naming cause and remedy.
- Module docstring corrected — it still advertised a low-score fallback that could never
  fire.

**Four documents amended** (not rewritten) with dated errata: AD-01 §AD-01.15, AD-01
Draft 2, AD-04 §3.19, and the 2026-08-14 status doc.

## 4. What was deliberately NOT changed

- **No score was wired.** Anything derivable from ffprobe today would be a fifth metric
  of the same family — computed, plausible, and blind to articulation. Adding one would
  restore false assurance rather than remove it.
- **The segment gate was not re-thresholded.** There is nothing real to threshold.
- **`av_duration_agreement` was not deleted** — history stays legible.
- **No graceful degradation to a headless render** on face-detection failure. Silently
  producing video without the presenter someone uploaded is this codebase's
  characteristic failure mode.
- **`server.py` untouched** — see §6.
- **No model swap** — see §1.

## 5. The message-predicate compromise, and its follow-up

`_is_face_detection_failure` in `talking_head_task.py` matches the exception **message**,
not its type, because the engine raises a bare `RuntimeError("Face not detected")`.

Markers are deliberately narrow so transient errors still retry. Verified in-image:

```
"Face not detected"                 -> True   (aborts)
"face detection failed on frame 12" -> True   (aborts)
"CUDA out of memory"                -> False  (retries)
"read timeout" / "Connection refused" -> False (retries)
```

**FOLLOW-UP, tied to IVGS-3/4:** when `server.py` is eventually rebuilt, replace this
predicate with a typed error. Recorded in the ledger under P1.4e so the compromise is
not forgotten once the constraint lifts.

## 6. IVGS-3 and IVGS-4 remain deferred — and why it is a hard constraint

> **ERRATUM 2026-08-22 — the address below is wrong.** node-04 is **`192.168.1.93`**, as
> `dev/CLAUDE.md` §2 has always said. Established by measurement
> (WP-DEPLOY-R2-R5-NODE04 §6.1): `.93` answers ping and tcp/22, is in `known_hosts`, and
> returns `hostname: node-04` over ssh; `.52` is DOWN, port closed, absent from
> `known_hosts`. Read every `192.168.1.52` below as `192.168.1.93`, including the MBCP
> endpoint URL. The rest of the section — one shared instance, coordinated changes only —
> is unaffected and still binding.
>
> **Also superseded:** "The image cannot be re-pulled … It exists only in Docker storage."
> As of 2026-08-22 19:32 UTC it is banked at
> `/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_latentsync-v5.2.7-h0.tar.zst`
> (7.7G, sha256 `2da83e5a2bb60f4f…`, verified restorable), and that store **is** covered by
> the `.7` asset backup. Still treat the running container as irreplaceable — but the image
> is no longer a single copy.

There is **ONE** LatentSync instance: `192.168.1.52` (which is node-04), container
`ivgs-latentsync` from `ghcr.io/brucecostello2/ivgs-workers:latentsync-v5.2.7-h0`. MBCP
reaches it at `http://192.168.1.52:7860`. **The instance IVGS renders against IS the
instance MBCP certifies against.**

Therefore **any `server.py` change is coordinated, never unilateral** — it changes the
image digest for both systems and invalidates MBCP certificate provenance.

**The image cannot be re-pulled.** ghcr.io has been cleared. It exists only in Docker
storage on `.52` and in the MBCP local registry as
`192.168.1.51:5000/mbcp/latentsync:v5.2.7-h0`. **Treat the running container as
irreplaceable until a rebuild is deliberately sequenced.**

Deferred with it: IVGS-3 (constant `alignment_score`) and IVGS-4 (silently ignored
parameters).

## 7. IVGS-1 was withdrawn — a correction worth reading

The working theory was: Stage 6 requests `pip` and sends a scene image; the engine
discards both and emits `full_frame`; that explains the poor output. It was traced to
`stage6_talking_head.py:99`.

**That file does not exist.** It was deleted in commit `09e4212` (WP-02) as a dead
duplicate that was **in no `STAGE_TASK_MAP`** — it never ran. The live task requests
`full_frame` and sends no scene image, so there is no contract mismatch. The theory was
refuted, not merely mis-cited, and IVGS-1 was withdrawn entirely.

**Lesson for the next investigator: confirm a file is dispatched before diagnosing from
it.** `docs/stage-numbering-map.md` exists for exactly this.

## 8. Open, recorded, not acted on

- **P1.4f.1** — `latentsync-alt` is a deliberate test model, currently `approved`. Once
  WP-02 closes, retire it so it cannot become a production default.
- **P1.4f.2** — `vetting_reference` is free text. 22 rows hold certificate UUIDs, 4 hold
  prose. **Nothing distinguishes attested-by-certificate from attested-by-free-text** when
  enumerating approved models.
- **P1.4f.3** — 20 of 26 attestations belong to models still in `candidate`. Flag whether
  intended.
- **P1.4f.4** — a MagiHuman or HuMo win would need an IVGS provider builder that does not
  exist. Recorded for completeness only — **not a swap plan**, see §1.

## 9. Not deployed

> **CORRECTION 2026-08-22 (WP-TREE-TRIAGE).** The paragraph below claimed these changes
> were "now committed." **They were not.** They existed only in the working tree until the
> 2026-08-22 disposition — nothing in git history held them, so any tree-clearing
> operation would have lost them silently. The two states named here are also *different*,
> not "the same":
>
> | Change | Committed? | Deployed? |
> |---|---|---|
> | This session's Stage 6 + threshold changes | No — working tree only until 2026-08-22 | No |
> | WP-03 bitrate collapse assertion | **Yes**, at `3e2744b` | No |
>
> Verified on node-01: `ivgs-celery-default:/app/tasks/talking_head_task.py` is md5
> `acfd694a…`, byte-identical to the HEAD blob and carrying none of §3's changes;
> the same container's `corruption_detector.py` is md5 `3d08f5c6…`, which matches
> `3e2744b^`, not HEAD. Neither container bind-mounts source or config, so both changes
> need a rebuild.
>
> **Also corrected:** §2's table and `OUTSTANDING_WORK.md:235` both state that metric 2
> is "gated at 0.85 by `quality_thresholds.yaml`". **Nothing reads that file.**
> `get_quality_threshold()` (`shared/config_loader.py:61`) has zero call sites repo-wide,
> the worker image does not ship the file at all, and the loader's `_CONFIG_DIR`
> (`/ivgs/ivgs-api/config`) does not exist inside `ivgs-fastapi`. The live 0.85 is a Python
> default (`shared/providers/__init__.py:233`, `talking_head_task.py:122`). This does not
> weaken the finding — one of the two gates this session believed it closed was never
> wired in the first place.

Every change here is **working-tree only, and in no image.** The WP-03 bitrate assertion
is **committed at `3e2744b`** and is likewise undeployed. They ship together on the next
rebuild of `ivgs-workers` — which is **not** the LatentSync image and does not touch MBCP
provenance.
