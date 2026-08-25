# WP-44-QUALITY — the gate stops rubber-stamping, and gets a model to score with

| | |
|---|---|
| **Ships** | `ivgs-workers:v5.10.0-quality` (4 nodes), `ivgs-api:v5.10.0-quality` (node-01), **`ivgs-clip-scorer:v5.10.0-quality` (node-05, new)** |
| **Closes** | swallow register **instance 24**, and **instance 25** — found while closing 24. Ledger **P2.41**. |
| **Opens** | ledger **P2.45** (a stale test module, pre-existing) |
| **State** | Committed and **HELD**. 7 commits. Nothing pushed. |
| **Engines** | vLLM, CogVideoX, LatentSync, ComfyUI, Coqui, Kokoro, WhisperX, Wan-Animate — **all untouched**, verified by uptime. |
| **Frontend** | not touched; stays `v5.9.0-telemetry`. |

---

## 0. Executive summary

The quality gate could not fail an asset. Sixteen deformed images from the first
end-to-end run carry `quality_score: 1.0` — a perfect score awarded by a gate in which
**two of its three real checks never executed**, and where the third's absence was worth
its full weight because of this line:

```python
        else:
            score += 0.15  # Default pass if CLIP unavailable
```

All of that is gone, and every limb of it is verified live on the deployed image.

**What is proven end to end.** A real CLIP model runs on node-05. A real score travels
node-05 → the API's new `/api/v1/clip/score` → the worker's `ImageValidator` → the
stage-3 result fields, measured inside the deployed worker container. The same image
scores **0.3402** against its own prompt (approved) and **0.1393** against an unrelated
one (**rejected** — "CLIP score too low"). numpy is in the image and its blank/solid
check now rejects six of the first run's sixteen images. Video assets are validated for
the first time, including a frame-distinctness measurement that reproduces the WP-46
addendum's 77/77. The animation branch refuses a person-free reference by name, using the
engine's own detection weights. §1–§5.

**What I found while doing it.** `POST /api/v1/quality-scores` — the route the worker has
been calling since Phase 4 — **did not exist**, and the call site swallowed the 404
because `await client.post` does not raise on one. `asset_quality_scores` held **zero
rows for the entire life of the system**. That reframes Task 6(c): there is no review
history to clear, because none was ever written. Registered as instance **25**, fixed, and
watched landing. §3.4, §7c.

**What a real gate still cannot do, stated rather than buried.** CLIP cannot do
arithmetic. Scene 0's image — whose whiteboard reads `2? x 23.14` where the prompt asked
for `23 x 14` — scores **0.3673** and is **approved**. CLIP is measuring *"is this a
teacher at a whiteboard"*, and it is. No scorer on this fleet catches deformed on-screen
text, which is exactly why Task 4 forbids requesting it. §7c.

**One deviation I introduced and corrected.** Deploying node-03 by service name recreated
a `profiles: ["standby"]` worker that was not running, and left the real one on the old
image. Caught in the same minute, undone, and reported in full. §6.3.

---

## 1. Per-task verdicts

| Task | Verdict | Evidence |
|---|---|---|
| **1 — the checks that silently pass** | **PASS** | numpy declared + imports in all four deployed workers; free +0.15 gone (negative gate run inside the image); `clip_score: "unavailable"` as a literal string; `checks_missing` / `check_coverage` / `quality_score_complete` on every result and in every submitted record; missing checks cap the decision at `flagged`. §2 |
| **2 — a real CLIP service on node-05** | **PASS** | `ivgs-clip-scorer` live and healthy on node-05. Real scores flow to stage-3 results end to end, proven inside the deployed worker against banked reference images. VRAM 1040 MiB (2.1% of the card); 21 ms compute, 130 ms end-to-end through the proxy. **Decision: proxy, justified in §3.2.** MBCP registration raised as **D-1**, not blocked on. §3 |
| **3 — video assets get a validator** | **PASS** | `VideoValidator` was built-and-discarded; it runs now in both video and animation tasks. Duration-vs-expected, frame distinctness (the WP-46 pattern), ffprobe corruption probe, honest missing-check reporting. Live on node-03 against three real assets. §4 |
| **4 — storyboard prompt rules** | **PASS (files) / HELD (the DB row)** | All four rules in all three templates, each carrying the evidence that bought it, 45 tests pinning the text. The live prompt is a DB row `seed_prompts.py` will not touch; corrective SQL authored, md5-guarded, dry-run verified, **HELD**. §5 |
| **5 — animation input guard** | **PASS** | `WanAnimateInputError("reference image contains no person to animate")` fires before any GPU reservation, on YOLOv10m — the engine's own MBCP-provenance weights. Tested with a person image and a person-free image; both are real frames from the first run. §5.5 |
| **6a — AD-04 doctrine, close P2.41** | **PASS** | Ruled Seam-2-scoped; written into `dev/CLAUDE.md` §11.1 with both quotes. P2.41 CLOSED. §7a |
| **6b — AD-02 amendment, close P2.43** | **DRAFTED, P2.43 stays OPEN** | Draft 4 authored as a document under §18 change control. **No spec text edited.** P2.43 is now blocked on review, not on work — which is what "under change control" means. §7b |
| **6c — the 18 stale review items** | **PASS, premise corrected** | There is nothing to clear: the queue has always been empty. Decision: **re-score**, with a held tool and a full dry run of all 19 assets. §7c |

---

## 2. TASK 1 — what a quality score is allowed to claim

### 2.1 The three mechanisms, and what replaced each

| # | The defect | The fix |
|---|---|---|
| a | `numpy` was never in `ivgs-workers/requirements.txt`. `import numpy` raised inside the image and the handler set `blank_check_ok = noise_check_ok = True`. | `numpy==2.2.1` declared and pinned. The `ImportError` guard **stays** and now sets nothing to True: it appends both names to `checks_missing`. |
| b | The CLIP endpoint 404'd; `_compute_clip_score` returned `None`, indistinguishable from "not requested". | A real scorer (§3), and `ClipStatus` — `scored` / `unavailable` / `not_requested`. `clip_score` serializes as the float when scored and the literal string `"unavailable"` otherwise. |
| c | `score += 0.15  # Default pass if CLIP unavailable`. | An unscored check is removed from the numerator **and the denominator**. `quality_score` means *"of the checks that ran, this fraction passed"*; `check_coverage` says how much that was. |

### 2.2 The scoring rule, stated

With every check present the result is identical to the old weighted sum — pinned by a
test. With a check missing it is renormalised, and **three fields carry the difference**:

```
scorer present : quality_score 1.0   coverage 1.00   complete True    clip_score 0.3402
scorer absent  : quality_score 1.0   coverage 0.85   complete False   clip_score "unavailable"
```

