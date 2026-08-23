# WP-33 - Model Store population checklist

**For the operator. One action per line. Do them in order.**

| | |
|---|---|
| **Produced by** | WP-33-MODELSTORE-PREP, 2026-08-23 |
| **Evidence** | `reports/WP-33-MODELSTORE-PREP-report_2026-08-23.md` |
| **Where** | The Model Store admin page: `/admin/models`. Sign in as an admin user - every action below is admin-only. |
| **What this achieves** | `get_binding` will resolve for all six pipeline stages that ask for a model. Six of nine; the other three are deliberately left alone (see "Stages we are NOT touching"). |
| **What this does NOT achieve** | A running pipeline. Three separate blockers sit behind this - see "Before any of it actually runs" at the end. Read that section first if you want to know why the pipeline may still not start. |

Nothing in this checklist deletes or retires anything. Every step either adds a
new model or promotes one that is already there. If a step goes wrong, the
worst case is an extra CANDIDATE row sitting unused.

---

## How the page works

Three things have to be true before the pipeline will use a model:

1. Its **state** is `approved` - you do this with the green **Approve** button.
2. It is the **default** for its stage - you do this with the **Set default**
   button. Only one model per stage can be the default; setting a new one
   automatically clears the old one.
3. It is **enabled** - new models are enabled automatically. The **Enable /
   Disable** button toggles it. You should not need to touch this.

**A model must be `approved` before the "Set default" button appears.** Always
Approve first, then Set default.

**One warning.** `Register` and `Approve` are one-way. A model that is
registered can never be un-registered, and a model that is retired can never be
brought back. Type the names carefully.

---

## Step 1 of 5 - Stage 1, transcript refinement

There is no model for this stage at all. We are creating one.

- [ ] 1.1 Click **Register Model**.
- [ ] 1.2 **Name (unique id)**: `mistral-24b-transcript`
- [ ] 1.3 **Display name**: `Mistral Small 24B (transcript refinement)`
- [ ] 1.4 **Stage**: select `transcript_refinement`
- [ ] 1.5 **Engine**: select `vllm`
- [ ] 1.6 **Tier**: select `both`
- [ ] 1.7 **VRAM (GB)**: `30.6` - this is the allocation vLLM is configured to take on node-04 (`--gpu-memory-utilization 0.32` of a 97887 MiB card), not a measured usage figure. It is the right number for reserving space; it is recorded as configured, not measured, in the attestation below.
- [ ] 1.8 **Description**: `Mistral-Small-24B-Instruct-2501 w4a16, served on node-04 as mistral-24b. Registered by WP-33 to give Stage 1 a binding; the store had no transcript_refinement model of any kind.`
- [ ] 1.9 **Source URL**: `https://huggingface.co/RedHatAI/Mistral-Small-24B-Instruct-2501-quantized.w4a16`
- [ ] 1.10 **License**: `Apache-2.0`
- [ ] 1.11 **Weights ref**: `RedHatAI/Mistral-Small-24B-Instruct-2501-quantized.w4a16@2722d19f241850fa3bdb479e0fd9e6fcd0a584d8`
- [ ] 1.12 **Weights checksum**: **leave blank.** (See "Fields we deliberately left blank" below - the value we could get is a repository revision, not a checksum, and it is already in the Weights ref field above.)
- [ ] 1.13 **Default params (JSON object)** - type exactly this:
      ```
      {"engine_model": "mistral-24b"}
      ```
      **This line is not optional.** Without it the pipeline sends the text
      `mistral-24b-transcript` to vLLM as the model name and vLLM answers 404.
- [ ] 1.14 **Dynamically loadable**: **UNTICK** it. (vLLM serves one fixed model; it cannot load another on request.)
- [ ] 1.15 Click **Register**. The model appears in the list as `candidate`.
- [ ] 1.16 Find `mistral-24b-transcript` in the list and click **Approve**.
- [ ] 1.17 **Attested by**: your username (`bruce`)
- [ ] 1.18 **Vetting reference** - paste exactly:
      ```
      WP-33-MODELSTORE-PREP 2026-08-23: served-model identity verified live on node-04 (ivgs-vllm-midsize, --served-model-name mistral-24b, HF revision 2722d19f241850fa3bdb479e0fd9e6fcd0a584d8). No IVGS quality benchmark exists for this model on this stage.
      ```
