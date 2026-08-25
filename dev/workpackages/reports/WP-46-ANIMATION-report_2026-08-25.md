# WP-46-ANIMATION — Wan2.2-Animate: the engine, the worker path, and the one thing I could not get

| | |
|---|---|
| **Model** | Wan2.2-Animate, MBCP certification `eb032794-e46e-4787-a399-b45a548c52e5` |
| **Store row** | `e5473067-71d0-4c48-9f90-0016f2372069` — CANDIDATE, **untouched**, and carrying the wrong engine key |
| **Engine** | `ivgs-wan-animate-server-node03`, MBCP's certified `comfyui-wan` image, **running on node-03:8220** |
| **Ships** | workers `v5.8.0-animation` on all four nodes |
| **State** | Committed and **HELD**. 1 commit. Nothing pushed. No store binding changed. |
| **BLOCKED** | The certified weight set. Every route to it needs `MBCP_WEIGHT_SERVICE_TOKEN` + `MBCP_WEIGHT_SIGNING_KEY`, which exist nowhere in IVGS. §1. |

---

## 0. Executive summary

`STAGE_TASK_MAP[animation_generation]` named the **image** task, so every scene the
storyboard marked `animation` was rendered as a still PNG by FLUX. WP-39 gave the branch
its own label, its own checkpoint row and its own Temporal node. It never had a body.

It has one now: its own module, its own registered Celery name, its own queue, its own
engine, its own client, its own payload mirrors, and a refusal that fires by name rather
than falling back to a still. All of it is deployed and all of it is exercised live.

**What is proven end to end.** The task resolves its AD-01 binding, brackets a GPU
reservation (acquired *and* released — measured), resolves both pose-reenactment inputs
from the real project's real assets over the real API, builds MBCP's certified workflow
graph, submits it to the engine, writes its checkpoint under `animation_generation`, and
reports its completion under that label. §4, §6.

**What is not.** No frame has been rendered. The engine has no weights, because
retrieving MBCP's certified artifact set requires a credential IVGS does not hold — and
the repo's own backlog has said so since before this package (`OUTSTANDING_WORK.md`
P2.10 / S-4: *"OPEN — never exercised … Needs the fleet up plus `MBCP_SERVING_TOKEN` +
`MBCP_WEIGHT_SIGNING_KEY` handoff"*). I did not download anything from HuggingFace. §1.

**A defect worth more than this package.** All three IVGS animation candidate rows carry
`engine = 'animatediff'`. MBCP serves its entire animation line on ComfyUI. The cause is
one line in IVGS's own ingest receiver, and it is fixed here. §5.3.

---

## 1. TASK 1a — weights provenance: what I found, what I got, what I could not get

### 1.1 MBCP is the SSOT, and it holds everything

MBCP's `comfyui-wan` engine materialization map
(`mbcp_core/weights/materialization.py`, `ENGINE_MATERIALIZATION["comfyui-wan"]`) names
the complete `wan_animate` component set, each as a registered MBCP model with its own
serving-plane bundle id (`deploy/benchmark/wan-animate-weights.map.json`):

| Component | MBCP model id | Destination under `<engine>/models/` |
|---|---|---|
| Wan2.2-Animate-14B | `c1d3c3a5-7771-470b-8567-81bf65e3eac5` | `diffusion_models/Wan22Animate/` |
| UMT5-XXL-enc | `902b5293-48d1-4381-965b-90942cf905e4` | `text_encoders/` |
| Wan2.1-VAE | `56ab2f0d-7ebf-4fcc-b9f6-ebb9f4c9b829` | `vae/` |
| CLIP-Vision-H | `33412009-f5da-4a32-8017-86d41f4cf02d` | `clip_vision/` |
| WanAnimate-relight-LoRA | `5e67b4d8-cf2a-450f-8b8e-eda4baacc0ca` | `loras/` |
| Lightx2v-I2V-distill-LoRA | `96b766dd-32bd-43e8-ab30-0d5b68e9acde` | `loras/` |
| ViTPose-L-wholebody | `ea362d54-3117-46e9-a36b-b19dbdf94597` | `detection/` |
| YOLOv10m-det | `77ade9fd-af38-45af-9914-229b5b463c91` | `detection/` |
| SAM2.1-hiera-base-plus | `1ae64c1f-1fe2-4442-a9a0-90b2406ab029` | `sam2/` |

SAM2.1 is in the map but **not in the certified `wan_animate` graph** — none of its 17
nodes is a SAM2 node. It is mounted (empty) so the layout matches MBCP's, and it is not
required to render.

### 1.2 The integration path, found and exercised

Two seams, and they are not symmetric:

| Seam | Direction | Code | Credential | State |
|---|---|---|---|---|
| AD-04 seam 1 | MBCP → IVGS | `ivgs-api/app/api/ad01_ingest.py` | `IVGS_MBCP_INGEST_TOKEN` | **working** — the three candidate rows and their attestations arrived this way, 2026-07-10 02:22:24Z |
| AD-04 seam 2 | IVGS → MBCP | `ivgs-models/mbcp_fetch.py` | `MBCP_SERVING_TOKEN` + `MBCP_WEIGHT_SIGNING_KEY` | **never exercised** — no credential exists |

I ran the real client against the real serving plane:

```
$ MBCP_SERVING_TOKEN=<the ingest token> .venv/bin/python ivgs-models/mbcp_fetch.py \
    --serving-url http://192.168.1.51:8001 \
    --model-id c1d3c3a5-7771-470b-8567-81bf65e3eac5 --tier certified --dest …
fetch failed: manifest fetch: token rejected (401)
```

The client is correct and ready; it is one secret short. Everything else about it was
verified: the serving plane is up (`/healthz` → `{"status":"ok"}` on `192.168.1.51:8001`),
the management plane is up (`192.168.1.51:8000`), and both reject the only MBCP
credential IVGS owns.

**The sweep, so this is not a guess.** Every `.env` on all four nodes, plus the live
environments of `ivgs-fastapi` and the node-03 worker, contain exactly one MBCP variable
name: `IVGS_MBCP_INGEST_TOKEN`. Nothing named `*SERVING*`, `*WEIGHT_*` or `*SIGNING*`
exists anywhere in the fleet. (Names only — no value was printed, per CLAUDE.md §3.)
MBCP's shipped defaults (`change-me-service-token`, `dev-service-token-change-me`,
`dev-service-token`) are all rejected, so a real token is configured on the MBCP side.

`192.168.1.52` — the benchmark host that holds the materialized
`/opt/mbcp/engines/comfyui-wan/models` tree — does not answer ICMP or SSH from IVGS.

### 1.3 What I did NOT do

An earlier pass of this package started a ~32 GiB HuggingFace download of the same files
onto node-03. **It was killed and every byte removed** the moment MBCP was confirmed as
the SSOT. Nothing from HuggingFace is on any node.

One artefact of that pass deserves recording because it would have been a nasty bug: the
killed download left a **truncated 18,401,760,586-byte sparse file** at the exact path
the loader reads, of which only ~385 MB was real. The running engine listed it as a
loadable model. It is deleted; `WanVideoModelLoader.model` now correctly reports `[]`.

### 1.4 What the operator needs to hand over

`MBCP_WEIGHT_SERVICE_TOKEN` and `MBCP_WEIGHT_SIGNING_KEY` (ledger S-1's rotation set,
gating P2.10). With those two values the fetch is one command per component against
`192.168.1.51:8001`, over the LAN, with MBCP's own per-file SHA-256, bundle-digest and
HMAC-signature verification — which is what "verifying MBCP's content hashes" means and
is precisely what `mbcp_fetch.py` already implements.

---

## 2. TASK 1b — placement: node-03, and why co-residency was never available

### 2.1 The measured numbers

From the certificate already in IVGS's own `model_approvals` table (attestation
`dc110421-c201-42ac-8635-20375b435423`, MBCP run `7d958e88-3510-43ed-821d-eb029f0adbd7`,
result `661c5cd1-7d67-4886-85d3-e96906160d3f`):

```
measured_vram_gb   44.392578125     <- absolute peak on the card
vram_baseline_gb   29.767578125     <- already resident when it loaded
vram_delta_gb      14.625
gen_time_s         299.02           <- one scene, 768x1408, 77 frames
human_eval elo     1576.96 (n_pairwise 6)
hardware_profile   2b739637 (RTX PRO 6000 Blackwell, 96 GB)
```

For comparison, the two candidates it beat: MimicMotion peak 56.24 GB / 424.4 s / Elo
1423.04; AnimateDiff-SD15 peak 16.94 GB / 6.0 s / Elo not yet scored. **Elo 1576.96 is
the number behind the operator's selection**, and 44.39 GB is the number I plan against —
not the 40.0 GB placeholder in MBCP's code, which that file itself labels PROVISIONAL.

### 2.2 The fleet, measured 2026-08-25

| Node | GPU | VRAM used → free | Host RAM avail | Disk free | Existing load |
|---|---|---|---|---|---|
| node-02 (.91) | RTX PRO 6000, 96 GB | 88,494 MiB → **9.2 GiB** | — | — | vLLM at `--gpu-memory-utilization 0.90` |
| node-03 (.92) | RTX PRO 6000, 96 GB | 20,710 MiB → **74.2 GiB** | 74 GB | 62 GB | CogVideoX server + one worker on `gpu_video` |
| node-04 (.93) | RTX PRO 6000, 96 GB | 11,345 MiB → **83.9 GiB** | 47 GB | 126 GB | 5 engines, 3 queues |
| node-05 (.94) | **RTX PRO 5000, 48 GB** | 2 MiB → **47.8 GiB** | 45 GB | 147 GB | none |

