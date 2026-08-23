# WP-27-MANIFEST-BUILDER — report

| | |
|---|---|
| **Package** | **No brief file exists.** Built from swallow-register instances **14** and **15** (`reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md`), which both name "Owned by WP-27-MANIFEST-BUILDER", plus the operator's scoping in the 2026-08-23 overnight batch instruction. |
| **HEAD at start** | `01a35ed` (batch base `f70d63e`) |
| **Date** | 2026-08-23 |
| **Scope given** | (a) Stage 7 must raise on ffmpeg `rc != 0` instead of reporting `task_succeeded` over no draft — instance 14. (b) The Stage-4 manifest builder must filter background layers to image/video asset types and dedupe to latest per scene — instance 15. Tests proving each fix fails pre-fix. Close register entries only per the register's own closing rule. |

## Scope authorisation — recorded, because a binding rule is involved

`dev/CLAUDE.md` §3 and WP-QUEUE common rule 5 forbid modifying **the eight stage task bodies**.
Stage 7 is one of them. Rule 5's own wording carries the exception — *"except where a brief
explicitly scopes it"* — and the operator's instruction explicitly scopes exactly this edit, as
does the register's own `Scope/action (WP-27): raise on rc != 0 instead of returning`.

Reading AD-05 §8 directly (`docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md:210-233`),
the freeze is aimed at **migration sessions**: *"If a **migration session** finds itself editing
stage internals, stop."* Its purpose is to stop the Temporal migration ballooning into a stage
rewrite. This is a two-line behavioural fix to an error path, not a rewrite of stage internals,
and it is not a migration session. **Proceeding, and recording the reasoning so the exception is
visible rather than assumed.**

---

# PASS 1 — findings

## 1.1 Which nodes execute this code — verified, because tonight's deploy depends on it

The operator's instruction says both fixes run on node-01 workers, and conditions the whole
batch's deploy on that being true. Verified two ways:

**Routing.** `ivgs-workers/tasks/pipeline_orchestrator_v2.py:124-135` `STAGE_QUEUE_MAP` (the
authoritative dispatcher; `celery_app.py:119` `TASK_ROUTES` is the fallback and agrees):

```
PROTOTYPE_DRAFT       (Stage 7) -> "composition"
COMPOSITION_MANIFEST  (Stage 4) -> "default"
```

**Consumers.** From the live fleet (`celery inspect active_queues`, this session):

| Worker | Queues |
|---|---|
| `composition-worker@node01` | **composition** |
| `default-worker@node01` | **default**, notifications, cleanup |
| `celery-worker@node02` | gpu_llm |
| `cogvideox-worker@node03` | gpu_video |
| `image-worker@node04` | gpu_image, gpu_talking_head, gpu_tts |

Neither `composition` nor `default` is consumed anywhere but node-01. **Confirmed: node-02/03/04
never execute Stage 7 or Stage 4.**

**And half of this package is not even in the workers image.** Stage 4's manifest is built
**server-side by the Pipeline API** — `tasks/stage4_manifest.py:1-19` is a thin driver that calls
`POST /api/v1/jobs/{id}/manifest/generate`. The defective code is in `ivgs-api`, which runs only
on node-01.

## 1.2 Instance 14 — Stage 7 returns after failing

`ivgs-workers/tasks/stage7_prototype_draft.py:573-591`:

```python
    except Exception as e:
        log.error("stage7_unexpected_error", error=str(e))
        output.status = StageStatus.FAILED
        output.errors.append(str(e))
        output.completed_at = datetime.now(timezone.utc)
        update_job_status(job_id, "failed", error_message=f"Stage 7 error: {e}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Dispatch stage completion          <- OUTSIDE the try
    output_dict = output.model_dump(mode="json")
    celery_app.send_task("tasks.pipeline_orchestrator_v2.handle_stage_completion", ...)
    return output_dict                   <- returns normally; Celery records SUCCESS
```

