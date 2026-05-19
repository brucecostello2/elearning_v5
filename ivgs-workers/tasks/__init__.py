"""
IVGS v5 — Task Registration
==============================

Imports all Celery tasks so they are registered with the app on worker startup.
Celery auto-discovers tasks from modules listed in app.conf.include,
but explicit imports here ensure reliable registration and provide
a central manifest of all available tasks.

Task inventory:
- Stage 1: tasks.stage1_transcript.refine_transcript_task
- Stage 2: tasks.stage2_storyboard.generate_storyboard_task
- Orchestrator: tasks.pipeline_orchestrator.dispatch_pipeline
- Orchestrator: tasks.pipeline_orchestrator.handle_stage_completion
- Beat: tasks.pipeline_orchestrator.supervise_worker_heartbeats
- Beat: tasks.pipeline_orchestrator.process_dead_letter_queue
- Beat: tasks.pipeline_orchestrator.run_orphan_cleanup
- Beat: tasks.pipeline_orchestrator.run_retention_migration
- Beat: tasks.pipeline_orchestrator.run_backup_verification
- Beat: tasks.pipeline_orchestrator.collect_gpu_fleet_metrics
"""

from tasks.stage1_transcript import refine_transcript_task  # noqa: F401
from tasks.stage2_storyboard import generate_storyboard_task  # noqa: F401
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
    "dispatch_pipeline",
    "handle_stage_completion",
    "supervise_worker_heartbeats",
    "process_dead_letter_queue",
    "run_orphan_cleanup",
    "run_retention_migration",
    "run_backup_verification",
    "collect_gpu_fleet_metrics",
]