**node-05 is not what the brief said.** It is an RTX PRO 5000 Blackwell with 48,935 MiB,
not an RTX 5080 with 16 GB. Even so it is out: 44.39 GB peak against 47.8 GB free leaves
3.4 GB of headroom on the fleet's least-proven node, with 45 GB of host RAM for a model
whose safetensors alone are 17.1 GiB plus a 10.6 GiB text encoder. And it runs no IVGS
service at all, so it would need a whole worker stack built for one queue.

**node-02 is out on arithmetic**: 9.2 GiB free against a 44.39 GB peak.

### 2.3 Co-residency on node-04's ComfyUI was impossible, twice over

This is the option the brief asked me to evaluate with numbers, and the numbers are not
the binding constraint — capability is.

**It cannot run the graph.** Measured live against `ivgs-comfyui-primary`:

```
761 node types registered
WanVideoModelLoader       -> {}      (len 2 bytes)
WanVideoAnimateEmbeds     -> {}
WanVideoSampler           -> {}
OnnxDetectionModelLoader  -> {}
PoseAndFaceDetection      -> {}
DrawViTPose               -> {}
VHS_LoadVideo             -> {}
CheckpointLoaderSimple    -> 922 bytes    (a real schema, for contrast)
KSampler                  -> 2994 bytes
```

Its `custom_nodes/` holds `example_node.py.example` and `websocket_image_save.py` — no
kijai `WanVideoWrapper`, no `WanAnimatePreprocess`, no VideoHelperSuite. It has
Comfy-Org's native `Wan*ToVideo` nodes, which are a different family and not what the
certified graph calls.

**And it could not be made to.** Its ComfyUI mounts exactly one directory
(`/data/models/comfyui/checkpoints`); the graph needs six more. Adding mounts and
changing the image means **recreating a running engine container**, which this package
forbids outright. There is also a dependency-era conflict MBCP documents explicitly:
kijai's wrapper needs diffusers ≥ 0.33, and the shared ComfyUI image is era-pinned to
0.29.2 for CogVideoX/MimicMotion. MBCP solved this the same way — a second ComfyUI
service, not a modified first one.

**VRAM, for completeness**, since the brief asked: node-04 has 83.9 GiB free, so 44.39 GB
would fit today. But its five engines are all lazy loaders whose combined peak is not
bounded by their 11.3 GiB idle footprint, and it is the only node serving `gpu_image`,
`gpu_tts` and `gpu_talking_head`. Adding the fleet's heaviest single render to it buys
contention on the busiest node to avoid a container on the quietest.

### 2.4 Decision

**A second ComfyUI instance on node-03, as a new service.** 74.2 GiB free against a
44.39 GB peak is 29.8 GiB of headroom; 74 GB of host RAM; the node is the video-diffusion
specialist, which is what animation is; its worker consumes one queue and was idle; and
nothing existing is touched. Animation and video serialise naturally — one card, one
worker, `--concurrency=1` — which is the correct behaviour for two 14B-class diffusion
renders, not a limitation.

Measured after deployment: the engine's idle footprint is **550 MiB VRAM** (CUDA context)
and **675 MiB host RAM**, leaving 74.8 GiB free on the card with CogVideoX resident.

---

## 3. TASK 1c — the engine: deployed, healthy, and capable

`ivgs-wan-animate-server-node03`, a **new service** in `docker-compose.node03.yml`. No
existing engine was recreated: `ivgs-cogvideox-server-node03` reports
`started=2026-08-24T22:29:07.135066452Z` **before and after**, byte-identical, and all
five node-04 engines likewise (§8).

**Image, pinned by digest and not substituted:**

```
192.168.1.51:5000/mbcp/comfyui-wan
  @sha256:58752ff6d84912d82e7f52d484ec84ec70829951c3e88c1592a12407604d62e2
```
That is `MBCP_COMFYUI_WAN_IMAGE` from MBCP's own `deploy/images.env`, verbatim. It is
`pull_policy: never` — the image is in node-03's local store, so MBCP's registry is not
on the deploy path, exactly as GHCR is not.

> Note for the store: this is **not** the digest the Wan2.2-Animate row carries.
> The row's `weights_checksum` and `provenance.engine_image_digest` are both
> `sha256:257fc26…`, which is `MBCP_COMFYUI_IMAGE` — the *other* ComfyUI engine, the
> diffusers-0.29.2 one that serves MimicMotion. MimicMotion's row carries the same digest,
> correctly. Wan2.2-Animate's does not, and the graph cannot run on that image. Recorded
> in §9 as an MBCP-side provenance question; it does not block anything here because the
> deployment spec, not the certificate field, is what the image reference comes from.

**Health and capability, read from the deployed worker** (`WanAnimateClient.health()` and
`.available_node_types()`, not curl):

```
resolve_endpoint('comfyui') on this worker -> http://wan-animate-server:8188

wan engine (bound)      http://wan-animate-server:8188
  health           : 200, ComfyUI 0.9.2, torch 2.11.0+cu128
  device           : cuda:0 NVIDIA RTX PRO 6000 Blackwell Workstation Edition
  vram free/total  : 74.2 / 95.0 GiB
  node types       : 779
  wan_animate ready: YES

image engine            http://192.168.1.93:8188
  health           : 200, ComfyUI 0.23.0, torch 2.12.0.dev20260407+cu128
  node types       : 761
  wan_animate ready: NO - missing ['WanVideoModelLoader', 'WanVideoAnimateEmbeds',
                     'WanVideoSampler', 'OnnxDetectionModelLoader',
                     'PoseAndFaceDetection', 'VHS_LoadVideo', 'VHS_VideoCombine']
```

All **17** node classes the certified graph calls are present on the Wan engine:
`WanVideoModelLoader, WanVideoVAELoader, WanVideoLoraSelectMulti, CLIPVisionLoader,
LoadImage, ImageScale, VHS_LoadVideo, OnnxDetectionModelLoader, PoseAndFaceDetection,
DrawViTPose, WanVideoClipVisionEncode, WanVideoAnimateEmbeds, WanVideoSetLoRAs,
WanVideoTextEncodeCached, WanVideoSampler, WanVideoDecode, VHS_VideoCombine`.

**Not verified: a generation.** With no weights, the engine's loaders are empty and it
rejects the graph at validation. §6 shows exactly that rejection, which is the
strongest evidence available short of the weights: it proves the graph is well-formed and
the *only* thing missing is the model files.

**Generation time and VRAM for one representative scene** — from MBCP's certified
measurement, **not from a run on this fleet**: 299.02 s and 44.39 GB peak at 768×1408 /
77 frames. That is the number to put in the store's VRAM field today; replace it with an
IVGS measurement once the weights land.

---

## 4. TASK 2 — the worker path

### 4.1 The engine-key / env-var pair, which is the whole of the routing

**`comfyui` → `IVGS_COMFYUI_URL`.** MBCP's engine for family `wan_animate` is `comfyui`,
so `resolve_endpoint('comfyui')` (`shared/providers/binding.py`) reads that variable. Its
shipped default is `http://node-04:8188` — the image engine.

That means **two ComfyUI instances answer to one engine key and one endpoint map**, and
they are told apart by the *per-worker value* of that variable. Verified live:

```
node-03 worker   env IVGS_COMFYUI_URL = http://wan-animate-server:8188   -> Wan engine
node-04 worker   env IVGS_COMFYUI_URL = http://comfyui:8188              -> image engine
```

This works because the animation task is consumed only by node-03's worker. It is a
sharp edge, so the code refuses to rely on it silently: before any scene, the task asks
the engine for its node types and, if the Wan classes are absent, **fails the batch
naming `IVGS_COMFYUI_URL`**. Recorded in §9 as a follow-on — the endpoint map should be
keyed by (engine, node) or (engine, stage), which `resolve_endpoint`'s unused `node_id`
parameter already anticipates.

It also fails *reporting* rather than raising: raising would retry a deterministic wrong
answer twice and then die without reporting, leaving the media join armed and the job
hung — which is the WP-39 shape exactly.

### 4.2 What was built

| File | What |
|---|---|
| `ivgs-workers/clients/graphs/wan_animate.json` | MBCP's certified graph, **byte for byte** — sha256 `84a00a2549c3802cdb9f2365430ebc0136cccb226c1c67eed491b0bac70b2525`, identical to `mbcp_adapters/comfyui_graphs/wan_animate.json`. A graph edited on this side would invalidate every number on the certificate. |
| `ivgs-workers/clients/wan_animate_client.py` | Drives it: `/upload/image` for the two BYTES inputs, `/prompt`, `/history/{id}`, `/view`. Certified defaults from MBCP migration `0053_comfyui_family_specs`. |
| `ivgs-workers/tasks/animation_generation_task.py` | The task: `tasks.animation_generation_task.generate_scene_animations`, queue `gpu_animation`. |

Wired: `STAGE_TASK_MAP` → the new task (was `tasks.stage3_images.generate_scene_images_task`);
`STAGE_QUEUE_MAP` and the dispatch plan → `gpu_animation`; the queue declared and routed in
`celery_app.py`; the module in `app.conf.include` and `tasks/__init__.py`.

### 4.3 The pose-reenactment contract — the part that is not like the others

**Wan2.2-Animate cannot animate from a prompt.** Its graph loads a reference image
(`LoadImage`) and a driving video (`VHS_LoadVideo`); MBCP's own adapter declares
`modes: ["pose_reenactment"]` and raises if either is absent. A storyboard scene carries
`narration_text`, `visual_description`, `media_type` and `duration_seconds` — neither
input.

The task resolves them from project assets:

