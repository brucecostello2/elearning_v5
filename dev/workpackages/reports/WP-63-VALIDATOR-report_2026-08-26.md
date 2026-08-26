# WP-63-VALIDATOR — report

**Date:** 2026-08-26 · **Node:** node-01 · **Deployed:** `v5.22.0-validator`
(api, workers, frontend) · **Migration:** 0036 · **Commits:** 9, HELD, not
pushed (11 held on `main` in total, with the operator's two).

---

## S0. Verdicts

| Task | Verdict | One line |
|---|---|---|
| **1 — the blank/solid check** | **PASS** | The check was measuring colour density and Stage 3's own letterbox padding put 43.75% of the frame into its denominator. Replaced with a scale-invariant structure measure. Three banked frames pass, two constructed blanks fail, the gap between the populations is 28x. |
| **2 — the message's history** | **PASS** | Re-scored under the fixed validator, append-only. **6 of 20 verdicts flip from `rejected` to `approved`**; the two video rejections and the one flag do not move. The correctness annotation is extended. |
| **3 — three stories about one failure** | **PASS** | The job row now names the stage the checkpoint recorded, `resume_from_stage` with it, and a validator rejection is no longer classed `transient`. |
| **4 — partial-failure recovery** | **PART PASS, one half STOPPED and reported** | Resume-from-checkpoint EXISTS on the Celery path and **computes the wrong stage for this exact shape** — measured, §S4. Evidence banked. The final press is the operator's: see **D-2**. |
| **5 — the dead link** | **PASS** | The link was a self-link on two of the three pages the panel renders on. Numbering unified on `scene_index`. |
| **6 — node-03's GPU exporter** | **PASS, and the premise was wrong** | The exporter is deployed, running and scraped. `nvidia-smi` INSIDE it exits **255**, 2260 scrapes in a row. Diagnose-then-fix block in §S6. |
| **7 — per-scene regeneration** | **PASS** | The API dispatch was real; the refusal was correct and the UI threw it away. Plus a bulk route that had answered 404 since WP-38. |
| **8 — the gate's regenerate decision** | **PASS** | Dispatches through the existing trigger layer, run-typed and guarded. Needed one prerequisite fix: a storyboard re-run used to DUPLICATE every scene. |
| **9 — visual descriptions** | **PASS (prompt authored, publisher HELD)** | v4 written, gated and tested. **Not published**, deliberately: publishing it now would pre-empt Task 4's sequencing. One command, §S9.4. **D-1 is a ruling request.** |
| **10 — CI red on a false positive** | **PASS** | Scanner fixed, not the test. Exits 0 locally with the exemption listed. |

**Two decisions needed: D-1 and D-2.** Both are in §S11.

**Test movement: +80, zero new failures.** 2053 → 2133 passed; failed, skipped
and errors unchanged in every tree. Three existing tests updated, none
weakened, each argued in `TEST-BASELINE`. Measured on the committed tree, the
second and last full run of this package:

| Tree | passed | failed | skipped | errors | was |
|---|---|---|---|---|---|
| `ivgs-api` | **1061** | 0 | 0 | 0 | 1026 |
| `ivgs-workers` | **868** | 18 | 48 | 15 | 838 |
| `ivgs-scheduler` | 35 | 20 | 0 | 0 | 35 / 20 |
| `ivgs-backup-worker` | 4 | 0 | 0 | 0 | 4 |
| `tests_system` | **165** | 12 | 15 | 30 | 150 |
| **Total** | **2133** | **50** | **63** | **45** | 2053 / 50 |

No assertion was weakened, no skip marker added, no coverage deleted.

---

## S1. Task 1 — the check was not measuring blankness

### 1.1 What it computed

`ivgs-workers/utils/image_validator.py` computed
`distinct colours / total pixels` and demanded more than `0.05`. That is a
measure of colour *density*, and its denominator is the pixel count.

### 1.2 The measurement

The three banked frames (`/mnt/ivgs-shared/wp63-rejects/`,
operator-verified by eye — people at whiteboards, a hand with a pencil over
paper), measured twice: as ComfyUI produced them, and after the resize Stage 3
performs before it validates.

| File | as generated (1024×1024) | after Stage 3's resize (1920×1080) | old verdict |
|---|---|---|---|
| `ivgs_flux_00087_.png` | 0.0876 | **0.0485** | REJECT (floor 0.05) |
| `ivgs_flux_00089_.png` | 0.0766 | **0.0427** | REJECT |
| `ivgs_flux_00094_.png` | 0.0809 | **0.0447** | REJECT |

**Nothing about the pictures changed between those two columns.** Stage 3 fits
each square frame inside 1920×1080 and pads it with black
(`utils/media_converter.py::ImageConverter.resize_to_target`, called at
`tasks/stage3_images.py` step 3). That adds **907,200 identical pixels — 43.75%
of the frame** — to the denominator while adding one colour to the numerator.

**The pipeline's own letterboxing is what rejected these frames**, and at this
resolution the metric sat so close to its floor that six of nine scenes fell
the other way by accident.

### 1.3 What it measures now, and why a whiteboard passes while a white square fails

A blank or solid-colour frame is one with **no spatial structure**. So:

1. **Strip the uniform border** (`_content_box`) — the letterbox bars, if any,
   stated as a property rather than a special case: rows and columns are
   examined independently, so it removes bars on any side. A frame with no
   non-uniform region at all is solid — verdict blank immediately, and that is
   also the verdict for a solid frame inside bars of a *second* solid colour.
2. **Tile what is left** into a 16×16 grid and count the tiles whose luminance
   standard deviation reaches 3.0.
3. **Blank iff fewer than 2%** of tiles are structured.

Both statistics are scale-invariant, so neither the resize nor the padding that
broke the old check can move this one.

**Both a whiteboard and a white square are overwhelmingly white**, so every
statistic of *how much white there is* — the old ratio, the dominant-colour
share, the mean — flags the whiteboard too. What separates them is that the
whiteboard has writing, a marker, a person and the board's own edges, and those
live in particular tiles. The white square has no such tile anywhere.

### 1.4 It is a gap, not a threshold tuned until the complaint stopped

Measured on the five pinned files, post-resize:

| File | `structured_tile_fraction` | verdict |
|---|---|---|
| `ivgs_flux_00087_` (whiteboard) | 0.6406 | pass |
| `ivgs_flux_00089_` (whiteboard) | 0.5664 | pass |
| `ivgs_flux_00094_` (hand, pencil, paper) | 0.7227 | pass |
| constructed pure white | **0.0000** | REJECT |
| constructed solid colour | **0.0000** | REJECT |

The floor is **28× below the lowest legitimate frame and above the highest
blank one, which is exactly zero**. No value of it makes those two groups
overlap, and `test_the_floor_is_a_gap_not_a_setting` asserts that separation
directly rather than asserting that the frames pass.

Four cases the fix could plausibly have got wrong, each pinned:

* a truly blank frame **inside letterbox bars** — a naive edge count would read
  the bar/content seam as content and pass a white square. It fails.
* a flat frame with imperceptible noise — over a million distinct colours, no
  picture. It fails.
* the same picture at two sizes gets the same verdict. The old metric did not:
  0.0876 and 0.0485, either side of its own floor.
* every statistic is recorded on the result — including `unique_color_ratio`,
  the OLD verdict's number — so a rejection can be argued with from the quality
  record rather than re-run.

### 1.5 Gated both ways

15 tests. Verified **red** by restoring the old verdict rule inside the new
function: 5 fail, including all three banked frames and the scale-invariance
test. Green with it. The three files are committed at
`ivgs-workers/tests/fixtures/wp63/` with the measurement in that directory's
README, and **every test runs the real Stage-3 resize first** — a test that fed
the banked bytes straight to `validate()` would have passed against the broken
code and proved nothing.

---

## S2. Task 2 — the same message's history

### 2.1 Before

`asset_quality_scores` for the reference project `c12fa967`, the 2026-08-26
08:10 rescore pass, 20 assets:

| decision | count | of which "Image appears blank or solid color" |
|---|---|---|
| approved | 11 | — |
| flagged | 1 | — |
| rejected | **8** | **6** |

### 2.2 After — run live inside `ivgs-celery-default` on `v5.22.0-validator`

```
project      : c12fa967-f989-4ed4-8e20-3ea62cb92e8f
assets       : 20
rescored_by  : WP-63-VALIDATOR
verdicts     : {"approved": 17, "flagged": 1, "rejected": 2}
persisted    : 20 of 20
```

| | before (08:10) | after (WP-63) | moved |
|---|---|---|---|
| approved | 11 | **17** | +6 |
| flagged | 1 | 1 | — |
| rejected | 8 | **2** | −6 |

**The six that moved are exactly the six that carried the blank/solid message.**
The two video rejections (`Unsupported video codec: mpeg4`) and the one flagged
video (resolution/duration) are unchanged, which is the control: nothing moved
that the fix did not touch.

| asset | scene | old ratio | old verdict | new verdict | CLIP |
|---|---|---|---|---|---|
| `2a912fb7…` | 2 | 0.0058 | rejected (blank) | **approved** | 0.2727 |
| `ef51a8c8…` | 4 | 0.0010 | rejected (blank) | **approved** | 0.3078 |
| `e58947e6…` | 6 | 0.0062 | rejected (blank) | **approved** | 0.3030 |
| `3d89b0ef…` | 9 | 0.0112 | rejected (blank) | **approved** | 0.3125 |
| `cec54989…` | 13 | 0.0067 | rejected (blank) | **approved** | 0.3074 |
| `a3c48700…` | 15 | 0.0080 | rejected (blank) | **approved** | 0.3459 |

### 2.3 Append-only, verified

```
      pass       |    day     | decision | count
-----------------+------------+----------+-------
 WP-44-QUALITY   | 2026-08-26 | approved |    11
 WP-44-QUALITY   | 2026-08-26 | flagged  |     1
 WP-44-QUALITY   | 2026-08-26 | rejected |     8
 WP-63-VALIDATOR | 2026-08-26 | approved |    17
 WP-63-VALIDATOR | 2026-08-26 | flagged  |     1
 WP-63-VALIDATOR | 2026-08-26 | rejected |     2
```

New rows beside the old. Nothing edited: 32 rows across the fleet still carry
`Image appears blank or solid color` in their `scoring_details` and still say
`rejected`, which is the record of what the validator said at the time.

The rescore script now takes `--rescored-by` and `--note`, because it had
hardcoded `WP-44-QUALITY` and three passes were distinguishable only by
timestamp — which works until two run on one day, as they now have.

### 2.4 What the frames actually are, and the honest limit

**They are not blank, and two of them are not good either.** Read by eye:

* `3d89b0ef…` is a wall-mounted screen carrying five rows of garbled
  arithmetic — `− 45 − 15+4+ − 15+2`, `− 25 − 15+ = − 15`. Rich, structured,
  and wrong.
* `ef51a8c8…` is a near-white sheet with a faint `x 6/4 =` in the middle.
  Sparse (`structured_tile_fraction` 0.0586, the lowest of the six) and still
  clearly not blank.

The blank check now gives the right answer to *its own question*. Whether those
frames are USABLE is a different question, and it is the one **RULE 1** of the
storyboard prompt exists to prevent ever being asked: both are text-in-the-
visual failures. That is Task 9's subject, and it is why RULE 1 wins on the
digits there (§S9.2).

### 2.5 The annotation is extended

`docs/reference-run-2026-08-23-correctness-annotation.md` gains §8: the
technical baseline's *quality record* was validator-distorted until 2026-08-26.
The run itself is untouched — no asset regenerated, no narration edited, no
variant touched, and the es-ES variant not read.

---

## S3. Task 3 — one failure, three stories

### 3.1 The incident, measured

Project `14f71729`, job `d4b41765`, 2026-08-26:

| surface | what it said |
|---|---|
| `render_jobs` row | `"Stage talking_head_render failed"`, `failure_category = transient` |
| checkpoint ledger | `image_generation` **failed** (`failed_count 3`, `successful_count 6`); `tts_audio` complete |
| stepper | Media |

**The checkpoints were right.** Stage 3 rejected 3 of 9 scenes; the media join
drained and **partial-advanced by design** (a failed scene must not strand the
pipeline); stages 4 and 5 ran; the run died at stage 6 with three scenes
carrying no image. `handle_stage_completion` writes
`f"Stage {completed_stage} failed"` (`pipeline_orchestrator_v2.py:409`) for
whichever stage *reported* the terminal failure — so **under partial-advance
the job row can only ever name the symptom.**

### 3.2 The fix, at WP-58's choke point

`update_job_status` now attributes a terminal failure BEFORE it classifies it,
so the class is derived from the corrected message rather than a downstream
symptom. Both live at the one site because most terminal-failure callers are
inside frozen stage bodies (AD-05 §8) — the same reason WP-58 gave.

The message the incident now produces:

> Stage image_generation failed (the stage's own checkpoint). 3 of 9 scenes
> produced no usable asset. The other 6 succeeded in the same pass, so the
> difference is the generated content, not the fleet. The terminal failure was
> reported at stage talking_head_render, which ran after it under
> partial-advance; the checkpoint ledger is authoritative for which stage
> failed.

The reported stage is **kept, not erased** — `talking_head_render` genuinely
did fail, *because* three scenes had no image, and an operator sent to stage 3
needs to know why the stage-6 logs look the way they do.

`resume_from_stage` gets the ledger's stage too. The live row says
`talking_head_render`, **three stages past the fault**; a resume from there
would have skipped the only work that needed redoing.

The two checkpoint GET routes now accept the service token. The worker wrote
those rows and reads them back from a Celery worker holding
`IVGS_SERVICE_TOKEN`, not a human JWT. `/resume` and DELETE stay human-facing —
those *act*.

### 3.3 A validator rejection is not transient

`"Image appears blank or solid color"` matched nothing in the classifier and
landed on the `transient` default — and `transient` means *retry it*. Nothing
about the fleet was wrong: a frame was produced, measured and refused, and a
retry re-measures it to the same verdict. §6.2's `external` is the class for
model/service OUTPUT quality. Pinned, with the British spelling covered.

**The one class inference, and its limit.** The attributed message is classed
`external` on a pattern keyed to **the evidence, not the failure**:
`succeeded\s+in\s+the\s+same\s+pass`. "N of M scenes produced no usable asset"
is not by itself external — if M of M failed, "the generator was unreachable"
fits it just as well. What makes it external is that the *others succeeded*, in
one pass on one node against one model, leaving only the content to differ.
A total media failure does not contain that clause and falls through to WP-57's
honest default. `test_a_total_media_failure_offers_no_class` pins that limit
rather than glossing it.

---

## S4. Task 4 — three scenes, not nine

### 4.1 THE EVIDENCE, BANKED (project 14f71729, read 2026-08-26 before anything touched it)

**The six original image asset ids, and the three scenes that have none:**

| `scene_index` | media_type | scene id | image asset id |
|---|---|---|---|
| **0** | image | `e4f8bee3-a1c0-4245-8eb4-803623dac744` | **— none —** |
| 1 | image | `84b969fc-0f6c-4837-b407-a1c60cab10d0` | `830b58dd-bf8d-48b4-a62f-68fcd5cb5b27` |
| **2** | **video_clip** | `bc4b52ef-f9c9-46e8-9ae9-e59a8a9c4cb3` | **— none —** |
| 3 | video_clip | `b793d058-9e6c-4ee1-8450-eed836f39160` | `53e0d98c-9e98-4d0a-ae61-84e8024aeec3` |
| 4 | image | `96d01d2a-c09f-4dda-84cc-9da0696e8f5e` | `5fdc2f4a-b067-46f9-a209-33c6a0a471ff` |
| 5 | image | `ecc54420-a35c-4e8c-b9c2-ddb4fad5e202` | `4c9b378f-3754-4c7d-9704-a006c514a820` |
| 6 | image | `2c4a2163-4343-48a7-8297-8a14170821bd` | `54b79fda-aed3-444a-93fd-ad059a330e61` |
| **7** | image | `c404ccbf-1a22-464d-9ada-28d800866501` | **— none —** |
| 8 | image | `73034930-fc9d-4afa-b1c0-94bfced4dddf` | `dc87cfc5-8fad-4c74-8164-da59beaa74ac` |

**The three missing scenes are `scene_index` 0, 2 and 7 — exactly the indexes
the incident names.** Plus 9 audio assets (one per scene, complete), 1
reference clip, 1 document. `superseded_by` is NULL on all of them.

Note scene 2 is now `video_clip`: that is the operator's own edit at
15:15:40Z, which is what Task 7's acceptance gesture is about.

### 4.2 Does resume-from-checkpoint exist on the Celery path? YES — and it computes the wrong stage for this shape

`POST /jobs/{id}/resume` → `CheckpointService.resume_from_checkpoint` →
`dispatch_pipeline` with `resume_from_stage`. It is real and it dispatches;
WP-45 proved it live on job `b3df6eb6`.

**Computed against this job's real ledger, without dispatching:**

```
ledger:
  idx=1 transcript_refinement    complete
  idx=2 storyboard_generation    complete
  idx=3 image_generation         failed
  idx=4 tts_audio                complete

last COMPLETE checkpoint (the query /jobs/{id}/resume runs): tts_audio idx 4
resume_from_stage it would compute: talking_head_render
```

**It would resume at stage 6.** The query is *"the last checkpoint with status
`complete`, by `stage_index` descending"* — and under partial-advance a run
leaves **complete checkpoints AHEAD of the failed one**, so "last complete"
points *past the fault*. It ignores the failed `image_generation` checkpoint
entirely, would render talking heads over three imageless scenes, produce the
same broken draft, and skip `composition_manifest` as well (which never
checkpoints at all — WP-07 F5).

WP-45 fixed this function's *vocabulary*; the **query** is still wrong for a
mid-chain partial failure. **Not fixed here**: changing resume semantics
fleet-wide deserves a ruling, and even a corrected resume is not the least-waste
path (see below). **Ledgered as P2.61.**

### 4.3 The least-waste operator path that does exist

`POST /projects/{id}/scenes/batch-regenerate` — the route this package built
(§S7.3). Three scenes, **one job row, one broker message, one armed media
join**. The join drains and dispatches `composition_manifest` →
`tts_audio` → `talking_head_render` → `prototype_draft` → **DRAFT GATE**.

* The six good image asset ids are untouched. Nothing supersedes them: only
  the three scenes that have no asset receive one.
* The audio **is** re-run, because Stage 5 is project-wide and the chain runs
  through it. That is the residual waste, it is ~30 seconds of TTS, and it is
  the gap the Celery path cannot express.

**The gap, for Temporal (M3.3):** the Celery orchestrator has no way to say
*"these three scenes, then the tail of the chain, skipping stage 5"*. A durable
workflow can, because it holds per-activity completion rather than a per-stage
checkpoint table queried by "last complete". **Ledgered as P2.62.**

### 4.4 What was verified live, and what was not

Verified live on `v5.22.0-validator`, against the real project:

* `POST /projects/14f71729/scenes/{sid}/regenerate` → **409 GATE_NOT_APPROVED**,
  message: *"Media generation is refused: the storyboard review gate is not
  currently approved for this project - the last decision was 'regenerate'.
  Approve the storyboard that is on screen now, then retry."*
* `POST /projects/14f71729/scenes/batch-regenerate` → **409**, the same
  refusal. **This route answered 404 before this package.**
* Nothing changed: still 1 job row, 0 pending, six images, 0 superseded.

**The final press is not mine — see D-2.** The project's most recent recorded
gate decision is `regenerate` (twice, 15:17:25 and 15:17:29). Under this
package's Task 8 that decision now *means* "re-run the storyboard", which is
Task 9's path, not Task 4's. Recording an `approved` decision on the operator's
behalf would overwrite their stated intent and forge the human half of a gate
whose entire purpose is that it is human — the exact defect WP-62 closed.

---

## S5. Task 5 — the dead link, and the numbering

### 5.1 "Open editor →" navigated nowhere, and it was right both times

`GateReviewPanel` renders on **three** pages:

| page | link it offers | where it goes |
|---|---|---|
| `/projects/[id]` (overview) | `/projects/[id]/storyboard` | works |
| `/projects/[id]/storyboard` | `/projects/[id]/storyboard` | **the page you are on** |
| `/projects/[id]/draft` | `/projects/[id]/draft` | **the page you are on** |

Next coalesces a navigation to the current URL into nothing. The `href` was
never wrong and both routes exist; what was wrong was offering the affordance
in the one place it cannot do anything. A dead control teaches an operator to
stop trusting live ones, so it is not rendered where it is dead.

**Sweep of the panel's other affordances**, all verified against their targets:

| affordance | target | status |
|---|---|---|
| Approve / Reject / Regenerate | `POST /api/v1/projects/{id}/gates/{gate}` | exists; all three now do what their tooltip says (§S8) |
| Note textarea | recorded on the decision and in `audit_log` | verified — `note` round-trips |
| Storyboard preview | `useStoryboard` → `GET /projects/{id}/scenes` | exists |
| Draft player | `useAssets` + `useAssetObjectUrl` | exists |
| "Open editor →" | `/projects/[id]/storyboard` | route exists; **link suppressed where it is a self-link** |
| "Open full preview →" | `/projects/[id]/draft` | route exists; same treatment |

The `regenerate` tooltip said *"Nothing is dispatched here; re-run the stage
that produced it"*, which was accurate and is no longer true. It now says what
it does and what it costs.

### 5.2 Scene numbering

The cards, the timeline and the edit modal rendered `scene_index + 1` — scenes
1 to 9. Everything else speaks `scene_index`, zero-based: the storyboard rows,
the checkpoint data, the worker logs, the translation flags, and this
package's own rejection ("scene indexes 0, 2 and 7").

**The collision is not hypothetical — it is in this work package's own brief.**
It says *"scene 5 teaches 92 + 230 = 322 and its visual is a hand holding a
pencil"*. In the database that is `scene_index = 4`; `scene_index = 5` is
*"Let's try another one: 32 times 21"*, a different scene entirely.

Both numbers are now shown and the zero-based one leads, through one helper
(`sceneBadge` / `sceneTitle`), so the badge, the timeline, the modal header and
the gate panel's preview cannot drift apart.

---

## S6. Task 6 — node-03's GPU exporter (WP61-L4)

### 6.1 The premise has changed, and the real fault is narrower

Measured on node-01's Prometheus, 2026-08-26:

```
up{job="nvidia-gpu-exporter"}    node-02 1   node-03 1   node-04 1
                                 node-05 1   node-06 1
```

**node-03's exporter is deployed, running and being scraped.** What it does not
produce is any GPU series:

| node | `nvidia_*` metric families | `nvidia_smi_command_exit_code` | `nvidia_smi_failed_scrapes_total` |
|---|---|---|---|
| node-02 | 12 | 0 | — |
| node-04 | 12 | 0 | — |
| node-05 | 12 | 0 | — |
| node-06 | 12 | 0 | — |
| **node-03** | **3** | **255** | **2260** |

The three it emits are `nvidia_gpu_exporter_build_info`,
`nvidia_smi_command_exit_code` and `nvidia_smi_failed_scrapes_total` — its own
health, and nothing about a GPU. `build_info` is identical on all five
(v1.2.1, revision `0a05a485`), so it is **not** an image or config drift: the
container is right and **`nvidia-smi` inside it exits 255, on every scrape,
2260 times running.**

Exit 255 from `nvidia-smi` in a container is the NVIDIA runtime not reaching
it: the container started without device access, or the toolkit/driver on the
host is not serving it. The block below **measures which**, then applies the
one fix that is safe either way.

**node-03 runs `cogvideox-worker`, not `celery-worker`** (WP-44 S6.3). The
telemetry overlay is its own compose project (`name: ivgs-telemetry`), so it
cannot reach an engine — but the block never names an engine service anyway.

### 6.2 Operator paste block — node-03 (192.168.1.92)

```bash
# node-03 (192.168.1.92) — diagnose then repair the GPU exporter.
# Self-gating. Touches ONLY the ivgs-telemetry compose project.
( set -u
  cd /opt/ivgs-infra || { echo "FAIL: /opt/ivgs-infra missing"; false; }

  echo "== 1. what is actually running =="
  docker ps --filter name=ivgs-gpu-exporter \
    --format 'name={{.Names}} image={{.Image}} status={{.Status}}' \
    | tr -cd '\11\12\15\40-\176'
  docker inspect ivgs-gpu-exporter \
    --format 'devices={{.HostConfig.DeviceRequests}}' 2>/dev/null \
    | tr -cd '\11\12\15\40-\176'

  echo
  echo "== 2. nvidia-smi ON THE HOST =="
  nvidia-smi --query-gpu=name,memory.total,driver_version \
             --format=csv,noheader 2>&1 | tr -cd '\11\12\15\40-\176'
  echo "host rc=$?"

  echo
  echo "== 3. nvidia-smi INSIDE the exporter, with the exact field list =="
  docker exec ivgs-gpu-exporter nvidia-smi \
    --query-gpu=uuid,name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,clocks.current.graphics \
    --format=csv,noheader 2>&1 | tr -cd '\11\12\15\40-\176' | head -5
  echo "in-container rc=$?"

  echo
  echo "== 4. does the runtime exist at all =="
  docker info --format '{{json .Runtimes}}' 2>/dev/null \
    | tr -cd '\11\12\15\40-\176'
  echo

  echo "== 5. recreate the exporter from the TRACKED overlay =="
  docker compose -f docker-compose.telemetry.yml up -d --force-recreate \
    --no-deps gpu-exporter 2>&1 | tr -cd '\11\12\15\40-\176'

  echo
  echo "== 6. local exit gate: exit code must be 0, and memory must appear =="
  sleep 15
  curl -s --max-time 10 http://127.0.0.1:9400/metrics \
    | grep -E '^nvidia_smi_(command_exit_code|memory_used_bytes|name)' \
    | head -5 | tr -cd '\11\12\15\40-\176'
)
```

**Reading the output.** If step 3 prints a GPU line and `rc=0` while step 6
still shows `nvidia_smi_command_exit_code 1.0`, the fault is the exporter's own
invocation and the recreate has fixed it. If step 3 fails the same way as the
metric says, the container has no device access — check that step 1 printed a
non-empty `devices=` and that step 4 lists an `nvidia` runtime; if either is
empty, the host's `nvidia-container-toolkit` is the fault and no compose change
will help. **Report back rather than improvising** — the fix in that case is a
host package, not this file.

### 6.3 Operator paste block — node-01, verify the series land in Prometheus

```bash
# node-01 (192.168.1.90) — run AFTER the node-03 block. Read-only.
( set -u
  echo "== exit code and failed scrapes, all GPU nodes =="
  curl -s --get http://127.0.0.1:9090/api/v1/query \
    --data-urlencode 'query=nvidia_smi_command_exit_code' \
    | tr -cd '\11\12\15\40-\176'
  echo; echo
  echo "== THE GATE: node-03 must now report memory, like every other node =="
  curl -s --get http://127.0.0.1:9090/api/v1/query \
    --data-urlencode 'query=count by (instance) (nvidia_smi_memory_used_bytes)' \
    | tr -cd '\11\12\15\40-\176'
  echo
  echo "PASS when node-03 appears in the second result with a count of 1,"
  echo "and its exit code in the first is 0."
)
```

**Baseline for the diff**, measured now: the second query returns node-02,
node-04, node-05 and node-06 and **not** node-03.

---

## S7. Task 7 — per-scene regeneration

### 7.1 What the buttons actually call today — MEASURED, and the brief is half right

**The chain, established by reading it and confirmed on the wire:**

```
SceneCard "Regen"  ─┐
Edit Scene modal   ─┴─> page.handleRegenerateScene ──> useStoryboard.regenerateScene
                        └─> POST /api/v1/projects/{id}/scenes/{sid}/regenerate
                            └─> storyboard.py::regenerate_scene
                                └─> StoryboardService.regenerate_scene
                                    └─> dispatch_scene_media_regeneration
                                        └─> broker: dispatch_media_generation
```

**The dispatch layer WP-45 built is real.** What the operator observed was this
(node-01 API log, project 14f71729, 2026-08-26):

```
15:15:40.605998Z  PATCH  .../scenes/bc4b52ef                    200 OK
15:15:59.961499Z  POST   .../scenes/bc4b52ef/regenerate    409 Conflict
```

**The 409 was correct.** The edit nineteen seconds earlier moved the storyboard
fingerprint, so the approval recorded at 13:41:29 (`sb-9-1998b350…`) no longer
named the storyboard on screen (`sb-9-dba2b224…`), and WP-62's gate refused the
media work — with a message naming the gate, the reason and the remedy.

**The operator saw none of it.** Every regeneration path in the storyboard UI
awaited its promise inside a `try/finally` with **no `catch`**, and SWR's
`rollbackOnError` reverted the optimistic "Regenerating…" state. A refusal
nobody is shown is indistinguishable from a button that is not wired up.

So: **the gate half of "decorative" is a UI defect, not a dispatch defect.**
The gate decision half (Task 8) genuinely dispatched nothing.

### 7.2 (a) The current settings, and the right branch

`dispatch_scene_media_regeneration` reads the scene row and sends
`media_type` with the payload; `dispatch_media_generation` groups by
`media_type` and routes image / video_clip / animation to their own branches.
An image scene switched to video regenerates as video, and the job row says
`video_generation` rather than defaulting to images — WP-60's six-dispatch
storm was diagnosed off `job_type`.

**One trap this exposed and closed.** A regeneration runs the scene **as
stored** — WP-45's ruling, and the right one, because an operator pressing
Regen has usually just edited the scene and replaying the *original* arguments
would regenerate exactly what they were trying to change. The corollary is that
*unsaved* edits are not part of it, and the modal offered Save and Regenerate
side by side saying nothing about the order. It now refuses with the reason
instead of quietly producing another image.

### 7.3 The bulk route that did not exist

`useStoryboard.regenerateScenes` has POSTed to
`POST /api/v1/projects/{id}/scenes/batch-regenerate` **since WP-38**. There was
no such route. Every press of "Regenerate Selected" answered **404** into the
same silence.

Serving it forced the right shape rather than a loop:

* three sequential single-scene calls **fail on the second**, at WP-62's
  in-flight guard, because the first leaves a `running` job;
* the media join is armed **once per job**, so N jobs against one project is
  the stranding shape WP-06 exists to prevent.

So the choke point takes N scenes and produces **one job row, one broker
message, one armed join**. The singular entry point delegates to it rather than
holding a second copy of the guards. WP-62's choke-point test follows it and
now asserts the delegation — one definition across four callers instead of
three, and it fails if either guard is *copied* into the wrapper.

A foreign scene id refuses the **whole** batch: an operator who selected six
scenes and got four has no way to find out which two were dropped.

### 7.4 (b) It composes with the guards, and with gate state

| situation | result | asserted on |
|---|---|---|
| scene edited since the approval | 409 `GATE_NOT_APPROVED`, **zero** broker messages | broker |
| a run already in flight | 409 `PIPELINE_ALREADY_RUNNING`, naming the run | broker |
| either refusal | **no job row left behind** | `render_jobs` count |
| second press while the first runs | exactly one dispatch, never two | broker |

**Which approval a regeneration invalidates, and why it is the draft one.**
`scene_media_version` fingerprints the project's CURRENT (non-superseded)
scene-linked assets, and the DRAFT gate's upstream is now
`storyboard_version + scene_media_version`. Regenerate a scene after the draft
was approved and that approval stops being current — the draft on screen was
assembled from a frame that is no longer the scene's frame. Same recompute
mechanism WP-62 built, no invalidation write.

It deliberately does **not** invalidate the STORYBOARD approval. That approval
*authorised* the regeneration; invalidating it by its own effect would refuse
the second regeneration and make the recovery in Task 4 impossible. **This is a
reading of the brief and it is D-1(b) in §S11.**

### 7.5 (c) Supersede with provenance — migration 0036

`assets` gains `superseded_by` / `superseded_at`, the pattern `library_assets`
has had since WP-56 under the rule *bytes are immutable; replacing a file is a
supersede*. The new asset becomes current; the old one is **retained**:

* a quality score row points at it, and that score is the evidence for **why**
  the operator regenerated;
* an already-locked composition manifest may reference it, and a manifest
  naming a row that no longer exists cannot be replayed;
* *"what did this look like before?"* is asked after a regeneration.

Retention (WP-58/59) removes it later, under a policy, with an audit trail —
not a media task deciding on the spot.

**Nothing is backfilled.** NULL means current, which is true of every existing
row; inventing an ordering for the fleet's historical duplicates would be this
package's guess presented as the pipeline's record — the defect WP-58 refused
to commit when it declined to backfill `failure_category`.

The write lives in `AssetService.upload_asset`, not in the regeneration
service, and that is not tidiness: the replacement arrives from a Celery worker
minutes after the API call that asked for it returned. Keying on the *arrival*
also makes it correct for a full pipeline re-run, not only for the button.

**`SceneThumbnail` had to follow.** It did `assets.find(...)` and would have
shown the frame the operator had just replaced.

### 7.6 (d) Frozen stage bodies

Untouched. Every change is in the API's trigger layer, the asset service, the
schemas, the migration or the frontend. `ivgs-workers/tasks/` is modified in
**no** commit of this package; the two worker files that changed are
`utils/image_validator.py` and `utils/error_handler.py`, neither of which is a
stage task body. `test_wp62_gates.py::TestFrozenStageBodiesAreUntouched` still
passes.

### 7.7 Acceptance

Live on `v5.22.0-validator` against project 14f71729: the route exists, the
guards bite, the refusal is exact, nothing was dispatched and nothing was left
behind. **The operator's gesture on scene 2 (already switched to `video_clip`
by them at 15:15:40Z) is one gate approval away** — see D-2. 22 broker-level
tests cover the behaviour end to end, including the image→video branch, the
three-scene batch, and the exactly-one-dispatch property.

---

## S8. Task 8 — the gate's regenerate decision

### 8.1 What it did

```
15:17:25.362931Z  gate_decision ... gate=storyboard decision=regenerate
                  version=sb-9-dba2b2244a87ac6f... by=admin        -> 200 OK
15:17:29.616325Z  the same line again, four seconds later          -> 200 OK
```

Two rows in `project_gate_decisions`, two audit entries, **zero broker
messages**. The second press exists because nothing happened after the first.
§6.4 says the gates *"additionally accept reject / regenerate signals"*; the
decision was recorded faithfully and released nothing.

### 8.2 Both halves ARE dispatchable standalone through the existing trigger layer

`dispatch_pipeline` has read `resume_from_stage` off the job context since it
was written, and `STAGE_TASK_MAP` resolves both stage names. This is the
identical mechanism `CheckpointService.resume_from_checkpoint` uses, proven
live on job `b3df6eb6` (WP-45 §4.6). Each stage reports to
`handle_stage_completion`, which finds **no next stage** after either
`storyboard_generation` or `prototype_draft` and pauses at the gate — so the
re-run ends where it should, at a human. **Neither half is a full-pipeline
run, and neither half needed to be STOPPED.**

| gate | decision | dispatched | job_type |
|---|---|---|---|
| storyboard | regenerate | `dispatch_pipeline`, `resume_from_stage=storyboard_generation` | `storyboard_generation` |
| draft | regenerate | `dispatch_pipeline`, `resume_from_stage=prototype_draft` | `prototype_draft` |

The job row is **run-typed** rather than borrowing `final_render` as a sentinel
the way the resume route does. A row that misnames its own work points a
fleet-wide guard at the wrong thing.

The decision row it already wrote is now **the audit of the dispatch**, which
is why the dispatch happens after `decide()` rather than instead of it. A
refused dispatch does **not** roll the decision back: a reviewer's decision must
not be lost to a scheduling condition — the rule `_gate_decision` already
applies to an approval whose release is refused. The measured double-press now
costs one run, and **both decisions are still recorded**.

### 8.3 Broker-level proof, both ways

| decision | broker |
|---|---|
| `regenerate` (storyboard) | exactly one `dispatch_pipeline`, `resume_from_stage=storyboard_generation` |
| `regenerate` (draft) | exactly one `dispatch_pipeline`, `resume_from_stage=prototype_draft` |
| `rejected` | **zero** |
| `approved` | the media release only — never a stage re-run |
| `regenerate` pressed twice | **one** dispatch; the second 409s and is still recorded |

### 8.4 The prerequisite nobody had hit: a storyboard re-run duplicated every scene

`create_scene` **inserted unconditionally**. Stage 2 POSTs one of these per
scene, and its own code says what it expected — *"Try POST to create; if scenes
already exist, try PATCH"*, with a branch on 409
(`stage2_storyboard.py:452`). No 409 was ever returned, so a second Stage-2 run
over a 9-scene project would leave **18 rows**: two scenes at every index, the
storyboard fingerprint meaningless, and the media dispatch fanning out over
both copies.

Nothing had noticed because **nothing had ever re-run Stage 2 on a project that
already had scenes** — which is exactly what Task 8 makes the gate do, so it
had to be true before this could ship.

The row is **updated in place, not deleted and recreated**: `assets.scene_id`,
the quality scores through them, and every language variant hang off that id,
and recreating would orphan the six good images this package's recovery depends
on. Updating also moves `updated_at`, which moves the fingerprint, which
re-opens the gate on the new artifact — the behaviour Task 8 wants, for free
from WP-62's mechanism.

**Stated limitation:** a re-run producing FEWER scenes leaves the surplus rows.
This method sees one scene at a time and cannot know the new total; trimming
needs a whole-storyboard write Stage 2 does not make. Logged as `scene_upsert`
so the count is visible in the run's log, and the gate re-opens either way.
**Ledgered as P2.63.**

---

## S9. Task 9 — visual descriptions must depict the lesson

### 9.1 The measurement, verbatim from `storyboard_scenes` (project 14f71729)

| `scene_index` | narration (abridged) | visual_description |
|---|---|---|
| 1 | "…set up the problem. We have 23 times 14…" | "A close-up of a hand holding a pencil, **poised over a blank sheet of paper**…" |
| 2 | "…multiply 4 times 3, which equals 12. Write down 2 and **carry the 1**…" | "A hand moving a pencil across a **blank sheet of paper**…leaving space for the composition overlay" |
| 3 | "…**put a zero in the ones place as a placeholder**…second answer is 230." | **THE IDENTICAL STRING, word for word** |
| 4 | "…add the two answers together. We have 92 and 230…final answer is 322." | "A hand holding a pencil, **looking at a blank sheet of paper** on a wooden desk…" |

Two further scenes shared *"A teacher standing in front of a clean, empty
whiteboard"*. **Six of nine visuals would have fitted any lesson on any
subject**, and the generated images were correspondingly content-free.

*(Note the numbering: the brief's "scene 5" is `scene_index 4`. See §S5.2.)*

### 9.2 THE COLLISION, and how v4 resolves it — this is D-1

The brief's example is that scene 4's visual *"should show 92 + 230 = 322 being
worked"*. **Taken literally, that asks an image model to draw digits — and
RULE 1 of this very prompt exists because that was measured twice on this
pipeline:**

* *"a whiteboard with a multiplication problem written on it, such as 23 x 14"*
  → a whiteboard reading **"2? x 23.14"**
* calculations *"appearing on screen"* → **"12 + 44 = 67 + 5"**

And §S2.4 of this report is a third instance, found today: two of the six
frames the old blank check rejected are text-in-the-visual failures — a screen
of garbled arithmetic and a sheet carrying a faint `x 6/4 =`.

**So v4 binds the visual to the STEP and to the STATE OF THE WORKING SURFACE,
in words, and leaves the digits to the composition overlay**, which renders
them in a real font:

> "Over-the-shoulder view of a hand resting a pencil tip at the foot of a
> two-row column addition on lined paper; **both partial-product rows are
> already written above a ruled horizontal line and the answer row beneath it
> is still empty**; warm desk lamp from the left, upper right third of the
> sheet kept clear for the overlay"

That is specific, it differs for every scene, a reader could put the scenes back
in order from the visuals alone, and there is nothing in it for the model to
misspell. **RULE 1 is unchanged and still wins on the digits.**

### 9.3 What v4 adds

* **RULE 5 — every visual must depict its own scene's step.** Three questions
  to answer from that scene's narration, all three of which go in the
  description: which operation is happening; what the working surface looks
  like *at this moment* (how many rows, is there a ruled line, is the answer
  row empty, is there a carry mark, is the placeholder zero in place); and
  where the attention is. *"A blank sheet is only correct for a scene whose
  narration is about a blank sheet. Every later scene has MORE on the page than
  the one before it."*
* **RULE 6 — no two scenes may share a visual, and none may be stock
  photography.** With the measured failures named: *"if the description you
  have written would still make sense for a lesson about photosynthesis, it is
  not a description of this scene."* A rule stated abstractly did not stop this
  one — which is what WP-62 learned about the translation prompt's scene 9.
* RULE 1 gains one clause: it bounds *how* a visual may show content; it does
  not excuse a visual from showing any.

### 9.4 Published through the prompts table — and HELD, deliberately

`ivgs-api/app/scripts/wp63_publish_storyboard_prompt.py`, the same versioning
path `wp61_publish_prompt.py` uses for translation: current version preserved
inactive, next inserted active, change note on the row, rollback is one UPDATE
of `is_active`. It **refuses** to publish a template that has lost RULE 5,
RULE 6 or RULE 1, and prints two digests each named for what it covers
(WP-62 Task 8(e)'s correction).

**THE MODEL DOES NOT MOVE.** Stage 2 stays on Llama. The conformance baseline
replays banked artefacts, not the active prompt row, so this cannot move the
AD-05 diff.

**It is NOT run.** Task 9's sequencing puts it after Task 4's acceptance is
banked, and Task 4's acceptance ends at an operator press (D-2). If v4 went
active now, the operator's next `regenerate` at the gate would rewrite the
storyboard under v4 and **Task 4's recovery of scenes 0, 2 and 7 would never
happen**. The active row is still v3, verified after the deploy.

```bash
# node-01 — run AFTER Task 4's acceptance is banked (D-2).
sudo docker exec -i ivgs-fastapi \
  python -m app.scripts.wp63_publish_storyboard_prompt \
  | tr -cd '\11\12\15\40-\176'
```

### 9.5 The shape test

Deterministic and model-free, so it gates in CI without an LLM in the loop and
without a flaky assertion about what Llama said today. The **four measured
scenes fail it** (identical visuals named as such; stock framing named by
pattern; "names no step and no state of the working surface"), and a compliant
rewrite of the same four passes — while containing **no digit at all**, which
is asserted separately so RULE 1 cannot be traded away for RULE 5.

**Not wired into the pipeline.** Stage 2's task body is frozen (AD-05 §8). The
place it could go without touching one is the scene-create route, as a FLAG
rather than a refusal — a behaviour change beyond this task. **Ledgered as
P2.64.**

### 9.6 The scene-5 before / after, verbatim

**BEFORE** (live, `scene_index 4`, the scene the brief calls scene 5):

> A hand holding a pencil, looking at a blank sheet of paper on a wooden desk,
> with a subtle background of a classroom, illustration style, leaving space
> for the composition overlay

**AFTER** — *the shape v4 asks for, from this report's own compliant fixture.*
The live after-text is produced by Llama under v4 and is the operator's
inspection step (D-2); this is what it is required to look like:

> The same desk and lamp; two partial-product rows already written above a
> second ruled line, the answer row beneath it still empty, the pencil resting
> at the foot of the ones column ready to descend, muted blue-grey illustration
> style

---

## S10. Task 10 — CI red on a compliance false positive

### 10.1 The one violation

Runs **#262 (`6a3b074`)** and **#263 (`8f64692`)** failed at `compliance-scan`,
Appendix F.2 Rule 1, on one line:

```
tests_system/test_wp61_node05.py:251
for banned in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
```

That is the WP-61 test which **asserts those variables are absent** from
node-05's environment. Downstream jobs cancel on the failed gate, so CI has
been fully red since the WP-61 push.

### 10.2 (a) The scanner is fixed, not the test

Renaming the literals, assembling them from fragments, or deleting the
assertion would each turn a working compliance test into a decoration for
getting past a compliance scanner. **The test's honesty is the point of the
test.**

A flagged line may carry, **on that line**:

```python
# compliance-exempt: F.2-R1 - asserts these names are ABSENT from node-05
```

honoured only when **all three** hold: the rule id names the rule that flagged
*that* line; a non-empty reason follows it; and the pragma is on the flagged
line itself. A bare pragma, a rule id with no reason, and a pragma for another
rule all **fail closed** — so an exemption cannot widen itself when a second
rule starts matching the same line.

**Every applied exemption is printed**, on clean runs as well as failing ones.
So are the four files `SKIP_FILES` has always excused *wholesale*, which were
silent until now — the same defect one file at a time instead of one line.

### 10.3 (b) Tests for the scanner

15 cases: the violating line fails; each of five incomplete or wrong pragmas
fails; the correct pragma passes **and is listed in the report**; the wrong
rule id fails **and is not even counted as an exemption** (the report must not
claim a line was excused when it was not); a pragma on the neighbouring line
does not reach; the `//` form works for TypeScript; the real repository scans
clean with its one exemption visible; and the wholesale skips are named.

### 10.4 (c) The Node.js 20 deprecations

Bumped in the two workflows that run on `ubuntu-latest`: `checkout` v4→**v7**,
`setup-python` v5→**v7**, `setup-node` v4→**v7**. What the changelogs declare:

| version | declared change | effect here |
|---|---|---|
| checkout v5 | node24 runtime; **minimum runner v2.327.1** | met by construction on `ubuntu-latest` |
| checkout v6 | credentials persisted to a separate file | none |
| checkout v7 | **refuses fork PRs under `pull_request_target` / `workflow_run`** | inert — no workflow here uses either trigger |
| setup-python v6 | node24; same runner minimum | met |
| setup-python v7 | **`pip-install` input REMOVED** | not used here |
| setup-node v5 | node24; **automatic caching when `package.json` has `packageManager`** | `ivgs-frontend/package.json` has no such field, so nothing starts caching that was not |
| setup-node v6 | automatic caching narrowed to npm | none |
| setup-node v7 | adds `cache-primary-key` / `cache-matched-key` outputs | none |

**`cd-deploy.yml` is deliberately NOT bumped, and that is the "report instead of
absorbing risk" branch.** Its three jobs run on
`[self-hosted, linux, x64, ivgs-infra]`, and that runner **has been dead since
2026-05-26** (recorded in `compliance-check.yml`'s own note). Its agent version
cannot be read, so whether it meets v2.327.1 is unknown, and a checkout that
refuses to run is a worse outcome than a deprecation warning on a workflow only
invoked by hand. **Bump it when the runner is back and its version is known.**

### 10.5 (d) Acceptance

```
Files scanned:       1583
Violations found:    0
Exemptions applied:  1
Files skipped whole: 4
------------------------------------------------------------------------
  [Exemptions applied - each honoured because its pragma names
   the rule that flagged the line, and gives a reason]
    tests_system/test_wp61_node05.py:261  [F.2-R1]
      reason: asserts these names are ABSENT from node-05
...
✓ Compliance check PASSED (1 exemption(s) applied, listed above)
EXIT=0
```

The full local suite is unchanged apart from the +80 this package adds.
**CI itself turning green happens at the operator's next push. That is the
expected outcome; it is not claimed as observed.**

---

## S11. Decisions needed

### D-1 — Task 9: binding the visual to the lesson, WITHOUT asking for the digits

**Ruling requested: confirm, or overrule.**

Task 9's example says scene 5's visual *"should show 92 + 230 = 322 being
worked"*. Implemented literally that reintroduces the defect RULE 1 was written
for and which this repository has now measured **three** times. v4 therefore
binds the description to the **step and the state of the working surface** and
leaves the digits to the composition overlay.

If the operator wants the digits in the description anyway, it is a one-line
change to the template and a re-run of the publisher — but RULE 1 should then
be relaxed explicitly and knowingly rather than by side effect.

**D-1(b), the smaller half.** Task 7(b) says *"a regeneration after approval
invalidates the approval exactly as an edit does"*. Implemented on the **DRAFT**
gate, not the storyboard one: the storyboard approval is what *authorises* a
regeneration, so invalidating it by its own effect would refuse the second
regeneration and make Task 4's three-scene recovery impossible. If the intent
was the storyboard gate — one approval per regeneration, deliberately — say so
and it is a two-line change.

### D-2 — Task 4 / Task 7 / Task 9 acceptance: the gate press is the operator's

Everything is deployed and proven. What remains is one human decision, and this
package will not forge it.

**The project's most recent recorded gate decision is `regenerate`, twice**
(15:17:25 and 15:17:29). Under this package's Task 8 that decision now *means*
"re-run the storyboard", which is Task 9's path. Recording an `approved`
decision on the operator's behalf would overwrite their stated intent and forge
the human half of a gate whose entire purpose is that it is human — the exact
defect WP-62 closed.

**The sequence, one press each:**

1. **Storyboard tab → Approve** (the storyboard on screen now, `sb-9-dba2b224…`).
2. Select scenes **#0, #2 and #7** → **Regenerate Selected**. One job, one
   dispatch. Scene #2 is already `video_clip` from the operator's own edit, so
   its new asset arrives through the video path — that is Task 7's acceptance
   gesture, completed.
3. The chain drains: manifest → audio → talking head → draft → **DRAFT GATE**.
   The six banked image asset ids in §S4.1 must be unchanged; check them.
4. **Then** publish storyboard v4 (§S9.4), press **Regenerate** at the
   storyboard gate, and inspect the new visuals — Task 9's acceptance, in its
   ruled order.

---

## S12. Ledger

| id | entry |
|---|---|
| **P2.61** | `CheckpointService.resume_from_checkpoint` asks for *the last checkpoint with status `complete`*. Under partial-advance a run leaves complete checkpoints AHEAD of the failed one, so the query points past the fault: job `d4b41765` would resume at `talking_head_render` while `image_generation` is the failure. WP-45 fixed the vocabulary; the query is still wrong for a mid-chain partial failure. Needs a ruling — a fix changes resume semantics fleet-wide. |
| **P2.62** | The Celery orchestrator cannot express *"these three scenes, then the tail of the chain, skipping stage 5"*. The least-waste path re-runs project-wide TTS. Temporal M3.3's durable resume is the real answer. |
| **P2.63** | A storyboard re-run producing FEWER scenes than the project holds leaves the surplus rows. `create_scene` sees one scene at a time; trimming needs a whole-storyboard write Stage 2 does not make. |
| **P2.64** | The visual-binding checker (`test_wp63_storyboard_prompt.check_visuals`) is deterministic and could gate a real run, but Stage 2's body is frozen. The place it could go is the scene-create route, as a flag rather than a refusal. |
| **WP61-L4** | **CLOSED by S6**, with its premise corrected: the exporter is up and scraped; `nvidia-smi` inside it exits 255. Operator block held. |

---

## S13. What was deployed, and what was changed on the live fleet

**Deployed to node-01 only**, by the artifact path (WP-34 rule 1; GHCR is off
the deploy path):

| service | image | verified |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.22.0-validator` | `docker inspect` — healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.22.0-validator` | healthy |
| `ivgs-celery-default` / `-composition` / `-beat` | `ivgs-workers:v5.22.0-validator` | healthy |

Artifacts at `/mnt/ivgs-shared/image-artifacts/`, registered in `MANIFEST.txt`,
standard filenames. **Nodes 02/03/04 need the workers rebuild** — the validator
lives in `ivgs-workers` — and that is an operator step; node-03's is the
`cogvideox-worker` service, not `celery-worker`.

`scripts/check_seed_conformance.sh` **PASSES** against the deployed image: all
ten baked seed templates byte-identical to the tracked ones, including the
amended `storyboard_generation.j2`.

**Migration 0036 applied** to `ivgs` and to `ivgs_reconciliation_test`.

**Live data changed, and nothing else:**

| change | scope |
|---|---|
| 20 append-only rows in `asset_quality_scores` | project `c12fa967`, tagged `WP-63-VALIDATOR`; no existing row edited |
| migration 0036 (two nullable columns, one FK, one partial index) | schema; no row rewritten |
| `ivgs-infra/.env` image tags | node-01 deploy |

**Project 14f71729 is byte-for-byte as it was**: 1 job row, 0 pending, 6 image
assets, 9 audio assets, 0 superseded, storyboard prompt still v3. The two live
probes against it were **refused** and left nothing behind, which was verified
rather than assumed.

Untouched: `c12fa967`'s assets, narration and variants; `52d52867`; the five
`e2e-photosynthesis-*`; every other project row. No node other than node-01 was
written to. node-05 and node-06 were read for telemetry only.

---

## S14. Push block — count-gated, for ALL held commits

**Eleven commits are held on `main` ahead of `origin/main`: the operator's two,
then this package's eight, then this report.** The gate counts all eleven and
refuses on anything else.

```bash
# node-01 (192.168.1.90). Run from /opt/ivgs. Self-gating; pushes nothing
# unless the count and the two boundary commits are exactly right.
( set -u
  cd /opt/ivgs || { echo "FAIL: /opt/ivgs missing"; false; }

  AHEAD=$(git rev-list --count origin/main..HEAD)
  FIRST=$(git rev-list origin/main..HEAD | tail -1)
  HEADSHA=$(git rev-parse --short HEAD)

  echo "ahead of origin/main : $AHEAD  (expected 11)"
  echo "oldest held commit   : $(git log -1 --format=%h%x20%s "$FIRST" | tr -cd '\11\12\15\40-\176')"
  echo "newest held commit   : $(git log -1 --format=%h%x20%s HEAD | tr -cd '\11\12\15\40-\176')"
  echo
  git log --oneline origin/main..HEAD | tr -cd '\11\12\15\40-\176'
  echo

  if [ "$AHEAD" -ne 11 ]; then
    echo "REFUSED: expected 11 held commits, found $AHEAD."
    echo "Something has been added or removed since this block was written."
  elif [ "$(git rev-parse --short "$FIRST")" != "fd7bb09" ]; then
    echo "REFUSED: the oldest held commit is not fd7bb09 (the 450W power cap)."
  elif [ -n "$(git status --porcelain)" ]; then
    echo "REFUSED: the working tree is not clean."
    git status --short | tr -cd '\11\12\15\40-\176'
  else
    echo "GATE PASSED. Pushing $AHEAD commits, fd7bb09..$HEADSHA"
    git push origin main
  fi
)
```

**The eleven, oldest first:**

```
fd7bb09  fix(node-04): 450W power cap survives reboots (WP-62 D-3)          [operator]
a6a4f8e  fix(node-05): the full engine digest, closing WP-62 D-1 / WP62-L8  [operator]
2328986  fix(wp-63): the blank check was measuring colour density...
bbf13e2  fix(wp-63): the job row names the stage the checkpoint recorded...
60c7992  fix(wp-63): the compliance scanner gets a visible exemption...
d536e89  fix(wp-63): "Open editor" was a link to the page you were on...
74ad431  fix(wp-63): per-scene regeneration was refused, correctly...
6e16e96  fix(wp-63): the gate's regenerate decision dispatches the stage...
922930b  fix(wp-63): storyboard v4 binds each visual to its own scene's step
c6d2344  fix(wp-63): the rescore says which pass wrote a row...
<this>   docs(wp-63): report - the check was measuring colour density...
```

The eleventh is this report and the annotation extension; its sha is printed by
the block's own `git log` line, so read that rather than trusting a number
written before the commit existed.

**CI on that push is expected to go green** at `compliance-scan` for the first
time since the WP-61 push. That is the expected outcome, not an observation.
