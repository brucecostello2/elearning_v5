# WP-04-FRAME-ALIGN - report

| | |
|---|---|
| **Package** | WP-04-FRAME-ALIGN (Track S #5, Tier A) |
| **HEAD SHA at session start** | `9af5a485dfbd732bd9f0ce2519523f3fb267936f` |
| **Date** | 2026-08-23 |
| **Session** | Overnight unattended batch, Track S, sequential (package 1 of 5) |
| **Ledger** | AD-03 s4.4; AD-03 s10 criterion 3 (head A/V drift < 1 frame) |

## Precondition - AD-03 s7 Q5

The brief blocks on Q5 (authoritative target fps per profile). **Operator supplied
Q5 = 30** in the batch instruction of 2026-08-23. Recorded here as the ruling this
package was executed under. Precondition SATISFIED; the package proceeded.

Q5 = 30 is corroborated by measurement, not only by the ruling - see Finding 2.

---

## Pass 1 - findings

### Evidence basis: VERIFIED LIVE (measured on node-01 this session)

All measurements below were taken with `ffprobe` 5.1.9 from the deployed worker image
`ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics`, run against real stored artifacts
pulled from the SeaweedFS volume server by fid. No figure in this section is inferred.

**The artifacts.** Project `3814f845-4668-496b-a88a-53fea95897c2`:

| Asset | fid | What it is |
|---|---|---|
| `talking_head_en.mp4` | `5,5b66d602e3` | The rendered head, 50,104,735 bytes, row created 2026-06-07 17:56:17Z |
| six scene WAVs | `5,5245bb96d3` `4,53dd9aa7dc` `2,5468a339a1` `3,55cd2117bd` `6,5699335c2a` `7,571fe17c6d` | the Stage 5 narration the head was lip-synced to (batch of 2026-06-06 18:15Z) |

Retrieval used (reproducible):

    curl -s -o th.mp4 "http://192.168.1.90:8080/5,5b66d602e3"

The filer at `:8888` reports an EMPTY root (`"EmptyFolder": true`) while the rows in
`assets.seaweedfs_path` name filer paths under `/ivgs/...`. Fetch by fid from the
volume server works; fetch by path from the filer 404s. Recorded as a side finding -
see "Additional findings" below.

**Finding 1 - the ~0.62s is real and reproduces exactly.**

    head video stream : r_frame_rate 30/1, avg_frame_rate 30/1, nb_frames 6465
                        => 6465 / 30 = 215.500000 s   (exact, CFR)
    narration audio   : 7.094667 + 5.558667 + 31.397333
                      + 75.349333 + 57.108667 + 38.372667
                        =  214.881334 s   (pcm_s24le, 48 kHz mono, per-file ffprobe)

    head A/V drift    =  215.500000 - 214.881334  =  0.618666 s
                      =  18.56 frames at 30 fps

AD-03 s10 criterion 3 records "~0.62s remains". **Measured: 0.618666 s.** The ledger
figure is correct to three significant figures. Criterion 3 is open on evidence, not
on assertion.

**Finding 2 - the head is genuinely 30 fps; Q5 = 30 is consistent with the machine.**

`r_frame_rate=30/1` AND `avg_frame_rate=30/1` on the head's video stream - constant
frame rate, exactly 30. This matters because the fps the engine actually emits was
NOT established anywhere in the repo before this session (see Finding 5). The Q5
ruling of 30 and the engine's real output agree.

### Evidence basis: INFERRED FROM READING CODE

**Finding 3 - the defective arithmetic, re-verified at HEAD `9af5a48`.**

`ivgs-workers/tasks/talking_head_task.py:495-497`:

    n_parts = math.ceil(scene_dur / MAX_SEGMENT_SECONDS)
    piece_dur = scene_dur / n_parts

then `:501-507` emits the slice with

    "-ss", f"{p * piece_dur:.3f}"        # every piece
    "-t",  f"{piece_dur:.3f}"            # every piece except the last

`MAX_SEGMENT_SECONDS = 30.0` at `:83`. `piece_dur` is an unconstrained float, so each
piece's audio duration is an arbitrary real number. The engine emits whole frames, so
each piece's video is `ceil(d_p * 30) / 30` and each piece contributes up to 1/30 s of
round-up. The brief's line references (`segment_planner.py`, "talking-head slicing")
were audited at `e613e844`; at `9af5a48` the site is `talking_head_task.py:476-518`.
Re-verified. No line drift beyond the file having grown - the arithmetic is unchanged.

**Finding 4 - the splitter accounts for only about a fifth of the measured drift.**

Modelling the current code against the six real scene durations above
(`MAX_SEGMENT_SECONDS = 30.0`) gives 11 render pieces:

| scene | audio s | n_parts | piece_dur s |
|---|---|---|---|
| 0 | 7.094667 | 1 | 7.094667 |
| 1 | 5.558667 | 1 | 5.558667 |
| 2 | 31.397333 | 2 | 15.698667 |
| 3 | 75.349333 | 3 | 25.116444 |
| 4 | 57.108667 | 2 | 28.554333 |
| 5 | 38.372667 | 2 | 19.186333 |

Summing `ceil(d_p * 30)` over those 11 pieces predicts **6450 frames = 215.000 s**,
i.e. a splitter-attributable drift of about **0.12 s (3.6 frames)**.

**The artifact measures 6465 frames = 215.500 s.** The residual ~0.5 s (15 frames) is
NOT explained by the splitter arithmetic.

This is the single most important finding in this package and it qualifies the brief.
The brief and AD-03 s4.4 both attribute the whole ~0.62s to `ceil(slice_s * 30)` per
piece. On measurement that attribution is wrong: the splitter is a real defect worth
about 0.12 s, and something else contributes about 0.50 s. Candidates, none tested
(the engine runs on node-04 and this session is confined to node-01 per common rule 5):

- LatentSync may not emit exactly `ceil(d * 30)` frames per render - it may pad to a
  mel-chunk or batch multiple, which would add a fixed per-piece quantum larger than
  one frame.
- The `:.3f` truncation on `-ss`/`-t` (`:502`, `:505`) perturbs each slice by up to
  0.5 ms, which is far too small to account for 0.5 s.
- The artifact predates Pillar 2 (row 2026-06-07 17:56Z; the splitter landed in
  `6a1324a` at 2026-06-07 15:56Z, so the artifact IS post-splitter, but Pillar 2 closed
  2026-06-08). The head render path was reordered by Pillar 2. A post-Pillar-2 head
  artifact does not exist in `assets` - the only `talking_head` row is this one.

**Consequence for the exit gate:** fixing the splitter arithmetic is necessary but,
on this evidence, NOT sufficient to reach "< 1 frame". Predicted post-fix drift on
this material is ~0.5 s (~15 frames), not < 0.033 s. This is stated up front rather
than discovered after the fact.

**Finding 5 - `output_fps` is accepted and discarded by the engine server.**

`ivgs-workers/servers/latentsync/server.py:145` declares `output_fps: int = Form(30)`.
It is never passed to `_runner` (`:164-165` passes width, height, mode, seed only) and
`_runner`'s final ffmpeg pass (`:105-109`) carries no `-r`. So IVGS cannot set the head
fps; it gets whatever LatentSync emits.

Meanwhile `ivgs-workers/clients/latentsync_client.py:380` returns `fps=params.output_fps`
- the client REPORTS the fps it asked for, not the fps it received. That value flows to
`talking_head_task.py:616` (`output.fps = seg_result.fps`) and into the asset metadata
at `:827`. **`output.fps` is a claim, not a measurement**, at every point it is stored.

It happens to be true today (Finding 2 measured 30/1). It is unverified in the system,
and a Q5 change to any other value would silently not take effect.

**Finding 6 - `segment_planner.py` has the same defect class, on a different path.**

`ivgs-workers/services/segment_planner.py:239-241`:

    num_segments = math.ceil(scene_duration / self._max_duration)
    segment_duration = scene_duration / num_segments

Float boundaries again, at `:244-246`. This is Stage 8's render-segment planner
(`stage8_final_render.py:395-399`), not the head, so it does NOT bear on criterion 3.
It is a plausible source of the 0.13 s draft-to-final delta recorded in AD-03 v0.4 s13
(draft 214.94 s, final 215.07 s). Not measured this session.

### Proposed fix

**In `ivgs-workers/tasks/talking_head_task.py` - the boundary arithmetic only.**

1. Add a module-level `TARGET_FPS_DEFAULT = 30` carrying the AD-03 Q5 ruling in a
   comment, and resolve the working fps from `task_input.output_fps` with that default.
2. Extract the boundary arithmetic into a pure, unit-testable helper
   `plan_frame_aligned_pieces(scene_duration_s, max_segment_seconds, fps)` returning
   `(start_s, duration_s_or_None, frames)` per piece.
3. Compute in integer frames:
   - `total_frames = round(scene_dur * fps)`
   - `n_parts = ceil(scene_dur / max_segment_seconds)` (unchanged - piece COUNT is not
     the defect)
   - `base_frames = total_frames // n_parts`
   - piece `p` starts at frame `p * base_frames`; every piece except the last is
     exactly `base_frames` long; the last piece runs to EOF and absorbs the remainder.
4. Emit `-ss`/`-t` at 6 decimal places instead of 3, so a frame boundary survives the
   format string (`754/30 = 25.133333`, not `25.133`).

Effect: every non-final piece has an audio duration that is an exact multiple of
`1/fps`, so `ceil(d * fps) == d * fps` and the per-piece round-up is exactly zero.
Rounding survives only on the last piece of each scene - once per scene instead of
once per piece.

**Not proposed, and why.** `segment_planner.py` (Finding 6) is left alone. The brief
anticipated it as a site, but measurement puts it on the Stage 8 path, not on
criterion 3, and touching Stage 8's segment boundaries would change the one
end-to-end-validated render path for a defect this package has not measured. Common
rule 6 (scope stop-rule), which this brief says applies "with force". Recorded as a
decision requested.

**Measurement script.** `scripts/measure_head_av_drift.sh` - ffprobe-based, takes a
head mp4 and the narration audio, prints frames, fps, both durations, and the drift in
seconds and frames. Reproduces Finding 1 exactly on the stored artifact.

### Decisions requested

| # | Decision | Why it is the operator's |
|---|---|---|
| D-1 | The ~0.5 s residual (Finding 4). Needs a node-04 investigation of what LatentSync actually emits per render. Out of this session's reach. | Requires running on node-04; common rule 5 |
| D-2 | Whether `segment_planner.py` (Finding 6) is scoped into this package or a new one | Scope stop-rule; touches the validated Stage 8 path |
| D-3 | Whether `output_fps` should be plumbed through to the engine (Finding 5), making Q5 an effective control rather than a documented intention | New behaviour in a stage server, outside this brief |
| D-4 | The exit gate cannot be met by an agent - see below | Requires a build+deploy to node-04 |

---

## Pass 2 - what changed

### Diff stat

    ivgs-workers/tasks/talking_head_task.py |  89 +++++++++++++++++++++-------  (89 insertions, 7 deletions)
    ivgs-workers/tests/test_wp04_frame_align.py       | new, 51 tests
    scripts/measure_head_av_drift.sh                  | new, executable
    dev/workpackages/reports/WP-04-FRAME-ALIGN-report_2026-08-23.md | this file

Touched files, complete list:

| File | Change |
|---|---|
| `ivgs-workers/tasks/talking_head_task.py` | `TARGET_FPS_DEFAULT = 30` at `:85-91`; `plan_frame_aligned_pieces()` at `:255-308`; `target_fps` resolution at `:546`; the slice loop at `:563-590`; comment correction at `:539-543` |
| `ivgs-workers/tests/test_wp04_frame_align.py` | new |
| `scripts/measure_head_av_drift.sh` | new |

No other file was modified. `segment_planner.py` was deliberately NOT touched (D-2).

### The change

`plan_frame_aligned_pieces(scene_duration_s, max_segment_seconds, fps)` replaces
`piece_dur = scene_dur / n_parts`. Piece `p` starts at frame `p * base_frames` where
`base_frames = round(scene_dur * fps) // n_parts`; every piece but the last is exactly
`base_frames` frames; the last runs to EOF and absorbs the remainder. `-ss`/`-t` now
carry six decimals instead of three.

The piece COUNT is unchanged - that bound exists because a whole long-scene render
OOM'd the engine (`:77-80`), and this package has no business moving it. A test asserts
it (`test_piece_count_is_unchanged`) and another asserts no piece exceeds
`MAX_SEGMENT_SECONDS`.

### Verification - OBSERVED

**1. The measurement script reproduces the pre-fix baseline on the real artifact.**

    $ docker run --rm -u 0 -v $SCRATCH:/w -v /opt/ivgs/scripts:/s:ro -w /w \
        --entrypoint bash ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics \
        /s/measure_head_av_drift.sh th.mp4 s0.wav s1.wav s2.wav s3.wav s4.wav s5.wav

    r_frame_rate       : 30/1
    avg_frame_rate     : 30/1
    frames             : 6465
    fps                : 30.000000000
    video length       : 215.500000000 s   (frames / fps)
    narration length   : 214.881334000 s   (sum of 6 part(s))
    A/V drift          : 0.618666000 s
    A/V drift (frames) : 18.5600
    VERDICT: FAIL - drift is 18.5600 frames, criterion 3 requires < 1
    exit=1

Reproducible, ffprobe-based, run on the actual render artifact. This is the baseline.

**2. Unit tests: 51 passed.**

    $ .venv/bin/python -m pytest ivgs-workers/tests/test_wp04_frame_align.py -q
    51 passed, 5 warnings in 0.35s

Including `test_new_arithmetic_beats_old_on_the_real_material`, which asserts the
PRE-FIX arithmetic drifts by more than one frame - the "fails against the pre-fix
code" demonstration the queue rules require. The pre-fix arithmetic is carried in the
test file as `_old_pieces()` so the comparison is executable, not narrated.

**3. No regression in the existing Stage 6 suite.**

    $ .venv/bin/python -m pytest ivgs-workers/tests/test_talking_head_task.py -q
    1 failed, 9 passed

The one failure, `TestStage6Input::test_requires_at_least_one_audio_ref`, is
PRE-EXISTING. Confirmed by `git stash`-ing this package's change and re-running the
single test: it fails identically at HEAD `9af5a48`. Not caused here, not fixed here
(outside the brief's file set - common rule 6).

`tests/` (the repo-root suite) cannot be collected at all in this environment:
`tests/conftest.py:34` imports `shared.database`, which builds an aiosqlite engine, and
`aiosqlite` is not installed in `.venv`. Pre-existing, unrelated, recorded not fixed.

### Verification - NOT OBSERVED

**The exit gate was not met, and could not be met by this session.** Stated plainly:

The gate requires a measured post-fix drift on a real render artifact. Producing one
requires Stage 6 to run the changed code, Stage 6 runs on node-04, and node-04 runs a
built worker image. That is a build, a push and a deploy - all three barred (queue
common rule 1; batch instruction "no push"). The change is committed and held.

**What the operator needs to do to close the gate:**

1. Build and deploy the worker image carrying this change to node-04.
2. Run a short job with at least one scene over `MAX_SEGMENT_SECONDS` (30 s) - a scene
   under 30 s is never split and exercises nothing.
3. Pull the resulting `talking_head` asset and its scene WAVs and run
   `scripts/measure_head_av_drift.sh`. The task also now logs `piece_frames` and
   `target_fps` on the `scene_split` event, and `av_drift_seconds` on
   `talking_head_quality_summary` (`:797`, pre-existing) - either is a cross-check.

### The honest prediction, and why the gate will probably still fail

Modelling the engine as "emits `ceil(d * fps)` frames per piece" over the six real
scene durations:

| | pieces | video s | drift s | drift frames |
|---|---|---|---|---|
| pre-fix arithmetic | 11 | 215.000000 | 0.118666 | 3.560 |
| post-fix arithmetic | 11 | 214.966667 | 0.085333 | **2.560** |

Per scene, post-fix: 0.160, 0.240, 0.080, 0.520, 0.740, 0.820 frames. Only scene 3
(the one split three ways) improved - by exactly one frame. The other five scenes are
single- or double-piece and their drift is entirely the LAST piece's remainder, which
this fix cannot touch.

**Two reasons the gate will likely still read FAIL after deploy:**

- **The model says 2.56 frames, not < 1.** The residual is one round-up per SCENE, and
  it exists because the Stage 5 scene audio durations are not themselves whole numbers
  of frames (7.094667 s is 212.84 frames). Removing it means frame-aligning the
  timeline's scene durations - the Stage 4/5 timeline model, not this splitter.
  Squarely outside this brief's file set.
- **The model does not explain the artifact.** It predicts 6450 frames; the artifact
  has 6465. The measured drift is 0.618666 s over 11 pieces - **0.0562 s per piece,
  about 1.69 frames**, not the < 1 frame a simple `ceil` would give. Something in the
  engine pads by more than a frame per render and this session could not measure what
  (node-04, common rule 5).

If that per-render quantum is proportional to the ceil behaviour, this fix removes it
on 5 of 11 pieces. If it is a fixed pad per render call, this fix removes none of it
and only piece COUNT would matter - which is bounded by the OOM constraint and is not
this package's to move. **Which of those two it is has not been tested.** That is D-1
and it is the thing that actually decides criterion 3.

### Swallowed-failure register

No new instance found in this package's file set. `ffmpeg_seg.probe()` failure at
`:552-556` sets `scene_dur = 0.0` on any exception, which the very next line reads as
"do not split" - a sentinel a caller acts on. It is arguably an instance, but it
pre-dates this package, is not in the brief's scope, and its consequence is a
conservative single-piece render rather than a silent advance. Recorded here, NOT
appended to the register, because I could not demonstrate it swallowing a real failure.

### Open items

- D-1 - the ~0.5 s residual. Needs node-04. **This decides the exit gate.**
- D-2 - `segment_planner.py:239-241`, same defect class on the Stage 8 path.
- D-3 - `output_fps` is discarded by `servers/latentsync/server.py`; `output.fps` is a
  claim at every point it is stored (`latentsync_client.py:380`).
- D-4 - build/deploy to node-04 and re-run the measurement, to close the gate.
- Side finding, no package owns it: the SeaweedFS **filer reports an empty root** while
  `assets.seaweedfs_path` rows name filer paths. Fetch by `fid` from the volume server
  at `:8080` works; fetch by path from the filer at `:8888` returns 404. Every stored
  asset is reachable only by fid today. Not investigated - outside this brief.

---

## Exit-gate verdict

**NOT MET.** Deferred to the operator, not failed on the merits.

| Gate clause | Status |
|---|---|
| Measurement method shown, ffprobe-based, reproducible | **MET** - `scripts/measure_head_av_drift.sh`, run live |
| Run on the actual render artifact, not asserted from arithmetic | **MET for the baseline** - 0.618666 s / 18.56 frames on the stored head |
| Measured drift < 1 frame, down from ~0.62 s | **NOT MET** - requires a post-fix render on node-04 |

The arithmetic defect the brief names is real, is fixed, and the fix is proven by 51
tests including an executable comparison against the pre-fix code. The brief's
attribution of the whole 0.62 s to that defect is **not supported by measurement** -
the arithmetic accounts for about 0.12 s of it. Criterion 3 does not close on this
package alone, and this report says so rather than claiming a gate it did not observe.

Commit-and-HOLD. Nothing pushed, nothing deployed.

---

## Operator rulings, 2026-08-23 — applied

| # | Ruling | Applied as |
|---|---|---|
| **D-1** | **APPROVED as a deploy-time investigation.** The ~0.5 s residual gets measured on node-04 during deploy verification. | Ledger **P1.4o** (new), carrying the measurement, the two competing hypotheses, and the instruction to use a job with at least one scene over 30 s — a shorter scene is never split and exercises nothing. |
| **D-2** | **Record `segment_planner` as a ledger item; do not touch.** | Ledger **P2.37** (new), marked RECORD ONLY. `services/segment_planner.py` is unmodified — confirmed by `git diff`. |
| **D-3** | **Record `output_fps` plumbing as a ledger item; do not build.** | Ledger **P2.38** (new), marked RECORD ONLY. `servers/latentsync/server.py` and `clients/latentsync_client.py` are unmodified. |
| **D-4** | Acknowledged — the exit gate needs a build and deploy to node-04. | Exit-gate verdict above stands at **NOT MET**, deferred to the operator, not failed on the merits. |

**Q5 is now recorded in the ledger, not only in a batch instruction.** P1.4o states
AD-03 §7 Q5 = 30 as an operator ruling of 2026-08-23, with the measurement that
corroborates it (`r_frame_rate 30/1` **and** `avg_frame_rate 30/1` on the stored head).

**Corroboration found after the fact, worth recording.** Ledger **P1.4e** already
carried `0.618667 / 214.881333` from the LipsyncValidator's own logged arithmetic. This
package measured `0.618666 / 214.881334` independently, from `ffprobe` on the stored
artifact and the six Stage-5 WAVs, without having read that line first. Two routes, same
numbers. The drift figure is not in doubt; only its **cause** is, which is D-1.

**Nothing was implemented under D-2 or D-3.** The only files this package touched remain
`tasks/talking_head_task.py`, `tests/test_wp04_frame_align.py`,
`scripts/measure_head_av_drift.sh` and this report.