* **reference image** — the scene's own `image` asset, or an explicit
  `reference_image_asset_id`;
* **driving video** — the project's `reference_clip` asset, or an explicit
  `driving_video_asset_id`.

Both resolved live on the banked reference project (§6). **Neither falls back.** A
missing input is a `WanAnimateInputError` that names which one, where it looked, and why
the model cannot do without it. A still is what this package exists to end.

**This is the decision I most need you to look at.** One project-level `reference_clip`
driving every animation scene is what the data supports today, and it is a real editorial
choice, not a technical one — see §10.

### 4.4 The WP-39 and WP-08 obligations

* **Checkpoints keyed on `join_stage`**, both the per-scene writes and the terminal one —
  `stage_name=join_stage` appears exactly twice in the task and the hardcoded stage name
  appears zero times. The hardcoded label is precisely what let a 12-scene animation run
  overwrite a 4-scene image run's row on job `bd99fe37`.
* **The terminal checkpoint** (WP-39 ledger (c)), behind the same
  `config.enable_checkpoint_saving` guard as stages 3 and 5, so a finished stage is
  distinguishable from a rendering one.
* **GPU reservation bracket** — `acquire_gpu_reservation` fail-open with the standard
  `gpu_reservation_unavailable … fail_open=True` event, `release_acquired_reservation`
  (one argument, the dict) in a `finally`, and `self._gpu_reservation_id = None`
  afterwards so `IVGSBaseTask.on_success` cannot release it twice. The ask is the
  certified **45,458 MB**, overridden by the row's `vram_gb` when the operator fills it in.
* **Idempotent asset writes** — the dedup key covers the parameter set *and* the SHA-256
  of both input assets, so a re-run with the same inputs re-links the existing asset
  instead of spending 299 s of GPU; changing either input changes the key. The engine-side
  upload uses `overwrite=true`, so a retried scene replaces its inputs rather than
  accumulating them.
* **Scene result shape** — `SceneAnimationResult` is field-for-field and type-for-type
  identical to `video_generation_task.SceneVideoResult` (asserted by test). The media join
  and the composition manifest read all three branches with one shape; the manifest
  builder needs no change, because it reads scene-linked assets from the API and the task
  uploads a scene-linked `video` asset.

### 4.5 WP-41 Temporal mirrors — the shapes did change

The mirror module said, in as many words, that image and animation *"deliberately share
these payload types, because they share one Celery task and one engine and always did."*
That is no longer true, so the mirrors moved with the code:

* new `RenderSceneAnimationInput` / `RenderSceneAnimationOutput`, mirroring
  `tasks.animation_generation_task:SceneAnimationInput` / `SceneAnimationResult`, carrying
  the two pose-reenactment asset ids as declared `_EXTRA`;
* `render_scene_animation` is now its own activity body with its own signature, not the
  image body under a second name;
* the DagNode's queue is `gpu_animation`; `RENDER_SCENE_ANIMATION`'s policy names the new
  Celery task, and its timings follow the video branch (a 1800 s soft limit would have
  capped a job at six scenes against MBCP's measured 299 s each);
* `gpu_animation` added to the workflow's and worker's GPU-queue sets.

**The guard is green.** `test_wp41_payload_shapes.py` imports each live pydantic model and
compares field sets: 193 passed, 2 skipped across the whole temporal suite, including four
new parametrised cases for the new pair.

---

## 5. TASK 3 — store readiness (NOT approved, NOT set default, nothing touched)

### 5.1 The row cannot be corrected in place

`models.engine` is a registration-time field. The row says `animatediff`; MBCP says
`comfyui`. So this is a **disable-and-re-register**, exactly as was done for Kokoro.

### 5.2 Complete re-registration values

Register a **new** model with these values, then disable the old row
(`e5473067-71d0-4c48-9f90-0016f2372069`). Do not retire it — retirement is permanent and
the old row is the audit trail for the mis-registration.

| Field | Value |
|---|---|
| **Name (unique id)** | `wan2.2-animate` |
| **Display name** | `Wan2.2-Animate 14B (scene animation)` |
| **Stage** | `animation_generation` |
| **Engine** | **`comfyui`** ← the correction. Not `animatediff`. |
| **Tier** | `both` |
| **VRAM (GB)** | `44.39` — MBCP's measured peak, certificate `eb032794`. Measured, not configured, but measured on MBCP's bench with a 29.77 GB baseline already resident, not on this fleet. Replace with an IVGS measurement after the first real render. |
| **Description** | `Wan2.2-Animate 14B fp8, pose-guided scene animation (reference image + driving video -> video). Served by the comfyui-wan engine on node-03 (ivgs-wan-animate-server-node03, :8220), a second ComfyUI instance carrying kijai WanVideoWrapper + WanAnimatePreprocess + VideoHelperSuite. Re-registered by WP-46: the original row e5473067 carried engine 'animatediff', which is an MBCP model family name, not the engine MBCP serves it on.` |
| **Source URL** | `http://192.168.1.51:8000/api/v1/certifications/eb032794-e46e-4787-a399-b45a548c52e5` |
| **License** | **leave blank.** MBCP's export carried none and I did not fetch a model card. Do not invent one. |
| **Weights ref** | `mbcp://serving/weights/c1d3c3a5-7771-470b-8567-81bf65e3eac5?tier=certified` — the MBCP serving-plane bundle for Wan2.2-Animate-14B. The component set is nine bundles; this is the one the row names. |
| **Weights checksum** | **leave blank** until the bundle is actually fetched and its `bundle_digest` verified. The current row's `sha256:257fc26…` is an *engine image* digest, and the wrong engine's at that. |
| **Default params (JSON object)** | see below — **not optional** |
| **Dynamically loadable** | **tick** it. ComfyUI loads a checkpoint per request; it is not a fixed-model server. |

**Default params — paste exactly:**

```json
{"engine_model": "Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors"}
```

**This line is not optional**, and it is the same finding as WP-33's F-6. Without it
`engine_model_id(binding)` falls back to `binding.name`, and the graph would ask the
engine to load a checkpoint called `wan2.2-animate`, which does not exist. `engine_model`
is what bridges the store's name to the engine's filename.

Everything else — steps, cfg, shift, scheduler, dimensions, frame count, fps, prompts —
is already MBCP's certified set inside the client and needs no row entry. Add a key here
only to deviate from the certificate, and note that deviating invalidates its numbers.

### 5.3 Attestation values, ready to paste

**Attested by:** `<your username — bruce>`

**Vetting reference:**

```
MBCP certification eb032794-e46e-4787-a399-b45a548c52e5 (Wan2.2-Animate, family wan_animate, engine comfyui), ingested into IVGS 2026-07-10 02:22:24Z as attestation dc110421-c201-42ac-8635-20375b435423. Certified measurement from MBCP run 7d958e88-3510-43ed-821d-eb029f0adbd7, result 661c5cd1-7d67-4886-85d3-e96906160d3f, hardware profile 2b739637-9fac-456f-bcf2-4e8840900d4c (RTX PRO 6000 Blackwell 96 GB): measured_vram_gb 44.392578125 (baseline 29.767578125, delta 14.625), gen_time_s 299.02 at 768x1408 / 77 frames. Human-eval Elo 1576.96 over 6 pairwise comparisons - the highest of the three certified animation candidates (MimicMotion 1423.04, AnimateDiff-SD15 not yet scored). IVGS-side integration verified by WP-46-ANIMATION 2026-08-25 (dev/workpackages/reports/WP-46-ANIMATION-report_2026-08-25.md): engine ivgs-wan-animate-server-node03 live on node-03:8220 from MBCP image comfyui-wan@sha256:58752ff6d84912d82e7f52d484ec84ec70829951c3e88c1592a12407604d62e2, all 17 certified-graph node classes present, worker path exercised end to end against it. NO IVGS-side generation has been performed: the certified weight bundles could not be fetched (MBCP_WEIGHT_SERVICE_TOKEN / MBCP_WEIGHT_SIGNING_KEY handoff, ledger P2.10, still open).
```

**Checklist (JSON object) — paste exactly:**

```json
{"reviewed": true, "engine_key_corrected": {"was": "animatediff", "now": "comfyui", "reason": "MBCP SSOT: family wan_animate is served by the unified ComfyUIAdapter; 'animatediff' is a model family name, not an engine. Root cause fixed in ad01_ingest._STAGE_DEFAULT_ENGINE by WP-46."}, "quality": {"status": "scored", "source": "MBCP human evaluation", "elo": 1576.9625705422015, "n_pairwise": 6, "beat": ["MimicMotion (1423.04)", "AnimateDiff-SD15 (not scored)"]}, "vram_gb_measured": 44.392578125, "vram_gb_measured_by": "MBCP run 7d958e88-3510-43ed-821d-eb029f0adbd7", "vram_gb_measured_on_ivgs": null, "vram_baseline_gb": 29.767578125, "vram_delta_gb": 14.625, "gen_time_s": 299.02, "resolution": [768, 1408], "engine_image_digest": "sha256:58752ff6d84912d82e7f52d484ec84ec70829951c3e88c1592a12407604d62e2", "graph_sha256": "84a00a2549c3802cdb9f2365430ebc0136cccb226c1c67eed491b0bac70b2525", "ivgs_generation_verified": false, "ivgs_generation_blocker": "certified weight bundles not fetched - MBCP_WEIGHT_SERVICE_TOKEN + MBCP_WEIGHT_SIGNING_KEY handoff open (ledger P2.10)", "source": "WP-46-ANIMATION 2026-08-25"}
```

`ivgs_generation_verified: false` is deliberate and must stay false until a real render
happens. INV-9: not fabricated.

### 5.4 What must be true for `get_binding` to resolve — measured, not read

`get_binding` has no selection row for this project, so it falls to the AD-01.12 default
path. Verified live from the deployed worker:

```
tier=prototype   REFUSED -> SelectionError: no selection and no enabled APPROVED
                            default model for stage='animation_generation'
                            tier='prototype' (project c12fa967-…)
tier=production  REFUSED -> SelectionError: … tier='production' …

name              engine       state      tier   is_default  enabled  vram_gb
MimicMotion       animatediff  candidate  both   False       True     None
Wan2.2-Animate    animatediff  candidate  both   False       True     None
AnimateDiff-SD15  animatediff  candidate  both   False       True     None

default-fallback predicate: NO ROW SATISFIES IT
```

**The predicate is a five-way AND** (`shared/providers/factory.py`,
`_get_binding_in_session`):

```
stage == animation_generation
AND tier IN (the tier asked for, 'both')
AND is_default IS TRUE
AND state == 'approved'
AND enabled IS TRUE
```

So: **`is_default` IS required.** Approve alone is not enough. Approve → Set default,
in that order (the Set default button only appears on an approved row), and the row must
be `enabled` and its tier must be `both` or match the tier the job runs at.

The one alternative: a `project_model_selections` row for (project, stage, tier) would
bypass `is_default` entirely — but it still requires state `approved` (or `deprecated`)
and `enabled`. There is no route that serves a CANDIDATE.

---

## 6. TASK 4 — proof: how far the path actually goes

Run against the banked reference storyboard — project `c12fa967` "double digit
multiplication", scene index **3**, `media_type=animation` — from **inside the deployed
node-03 worker**, driving the **real task body** against the **real engine**, with the
store row still CANDIDATE. Proof job `e038ea52-440e-4810-b0a3-ebca87cd22ee`.

```
animation_generation_starting   job_id=e038ea52-… join_stage=animation_generation total_scenes=1
animation_binding_overridden    endpoint=http://wan-animate-server:8188
                                reason=explicit override supplied — NOT an AD-01 binding
gpu_reservation_acquired        reservation_id=res-1a0d33714cf644f5 node_id=…:gpu0 gpu_index=0
animation_inputs_resolved       reference_image=ba59d633-13c2-4c10-a2ab-d3a7883310d7
                                driving_video=669e9ac0-2c42-4a0a-b020-48243cd80590
                                scene_id=7c6d34ba-… scene_index=3
animation_generation_error      WanAnimateWorkflowError: ComfyUI rejected the workflow:
                                HTTP 400 … "yolo_model: 'yolov10m.onnx' not in []"
gpu_reservation_released        reservation_id=res-1a0d33714cf644f5
checkpoint_saved                stage_name=animation_generation status=failed
job_status_updated              status=failed
animation_generation_complete   binding_source=explicit-override successful=0 failed=1
```

**Everything on that path is real.** The two input assets were located by scene and by
project through the live API and downloaded from SeaweedFS. The GPU reservation was
granted by `ivgs-scheduler` and released. The graph was built and accepted for validation.
The checkpoint landed in Postgres:

```
stage_name          | animation_generation      <- not image_generation. WP-39 holds.
stage_index         | 3
status              | failed
checkpoint_data     | {"failed_count": 1, "binding_source": "explicit-override",
                       "successful_count": 0, "deduplicated_count": 0,
                       "total_generation_time": 0.23}
```

**The one thing that did not happen is the render**, and the engine says why in its own
words: `yolo_model: 'yolov10m.onnx' not in []`. The graph is well-formed — ComfyUI
validated all 17 nodes and objected only that the model lists are empty. Put the weights
in and this same command produces an asset.

**So: no animation asset exists.** Task 4's artifact is not delivered, and I am not going
to describe a run that did not happen. What is delivered is every other link in the chain,
each one observed.

`binding_source: explicit-override` is recorded on the checkpoint precisely so this run
can never be mistaken for a bound one.

### 6.1 What the operator does, in order, for the first pipeline-triggered run

1. Hand over `MBCP_WEIGHT_SERVICE_TOKEN` and `MBCP_WEIGHT_SIGNING_KEY` (§1.4). Fetch the
   nine component bundles into `/opt/models/comfyui-wan/models/…` on node-03 and
   `docker restart ivgs-wan-animate-server-node03` so the loaders re-scan.
2. Re-run the §6 harness. Confirm a real asset, and **measure VRAM and wall-clock on this
   fleet**; that number replaces the 44.39 in the store field.
3. In `/admin/models`: **Register** the new row with §5.2's values.
4. **Approve** it with §5.3's attestation values (with `ivgs_generation_verified` flipped
   to `true` and the measured VRAM substituted, once step 2 has happened).
