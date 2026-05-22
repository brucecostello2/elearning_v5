"""
IVGS v5 — Task Registration
==============================

Imports all Celery tasks so they are registered with the app on worker startup.
Celery auto-discovers tasks from modules listed in app.conf.include,
but explicit imports here ensure reliable registration and provide
a central manifest of all available tasks.

Task inventory (spec §6.1 — 8 stages):
- Stage 1: tasks.stage1_transcript.refine_transcript_task
- Stage 2: tasks.stage2_storyboard.generate_storyboard_task
- Stage 3: tasks.stage3_images.generate_scene_images
- Stage 4: tasks.stage4_manifest.build_composition_manifest
- Stage 5: tasks.stage5_voiceover.synthesize_voiceover
- Stage 6: tasks.stage6_talking_head.render_talking_head
- Stage 7: tasks.stage7_prototype_draft.assemble_prototype_draft
- Stage 8: tasks.stage8_final_render.render_final
- Orchestrator v1: tasks.pipeline_orchestrator (deprecated, kept for compat)
- Orchestrator v2: tasks.pipeline_orchestrator_v2
- Beat: periodic_tasks (DLQ, heartbeat, orphan, retention, backup, metrics)
"""

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
]