Both say 1.0 and they are no longer the same claim. The second says *"of the 85% of this
gate that ran, everything passed"*, names `clip_ok` as missing, and **cannot reach
`approved`** — because a gate may not certify what it did not measure. That last clause is
the one that makes instance 24 structurally impossible rather than merely fixed.

### 2.3 Watched surfacing — the first run's exact condition, reconstructed

`numpy`'s import forced to fail, no scorer reachable:

```
checks_missing   ['blank_check_ok', 'clip_ok', 'noise_check_ok']
blank_check_ok   False        <- MISSING, and no longer reading as passed
noise_check_ok   False
quality_score_complete  False
check_coverage   0.6
decision         flagged
warnings         ['CHECK MISSING — blank/solid-colour and pixel-variance detection did
                   not run: numpy is unavailable in this image …']
```

### 2.4 And it catches real assets

With numpy present, the blank/solid check **rejects six of the sixteen** first-run images
(§7c) — the letterboxed equation cards, which are mostly black frame. That check has never
run before on this fleet.

---

## 3. TASK 2 — a CLIP model that exists

### 3.1 What was built

`ivgs-clip-scorer/` — FastAPI, `openai/clip-vit-base-patch32`, weights **baked into the
image at build time**, so the running container needs no network and no HuggingFace
reachability, and the banked artifact restores with `docker load` alone.

**Why ViT-B/32 and not something larger.** IVGS's thresholds — `clip_score_approved: 0.25`
and `clip_score_flagged: 0.18`, in `configs/media_generation.yml` and
`ImageQualityThresholds` — are on the raw-cosine scale ViT-B/32 produces, and it is the
model the CLIPScore literature is calibrated on. A bigger tower shifts that scale and
silently re-calibrates every threshold on the fleet; that is a change needing its own
measurement pass, not a default. The service reports `scale: "raw_cosine_similarity"` in
every response and exposes `/thresholds` so a future substitution has to confront it.

**A bad request is not an unavailable scorer.** The proxy passes a backend 4xx through
with its own status and a `BAD_SCORING_REQUEST` code, rather than folding it into the 503.
"The scorer is unreachable" and "your bytes are not an image" are different facts, and
collapsing them would be the same imprecision this package exists to remove. Verified live:
an empty `image_base64` returns **HTTP 400** naming the decode failure, while a real image
still scores 0.3402 through the same route.

**Honesty contract.** `/score` returns a score or an error. No fallback constant, no
"conservative default", no `0.80`-on-exception. `/health` reports `model_loaded` from the
object, not from the fact that the process is up, and the container's HEALTHCHECK greps
for it — so a scorer whose model failed to load is UNHEALTHY rather than quietly serving
503s.

### 3.2 DECISION — implement the API route as a proxy, not repoint the workers

The work order offered both. **I implemented the route stage 3 already speaks.**

1. **One deployment surface, not four.** A worker-side repoint is a new environment
   variable that must be correct in four `.env` files on four nodes and stay correct
   through every future recreate. Every per-node env-drift incident in this repo's history
   — node-04's VRAM figure, node-02's orphaned compose network, the `IVGS_VLLM_URL`
   overrides — argues against adding another. The API already is the workers' single
   callback hub: checkpoints, DLQ, assets, prompts and job status all come here.
2. **The scorer stays off the worker network path.** Workers gain no new outbound
   dependency; node-05 is reachable only from the API. Same containment WP-48 gave the
   node-logs source.
3. **No already-deployed worker is left pointing at a URL that does not answer** — which
   is precisely the failure being fixed. Recreating it elsewhere would be perverse.
4. **The scorer's state becomes checkable in one place**: `GET /api/v1/clip/health`.

**The cost, measured rather than assumed:** the extra LAN hop for a base64'd 1.1 MB PNG is
**130 ms end-to-end vs 60 ms direct** (medians of 10). Against a FLUX render this is
noise. Recorded so a future package that wants the 70 ms back knows what it is buying.

### 3.3 Live scoring evidence — direct to node-05

Six calls, two banked reference images from the first run, on the running service:

```
case                                              score    svc ms     rt ms
---------------------------------------------------------------------------
scene-0 image vs ITS OWN prompt                  0.3402      21.3      61.0
scene-0 image vs scene-2 prompt (mismatch)       0.2294      21.5      60.1
scene-0 image vs unrelated ("a submarine")       0.1393      20.9      59.8
scene-2 image vs ITS OWN prompt                  0.2738      21.2      46.5
scene-2 image vs scene-0 prompt (mismatch)       0.2432      21.6      47.2
scene-2 vs literal description                   0.2724      21.1      46.5

model: openai/clip-vit-base-patch32   device: cuda   scale: raw_cosine_similarity
```

The ordering is the calibration argument: own prompt 0.3402 (above the 0.25 approve
threshold), mismatched 0.2294 (the flag band), unrelated 0.1393 (below the 0.18 reject
threshold). **The thresholds already in the codebase separate these three populations
correctly, unchanged.** No threshold was touched by this package.

### 3.4 Real scores reaching stage-3 results — end to end, inside the deployed worker

Run inside `ivgs-celery-default` on the shipped image, building the scorer URL with
**stage 3's own expression** and calling the real route:

```
clip_api_url stage 3 builds : http://fastapi-backend:8001/api/v1/clip

=== scene 0 (teacher) vs its own prompt ===
  decision              : approved
  quality_score         : 1.0      complete: True   coverage: 1.0
  clip_score            : 0.34018367528915405     clip_status: scored
  checks_run            : [blank_check_ok, clip_ok, corruption_ok, file_size_ok,
                           format_ok, noise_check_ok, resolution_ok]
  checks_missing        : []
  submitted clip_score  : 0.34018367528915405

=== scene 0 vs unrelated prompt ===
  decision              : rejected
  clip_score            : 0.13932180404663086     clip_status: scored
  errors                : ['CLIP score too low: 0.139 (threshold: 0.18)']

=== control: the SAME validator with no scorer configured ===
  decision              : flagged
  quality_score         : 1.0      complete: False  coverage: 0.85
  clip_status           : unavailable
  checks_missing        : ['clip_ok']
  submitted clip_score  : "unavailable"
```

**A defect of my own, found by this probe and fixed.** The first run of it returned
**HTTP 403**: `ImageValidator` sent no `Authorization` header, and `/clip/score` is
service-token authenticated like every other worker→API route. The honesty machinery
behaved perfectly — recorded `unavailable`, contributed nothing, capped at `flagged` — and
that is exactly how the miss became visible instead of being paid a free 0.15. The token
is threaded through (`clip_auth_token`), pinned by a test, rebuilt and redeployed.