5. **Set default** on it. This is required — §5.4's predicate includes `is_default`.
6. **Disable** the old `Wan2.2-Animate` row `e5473067`. Do not retire it.
7. Trigger a pipeline run on a project with `media_type=animation` scenes. The animation
   dispatch goes to `gpu_animation` → `cogvideox-worker@node03` → the Wan engine.

Steps 3–6 are yours; I have changed no store state.

---

## 7. Tests

### 7.1 New: `ivgs-workers/tests/test_wp46_animation.py` — 27 tests, all passing

| Group | What it pins |
|---|---|
| **Wiring** (5) | `STAGE_TASK_MAP` no longer names the image task and differs from the image entry; `STAGE_QUEUE_MAP` says `gpu_animation`; the queue is declared and routed in `celery_app`; the task's registered name and `queue=` attribute; **and that the dispatch plan's queue literal agrees with `STAGE_QUEUE_MAP`** — those are two separate places, and a scene routed by one and consumed by the other is a job that hangs with its assets already in SeaweedFS. |
| **Provenance** (4) | the graph's sha256 equals MBCP's; the certified family-spec defaults (checkpoint name, steps 6, cfg 1.0, shift 5.0, `dpm++_sde`, 768×1408, 77 frames, 30 fps); the reservation ask equals MBCP's measured peak; `comfyui` → `IVGS_COMFYUI_URL`. |
| **Graph build** (7) | every slot filled by the certified defaults; INT/FLOAT slots are real numbers, not quoted strings (ComfyUI's sockets reject quoted numbers outright); both uploaded filenames land in `LoadImage` / `VHS_LoadVideo`; store `default_params` override the certified defaults; `engine_model` bridges the store name to the checkpoint filename; the terminal node is cache-busted while the seed stays fixed; an unfilled slot is **named** rather than POSTed. |
| **Refusal** (2) | a missing `reference_image` or `driving_video` raises naming that input and saying why. |
| **Result shape** (2) | `SceneAnimationResult` field sets and annotations equal `SceneVideoResult`'s. |
| **Checkpoints** (6) | every checkpoint keyed on `join_stage` and never on `image_generation`; an explicit `join_stage` honoured; the terminal write present with the right status; a partial run lands `partial_success`; the completion reports under the animation label; `binding_source` recorded. |
| **Capability gate** (1) | reaching a stock ComfyUI fails the batch naming `IVGS_COMFYUI_URL` and the missing node classes, **while still reporting** — the join closes and the row lands terminal. |

### 7.2 Regression check — the honest version

`ivgs-workers/tests`, compared against a clean `git worktree` at HEAD (`b536c06`):

```
baseline (HEAD)      27 failed, 593 passed, 38 skipped, 15 errors
with WP-46           27 failed, 597 passed, 38 skipped, 15 errors   (+31 with the new file)
FAILED/ERROR sets    42 lines each, diff EMPTY -> IDENTICAL
```

**42 pre-existing failures, identical set before and after. Nothing regressed.** The
pre-existing set is `test_dlq_service`, `test_quality_gate`, `test_stage1/2/3`,
`test_retry_engine`, `test_orphan_cleanup`, `test_fallback_chain`, `test_quality_validator`,
`test_talking_head_task` — none of them in this package's blast radius, and all of them
failing the same way at HEAD.

Temporal suite specifically: **193 passed, 2 skipped**, including the WP-41 payload-shape
guard.

### 7.3 Full suite — an environment note

The full suite does not run cleanly in this environment, for reasons that predate this
package:

* Bare `pytest` **refuses to start**: `ivgs-api/tests/conftest.py` guards against a
  non-test database and `DATABASE_URL` points at the live one. Correct behaviour — that
  guard exists because the fixture TRUNCATEs every table.
* Pointed at `ivgs_reconciliation_test` it does run to completion — 1536 items collected,
  **249 failed, 737 passed, 53 skipped, 1093 errors in 347 s** — but the `ivgs-api` half
  errors at fixture setup en masse. The cause is the auth fixture, not the schema:
  `conftest.py:513 operator_token -> create_test_user`, alongside
  `passlib.handlers.bcrypt: module 'bcrypt' has no attribute '__about__'`. That is a
  passlib/bcrypt version incompatibility in the venv, and it takes down every fixture that
  needs a user, which is most of `ivgs-api/tests` and all of `tests_system/integration`.

This is an environment condition, not a WP-46 result — worth its own small package, since
it means the api suite has effectively not run in this venv for some time.

**Zero of those failures or errors is in this package's code.** Grepping the full run for
`test_wp46_animation` and `temporal/` among the FAILED/ERROR lines returns **0 matches**;
both suites passed inside the full run exactly as they do alone.

The regression claim above rests on the like-for-like `ivgs-workers` comparison, which is
where every code change of consequence lives; the single `ivgs-api` change is one dict
value, and no test in the repo asserts on it (grepped).

---

## 8. Deploy evidence — `v5.8.0-animation`, WP-34 rules in full

Built from the repository root, `docker build` rc=0, image id
`sha256:edd402deb862e71ce2d39a755caced235432962c58d84e27bc9b2536d93cd90c`.

**Rule 1 — registry off the deploy path.** Banked first to
`/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.8.0-animation.tar.zst`
— **271,134,418 bytes**, sha256 `b78c5bfcde8faf6fbabfcb30f8067bd4fcbe1188cead869a705ea1039a9363b1`,
`zstd -t` **OK**, **exactly 1** manifest entry
(`['ghcr.io/brucecostello2/ivgs-workers:v5.8.0-animation']`). Distributed by artifact copy
+ `docker load`, with the sha256 re-checked **on each node before loading** (`sha256sum -c`
OK on 02/03/04). **GHCR push deliberately NOT done** — this WP's rule is never push, and
WP-34 makes the registry non-blocking. Flagged in §10.

**Rule 1b — a content gate on the image itself, not on its tag.** A 23-check script run
*inside* the built image before anything was deployed: the certified graph's sha256; that
`STAGE_TASK_MAP`'s animation entry names the new task and no longer mentions
`stage3_images`; that `STAGE_QUEUE_MAP` and the dispatch plan agree; the queue, route and
include; four certified defaults; `stage_name=join_stage` appearing exactly twice; the
`enable_checkpoint_saving` guard; the release bracket and the id clear; the refusal text;
the env-var name in the gate; the VRAM constant; and four prior-WP markers still present
(`strip_tts_markup`, `release_acquired_reservation`, `CheckpointWriteError`,
`RenderSceneAnimationOutput`). Result: **WP46_IMAGE_GATE: PASS**.

> The gate lied to me once and I am recording it. Its `STAGE_TASK_MAP` check anchored on
> the first `ANIMATION_GENERATION.value: (` in the file, which is **`STAGE_TRANSITIONS`**,
> not `STAGE_TASK_MAP` — same shape, twenty lines earlier. It reported FAIL on correct
> code. Re-anchored inside `STAGE_TASK_MAP` explicitly.

**Rule 2 — presence gate before every `.env` write.** `docker image inspect` returned the
same id `sha256:edd402de…` on **all four** nodes before any tag was touched. Rollback
recorded on all four: `.env.bak-wp46-<ts>`, prior value `IVGS_WORKERS_TAG=v5.6.9-voice`
on every node.

**Rule 3 — label-derived compose.** Every invocation came from
`docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'`,
with `--project-directory /opt/ivgs/ivgs-infra`, absolute `-f` paths, `--force-recreate
--no-deps --pull never`, and services named explicitly. node-01 used its three `-f` files
(`node01` + `override.node01` + `monitoring`).

**Rule 4 — real `$?`, and verification by CONTENT.** Every compose step wrote `REAL_RC=0`
from a real exit status. Fleet verified by asking the running workers, not by reading tags:

```
celery-worker@node02        queues=gpu_llm                              animation_task_registered=True
cogvideox-worker@node03     queues=gpu_animation,gpu_video              animation_task_registered=True
composition-worker@node01   queues=composition                          animation_task_registered=True
default-worker@node01       queues=cleanup,default,notifications        animation_task_registered=True
image-worker@node04         queues=gpu_image,gpu_talking_head,gpu_tts   animation_task_registered=True

consumers of gpu_animation: ['cogvideox-worker@node03']
```

Exactly one consumer, on the node with the engine. All five workers on `v5.8.0-animation`,
all healthy.

**Rule 5 — existing engines untouched.** `StartedAt` compared before and after every
recreate, byte for byte:

| Container | Node | StartedAt before | StartedAt after |
|---|---|---|---|
| `ivgs-cogvideox-server-node03` | 03 | `2026-08-24T22:29:07.135066452Z` | **identical** |
| `ivgs-latentsync` | 04 | `2026-08-24T21:23:28.127688598Z` | **identical** |
| `ivgs-comfyui-primary` | 04 | `2026-08-24T21:23:27.524024504Z` | **identical** |
| `ivgs-kokoro` | 04 | `2026-08-24T21:23:26.57908219Z` | **identical** |
| `ivgs-whisperx` | 04 | `2026-08-24T21:23:26.896228597Z` | **identical** |
| `ivgs-coqui` | 04 | `2026-08-24T21:23:26.258054008Z` | **identical** |
| `ivgs-vllm-primary` | 02 | `2026-08-24T20:39:29.20930049Z` | **identical** |

node-04's engine tags confirmed unchanged either side:
`IVGS_COMFYUI_TAG=v5.2.7-h0 IVGS_COQUI_TAG=v5.2.7-h0 IVGS_KOKORO_TAG=v5.2.7-h0
IVGS_WHISPERX_TAG=v5.2.7-h0 IVGS_LATENTSYNC_TAG=v5.2.7-h0`. **api, frontend and scheduler
were not rebuilt and not recreated** — note that the `ad01_ingest.py` fix therefore ships
with the *next* api build, not this one. It only affects future MBCP ingests, so nothing
is waiting on it.

**Rule 6 — secrets.** Only narrow `^IVGS_[A-Z]*_TAG=` and key-name greps; no value
printed. The MBCP token was read into a shell variable to test the serving plane and never
echoed; `sed`-masked in this report.

**Rule 7 — no `ivgs-infra/.env*` committed.** `docker-compose.node03.yml` *is* tracked and
*is* in the held commit; it was shipped to node-03 under a sha256 gate
(`1f705037096c30f6053c64cc36eee7210f1e92ecd967dd0342a2b43163e264f7`, matched both ends)
with the live file backed up to `docker-compose.node03.yml.bak-wp46-<ts>`.

**One host change outside the repo, recorded.** node-03's `/etc/docker/daemon.json` gained
`"insecure-registries": ["192.168.1.51:5000"]` so the certified MBCP image could be pulled
(it is an HTTP registry). Applied with **`systemctl reload docker`** — SIGHUP, which
Docker treats as a reloadable option — **not** a daemon restart. Both node-03 containers'
`StartedAt` were identical before and after. Backup at
`/etc/docker/daemon.json.bak-wp46-<ts>`.

**Rollback.** Per node: restore `.env.bak-wp46-<ts>` and re-run the same compose
invocation; `v5.6.9-voice` is still present in every node's local image store and in the
artifact store. For node-03 additionally restore `docker-compose.node03.yml.bak-wp46-<ts>`
and `docker compose … stop wan-animate-server && docker compose … rm -f wan-animate-server`.
The engine service is additive: removing it returns node-03 to its prior shape exactly.

---

## 9. Ledger — defects found, one fixed, three recorded

**L-1 (FIXED here). All three IVGS animation candidate rows carry the wrong engine key.**
`MimicMotion`, `Wan2.2-Animate` and `AnimateDiff-SD15` are all `engine = 'animatediff'`.
MBCP serves its whole animation line on ComfyUI — one `ComfyUIAdapter`, one graph per
family (`mbcp_adapters/comfyui.py`). The cause is a single line in IVGS's own ingest
receiver:

```python
# ivgs-api/app/api/ad01_ingest.py — _STAGE_DEFAULT_ENGINE
ModelStage.ANIMATION_GENERATION: ModelEngine.ANIMATEDIFF,   # was
ModelStage.ANIMATION_GENERATION: ModelEngine.COMFYUI,       # now
```

MBCP's `ExportBundle` may omit the engine, and IVGS then derives it from the stage. The
receiver's own docstring calls this a "recorded gap"; what was not recorded is that the
animation default was *wrong*. Fixed for future ingests. **The rows already written cannot
be corrected** — `models.engine` is registration-time — so all three need
disable-and-re-register. §5 gives the values for Wan2.2-Animate; MimicMotion and
AnimateDiff-SD15 need the same treatment before they can ever bind.

**L-2 (recorded). The same table's video default is questionable.**
`VIDEO_GENERATION: ModelEngine.COGVIDEOX` — but MBCP's `wan_t2v` is also a ComfyUI family
and would land as `cogvideox`. No video row is affected today, so I did not change it;
changing it needs a decision about what a multi-engine stage's default should be, which is
the real defect underneath both L-1 and L-2. The honest fix is for MBCP to always send
`engine` (the field exists and the receiver already prefers it) and for IVGS to reject the
bundle rather than guess.

**L-3 (recorded). Two ComfyUI instances, one engine key, one endpoint map.**
`_ENGINE_ENDPOINTS` maps `comfyui` → `IVGS_COMFYUI_URL` fleet-wide. Correct routing now
depends on that variable having different values on different workers. It is defended by
the capability gate (§4.1) and by the queue map, but it is a coupling that will bite the
first time a worker consumes both `gpu_image` and `gpu_animation`. `resolve_endpoint`
already takes a `node_id` parameter it does not use, and its docstring names per-node
endpoint maps as an AD-01.9 follow-on. That is the fix.

**L-4 (recorded, MBCP-side). Wan2.2-Animate's certificate carries the wrong engine image
digest.** `provenance.engine_image_digest` is `sha256:257fc26…` = `MBCP_COMFYUI_IMAGE`,
the diffusers-0.29.2 instance that serves MimicMotion — which is also the digest
MimicMotion's certificate carries, correctly. The `wan_animate` graph **cannot run on that
image**: kijai's `WanVideoWrapper` needs diffusers ≥ 0.33, which is why MBCP built
`comfyui-wan` (`sha256:58752ff6…`) as a separate service in the first place. Either the
provenance is stamped per-plane rather than per-engine, or the certification predates the
engine split. Worth a question to MBCP, because AD-04-v3's whole premise is that the
pinned digest is load-bearing.

**L-5 (housekeeping, done).** A killed download left a truncated 18 GB sparse safetensors
that the running engine advertised as loadable. Deleted. Recorded because the failure it
would have produced — a load error deep inside a node, hours later — would have looked
like a model problem rather than a disk problem.

---

## 10. Decisions you own

1. **The two MBCP secrets.** `MBCP_WEIGHT_SERVICE_TOKEN` and `MBCP_WEIGHT_SIGNING_KEY`.
   Everything in this package is finished and waiting on them, including the only two
   things it could not deliver: a verified generation and a real animation asset. Ledger
   P2.10 / S-4; they are in S-1's rotation set, so it may be worth doing the rotation and
   the handoff in one window.

2. **Where the motion comes from — the real editorial question.** Wan2.2-Animate needs a
   driving video per scene. The task currently uses the project's single `reference_clip`
   for every animation scene (on the banked reference project, `magihuman_testB_t2v.mp4`,
   5.4 MB). That means twelve animation scenes would all perform *the same motion* with
   different subjects. Options, none of which I should pick for you:
   * one project-level clip, as built — cheapest, and visibly repetitive across a long video;
   * a per-scene `driving_video_asset_id`, which the task already honours — needs a motion
     library and a way for Stage 2 to choose from it;
   * a motion clip generated per scene by CogVideoX and fed in as the driver — expensive,
     and it makes animation depend on the video branch.
   Until you decide, animation scenes are best treated as a small subset, not the 12-of-18
   the reference storyboard produced.

3. **The other two animation rows.** `MimicMotion` and `AnimateDiff-SD15` carry the same
   wrong engine key. They are unusable as they stand. Re-register or leave dormant?

4. **GHCR push.** `v5.8.0-animation` is banked and deployed on four nodes but not in the
   registry, because this WP's rule is never push. Say the word.

5. **node-05.** It is a 48 GB RTX PRO 5000, online and completely idle, and `dev/CLAUDE.md`
   still lists it as OFFLINE. It is not right for Wan2.2-Animate (§2.2) but it is a real
   card doing nothing. Worth a purpose.

---

## 11. Push block — count-gated, for ALL held commits

> **Superseded 2026-08-25 by the addendum's §A9.** Both commits below were pushed to
> `origin/main` between the two halves of this package — not by me. `origin/main` is at
> `2590e0d` as of the addendum. This block is kept as the record of what was held at the
> time; use §A9.

**HELD: 1 commit.** Nothing has been pushed.

```
d536967  feat(wp-46): animation gets a body - Wan2.2-Animate, its own task, its own queue
```

Run this as one block. It refuses unless the count is exactly what this report claims.

```bash
\
git fetch origin main && \
EXPECTED=2 && \
ACTUAL=$(git rev-list --count origin/main..HEAD) && \
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git log --oneline origin/main..HEAD && \
  git status --short && \
  git push origin main && \
  echo "PUSHED $ACTUAL commit(s)"
fi
```

`EXPECTED=2` — this report is committed after the code, so at push time there are two:
the code commit above and the report commit. If you push before the report lands, set it
to 1. If it reports any other number, stop and find out what else is held before pushing.

---
---

# ADDENDUM — 2026-08-25, credentials delivered: the weights, and the first real animation

The operator handed over the MBCP weight credentials. §6.1 steps 1–2 are done. **A real
animation asset exists**, rendered by Wan2.2-Animate on node-03 from one scene of the
banked reference storyboard, uploaded, checkpointed and scene-linked.

| | |
|---|---|
| **Asset** | `3bc54e58-3901-440c-a2ea-8f89bbc7476c` — `/ivgs/videos/c12fa967-…/7c6d34ba-…_animation.mp4` |
| **Render** | 768×1408, 30 fps, **77 frames**, 2.567 s, h264, 796,500 bytes |
| **Wall clock** | **256.49 s** task, 255.63 s inside the engine (MBCP certified 299.02 s) |
| **VRAM peak** | **56,139 MiB = 54.82 GiB** absolute; **34,874 MiB = 34.06 GiB** attributable to this render |
| **Job** | `5eb2bda1-1267-4f29-a219-aee39c266801`, checkpoint `animation_generation` → `complete` |
| **Store** | still **CANDIDATE**, engine still `animatediff`, `is_default` still false. Nothing touched. |
| **State** | Committed and **HELD**. Nothing pushed. |

---

## A1. Credential handling

`/opt/ivgs/ivgs-infra/.mbcp-weights.env`, mode 600, three variables:
`MBCP_WEIGHT_SERVICE_TOKEN`, `MBCP_SERVING_TOKEN`, `MBCP_WEIGHT_SIGNING_KEY`. Sourced into
the fetch process's environment and never written elsewhere, never echoed, never passed on
a command line, and never copied to another host — the entire fetch ran on node-01.

**One thing needed fixing first.** `git status` listed the file as untracked: it was one
`git add -A` away from the repository's permanent history. `.gitignore` now covers it
(`.mbcp-weights.env` and `ivgs-infra/.mbcp-weights.env`), verified with `git check-ignore`.

---

## A2. Step 1 — the nine bundles: fetched, verified, placed

### A2.1 The tier is `candidate`, not `certified`

`?tier=certified` returns `{"detail":"no such bundle"}` for every one of the nine. The
serving plane holds **26 bundles**; all nine `wan_animate` components are present at
`tier=candidate`, none revoked, and every one carries `promoted_at: null` — MBCP's
`POST /promote/{stored_weight_id}` has never been run on them.

So: **the model is certified; its weight bundles are not promoted.** The fetch therefore
uses `tier=candidate`. That is a real gap between the certification record and the weight
store, and it is worth an answer from MBCP before the row is approved — see A6.

### A2.2 What was verified, stated exactly

Using the repo's own seam-2 client (`ivgs-models/mbcp_fetch.py`) for both primitives:

* **Manifest HMAC-SHA256 signature — verified for all nine.** This is the one that matters
  most: it proves every `logical_name → sha256` pair in the manifest is MBCP's.
* **Bundle digest — verified for all nine.** Recomputed from the manifest's file list with
  `compute_bundle_digest` and compared to the published `bundle_digest`.
* **Per-file SHA-256 — verified for all 23 files while streaming**, then **verified a
  second time on node-03 after the copy**: `sha256sum -c` → **23 of 23 OK, zero failures**.

> **One honest limitation.** For the Wan2.2-Animate bundle only, the include filter means
> we keep 1 of 4 files, so the bundle digest cannot be a checksum of what is on disk — by
> definition it covers all four. It is verified against the manifest (proving the manifest
> intact and authentic) and the kept file's own SHA-256 is verified against it. The other
> eight bundles were taken whole.

### A2.3 Fetch evidence

Full record at `/mnt/ivgs-shared/wan-weights-staging/FETCH_EVIDENCE.json`.

| Component | tier | ver | files | sig | digest | bundle_digest |
|---|---|---|---|:--:|:--:|---|
| Wan2.2-Animate-14B | candidate | 2.2-fp8 | **1/4** | OK | OK | `5607289a96eb1804a229944d1a9d0ec2622232281671a18f7fc4772149258b42` |
| UMT5-XXL-enc | candidate | bf16 | 3/3 | OK | OK | `783cf397eb788d4597accd2ebe792c8912c4262719cf1ab2add3cf1b8eee4cb2` |
| Wan2.1-VAE | candidate | 2.1-bf16 | 3/3 | OK | OK | `36b520a5afa2c857b8891aa744e45244210f88faad693f8ee41fe9a93e72654e` |
| CLIP-Vision-H | candidate | h | 3/3 | OK | OK | `1eedcacffe7a3d6bb3e5d4f1a50aca7323ebbd1f00c3f322692b455b17c3710b` |
| WanAnimate-relight-LoRA | candidate | fp16 | 3/3 | OK | OK | `24766a12fde5555f57e59db660c945a81b732378824fdb3ca8b9e9c2f861ca54` |
| Lightx2v-I2V-distill-LoRA | candidate | rank64-bf16 | 1/1 | OK | OK | `91a004b59ac3d8a30cfd99fc6768d1ed91b7e1192bf5c18912b34ca61d5add3a` |
| ViTPose-L-wholebody | candidate | l-wholebody | 3/3 | OK | OK | `538377805047414abeb7b48a47dbe83573b8da7b8ff2ec89d963583945655abd` |
| YOLOv10m-det | candidate | 10m | 3/3 | OK | OK | `d2906ea7811cb4d81ab20d728350c7d0c242d3da9e452ebf6d82531c69b060f7` |
| SAM2.1-hiera-base-plus | candidate | 2.1-base-plus | 3/3 | OK | OK | `9b63962f6017d0ce097c3a781a9f377d99d8be62b2cc2363b4231d307677b54c` |

Every manifest reports `engine_version: comfyui` — MBCP's own confirmation, at the weight
store, that this family's engine is **`comfyui`** and not `animatediff` (§9 L-1).

**23 files, 35,076,023,613 bytes (32.67 GiB), fetched in 66.2 s.**

**The include filter earned its place.** The Wan2.2-Animate bundle holds all four fp8
variants and weighs **71,437,807,292 bytes (66.5 GiB)**:

```
18,401,760,586  2936b314…  Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors   <- kept
18,401,760,586  7d9c1efa…  Wan22Animate/Wan2_2-Animate-14B_fp8_e5m2_scaled_KJ.safetensors
17,317,143,060  b1cd5a67…  Wan22Animate/Wan2_2-Animate-14B_fp8_scaled_e4m3fn_KJ_v2.safetensors
17,317,143,060  5fff9ba1…  Wan22Animate/Wan2_2-Animate-14B_fp8_scaled_e5m2_KJ_v2.safetensors
```

The kept file is the one the certificate's `performance.model_used` names. Taking the
bundle whole would have needed 66.5 GiB against node-03's 62 GiB free — it would not have
fitted.

### A2.4 Placement and the loaders

`rsync` to node-03 at 291 MB/s (2m 0s), then `chown 10001:10001`, `755`/`644`. Node-03
disk: 62 GB → 30 GB free. Layout is exactly MBCP's materialization map:

```
 18,401,760,586  diffusion_models/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors
 11,361,845,464  text_encoders/umt5-xxl-enc-bf16.safetensors
  1,436,672,440  loras/WanAnimate_relight_lora_fp16.safetensors
  1,264,219,396  clip_vision/clip_vision_h.safetensors
  1,234,579,166  detection/vitpose-l-wholebody.onnx
    738,005,744  loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
    323,474,320  sam2/sam2.1_hiera_base_plus.safetensors
    253,806,278  vae/Wan2_1_VAE_bf16.safetensors
     61,659,339  detection/yolov10m.onnx
```

`docker restart ivgs-wan-animate-server-node03` — the WP-46 service only.
`ivgs-cogvideox-server-node03` and `ivgs-cogvideox-worker-node03` reported identical
`StartedAt` before and after.

**The loaders now list exactly what the certified graph names, and nothing else:**

```
WanVideoModelLoader.model        ['Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors']
WanVideoVAELoader.model_name     ['Wan2_1_VAE_bf16.safetensors']
CLIPVisionLoader.clip_name       ['clip_vision_h.safetensors']
WanVideoTextEncodeCached.model_name ['umt5-xxl-enc-bf16.safetensors']
WanVideoLoraSelectMulti.lora_0   ['none', 'WanAnimate_relight_lora_fp16.safetensors',
                                  'lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors']
OnnxDetectionModelLoader.*       ['vitpose-l-wholebody.onnx', 'yolov10m.onnx']
```

Before the fetch every one of these was `[]`.

---

## A3. Step 2 — the render

Same harness, same scene: project `c12fa967`, scene index **3**, `media_type=animation`,
run from inside the deployed node-03 worker against the deployed engine, store row still
CANDIDATE (so `engine_endpoint_override`, recorded as `binding_source=explicit-override`).

```
03:40:52 animation_generation_starting   join_stage=animation_generation total_scenes=1
03:40:52 job_status_updated              status=running
03:40:52 gpu_reservation_acquired        reservation_id=res-4fc5b4ab70bc42ab gpu_index=0
03:40:53 animation_inputs_resolved       reference_image=ba59d633-…  driving_video=669e9ac0-…
03:45:09 animation_generation_success    elapsed=256.49  engine_elapsed=255.63
                                         prompt_id=7ebd665a-d5c6-48c5-bdd9-11233cb3d48b
                                         model=Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors
03:45:09 checkpoint_saved                stage_name=animation_generation status=running
03:45:09 gpu_reservation_released        reservation_id=res-4fc5b4ab70bc42ab
03:45:09 checkpoint_saved                stage_name=animation_generation status=success
03:45:09 animation_generation_complete   successful=1 failed=0
RENDER_RC=0 WALL_S=258
```

**The asset, in the database:**

```
id              3bc54e58-3901-440c-a2ea-8f89bbc7476c
scene_id        7c6d34ba-e235-43ff-acb0-ac894b5f75c7   scene_index 3, media_type animation
asset_type      video          mime_type video/mp4
seaweedfs_fid   4,8c2c448fe6
seaweedfs_path  /ivgs/videos/c12fa967-…/7c6d34ba-…_animation.mp4
file_size_bytes 796500
content_hash    32408643e3c4be400f68a858fab6e22eeaf75f755ca654b27ee6b83fe6204d5a
```

**The checkpoint:**

```
stage_name  animation_generation      <- not image_generation
stage_index 3
status      complete
data        {"failed_count": 0, "successful_count": 1, "deduplicated_count": 0,
             "total_generation_time": 256.49, "binding_source": "explicit-override"}
```

Round-trip verified: the bytes downloaded back out of SeaweedFS hash to
`32408643e3c4be400f68a858fab6e22eeaf75f755ca654b27ee6b83fe6204d5a` — the value the task
reported.

### A3.1 It is an animation, not a still — measured

The point of this package is that `media_type=animation` stopped producing a static PNG.
So I measured motion rather than asserting it. 77 frames decoded to greyscale and
compared pairwise:

```
frames decoded                    : 77
distinct frames                   : 77 of 77
identical consecutive pairs       : 0 of 76
consecutive-frame mean abs diff   : min 0.296   mean 1.416   max 2.977   (0–255 scale)
first-vs-last frame diff          : 10.214
```

Zero identical pairs, and the first-to-last difference is 7× the mean step — it moves, and
it goes somewhere. Frame content is real, not a black or blown-out buffer (frames 0/38/76:
mean 196–199, stdev 59–60, full 0–251 range).

Container: `h264`, `yuv420p`, `768x1408`, `30/1` fps, `nb_frames=77`, `duration=2.567`.

---

## A4. The measured numbers, on this fleet

VRAM sampled every 2 s across the whole run (128 samples over 257 s):

| | MiB | GiB | note |
|---|---:|---:|---|
| Baseline at t=0 | 21,265 | 20.77 | CogVideoX 20,700 + Wan engine idle ~550 |
| **Absolute peak** | **56,139** | **54.82** | 57.4% of the 97,887 MiB card |
| **Attributable to this render** | **34,874** | **34.06** | peak − baseline |
| Free at peak | 41,748 | 40.77 | |
| Resident after the render | 41,227 | 40.26 | ComfyUI keeps the model cached |

Trace (seconds : MiB) — the load, the sample, the release:

```
0:21265  21:21469  41:26277  61:55851  81:55915  101:55947  122:55979
142:55979  162:56139  182:56139  202:56139  222:56139  243:42571
```

Peak reached 148 s in; the step from 26 GB to 55.8 GB between 41 s and 61 s is the 17.1 GiB
checkpoint plus the 10.6 GiB text encoder loading from disk.

**Wall clock: 256.49 s** for the task, 255.63 s inside the engine, 258 s including harness
overhead. **14% faster than MBCP's certified 299.02 s** at identical settings.

### A4.1 Against MBCP's certificate — and which number belongs in the store

| | MBCP (cert `eb032794`) | IVGS (this run) |
|---|---:|---:|
| absolute peak | 44.39 GB | **54.82 GiB** |
| baseline already resident | 29.77 GB | 20.77 GiB |
| delta attributed to the model | 14.63 GB | **34.06 GiB** |
| generation time | 299.02 s | **256.49 s** |

The deltas differ by more than 2× and the reason matters: **MBCP's 14.63 GB delta was
almost certainly measured warm.** Its baseline of 29.77 GB is larger than this run's
*entire* engine-plus-CogVideoX baseline, which is consistent with the Wan checkpoint
already being resident when its delta was sampled. This run measured it **cold** — the
step at 41–61 s in the trace above is that load happening.

**So the number to put in the store's VRAM field is 34.10, not 44.39.** That field feeds
`acquire_gpu_reservation` as "how much must be free", and the honest answer for a cold
start is the 34.06 GiB this run measured, rounded up. The absolute peak of 54.82 GiB is a
*co-residency* figure — it includes CogVideoX's 20.7 GB — and would over-reserve on a node
that is not also running CogVideoX.

Corollaries worth knowing:
* A second scene in the same job starts **warm** — 40.26 GiB stays resident after the
  render — so per-scene time after the first will be well under 256 s.
* `CERTIFIED_VRAM_MB = 45458` in the task is the fallback used only when the row carries no
  `vram_gb`. It is now known to be conservative by ~10 GiB (asks for more than needed,
  which fails safe). The store row's value overrides it, which is the intended path; I have
  left the constant alone rather than ship a rebuild for a fallback that a registered row
  replaces.

---

## A5. Findings from the first real render

### A5.1 The geometry is wrong for a 16:9 lesson — QUALITY, not correctness

The render succeeded and the model behaved. The **shape** is wrong for this content:

```
reference still : 1920x1080   aspect 1.778   (16:9 landscape)
render output   :  768x1408   aspect 0.545   (portrait)
ImageScale, crop: disabled -> x0.400 horizontally, x1.304 vertically
                              = a 3.26x vertical stretch relative to horizontal
```

768×1408 is MBCP's certified benchmark geometry, and it is the right shape for what MBCP
benchmarks: a single standing human. An educational scene showing a worked multiplication
on a board is 16:9, and the certified graph's `ImageScale` node has `crop: disabled`, so it
does not letterbox — it squashes.

**The fix is two keys in the store row's `default_params`** (`output_width` /
`output_height`, e.g. 1280×720 — both divisible by 16). But changing them **deviates from
the certified configuration**, so the certificate's 44.39 GB / 299.02 s / Elo 1576.96 stop
strictly applying, and VRAM scales with pixel count: 1280×720 is 0.85× the pixels of
768×1408, so it should land slightly *under* today's 34.06 GiB. This is a decision, not a
defect — see A7.2.

