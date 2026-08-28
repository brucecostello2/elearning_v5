# WP-IVGS-09e — the mpeg4 was never ours, and RUN-2's draft is unblocked

**Report · 2026-08-28 · written as the work proceeded.**

⛔ **The primary deliverable is `OUTSTANDING_WORK.md` §RC-N.** This file says what was done,
what was measured, and — at length, because two of them matter — **what was not**.

---

## §1 Headline

| Task | Result |
|---|---|
| Measure where mpeg4 arises, with file:line | ✅ **Three hops, none of them our code** — §2 |
| Fix at the source: h264 / yuv420p / faststart | ✅ **Pinned in our own call**, not inherited — §3 |
| Do NOT widen the allowlist, do NOT transcode | ✅ **Neither touched.** `video_validator.py:85` unchanged |
| Rebuild + redeploy under the deploy standard | ✅ **`DEPLOY VERIFIED`** — ⚠ but **not from the canonical Dockerfile**, and that is a defect: §5 |
| Re-render scene 11 via the normal per-scene path | ✅ **Asset `ec6fedcd`**, h264, validator `is_valid=True` |
| Rerun `prototype_draft` **to a draft asset** | ✅ **`c9cabd58`** — 1280×720, 136.61 s, **14/14 scenes** |
| Zero new failures | ✅ **All three suites byte-identical to their HEAD baselines** — §6 |

**Held: 5** (RC-N6…RC-N10).

---

## §2 The measurement — the encode is a vendored default, and we were on a branch nobody chose

Our only encode statement was **one line that names no codec**:

    ivgs-workers/servers/cogvideox/server.py:120
      export_to_video(frames, str(out_path), fps=req.fps)

Everything downstream of it is diffusers'. Measured **inside the running `cogvideox-pilot-1`
image**, not read from a changelog:

    diffusers/utils/export_utils.py:168   if not is_imageio_available():
                             :176           return _legacy_export_to_video(...)
                             :130           fourcc = cv2.VideoWriter_fourcc(*"mp4v")

`mp4v` is MPEG-4 Part 2 == **`mpeg4`**. So the answer to *"is it our code?"* is **no** — and the
order's branch applies: say so, and pin the encode explicitly in our call.

⛔ **The more useful finding is WHY we were on that branch.** `is_imageio_available()` measured
**`False`**:

| Package | In image | Satisfies `is_imageio_available()` |
|---|---|---|
| `imageio-ffmpeg` 0.6.0 | ✅ `requirements.txt:16` | ❌ — it is only the ffmpeg **binary wheel** |
| `imageio` | ❌ **absent** | — this is the one the check wants |
| `opencv-python-headless` 4.13.0.92 | ✅ | (this is what the fallback then used) |

`diffusers` 0.38.0. **One absent transitive dependency silently chose the codec for the entire
pipeline**, down a path whose own docstring calls itself deprecated.

---

## §3 The fix — named, not inherited

`export_to_video` is **no longer called at all**. `server.py` now carries `encode_h264()`, driving
`imageio_ffmpeg.write_frames` with every parameter composition depends on stated explicitly:

    codec="libx264"            -> ffprobe codec_name "h264"
    pix_fmt_out="yuv420p"
    output_params=["-movflags","+faststart","-profile:v","high","-level","4.0"]
    macro_block_size=16        -> odd dimensions padded; yuv420p cannot do odd

⛔ **`pip install imageio` was considered and deliberately rejected.** It *would* have stopped the
mpeg4 — the other branch's default is h264 — but by accident: one dependency resolution away from
silently reverting, and with pix_fmt and faststart still left to a library default. A codec that
is correct by coincidence is the thing that produced this bug.

Two smaller things came with it:

- **The producer now refuses to ship what stage 7 would reject.** `encode_h264` ffprobes its own
  output and raises if `codec_name != "h264"`. Cost of a wrong codec drops from *a whole draft* to
  *one render*.
- **A latent vendored bug is not inherited.** diffusers multiplies **any** ndarray by 255 assuming
  float 0..1, which destroys an already-uint8 frame. `_frames_to_uint8_rgb` branches on dtype.