### 3.5 The write actually lands now — register instance 25

`POST /api/v1/quality-scores` did not exist. The worker had been calling it since Phase 4
inside a bare `except Exception`, and **a 404 raises nothing**. Measured before the fix:

```
SELECT count(*) FROM asset_quality_scores;   ->  0
GET /api/v1/quality/flagged                  ->  0 rows
```

Zero, for the entire life of the system. Route added; worker side now checks the status
code and logs it. **Watched landing** — one genuine verdict, computed by the real gate for
a real asset, submitted through the deployed path:

```
computed verdict: approved 1.0 clip 0.3402 complete True
[info] quality_score_submitted asset_id=737238b0-… decision=approved

-[ RECORD 1 ]-+-------------------------------------
id            | a52b41b9-128b-48e9-bf3c-473dd5fac6cd
asset_id      | 737238b0-65ee-4fa6-8802-dd6609633efe
quality_score | 1
decision      | approved
reviewed_by   |            <- NULL: an automated verdict, not a human one
clip          | 0.34018367528915405
complete      | true
coverage      | 1.0
missing       | []
```

That is the first row `asset_quality_scores` has ever held. It is real data, kept.

### 3.6 VRAM and latency, measured

| | |
|---|---|
| Card | NVIDIA RTX PRO 5000 Blackwell, 48935 MiB, driver 580.173.02 |
| **VRAM, process** | **1040 MiB** (`nvidia-smi --query-compute-apps`) |
| VRAM, torch allocator | 577.1 MiB allocated / 630.0 MiB reserved / 577.1 peak |
| VRAM, whole card | 1050 / 48935 MiB — **2.1%** |
| Idle power | 59.04 W |
| **Compute latency** | **21 ms** median, 1920×1080 PNG (min 21.3 / med 21.7 / max 21.9, n=10) |
| Round trip, direct | 60 ms median |
| Round trip, via node-01 proxy | 130 ms median (116 / 129.6 / 133.8) |
| Model load at startup | ~40 s cold (healthcheck `start_period: 180s`) |

### 3.7 D-1 — should the scorer be registered in MBCP? (raised, not blocked on)

**Raised as a decision, as the work order asks.** The argument for: every other model that
influences a pipeline outcome on this fleet is an AD-01 store row with an attestation, and
a CLIP score now decides whether an asset is approved or rejected. Provenance symmetry
says the thing doing the deciding should be as traceable as the things being decided about.

The argument against, and why I did not do it: the store's `models` table is keyed on
`(stage, tier)` in **MBCP's** taxonomy, and image-text scoring is not one of MBCP's nine
capability stages. Registering it needs either a taxonomy extension (MBCP-owned) or a
deliberate misuse of an existing stage key. There is also no MBCP certification for
`clip-vit-base-patch32` to attest to; the weights came from HuggingFace, not the MBCP
serving plane, and inventing an attestation is precisely the class of thing this package
exists to stop.

**Recommendation:** raise it with MBCP as a taxonomy question before creating a row. In
the meantime the provenance that exists is real and stated: the model id and revision are
pinned by the image digest, `/health` reports the model id, and every score carries
`model` and `served_by`.

---

## 4. TASK 3 — video assets get a validator that runs

### 4.1 The finding

`VideoValidator` has existed for months. Its **only** construction anywhere in the
repository was:

```python
        # 4. Validate
        _validator = VideoValidator()  # noqa: F841
```

Built, lint-silenced, discarded. That is why the first run's video assets carry
`quality_decision: ""` and `quality_score: 0.0` — not a bad score, **no score**.

### 4.2 What it does now

Wired into `video_generation_task` and `animation_generation_task`, under the same honesty
contract as the image side, plus:

* **Duration vs expected** against the storyboard's own `duration_seconds`. With no
  expected value the comparison reports itself missing rather than passing by default.
* **Frame distinctness** — the WP-46 addendum's method promoted from a one-off proof to a
  standing check. Frames decoded to greyscale at a fixed working resolution and compared
  pairwise. All-identical → **REJECTED**: that is a still in an MP4, which is the exact
  defect WP-46 existed to end.
* **Corruption probe** via the ffprobe checks the draft assembler already uses.
* **`expect_audio=False`** for CogVideoX and Wan. A video-only MP4 is their normal output;
  before, "No audio stream found" flagged every single clip for a non-defect.

### 4.3 Live, on node-03, against the real banked assets

```
--- asset 3bc54e58 — the WP-46 Wan2.2-Animate render (scene 3, expected 10s)
  decision   : flagged     quality_score 0.7222   complete False   coverage 0.9
  geometry   : 768x1408 @ 30.00 fps, 2.567 s, h264, 77 frames
  distinctness: 77/77 distinct, 0/76 identical consecutive pairs
                consecutive abs diff min 0.292 mean 1.357 max 2.839; first-vs-last 10.076
  warnings   : Resolution mismatch: expected 1920×1080, got 768×1408
               Duration deviation: expected 10.00s, got 2.57s (tolerance ±1.50s)

--- asset 3e133509 — CogVideoX clip (scene 1, expected 8s)
  decision   : rejected    quality_score 0.5
  geometry   : 720x480 @ 8.00 fps, 6.000 s, mpeg4, 48 frames
  distinctness: 46/48 distinct, 2/47 identical consecutive pairs
  errors     : Unsupported video codec: mpeg4 (allowed: h264, h265, hevc, vp9)
```

**The distinctness figure reproduces the WP-46 addendum's independent measurement**: it
recorded *77 distinct of 77, zero identical consecutive pairs*, mean consecutive diff
1.416 and first-vs-last 10.214 at full resolution; this check reports 1.357 and 10.076 at
its 128×128 working resolution. Two different implementations, one conclusion: it moves.

The Wan render is **flagged**, correctly — 768×1408 is the certified geometry, not IVGS's
1920×1080, and 2.567 s is not the 10 s the storyboard asked for. Both are known, recorded
deviations (WP-46 addendum), and they are now *surfaced by the gate* rather than living
only in a report.

The two CogVideoX clips are **rejected**: `mpeg4` where h264 was required, 720×480 where
1920×1080 was required, 8 fps where 24–60 was required, 6 s where 8 s was asked for. Those
four facts were true on 2026-08-23 and nothing said so.

---

## 5. TASKS 4 & 5 — teaching the storyboard, and guarding the input

### 5.1 The four rules, and what each one cost

