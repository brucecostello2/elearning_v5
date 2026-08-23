# WP-33-MODELSTORE-PREP - report

| | |
|---|---|
| **Package** | WP-33-MODELSTORE-PREP (Tier B, single unattended overnight session) |
| **Brief** | `dev/workpackages/WP-33-MODELSTORE-PREP.md` |
| **Ledger** | P1.4m (Model Store cannot bind 8 of 9 stages), P1.4f (store hygiene) |
| **Date** | 2026-08-23 |
| **HEAD SHA** | `9af5a48` |
| **Agent** | Claude, node-01. Read-only ssh to node-02/03/04. |
| **Writes performed** | **ZERO.** Proof in S2.3. No commit, push or deploy beyond the docs commit this package authors, which is HELD. |

---

# HEADLINE

**P1.4m is NEWLY-EXPOSED TRUTH, not a regression.** Nothing was broken by an
operator action. The Model Store never could bind stages 1-5, and the pipeline
never once relied on it to do so. The 08-15 "end-to-end run" in the brief's
premise did not happen: **stages 1, 2 and 3 did not run on 2026-08-15**, the
run died at Stage 5 with the identical `SelectionError` we see today, and the
4K render was produced from June artefacts through stages 7 and 8 only.

There is nothing to un-break. There is only population to do - and four
blockers in front of it that populating the store cannot fix.

---

# S1. Method, and what is live versus inferred

**Live measurement (this session, 2026-08-23):**
- `SELECT`-only against the live `ivgs` database on `ivgs-postgres`, every psql
  session opened with `SET default_transaction_read_only = on`.
- Read-only ssh to node-02 (.91), node-03 (.92), node-04 (.93): `docker ps`,
  `docker inspect`, `docker exec <c> env`, HTTP GETs against engine APIs,
  `nvidia-smi`, one `sha256sum` of an on-disk checkpoint.
- Two read-only Python probes executed inside `ivgs-celery-node04` and
  `ivgs-celery-node02`, importing the deployed `shared.providers` and calling
  `resolve_endpoint` / `registered_engines` / the engine enums. No DB access,
  no state change.

**Inferred from code at HEAD (not executed):** the exact line numbers of the
`get_binding` call sites, and the behaviour of stage bodies not run here.

**Taken from prior reports as evidence, re-read in full:**
`WP-03-STAGE8-VALIDATION-report_2026-08-15.md` S1.8/S1.9/Pass 2,
`WP-IVGS-0-report_2026-08-22.md` S7, `WP-02-ORCH6-report_2026-08-15.md`.

---

# S2. Task 1 - full store truth

## 2.1 `models` - all 13 rows

| name | stage | tier | state | engine | dflt | en | created_by | created_at | updated_at |
|---|---|---|---|---|---|---|---|---|---|
| test-model-1 | storyboard_generation | both | **retired** | vllm | f | **f** | admin | 2026-07-10 00:59 | 2026-07-10 01:01 |
| FLUX.1-dev | image_generation | both | candidate | comfyui | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| CogVideoX-5b | video_generation | both | candidate | cogvideox | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| Wan2.2-T2V | video_generation | both | candidate | cogvideox | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| AnimateDiff-SD15 | animation_generation | both | candidate | animatediff | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| MimicMotion | animation_generation | both | candidate | animatediff | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| Wan2.2-Animate | animation_generation | both | candidate | animatediff | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| Kokoro | voiceover_tts | both | candidate | coqui | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| XTTS-v2 | voiceover_tts | both | candidate | coqui | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |
| **latentsync** | talking_head | both | **approved** | latentsync | **t** | t | bruce | 2026-07-10 02:22 | **2026-08-15 05:37** |
| latentsync-alt | talking_head | both | **approved** | latentsync | f | t | bruce | **2026-08-15 01:18** | 2026-08-15 05:37 |
| FFmpeg-composition | composition | both | candidate | ffmpeg | f | t | bruce | 2026-07-10 03:13 | 2026-07-10 03:13 |
| Llama-3.3-70B-Instruct | translation | both | candidate | vllm | f | t | bruce | 2026-07-10 02:22 | 2026-07-10 02:22 |

**No `transcript_refinement` row exists.** `storyboard_generation` has exactly
one row and it is `retired` + `enabled=false`.

Every row carries `tier='both'`, `source_url=NULL`, `license=NULL`,
`vram_gb=NULL`, `dynamically_loadable=true`. The eleven MBCP-backfilled rows
carry a `weights_ref` of the form
`http://serving-api:8000/engines/<digest>/manifest` and a `weights_checksum`
that is the **engine image digest, not a weights hash** - the backfill's own
attestation payloads say `"weights_checksum": null`. Recorded as a new hygiene
item (F-7).

## 2.2 The other four tables

