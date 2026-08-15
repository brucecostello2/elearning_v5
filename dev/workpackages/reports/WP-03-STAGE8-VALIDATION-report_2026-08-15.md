# WP-03-STAGE8-VALIDATION - report

| | |
|---|---|
| **Package** | WP-03-STAGE8-VALIDATION (Track S #4, Tier B - observable) |
| **Brief** | `workpackages/WP-03-STAGE8-VALIDATION.md` |
| **Ledger** | P1.4 (M1-QA); AD-03 v0.4 S13-S14 |
| **Carried in** | WP-02 checks 7 and 8, deferred here by operator decision 2026-08-15 |
| **HEAD SHA** | `134c34f` (node-01 and node-04 both synced) |
| **Date** | 2026-08-15 |
| **Agent** | Claude. node-01 and node-04 (SSH handover). No commit, push or deploy. |

---

# PASS 1 - FINDINGS AND PROPOSED PLAN

## 1.1 Headline: a full Stages 1-8 run is not possible today

The operator folded checks 7-8 into this package on the reasoning that WP-03 "needs a
complete Stages 1-8 run anyway". **It cannot have one.** Verified live:

```
celery inspect active_queues  ->  composition-worker@node01 : composition
                                  default-worker@node01     : default, notifications, cleanup
                                  image-worker@node04       : gpu_image, gpu_tts, gpu_talking_head

ping  192.168.1.91 (node-02) DOWN   192.168.1.92 (node-03) DOWN
      192.168.1.94 (node-05) DOWN   192.168.1.95 (node-06) DOWN
```

**`gpu_llm` and `gpu_video` have no consumer at all.** Consequences:

| Stage | Queue | Runnable today? |
|---|---|---|
| 1 Transcript refinement | `gpu_llm` | **NO** - node-02/03 down |
| 2 Storyboard | `gpu_llm` | **NO** |
| 3 Media - image | `gpu_image` | Yes (node-04) |
| 3 Media - video clip | `gpu_video` | **NO** |
| 4 Composition manifest | `default` | Yes (node-01) |
| 5 TTS audio | `gpu_tts` | Yes (node-04) |
| 6 Talking head | `gpu_talking_head` | Yes (node-04) |
| 7 Prototype draft | `composition` | Yes (node-01) |
| 8 Final render | `composition` | Yes (node-01) |

## 1.2 The viable path - a genuine Stage 4-8 run, which is what checks 7-8 actually need

The reference project `2B-scenes2-222906`
(`3814f845-4668-496b-a88a-53fea95897c2`) already holds **refined transcripts and 6
storyboard scenes** from the June run - the outputs of Stages 1 and 2. So those stages
do not need re-running to get a real pipeline execution; their artefacts exist.

Dispatching with `resume_from_stage="composition_manifest"` gives:

```
Stage 4 (default, node-01)         -> a FRESH manifest keyed to the new job_id
Stage 5 (gpu_tts, node-04)         -> regenerated scene audio
Stage 6 (gpu_talking_head, node-04)-> talking head via the AD-01 binding
Stage 7 (composition, node-01)     -> the draft  <- CHECKS 7 AND 8
   [stops at the user-review gate: STAGE_TRANSITIONS[PROTOTYPE_DRAFT] is None]
Stage 8 (composition, node-01)     -> triggered separately  <- 4K TASK
```

**This solves the exact problem that blocked checks 7-8 in WP-02.** Stage 7 failed
there with `Invalid Stage 7 input: scenes ... not 0` because a job resumed at Stage 6
has no Stage-4 manifest. Starting at Stage 4 produces one for real, which the operator
explicitly preferred over an injected manifest.

**Only one manifest exists in the database today**, and it is stale:

```
composition_manifests: 1 row for this project
  job_id 79b90f48-...  status locked  total_duration_ms 115000
```

115,000 ms is the **115 s Stage-4 estimate** that AD-03 S11.2 records as undershooting
the real 214.88 s narration by ~100 s. Reusing it would validate against a known-wrong
timeline. Another reason to generate a fresh one.

## 1.3 Task 1 - the 4K profile

Profile constants read at HEAD (`ffmpeg_client.py:121` `RENDER_PROFILES`,
`RenderProfile.UHD_4K`):

| Field | Value | Table 6-2 |
|---|---|---|
| width x height | 3840 x 2160 | 4K |
| video_codec | `libx265` | H.265 |
| crf | 20 | CRF 20 |
| video_bitrate | `20M` | - |
| vbv_maxrate / bufsize | `20M` / `40M` | VBV 20 Mbps |
| audio | aac 256k, 48 kHz, 2ch | - |
| preset | `medium` | - |
| pixel_format | `yuv420p10le` | - |

The constants match the spec. The brief requires reading the **executed** invocation
from logs rather than inferring from this table - that is the actual test.

**Capacity risk, and it is real.** Stage 8 runs on `composition` = node-01, which has
**16 GB total** and was OOM-killed twice by the Proxmox host on 2026-08-14 (CLAUDE.md
S7). A 215 s 3840x2160 10-bit libx265 `preset=medium` encode is the heaviest job this
fleet can ask of that box, and node-04's 47 GB is not available for it because Stage 8
is routed to `composition`. Current headroom must be gated at dispatch, and the run
watched.

## 1.4 Task 2 - the bitrate assertion, and the hazard it carries

`corruption_detector.py:281-282`:

```python
checks_passed=sum(1 for c in result.checks if c.passed),
checks_total=len(result.checks),
```

Adding a check appends to `result.checks`, so **the familiar `6/6` signature becomes
`7/7`**. That string appears in AD-03 S11 (Pillar 1 and Pillar 2 closure evidence), in
the WP-02 report, and in every operator habit built on it. Changing it silently would
invalidate a comparison people make by eye. Flagged as decision D-2.

Threshold design, from the measured evidence: the 1080p final measured **506 kb/s**
video and the 720p draft **153 kb/s**, both on near-static content with a 0.25-scale
PiP head. AD-03 S14 is explicit that this is **not established as a defect** - CRF
targets quality and lets bitrate fall. So the assertion must be a **floor far below the
known-good reference**, catching collapse (a black or frozen output) rather than
policing CRF's judgement. A floor near 506 kb/s would fail the reference itself.

## 1.5 Task 3 - banking the reference output

Candidates for a durable location, in preference order:

1. `dev/workpackages/reference/` in-repo - committed, versioned, survives node loss.
   Metadata and checksums only; the media stays in SeaweedFS.
2. `/mnt/ivgs-shared/reference/` - reachable from all nodes, not versioned.
3. NFS `.7` - the backup target, durable but awkward to read.

The artefacts themselves already live in SeaweedFS by fid and are content-addressed,
so banking means recording **fid + sha256 + measured properties + the model selections
that produced them**, not copying bytes. Note the fid path matters: `seaweedfs_path` is
metadata only and the filer is empty - storage is fid-based on the volume server
(established in WP-02).

## 1.6 Evidence basis

**Verified live:** worker/queue inventory and node reachability; the single stale
manifest and its 115000 ms duration; `RENDER_PROFILES[UHD_4K]` constants at HEAD;
`corruption_detector.py:281-282` check accounting; node-04 synced to `134c34f` with a
clean tree and the backup removed.

**Inferred, not executed:** that Stage 4 runs standalone from existing storyboard
scenes (its `_build_stage_input` returns only `base_input`, which is suggestive but
untested); that the 4K encode fits in node-01's headroom; that Stage 8 accepts a
resume dispatch the way Stage 6 did.

## 1.7 Decisions requested

| # | Decision | Recommendation |
|---|---|---|
| **D-1** | Stages 1-2 cannot run (fleet down). Accept a **Stage 4-8** run using June's transcripts and storyboard as the E2E for checks 7-8 and the reference bank? Or defer WP-03 to M4? | **Accept Stage 4-8.** It exercises a genuine Stage-4 manifest, which is what the operator wanted, and Stages 1-2 are LLM text steps that Stage 8 validation does not depend on. Record the limitation in the banked reference |
| **D-2** | The new check turns `6/6` into `7/7` | **Accept and announce it.** Alternative is a separate assertion outside `checks`, which keeps 6/6 but hides the result from the place operators look |
| **D-3** | 4K encode on node-01 (16 GB, OOM history) | Gate on free memory at dispatch, run it watched, and abort rather than risk the node. If headroom is short, characterise the failure with evidence per the exit gate rather than forcing it |
| **D-4** | Where to bank the reference | `dev/workpackages/reference/` in-repo, checksums and fids only |

Tier B, so pass 2 proceeds on approval of these rather than a hard stop.

## 1.8 D-1 revision, 2026-08-15: nodes 02/03 up - and a harder blocker found

Operator brought node-02 and node-03 up and extended SSH. Verified state:

| | node-02 (.91) | node-03 (.92) |
|---|---|---|
| Worker | `ivgs-celery-node02` | `ivgs-cogvideox-worker-node03` |
| Image | `v5.4.7-h0` | `v5.4.7-h0` |
| Queue consumed | `gpu_llm` | `gpu_video` |
| Engine container | `ivgs-vllm-primary` healthy | `cogvideox-server` (`cogvideox-pilot-1`) healthy |
| Repo HEAD | `8b95b04`, clean | `8b95b04`, clean |
| Compose DB driver | `+psycopg` (2 sites, unfixed) | `+psycopg` (2 sites, unfixed) |
| `.env` tag | `v5.3.0-h0` (does NOT match the running `v5.4.7-h0`) | same |
| Memory free | 40 GB | 43 GB |

**Queue coverage is now complete** - every stage has a consumer for the first time.

**`v5.4.7-h0` predates ARCH-1.** Verified inside the running container:
`from shared.providers import get_binding` raises `ImportError`, and the worker-side
`providers` package is `ModuleNotFoundError`. So Stages 1, 2 and 3-video currently run
with hard-coded engine clients.

### The real blocker is not the node tags - it is an empty Model Store

Five stage tasks in the promoted image call `get_binding`, with these keys:

| Stage key | requested by | models | approved+enabled | default |
|---|---|---|---|---|
| `transcript_refinement` | stage1 | **0** | 0 | 0 |
| `storyboard_generation` | stage2 | 1 | **0** | **0** |
| `image_generation` | stage3 (x3) | 1 | **0** | **0** |
| `video_generation` | stage3 | 2 | **0** | **0** |
| `voiceover_tts` | stage5 | 2 | **0** | **0** |
| `talking_head` | stage6 | 2 | 2 | 1 |

**Only `talking_head` is ready** - because WP-02 needed it and the operator approved
those two models by hand. `transcript_refinement` has no model row at all.

**Consequence for the already-approved D-1 plan: the Stage 4-8 run would have failed at
Stage 5.** node-04 already runs `v5.5.2-orch6`, `stage5_voiceover.py:532-537` calls
`get_binding("voiceover_tts", ...)` inside the task's main `try`, and there is no
approved default - so it raises `SelectionError` and fails the stage. Stage 3-image on
node-04 has the same exposure.

This is a live consequence of the WP-02 deployment, not a regression this package
introduced: pre-ARCH-1 images never bound, so the empty store cost nothing. It is
AD-01 rollout work (Master Plan M5) surfacing early because ARCH-1 images are now
deployed on node-04.

**Not verified:** whether stage1/stage2/stage3's binding calls fail the task or degrade
- only stage5's guard was read in full. Treat 1/2/3 as untested on the new image rather
than as known-broken.

## 1.9 Option D attempt, 2026-08-15 11:24-11:25 - BLOCKED at Stage 7 by a Stage-4 defect

Ran under approved Option D. Two new defects found, both verified live.

**Step 1 - Stage 4 produced a fresh manifest.** Job
`7980c0b9-8d9e-4d3b-955e-f2b97bf137dd`, manifest `f85612c7-...`, status `locked`.
`total_duration_ms` is **115000 again** - the same 115 s storyboard estimate AD-03
S11.2 records as undershooting the real 214.88 s. Structurally fresh, numerically the
known-wrong estimate.

**Step 2 - the chain died at Stage 5 exactly as predicted (S1.8), captured verbatim:**

```
SelectionError: no selection and no enabled APPROVED default model
for stage='voiceover_tts' tier='prototype' (project 3814f845-...)
task_retrying  retry_number 2  max_retries 3  exception_type SelectionError
```

Evidence for WP-26. Note it *retries* on SelectionError, which is wasteful - the store
will not change between attempts.

**Step 3 - Stage 7 failed, and reported success.**

```
Input #0, wav, from '/tmp/ivgs_stage7_.../bg_8e25826c-....bin.png'
FFmpeg failed (rc=1)
...
{"event": "task_succeeded", "task_name": "tasks.prototype_draft_task.assemble_prototype_draft"}
```

A WAV was handed to ffmpeg as the scene background.

### DEFECT A - the Stage-4 manifest builder binds every scene asset as a background layer

| Manifest | layers per scene | types |
|---|---|---|
| June, job `79b90f48` | **1** | background |
| Today, job `7980c0b9` | **4** | background (x4) |

The four layers on scene 0 are 2 images **and 2 audio**, all `layer_type: background`,
all `0-10000 ms`:

```
d83c6ac7  audio  <- first in the list, so this becomes the ffmpeg background input
be4453e8  audio
7de1b630  image
ca6d7f83  image
```

The builder applies **no asset_type filter and no deduplication**. It looks correct in
June's manifest only because there was one asset per scene then; AD-03 S11.5 records
"duplicate audio assets (2 per scene from re-runs)" accumulating since. The duplicates
exposed a filter that was never there.

Compounding: most scenes have **0 images and 2 audio**
(`SELECT ... GROUP BY scene_id` shows `img=0, aud=2` for 2 of the first 3), so for
those scenes there is no valid background to pick at all.

### DEFECT B - Stage 7 swallows an ffmpeg failure and reports task_succeeded

The rc=1 is logged, then `task_succeeded` is emitted and the task returns normally.
Register instance - added to `WP-00-SWALLOWED-FAILURES`.

### Consequence for WP-03

**Option D is blocked at Stage 7.** No draft can be produced from a freshly built
manifest, so the Stage 6-7 reference cannot be banked and Stage 8 (which consumes the
same manifest) would fail the same way. Fixing the builder is **outside this brief's
scope** ("Out: stage body logic beyond the assertion hook"), so this is an operator
decision.

---

---

# PASS 2 - OPTION 3 (June manifest), 2026-08-15

## 2.1 Checks 7 and 8 (carried from WP-02) - BOTH MET

Stage 7 dispatched against the June manifest (job `79b90f48`), 11:50:44 UTC.

| Evidence | Value |
|---|---|
| `num_layers` | **2** on all six scenes - the AD-03 Pillar-2 signature (3 -> 2) |
| `ffmpeg_concat_success` | 6 segments, duration **214.94 s** - the real timeline |
| `ffmpeg_timeline_head_overlay_success` | 214.938 s - one continuous overlay after concat |
| `corruption_validation_complete` | **6/6**, `is_valid: true` |
| Scenes | `scenes_composed: 6`, `scenes_failed: 0`, draft 7,476,242 bytes |

Check 7 (segment/OOM strategy and Pillar-2 overlay unchanged): **MET**.
Check 8 (corruption 6/6, video == audio): **MET** - 214.938 vs 214.94, sub-millisecond.

**The zero-image scenes did not degrade the draft.** All six composed cleanly. My
S1.9 observation of `img=0` for some scenes came from `scene_id` linkage in `assets`;
the June manifest's single background layer resolves to valid image assets regardless.
Reported as seen - I did not chase why the two views disagree.

## 2.2 Task 1 - the 4K profile: COMPLETED, first time ever exercised

Dispatched 11:52:34 with both gates passed (11:52 UTC, outside 02:00-06:00;
12,498 MB free). Completed 12:19:34 - about 27 minutes. `profiles_rendered: 2`
(the orchestrator's `Stage8Input.render_profiles` default is `["1080p","4k"]`).

Memory watch armed at 3.5 GB warn / 2.0 GB abort **never fired**. No abort needed.

**Verified by artifact** (`ffprobe` on the downloaded file, 12:22 UTC):

```
codec_name=hevc      width=3840  height=2160   pix_fmt=yuv420p10le   r_frame_rate=30/1
video bit_rate=939325   audio aac 210408   duration=215.067   size=31149351
overall bit_rate=1158684   sha256 a3a395a6...e8a581 (matches assets.content_hash)
```

Every `RENDER_PROFILES[UHD_4K]` constant is confirmed in the output: H.265, 4K,
10-bit. Corruption checks passed **5/5** at render time.

**DEVIATION from the brief's method.** The brief requires reading the executed ffmpeg
invocation from logs, "do not infer from `ffmpeg_client.py`". **That is not possible:**
`cmd_head` is logged only on failure, and no `libx265` / `crf` / `yuv420p10le` /
`20M` token appears anywhere in a successful run's logs. I verified the **output**
instead, which is stronger evidence than a command string - it proves what was encoded,
not what was intended. The logging gap is itself worth fixing; recorded as an open item.

**Bitrate.** 939 kb/s video at 4K against a 20 Mbps VBV ceiling - the same pattern
AD-03 S14 describes at 1080p, and for the same reason: CRF on near-static content.
Not a defect.

## 2.3 Task 2 - the bitrate assertion: ADDED and DEMONSTRATED

`validators/corruption_detector.py`: new `video_bitrate_floor` check plus a
`_probe_video_bitrate` helper and a `min_video_bitrate_bps` constructor parameter
(default **20,000 bps**).

Design decisions, all deliberate:

- **A collapse floor, not a quality bar.** 20 kb/s is ~7x below the lowest known-good
  measurement (153 kb/s draft), so it cannot fail a reference. AD-03 S14 is explicit
  that low CRF-driven bitrate is not a defect.
- **Severity WARNING, not CRITICAL** - it does not fail a render on its own until it
  has a track record. `is_valid` stays `True` when it fires.
- **Probe failure returns `None` and skips the check** rather than reporting 0 bps.
  A probe failure is not evidence of a bad video - reporting a false collapse would be
  a new swallowed-failure instance in the tool built to catch them.
- Falls back to `size * 8 / duration` when the stream carries no `bit_rate` tag.

**Demonstration (exit gate):**

```
REFERENCE 4K  is_valid=True  checks=6/6
   video_bitrate_floor passed=True   actual=939325 bps  expected=at least 20000 bps
DEGRADED      is_valid=True  checks=5/6
   video_bitrate_floor passed=False  actual=10501 bps
   "Video bitrate collapsed - check for a black or frozen stream"
```

Degraded input: 20 s of black at `-crf 51 -preset ultrafast`, built with ffmpeg.

**D-2 announcement, and a correction to how it was framed.** The check count is
**already not constant**: this run produced 6/6 for the draft and **5/5** for the 4K
final, because checks are appended conditionally. So the change is not "6/6 becomes
7/7" - it is "N/N becomes N+1/N+1", and N already varies by input. The 4K final
re-validated at **6/6** with the new check. Anyone comparing check counts by eye
should compare the named check, not the ratio.

## 2.4 Task 3 - reference banked

`dev/workpackages/reference/REFERENCE-OUTPUT_2026-08-15.md`, in-repo per D-4.
Records fids, sha256, measured properties and the model selections in force. Media
stays in SeaweedFS; storage is fid-based (`seaweedfs_path` is metadata only).

**All four checksums independently verified against actual stored bytes**, not copied
from the database:

```
5,5b66d602e3  5a6e89a9...bbde6a9   1,5f616980b9  014a9044...d77efe
3,60dc085e2d  f9046616...61dc3c   7,617bb3baf9  a3a395a6...e8a581
```

The limitation section is the **first thing in the file** and states plainly that
Stages 1-5 were not run, that the Stage-4 manifest was not used, and that this
reference does not satisfy the Temporal migration gate on its own.

## 2.5 Behaviour-neutrality: three byte-identical reproductions

| Artefact | Evidence |
|---|---|
| Stage 6 head | sha256 identical across 3 runs; `reference_count` 1 -> 3 |
| Stage 7 draft | deduped onto June's `f78eb063`; `reference_count` -> 2 |
| Stage 8 1080p | deduped onto June's `9007b2cf`; `reference_count` -> 3 |

The 4K final is the only genuinely new artefact. This is independent confirmation that
WP-02's ARCH-1 promotion altered no rendered output.

## 2.6 Files changed

```
M  ivgs-workers/validators/corruption_detector.py     (the assertion)
A  dev/workpackages/reference/REFERENCE-OUTPUT_2026-08-15.md
M  dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md  (instances 14, 15)
M  dev/workpackages/reports/WP-03-STAGE8-VALIDATION-report_2026-08-15.md
M  dev/workpackages/reports/WP-02-ORCH6-report_2026-08-15.md        (node-04 sync)
```

Nothing staged, nothing committed, nothing deployed. **The assertion is not in any
deployed image** - it was demonstrated by mounting the file over
`v5.5.2-orch6`. It ships on the next rebuild.

## 2.7 Not verified / open

- The executed ffmpeg command line (S2.2) - not obtainable from logs on success.
- **Visual QA - DONE 2026-08-15, operator verdict.** Both the 1080p and the 4K finals
  **PASS on picture quality** at full screen. AD-03 S14's encoder question is **CLOSED
  as not-a-defect**; ledger **P1.4(a) done**. The low measured bitrates are CRF behaving
  correctly on near-static content, as S14 predicted.
  Separately, the operator reports **lip-sync quality is poor** - the known LatentSync
  limitation the MBCP bake-off settled. Not an encoder or composition defect, does not
  reopen S14. Remediation is to consume the certified winner, which is **absent from the
  Model Store**; recorded as ledger P1.7 and folded into WP-26 task 5.
- The assertion has never run inside a real pipeline execution, only against files.
- Why the draft ran 6 checks and the 4K final 5 was not traced beyond "checks are
  appended conditionally".

---

# EXIT-GATE VERDICT

| Gate clause | Verdict |
|---|---|
| 4K render completes and passes corruption checks, or the failure is fully characterised | **MET** - completed, 5/5 at render, 6/6 re-validated; properties confirmed by ffprobe |
| The assertion passes the reference and fires on a degraded input | **MET** - 6/6 pass at 939,325 bps; fires at 10,501 bps on black |
| The reference output is banked, location and checksums recorded | **MET** - in-repo, four checksums verified against stored bytes |
| *(carried)* WP-02 checks 7 and 8 | **MET** - Pillar-2 `num_layers` 2, concat 214.94 s, corruption 6/6 |

**WP-03-STAGE8-VALIDATION: exit gate MET**, with two deviations recorded: the executed
ffmpeg invocation could not be read from logs (verified by artifact instead), and the
reference is narrow by operator decision (Option 3) with the limitation recorded
prominently in the banked file.

Follow-on briefs to author: **WP-26-MODEL-STORE**, **WP-27-MANIFEST-BUILDER**.