| Rule | The evidence that bought it |
|---|---|
| **(a) no on-screen text** | Scene 0 asked for *"a whiteboard with a multiplication problem written on it, such as 23 x 14"*; FLUX produced a whiteboard reading **`2? x 23.14`**. Scene 2 asked for calculations *"appearing on screen"* and produced **`12 + 44 = 67 + 5`** and **`3 + 4 = 7 = 8`**. Sixteen images, none salvageable by regeneration — the model cannot do the thing being asked. |
| **(b) `animation` only with a character** | Both templates said the opposite in as many words: *'Use "animation" for data visualizations, flowcharts, and step-by-step processes'*. **Eleven of the eighteen** reference scenes were typed `animation` on that instruction, and every one is an equation card with no subject in it. |
| **(c) narration self-consistency** | The reference narration reads *"we should add 92 and 230 … but that was also incorrect"* and *"this gives us 260, but we wrote it as 640 in the previous step, which is incorrect"* — a script arguing with a draft the audience never saw. |
| **(d) durations sum to runtime** | Eighteen scenes summing to **190 s against a 300 s target** (63%). The old instruction was a parenthetical *"(sum should approximate total runtime)"*. |

Each rule ships **with the evidence attached**, so it does not get edited back out by
someone who does not know why it is there — and a test asserts the evidence is still
present. Rule (b) also states the *mechanism* (pose reenactment, and that the pipeline now
refuses such a scene by name), because a model that knows why can generalise and a model
given a bare prohibition cannot.

### 5.2 All three templates, not one

`ivgs-workers/prompts/stage2_system.j2`, `stage2_user.j2`, and
`ivgs-api/seed/default_prompts/storyboard_generation.j2` all carry all four rules. A rule
present in one and absent from another is the WP-43 defect ("the storyboard prompt
template still taught the rejected vocabulary"), and the test parametrises over all three
so it cannot recur silently.

`animation_generation.j2` is corrected too: it described *"an animated diagram or
visualization … Remotion component specification format"*. IVGS has no Remotion renderer,
and that branch is Wan2.2-Animate.

### 5.3 The live prompt is a fourth copy, and it is HELD

Stage 2 fetches the **active global `storyboard_generation` row from the database**, and
`seed_prompts.py` skips any type that already has one (`seed_prompts.py:52-62`). Editing
the seed file changes nothing about what the model receives.

`dev/workpackages/WP-44-storyboard-prompt-v3.sql` — **authored and HELD**, following the
`WP-IVGS-0-F6-corrective-prompts.sql` precedent that produced the currently-active v2 row.
It is one transaction; it guards on `md5(prompt_text)` of the exact measured state and
aborts otherwise; it **inserts a new version and deactivates the old one, deleting
nothing**; and a test asserts it embeds the seed files byte-for-byte so the two cannot
drift.

**Dry-run verified against the live database** with `COMMIT` swapped for `ROLLBACK`:

```
BEGIN / DO / UPDATE 1 / INSERT 0 1 / DO / UPDATE 1 / INSERT 0 1

 storyboard_generation | 3 | t | wp-44-quality | 8b120d1ff6f84f8286bf16d6022041a0 | 3793
 animation_generation  | 2 | t | wp-44-quality | d8f8b018c51931cc7caa0b1df140b9f8 | 1744
 → exactly one active global row per type
ROLLBACK
```

The md5s match the committed seed files exactly. **The live rows are unchanged.**

### 5.4 A judgement call worth naming

Rule (b) converts a wrongly-typed scene from *"a bad animation"* into *"a failed scene"*.
Left as they are, the reference project's eleven equation-card `animation` scenes would
now **fail** rather than render a hallucinated body. That is the intended behaviour and it
is strictly better — but it means the prompt fix and the guard belong together, and
applying the guard without the corrected prompt would turn sixteen bad images into eleven
failures. Both ship in `v5.10.0-quality`; the DB row is the one piece still held, and
§8 D-2 flags it.

### 5.5 TASK 5 — the guard, live

YOLOv10m, COCO class 0, CPU via onnxruntime, run on the reference image **before any GPU
reservation**. The weights are **the engine's own**: `yolov10m.onnx` is one of the nine
certified bundles WP-46's addendum fetched from the MBCP serving plane with manifest HMAC,
bundle digest and per-file SHA-256 all verified. It is the model the certified Wan graph
loads in `OnnxDetectionModelLoader` to find the subject it is about to animate. The guard
asks the engine's own question, with the engine's own model, one step earlier.

Measured in the deployed node-03 worker, on real frames from the first run:

```
scene 0 reference (teacher)   present   n=1  best 0.9427  813 ms  => RENDER PROCEEDS
scene 2 reference (equations)  absent   n=0  best 0.0013  464 ms  => SCENE REFUSED
scene 3 reference (equations)  absent   n=0  best 0.0052  446 ms  => SCENE REFUSED
```

Three orders of magnitude between the populations: the 0.25 floor is a chasm, not a
delicate threshold. **Scene 3 is the image WP-46 actually rendered an animation from.**

**Three outcomes, not two.** `absent` fails the scene. `unavailable` — no onnxruntime, no
weights file, a load or inference error — does **not**, because *"we did not look"* is not
*"there is nobody there"*. A guard that failed scenes when its own detector was missing
would be instance 24 pointed the other way. The verdict travels on the result either way,
so a render made while the detector was unavailable stays distinguishable afterwards from
one made against a verified subject.

Cost: ~1.3 s single-threaded on node-01, 0.45–0.8 s on node-03, against the **256 s** WP-46
measured for one real Wan render. Deliberately single-threaded so it does not contend with
the render.

---

## 6. Build and deploy evidence (WP-34 binding rules)

### 6.1 Rule-by-rule

| Rule | Compliance |
|---|---|
| **1** Registry off the deploy path; bank first, distribute via `/mnt/ivgs-shared` + `docker load` | Followed. All three images banked with `scripts/save-image-artifact.sh`, `sha256sum -c` and `zstd -t` verified, MANIFEST lines recorded. Distribution to nodes 02–05 by artifact copy + `docker load`. **Nothing pushed to GHCR** (see §6.4). |
| **2** Gate image presence on each node before any `.env` write; record rollback tag | Followed. Presence gated before and after `docker load` on every node; image ID `138250c69a60` identical on all four. Rollback tags recorded and `.env` backed up per node. |
| **3** Label-derived compose, `--force-recreate --no-deps --pull never`, services named | Followed — and this is where I deviated once; see §6.3. |
| **4** Verify by CONTENT inside running containers, never by tag | Followed. §6.2. |
| **5** node-04 `IVGS_LATENTSYNC_TAG` unchanged before and after; engines not recreated | **Verified: `v5.2.7-h0` before and after.** latentsync/comfyui/coqui/kokoro/whisperx all still `Up 12 hours`. |
| **6** Never `env \| grep IVGS_`; narrow greps only | Followed (`^IVGS_CLIP_SERVICE_URL=`, `^IVGS_WORKERS_TAG=`, `^IVGS_LATENTSYNC_TAG=`). |
| **7** `ivgs-infra/.env*` never committed | Followed. `docker-compose.node01.yml` is tracked and committed; `.env` is not, and the new `IVGS_CLIP_SERVICE_URL` is composed from the existing `${NODE_05_IP}` rather than needing a new secret. |

### 6.2 Content markers verified in RUNNING containers

```
node-01 api     clip.py present; quality_scores_router registered
node-01 worker  numpy 2.2.1 / onnxruntime 1.20.1; distinctness; guard message;
                no free-pass line; clip auth; ffmpeg
node-02 worker  numpy 2.2.1  onnxruntime 1.20.1  distinctness OK  guard OK
                no free-pass OK  clip auth OK
node-03 worker  (same, all pass)
node-04 worker  (same, all pass)
node-05         /health -> {"model_loaded": true, "device": "cuda",
                            "model": "openai/clip-vit-base-patch32"}
```

Live route listing on the deployed API:

```
/api/v1/clip/health          ['get']
/api/v1/clip/score           ['post']
/api/v1/quality-scores       ['post']      <- the route that did not exist
/api/v1/quality/flagged      ['get']
/api/v1/jobs/{job_id}/quality ['get']
```

Fleet after: 5 Celery workers online with the **same queue map as before** —
`composition` / `default+notifications+cleanup` / `gpu_llm` / `gpu_video+gpu_animation` /
`gpu_image+gpu_tts+gpu_talking_head`. node-02's vLLM still serves `llama-3.3-70b` through
`resolve_endpoint('vllm')` after the worker recreate (HTTP 200; key read from env, never
printed).

### 6.3 A deviation I introduced, and undid

**What happened.** I deployed nodes 02–04 with one loop that named the compose service
`celery-worker`. On node-02 and node-04 that is the running worker. **On node-03 it is
not**: node-03's running worker is `cogvideox-worker` (`ivgs-cogvideox-worker-node03`,
queues `gpu_video` + `gpu_animation`), and `celery-worker` is a `profiles: ["standby"]`
service consuming `gpu_llm` — profile-gated precisely so it is not resurrected by accident
(the AD-02 standby precedent, `68ac33b`).