The driving clip is `magihuman_testB_t2v.mp4`, 896×512, 25 fps, 425 frames (17.04 s); the
graph consumes the first 77 frames at `force_rate: 0`, i.e. ~3.1 s of source motion
rendered as 2.567 s at 30 fps.

### A5.2 Content-hash dedup is dead — fleet-wide, and it is not mine

`was_deduplicated: false` is correct here (first render), but it would be false forever.
Two API gaps, measured:

1. **`check_duplicate_asset` calls a route that does not exist.** It does
   `GET /api/v1/assets?sha256=…`; `asset_router` has only `/{asset_id}`,
   `/{asset_id}/download`, `/{asset_id}/regenerate` and DELETE. There is no bare list
   route. The function catches every exception and returns `None`, so it fails silently —
   a **swallowed failure** in the WP-00 register's sense.
2. **`POST /projects/{id}/assets/upload` silently drops `content_hash` and `metadata`.**
   Its signature takes `file`, `asset_type`, `scene_id`, `language_code` and nothing else;
   FastAPI discards unknown form fields, and `AssetService` computes `content_hash` from
   the bytes. Proof: the stored `content_hash` is `32408643…`, the hash of the *video*, not
   the dedup key the task supplied.

Consequence: the dedup key can never be found, **for animation, video and image alike** —
`video_generation_task` and `stage3_images` pass the same two ignored fields. And the
animation task's provenance metadata (engine, `prompt_id`, `engine_model`, and the two
input asset ids) **is not persisted anywhere**, which is a real loss: those four facts are
what would let anyone reconstruct how a given clip was made.