The `ffmpeg` failure propagates out of `ffmpeg.compose_timeline` (`:493`), is caught by the broad
`except Exception`, is faithfully recorded **inside the output object** — and then execution
falls through the `finally` to a plain `return`. Celery sees a task that returned a value, so it
records SUCCESS. That reproduces the register's captured evidence exactly: the `FFmpeg failed
(rc=1)` line and `task_succeeded` for the same task, with no draft produced.

**Two further paths reach the same lie**, and the register did not list them:
`:470` `"No scenes could be composed"` and `:549` `scenes_composed == 0` both set
`StageStatus.FAILED` and then fall through the same `return`. A fix that only caught the ffmpeg
exception would leave two open.

**PARTIAL_SUCCESS must keep returning** — `:547`, some scenes composed, some failed. That is a
real partial result, not a failure, and raising on it would be an overcorrection.

## 1.3 Instance 15 — worse than recorded: the layer mapping is written against asset-type names that do not exist

`ivgs-api/app/api/v1/manifests.py:189-199` binds **every** asset of a scene as a layer, with no
dedup and no filter:

```python
for asset in scene_assets:
    layers.append({"layer_type": _asset_type_to_layer(asset.asset_type), ...})
```

and `manifests.py:369-380`:

```python
mapping = {
    "scene_image": "background", "video_clip": "background", "animation": "background",
    "tts_audio": "audio", "talking_head": "talking_head",
    "caption_srt": "captions", "caption_vtt": "captions", "lower_third": "lower_third",
}
return mapping.get(asset_type, "background")
```

**Verified against the live schema** — `enum_range(NULL::asset_type)`:

```
image, video, audio, document, talking_head, final_render, reference_clip
```

Of the eight mapping keys, **exactly one — `talking_head` — is a real enum value.** Every other
key is a name this schema has never used. So `image`, `video`, `audio`, `document`,
`final_render` and `reference_clip` all miss the mapping and hit the default.

**And the default is `"background"`.** That is what turns a miss into damage: an unmapped type
does not become an unknown layer or get dropped, it becomes *the scene background*. This is why
the register saw two `audio` assets typed `background` — `audio` is not a key — and it is why
`ffmpeg` received a WAV as the background input. On the live data it is worse still: a
`document` (a source PDF) and a `reference_clip` (the user's presenter video) would also be
offered as scene backgrounds.

Live asset population, for scale:

```
audio 12 | image 12 | final_render 7 | video 6 | document 6 | reference_clip 1 | talking_head 1
```

So of 45 assets, **44 miss the mapping**; 25 of them (`document`, `final_render`,
`reference_clip`, `audio`) would be typed `background`.

The dedup half is real too — nothing groups or orders the assets, and `AD-03 S11.5` records
duplicates accumulating from re-runs — but **the mapping defect is the larger one**, and the
register attributes the whole symptom to "no filter and no dedup". Recorded as a correction to
instance 15.

## 1.4 Proposed fix

**`ivgs-api/app/api/v1/manifests.py`** — three changes, all in the generate path:

1. `_asset_type_to_layer` keyed on the **real** enum values, and returning `None` for anything
   unmapped instead of defaulting to `background`. An unknown asset type is excluded from the
   timeline and logged; it is never silently promoted to the scene background.
2. Background layers restricted to visual types (`image`, `video`).
3. Dedup to the **latest per (scene, layer_type)**, which needs `created_at` in the query and a
   deterministic order. Scenes that end up with no background are logged as a warning and
   surfaced in the response — they are the separate media-generation gap the register notes, and
   they must not pass silently.

**`ivgs-workers/tasks/stage7_prototype_draft.py`** — after dispatching `handle_stage_completion`
(so the orchestrator still receives the failed stage output, which is its contract), **raise**
when `output.status is FAILED`. Order matters: dispatch first, then raise. `PARTIAL_SUCCESS` and
`COMPLETED` return as before.

Tests for both, each written to fail against the pre-fix code.

---

# PASS 2 — what changed, and how it was verified

## 2.1 Change summary

```
 ivgs-workers/tasks/stage7_prototype_draft.py    | +Stage7RenderError; raise on FAILED
 ivgs-api/app/api/v1/manifests.py                | mapping rewritten; filter + dedupe
 ivgs-workers/tests/test_wp27_stage7_raises.py   | NEW   8 tests
 ivgs-api/tests/test_wp27_manifest_layers.py     | NEW  14 tests