Naming it explicitly bypassed the profile gate. For about sixty seconds node-03 ran a
second worker competing with node-02 for `gpu_llm`, while **the real worker stayed on the
old image**.

**What I did.** Stopped and removed `ivgs-celery-node03`, then recreated `cogvideox-worker`
— the correct service. Verified after: node-03 runs one worker on `v5.10.0-quality`;
`gpu_llm` has exactly one consumer (node-02); the Wan-Animate and CogVideoX engine
containers show `Up 6 hours` and `Up 11 hours`, i.e. **not recreated**.

**Why it is in the report rather than quietly fixed.** WP-34 rule 3 says services named
explicitly, and I named the wrong one because I assumed a service name was uniform across
nodes. It is not. The lesson is the one the runbook already teaches and I under-applied:
derive the service from the **running container's own labels**, per node, every time — not
from the compose file's service list and not from the other nodes' names.

### 6.4 GHCR

Not pushed. Rule 1 decouples it and a push failure aborts nothing; the artifact is the
distribution path and all three are banked and verified. The clip-scorer image is 12.6 GB
(4.3 GB compressed) and the fleet's standing policy is that large GPU images are not
pushed to GHCR (RECOVERY.md, decision of 2026-06-02) — recovery is Dockerfile-in-git plus
the banked artifact, which is exactly what exists.

### 6.5 Artifacts banked

| Image | ID | Artifact sha256 | Size |
|---|---|---|---|
| `ivgs-workers:v5.10.0-quality` | `138250c69a60` | `ac59465e2453934c36b33633a9c0324e535a2c664684c836d0f5860addae5fe7` | 313 M |
| `ivgs-api:v5.10.0-quality` | see `docker images` | `253631cda7fd55e1f3f1b2568479b098df37f97be5cd4c94ccbfeae1d1d7e264` | 113 M |
| `ivgs-clip-scorer:v5.10.0-quality` | `c52d6020a4cf` | `eec9193ccc24916dc2f20da84ccc72f1303f92dcc6999295966b67858b56b7f0` | 4.3 G |

All three: `sha256sum -c` OK and `zstd -t` OK. **Note:** MANIFEST.txt carries repeated lines for `ivgs-workers` and `ivgs-api`. The
register records *saves*, not invocations, and both images were rebuilt after their first
banking — workers twice (the CLIP auth fix, §3.4; the Temporal payload mirrors, §8.2) and
api once (the 4xx pass-through, §3.1). The **last** line for each is the deployed artifact;
the shas in the table above are the ones on disk now and they match the running images.

### 6.6 Rollback

Per node: restore the recorded `.env` tag and re-run the same label-derived compose
invocation. Verified present, not assumed — `v5.8.0-animation` is still in the local image
store on all four nodes and its artifact is still in `/mnt/ivgs-shared/image-artifacts`.
`.env` backups written as `.env.bak-wp44-<timestamp>` on every node.
node-05 rollback is `docker compose -f docker-compose.quality.node05.yml down` — the
service is purely additive and removing it returns the node to its WP-48 state.

---

## 7. TASK 6 — riders

### 7a. AD-04 direction doctrine — P2.41 CLOSED

Ruled **option (i): the doctrine is Seam-2-scoped**, and written into `dev/CLAUDE.md`
§11.1 as a table of the two seams with their directions, mechanisms, IVGS-side components
and authorities:

* **Seam 1 (metadata/attestation): MBCP-initiated PUSH**, per SSOT §12.4/§12.6.
  `ad01_ingest.py` is a receiver, and correctly so.
* **Seam 2 (weights): IVGS-initiated PULL**, per AD-04 v3.1 closed decision #2.

The "PULL-ONLY: IVGS initiates all transfers" phrasing comes from decision #2, which is
titled *Weight-serving transport*. It is true of Seam 2 and false of Seam 1, and AD-04-v3
§3.14 says so directly: *"`AD01Export` (Phase 4): POSTs the bundle to AD-01."* Both quotes
are in the doc.

**No code changes.** The implementation already conformed to the SSOT on both seams; the
sentence was what needed correcting. The entry carries the practical consequence
explicitly — **do not "fix" `ad01_ingest.py` into a puller** — because that is the change
someone reading "pull-only" would reach for, and it would be an MBCP-owned amendment to a
section §787 freezes.