| table | rows |
|---|---|
| `model_approvals` | **26** |
| `model_capability_tags` | **0** |
| `model_node_availability` | **0** |
| `project_model_selections` | **0** |

`model_approvals`: 24 rows attested 2026-07-10 (the MBCP backfill, certificate
UUIDs in `vetting_reference`), 1 on 2026-07-10 01:01 (`test-model-1`,
`"anything text"`), and 2 on 2026-08-15 (`latentsync` / `"MBCP bake-off
2026-07"`; `latentsync-alt` / `"a test model"`). One model can hold several -
`Llama-3.3-70B-Instruct` holds six.

Because `model_node_availability` is empty, `_pick_node`
(`shared/providers/factory.py:57-72`) returns `None` for every model, so every
binding this fleet can produce carries `node_id=None`. Nothing downstream reads
it today, so this is latent rather than breaking.

## 2.3 Row history - the `audit_log` trail, and the zero-write proof

`audit_log` holds 697 rows. Filtered to the store:

| resource_type | action | count | first | last |
|---|---|---|---|---|
| `certified-models` | CREATE | 25 | 2026-07-10 02:22 | 2026-07-12 03:18 |
| `models` | CREATE | 7 | 2026-07-10 00:59 | 2026-08-15 01:19 |
| `models` | UPDATE | 5 | 2026-08-15 00:35 | 2026-08-15 05:37 |
| `models` | **DELETE** | **0** | - | - |

The twelve `models` rows in full, in order:

| when | what happened |
|---|---|
| 2026-07-10 00:59:11 | `test-model-1` registered (CANDIDATE) |
| 2026-07-10 01:01:05 | `test-model-1` approved (`"anything text"`) |
| 2026-07-10 01:01:46 | `test-model-1` -> DEPRECATED |
| 2026-07-10 01:01:48 | `test-model-1` -> RETIRED, `enabled=false` |
| 2026-08-15 00:35:24 | `latentsync` approved (`"MBCP bake-off 2026-07"`) |
| 2026-08-15 00:35:27 | `latentsync` `is_default=true` |
| 2026-08-15 01:18:57 | `latentsync-alt` registered (CANDIDATE) |
| 2026-08-15 01:19:27 | `latentsync-alt` approved (`"a test model"`) |
| 2026-08-15 02:55:38 | `latentsync-alt` `is_default=true` (swaps `latentsync` off) |
| 2026-08-15 02:56:18 | `latentsync` `is_default=true` (swap back) |
| 2026-08-15 03:11:58 | `latentsync-alt` `is_default=true` (swap again) |
| 2026-08-15 05:37:56 | `latentsync` `is_default=true` (final state) |

That is the complete write history of this store. **Four rows of it are the
WP-02 check-6b GUI swap demonstration.**

**Zero-write proof.** Opening and closing measurements, taken at the start and
end of this session, are identical:

```
models                     13 rows   max(updated_at)  2026-08-15 05:37:56.430254+00
model_approvals            26 rows   max(attested_at) 2026-08-15 01:19:27.745054+00
project_model_selections    0 rows
model_node_availability     0 rows
model_capability_tags       0 rows
audit_log                 697 rows   max(timestamp)   2026-08-21 21:01:55.401381+00
```

## 2.4 Baseline binding resolution, re-measured

Replicating the `get_binding` default-fallback predicate exactly
(`shared/providers/factory.py:173-183`: `stage` match, `tier IN (tier,'both')`,
`is_default`, `state='approved'`, `enabled`) across all 18 (stage, tier) pairs:

```
talking_head          prototype/production -> latentsync
all eight other stages, both tiers         -> SelectionError
```

WP-IVGS-0 S7 is confirmed unchanged, 24 hours later.

---

# S3. Task 2 - the 08-15 mystery: answered

## 3.1 The brief's premise is false, and that is the answer

> "Yet the pipeline ran end-to-end through all 8 stages on 2026-08-15
> (WP-03: first 4K render)."

It did not. WP-03's own report, written that day, says the opposite in its
first section heading: **"1.1 Headline: a full Stages 1-8 run is not possible
today."** What actually happened on 2026-08-15:

| | |
|---|---|
| Stages 1, 2 | **Did not run.** WP-03 S1.2 reuses the existing refined transcript and 6 storyboard scenes "from the June run". |
| Stage 3 | **Did not run.** Same reason. |
| Stage 4 | Ran 11:24 (job `7980c0b9`), produced a fresh manifest. |
| Stage 5 | Ran and **FAILED**: `SelectionError: no selection and no enabled APPROVED default model for stage='voiceover_tts' tier='prototype'` (WP-03 S1.9, captured verbatim). |
| Stages 6, 7, 8 | Re-run in Pass 2 against the **June** manifest (job `79b90f48`). That is the 4K render. |

