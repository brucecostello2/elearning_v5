"""
IVGS v5 — Pipeline Orchestrator (v1)
=======================================

.. deprecated:: 5.0.1
   This is the v1 orchestrator. The v2 orchestrator
   (pipeline_orchestrator_v2.py) adds composition manifest building,
   parallel media dispatch, and enhanced checkpoint recovery.
   Migrate to v2 for new features. v1 is retained for backward
   compatibility with existing Celery Beat schedules and task references.

Event-driven pipeline orchestration per §6.4:
- Uses handle_stage_completion callbacks (NOT Celery chains)
- On stage success: determines next stage, enqueues corresponding task
- On stage failure: retry or route to DLQ
- Enables partial pipeline restart from checkpoints
- Celery Beat periodic tasks: heartbeat supervision, DLQ processing,
  orphan cleanup, retention migration, backup verification

Stage sequence (§6.1):
  1. Transcript Refinement
  2. Storyboard Generation
  3. Media Generation (parallel per scene)
  4. Composition Manifest
  5. Audio Generation (TTS)
  6. Talking Head Rendering
  7. Prototype Draft Assembly
  8. Final Render

User gates:
  - After Stage 2: user reviews/edits storyboard
  - After Stage 7: user reviews prototype
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
import structlog

from celery_app import IVGSBaseTask, celery_app
from config import WorkerConfig
from models.task_result import (
    PipelineJobContext,
    PipelineStage,
    StageStatus,
)
from utils.error_handler import (
    update_job_status,
)

logger = structlog.get_logger("ivgs.orchestrator")

# Stage transition map: current_stage → next_stage
# Stages with user gates return None (pipeline pauses for user review)
STAGE_TRANSITIONS: Dict[str, Optional[str]] = {
    PipelineStage.TRANSCRIPT_REFINEMENT.value: (
        PipelineStage.STORYBOARD_GENERATION.value
    ),
    # After storyboard: user gate (review/edit scenes)
    PipelineStage.STORYBOARD_GENERATION.value: None,
    # After user approval, Stage 3 is dispatched by API trigger
    PipelineStage.IMAGE_GENERATION.value: (
        PipelineStage.COMPOSITION_MANIFEST.value
    ),
    PipelineStage.VIDEO_GENERATION.value: (
        PipelineStage.COMPOSITION_MANIFEST.value
    ),
    PipelineStage.ANIMATION_GENERATION.value: (
        PipelineStage.COMPOSITION_MANIFEST.value
    ),
    PipelineStage.COMPOSITION_MANIFEST.value: PipelineStage.TTS_AUDIO.value,
    PipelineStage.TTS_AUDIO.value: (
        PipelineStage.TALKING_HEAD_RENDER.value
    ),
    PipelineStage.TALKING_HEAD_RENDER.value: (
        PipelineStage.PROTOTYPE_DRAFT.value
    ),
    # After prototype: user gate (review/approve)
    PipelineStage.PROTOTYPE_DRAFT.value: None,
    PipelineStage.FINAL_RENDER.value: None,
}

# Task name mapping for dispatch
STAGE_TASK_MAP: Dict[str, str] = {
    PipelineStage.TRANSCRIPT_REFINEMENT.value: (
        "tasks.stage1_transcript.refine_transcript_task"
    ),
    PipelineStage.STORYBOARD_GENERATION.value: (
        "tasks.stage2_storyboard.generate_storyboard_task"
    ),
    # Future phases will add Stage 3-8 task mappings
}


# ---------------------------------------------------------------------------
# Pipeline dispatch
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.pipeline_orchestrator.dispatch_pipeline",
    queue="default",
    max_retries=2,
    soft_time_limit=60,
)
def dispatch_pipeline(
    self: IVGSBaseTask,
    job_context_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Entry point: dispatch the pipeline for a render job.

    Creates job context, determines starting stage (or resume point),
    and enqueues the first task.
    """
    config = WorkerConfig()

    try:
        job_context = PipelineJobContext(**job_context_dict)
    except Exception as e:
        logger.error("pipeline_dispatch_input_error", error=str(e))
        raise ValueError(f"Invalid pipeline dispatch input: {e}") from e

    job_id = job_context.job_id
    project_id = job_context.project_id

    log = logger.bind(job_id=job_id, project_id=project_id)
    log.info("pipeline_dispatch_starting")

    # Determine starting stage
    start_stage = job_context.current_stage.value
    if job_context.resume_from_stage:
        start_stage = job_context.resume_from_stage
        log.info(
            "pipeline_resuming",
            resume_from=start_stage,
        )

    # Update job status
    update_job_status(job_id, "running")

    # Dispatch the starting stage
    task_name = STAGE_TASK_MAP.get(start_stage)
    if not task_name:
        log.error(
            "pipeline_no_task_for_stage",
            stage=start_stage,
        )
        update_job_status(
            job_id, "failed",
            error_message=f"No task registered for stage: {start_stage}",
        )
        return {
            "job_id": job_id,
            "status": "failed",
            "error": f"No task for stage {start_stage}",
        }

    # Build task input based on stage
    task_input = _build_stage_input(start_stage, job_context, config)

    # Dispatch task
    result = celery_app.send_task(
        task_name,
        kwargs={"task_input_dict": task_input},
        queue=_get_queue_for_stage(start_stage),
        priority=_get_priority(job_context.priority.value),
    )

    # Update job with Celery task ID
    _update_job_celery_task_id(job_id, result.id, config)

    log.info(
        "pipeline_stage_dispatched",
        stage=start_stage,
        task_name=task_name,
        celery_task_id=result.id,
    )

    return {
        "job_id": job_id,
        "project_id": project_id,
        "stage": start_stage,
        "celery_task_id": result.id,
        "status": "dispatched",
    }