### 7b. AD-02 amendment for node-05 — DRAFTED, P2.43 stays OPEN

`docs/IVGS_v5_Addendum_AD-02_Draft4_node05_quality_services_DRAFT.md`. **Document only. No
specification text has been edited** — AD-02 Draft 3 and `docs/ivgs_v5_functional_spec.md`
are untouched, deliberately, because that is what "under change control" means.

It proposes replacing the node-05 bullet and Appendix AD-B row with *the quality-services
node*; supplies the measured basis (48935 MiB card; the deployed scorer at 1040 MiB /
**2.1%**, 21 ms); records that the Draft-3 role — SDXL image fallback, Ollama LLM
fallback, FFmpeg composition overflow — **has never run on that node**; inventories the
four consequential edit sites, one of which is a *test* asserting the wrong hardware and a
service map for services the node does not run; and leaves four questions for the reviewer,
including whether those fallbacks survive anywhere at all and where §11.1's unimplemented
safety classifier goes.

It also states what it does **not** propose: node-05 does not become a Celery consumer. A
quality check running inside the worker fleet competes with the pipeline for the resource
it is auditing; scoring is a synchronous call from the API and node-05 holds no queue.

**P2.43 stays OPEN**, now blocked on a decision rather than on work.

### 7c. The "18 stale flagged review items" — the premise needed correcting first

**Measured, before deciding anything:**

```
SELECT count(*) FROM asset_quality_scores;   ->  0
GET /api/v1/quality/flagged                  ->  0 rows
celery_taskmeta rows for stage-3 task names  ->  0
```

**There is no review history.** Those sixteen verdicts were never written anywhere: they
were POSTed to a route that did not exist and the 404 was swallowed (§3.5, register
instance 25). The only copy that ever existed was the Celery result row, and
`celery.backend_cleanup` has since reaped every stage-3 task from `celery_taskmeta` — which
is why the WP-39 report could decode them on 2026-08-23 and I cannot today.

So "clear or re-score" has one available answer. Clearing is a no-op on an empty table. The
**19 assets** (16 images + 3 videos) are still there, with no verdict of any kind attached.

**DECISION: re-score. Do not clear.** Nothing is deleted because nothing exists to delete;
the re-score is purely additive and gives the review queue the first real content it has
ever had.

**Dry run, all 19 assets, through the real gate on the deployed image:**

```
asset_id                               type   scn  decision     score   cmpl     clip  why
737238b0-65ee-4fa6-8802-dd6609633efe   image  0    approved    1.0000   True   0.3673  -
2a912fb7-72eb-4f40-8aae-f6e2c38b286f   image  2    rejected    0.8500   True   0.2727  blank or solid color
ba59d633-13c2-4c10-a2ab-d3a7883310d7   image  3    approved    1.0000   True   0.3209  -
ef51a8c8-4c91-45e2-a9fa-5658a1825590   image  4    rejected    0.8500   True   0.3078  blank or solid color
4d0e31d7-655c-43f0-8967-9bd293b15cdc   image  5    approved    1.0000   True   0.2993  -
e58947e6-22de-40d8-bcb2-8259eb2ea77f   image  6    rejected    0.8500   True   0.3030  blank or solid color
a71d0f46-5016-403b-9548-3c17c23e7c56   image  7    approved    1.0000   True   0.3028  -
3d89b0ef-a859-4a34-a110-b3310cbf6fa7   image  9    rejected    0.8500   True   0.3125  blank or solid color
ecaeefc6-d18f-49b7-a924-eae2e95776a8   image  10   approved    1.0000   True   0.2971  -
87486621-355b-418d-82ec-ff4ac6ebaa27   image  11   approved    1.0000   True   0.3463  -
9f6ee9ea-56a1-4ce5-9f7c-a7e9625fa460   image  12   approved    1.0000   True   0.3030  -
cec54989-dacf-4b70-8ad9-18de1334de84   image  13   rejected    0.8500   True   0.3074  blank or solid color
8431cc40-1e57-473e-be17-2745308526d0   image  14   approved    1.0000   True   0.2996  -
a3c48700-b895-44a2-9d53-8ebbc60cc577   image  15   rejected    0.8500   True   0.3459  blank or solid color
5af48ff2-b40c-494f-ba3d-85dbef309469   image  16   approved    1.0000   True   0.3604  -
fbbcefe0-1bc1-4081-babf-14f55685d86e   image  17   approved    1.0000   True   0.3102  -
3e133509-eae7-45e0-ba06-f1c3b4bc0715   video  1    rejected    0.5000  False      n/a  Unsupported video codec: mpeg4
3bc54e58-3901-440c-a2ea-8f89bbc7476c   video  3    flagged     0.7222  False      n/a  Resolution + duration deviation
8b39d4f5-aa58-41a3-badb-927077942e4e   video  8    rejected    0.5000  False      n/a  Unsupported video codec: mpeg4

verdicts : {"approved": 10, "flagged": 1, "rejected": 8}
```

**10 approved / 1 flagged / 8 rejected**, against the original run's uniform `flagged` at a
perfect 1.0. Every number is earned.

**And here is the caveat, stated plainly rather than buried.** Ten of these are
**approved** and several of them are visually wrong — scene 0's whiteboard reads
`2? x 23.14`, scene 3 is an equation card whose maths is nonsense. **CLIP cannot do
arithmetic.** It is measuring *"is this a teacher at a whiteboard"* and *"is this an
animation of a multiplication process"*, and by those questions the images are faithful to
prompts that should never have been written. **No scorer available to this fleet catches
deformed on-screen text.** That is not a gap in this implementation; it is why Task 4's
rule (a) forbids requesting the text at all. A gate that is real is not a gate that is
omniscient, and pretending otherwise would be the same failure in a new costume.

**The tool is committed and its writing mode is HELD.**
`dev/workpackages/WP-44-rescore-reference-run.py` — dry run by default, `--write` persists
via `POST /api/v1/quality-scores` (INSERTs, deletes nothing). WP-44 ran the dry run and
did not run `--write`. Every submitted record carries `checks_missing`, `check_coverage`
and `quality_score_complete`, so a reviewer can tell what each number measured.

One row **was** written — a single genuine verdict for asset `737238b0`, as the deliberate
probe that closes register instance 25 on observed evidence (§3.5). It is real data and it
stays.

---

## 8. Tests

### 8.1 What was added

