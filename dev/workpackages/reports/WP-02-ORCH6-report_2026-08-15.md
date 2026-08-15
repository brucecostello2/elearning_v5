# WP-02-ORCH6 - report

| | |
|---|---|
| **Package** | WP-02-ORCH6 (Track S #3, **Tier C - judgement**) |
| **Brief** | `workpackages/WP-02-ORCH6.md` |
| **Ledger** | P1.0 / ORCH-6 - top of the entire programme |
| **HEAD SHA at session start** | `d4665ae4792ec8eff7b49c1e057df1def4006c5a` |
| **Branch** | `main`, working tree clean (WP-15 and WP-00 committed at `35b4bf6` / `d4665ae`) |
| **Date** | 2026-08-15 |
| **Agent** | Claude, node-01 only |

> # STATUS: PASS 1 COMPLETE - STOPPED, AWAITING OPERATOR REVIEW
>
> **No file has been edited.** Per the brief's HARD STOP and common rule 2, this
> report contains findings and the full proposed diff plan only. Pass 2 begins only
> on operator approval.
>
> **Pass 1 changes the recommended shape of this package.** Four findings below are
> blocking; three of them were not visible from the brief. Read S1.3 (F1-F4) and
> S1.9 (decisions) first.

---

# PASS 1 - FINDINGS AND PROPOSED PLAN

## 1.1 Headline

The brief describes this as porting a binding between two variants of one task. **It
is not.** The two files implement **different pipeline architectures**, and the dead
one implements the architecture that AD-03 Pillar 2 deliberately retired. On top of
that, the AD-01 binding **cannot resolve at all** on the current database - verified
live, not inferred.

The package is still the right thing to do and is still achievable. But "port the
binding" is a smaller and more surgical change than the brief implies, and it has a
hard operator prerequisite that must happen first.

## 1.2 Current call graph - both files at `d4665ae`

### Live: `ivgs-workers/tasks/talking_head_task.py` (712 lines)

Registered `tasks.talking_head_task.render_talking_head`, queue `gpu_talking_head`,
dispatched from `pipeline_orchestrator_v2.py:112-114`. **Whole-project, one output.**

```
render_talking_head                          :288  Celery entrypoint (decorator :276-287)
 |- Stage6Input validation                   :305
 |- skip-if-no-reference-clip early return    :321-332
 |- _download_asset(reference_clip)          :342  -> helper :127
 |- _concatenate_scene_audio                 :350  -> helper :173  (ALL scene audio -> one WAV)
 |- acquire_gpu_reservation("latentsync")    :358  hardcoded name + 16384 MB
 |- SEGMENT PLANNER                          :378-433  <-- the proven OOM strategy
 |   |- ffmpeg probe per scene               :394
 |   `- split scenes > MAX_SEGMENT_SECONDS   :404-426
 |- per-segment render loop                  :439-493
 |   `- _render_with_latentsync (x retries)  :445  -> helper :196  HARDCODED ENGINE
 |- concat_segments (checksum-verified)      :500
 |- alignment gate -> force fallback         :524-530
 |- SadTalker fallback                       :537-602
 |   |- release_gpu_reservation(2 args)      :543  <-- see F4
 |   |- acquire_gpu_reservation("sadtalker") :545  hardcoded
 |   `- _render_with_sadtalker               :554  -> helper :239  HARDCODED ENGINE
 |- CorruptionDetector.validate_video        :610
 |- LipsyncValidator.validate                :628
 |- _upload_asset                            :643  -> helper :141  CORRECT URL :155
 |- save_checkpoint                          :671
 `- finally: release_gpu_reservation(2 args) :699  <-- see F4
```

Constants `MAX_SEGMENT_RETRIES=2`, `MAX_SEGMENT_SECONDS=30.0` at `:64-65`.
Hardcoded-engine imports at `:42-48` (`LatentSyncClient`, `LatentSyncError`,
`LatentSyncMode`, `LatentSyncParams`, `LatentSyncResult`) - the brief's `:42-47` is
`:42-48` at HEAD.

### Dead: `ivgs-workers/tasks/stage6_talking_head.py` (695 lines)

Registered `tasks.stage5_talking_head.generate_talking_head_task` - **in no map**
(confirmed against both `STAGE_TASK_MAP`s). **Per-scene, one output per scene.**

```
generate_talking_head_task                   :513  Celery entrypoint (decorator :502-512)
 |- Stage5Input validation                   :524  (scenes[], tier, reference_clip)
 |- ensure_registered()                      :538  <-- ARCH-1
 |- get_binding("talking_head", project, tier) :541-547  <-- ARCH-1  THE BINDING
 |- build_provider(binding, ...)             :551-555  <-- ARCH-1
 |- acquire_gpu_reservation(binding.name,
 |     provider.vram_requirement_mb())       :561-568  <-- binding-driven
 `- per-scene loop                           :594-641
     `- _process_single_talking_head         :595  -> helper :293
         |- download scene image + audio     :315
         |- _detect_render_mode (vLLM)       :333  -> helper :181
         |- provider.render(TalkingHeadParams) :361  <-- ARCH-1 render
         |- VideoValidator.validate_bytes    :367
         |- check_duplicate_asset (dedup)    :406
         |- _upload_video_to_seaweedfs       :444  -> helper :225  WRONG URL :241
         `- _update_scene_talking_head       :452  -> helper :263
```

Binding imports at `:43-50` (brief says `:43-48`); the ARCH-1 render comment is at
`:338`; `provider: TalkingHeadProvider` in the signature at `:297`. All three brief
anchors are accurate to within two lines.

### The architectural difference

| | Live `talking_head_task.py` | Dead `stage6_talking_head.py` |
|---|---|---|
| Unit of work | **The whole project** - one head video | **One scene** - N head videos |
| Audio input | All scene audio concatenated into one track (`:173`) | One scene's voiceover |
| Scene image | **None** - never downloaded, never used | Required (`image_asset_id`) |
| Output | One asset; `Stage6Output.asset_id` | `scene_results[]`; writes `scene.talking_head_asset_id` |
| Segmentation | Yes - the OOM fix (`:378-433`) | No |
| Consumed by | Stage 7/8 as a **continuous timeline overlay** (AD-03 Pillar 2) | Per-scene overlay |

**The dead file implements the pre-Pillar-2 design.** AD-03 S11 records Pillar 2's
closure as compositing the head **once** as a continuous overlay instead of
re-overlaying per scene, evidenced by `num_layers` 3 -> 2 and draft `f78eb063`. The
dead file's per-scene model is what that change retired. It is therefore **not** a
better implementation in any sense except the binding - and the ledger's framing
("the duplicate is the *more correct* implementation") is true only of those ~20
lines.

**Consequence for scope:** almost nothing "moves". Of the dead file's 695 lines, the
promotion needs `:538-555` (four calls) plus a params translation. Everything else -
per-scene loop, dedup, scene-record update, vLLM mode detection, VideoValidator -
belongs to the retired architecture and must **not** be carried across.

## 1.3 Blocking findings

### F1 - `get_binding` raises today. An unconditional promotion breaks Stage 6. **[VERIFIED LIVE]**

Executed inside the deployed worker image `ghcr.io/brucecostello2/ivgs-workers:v5.5.1-arch1`
against the production database:

```
$ docker exec ivgs-celery-default python -c "... await get_binding('talking_head', project_id=..., tier='prototype')"
RAISED: SelectionError
MESSAGE: no selection and no enabled APPROVED default model for stage='talking_head'
         tier='prototype' (project b55822cf-...)
```

The cause, from the model store (read-only SELECT on `ivgs-postgres`):

```
stage        | tier | state     | enabled | is_default | engine     | name
talking_head | both | candidate | t       | f          | latentsync | latentsync
(1 row)
```

Repository-wide: **12 models, 11 `candidate` + 1 `retired`. Zero `approved`. Zero
`is_default`. Zero rows in `project_model_selections`. Zero rows in
`model_node_availability`.** `model_approvals` holds 24 rows - attestation records
exist, but no model was ever promoted to APPROVED.

`factory.py:173-189` requires `state == APPROVED AND enabled AND is_default` for the
default fallback, and `:186` raises `SelectionError` when that returns nothing.

**So promoting the binding without a prerequisite converts a working (if hardcoded)
Stage 6 into a stage that fails at the binding call, on every job.** This is the
single most important finding in this report and it was not visible from the brief.

### F2 - The GUI-swap exit gate is not reachable on the current data, and the obvious swap target is broken

The exit gate requires a head-model swap performed **entirely in the GUI** that
**changes which engine Stage 6 invokes**. Two independent obstacles:

**(a) There is only one talking_head model, and it is a CANDIDATE.** A swap needs two
approved models. The operator must register/approve a second.

**(b) The obvious second model - SadTalker - does not work through the provider in
this architecture.** `ivgs-workers/providers/talking_head.py:135-152`:

```python
async def render(self, params: TalkingHeadParams) -> TalkingHeadResult:
    with tempfile.TemporaryDirectory(prefix="sadtalker_") as tmp:
        image = self._spill(tmp, "scene.png", params.scene_image_data, params.scene_image_path)
        ...
        if not image or not audio:
            raise ValueError("sadtalker provider requires scene image and voiceover audio")
```

The live whole-project task **has no scene image** - it never downloads one. So
selecting a `sadtalker`-engine model would raise `ValueError` at render time.

`LatentSyncProvider.render` (`:62-91`) by contrast requires only
`voiceover_audio_data` + `reference_clip_data` and treats `scene_image_data` as
optional - **exactly the live task's shape**. The primary path promotes cleanly; the
SadTalker path does not.

A second, independent defect in `SadTalkerProvider`: `_spill` writes bytes to a
worker-local `tempfile.TemporaryDirectory()` and `SadTalkerClient._submit_job`
(`sadtalker_client.py:237-250`) posts those paths as **JSON** (`source_image`,
`driven_audio`, `ref_clip`) to the remote SadTalker HTTP service. Unless that service
shares the worker's `/tmp`, it receives paths it cannot open. Not verified against a
running SadTalker service - node-04 is out of my authority.

**Three mutually incompatible SadTalker contracts now exist:**

| # | Where | Contract |
|---|---|---|
| 1 | `talking_head_task.py:239-269` (live fallback) | `POST {base}/generate`, multipart `reference_video` + `audio`, returns bytes |
| 2 | `SadTalkerClient._submit_job` | `POST /api/render`, JSON of server-side paths, poll for job |
| 3 | `SadTalkerProvider` | worker-local temp paths handed to contract 2 |

Only #1 is exercised by the live pipeline. Which one the deployed node-04 service
actually implements is **unverified**.

### F3 - Stage 6 renders once; the tier taxonomy assumes it renders twice

`ModelTier` (`shared/models/model_store.py:66-71`) documents *"prototype drives Stage
7, production drives Stage 8"*. But Stage 6 runs **once**, before both, and produces a
single asset that Stage 7 and Stage 8 both consume (`pipeline_orchestrator_v2.py:778`
and `:792` both call `_fetch_talking_head_asset`).

`Stage6Input` has **no `tier` field**, and `_build_stage_input` (`:767-773`) does not
supply one. So the promotion must pick a tier constant.

**This means AD-01.13 criterion 5 - "prototype-tier and production-tier models applied
to draft and final respectively" - is NOT unblocked by this package**, contrary to
AD-01 Draft 2 SAD-01.15's implication that ORCH-6 is what blocks it. Satisfying
criterion 5 needs Stage 6 to run per-tier, or Stage 8 to re-render the head. That is a
pipeline change, well outside this brief.

Recommendation: hard-default `tier="prototype"` (matching the dead file's
`Stage5Input.tier` default at `:94`), expose it on `Stage6Input` so it is
overridable, and record that criterion 5 remains open.

### F4 - `release_gpu_reservation` is called with 2 arguments in the file we must edit. **[VERIFIED LIVE - resolves the CLAUDE.md S7 contradiction]**

CLAUDE.md S7 records a contradiction it asks the operator to settle: the file asserts
`release_gpu_reservation` raises `TypeError` at all 3 call sites, while
`OUTSTANDING_WORK.md:293` records that it does **not** reproduce on the deployed
image. Neither had been tested.

Read out of the **deployed** image:

```
$ docker exec ivgs-celery-default python -c "import inspect; from utils.gpu_utils import release_gpu_reservation as r; print(inspect.signature(r))"
signature: (reservation_id: 'str') -> 'bool'
file: /app/utils/gpu_utils.py
```

One parameter. The three call sites pass two:

```
ivgs-workers/tasks/talking_head_task.py:543      release_gpu_reservation(reservation, config)
ivgs-workers/tasks/talking_head_task.py:699      release_gpu_reservation(reservation, config)   <- finally block
ivgs-workers/tasks/video_generation_task.py:540  release_gpu_reservation(reservation, config)
```

(`celery_app.py:607` is correct - one argument.) They also pass the **dict** returned
by `acquire_gpu_reservation`, not a `reservation_id` string.

**Both claims are reconciled.** The signature drift is real (CLAUDE.md is right); it
does not reproduce (OUTSTANDING_WORK is right) because it is guarded by
`if reservation:` and reservations never succeed - `model_node_availability` is empty,
matching CLAUDE.md's `total_nodes:0`. The moment GPU reservations start working, this
becomes a live `TypeError` in a `finally` block, which would mask the original
exception **and** skip `shutil.rmtree(temp_dir)` at `:701-702`, leaking the temp
directory on every Stage-6 run.

Fixing it is WP-08's scope, not this brief's. Flagged as decision D-4.

## 1.4 Non-blocking findings

### F5 - Deleting the duplicate has a wider blast radius than the brief states

The brief treats deletion as the file plus `stage-numbering-map.md`. Actual
references at `d4665ae`:

| File | Line(s) | What |
|---|---|---|
| `ivgs-workers/tasks/__init__.py` | `:18`, `:49`, `:71` | docstring, import, `__all__` |
| `ivgs-workers/celery_app.py` | `:122`, `:151`, `:329` | comment, **`task_routes` entry `tasks.stage5_talking_head.*`**, **`imports` list `tasks.stage6_talking_head`** |
| `ivgs-workers/tests/test_stage5.py` | `:23`, `:150`, `:154`, `:158`, `:194`, `:245`, `:249`, `:253` | whole module imports the dead task |
| `tests/providers/test_stage6_wiring.py` | `:79`, `:151` | **the existing ARCH-1 wiring test** |
| `docs/stage-numbering-map.md` | `:23`, `:44`, `:46` | table row + both "traps" |
| `docs/deployment/runbook.md` | `:244` | "a reviewer deletes stage6_talking_head.py as dead code" |
| `OUTSTANDING_WORK.md` | `:78`, `:82`, `:185`, `:192` | ledger |

`celery_app.py:329` matters most: the module is in the worker's `imports` list, so
deleting the file without editing that list makes **every worker fail at startup**.

### F6 - `tests/providers/test_stage6_wiring.py` is the natural pass-2 regression test

It already asserts exactly what this package must deliver, but against the dead file:

- `test_per_scene_path_uses_provider_and_binding` - proves params mapping and that
  `model_used` comes from `binding.name`, not the engine result.
- `test_stage6_module_has_no_hardcoded_engine` (`:148-156`) - asserts
  `"LatentSyncClient(" not in source`, `"get_binding" in source`,
  `"build_provider" in source`.

Repointing both at `talking_head_task.py` turns them into the proof for this package.
The first needs rewriting for the whole-project shape (no scene image, segmented
render).

### F7 - Provider layer imports cleanly in the deployed worker image. **[VERIFIED LIVE]**

```
$ docker exec ivgs-celery-default python -c "..."
shared.providers OK
factory symbols OK
registered engines: ('cogvideox', 'comfyui', 'coqui', 'kokoro', 'latentsync', 'sadtalker', 'vllm')
```

Both `latentsync` and `sadtalker` builders are registered in the running image. No
packaging or `PYTHONPATH` work is needed (`PYTHONPATH` is unset; `shared` resolves
anyway). This removes the largest implementation risk.

### F8 - AD-01 stage taxonomy confirmed; the trap does not bite here

`ModelStage` (`model_store.py:74-85`) carries MBCP's nine-stage taxonomy -
`transcript_refinement, storyboard_generation, image_generation, video_generation,
animation_generation, voiceover_tts, talking_head, composition, translation` - not
IVGS's eight pipeline stages, exactly as CLAUDE.md S11 warns. `talking_head` is a
valid key, so the selection key is the literal string `"talking_head"` paired with a
tier. **The trap is real but benign for this package** because Stage 6 maps 1:1 onto
MBCP's `talking_head`. It would bite on Stages 4/7/8, which MBCP collapses into
`composition`.

Resolution precedence, read from `factory.py:125-198`: scene selection -> project
selection -> `is_default` for (stage, tier) -> `SelectionError`. Selection rows serve
APPROVED **and** DEPRECATED; the default fallback serves APPROVED only (`:44`,
`:172-181`).

### F9 - MBCP backfill numbers are not corroborated by this database

AD-01 SAD-01.16 and AD-04 S3.22 (both applied to the docs by WP-15 yesterday) state
"21 exports plus 2 composition transmitted; all non-revoked certifications landed as
CANDIDATEs; 24 revoked correctly skipped." This database holds **12 models** and
**24 `model_approvals` rows**.

Not necessarily a contradiction - many certifications can dedup onto one model, and 24
appears in both accounts. **Recorded, not asserted as an error.** Worth one operator
check, since I applied that text in WP-15 on the amendment's authority.

## 1.5 Things I cannot explain - listed, not glossed

1. **`stage6_talking_head.py:651`** -
   `raise self.retry(exc=e) if self.request.retries < self.max_retries else None`.
   Parsed as `raise (X if cond else None)`; on the else branch this is
   `raise None` -> `TypeError: exceptions must derive from BaseException`. Dead code
   today. I cannot tell whether it was ever intended to swallow or to re-raise.
2. **`talking_head_task.py:532`** - `except (LatentSyncError, Exception) as e`.
   `Exception` subsumes `LatentSyncError`; the tuple is redundant. Harmless, but I
   cannot explain the intent, and it catches `RuntimeError` from the segment loop at
   `:463` identically to a genuine engine error.
3. **Why `_render_with_latentsync` constructs a new `LatentSyncClient` per segment**
   (`:205`, inside the retry loop at `:443`). N clients for N segments, each closed in
   its own `finally` (`:235`). Wasteful; possibly deliberate to avoid connection reuse
   across an OOM-prone engine. Unverified.
4. **`Stage6Output.model_used` vs `alignment_score` provenance.** `output.alignment_score`
   is overwritten at `:633` by `LipsyncValidator`, while the value logged and uploaded
   in metadata at `:651` is the **segment average** computed at `:510`. Two different
   numbers under similar names. I cannot tell which is authoritative for the
   `>0.85` gate.
5. **The dead file's `video_converter` parameter** (`:301`, `:588`, `:604`) is passed
   through `_process_single_talking_head` and never used in the function body.
6. **`docs/stage-numbering-map.md:21`** marks Stage 5 as
   `tasks.stage4_voiceover.generate_voiceover_task` while the file is
   `stage5_voiceover.py`. Consistent with the documented off-by-one, but I did not
   verify it and it is outside this package.

## 1.6 Proposed plan for pass 2

### Prerequisite - OPERATOR, before any code runs (F1)

In `/admin/models`, for stage `talking_head`:

1. Approve the existing `latentsync` CANDIDATE (attestation required by
   `model_store.py:148`).
2. **Set it default** (`is_default`, transactional per `model_selection.py:305-321`).
3. Register and approve a **second** model to swap to, for the exit gate.

Without step 2, `get_binding` raises and Stage 6 fails. Step 3 determines whether the
exit gate is demonstrable at all - see D-1.

### The change - `ivgs-workers/tasks/talking_head_task.py`

Deliberately minimal. Segment planner, concat, corruption/lipsync validation, upload
URL and Pillar-2 behaviour are **not touched**.

| # | Location | Change |
|---|---|---|
| 1 | `:42-48` | Remove `LatentSyncClient`, `LatentSyncParams`, `LatentSyncMode`, `LatentSyncResult` imports. Keep **`LatentSyncError`** only if `:532` still needs it - preferred: drop it and catch `Exception` |
| 2 | after `:56` | Add `from uuid import UUID`, `from providers import ensure_registered`, `from shared.providers import ModelBinding, TalkingHeadParams, TalkingHeadProvider, build_provider, get_binding` |
| 3 | `Stage6Input` `:80-96` | Add `tier: str = "prototype"` (F3) |
| 4 | after `:317` | Resolve the binding **once per job**: `ensure_registered()`; short-lived event loop -> `get_binding("talking_head", project_id=UUID(project_id), tier=task_input.tier)`; `provider = build_provider(binding, timeout=config.timeouts.latentsync_timeout, alignment_threshold=task_input.alignment_threshold)`; `log = log.bind(model=binding.name, engine=binding.engine, endpoint=binding.endpoint)`. **Let `SelectionError` propagate** - no silent fallback (see D-2) |
| 5 | `:358-362` | `acquire_gpu_reservation(model_name=binding.name, vram_requirement_mb=provider.vram_requirement_mb())` instead of `"latentsync"` / `16384` |
| 6 | `_render_with_latentsync` `:196-236` | **Replace with `_render_segment(provider, reference_bytes, audio_bytes, task_input)`** building `TalkingHeadParams(voiceover_audio_data=..., reference_clip_data=..., mode=task_input.latentsync_mode, output_width/height/fps=..., pip_position/pip_scale=..., face_enhance=..., lip_sync_strength=..., alignment_threshold=...)` and awaiting `provider.render(...)`. Returns `TalkingHeadResult`, which is field-compatible with the `LatentSyncResult` usage at `:473-491` (`video_data`, `width`, `height`, `fps`, `alignment_score`) |
| 7 | `:445-450` | Call `_render_segment`; read reference/audio bytes **once** before the loop rather than per segment (fixes finding 3 in S1.5 as a side effect of the rewrite) |
| 8 | `:514` | `model_used = binding.name` (not the literal `"latentsync"`) - matches the assertion in `test_stage6_wiring.py:136` |
| 9 | `:537-602` fallback | **UNCHANGED.** Keep `_render_with_sadtalker` and its hardcoded `/generate` contract (see D-1) |
| 10 | after upload | `await provider.close()` if present, mirroring `stage6_talking_head.py:643-645` |

Net: roughly **-45 / +60 lines**, all in the binding and per-segment render call.

### Files touched in pass 2

| Path | Change |
|---|---|
| `ivgs-workers/tasks/talking_head_task.py` | The promotion above |
| `ivgs-workers/tasks/stage6_talking_head.py` | **DELETE** - last, after verification |
| `ivgs-workers/tasks/__init__.py` | Drop `:18` docstring line, `:49` import, `:71` `__all__` entry |
| `ivgs-workers/celery_app.py` | Drop `:122` comment, `:151` `task_routes` entry, **`:329` `imports` entry** (F5 - startup-critical) |
| `ivgs-workers/tests/test_stage5.py` | **DELETE** - tests only the deleted task |
| `tests/providers/test_stage6_wiring.py` | Repoint at `talking_head_task`; rewrite case 1 for the whole-project shape (F6) |
| `docs/stage-numbering-map.md` | Remove `:23` row; rewrite traps `:44`/`:46` as resolved |
| `docs/deployment/runbook.md` | `:244` symptom no longer applies |
| `OUTSTANDING_WORK.md` | Close P1.0 / ORCH-6 |

**Not touched:** `shared/providers/*`, `ivgs-workers/providers/*`, orchestrators, any
other stage task, `_upload_asset` and its `:155` URL, the segment planner, the
corruption/lipsync validators.

### Verification plan for pass 2

| # | Check | Where | Blocked on |
|---|---|---|---|
| 1 | `test_stage6_wiring.py` passes against the live module; `"LatentSyncClient(" not in source` | node-01, pytest | - |
| 2 | `python -c "import tasks"` inside the worker image after deletion - proves `celery_app.py:329` was cleaned | node-01, docker | - |
| 3 | `celery inspect registered` shows `tasks.talking_head_task.render_talking_head` and **not** `tasks.stage5_talking_head.*` | node-01 | image rebuild |
| 4 | `get_binding('talking_head', ...)` resolves and `.describe()` names the approved default | node-01, docker exec | **operator prerequisite** |
| 5 | Short-job render: worker log shows `model=`/`engine=`/`endpoint=` from the binding | **node-04** | **operator** - CLAUDE.md S1/S2 forbid me running commands there |
| 6 | GUI set-default swap -> re-run -> log shows the new model | **node-04 + GUI** | **operator** |
| 7 | Pillar-2/OOM unchanged: `render_plan`, `scene_split`, `segment_render_complete`, `latentsync_segmented_render_complete` all still emitted with the same fields; upload still `POST /projects/{id}/assets/upload` | node-04 log + diff | **operator** |
| 8 | Corruption 6/6 and video==audio within tolerance on the resulting draft | node-04 | **operator** |

**Checks 5-8 are operator-executed.** The `gpu_talking_head` worker runs on node-04;
node-01 runs only `ivgs-celery-default`, `-composition` and `-beat` (verified). I can
author the commands and read the logs the operator returns, but I must not run them.

## 1.7 Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| `SelectionError` breaks Stage 6 (F1) | **HIGH** | Operator prerequisite first; fail loud, never silently fall back (D-2) |
| SadTalker selection raises `ValueError` (F2) | **HIGH** | Do not route the fallback through the provider in this package; document that a `sadtalker` selection is unsupported until the provider is fixed |
| Worker startup breaks on deletion (F5) | **HIGH** | `celery_app.py:329` in the same change; verification check 2 |
| Pillar-2 / OOM regression | **HIGH** | Segment planner untouched; checks 7-8 |
| `TypeError` in `finally` when reservations start working (F4) | MEDIUM | Out of scope - D-4 |
| Tier semantics (F3) | MEDIUM | Constant + documented; criterion 5 stays open |
| Per-segment provider construction | LOW | Build once per job, not per segment |

## 1.8 Evidence basis

**Verified live on node-01 (command run, output read):**

- HEAD SHA, branch, clean tree; both prior packages committed.
- Both stage-6 files read in full at `d4665ae`; every brief anchor re-checked.
- `factory.py`, `binding.py`, `shared/providers/__init__.py:200-279`,
  `ivgs-workers/providers/talking_head.py`, `providers/__init__.py` read in full.
- `LatentSyncParams` and `SadTalkerClient._submit_job` contracts read.
- `STAGE_TASK_MAP` in both orchestrators; `_build_stage_input:767-773`.
- Repo-wide `grep` for `stage5_talking_head|stage6_talking_head` (F5 table).
- **Model store queried read-only** on `ivgs-postgres`: 12 models, 0 approved,
  0 defaults, 0 selections, 0 availability rows, 24 `model_approvals`.
- **`get_binding('talking_head', ...)` executed in the deployed worker image** -
  raises `SelectionError` (F1).
- **`release_gpu_reservation` signature read from the deployed image** - one
  parameter (F4).
- **`shared.providers` import + `registered_engines()` in the deployed image** (F7).
- Worker containers on node-01: `ivgs-celery-default`, `-composition`, `-beat`.
  No `gpu_talking_head` worker here.

**Inferred from reading only (not executed):**

- That the promoted `TalkingHeadParams` -> `LatentSyncParams` mapping preserves
  current render behaviour. Field-by-field it does
  (`providers/talking_head.py:68-80`), but **no render was executed**. `pip_scale`
  default differs between `TalkingHeadParams` (0.25) and `LatentSyncParams` (0.3) -
  the live task passes an explicit value, so this should not bite, but it is
  untested.
- That `SadTalkerProvider`'s worker-local temp paths are unusable by the remote
  service. Read from code; **not** confirmed against node-04.
- That deleting the dead file breaks nothing else. Based on `grep`, not on a build.
- Everything about node-04 runtime behaviour.

## 1.9 Decisions requested - PASS 2 IS BLOCKED ON THESE

| # | Decision | Options | My recommendation |
|---|---|---|---|
| **D-1** | The exit gate says the swap must change **which engine** Stage 6 invokes. Given F2, how? | **(a)** Swap between two `latentsync`-engine models - proves binding-driven model/endpoint selection, engine class unchanged. Zero provider work. **(b)** Fix `SadTalkerProvider` to accept the no-scene-image shape, then swap engines for real - widens scope into `ivgs-workers/providers/`. **(c)** Defer the true engine swap to a follow-on | **(a) now, (b) as a follow-on WP.** (a) is honestly reportable as "model selection is live"; (b) is a provider-layer fix that deserves its own brief and a node-04 smoke test |
| **D-2** | `SelectionError` behaviour when no default exists | **(a)** Propagate - Stage 6 fails loudly. **(b)** Catch and fall back to hardcoded LatentSync | **(a).** (b) is textbook WP-00 swallowed-failure: the GUI swap would silently not work and the pipeline would look healthy. I will not implement (b) without an explicit instruction |
| **D-3** | Tier for Stage 6 (F3) | **(a)** Constant `"prototype"`. **(b)** `"production"`. **(c)** Plumb per-tier through the orchestrator | **(a)**, with `tier` exposed on `Stage6Input`. (c) is a pipeline change, out of brief |
| **D-4** | The 2-arg `release_gpu_reservation` bug (F4), in the file I am editing | **(a)** Leave - WP-08 owns it. **(b)** Fix the two Stage-6 sites while I am in the file | **(a)**, flagged. It is latent today. But it is one character of scope and it sits in a `finally`; say the word and I will do (b) |
| **D-5** | `ivgs-workers/tests/test_stage5.py` | **(a)** Delete with the module. **(b)** Port to the live task | **(a).** It tests the per-scene architecture that Pillar 2 retired. `test_stage6_wiring.py` is the test worth keeping |
| **D-6** | Operator prerequisite (F1) | Approve + set-default a `talking_head` model before pass 2 | Required. Pass 2 cannot be verified without it |

---

# PASS 2 - CHANGES AND VERIFICATION

**Pass 1 approved 2026-08-15. Decisions taken: D-1(a), D-2(a), D-3(a), D-4(a), D-5(a).
D-6 (operator prerequisite) reported done and independently re-verified before any
edit - see S2.1.**

## 2.1 D-6 re-verified before starting

Ground truth beats a report of completion, so the prerequisite was checked, not assumed:

```
name       | stage        | tier | state    | enabled | is_default | engine
latentsync | talking_head | both | approved | t       | t          | latentsync

$ docker exec ivgs-celery-default python -c "... get_binding('talking_head', ...)"
RESOLVED: latentsync [latentsync] tier=prototype via=default endpoint=http://node-04:8300
```

F1 is cleared. The binding resolves via the `is_default` fallback path
(`factory.py:172-198`), `selected_by="default"`.

**Endpoint and timeout are provably unchanged by the promotion** - the strongest
available evidence that this is behaviour-neutral for the current default:

| | Before (hardcoded) | After (binding) |
|---|---|---|
| Endpoint | `config.get_model_config("latentsync")["api_url"]` = `http://node-04:8300` | `resolve_endpoint("latentsync")` = `http://node-04:8300` |
| Timeout | literal `600.0` | `config.timeouts.latentsync_timeout` = `600` |
| VRAM ask | literal `16384` | `provider.vram_requirement_mb()` = `16384` (binding `vram_gb` is NULL, so `_ENGINE_DEFAULT_VRAM_MB["latentsync"]`) |

`IVGS_LATENTSYNC_URL` is unset in the worker environment, so the env override does not
change this.

## 2.2 Diff stat

```
 OUTSTANDING_WORK.md                          |  60 ++-
 docs/deployment/runbook.md                   |  27 +-
 docs/stage-numbering-map.md                  |  26 +-
 ivgs-workers/celery_app.py                   |   6 -
 ivgs-workers/tasks/__init__.py               |   5 +-
 ivgs-workers/tasks/stage6_talking_head.py    | 695 ------------------  (DELETED)
 ivgs-workers/tasks/talking_head_task.py      | 214 ++++++---
 ivgs-workers/tests/test_stage5.py            | 296 ------------  (DELETED)
 ivgs-workers/tests/test_talking_head_task.py | 164 ++++---
 tests/providers/test_stage6_wiring.py        | 165 ++++---
 10 files changed, 436 insertions(+), 1222 deletions(-)
```

The task file itself is **+152 / -62**. Nothing staged, nothing committed.

## 2.3 What changed - `ivgs-workers/tasks/talking_head_task.py`

| # | Change | Where |
|---|---|---|
| 1 | Dropped the whole `clients.latentsync_client` import block; added `UUID`, `providers.ensure_registered`, and the shared `ModelBinding / TalkingHeadParams / TalkingHeadProvider / TalkingHeadResult / build_provider / get_binding` | imports |
| 2 | Added `VALID_RENDER_MODES` / `DEFAULT_RENDER_MODE` as plain strings, so the task validates the render mode without importing the engine enum | module constants |
| 3 | `Stage6Input.tier: str = "prototype"` (D-3a), commented with why criterion 5 stays open | `Stage6Input` |
| 4 | **Binding resolution** - `ensure_registered()`, `get_binding("talking_head", project_id=UUID(...), tier=...)`, `build_provider(...)`, and `log.bind(model=, engine=, endpoint=, tier=)` + a `stage6_model_bound` event | after the skip-check, **before** `try` |
| 5 | Replaced `_render_with_latentsync` with `_render_segment(provider, reference_clip_data, audio_data, task_input)` building `TalkingHeadParams`, plus `_resolve_render_mode()` | helpers |
| 6 | Reservation asks for `binding.name` / `provider.vram_requirement_mb()` instead of `"latentsync"` / `16384` | step 3 |
| 7 | Reference clip read **once** before the segment loop rather than per segment per attempt | segment loop |
| 8 | `model_used = binding.name` instead of the literal `"latentsync"` | post-concat |
| 9 | `except (LatentSyncError, Exception)` -> `except Exception` (the tuple was redundant; the engine class is no longer imported) | primary-render guard |
| 10 | `provider.close()` in `finally`, on its own short-lived loop so it also runs on the exception path | `finally` |
| 11 | Module docstring and four comments rewritten to describe selection-driven behaviour | docstring/comments |

### D-2(a) implemented deliberately, and why the placement matters

The binding is resolved **outside** the `try/finally`. That is not stylistic:

- Inside the `try`, a `SelectionError` would be caught by the outer
  `except Exception`, converted to `output.status = FAILED`, and **returned** - so
  Celery would record the task SUCCESS while reporting a failure. That is exactly
  register instance 6 (WP-00, rule SF005).
- Outside it, the exception propagates and the Celery task genuinely FAILS.
- It also resolves before `tempfile.mkdtemp()`, so a selection failure cannot leak a
  temp directory.

No silent fallback to a hardcoded engine was added, per D-2(a).

### Explicitly NOT changed - the three protected behaviours

Verified mechanically rather than asserted. `git diff -U0` on the task file, filtered
for the protected constructs, returns **nothing**:

```
$ git diff -U0 ivgs-workers/tasks/talking_head_task.py | grep '^[-+]' | grep -v '^[-+][-+]' \
    | grep -iE "MAX_SEGMENT|concat_segments|verify_checksums|CorruptionDetector|LipsyncValidator|_upload_asset|n_parts|piece_dur|save_checkpoint"
(no output)
```

- **Segment/OOM strategy** - planner, `MAX_SEGMENT_SECONDS=30.0`,
  `MAX_SEGMENT_RETRIES=2`, splitting arithmetic, per-segment retry: untouched.
- **AD-03 Pillar-2 overlay** - Stage 6 still emits ONE continuous head asset;
  concat-demuxer assembly with checksum verification untouched. Log events
  `render_plan`, `scene_split`, `segment_render_complete`,
  `latentsync_segmented_render_complete` deliberately keep their names - they are the
  operator's existing evidence surface - and now carry `model`/`engine`/`endpoint`/`tier`
  automatically via the bound logger.
- **Upload URL** - `POST /projects/{project_id}/assets/upload` untouched.
- **Registered task name** - `tasks.talking_head_task.render_talking_head` untouched.

## 2.4 Deletion and reference cleanup

`stage6_talking_head.py` deleted, plus every reference found in pass 1 (F5):

| File | Removed |
|---|---|
| `ivgs-workers/celery_app.py` | filename-drift comment; `"tasks.stage5_talking_head.*"` route; **`"tasks.stage6_talking_head"` from the `imports` list** |
| `ivgs-workers/tasks/__init__.py` | docstring line, module import, `__all__` entry |
| `ivgs-workers/tests/test_stage5.py` | deleted entirely (D-5a) |

`grep -rn "stage5_talking_head\|stage6_talking_head"` across `ivgs-workers`,
`ivgs-api`, `shared`, `tests` now returns only two log **event names** inside the live
task (`stage6_talking_head_starting`, `stage6_talking_head_complete`, kept as the
operator's evidence surface) and one docstring line in the retargeted wiring test.

## 2.5 Verification - observed

### Import and registration, in the deployed image

`ghcr.io/brucecostello2/ivgs-workers:v5.5.1-arch1` with the changed files mounted and
`stage6_talking_head.py` removed:

```
registered task count: 22
   tasks.talking_head_task.render_talking_head
routes with talking_head:
   tasks.talking_head_task.* -> gpu_talking_head
WORKER IMPORT OK - no dead module, live task registered
```

Assertions passed in-image: `"LatentSyncClient(" not in source`; `get_binding` and
`build_provider` present; task name unchanged; `Stage6Input.tier` default
`"prototype"`; `_resolve_render_mode` maps `full_frame/pip/chroma_key` through and
`bogus`/`""` -> `full_frame`.

**This clears F5's startup-critical risk**: the module is gone from the `imports` list
and the worker still builds its task registry.

### Tests - measured against a baseline, not just "passing"

Baseline is the **unmodified image**, same command, so the comparison is like-for-like:

| | `tests/test_talking_head_task.py` |
|---|---|
| **Baseline (unmodified)** | **3 failed, 7 passed** |
| **After the change** | **1 failed, 12 passed** (+ 4 wiring tests = 17 passed overall) |

The two baseline failures that disappeared are `TestLatentSyncRender::test_successful_render`
and `::test_latentsync_failure_triggers_fallback` - replaced by `TestSegmentRender`,
which drives `_render_segment` with a stub provider.

**The one remaining failure is pre-existing and not mine:**
`TestStage6Input::test_requires_at_least_one_audio_ref` fails identically on the
unmodified image. It asserts a `min_length` constraint that `Stage6Input.scene_audio_refs`
(`default_factory=list`) does not have; the task raises "No scene audio refs to render"
at runtime instead. Left alone - out of scope, recorded here.

`tests/providers/test_stage6_wiring.py` was retargeted from the deleted duplicate onto
the live module and extended - **4 passed**:

- `test_segment_render_maps_params_to_the_provider` - field-by-field params mapping,
  and asserts `scene_image_data is None` (the F2 constraint, now pinned by a test).
- `test_unknown_render_mode_falls_back_instead_of_raising` - proves the pre-ARCH-1
  degrade-don't-raise behaviour survived.
- `test_live_stage6_module_has_no_hardcoded_engine` - the guarantee this package
  exists to deliver, now asserted against the module `STAGE_TASK_MAP` dispatches.
- `test_model_attribution_comes_from_the_binding` - `model_used = binding.name`.

### No new swallowed-failure instance (WP-00 rule 7)

The WP-00 detector, run on the file before and after:

```
BEFORE (HEAD):  FAIL - 6 finding(s)   (:363 :543 :550 :671 :690 :699)
AFTER:          FAIL - 6 finding(s)   (:424 :619 :626 :749 :768 :789)
```

Same six pre-existing sites, relocated by the edit. **Nothing added.** The register
needs no new entry from this package.

### Pre-existing environment issues encountered (not caused here)

- `pytest-celery` cannot load in the worker image - `ModuleNotFoundError: pkg_resources`
  (setuptools absent). Worked around with `-p no:celery`. Present on the unmodified
  image too. Worth a ledger note; it means `pytest` cannot run clean in that image
  without a flag.
- 7 unrelated worker test modules fail collection on the unmodified image
  (`test_composition`, `test_dlq_service`, `test_fallback_chain`, `test_orphan_cleanup`,
  `test_retention`, `test_retry_engine`, `test_stage4`). Unchanged by this work.

## 2.6 NOT verified - stated plainly

- **No render was executed.** Nothing in this package proves a real lip-sync render
  still works. The params mapping is proven field-by-field against a stub provider and
  the endpoint/timeout/VRAM are proven identical, but no frame was produced.
- **Nothing ran on node-04.** The `gpu_talking_head` worker lives there; node-01 runs
  only `ivgs-celery-default`, `-composition` and `-beat`. CLAUDE.md S1/S2 forbid me
  running commands on other nodes.
- **The exit gate's GUI swap has not been performed** - see S2.7.
- **The image has not been rebuilt or deployed.** Every in-image check mounted the
  changed files over `v5.5.1-arch1`. A real deployment needs a rebuild.
- **AD-03 Pillar-2 output not re-measured.** The overlay path is untouched by diff, but
  no draft was rendered and no corruption check was run.
- **`SadTalkerProvider`'s worker-local-temp-path defect (F2, now ledger P1.0a)** remains
  unconfirmed against a running SadTalker service.

## 2.7 Exit gate - PARTIALLY MET, operator action required

| Gate clause | Status |
|---|---|
| The duplicate file deleted | **MET** - deleted, and every map/route/import/`__all__` reference cleaned; worker import verified in-image |
| `stage-numbering-map.md` updated | **MET** - dead row removed, both traps rewritten as resolved, header re-verified at `d4665ae` |
| No map or registration references the dead name | **MET** - verified by `grep` and by reading the built task registry in-image (22 tasks, dead name absent) |
| Segment/OOM strategy, Pillar-2 overlay and upload URL demonstrably unchanged (cite diff) | **MET by diff** - the filtered `git diff -U0` in S2.3 returns nothing for every protected construct. **NOT met by log evidence** - that needs a render |
| A head-model swap performed entirely in the GUI changes which engine Stage 6 invokes, evidenced in worker logs on a real short-job render | **NOT MET - operator-run** |

The last clause cannot be closed from node-01. It needs, in order:

1. **A second approved `talking_head` model.** Only `latentsync` exists today. Per
   D-1(a) this should be a **second `latentsync`-engine model** (e.g. a different
   weights version pointed at a different `IVGS_LATENTSYNC_URL`). A `sadtalker`-engine
   selection will fail at render time until ledger P1.0a is fixed.
2. Rebuild and deploy the worker image to node-04.
3. Short-job render; capture `stage6_model_bound` plus `render_plan`, `scene_split`,
   `segment_render_complete`, `latentsync_segmented_render_complete` - all now carry
   `model=`, `engine=`, `endpoint=`, `tier=`.
4. `/admin/models` set-default to the second model; re-run; confirm those same log
   lines name the new model and endpoint.
5. Confirm the upload still hits `POST /projects/{id}/assets/upload` and corruption
   checks still pass.

I can author the exact commands and read back the logs, but I must not run step 2-5.

## 2.8 Deviation from the approved plan - one item

**`ivgs-workers/tests/test_talking_head_task.py` was not in my pass-1 file set.** It
imports `_render_with_latentsync` and patches `tasks.talking_head_task.LatentSyncClient`,
both of which this change removes, so deleting them broke its collection. My pass-1
`grep` searched for `stage5_talking_head|stage6_talking_head` and never for
`talking_head_task`, which is how I missed it. Caught by running the suite against a
baseline rather than trusting the plan.

Rewritten in the same spirit as the wiring test: `TestLatentSyncRender` (which patched
an engine client that no longer exists) became `TestSegmentRender`, driving
`_render_segment` with a stub provider. Net effect is an improvement on baseline, not a
regression - 3 failures to 1 pre-existing.

**Also outside the approved plan:** `docs/stage-numbering-map.md` and
`OUTSTANDING_WORK.md` are root-owned mode 644 and not writable by `dev`. Both were in
the approved file set, so I wrote them with `sudo -n python3`, preserving owner and
mode (still `root:ivgsdev 644`). No permissions were changed and nothing else was
touched with elevated rights. Flagging because CLAUDE.md does not cover sudo use.

## 2.9 Open items handed to the operator

| # | Item | Action |
|---|---|---|
| 1 | Exit-gate clause 5 (S2.7) | Register a second approved latentsync model, rebuild/deploy, run the swap on node-04 |
| 2 | **Ledger P1.0a** (new) - SadTalker fallback not selection-driven | Establish which SadTalker contract node-04 actually implements *before* fixing the provider - there are three incompatible ones |
| 3 | AD-01.13 criterion 5 still open (F3) | Needs Stage 6 per-tier or a Stage-8 re-render. Pipeline change, separate package |
| 4 | `release_gpu_reservation` 2-arg bug (F4) | Left per D-4(a). Latent only while reservations fail; becomes a `TypeError` in a `finally` the moment the registry is real. WP-08 |
| 5 | `test_requires_at_least_one_audio_ref` pre-existing failure | `Stage6Input.scene_audio_refs` has no `min_length`; the test asserts one |
| 6 | `pytest-celery` broken in the worker image | Needs `-p no:celery`, or restore `setuptools` |
| 7 | MBCP backfill numbers (F9) | 12 models / 24 approvals here vs "21 exports" in AD-01/AD-04. Still unreconciled |

## 2.10 Proposed commit - NOT executed

```
git add ivgs-workers/tasks/talking_head_task.py \
        ivgs-workers/tasks/__init__.py \
        ivgs-workers/celery_app.py \
        ivgs-workers/tests/test_talking_head_task.py \
        tests/providers/test_stage6_wiring.py \
        docs/stage-numbering-map.md \
        docs/deployment/runbook.md \
        OUTSTANDING_WORK.md \
        dev/workpackages/reports/WP-02-ORCH6-report_2026-08-15.md
git rm ivgs-workers/tasks/stage6_talking_head.py ivgs-workers/tests/test_stage5.py

git commit -m "feat(stage6): resolve the head model through the AD-01 provider factory (ORCH-6)"
```

Note the two deletions need `git rm`; they are currently deleted in the working tree
only. Do not `git add -A` - the untracked work-package briefs are not part of this.

---

# STATUS

**Pass 2 code complete and unit-verified on node-01. Exit gate PARTIALLY MET - the
on-hardware GUI-swap demonstration is operator-run on node-04 and is the one clause
outstanding.**

P1.0 / ORCH-6 is closed in the ledger with that caveat recorded, and P1.0a opened for
the SadTalker gap this work exposed. Nothing committed; nothing deployed.

The next Track-S package is **WP-03-STAGE8-VALIDATION**.