Measured this session, the Stage 1/2 artefacts that run consumed:

```
project 3814f845-4668-496b-a88a-53fea95897c2  "2B-scenes2-222906"
  transcripts        1 row,  created 2026-06-01 22:29:06
  storyboard_scenes  6 rows, created 2026-06-01 22:29:12
```

**2026-06-01.** The Model Store did not exist then: migration
`0026_ad01_model_store`, `shared/models/model_store.py` and
`shared/providers/factory.py` all arrived in a single commit, `303681e`, on
**2026-07-09** - five and a half weeks later. Stages 1 and 2 produced those
artefacts with hard-coded engine clients and never consulted a store, because
there was no store to consult.

## 3.2 Testing hypothesis (a) - "the store's state changed since 08-15"

**FALSE, and disprovable three ways.**

1. **No model row has ever been deleted.** `audit_log` holds zero
   `resource_type='models', action_type='DELETE'` rows, and zero for
   `certified-models`. Nothing vanished.
2. **No model has ever been moved out of `approved` except `test-model-1`,
   and that was on 2026-07-10** - five weeks before the run, not after it. Its
   `updated_at` (2026-07-10 01:01:48) has not moved since.
3. **The 08-15 measurement is on record and matches today's exactly.** WP-03
   S1.8, written that day, tabulates the same store:

   | Stage key | models | approved+enabled | default |
   |---|---|---|---|
   | `transcript_refinement` | **0** | 0 | 0 |
   | `storyboard_generation` | 1 | **0** | **0** |
   | `image_generation` | 1 | **0** | **0** |
   | `video_generation` | 2 | **0** | **0** |
   | `voiceover_tts` | 2 | **0** | **0** |
   | `talking_head` | 2 | 2 | 1 |

   Identical to S2.4 above. The store has not changed since 2026-08-15 05:37:56.

**The MBCP revocations are a non-event for IVGS.** AD-01/AD-04 record the
backfill as "21 exports plus 2 composition transmitted; all non-revoked
certifications landed as CANDIDATEs; **24 revoked correctly skipped**". Skipped
means never transmitted - they never created an IVGS row, so they cannot have
removed one. The audit trail agrees: 25 `certified-models` CREATEs, no deletes.

## 3.3 Testing hypothesis (b) - "the code path changed"

**TRUE, but in the direction opposite to the one the brief supposes.** The code
did not go from "optional/fallback-guarded" to "mandatory". It went from **not
consulting the store at all** to consulting it, one node at a time, as ARCH-1
images rolled out. There was never a fallback to lose.

`git show 303681e -- ivgs-workers/tasks/stage1_transcript.py` shows the
`get_binding("transcript_refinement", ...)` call being **added** on 2026-07-09,
already unguarded, replacing `config.vllm.primary_model`. Same commit, same
shape, for stages 2, 3 and 5. Stage 6 followed on 2026-08-15 in `09e4212`
("feat(stage6): resolve talking-head engine via AD-01 provider binding").

That last date is the whole story of the 08-15 store activity: the operator
approved `latentsync` at 00:35 and set it default at 05:37 **because WP-02 had
just made Stage 6 require a binding.** Exactly one stage needed one, and
exactly that one stage was populated. No other stage was touched, because no
other stage was being deployed that day.

## 3.4 What is deployed today is not HEAD, and that changes the picture

Measured live this session:

| Node | Container | Image | Consumes | ARCH-1 present? |
|---|---|---|---|---|
| node-01 | `ivgs-celery-default` / `-composition` | `v5.5.4-metrics` | default, notifications, cleanup, composition | yes |
| node-02 | `ivgs-celery-node02` | **`v5.4.7-h0`** | `gpu_llm` | **NO** |
| node-03 | `ivgs-cogvideox-worker-node03` | **`v5.4.7-h0`** | `gpu_video` | **NO** |
| node-04 | `ivgs-celery-node04` | `v5.5.4-metrics` | `gpu_image`, `gpu_tts`, `gpu_talking_head` | yes |

Verified by executing inside the containers:

```
node-02: from shared.providers.factory import get_binding
         -> ModuleNotFoundError: No module named 'shared.providers.factory'
node-03: -> ModuleNotFoundError   (same image)
```

Queue routing at `ivgs-workers/celery_app.py:127-151` sends
`transcript_refinement` and `storyboard_generation` to `gpu_llm` and
`video_generation` to `gpu_video`. Both queues are consumed only by
pre-ARCH-1 workers.

**Consequence, and it corrects a claim in P1.4m.** P1.4m states "Stage 1 raises
`SelectionError` on every run today". That is true of HEAD and of the
`v5.5.4-metrics` image - but Stage 1 does not run on either. It runs on
node-02, whose image cannot import `get_binding` at all. On the fleet as
deployed, **Stage 1 does not raise `SelectionError`; it ignores the store
entirely.** The stages that genuinely raise today are the three on node-04:
`image_generation`, `voiceover_tts` (observed on 08-15) and, were it not
already populated, `talking_head`.