I did not paper over this with a per-branch workaround. The fix is one API change —
accept and persist a caller-supplied `content_hash` plus a `metadata` JSONB — and it fixes
all three branches at once. `assets.content_hash` and `generation_params_hash` columns
already exist. See A7.3.

---

## A6. Ledger additions

**L-6. The weight bundles are not promoted.** All nine sit at serving tier `candidate`
with `promoted_at: null`, while the *model* carries a certification. `?tier=certified`
404s. Either promotion is a step MBCP has not run for this family, or certification and
bundle promotion are deliberately independent. Worth an answer before approval, because
"certified model, candidate weights" is not a state the AD-04 contract discusses.

**L-7. `POST /projects/{id}/assets/upload` silently drops `content_hash` and `metadata`.**
Every caller in the fleet passes both; none of them takes effect. Kills content-hash dedup
across all three media branches and loses per-asset generation provenance. A6/A5.2.

**L-8. `check_duplicate_asset` calls a nonexistent route and swallows the failure.**
`utils/media_converter.py:498`. Add to the WP-00 swallowed-failures register.

**L-9. The certified geometry does not fit 16:9 source material.** A5.1. Not a defect —
a configuration decision with a certificate attached to it.

---

## A7. Decisions you own (updated)

1. **Store registration is still yours and still untouched.** §5.2/§5.3 stand, with two
   substitutions now that the numbers are real:
   * **VRAM (GB): `34.10`** — IVGS-measured cold-start requirement (A4.1), not 44.39.
   * attestation JSON below, with `ivgs_generation_verified: true`.

