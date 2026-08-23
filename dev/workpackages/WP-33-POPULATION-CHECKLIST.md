# WP-33 - Model Store population checklist

**For the operator. One action per line. Do them in order.**

| | |
|---|---|
| **Produced by** | WP-33-MODELSTORE-PREP, 2026-08-23 |
| **Evidence** | `reports/WP-33-MODELSTORE-PREP-report_2026-08-23.md` |
| **Where** | The Model Store admin page: `/admin/models`. Sign in as an admin user - every action below is admin-only. |
| **What this achieves** | `get_binding` will resolve for all six pipeline stages that ask for a model. Six of nine; the other three are deliberately left alone (see "Stages we are NOT touching"). |
| **What this does NOT achieve** | A running pipeline. See "Before any of it actually runs" at the end - two of the three blockers recorded there are now cleared. |
| **AMENDED** | **2026-08-23 by WP-34-DEPLOY-BATCH R7.3.** Steps 1 and 2 now register **`llama-3.3-70b`** rows, not the `mistral-24b` interim rows. Reason: node-02 was dead when this checklist was written (its vLLM exited `nvml error: driver not loaded`, last attempt 2026-08-22 23:47) and stages 1 and 2 were pointed at node-04's mid-size model as a stopgap. node-02 came back at **2026-08-23 01:23:23Z** and now serves `llama-3.3-70b` - verified live, HTTP 200 on `/v1/models`, from inside both the node-02 and node-04 workers. WP-34 also deployed `v5.6.0-m2` to node-02 and node-03, which clears blocker 3. See `reports/WP-34-DEPLOY-BATCH-report_2026-08-23.md`. |

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

> **AMENDED 2026-08-23 (WP-34 R7.3).** This step used to register
> `mistral-24b-transcript` against node-04's mid-size vLLM, because node-02 -
> the node stage 1 actually runs on - had no working GPU driver. node-02 is
> back and serving `llama-3.3-70b`. Register that instead. Every value below
> was measured on node-02 on 2026-08-23, not inferred.