This is a correction of scope, not of substance: Stage 1 is still unrunnable
today, for a different and more basic reason (S5, D-1).

## 3.5 Verdict

**NEWLY-EXPOSED TRUTH. Combination (c), weighted almost entirely to (b).**

The old code did not lie about what it ran - it never claimed to consult a
store, because the store post-dates it. What changed is that ARCH-1 installed a
gate in front of an empty room, node by node, and the first node to get the
gate (node-04, WP-02, 2026-08-15) immediately hit it. The operator populated
the one stage that was blocking that day and moved on. The other five stage
keys have simply never been populated, and until the ARCH-1 image reaches
node-02 and node-03 they still will not be consulted.

**Nothing needs un-breaking. The work is population, plus four blockers that
population cannot reach (S5).**

---

# S4. Task 3 - what actually serves this fleet today

All measured live, read-only, 2026-08-23.

## 4.1 Reachability

`192.168.1.91` (node-02) UP, `.92` (node-03) UP, `.93` (node-04) UP.
`.94` (node-05) and `.95` (node-06) DOWN, as expected.

## 4.2 Engines, by node

| Node | Container | Image | Serves | Port | Network alias |
|---|---|---|---|---|---|
| node-02 | `ivgs-vllm-primary` | `vllm/vllm-openai:cu130-nightly` | **EXITED (128)** | - | `vllm` |
| node-03 | `ivgs-cogvideox-server-node03` | `cogvideox-pilot-1` | `THUDM/CogVideoX-5b` | 8200 | `cogvideox-server` |
| node-04 | `ivgs-vllm-midsize` | `vllm/vllm-openai:cu130-nightly` | **`mistral-24b`** | 8000 | `vllm` |
| node-04 | `ivgs-comfyui-primary` | `comfyui-v5.2.7-h0` | **one checkpoint only** | 8188 | `comfyui` |
| node-04 | `ivgs-coqui` | `coqui-v5.2.7-h0` | `tts_models/multilingual/multi-dataset/xtts_v2` | 5002 | `coqui-tts` |
| node-04 | `ivgs-kokoro` | `kokoro-v5.2.7-h0` | `kokoro-en-v0.19` | 5003 | `kokoro-tts` |
| node-04 | `ivgs-latentsync` | `latentsync-v5.2.7-h0` | `latentsync-v1` | 7860 | `latentsync` |
| node-04 | `ivgs-whisperx` | `whisperx-v5.2.7-h0` | `large-v3` | 9000 | `whisperx` |
| node-04 | *(no sadtalker container)* | - | - | 7861 refused | - |

node-04 GPU: `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, 97887 MiB
total, 38316 MiB in use.

**node-02's vLLM is not merely stopped, it cannot start:**

```
ExitCode 128
nvidia-container-cli: initialization error: nvml error: driver not loaded
FinishedAt 2026-08-22T23:47:19Z
```

The NVIDIA driver is not loaded on node-02. **`llama-3.3-70b` is served
nowhere on this fleet.** The only live chat LLM is node-04's `mistral-24b`
(`RedHatAI/Mistral-Small-24B-Instruct-2501-quantized.w4a16`,
`--served-model-name mistral-24b`, `--max-model-len 4096`,
`--gpu-memory-utilization 0.32`, `--api-key ivgs-internal`).

**ComfyUI holds exactly one checkpoint.** `GET /object_info/CheckpointLoaderSimple`
returns a single entry, and the filesystem agrees:

```
/app/ComfyUI/models/checkpoints/flux1-schnell-fp8.safetensors   17,236,328,572 bytes
sha256 ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72
```

`/app/models/unet/` and `/app/models/diffusion_models/` are empty.
**`flux1-dev` is not on this fleet.** The store's `FLUX.1-dev` candidate cannot
be served.

## 4.3 Endpoints are NOT a `models` column - they are env

This is the single most consequential finding for the checklist, and the brief
assumes otherwise (Task 3 lists "endpoint" as a field to register).

There is no `endpoint` column on `models`. `_binding_from_model`
(`shared/providers/factory.py:96`) calls
`resolve_endpoint(model_row.engine.value, node_id)`, and `resolve_endpoint`
(`shared/providers/binding.py:36-53`) reads `IVGS_<ENGINE>_URL` from the
**worker process environment**, falling back to a hard-coded default.
`node_id` is accepted and ignored. **The operator cannot set an endpoint in the
GUI at all.**

Measured `IVGS_*_URL` overrides on every worker:

| Worker | Overrides present |
|---|---|
| node-01 `ivgs-celery-default` | **none** |
| node-02 `ivgs-celery-node02` | **none** |
| node-03 `ivgs-cogvideox-worker-node03` | **none** |
| node-04 `ivgs-celery-node04` | `IVGS_COMFYUI_URL`, `IVGS_COQUI_URL`, `IVGS_LATENTSYNC_URL`, `IVGS_SADTALKER_URL` |

So, per engine, what a binding would actually resolve to - executed inside
`ivgs-celery-node04`:

| engine | resolves to | reachable? |
|---|---|---|
| `comfyui` | `http://comfyui:8188` | YES |
| `coqui` | `http://ivgs-coqui:5002` | YES |
| `latentsync` | `http://latentsync:7860` | YES |
| `cogvideox` | `http://cogvideox-server:8200` | on node-03 only |
| `vllm` | `http://node-02:8000` | **NO - dead engine** |
| `kokoro` | `http://node-05:8021` | **NO - node-05 is offline**; the real Kokoro is `kokoro-tts:5003` on node-04 |
| `sadtalker` | `http://sadtalker:7861` | **NO - no such container** |
| `ffmpeg` | **raises `EndpointResolutionError`** | n/a |