- [ ] 1.19 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "served_identity_verified": true, "quality": {"status": "not_benchmarked", "note": "No human-eval or MBCP certification for mistral-24b on transcript_refinement. Approved on served-identity evidence only (INV-9: not fabricated)."}, "vram_gb_measured": null, "vram_gb_configured": 30.6, "source": "WP-33-MODELSTORE-PREP 2026-08-23"}
      ```
- [ ] 1.20 Click the green **Approve**. State becomes `approved`.
- [ ] 1.21 Click **Set default** on the same row. A "default" marker appears.

---

## Step 2 of 5 - Stage 2, storyboard generation

This stage has one model, `test-model-1`, and it is **retired**. Retired is
permanent - there is no way to bring it back, and there is no reason to want
it. We are creating a real one.

- [ ] 2.1 Click **Register Model**.
- [ ] 2.2 **Name (unique id)**: `mistral-24b-storyboard`
- [ ] 2.3 **Display name**: `Mistral Small 24B (storyboard generation)`
- [ ] 2.4 **Stage**: select `storyboard_generation`
- [ ] 2.5 **Engine**: select `vllm` - **it must be `vllm`.** Stage 3 borrows this same model to write its image prompts, and the code refuses any engine that cannot hold a chat conversation.
- [ ] 2.6 **Tier**: select `both`
- [ ] 2.7 **VRAM (GB)**: `30.6` - same figure and same caveat as step 1.7.
- [ ] 2.8 **Description**: `Same served model as mistral-24b-transcript. A separate row is required because the Model Store records one model per stage. Also borrowed by Stage 3's image-prompt writer.`
- [ ] 2.9 **Source URL**: `https://huggingface.co/RedHatAI/Mistral-Small-24B-Instruct-2501-quantized.w4a16`
- [ ] 2.10 **License**: `Apache-2.0`
- [ ] 2.11 **Weights ref**: `RedHatAI/Mistral-Small-24B-Instruct-2501-quantized.w4a16@2722d19f241850fa3bdb479e0fd9e6fcd0a584d8`
- [ ] 2.12 **Weights checksum**: leave blank.
- [ ] 2.13 **Default params (JSON object)** - type exactly this:
      ```
      {"engine_model": "mistral-24b"}
      ```
- [ ] 2.14 **Dynamically loadable**: **UNTICK** it.
- [ ] 2.15 Click **Register**.
- [ ] 2.16 Find `mistral-24b-storyboard` and click **Approve**.
- [ ] 2.17 **Attested by**: `bruce`
- [ ] 2.18 **Vetting reference** - paste exactly:
      ```
      WP-33-MODELSTORE-PREP 2026-08-23: same served model as mistral-24b-transcript, verified live on node-04. Registered separately because AD-01.5.2 records one model row per stage. No IVGS quality benchmark exists for this model on this stage.
      ```
- [ ] 2.19 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "served_identity_verified": true, "quality": {"status": "not_benchmarked", "note": "No human-eval or MBCP certification for mistral-24b on storyboard_generation. Approved on served-identity evidence only (INV-9: not fabricated)."}, "vram_gb_measured": null, "vram_gb_configured": 30.6, "source": "WP-33-MODELSTORE-PREP 2026-08-23"}
      ```
- [ ] 2.20 Click the green **Approve**.
- [ ] 2.21 Click **Set default** on the same row.

---

## Step 3 of 5 - Stage 3, image generation

There is already a model called `FLUX.1-dev` sitting as a candidate. **Do not
approve it.** Those weights are not on node-04 - the only image checkpoint the
machine has is FLUX.1 *schnell*, a different model. Approving `FLUX.1-dev`
would give you a row that claims one thing and a machine that does another, and
Stage 3 would crash. We are registering the model that is actually there.

- [ ] 3.1 Click **Register Model**.
- [ ] 3.2 **Name (unique id)**: `flux1-schnell`
- [ ] 3.3 **Display name**: `FLUX.1 Schnell (fp8)`
- [ ] 3.4 **Stage**: select `image_generation`
- [ ] 3.5 **Engine**: select `comfyui`
- [ ] 3.6 **Tier**: select `both`
- [ ] 3.7 **VRAM (GB)**: **leave blank.** We have never measured this model on this machine, and the figure we do have (31.47 GB) belongs to FLUX.1-dev, a different model. Leaving it blank makes Stage 3 use its own 16 GB estimate, which is honest. Fill it in later if you measure it.
- [ ] 3.8 **Description**: `The only image checkpoint present on node-04's ComfyUI (verified 2026-08-23: /app/ComfyUI/models/checkpoints holds exactly this one file). FLUX.1-dev is registered as a candidate but its weights are not on this fleet.`
- [ ] 3.9 **Source URL**: `https://huggingface.co/black-forest-labs/FLUX.1-schnell`
- [ ] 3.10 **License**: `Apache-2.0`
- [ ] 3.11 **Weights ref**: `node-04:/app/ComfyUI/models/checkpoints/flux1-schnell-fp8.safetensors`
- [ ] 3.12 **Weights checksum** - paste exactly (this one is a real SHA-256, measured on node-04 on 2026-08-23):
      ```
      ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72
      ```