- [ ] 1.1 Click **Register Model**.
- [ ] 1.2 **Name (unique id)**: `llama-3.3-70b-transcript`
- [ ] 1.3 **Display name**: `Llama 3.3 70B Instruct FP8 (transcript refinement)`
- [ ] 1.4 **Stage**: select `transcript_refinement`
- [ ] 1.5 **Engine**: select `vllm`
- [ ] 1.6 **Tier**: select `both`
- [ ] 1.7 **VRAM (GB)**: `86.0` - the allocation vLLM is configured to take on node-02: `--gpu-memory-utilization 0.90` of a 97887 MiB RTX PRO 6000 Blackwell = 88098 MiB = 86.0 GiB. Configured, not measured. (The old `30.6` was node-04's mid-size allocation and does not apply.)
- [ ] 1.8 **Description**: `Llama-3.3-70B-Instruct-FP8-dynamic, served on node-02 as llama-3.3-70b. Registered by WP-33 to give Stage 1 a binding; the store had no transcript_refinement model of any kind. Amended by WP-34 from the mistral-24b interim row after node-02 was restored.`
- [ ] 1.9 **Source URL**: `https://huggingface.co/RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic`
- [ ] 1.10 **License**: `llama3.3` - the upstream Llama 3.3 Community License tag. Not verified from this box (no model-card fetch was made); confirm before attesting if the form validates it.
- [ ] 1.11 **Weights ref**: `RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic@565debb06c0e301ddc1d54dae00c16b376253fde` - the revision is the snapshot directory actually on node-02 at `/data/models/hub/`.
- [ ] 1.12 **Weights checksum**: **leave blank.** (See "Fields we deliberately left blank" below - the value we could get is a repository revision, not a checksum, and it is already in the Weights ref field above.)
- [ ] 1.13 **Default params (JSON object)** - type exactly this:
      ```
      {"engine_model": "llama-3.3-70b"}
      ```
      **This line is not optional.** Without it the pipeline sends the text
      `llama-3.3-70b-transcript` to vLLM as the model name and vLLM answers 404.
      This is finding **F-6**: the store's row name and the served name are not
      the same string, and `engine_model` is what bridges them.
- [ ] 1.14 **Dynamically loadable**: **UNTICK** it. (vLLM serves one fixed model; it cannot load another on request.)
- [ ] 1.15 Click **Register**. The model appears in the list as `candidate`.
- [ ] 1.16 Find `llama-3.3-70b-transcript` in the list and click **Approve**.
- [ ] 1.17 **Attested by**: your username (`bruce`)
- [ ] 1.18 **Vetting reference** - paste exactly:
      ```
      WP-34-DEPLOY-BATCH 2026-08-23: served-model identity verified live on node-02 (ivgs-vllm-primary, --served-model-name llama-3.3-70b, root RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic, HF snapshot 565debb06c0e301ddc1d54dae00c16b376253fde, max_model_len 32768). Authed HTTP 200 on /v1/models observed from inside the node-02 and node-04 workers. No IVGS quality benchmark exists for this model on this stage.
      ```
- [ ] 1.19 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "served_identity_verified": true, "quality": {"status": "not_benchmarked", "note": "No human-eval or MBCP certification for llama-3.3-70b on transcript_refinement. Approved on served-identity evidence only (INV-9: not fabricated)."}, "vram_gb_measured": null, "vram_gb_configured": 86.0, "source": "WP-34-DEPLOY-BATCH 2026-08-23"}
      ```
- [ ] 1.20 Click the green **Approve**. State becomes `approved`.
- [ ] 1.21 Click **Set default** on the same row. A "default" marker appears.

---

## Step 2 of 5 - Stage 2, storyboard generation

This stage has one model, `test-model-1`, and it is **retired**. Retired is
permanent - there is no way to bring it back, and there is no reason to want
it. We are creating a real one.

> **AMENDED 2026-08-23 (WP-34 R7.3)** - same reason as step 1. The store's
> existing `Llama-3.3-70B-Instruct` row cannot be reused here: it sits on stage
> `translation`, and AD-01.5.2 records one model row per stage. This is a new
> row.

- [ ] 2.1 Click **Register Model**.
- [ ] 2.2 **Name (unique id)**: `llama-3.3-70b-storyboard`
- [ ] 2.3 **Display name**: `Llama 3.3 70B Instruct FP8 (storyboard generation)`
- [ ] 2.4 **Stage**: select `storyboard_generation`
- [ ] 2.5 **Engine**: select `vllm` - **it must be `vllm`.** Stage 3 borrows this same model to write its image prompts, and the code refuses any engine that cannot hold a chat conversation (`utils/llm_binding.py`, `CHAT_ENGINES`).
- [ ] 2.6 **Tier**: select `both`
- [ ] 2.7 **VRAM (GB)**: `86.0` - same figure and same caveat as step 1.7.
- [ ] 2.8 **Description**: `Same served model as llama-3.3-70b-transcript. A separate row is required because the Model Store records one model per stage. Also borrowed by Stage 3's image-prompt writer.`
- [ ] 2.9 **Source URL**: `https://huggingface.co/RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic`
- [ ] 2.10 **License**: `llama3.3` - same caveat as step 1.10.
- [ ] 2.11 **Weights ref**: `RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic@565debb06c0e301ddc1d54dae00c16b376253fde`
- [ ] 2.12 **Weights checksum**: leave blank.
- [ ] 2.13 **Default params (JSON object)** - type exactly this:
      ```
      {"engine_model": "llama-3.3-70b"}
      ```
- [ ] 2.14 **Dynamically loadable**: **UNTICK** it.
- [ ] 2.15 Click **Register**.
- [ ] 2.16 Find `llama-3.3-70b-storyboard` and click **Approve**.
- [ ] 2.17 **Attested by**: `bruce`
- [ ] 2.18 **Vetting reference** - paste exactly:
      ```
      WP-34-DEPLOY-BATCH 2026-08-23: same served model as llama-3.3-70b-transcript, verified live on node-02. Registered separately because AD-01.5.2 records one model row per stage. No IVGS quality benchmark exists for this model on this stage.
      ```