`IVGS_KOKORO_URL` is unset everywhere, so **Kokoro is unbindable today even
though the container is healthy.** That removes it from consideration as the
`voiceover_tts` default and leaves XTTS-v2 as the only viable choice.

## 4.4 Two more gates behind `get_binding`

Resolving a binding is necessary but not sufficient. Executed inside
`ivgs-celery-node04` against the deployed code:

```
registered_engines() = ['cogvideox','comfyui','coqui','kokoro','latentsync','sadtalker','vllm']
```

`ffmpeg`, `animatediff`, `wan21`, `ollama` and `remotion` have **no registered
builder**; `build_provider` raises `EngineNotRegisteredError` for them.

And the engine-native handle is coerced into a closed enum at the Stage 3 call
sites (`stage3_images.py:355`, `:378` and `:400`). Executed:

```
FluxModel('flux1-schnell-fp8.safetensors')  -> OK
FluxModel('FLUX.1-dev')                     -> ValueError: not a valid FluxModel
FluxModel('flux1-dev-fp8.safetensors')      -> OK (enum accepts; file absent from disk)
CogVideoXModel('CogVideoX-5b')              -> OK
CogVideoXModel('Wan2.2-T2V')                -> ValueError: not a valid CogVideoXModel
```

`engine_model_id(binding)` (`ivgs-workers/providers/_common.py:21-24`) returns
`default_params["engine_model"]` if present, else `binding.name` verbatim. None
of the 13 existing rows sets `engine_model`. **So promoting `FLUX.1-dev` or
`Wan2.2-T2V` to approved+default would produce a resolving binding that then
raises `ValueError` inside the stage** - a worse failure than the one we have,
because it happens after the reservation and looks like a code bug.

The TTS builders (`ivgs-workers/providers/tts.py:23` and `:33`) ignore
`engine_model_id` entirely, so `XTTS-v2` needs no override.

## 4.5 Which stage keys are actually bound

Every `get_binding` call site in the tree at HEAD:

| Stage key | call site | queue | node | binds today? |
|---|---|---|---|---|
| `transcript_refinement` | `stage1_transcript.py:504`; borrowed by `stage5_voiceover.py` via `utils/llm_binding.py:55` | `gpu_llm` | node-02 | **no - pre-ARCH-1 image** |
| `storyboard_generation` | `stage2_storyboard.py:524`; borrowed by `stage3_images.py:624` | `gpu_llm` / `gpu_image` | node-02 / node-04 | partly |
| `image_generation` | `stage3_images.py:369`, `:390`, `:624` | `gpu_image` | node-04 | **yes** |
| `video_generation` | `stage3_images.py:346` | `gpu_video` | node-03 | **no - pre-ARCH-1 image** |
| `voiceover_tts` | `stage5_voiceover.py:542` | `gpu_tts` | node-04 | **yes** |
| `talking_head` | `talking_head_task.py:399` | `gpu_talking_head` | node-04 | **yes** |
| `animation_generation` | *none* | - | - | never |
| `composition` | *none* | - | - | never |
| `translation` | *none* | - | - | never |

**Three of the nine ModelStages have no binding consumer anywhere in the
codebase.** Populating them changes nothing and, for `composition`, cannot
work at all (S5, F-1). The plan populates six and leaves three alone.

One hard constraint the plan must respect: `utils/llm_binding.py:32` defines
`CHAT_ENGINES = {"vllm","ollama"}` and **refuses** a borrowed binding on any
other engine. Both `transcript_refinement` and `storyboard_generation` are
borrowed by other stages, so both **must** be registered on engine `vllm`.

---

# S5. New findings

