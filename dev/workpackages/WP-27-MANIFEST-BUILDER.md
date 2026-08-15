# WP-27-MANIFEST-BUILDER — Stage-4 layer binding, and Stage 7's swallowed ffmpeg failure

| | |
|---|---|
| **Ledger** | Swallowed-failure register instances **14** and **15** |
| **Tier** | B (observable) · **Track S**, after WP-26, before M2 |
| **Report** | `reports/WP-27-MANIFEST-BUILDER-report_<YYYY-MM-DD>.md` |
| **Blocks** | The full Stages 1→8 run (WP-26 task 5) — a fresh manifest is unusable today |

## Two defects, found together, one masking the other

Both verified live on 2026-08-15 during WP-03, job
`7980c0b9-8d9e-4d3b-955e-f2b97bf137dd`.

### Defect A — the Stage-4 builder binds every scene asset as a background layer

| Manifest | Layers per scene | Contents |
|---|---|---|
| June, job `79b90f48` | **1** | background |
| 2026-08-15, job `7980c0b9` | **4** | 2 images **and 2 audio**, all `layer_type: background` |

Scene 0's layers, all `0–10000 ms`, all typed `background`:

```
d83c6ac7  audio   <- first in the list, so ffmpeg receives a WAV as the background
be4453e8  audio
7de1b630  image
ca6d7f83  image
```

The builder applies **no `asset_type` filter and no deduplication**. It looked correct
in June only because there was one asset per scene then; AD-03 §11.5 records duplicate
audio assets accumulating from re-runs since. **The duplicates exposed a filter that
never existed.**

Downstream symptom:

```
Input #0, wav, from '/tmp/ivgs_stage7_.../bg_8e25826c-....bin.png'
FFmpeg failed (rc=1)
```

### Defect B — Stage 7 logs the failure and reports `task_succeeded`

```
{"error": "FFmpeg failed (rc=1): ...", "scene_count": 6}
{"event": "task_succeeded", "task_name": "tasks.prototype_draft_task.assemble_prototype_draft"}
```

The non-zero return is logged; the task then returns normally and Celery records
SUCCESS. **No draft was produced.** This is the register's defining shape, and it is
what concealed Defect A — without it, A would have surfaced the moment it occurred.

## Tasks

1. **Fix the builder.** Filter background layers to image/video asset types; dedupe to
   the latest per scene by `created_at`. Establish first whether a scene should ever
   carry more than one background layer — if the schema intends layered composition,
   the fix is a type filter plus correct `layer_type` assignment, not a blunt "take
   one". Read the layer consumer in `ffmpeg_client.compose_scene` before deciding.
2. **Fix Stage 7 to raise on `rc != 0`** instead of returning a success-shaped result.
   Then confirm a failing scene actually fails the task and the job row reflects it.
3. **Detector rule.** `scripts/swallow_detector.py` cannot currently express this
   shape: SF005 fires only on a `status` key carrying a failure literal, and this
   task's return has no such key. Add a rule for *"stage task logs an error-level event
   and then returns without raising"*, or record with evidence why it cannot be
   expressed without dataflow analysis (which WP-00 forbids).
4. **Re-run the Stage 4 → 7 path** on the reference project with a freshly built
   manifest and confirm it now matches the June manifest's shape and produces a draft.

## Known adjacent issues — record, do not fix here

- **Most scenes on the reference project have 0 images and 2 audio** (`assets` grouped
  by `scene_id`). Whether that is a media-generation gap or a `scene_id` linkage
  artefact was **not** established — the June manifest resolves valid image assets
  regardless, so the two views disagree and nobody has reconciled them.
- **`total_duration_ms` is 115000** on both the June and the fresh manifest — the stale
  115 s storyboard estimate against a real 214.88 s narration (AD-03 §11.2). The
  pipeline anchors on probed audio so output is correct, but the manifest number is
  wrong and misleads anyone reading it.
- Duplicate assets accumulating from re-runs (AD-03 §11.5) — the root condition that
  exposed Defect A. **Do not delete assets on the reference project** (operator
  decision, 2026-08-15); it holds every known-good artefact.

## Scope

**In:** the Stage-4 layer binding, Stage 7's ffmpeg return handling, the detector rule,
and re-verification.
**Out:** asset deletion or any mutation of the reference project's assets; segment
arithmetic (WP-04); the manifest duration estimate.

## Exit gate

A freshly built manifest has one background layer per scene, of an image/video asset
type, and the Stage 4 → 7 path produces a valid draft from it (corruption checks pass,
`num_layers: 2` preserved). A scene whose ffmpeg invocation returns non-zero fails the
task — demonstrated, not asserted. The detector either catches the pattern or the
report records with evidence why it cannot.
