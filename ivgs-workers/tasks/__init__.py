"""
IVGS v5 — Task Registration
==============================

Imports all Celery task modules so they register with the app on worker
startup. The authoritative registration path is ``app.conf.include`` in
``celery_app.py``; these imports mirror it so ``import tasks`` also registers
the full set and serves as a central manifest.

Task inventory (real registered names — several names differ from their
filenames; see ``celery_app.TASK_ROUTES``):
- Stage 1: tasks.stage1_transcript.refine_transcript_task
- Stage 2: tasks.stage2_storyboard.generate_storyboard_task
- Stage 3: tasks.stage3_images.generate_scene_images_task
           + tasks.video_generation_task.generate_video_clips
- Stage 4: tasks.stage4_manifest.build_composition_manifest
- Stage 5: tasks.stage4_voiceover.generate_voiceover_task        (file stage5_voiceover.py)
- Stage 6: tasks.stage5_talking_head.generate_talking_head_task  (file stage6_talking_head.py)
           + tasks.talking_head_task.render_talking_head
- Stage 7: tasks.prototype_draft_task.assemble_prototype_draft   (file stage7_prototype_draft.py)
- Stage 8: tasks.final_render_task.render_final                  (file stage8_final_render.py)
- Orchestrator v1: tasks.pipeline_orchestrator.* (linear dispatch + 6 beat/ops tasks)
- Orchestrator v2: tasks.pipeline_orchestrator_v2.* (canonical pipeline dispatch:
  parallel media generation + composition manifest)
- Dormant: tasks.periodic_tasks (not wired; H.1 consolidation item)
"""

# Symbol imports (kept so `from tasks import <symbol>` continues to work).
from tasks.stage1_transcript import refine_transcript_task  # noqa: F401
from tasks.stage2_storyboard import generate_storyboard_task  # noqa: F401
from tasks.stage4_manifest import build_composition_manifest  # noqa: F401
from tasks.pipeline_orchestrator import (  # noqa: F401
    dispatch_pipeline,
    handle_stage_completion,
    supervise_worker_heartbeats,
    process_dead_letter_queue,
    run_orphan_cleanup,
    run_retention_migration,
    run_backup_verification,
    collect_gpu_fleet_metrics,
)

# Module imports for the remaining stages/orchestrator: importing the module
# runs its @celery_app.task decorators (registration) without depending on
# internal function names.
from tasks import (  # noqa: F401
    stage3_images,
    stage5_voiceover,
    stage6_talking_head,
    stage7_prototype_draft,
    stage8_final_render,
    video_generation_task,
    talking_head_task,
    pipeline_orchestrator_v2,
)

__all__ = [
    "refine_transcript_task",
    "generate_storyboard_task",
    "build_composition_manifest",
    "dispatch_pipeline",
    "handle_stage_completion",
    "supervise_worker_heartbeats",
    "process_dead_letter_queue",
    "run_orphan_cleanup",
    "run_retention_migration",
    "run_backup_verification",
    "collect_gpu_fleet_metrics",
    "stage3_images",
    "stage5_voiceover",
    "stage6_talking_head",
    "stage7_prototype_draft",
    "stage8_final_render",
    "video_generation_task",
    "talking_head_task",
    "pipeline_orchestrator_v2",
]