| # | Finding | Severity |
|---|---|---|
| **F-1** | **`composition` can never bind.** `ffmpeg` was added to the `ModelEngine` enum by `e613e84` (migration 0027) to unblock MBCP exports, but never added to `_ENGINE_ENDPOINTS` in `shared/providers/binding.py` and never given a builder. Executed: `resolve_endpoint('ffmpeg')` raises `EndpointResolutionError`; `'ffmpeg' not in registered_engines()`. Approving `FFmpeg-composition` and setting it default would convert a `SelectionError` into an `EndpointResolutionError`. Latent today only because no task binds `composition`. This is exactly the untested coupling CLAUDE.md S11 warns about. | **HIGH** - blocks any future Stage 4/7/8 binding |
| **F-2** | **`RETIRED` is terminal; `storyboard_generation` therefore needs a fresh registration.** The API exposes `approve` (candidate->approved), `deprecate` (approved->deprecated) and `retire` (deprecated->retired). There is no reverse route and `PATCH /models/{id}` cannot set `state`. `test-model-1` can never be revived. The brief anticipated only `transcript_refinement` as needing registration; it is two stages, not one. | **HIGH** - changes the checklist |
| **F-3** | **`FLUX.1-dev` is not on the fleet and its store row would break Stage 3 twice.** The only checkpoint on node-04 is `flux1-schnell-fp8.safetensors`; and `FluxModel('FLUX.1-dev')` raises `ValueError`. Promotion is not an option; a new `flux1-schnell` row is required. | **HIGH** - changes the checklist |
| **F-4** | **Kokoro is unbindable.** `IVGS_KOKORO_URL` is unset on every worker, so the `kokoro` engine resolves to `http://node-05:8021` and node-05 is offline. The healthy `ivgs-kokoro` container on node-04 (`kokoro-tts:5003`) is unreachable through a binding. | MEDIUM |
| **F-5** | **`sadtalker` resolves to a container that does not exist.** `IVGS_SADTALKER_URL=http://sadtalker:7861` is set on node-04's worker; nothing listens on 7861 and no such container is present. `talking_head_task.py`'s SadTalker fallback path is dead. | MEDIUM |
| **F-6** | **No served model on this fleet matches its store row's name.** vLLM serves `mistral-24b`; the store's only vLLM models are `Llama-3.3-70B-Instruct` and the retired `test-model-1`. node-02's own env says `IVGS_VLLM_PRIMARY_MODEL=llama-3.3-70b` - so even the intended model's store name (`Llama-3.3-70B-Instruct`) does not match its served name (`llama-3.3-70b`). Any vLLM row needs `default_params.engine_model`. | MEDIUM |
| **F-7** | **`weights_checksum` on all eleven backfilled rows is an engine image digest, not a weights hash.** Six rows even carry the `sha256:`-prefixed *image* digest. The backfill's own attestation payloads record `"weights_checksum": null`. A field named for weight provenance holds container provenance. | LOW - hygiene, extends P1.4f |
| **F-8** | **The `models` audit trail is lossy.** Of the 5 `models` UPDATE rows, 3 have `after_payload = NULL`; model CREATE rows carry `resource_id = NULL`; and approvals and lifecycle transitions are all recorded with `action_type='CREATE'`. The trail was sufficient to answer Task 2 only because `before_payload` happened to carry the changed field. | LOW - hygiene |
| **F-9** | **P1.4m overstates Stage 1's failure mode on the deployed fleet.** See S3.4. Stage 1 runs on node-02's pre-ARCH-1 image and does not reach `get_binding` at all. Correction, not a reversal - Stage 1 is still unrunnable, because node-02 has no GPU driver. | LOW - accuracy |
| **F-10** | **`SelectionError` is retried.** WP-03 S1.9 observed Stage 5 retrying a `SelectionError` to `retry_number 2`. The store cannot change between attempts; the retries are pure waste and delay the failure signal. | LOW |

---

# S6. Task 3 - the population plan

Ordered so the pipeline becomes runnable stage by stage. Full operator steps
are in **`dev/workpackages/WP-33-POPULATION-CHECKLIST.md`**; this section is
the engineering rationale and the proof.

## 6.1 Prerequisites the Model Store cannot fix

**These are not store work. Populating the store without them produces
bindings that resolve and then fail at the socket.**