| Module | Tests | What it pins |
|---|---|---|
| `ivgs-workers/tests/test_wp44_quality_gate.py` | 23 | the free +0.15 cannot return; forced-`ImportError` numpy reports MISSING not passed; the first run's exact condition; missing checks cap at flagged; a complete pass can still approve; renormalisation equals the old sum at full coverage; the service token on the scoring call; the stage-3 seam |
| `ivgs-workers/tests/test_wp44_video_validator.py` | 16 | real ffmpeg-built MP4s; a still is REJECTED; a missing ffmpeg is a MISSING check; duration-vs-expected; silent clips not penalised; the validator is actually wired in |
| `ivgs-workers/tests/test_wp44_animation_input_guard.py` | 14 | the detector on two real frames; the three-outcome contract; guard ordering before GPU work; the named error and its message |
| `ivgs-workers/tests/test_wp44_storyboard_prompt_rules.py` | 45 | all four rules × all three templates, the evidence quotes, the templates still rendering through stage 2's own binder, and the held SQL matching the seed files |
| `ivgs-api/tests/test_wp44_quality_scores_and_clip.py` | 13 | the route is not a 404; the verdict round-trips through `/quality/flagged`; the missing-check record survives into `scoring_details`; 503-with-no-score on every scorer-absent path; RBAC |

**111 new tests. All green.** Plus 2 added to `test_video_gen.py` (a rejected clip is not
uploaded) and 1 to `test_wp46_animation.py`.

They are deliberately written against the **real** validators with real pixels and real
frames, not against mocks of them. The old code passed every test it had; none of them
ever asked what a score means when a checker is missing.

**Skips are honest.** The 10 ffmpeg-dependent tests SKIP on node-01's host, which has no
ffmpeg, with the reason stated — *"a check that cannot run must never report itself as
having passed, which is WP-44's whole subject"*. They **run and pass inside the workers
image**, which is the environment that matters:

```
in ghcr.io/brucecostello2/ivgs-workers:v5.10.0-quality
  51 passed, 45 skipped        (the 45 are the repo-level prompt module, see below)
```

The prompt-rules module reads from both `ivgs-workers/` and `ivgs-api/` and so is
repo-level by construction; it skips inside the workers image (where no `ivgs-api/` tree
exists) with that reason stated, rather than erroring 33 times or appearing to have run.

### 8.2 A regression I introduced, caught by an existing test

Adding fields to `SceneImageResult` / `SceneVideoResult` / `SceneAnimationResult` broke
`tests/temporal/test_wp41_payload_shapes.py`, which asserts the Temporal payload mirrors
match the Celery result models field-for-field. **That is WP-41's test doing exactly what
it was built for.** The three mirrors in `temporal_pipeline/payloads.py` are updated in the
same commit as the models. Confirmed green.

### 8.3 Full suite — two runs, as budgeted

```
run 1:  72 failed, 1447 passed, 63 skipped, 77 errors   (235.67s)
run 2:  same failure set, grouped by file
```

The suite is **red on `main` before this package**. Rather than spend the third run I was
not budgeted, I established the delta by targeted before/after comparison over **every
module that failed**, stashing the working tree to `5a9fd23` for the baseline:

| Module set | HEAD (5a9fd23) | WP-44 tree | Delta |
|---|---|---|---|
| stage2, quality_validator, dlq_service, video_gen, wp46_animation, health, projects, retry_engine, orphan_cleanup, stage1, fallback_chain, talking_head, scheduler | **25 failed**, 164 passed | **25 failed**, 166 passed | **0 new**, +2 passing |
| compliance_scanner, auth_integration, gpu_integration, projects_integration, stage3, wp41_payload_shapes, health | **42 failed** | **42 failed** | **0 new** |

`comm` over the sorted `FAILED` lists returns **empty** in both directions. **WP-44
introduces no new failures.** The three `wp41_payload_shapes` failures §8.2 describes were
real and are fixed; the comparison above is after that fix.

### 8.4 Pre-existing red, diagnosed and ledgered — P2.45

Five tests in `ivgs-workers/tests/test_stage3.py` are red on `main`, verified at `5a9fd23`
with this tree stashed. Three causes, all drift between the tests and a Stage 3 rewritten
under them: three patch targets naming `_update_scene_asset` (never existed), one naming
`CogVideoXClient` (the module imports the params/enum, not the client), and four calls
passing `flux_client=` / `cogvideox_client=` that the provider-factory rewrite removed.

**I made the three-line deletion, found the rest needs four tests rewritten against the
current signature, and reverted.** Half-repairing a stale module leaves it broken in a
*different* shape, which is worse for the next reader than finding it broken in the
documented one. Ledgered as **P2.45** with the diagnosis, so the work is scoped rather than
rediscovered. Six tests in `test_wp44_quality_gate.py::TestStage3CarriesTheRecord` cover
the WP-44 seam in the meantime — narrower than what `test_stage3.py` claims.

### 8.5 Environment notes

* `pytest-timeout` is declared in `requirements-dev.txt` and **not installed** in `.venv`,
  so `--timeout` is rejected. Unchanged from WP-32's note; the operator installs
  deliberately.
* `Pillow` was already declared in `ivgs-workers/requirements.txt` and missing from
  `.venv`, which is why the first WP-44 test run found no `PIL`. `Pillow`, `numpy` and
  `onnxruntime` are added to `requirements-dev.txt` with the reason, and installed.
* The API suite needs `TEST_DATABASE_URL` pointed at `ivgs_reconciliation_test`; its guard
  refuses anything else, correctly.

---

## 9. Files changed