**The allowlist was not widened and composition does not transcode.** `video_validator.py:85`
`("h264","h265","hevc","vp9")` is untouched. It was right all along.

Verified before rebuilding, in the running image, on both the normal and the odd-dimension path:
`codec=libx264 pix_fmt=yuv420p`, atoms `[ftyp, moov, free, mdat]` — **moov first**.

---

## §4 Deploy — and the one trap that caught me

Image `cogvideox-h264-1`, node-03, service **`cogvideox-server`** (not `celery-worker`;
node-03's worker is `cogvideox-worker` — `dev/CLAUDE.md §6.2`), `--no-deps`, **stderr never
redirected**, then asserted on the RUNNING container:

    DEPLOY VERIFIED [192.168.1.92]: ivgs-cogvideox-server-node03
      -> ghcr.io/brucecostello2/ivgs-workers:cogvideox-h264-1

`/app/server.py` sha256 inside the running container matches node-01's byte for byte, and the
three remaining `export_to_video` strings are all comments.

⚠ **The missing-`cd` trap fired, exactly as `dev/CLAUDE.md §6.1a` predicts.** My first build ran
without `cd /opt/ivgs` and printed `unable to prepare context: path ... not found` — **visible only
because stderr was not redirected.** I then re-sent the same command twice more with `pwd &&`
where `cd /opt/ivgs &&` belonged before writing it to a script. Three wasted attempts; the
standard caught all three loudly rather than exiting 0 on a no-op.

Every file crossing to node-03 went with a **sha256 gate** (`server.py`, `Dockerfile.serverpatch`,
`docker-compose.node03.yml`) — all three matched.

---

## §5 ⛔ The deploy is NOT from the canonical Dockerfile, and that is a real defect

**`Dockerfile` cannot build this image today. Measured, not assumed.**

    Dockerfile:59   pip install --pre torch torchvision torchaudio
                    --index-url https://download.pytorch.org/whl/nightly/cu128

1. **Run as written it fails outright** — unpinned `--pre` against a *moving* nightly index:
   `ERROR: Cannot install torch and torchvision==0.27.0.dev20260407+cu128 because these package
   versions have conflicting dependencies`. It was only ever going to work on the day it was
   first run.
2. **Pinning to the known-good set does not rescue it.** The running image carries
   `torch 2.12.0.dev20260407+cu128` / `torchvision 0.27.0.dev20260407+cu128` /
   `torchaudio 2.11.0.dev20260407+cu128`, and **`dev20260407` has been garbage-collected from the
   index** — checked directly; the nightly is gone upstream.

The only way to build from `Dockerfile` today is to move torch to a **current** nightly — swapping
the CUDA/torch stack under a **working Blackwell sm_120 server**, the exact fragility that file's
own header documents, **to ship a change to one Python file**. That trade is wrong and was not
made.

So the deploy used a **pinned-base derived layer**, `Dockerfile.serverpatch`:

    FROM ghcr.io/.../ivgs-workers@sha256:4eb9b82e...   <- IMAGE ID, cannot drift
    COPY server.py /app/server.py

**This is a workaround around a defect, not a fix for it.** It is recorded in the tracked tree, in
that file's header, in `Dockerfile`'s own comment block, and as **RC-N6**. It is not buried.

---

## §6 Evidence — and it is end-to-end, not a unit test

```
LIVE RENDER, scene 11 (208a8ec2, the only video_clip), via POST /scenes/{id}/regenerate -> 202
  cogvideox-server: encoded 81284d8f-....mp4: 720x480 @8fps
                    codec=libx264 pix_fmt=yuv420p faststart=yes (probed: h264)
  worker:           video_validated decision=flagged distinct=1.0
                    <- NO video_validation_rejected. It uploaded.

STORED ASSET ec6fedcd  (fetched from SeaweedFS; sha256 == assets.content_hash)
  codec_name=h264  pix_fmt=yuv420p  profile=High  720x480
  atoms [ftyp, moov, free, mdat]   <- moov BEFORE mdat: faststart real
  VideoValidator: is_valid=True  errors=[]
    was, three runs running: ["Unsupported video codec: mpeg4 (allowed: h264,h265,hevc,vp9)"]

MANIFEST dcc868ec — all 14 scenes: audio,background      scenes_without_background = []
    was, at RC-M3:                                       scenes_without_background = [11]

DRAFT ASSET c9cabd58-378e-4c51-b81d-9070edb46946     <- THE ACCEPTANCE
  /ivgs/final/9c29b1d1-.../draft_720p_en-US.mp4
  1280x720  30fps  h264 + aac 48kHz stereo  136.61s  3,461,078 bytes
  scene_count 14  scenes_composed 14  scenes_failed 0  corruption 7/7
  sha256 b59e06e3... == assets.content_hash
```

Scene 11 was **read by eye** at t=120 s in the composed draft (its window is 115–125 s): real
content, pillarboxed 720×480 into 1280×720 — not black, not a dropped scene.

⚠ **One thing the eye also saw, and no gate could:** the clip's on-paper text is model gibberish.
That is a CogVideoX quality matter, not a codec or composition one, and it is out of this order's
scope — but *"stage 7 accepted it"* is not the same claim as *"it is good"*.

**Tests — each suite run twice, once with the change and once stashed at HEAD:**

| Suite | With change | HEAD baseline | Delta |
|---|---|---|---|
| `ivgs-workers` | 18F / 935P / 52S / 15E | 18F / 935P / 52S / 15E | **0** |
| `ivgs-api` | 225F / 574P / 1547E | 225F / 574P / 1547E | **0** |
| `ivgs-scheduler` | 15F / 52P | 15F / 52P | **0** |

**Zero new failures — measured against a same-environment baseline, not against a remembered
number.** ⚠ The absolute api/scheduler figures are far worse than WP-IVGS-08's `1406 / 0` and
`52 / 0`; that is my invocation environment (`TEST_DATABASE_URL` → `ivgs_reconciliation_test`,
which is migrated to 0044 but is not how those figures were produced), **not** a regression. The
delta is the claim; the absolute is not.

**Fleet after:** 43 containers across nodes 01–04, **zero unhealthy**.

---

## §7 ⛔ HELD — 5 items, each with evidence

| id | What | Why held |
|---|---|---|
| **RC-N6** | The image cannot be rebuilt from its own Dockerfile (unpinned nightly; the known-good wheels garbage-collected) | Needs a GPU window and an sm_120 re-verification. Not a drive-by edit |
| **RC-N7** | `POST /jobs/{id}/resume` dispatches stage 7 with `scenes=[]` — the manifest is looked up by the **new** job id, which has none | Pre-existing; order said *"Nothing else"*. **I caused one live failed job (`a6e5f2d1`) exercising it** — see below |
| **RC-N8** | The server accepts `width`/`height` and **ignores them**; the client reports the **requested** size as if produced (854×480 asked, 720×480 made) | Warning-only, composes. Out of scope |
| **RC-N9** | Every CogVideoX clip is permanently `flagged`: `fps=8` requested vs `allowed_fps=(24,25,30,60)` | Warning-only, composes. Out of scope |
| **RC-N10** | RC-M7 DLQ write side still absent — `dlq_routing_api_error 405` fired again at 22:08:57 | Explicitly excluded by the order |

### ⚠ One failed job row I created, stated plainly

After the draft already existed, I called `POST /jobs/4bf3ff53/resume` to rerun `prototype_draft`
explicitly. It minted job **`a6e5f2d1`**, which **failed** at stage 7 on `scenes=[]` (RC-N7).

**That call was unnecessary** — the per-scene regen dispatch had already carried the pipeline
through to `prototype_draft` and produced `c9cabd58` at 21:59:36, nine minutes earlier. I did not
check the regen job's checkpoints before reaching for resume.

The failure is **not** caused by the codec change (it is a manifest-lookup defect on a path my
change does not touch), but it **is** a failed row that did not exist before I started, and the
order said *zero new failures*. Recorded rather than left for someone else to find.