# ---------------------------------------------------------------------------
# Stage completion handler
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.pipeline_orchestrator.handle_stage_completion",
    queue="default",
    max_retries=3,
    soft_time_limit=30,
)
def handle_stage_completion(
    self: IVGSBaseTask,
    stage_output_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle completion of a pipeline stage.

    Called as a callback after each stage task completes.
    Determines the next stage and dispatches it, or pauses at user gates.
    """
    config = WorkerConfig()

    completed_stage = stage_output_dict.get("stage", "")
    job_id = stage_output_dict.get("job_id", "")
    project_id = stage_output_dict.get("project_id", "")
    status = stage_output_dict.get("status", "")

    log = logger.bind(
        job_id=job_id,
        project_id=project_id,
        completed_stage=completed_stage,
    )

    log.info(
        "stage_completion_received",
        status=status,
    )

    # If stage failed, the task itself handles retry/DLQ
    if status == StageStatus.FAILED.value:
        log.warning(
            "stage_failed_no_advance",
            stage=completed_stage,
        )
        update_job_status(
            job_id, "failed",
            error_message=f"Stage {completed_stage} failed",
        )
        return {
            "job_id": job_id,
            "action": "none",
            "reason": "stage_failed",
        }

    # Determine next stage
    next_stage = STAGE_TRANSITIONS.get(completed_stage)

    if next_stage is None:
        # User gate — pipeline pauses
        gate_status = _determine_gate_status(completed_stage)
        log.info(
            "pipeline_paused_at_user_gate",
            completed_stage=completed_stage,
            gate_status=gate_status,
        )

        update_job_status(job_id, gate_status)

        return {
            "job_id": job_id,
            "action": "user_gate",
            "completed_stage": completed_stage,
            "gate_status": gate_status,
            "message": (
                f"Stage {completed_stage} complete. "
                "Awaiting user review to proceed."
            ),
        }

    # Dispatch next stage
    task_name = STAGE_TASK_MAP.get(next_stage)
    if not task_name:
        log.warning(
            "next_stage_task_not_registered",
            next_stage=next_stage,
        )
        return {
            "job_id": job_id,
            "action": "pending",
            "next_stage": next_stage,
            "message": f"Task for {next_stage} not yet registered",
        }

    # Build input for next stage from previous stage output
    _job_context_dict = _build_context_from_output(  # noqa: F841
        stage_output_dict, next_stage
    )
    task_input = _build_stage_input(next_stage, None, config, stage_output_dict)

    result = celery_app.send_task(
        task_name,
        kwargs={"task_input_dict": task_input},
        queue=_get_queue_for_stage(next_stage),
        priority=_get_priority(
            stage_output_dict.get("priority", "normal")
        ),
    )

    log.info(
        "next_stage_dispatched",
        next_stage=next_stage,
        task_name=task_name,
        celery_task_id=result.id,
    )

    return {
        "job_id": job_id,
        "action": "dispatched",
        "next_stage": next_stage,
        "celery_task_id": result.id,
    }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _build_stage_input(
    stage: str,
    job_context: Optional[PipelineJobContext],
    config: WorkerConfig,
    previous_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build task input dict for a given stage."""

    if stage == PipelineStage.TRANSCRIPT_REFINEMENT.value:
        context_dict = (
            job_context.model_dump(mode="json")
            if job_context
            else _extract_job_context(previous_output)
        )
        return {
            "job_context": context_dict,
            "transcripts": [],  # Stage 1 fetches from API
        }

    elif stage == PipelineStage.STORYBOARD_GENERATION.value:
        context_dict = (
            job_context.model_dump(mode="json")
            if job_context
            else _extract_job_context(previous_output)
        )

        # Extract refined transcripts from Stage 1 output
        refined_transcripts = []
        if previous_output:
            refined_transcripts = previous_output.get(
                "refined_transcripts", []
            )

        return {
            "job_context": context_dict,
            "refined_transcripts": refined_transcripts,
        }

    else:
        # Generic input for future stages
        context_dict = (
            job_context.model_dump(mode="json")
            if job_context
            else _extract_job_context(previous_output)
        )
        return {"job_context": context_dict}


def _extract_job_context(output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract job context from a stage output dict."""
    if not output:
        return {}
    return {
        "job_id": output.get("job_id", ""),
        "project_id": output.get("project_id", ""),
    }


def _build_context_from_output(
    output: Dict[str, Any],
    next_stage: str,
) -> Dict[str, Any]:
    """Build updated job context from previous stage output."""
    return {
        "job_id": output.get("job_id", ""),
        "project_id": output.get("project_id", ""),
        "current_stage": next_stage,
        "completed_stages": output.get("completed_stages", [])
            + [output.get("stage", "")],
    }


def _determine_gate_status(completed_stage: str) -> str:
    """Determine job status at a user gate."""
    if completed_stage == PipelineStage.STORYBOARD_GENERATION.value:
        return "storyboard_review"
    elif completed_stage == PipelineStage.PROTOTYPE_DRAFT.value:
        return "user_review"
    return "pending_review"


def _get_queue_for_stage(stage: str) -> str:
    """Get Celery queue name for a stage."""
    queue_map = {
        PipelineStage.TRANSCRIPT_REFINEMENT.value: "gpu_llm",
        PipelineStage.STORYBOARD_GENERATION.value: "gpu_llm",
        PipelineStage.IMAGE_GENERATION.value: "gpu_image",
        PipelineStage.VIDEO_GENERATION.value: "gpu_video",
        PipelineStage.ANIMATION_GENERATION.value: "gpu_image",
        PipelineStage.TTS_AUDIO.value: "gpu_tts",
        PipelineStage.TALKING_HEAD_RENDER.value: "gpu_talking_head",
        PipelineStage.COMPOSITION_MANIFEST.value: "default",
        PipelineStage.PROTOTYPE_DRAFT.value: "composition",
        PipelineStage.FINAL_RENDER.value: "composition",
    }
    return queue_map.get(stage, "default")


def _get_priority(priority: str) -> int:
    """Convert priority string to Celery priority integer."""
    return {"urgent": 9, "normal": 5, "batch": 2}.get(priority, 5)


def _update_job_celery_task_id(
    job_id: str,
    celery_task_id: str,
    config: WorkerConfig,
) -> None:
    """Update the render job with the Celery task ID."""
    api_url = f"{config.pipeline_api.full_base_url}/jobs/{job_id}"
    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            client.patch(
                api_url, json={"celery_task_id": celery_task_id}
            )
    except Exception as e:
        logger.warning(
            "job_celery_task_id_update_failed",
            job_id=job_id,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Celery Beat periodic tasks
# ---------------------------------------------------------------------------

@celery_app.task(
    name="tasks.pipeline_orchestrator.supervise_worker_heartbeats",
    queue="default",
    soft_time_limit=25,
)
def supervise_worker_heartbeats() -> Dict[str, Any]:
    """
    Heartbeat supervision task (runs every 30s via Celery Beat, §6.2).

    Checks for workers missing heartbeats:
    - >60s: marked suspected_dead
    - >120s: marked confirmed_dead, active jobs rescheduled
    """
    config = WorkerConfig()
    log = logger.bind(task="heartbeat_supervision")

    try:
        with httpx.Client(
            base_url=config.gpu_scheduler.base_url,
            timeout=config.gpu_scheduler.timeout_seconds,
            headers={
                "X-Service-Token": config.pipeline_api.service_token,
            },
        ) as client:
            resp = client.get("/fleet")
            if resp.status_code != 200:
                log.warning(
                    "fleet_status_fetch_failed",
                    status_code=resp.status_code,
                )
                return {"status": "error", "reason": "fleet_fetch_failed"}

            fleet_data = resp.json()
            nodes = fleet_data.get("nodes", [])

            now = time.time()
            suspected_dead = 0
            confirmed_dead = 0

            for node in nodes:
                last_heartbeat = node.get("last_heartbeat_epoch", 0)
                elapsed = now - last_heartbeat

                if elapsed > 120 and node.get("status") != "confirmed_dead":
                    confirmed_dead += 1
                    log.error(
                        "worker_confirmed_dead",
                        node_hostname=node.get("node_hostname"),
                        seconds_since_heartbeat=round(elapsed),
                    )
                    # Mark as dead and reschedule jobs
                    client.patch(
                        f"/nodes/{node.get('id')}",
                        json={"status": "confirmed_dead"},
                    )
                elif elapsed > 60 and node.get("status") == "online":
                    suspected_dead += 1
                    log.warning(
                        "worker_suspected_dead",
                        node_hostname=node.get("node_hostname"),
                        seconds_since_heartbeat=round(elapsed),
                    )
                    client.patch(
                        f"/nodes/{node.get('id')}",
                        json={"status": "suspected_dead"},
                    )

            return {
                "status": "ok",
                "total_nodes": len(nodes),
                "suspected_dead": suspected_dead,
                "confirmed_dead": confirmed_dead,
            }

    except Exception as e:
        log.error("heartbeat_supervision_error", error=str(e))
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="tasks.pipeline_orchestrator.process_dead_letter_queue",
    queue="default",
    soft_time_limit=120,
)
def process_dead_letter_queue() -> Dict[str, Any]:
    """
    DLQ processing task (runs every 5 minutes via Celery Beat, §6.4).

    Scans DLQ for auto-replayable messages (transient failures older
    than 10 minutes) and re-enqueues them.
    """
    config = WorkerConfig()
    log = logger.bind(task="dlq_processing")

    try:
        api_url = f"{config.pipeline_api.full_base_url}/dlq/messages"

        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            resp = client.get(
                api_url,
                params={"category": "transient", "status": "pending"},
            )

            if resp.status_code != 200:
                return {"status": "error", "reason": "dlq_fetch_failed"}

            messages = resp.json()
            if isinstance(messages, dict):
                messages = messages.get("items", messages.get("messages", []))

            replayed = 0
            for msg in messages:
                msg_id = msg.get("id")
                replay_url = (
                    f"{config.pipeline_api.full_base_url}"
                    f"/dlq/messages/{msg_id}/replay"
                )
                replay_resp = client.post(replay_url)
                if replay_resp.status_code in (200, 201):
                    replayed += 1
                    log.info("dlq_message_replayed", message_id=msg_id)

            return {
                "status": "ok",
                "total_messages": len(messages),
                "replayed": replayed,
            }

    except Exception as e:
        log.error("dlq_processing_error", error=str(e))
        return {"status": "error", "error": str(e)}


@celery_app.task(
    name="tasks.pipeline_orchestrator.run_orphan_cleanup",
    queue="default",
    soft_time_limit=300,
)
def run_orphan_cleanup() -> Dict[str, Any]:
    """Daily orphan cleanup task (§10.6). Stub for Phase 5; full implementation in Phase 8+."""
    logger.info("orphan_cleanup_started")
    return {"status": "ok", "message": "Orphan cleanup — stub (Phase 8)"}


@celery_app.task(
    name="tasks.pipeline_orchestrator.run_retention_migration",
    queue="default",
    soft_time_limit=300,
)
def run_retention_migration() -> Dict[str, Any]:
    """Daily retention tier migration (§10.3). Stub for Phase 5."""
    logger.info("retention_migration_started")
    return {"status": "ok", "message": "Retention migration — stub (Phase 8)"}


@celery_app.task(
    name="tasks.pipeline_orchestrator.run_backup_verification",
    queue="default",
    soft_time_limit=300,
)
def run_backup_verification() -> Dict[str, Any]:
    """Daily backup verification. Stub for Phase 5."""
    logger.info("backup_verification_started")
    return {"status": "ok", "message": "Backup verification — stub (Phase 10)"}


@celery_app.task(
    name="tasks.pipeline_orchestrator.collect_gpu_fleet_metrics",
    queue="default",
    soft_time_limit=15,
)
def collect_gpu_fleet_metrics() -> Dict[str, Any]:
    """Collect GPU fleet metrics every 60 seconds for monitoring."""
    config = WorkerConfig()

    try:
        with httpx.Client(
            base_url=config.gpu_scheduler.base_url,
            timeout=config.gpu_scheduler.timeout_seconds,
            headers={
                "X-Service-Token": config.pipeline_api.service_token,
            },
        ) as client:
            resp = client.get("/fleet")
            if resp.status_code == 200:
                fleet = resp.json()
                return {
                    "status": "ok",
                    "total_nodes": fleet.get("total_nodes", 0),
                    "online_nodes": fleet.get("online_nodes", 0),
                    "total_vram_mb": fleet.get("total_vram_mb", 0),
                    "used_vram_mb": fleet.get("used_vram_mb", 0),
                }
            return {"status": "error", "reason": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