```

**Stage 7** — new `Stage7RenderError`, raised **after** `handle_stage_completion` is dispatched
so the orchestrator still receives the failed stage output while Celery records FAILED. It fires
on all three paths that set `StageStatus.FAILED` (the broad `except` that catches the ffmpeg
failure, `"No scenes could be composed"`, and `scenes_composed == 0`), not only the one the
register named. `PARTIAL_SUCCESS` and `SUCCESS` return exactly as before.

**Manifests** — `_asset_type_to_layer` is rebuilt on the real enum and returns `Optional[str]`;
the `"background"` default is gone, so an unmapped type is **excluded and logged** rather than
promoted to the scene background. `_ASSET_TYPES_NOT_LAYERS` declares `document`, `final_render`
and `reference_clip` as deliberately-not-layers, so every enum value is classified and nothing
falls to a default. The assembly loop keeps the **latest asset per `(scene, layer_type)`**, which
required adding `created_at` to the query and `ORDER BY created_at ASC, id ASC`. Scenes that end
with no background are logged and recorded in the manifest as `scenes_without_background`, so a
downstream stage can refuse a manifest with no picture instead of discovering it at ffmpeg.

## 2.2 Tests — 22 passing, and shown to fail pre-fix

```
ivgs-api/tests/test_wp27_manifest_layers.py    14 passed in 0.69s
ivgs-workers/tests/test_wp27_stage7_raises.py   8 passed in 0.40s
```

The brief required tests proving each fix fails pre-fix. Rather than asserting that in prose,
**both pre-fix implementations are reproduced verbatim in the test files and exercised**:

- `TestTheDefectIsReal::test_prefix_typed_audio_and_documents_as_background` runs the old
  `mapping.get(asset_type, "background")` and asserts it returns `"background"` for `audio`,
  `document`, `reference_clip` and `final_render` — the exact symptom in instance 15.
- `TestLayerAssembly::test_prefix_produced_four_background_layers` replays the register's
  captured scene 0 (`d83c6ac7` audio, `be4453e8` audio, `7de1b630` image, `ca6d7f83` image)
  through the old loop and asserts **4 layers, all `background`, with the WAV first** — i.e. the
  input ffmpeg treats as the picture. The same scene through the fixed loop yields
  `["audio", "background"]`, the background being the later image.
- `TestTheDefectIsReal::test_prefix_returned_normally_after_an_ffmpeg_failure` shows the old
  terminal behaviour returning a `status: failed` payload — which is precisely how Celery came
  to record SUCCESS.
- `test_dispatch_precedes_the_raise_in_the_source` reads the actual source of
  `assemble_prototype_draft` and asserts the dispatch index precedes the raise index. Order is
  load-bearing: raising first would leave a failed Stage 7 never reaching
  `handle_stage_completion`, so the job would hang rather than fail.

## 2.3 Verified live

- **Routing** (1.1) — from `STAGE_QUEUE_MAP` and a live `celery inspect active_queues`.
- **The asset_type enum** — `enum_range(NULL::asset_type)` against the running Postgres, which
  is what exposed that 7 of the 8 mapping keys were fictional.
- **The asset population** — 45 rows across all seven types; 44 of them missed the old mapping.
- Both files parse; 22 tests pass.

## 2.4 NOT verified

- **No pipeline run.** Neither fix has been observed on a real job. Stage 7 has not been made to
  fail on the deployed image, and no manifest has been generated through the corrected API path.
  The batch instruction does not authorise a pipeline run, and the Model Store is unpopulated.
- The code is not deployed at the time of writing; it ships with tonight's node-01 deploy.

## 2.5 Register entries — NOT closed, per the register's own closing rule

The register's rule is *"do not close one without observed evidence that the failure now
surfaces."* Unit tests are not that evidence. **Instances 14 and 15 stay OPEN.**

After tonight's node-01 deploy a deliberate probe inside the running containers can supply it —
the same method that closed instances 2 and 3 under WP-34. Result recorded in the batch summary.
Note that a full closure of 15 arguably needs a generated manifest from a real job, which is a
larger claim than a probe can make; that is flagged rather than assumed away.

## 2.6 Correction to the register, and a new instance

**Instance 15's diagnosis was incomplete.** It records "no `asset_type` filter and no
deduplication". Both are true, but the dominant cause is that the mapping was keyed on asset-type
names that do not exist in this schema, combined with a `"background"` catch-all default. With
one asset per scene (June) the default hid completely; duplicates only made it visible. Recorded
in the register alongside the entry.

**Instance 14 understated the blast radius**: three code paths set FAILED and returned, not one.

**New instance for the register (queue rule 7): `_asset_type_to_layer`'s `"background"`
default.** `mapping.get(asset_type, "background")` is the swallow shape applied to a *lookup*
rather than an error path — a miss produced a confident, and maximally damaging, answer instead
of surfacing that nothing was known. Added as **instance 19**.