| File | Why |
|---|---|
| `ivgs-workers/utils/image_validator.py` | rewritten: `ClipStatus`, renormalised scoring, `checks_missing`/`check_coverage`/`quality_score_complete`, missing→flagged, auth on the scoring call |
| `ivgs-workers/utils/video_validator.py` | rewritten: same honesty contract + `measure_frame_distinctness`, `expect_audio`, duration-vs-expected |
| `ivgs-workers/utils/person_detector.py` | **new** — YOLOv10m person detection, three-outcome contract |
| `ivgs-workers/utils/quality_reporting.py` | **new** — one submission path for image/video/animation, status-checked |
| `ivgs-workers/tasks/stage3_images.py` | one `_quality_fields` helper at all three constructors; submission ungated and status-checked; token threaded |
| `ivgs-workers/tasks/video_generation_task.py` | the validator runs; rejected clips are not uploaded; verdict submitted |
| `ivgs-workers/tasks/animation_generation_task.py` | the input guard; the validator; `reference_person_check` on the result |
| `ivgs-workers/temporal_pipeline/payloads.py` | the three mirrors, in step with the models |
| `ivgs-workers/requirements.txt` | `numpy==2.2.1`, `onnxruntime==1.20.1`, each with its reason |
| `ivgs-workers/prompts/stage2_{system,user}.j2` | the four rules |
| `ivgs-api/seed/default_prompts/{storyboard,animation}_generation.j2` | the four rules; the animation branch described correctly |
| `ivgs-api/app/api/v1/clip.py` | **new** — the proxy, with the decision recorded in its docstring |
| `ivgs-api/app/api/v1/quality.py`, `schemas/quality.py`, `services/quality_service.py`, `api/v1/__init__.py` | `POST /quality-scores` |
| `ivgs-clip-scorer/` | **new** — the service, its Dockerfile, its weight-baking script |
| `ivgs-infra/docker-compose.quality.node05.yml` | **new** — the node-05 overlay, own project, `pull_policy: never` |
| `ivgs-infra/docker-compose.node01.yml` | `IVGS_CLIP_SERVICE_URL` on the API only |
| `dev/CLAUDE.md` | §11.1, the AD-04 seam-direction ruling |
| `docs/IVGS_v5_Addendum_AD-02_Draft4_…_DRAFT.md` | **new** — the node-05 amendment, document only |
| `dev/workpackages/WP-44-storyboard-prompt-v3.sql` | **new** — HELD |
| `dev/workpackages/WP-44-rescore-reference-run.py` | **new** — `--write` HELD |
| `OUTSTANDING_WORK.md` | P2.41 CLOSED, P2.43 updated, P2.45 added |
| `dev/workpackages/reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` | instance 24 CLOSED, instance 25 added and CLOSED |
| `requirements-dev.txt` | Pillow / numpy / onnxruntime |

---

## 10. Decisions needed

| | Decision | Recommendation |
|---|---|---|
| **D-1** | **Register the CLIP scorer in MBCP for provenance symmetry?** Every other model influencing a pipeline outcome is an AD-01 store row; a CLIP score now decides approve/reject. But the store is keyed on MBCP's nine-stage taxonomy and image-text scoring is not one of them, and there is no MBCP certification for `clip-vit-base-patch32` to attest to. | **Raise as a taxonomy question with MBCP before creating a row.** Do not invent an attestation. §3.7 |
| **D-2** | **Run `WP-44-storyboard-prompt-v3.sql`?** The file templates are corrected; the row Stage 2 actually receives is not. Until it runs, the deployed guard (Task 5) will *fail* the equation-card scenes the old row keeps producing rather than render them badly. | **Run it.** Guarded, one transaction, deletes nothing, dry-run verified. §5.3 |
| **D-3** | **Run `WP-44-rescore-reference-run.py --write`?** Purely additive; gives the review queue its first real content. Against: the 19 assets belong to a run whose storyboard is being replaced. | **Run it** if the reference project stays a reference; skip it if the project is to be regenerated from a corrected storyboard, in which case the fresh run populates the queue itself. §7c |
| **D-4** | **Adopt AD-02 Draft 4?** node-05's spec role has never been what it does. | Review the draft; it carries four sub-questions of its own, including where §11.1's unimplemented safety classifier lives. §7b |
| **D-5** | **`IVGS_SERVICE_TOKEN` is unset fleet-wide** and resolves to the `shared/config.py` default `"dev-service-token"` on both the API and the workers. Not introduced by WP-44 and not in its scope, but it is the credential now guarding the scoring route. | Set a real value in `ivgs-infra/.env` and the per-node `.env` files. Worth its own small package. |

---

## 11. Push block — count-gated, for ALL held commits

**HELD: 7 commits.** Nothing has been pushed. I have not run `git push` in this package.

```
842caf7  fix(wp-44): the gate stops paying a missing checker, and numpy stops being optional
ce708c4  feat(wp-44): a CLIP model that exists, and the two routes the gate was talking to
da61fe5  feat(wp-44): video assets get a validator that runs, and animation gets an input guard
f39a777  fix(wp-44): the storyboard learns the four rules this week's runs paid for
da6f1a5  test(wp-44): what a quality score is allowed to claim, pinned
26cdc02  docs(wp-44): the report, the AD-02 draft, and two register entries closed
<HEAD>   fix(wp-44): a malformed image is not an unavailable scorer
         (this commit; a commit cannot contain its own hash — `git log --oneline -1`)
```

The last commit lands after the report's own, because the defect it fixes was found by
probing the route the report describes. The report is amended in that commit rather than
left stale.

Run this as one block. It refuses unless the count is exactly what this report claims.

```bash
git fetch origin main && \
EXPECTED=7 && \
ACTUAL=$(git rev-list --count origin/main..HEAD) && \
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git log --oneline origin/main..HEAD && \
  git status --short && \
  git push origin main
fi
```

---

## 12. Exit gate

| Clause | Status |
|---|---|
| numpy in the workers image; blank/noise checks actually run | **MET** — verified inside all four deployed workers; rejects 6 of 16 real assets |
| the free +0.15 removed; `clip_score: "unavailable"`; never None-that-reads-as-scored | **MET** — negative gate run inside the image; string verified through the JSON round trip |
| a `quality_score` computed with checks missing says which | **MET** — `checks_missing` / `check_coverage` / `quality_score_complete` on the result, in the submitted record, and in the database |
| a real CLIP service on node-05, additive | **MET** — own compose project; telemetry pair untouched |
| the contract stage 3 speaks, honoured; choice justified | **MET** — proxy at `/api/v1/clip/score`; §3.2 |
| real scores flow into stage-3 results end to end | **MET** — proven inside the deployed worker against banked images; §3.4 |
| VRAM/latency reported | **MET** — 1040 MiB (2.1%), 21 ms compute, 130 ms end-to-end; §3.6 |
| MBCP registration raised, not blocked on | **MET** — D-1 |
| video validator: duration, distinctness, corruption; honest scores | **MET** — live on three real assets; §4.3 |
| stage-2 templates carry all four rules, with tests | **MET** — 45 tests over three templates |
| animation input guard with a named error, tested both ways | **MET** — live on real frames; §5.5 |
| AD-04 doctrine stated; P2.41 closed | **MET** — §7a |
| AD-02 amendment drafted under change control; document only | **MET** — §7b; P2.43 stays open pending review |
| the 18 review items: decided and reported, nothing deleted silently | **MET** — premise corrected, decision made, full dry run, tool held; §7c |
| workers `v5.10.0-quality` on all four nodes | **MET** — image ID `138250c69a60` on all four |
| scorer on node-05 only | **MET** |
| api `v5.10.0-quality` on node-01 | **MET** |
| every existing engine untouched | **MET** — verified by uptime and by unchanged `IVGS_LATENTSYNC_TAG` |
| full suite at most twice | **MET** — twice; delta established by targeted comparison |
| commit and HOLD | **MET** — 7 commits, nothing pushed |