2. **The render geometry.** Ship at the certified 768×1408 and accept a 3.26× vertical
   squash on 16:9 scenes, or set `output_width`/`output_height` in `default_params` and
   accept that the certificate's numbers no longer strictly describe what runs. My
   recommendation is the latter — 1280×720 — with a re-measure, because a distorted lesson
   is not shippable and the deviation is honest and recorded. Your call.

3. **The asset-upload API gap (L-7/L-8).** Small change, fixes dedup and provenance for
   image, video and animation together. Worth its own package; say the word and I will
   scope it.

4. **Driving video** — unchanged from §10.2, and now with a concrete illustration: this
   render used 2.6 s of one 17 s clip. Twelve animation scenes would each replay the same
   motion.

5. **GHCR push** for `v5.8.0-animation` — still banked and deployed but not pushed.

---

## A8. §5.3 attestation, updated

Everything in §5.2 stands except **VRAM (GB) = `34.10`**.

**Vetting reference** — replace §5.3's with this:

```
MBCP certification eb032794-e46e-4787-a399-b45a548c52e5 (Wan2.2-Animate, family wan_animate, engine comfyui), ingested into IVGS 2026-07-10 02:22:24Z as attestation dc110421-c201-42ac-8635-20375b435423. MBCP certified measurement (run 7d958e88-3510-43ed-821d-eb029f0adbd7, result 661c5cd1-7d67-4886-85d3-e96906160d3f, hardware profile 2b739637-9fac-456f-bcf2-4e8840900d4c): measured_vram_gb 44.392578125, gen_time_s 299.02 at 768x1408 / 77 frames, human-eval Elo 1576.96 over 6 pairwise comparisons - the highest of the three certified animation candidates (MimicMotion 1423.04). VERIFIED ON THIS FLEET by WP-46-ANIMATION addendum 2026-08-25 (dev/workpackages/reports/WP-46-ANIMATION-report_2026-08-25.md): all nine certified component bundles fetched from the MBCP serving plane via ivgs-models/mbcp_fetch.py with manifest HMAC signature verified, bundle digest verified and per-file SHA-256 verified on fetch and again on node-03 (23/23 files OK); engine ivgs-wan-animate-server-node03 on node-03 from MBCP image comfyui-wan@sha256:58752ff6d84912d82e7f52d484ec84ec70829951c3e88c1592a12407604d62e2 running MBCP's certified wan_animate graph unmodified (sha256 84a00a2549c3802cdb9f2365430ebc0136cccb226c1c67eed491b0bac70b2525). Real render of reference project c12fa967 scene 3: asset 3bc54e58-3901-440c-a2ea-8f89bbc7476c, 768x1408, 30 fps, 77 frames, 2.567 s, h264, 796500 bytes, sha256 32408643e3c4be400f68a858fab6e22eeaf75f755ca654b27ee6b83fe6204d5a; 77/77 distinct frames with zero identical consecutive pairs (it is an animation, not a still). IVGS-measured: 256.49 s wall clock and 34.06 GiB VRAM attributable to the render (56139 MiB absolute peak with CogVideoX co-resident, 21265 MiB baseline). Weight bundles are at MBCP serving tier 'candidate' (promoted_at null), not 'certified'.
```