- [ ] 3.13 **Default params (JSON object)** - type exactly this:
      ```
      {"engine_model": "flux1-schnell-fp8.safetensors"}
      ```
      **This line is not optional.** Without it Stage 3 crashes with
      `ValueError: 'flux1-schnell' is not a valid FluxModel`.
- [ ] 3.14 **Dynamically loadable**: leave it **ticked**. (ComfyUI does load checkpoints on demand.)
- [ ] 3.15 Click **Register**.
- [ ] 3.16 Find `flux1-schnell` and click **Approve**.
- [ ] 3.17 **Attested by**: `bruce`
- [ ] 3.18 **Vetting reference** - paste exactly:
      ```
      WP-33-MODELSTORE-PREP 2026-08-23: weights present and hashed on the serving node (node-04 ivgs-comfyui-primary, sha256 ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72, 17236328572 bytes); ComfyUI /object_info confirms it is the only loadable checkpoint. No IVGS quality benchmark exists for FLUX.1-schnell.
      ```
- [ ] 3.19 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "weights_present_on_serving_node": true, "weights_checksum_verified": "ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72", "quality": {"status": "not_benchmarked", "note": "MBCP certified FLUX.1-dev, not schnell. No measurement exists for this model on this fleet (INV-9: not fabricated)."}, "vram_gb_measured": null, "source": "WP-33-MODELSTORE-PREP 2026-08-23"}
      ```
- [ ] 3.20 Click the green **Approve**.
- [ ] 3.21 Click **Set default** on the same row.

---

## Step 4 of 5 - Stage 5, voiceover / text-to-speech

This one is easy - the right model is already registered as a candidate and
needs no edits. Nothing to type but the attestation.

There are two candidates for this stage, `XTTS-v2` and `Kokoro`. **Choose
XTTS-v2.** Kokoro's container is running and healthy, but the pipeline has no
address configured for it and would look for it on node-05, which is switched
off. XTTS-v2's address is configured correctly.

- [ ] 4.1 Find `XTTS-v2` in the list. Confirm it shows stage `voiceover_tts`, engine `coqui`, state `candidate`.
- [ ] 4.2 Click **Approve**.
- [ ] 4.3 **Attested by**: `bruce`
- [ ] 4.4 **Vetting reference** - paste exactly:
      ```
      WP-33-MODELSTORE-PREP 2026-08-23: MBCP certifications a00291ec-ff95-47f0-8c47-5c11f9739401 and b48b14c0-a243-4d81-a5d7-bb3f2cc72d0f (backfilled 2026-07-10). Serving verified live: node-04 ivgs-coqui, COQUI_TTS_MODEL=tts_models/multilingual/multi-dataset/xtts_v2, reachable at the configured endpoint http://ivgs-coqui:5002.
      ```
- [ ] 4.5 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "mbcp_certified": true, "certification_ids": ["a00291ec-ff95-47f0-8c47-5c11f9739401", "b48b14c0-a243-4d81-a5d7-bb3f2cc72d0f"], "serving_endpoint_verified": true, "quality": {"status": "pending_human_eval", "note": "Carried from the MBCP attestation as backfilled; no IVGS human-eval aggregate."}, "source": "WP-33-MODELSTORE-PREP 2026-08-23"}
      ```
- [ ] 4.6 Click the green **Approve**.
- [ ] 4.7 Click **Set default** on the `XTTS-v2` row.
- [ ] 4.8 Leave `Kokoro` as a candidate. Do not approve it.

---

## Step 5 of 5 - Stage 3, video clips

Also already registered. There are two candidates, `CogVideoX-5b` and
`Wan2.2-T2V`. **Choose CogVideoX-5b.** The video engine only recognises two
model names and `Wan2.2-T2V` is not one of them; approving it would crash the
stage.

- [ ] 5.1 Find `CogVideoX-5b`. Confirm stage `video_generation`, engine `cogvideox`, state `candidate`.
- [ ] 5.2 Click **Approve**.
- [ ] 5.3 **Attested by**: `bruce`
- [ ] 5.4 **Vetting reference** - paste exactly:
      ```
      WP-33-MODELSTORE-PREP 2026-08-23: MBCP certifications d37e7bd4-09f8-4bb9-9351-79abe509010d and b93ee372-1d83-40f8-a862-8f7e0a3b93f5 (backfilled 2026-07-10, measured 1920x1088, 875.7 s, 18.81 GB VRAM delta). Serving verified live: node-03 ivgs-cogvideox-server-node03, COGVIDEOX_MODEL=THUDM/CogVideoX-5b, reachable at the configured endpoint http://cogvideox-server:8200.
      ```
