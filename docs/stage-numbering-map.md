# Stage Numbering: Spec vs Files vs Registered Task Names

> **Verified against `brucecostello2/elearning_v5` @ `d4665ae`, 2026-08-15.**
> Re-verify on any change to task registration. The previous version of this document listed three files that do not exist and one that is dead code; it is the document that should have caught the mismatches below and did not.

## Why three columns

The filename is **not** the identity that matters. `STAGE_TASK_MAP` in `ivgs-workers/tasks/pipeline_orchestrator_v2.py` dispatches by **registered task name** — the `name=` argument on the Celery decorator. Filenames and registered names drifted apart historically and were never reconciled; the map was aligned to the names (commit `9f692ab`), and the tasks were deliberately **not** renamed.

A mismatch between the map and a registered name is a runtime-only `next_stage_task_not_registered` that no static check catches. See `OUTSTANDING_WORK.md` v4.0 **P2.3**.

## Current mapping

| Spec stage | Spec name | Implementation file | **Registered task name** (authoritative) | Queue |
|---|---|---|---|---|
| 1 | Transcript Refinement | `stage1_transcript.py` | `tasks.stage1_transcript.refine_transcript_task` | `gpu_llm` |
| 2 | Storyboard Generation | `stage2_storyboard.py` | `tasks.stage2_storyboard.generate_storyboard_task` | `gpu_llm` |
| 3 | Media — image / animation | `stage3_images.py` | `tasks.stage3_images.generate_scene_images_task` | `gpu_image` |
| 3 | Media — video clip | `video_generation_task.py` | `tasks.video_generation_task.generate_video_clips` | `gpu_video` |
| 4 | Composition Manifest | `stage4_manifest.py` | `tasks.stage4_manifest.build_composition_manifest` | `default` |
| 5 | Audio / TTS | `stage5_voiceover.py` | ⚠️ `tasks.stage4_voiceover.generate_voiceover_task` | `gpu_tts` |
| 6 | Talking Head | `talking_head_task.py` | `tasks.talking_head_task.render_talking_head` | `gpu_talking_head` |
| 7 | Prototype Draft | `stage7_prototype_draft.py` | ⚠️ `tasks.prototype_draft_task.assemble_prototype_draft` | `composition` |
| 8 | Final Render | `stage8_final_render.py` | ⚠️ `tasks.final_render_task.render_final` | `composition` |

⚠️ = registered name does not match its filename.

## Orchestration and periodic tasks

| File | Registered name | Live? |
|---|---|---|
| `pipeline_orchestrator_v2.py` | `tasks.pipeline_orchestrator_v2.dispatch_pipeline` | ✅ |
| | `…v2.handle_stage_completion` | ✅ |
| | `…v2.dispatch_media_generation` | ✅ |
| | `…v2.media_join_watchdog` | ✅ (Beat, 5 min) |
| | `…v2.build_composition_manifest` | ❌ dead inline duplicate — the map dispatches `stage4_manifest` |
| `pipeline_orchestrator.py` | `…pipeline_orchestrator.dispatch_pipeline` / `handle_stage_completion` | ❌ v1 stage orchestration, dead |
| | `…supervise_worker_heartbeats`, `process_dead_letter_queue`, `run_orphan_cleanup`, `run_retention_migration`, `run_backup_verification`, `collect_gpu_fleet_metrics` | ✅ **the live Beat schedule** |
| `periodic_tasks.py` | `ivgs_workers.tasks.periodic_tasks.*` | ❌ dormant duplicates — internal imports reference a package that does not exist. **Only** `poll_model_node_availability` is scheduled. |

## Two traps this table existed to prevent (both now resolved)

**1. The talking-head duplicate is gone (resolved 2026-08-15).** `stage6_talking_head.py`
— never dispatched, but the only file that resolved the head model through the AD-01
provider factory — was the reason certified models could not be selected. The binding has
been **promoted** into the live `talking_head_task.py` and the duplicate deleted
(WP-02-ORCH6, ledger P1.0 / ORCH-6). The registered task name is unchanged.

Two consequences worth carrying forward. Stage 6 now **fails loudly** with
`SelectionError` when no approved, enabled, default `talking_head` model exists — it does
not fall back to a hardcoded engine, because a silent fallback would make a GUI swap
appear to work when it had not. And the SadTalker *fallback* inside Stage 6 is still
engine-direct: the shared SadTalker provider requires a per-scene still image that this
whole-project stage does not have, so a `sadtalker`-engine selection fails at render time
(WP-02-ORCH6 finding F2).

**2. The wrong upload URL died with the duplicate.** `stage6_talking_head.py:241` posted
to `…/assets/upload`; the live `talking_head_task.py` correctly posts to
`…/projects/{id}/assets/upload`. That file no longer exists, so the bug can no longer be
inherited by reviving it.

## Under AD-05

The migration replaces string dispatch with typed function calls, so this entire mismatch class disappears — a mis-referenced stage becomes an import-time error. **This document then becomes obsolete and should be deleted, not maintained.** Until cutover, it is the authoritative reference for what actually runs.