| # | Blocker | Why | Options |
|---|---|---|---|
| **D-1** | **node-02 has no GPU driver.** `ivgs-vllm-primary` exits 128 with `nvml error: driver not loaded`. No chat LLM is served on node-02. | Stages 1 and 2 are dispatched to `gpu_llm` = node-02. | (a) restore the driver on node-02 and start `ivgs-vllm-primary`; or (b) point `gpu_llm` work at node-04's `mistral-24b`. |
| **D-2** | **`IVGS_VLLM_URL` is unset on every worker**, so the `vllm` engine resolves to `http://node-02:8000` regardless of which model is bound. | A compose/env change, not a GUI action. | If D-1 is answered (b): set `IVGS_VLLM_URL=http://192.168.1.93:8000` on the workers. Auth already works - `build_vllm` passes no key and `VLLMClient` falls back to `IVGS_VLLM_API_KEY`, which is set to `ivgs-internal` on both node-02 and node-04. |
| **D-3** | **node-02 and node-03 run pre-ARCH-1 `v5.4.7-h0`.** They cannot import `get_binding`. | Stages 1, 2 and 3-video will not consult the store no matter what it contains. | Deploy an ARCH-1 image (>= `v5.5.0-arch1`; `v5.5.4-metrics` is what node-01/04 run) to node-02 and node-03. |
| **D-4** | **`--max-model-len 4096` on node-04's vLLM**, against node-02's intended 32768. | Stage 1 and 2 prompts sized for the 70B may not fit. | Operator judgement. Recorded, not assessed here - no prompt-length measurement was taken. |

The checklist's store steps are safe to perform **before** these are resolved:
they cannot make anything worse, and each stage's binding will begin resolving
the moment its node is ready.

## 6.2 The plan, per stage

| Order | Stage | Action | Model | Engine | `engine_model` |
|---|---|---|---|---|---|
| 1 | `transcript_refinement` | **REGISTER** (no row exists) | `mistral-24b-transcript` | `vllm` | `mistral-24b` |
| 2 | `storyboard_generation` | **REGISTER** (only row is RETIRED - F-2) | `mistral-24b-storyboard` | `vllm` | `mistral-24b` |
| 3 | `image_generation` | **REGISTER** (FLUX.1-dev unusable - F-3) | `flux1-schnell` | `comfyui` | `flux1-schnell-fp8.safetensors` |
| 4 | `voiceover_tts` | **PROMOTE** existing candidate | `XTTS-v2` | `coqui` | *(not needed - TTS builders ignore it)* |
| 5 | `video_generation` | **PROMOTE** existing candidate | `CogVideoX-5b` | `cogvideox` | *(not needed - name matches the enum)* |
| 6 | `talking_head` | **none - already resolves** | `latentsync` | `latentsync` | - |
| - | `animation_generation` | **do not populate** | - | `animatediff` has no builder; no task binds this stage | - |
| - | `composition` | **do not populate** | - | F-1: would raise `EndpointResolutionError`; no task binds this stage | - |
| - | `translation` | **do not populate** | - | no task binds this stage; `llama-3.3-70b` is served nowhere | - |

Two `vllm` rows point at the same served model because `models.stage` is a
column on the row and `models.name` is globally unique - AD-01 requires one row
per stage. `default_params.engine_model` decouples the store label from the
engine handle, which is exactly what `_common.py`'s docstring says it is for.

All rows use `tier='both'`. `get_binding` matches `tier IN (tier,'both')`, so
one default per stage covers prototype and production in a single action; and
`planner.set_default` (`ivgs-api/app/services/model_selection.py:305-327`)
matches on exact tier, so keeping every row at `both` also keeps the
one-default-per-(stage,tier) invariant unambiguous. **Do not introduce a
prototype-tier row alongside a both-tier row for the same stage** - the default
query is `LIMIT 1` with no `ORDER BY` and would pick nondeterministically.

## 6.3 The proof - planned rows against the real predicate

Read-only projection: existing rows with the checklist's promotions applied
in-memory, unioned with the rows it registers, evaluated against the exact
`get_binding` predicate from `factory.py:173-183`. Script:
`dev/workpackages/reference/wp33-validate-binding.sql`.

```
         stage         |    tier    |      resolves_to       | candidates_matching
-----------------------+------------+------------------------+---------------------
 animation_generation  | prototype  | -- SelectionError --   |                   0
 animation_generation  | production | -- SelectionError --   |                   0
 composition           | prototype  | -- SelectionError --   |                   0
 composition           | production | -- SelectionError --   |                   0
 image_generation      | prototype  | flux1-schnell          |                   1
 image_generation      | production | flux1-schnell          |                   1
 storyboard_generation | prototype  | mistral-24b-storyboard |                   1
 storyboard_generation | production | mistral-24b-storyboard |                   1
 talking_head          | prototype  | latentsync             |                   1
 talking_head          | production | latentsync             |                   1
 transcript_refinement | prototype  | mistral-24b-transcript |                   1
 transcript_refinement | production | mistral-24b-transcript |                   1
 translation           | prototype  | -- SelectionError --   |                   0
 translation           | production | -- SelectionError --   |                   0
 video_generation      | prototype  | CogVideoX-5b           |                   1
 video_generation      | production | CogVideoX-5b           |                   1
 voiceover_tts         | prototype  | XTTS-v2                |                   1
 voiceover_tts         | production | XTTS-v2                |                   1
```