- [ ] 5.5 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "mbcp_certified": true, "certification_ids": ["d37e7bd4-09f8-4bb9-9351-79abe509010d", "b93ee372-1d83-40f8-a862-8f7e0a3b93f5"], "serving_endpoint_verified": true, "quality": {"status": "pending_human_eval", "note": "Carried from the MBCP attestation as backfilled; no IVGS human-eval aggregate."}, "vram_gb_measured": 18.81, "source": "WP-33-MODELSTORE-PREP 2026-08-23"}
      ```
- [ ] 5.6 Click the green **Approve**.
- [ ] 5.7 Click **Set default** on the `CogVideoX-5b` row.
- [ ] 5.8 Leave `Wan2.2-T2V` as a candidate. Do not approve it.
- [ ] 5.9 Optional, only if you want it visible: consider adding `{"vram_gb": 18.81}` via **Edit** -> **VRAM (GB)** on the `CogVideoX-5b` row, using the MBCP measurement. Not required.

---

## Stage 6 - talking head: nothing to do

`latentsync` is already approved, enabled and default. Leave it alone.

(Separately, and not part of this checklist: ledger item P1.4f.1 says
`latentsync-alt` - a deliberate test model, still `approved` - should be
retired once WP-02 is closed, so it can never be selected. That is a decision
for you, not a step here.)

---

## Stages we are NOT touching, and why

| Stage | Why we are leaving it empty |
|---|---|
| `animation_generation` | No part of the pipeline ever asks the Model Store for an animation model, and the `animatediff` engine has no driver in the code - it would fail immediately if anything did ask. |
| `composition` | Same - nothing asks. And there is a real defect underneath: the `ffmpeg` engine was added to the Model Store's list of engines but never given an address or a driver, so approving `FFmpeg-composition` would swap one error message for a worse one. Logged as ledger item P1.4n. |
| `translation` | Nothing asks. The model registered here (`Llama-3.3-70B-Instruct`) is not being served anywhere on the fleet right now. |

Leaving these three as candidates is the correct end state, not an omission.

---

## Fields we deliberately left blank

| Field | Why |
|---|---|
| `flux1-schnell` **VRAM (GB)** | Never measured for this model on this fleet. The 31.47 GB figure on record belongs to FLUX.1-dev, a different model. Guessing it would put a made-up number into a certification record. |
| **Weights checksum** on both Mistral rows | The value obtainable read-only from node-04 is a Hugging Face repository revision (`2722d19f...`), which identifies the source snapshot, not a hash of the weight files. It is recorded in the Weights ref field where it belongs. Putting it in a field called "checksum" would repeat a mistake already present on eleven backfilled rows, where the "checksum" is actually a container image digest. |
| **Capability tags** on every row | The Model Store supports them and holds zero. They feed automatic model selection, which is not in use - every binding today comes from the per-stage default. Adding them is real work with no effect yet. |

---

## Check it worked

After finishing all five steps, the page should show, per stage:

| Stage | Model | State | Default |
|---|---|---|---|
| `transcript_refinement` | `mistral-24b-transcript` | approved | yes |
| `storyboard_generation` | `mistral-24b-storyboard` | approved | yes |
| `image_generation` | `flux1-schnell` | approved | yes |
| `video_generation` | `CogVideoX-5b` | approved | yes |
| `voiceover_tts` | `XTTS-v2` | approved | yes |
| `talking_head` | `latentsync` | approved | yes |

If you want it confirmed against the database rather than the screen, run the
read-only query saved at `dev/workpackages/reference/wp33-validate-binding.sql`
(the header comment says how). It prints one line per stage and per tier and
should show a model name, not `SelectionError`, for all six of the above.

---

## Before any of it actually runs

Finishing this checklist stops the pipeline failing with "no approved default
model". It does **not** make the pipeline run. Three separate things sit behind
it, none of which can be fixed from this page:

1. **node-02 has no working graphics driver.** Its vLLM engine will not start -
   it exits with `nvml error: driver not loaded` (last attempt 2026-08-22
   23:47). Stages 1 and 2 are sent to node-02. Until this is fixed, or those
   stages are pointed at node-04's language model instead, they cannot run.
2. **The pipeline has no address configured for any vLLM engine.** It falls
   back to a built-in default of `http://node-02:8000` - which is the engine in
   point 1. If you decide to use node-04's language model instead, someone has
   to set `IVGS_VLLM_URL=http://192.168.1.93:8000` on the workers. That is a
   deployment change, not a Model Store change.
3. **node-02 and node-03 are running old software** (`v5.4.7-h0`, from before
   the Model Store existed). Those two machines cannot read the Model Store at
   all. Until they are updated, Stages 1, 2 and video generation will ignore
   everything you just configured.

Stages 3 (images), 5 (voiceover) and 6 (talking head) run on node-04, which is
up to date and correctly configured. **Those three become bindable the moment
you finish this checklist.**

Full detail and evidence for all three:
`reports/WP-33-MODELSTORE-PREP-report_2026-08-23.md`, sections 4 and 6.1.