**Checklist (JSON object)** — replace §5.3's with this:

```json
{"reviewed": true, "engine_key_corrected": {"was": "animatediff", "now": "comfyui", "reason": "MBCP SSOT: family wan_animate is served by the unified ComfyUIAdapter and every fetched bundle manifest reports engine_version 'comfyui'. Root cause fixed in ad01_ingest._STAGE_DEFAULT_ENGINE by WP-46."}, "quality": {"status": "scored", "source": "MBCP human evaluation", "elo": 1576.9625705422015, "n_pairwise": 6, "beat": ["MimicMotion (1423.04)", "AnimateDiff-SD15 (not scored)"]}, "vram_gb_measured": 34.06, "vram_gb_measured_on_ivgs": 34.06, "vram_gb_measurement": {"absolute_peak_mib": 56139, "baseline_mib": 21265, "delta_mib": 34874, "note": "cold start on node-03 with CogVideoX co-resident; MBCP's 44.39 GB peak / 14.63 GB delta was measured warm, which is why the deltas differ", "samples": 128, "interval_s": 2}, "vram_gb_mbcp_certified": 44.392578125, "gen_time_s": 256.49, "gen_time_s_mbcp_certified": 299.02, "resolution": [768, 1408], "frames": 77, "fps": 30, "engine_image_digest": "sha256:58752ff6d84912d82e7f52d484ec84ec70829951c3e88c1592a12407604d62e2", "graph_sha256": "84a00a2549c3802cdb9f2365430ebc0136cccb226c1c67eed491b0bac70b2525", "weights": {"bundles": 9, "files": 23, "bytes": 35076023613, "serving_tier": "candidate", "manifest_signature_verified": true, "bundle_digest_verified": true, "per_file_sha256_verified": true, "reverified_on_target_node": "23/23 OK"}, "ivgs_generation_verified": true, "ivgs_generation_evidence": {"job_id": "5eb2bda1-1267-4f29-a219-aee39c266801", "asset_id": "3bc54e58-3901-440c-a2ea-8f89bbc7476c", "scene_id": "7c6d34ba-e235-43ff-acb0-ac894b5f75c7", "asset_sha256": "32408643e3c4be400f68a858fab6e22eeaf75f755ca654b27ee6b83fe6204d5a", "distinct_frames": "77/77", "identical_consecutive_pairs": 0}, "known_deviation": "certified geometry 768x1408 is portrait; the reference still is 1920x1080, and ImageScale (crop disabled) applies a 3.26x vertical stretch. Not corrected here - changing output_width/output_height deviates from the certified configuration and needs a re-measure.", "source": "WP-46-ANIMATION addendum 2026-08-25"}
```

`ivgs_generation_verified` is now **true**, and every number behind it was measured on this
fleet rather than copied from the certificate.

---

## A9. Push block — count-gated, for ALL held commits

**HELD: 1 commit.**

`origin/main` moved while this package was in flight. The first two WP-46 commits are
**already on the remote** — pushed between the two halves of this work, and not by me;
I have never run `git push` in this package. Verified against a fresh `git fetch`:

```
origin/main = 2590e0d  docs(wp-46): the report - …the weights are not mine to fetch
              d536967  feat(wp-46): animation gets a body - …
```

So exactly one commit is held now — this addendum:

```
<this>   docs(wp-46): addendum - the weights, and the first real animation
```

```bash
\
git fetch origin main && \
EXPECTED=1 && \
ACTUAL=$(git rev-list --count origin/main..HEAD) && \
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "REFUSING: expected $EXPECTED held commit(s), found $ACTUAL"
  git log --oneline origin/main..HEAD
else
  git log --oneline origin/main..HEAD && \
  git status --short && \
  git push origin main && \
  echo "PUSHED $ACTUAL commit(s)"
fi
```

If it reports any other number, stop and find out what else is held before pushing.