(Verbatim output of Query B in `wp33-validate-binding.sql`, run 2026-08-23.
Query A in the same file prints the current state for comparison.)

All six bound stages resolve, on both tiers, with `candidates_matching = 1` -
so the un-ordered `LIMIT 1` is not ambiguous for any of them. The three
unbound stages continue to raise, which is correct and intended.

And the chain **behind** the predicate, executed inside `ivgs-celery-node04`
against the deployed code:

| stage | model | endpoint resolved | builder | engine-enum coercion |
|---|---|---|---|---|
| `transcript_refinement` | `mistral-24b-transcript` | `http://node-02:8000` **(D-2)** | yes | n/a |
| `storyboard_generation` | `mistral-24b-storyboard` | `http://node-02:8000` **(D-2)** | yes | n/a |
| `image_generation` | `flux1-schnell` | `http://comfyui:8188` | yes | `FluxModel` OK |
| `video_generation` | `CogVideoX-5b` | `http://cogvideox-server:8200` | yes | `CogVideoXModel` OK |
| `voiceover_tts` | `XTTS-v2` | `http://ivgs-coqui:5002` | yes | n/a |
| `talking_head` | `latentsync` | `http://latentsync:7860` | yes | n/a |

Four of six are complete end to end. The two vLLM stages resolve correctly and
are gated only by D-1/D-2, which are env and infrastructure, not store state.

---

# S7. Deliverables

1. **This report.**
2. **`dev/workpackages/WP-33-POPULATION-CHECKLIST.md`** - the operator's
   step-by-step GUI checklist, one action per line, in order, with every field
   value and attestation draft inline, written for a non-developer.
3. **`dev/workpackages/reference/wp33-validate-binding.sql`** - the read-only
   validation query of S6.3, so the operator can re-run it after executing the
   checklist and see the same table against real rows.
4. **Ledger updates** in `OUTSTANDING_WORK.md`: P1.4m amended with the Task 2
   verdict and F-9's correction; new **P1.4n** for F-1 (the `ffmpeg` seam);
   P1.4f extended with F-4, F-5, F-7, F-8, F-10.

## 7.1 Decisions recorded, not taken

Per the unattended profile, these were not blocked on:

| # | Decision | Recommendation |
|---|---|---|
| D-1 | Restore node-02's GPU driver, or move `gpu_llm` to node-04's `mistral-24b`? | Node-04 short-term (it is up, healthy and already serving); node-02 properly for the 70B. |
| D-2 | Set `IVGS_VLLM_URL` on the workers? | Required if D-1 is answered "node-04". A compose change; not in this package's scope. |
| D-3 | Deploy an ARCH-1 image to node-02/03? | Required before stages 1, 2 and 3-video consult the store at all. Sequence it with the WP-IVGS-0 deploy. |
| D-4 | Is `--max-model-len 4096` sufficient for Stage 1/2 prompts? | Unmeasured. Measure before relying on node-04 for `gpu_llm`. |
| D-5 | Fix F-1 (`ffmpeg` endpoint + builder) or formally exclude `composition` from AD-01? | Decide before anything binds `composition`. A one-line `_ENGINE_ENDPOINTS` entry is not enough - there is no builder either, and ffmpeg is in-process, not a served endpoint. The honest fix may be to exclude it. |
| D-6 | `flux1-schnell`'s `vram_gb`? | **Left NULL.** No measurement exists for schnell on this fleet, and FLUX.1-dev's 31.47 GB is a different model. Fabricating it would violate INV-9. Stage 3's reservation falls back to 16384 MB when it is NULL. |
| D-7 | Retire `latentsync-alt` (P1.4f.1)? | Still `approved`. Out of this package's scope (no mutations), and unchanged. |

---

# S8. Exit gate

| Requirement | Status |
|---|---|
| Task 2 answered definitively with evidence | **MET** - S3. Verdict: NEWLY-EXPOSED TRUTH; hypothesis (a) disproved three ways; hypothesis (b) true but inverted. |
| The checklist exists | **MET** - `dev/workpackages/WP-33-POPULATION-CHECKLIST.md`. |
| Every planned row provably satisfies the `get_binding` predicate | **MET** - S6.3, plus the endpoint/builder/enum chain behind it. |
| Zero writes against any live system | **MET** - S2.3, opening and closing measurements identical. |

**Caveat, stated plainly.** Executing this checklist makes `get_binding`
resolve for all six bound stages. It does **not** by itself produce a working
pipeline: D-1 (node-02 has no GPU driver), D-2 (`IVGS_VLLM_URL` unset) and D-3
(node-02/03 pre-ARCH-1) each sit between a resolving binding and a running
stage. This report would be repeating WP-IVGS-0's mistake if it implied
otherwise.