- [ ] 2.19 **Checklist (JSON object)** - paste exactly:
      ```
      {"reviewed": true, "served_identity_verified": true, "quality": {"status": "not_benchmarked", "note": "No human-eval or MBCP certification for llama-3.3-70b on storyboard_generation. Approved on served-identity evidence only (INV-9: not fabricated)."}, "vram_gb_measured": null, "vram_gb_configured": 86.0, "source": "WP-34-DEPLOY-BATCH 2026-08-23"}
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
| `transcript_refinement` | `llama-3.3-70b-transcript` | approved | yes |
| `storyboard_generation` | `llama-3.3-70b-storyboard` | approved | yes |
| `image_generation` | `flux1-schnell` | approved | yes |
| `video_generation` | `CogVideoX-5b` | approved | yes |
| `voiceover_tts` | `XTTS-v2` | approved | yes |
| `talking_head` | `latentsync` | approved | yes |

If you want it confirmed against the database rather than the screen, run the
read-only query saved at `dev/workpackages/reference/wp33-validate-binding.sql`
(the header comment says how). It prints one line per stage and per tier and
should show a model name, not `SelectionError`, for all six of the above.

That file's **Query B was amended on 2026-08-23** to project the
`llama-3.3-70b` rows instead of the `mistral-24b` ones, and re-run. It passes -
all six bindable stages resolve with `candidates_matching = 1`, so none of them
is ambiguous. The projection is reproduced in
`reports/WP-34-DEPLOY-BATCH-report_2026-08-23.md` S7.

---

## Before any of it actually runs

Finishing this checklist stops the pipeline failing with "no approved default
model". It does **not** by itself make the pipeline run.

**AMENDED 2026-08-23 by WP-34-DEPLOY-BATCH.** Two of the three blockers below
are now cleared and the third turned out to be more specific than it looked.

1. ~~**node-02 has no working graphics driver.**~~ **CLEARED.** node-02's vLLM
   is up - container `ivgs-vllm-primary`, started `2026-08-23T01:23:23Z`,
   healthy - and serving `llama-3.3-70b` on a 97887 MiB RTX PRO 6000 Blackwell.
   Verified live: authed `GET /v1/models` returns HTTP 200 with
   `models=[llama-3.3-70b]`.

2. **The pipeline has no address configured for any vLLM engine** - still true
   as written, but the conclusion has changed. `resolve_endpoint('vllm')`
   (`shared/providers/binding.py:26`) falls back to `http://node-02:8000`, and
   node-02 is now alive at that address, so **no override is needed for the
   cross-node consumers.** Measured on 2026-08-23 from inside the running
   workers: node-04 -> `http://node-02:8000` = HTTP 200, node-03 -> the same =
   HTTP 200.

   **One exception, and it is node-02 itself.** From inside
   `ivgs-celery-node02`, both `http://node-02:8000` and `http://192.168.1.91:8000`
   time out (`curl rc=28`). `ufw` on node-02 admits `192.168.1.0/24` to the
   host, and the compose bridge is `172.x`, so a container on node-02 cannot
   reach node-02's own published port. This matters because stages 1 and 2 -
   which run on node-02's `gpu_llm` queue - now dial `binding.endpoint`
   (`tasks/stage1_transcript.py:349`) rather than the old `VLLM_PRIMARY_URL`
   env profile. WP-34 therefore set `IVGS_VLLM_URL: http://vllm:8000` on
   node-02's `celery-worker` only - the identical server over the compose
   network, verified HTTP 200 - using the env override `resolve_endpoint` is
   documented to take first.

   > **Operator decision, recorded not taken:** the alternative is to open
   > `ufw` on node-02 to the docker bridge and drop the override, which would
   > make `http://node-02:8000` uniform fleet-wide. WP-34 chose the override
   > because it is the mechanism the code documents and its blast radius is one
   > service. Either is defensible; the override is in tracked compose
   > (`ivgs-infra/docker-compose.node02.yml`) and is trivial to reverse.

   The old suggestion to set `IVGS_VLLM_URL=http://192.168.1.93:8000` (node-04's
   mid-size model) is **superseded** - that was the workaround for node-02 being
   dead.

3. ~~**node-02 and node-03 are running old software** (`v5.4.7-h0`).~~
   **CLEARED.** WP-34 deployed `v5.6.0-m2` to node-02, node-03 and node-04 on
   2026-08-23. `from shared.providers.factory import get_binding` was verified
   to import cleanly inside all three running workers, so all three can now
   read the Model Store.

Stages 3 (images), 5 (voiceover) and 6 (talking head) run on node-04, which is
up to date and correctly configured. Stages 1, 2 and video generation are now
on the same footing. **All six become bindable the moment you finish this
checklist.**

Full detail and evidence: `reports/WP-33-MODELSTORE-PREP-report_2026-08-23.md`
sections 4 and 6.1 for the original findings, and
`reports/WP-34-DEPLOY-BATCH-report_2026-08-23.md` for the 2026-08-23
measurements that cleared blockers 1 and 3 and narrowed blocker 2.
