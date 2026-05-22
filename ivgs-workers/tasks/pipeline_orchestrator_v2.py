"""
IVGS v5 — Pipeline Orchestrator v2 (Complete)
=================================================

Complete event-driven pipeline orchestration per §6.4 with all 8 stages wired.

Extends Phase 5 orchestrator with:
- Stage 3: Media generation (parallel per-scene dispatch)
- Stage 4: Composition manifest generation
- Stage 5: Audio generation (TTS)
- Stage 6: Talking head rendering
- Stage 7: Prototype draft assembly
- Stage 8: Final render (segment-based)

Stage sequence (§6.1):
  1. Transcript Refinement       → auto → Stage 2
  2. Storyboard Generation       → USER GATE (review/edit)
  3. Media Generation (parallel) → auto → Stage 4
  4. Composition Manifest        → auto → Stage 5
  5. Audio Generation (TTS)      → auto → Stage 6
  6. Talking Head Rendering      → auto → Stage 7
  7. Prototype Draft Assembly    → USER GATE (review/approve)
  8. Final Render               → COMPLETE

Media Generation Routing (Table 6-1):
  image       → gpu_image queue (FluxClient)
  video_clip  → gpu_video queue (CogVideoX/Wan2.1)
  animation   → gpu_image queue (AnimateDiff) or composition queue (Remotion)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

from celery_app import IVGSBaseTask, celery_app
from config import WorkerConfig
from models.task_result import (
    PipelineJobContext,
    PipelineStage,
    StageStatus,
    STAGE_ORDER,
)
from utils.error_handler import (
    route_to_dead_letter_queue,
    save_checkpoint,
    update_job_status,
)

logger = structlog.get_logger("ivgs.orchestrator_v2")


# ---------------------------------------------------------------------------
# Stage transitions (complete map)
# ---------------------------------------------------------------------------

STAGE_TRANSITIONS: Dict[str, Optional[str]] = {
    PipelineStage.TRANSCRIPT_REFINEMENT.value: (
        PipelineStage.STORYBOARD_GENERATION.value
    ),
    # After storyboard: user gate (review/edit)
    PipelineStage.STORYBOARD_GENERATION.value: None,
    # After user approval → Stage 3 dispatched by API trigger
    # Media generation completion → Stage 4
    PipelineStage.IMAGE_GENERATION.value: (
        PipelineStage.COMPOSITION_MANIFEST.value
    ),
    PipelineStage.VIDEO_GENERATION.value: (
        PipelineStage.COMPOSITION_MANIFEST.value
    ),
    PipelineStage.ANIMATION_GENERATION.value: (
        PipelineStage.COMPOSITION_MANIFEST.value
    ),
    PipelineStage.COMPOSITION_MANIFEST.value: (
        PipelineStage.TTS_AUDIO.value
    ),
    PipelineStage.TTS_AUDIO.value: (
        PipelineStage.TALKING_HEAD_RENDER.value
    ),
    PipelineStage.TALKING_HEAD_RENDER.value: (
        PipelineStage.PROTOTYPE_DRAFT.value
    ),
    # After prototype: user gate (review/approve)
    PipelineStage.PROTOTYPE_DRAFT.value: None,
    # After user approval → Stage 8 dispatched by API trigger
    PipelineStage.FINAL_RENDER.value: None,  # Pipeline complete
}

# Complete task name mapping for all 8 stages
STAGE_TASK_MAP: Dict[str, str] = {
    PipelineStage.TRANSCRIPT_REFINEMENT.value: (
        "tasks.stage1_transcript.refine_transcript_task"
    ),
    PipelineStage.STORYBOARD_GENERATION.value: (
        "tasks.stage2_storyboard.generate_storyboard_task"
    ),
    PipelineStage.IMAGE_GENERATION.value: (
        "tasks.stage3_images.generate_scene_images"
    ),
    PipelineStage.VIDEO_GENERATION.value: (
        "tasks.video_generation_task.generate_video_clips"
    ),
    PipelineStage.ANIMATION_GENERATION.value: (
        "tasks.stage3_images.generate_scene_images"  # Animations via same Stage 3
    ),
    PipelineStage.COMPOSITION_MANIFEST.value: (
        "tasks.pipeline_orchestrator_v2.build_composition_manifest"
    ),
    PipelineStage.TTS_AUDIO.value: (
        "tasks.stage4_voiceover.synthesize_voiceover"
    ),
    PipelineStage.TALKING_HEAD_RENDER.value: (
        "tasks.talking_head_task.render_talking_head"
    ),
    PipelineStage.PROTOTYPE_DRAFT.value: (
        "tasks.prototype_draft_task.assemble_prototype_draft"
    ),
    PipelineStage.FINAL_RENDER.value: (
        "tasks.final_render_task.render_final"
    ),
}

# Queue routing per stage (Table 6-7)
STAGE_QUEUE_MAP: Dict[str, str] = {
    PipelineStage.TRANSCRIPT_REFINEMENT.value: "gpu_llm",
    PipelineStage.STORYBOARD_GENERATION.value: "gpu_llm",
    PipelineStage.IMAGE_GENERATION.value: "gpu_image",
    PipelineStage.VIDEO_GENERATION.value: "gpu_video",
    PipelineStage.ANIMATION_GENERATION.value: "gpu_image",
    PipelineStage.COMPOSITION_MANIFEST.value: "default",
    PipelineStage.TTS_AUDIO.value: "gpu_tts",
    PipelineStage.TALKING_HEAD_RENDER.value: "gpu_talking_head",
    PipelineStage.PROTOTYPE_DRAFT.value: "composition",
    PipelineStage.FINAL_RENDER.value: "composition",
}

# Media generation stages (dispatched in parallel per scene)
MEDIA_GENERATION_STAGES = {
    PipelineStage.IMAGE_GENERATION.value,
    PipelineStage.VIDEO_GENERATION.value,
    PipelineStage.ANIMATION_GENERATION.value,
}


# ---------------------------------------------------------------------------
# Pipeline dispatch (entry point)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.pipeline_orchestrator_v2.dispatch_pipeline",
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

    Determines starting stage (or resume point) and enqueues the first task.
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
    log.info("pipeline_v2_dispatch_starting")

    # Determine starting stage
    start_stage = job_context.current_stage.value
    if job_context.resume_from_stage:
        start_stage = job_context.resume_from_stage
        log.info("pipeline_resuming", resume_from=start_stage)

    update_job_status(job_id, "running")

    # Dispatch the starting stage
    task_name = STAGE_TASK_MAP.get(start_stage)
    if not task_name:
        log.error("pipeline_no_task_for_stage", stage=start_stage)
        update_job_status(
            job_id, "failed",
            error_message=f"No task registered for stage: {start_stage}",
        )
        return {"job_id": job_id, "status": "failed", "error": f"No task for {start_stage}"}

    task_input = _build_stage_input(start_stage, job_context, config)

    result = celery_app.send_task(
        task_name,
        kwargs={"task_input_dict": task_input},
        queue=STAGE_QUEUE_MAP.get(start_stage, "default"),
        priority=_get_priority(job_context.priority.value),
    )

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
# Stage completion handler (complete implementation)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.pipeline_orchestrator_v2.handle_stage_completion",
    queue="default",
    max_retries=3,
    soft_time_limit=60,
)
def handle_stage_completion(
    self: IVGSBaseTask,
    stage_output_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle completion of a pipeline stage.

    Determines the next stage and dispatches it, handles user gates,
    manages parallel media generation completion, and tracks progress.
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
        status=status,
    )

    log.info("stage_completion_received_v2")

    # Handle failure
    if status in (StageStatus.FAILED.value, "failed"):
        log.warning("stage_failed_no_advance", stage=completed_stage)
        update_job_status(
            job_id, "failed",
            error_message=f"Stage {completed_stage} failed",
        )
        return {
            "job_id": job_id,
            "action": "none",
            "reason": "stage_failed",
        }

    # Handle media generation stages (parallel completion tracking)
    if completed_stage in MEDIA_GENERATION_STAGES:
        return _handle_media_generation_completion(
            completed_stage=completed_stage,
            stage_output=stage_output_dict,
            config=config,
            log=log,
        )

    # Determine next stage
    next_stage = STAGE_TRANSITIONS.get(completed_stage)

    # User gate — pipeline pauses
    if next_stage is None:
        gate_status = _determine_gate_status(completed_stage)
        log.info(
            "pipeline_paused_at_gate",
            completed_stage=completed_stage,
            gate_status=gate_status,
        )
        update_job_status(job_id, gate_status)

        return {
            "job_id": job_id,
            "action": "user_gate",
            "completed_stage": completed_stage,
            "gate_status": gate_status,
            "message": f"Stage {completed_stage} complete. Awaiting user action.",
        }

    # Dispatch next stage
    task_name = STAGE_TASK_MAP.get(next_stage)
    if not task_name:
        log.warning("next_stage_task_not_registered", next_stage=next_stage)
        return {
            "job_id": job_id,
            "action": "pending",
            "next_stage": next_stage,
            "message": f"Task for {next_stage} not yet registered",
        }

    task_input = _build_stage_input(
        next_stage, None, config, stage_output_dict,
    )

    result = celery_app.send_task(
        task_name,
        kwargs={"task_input_dict": task_input},
        queue=STAGE_QUEUE_MAP.get(next_stage, "default"),
        priority=_get_priority(
            stage_output_dict.get("priority", "normal"),
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
# Media generation dispatch (Stage 3 — parallel per scene)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.pipeline_orchestrator_v2.dispatch_media_generation",
    queue="default",
    max_retries=2,
    soft_time_limit=60,
)
def dispatch_media_generation(
    self: IVGSBaseTask,
    dispatch_input: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Dispatch parallel media generation tasks per scene.

    Routes each scene to the appropriate queue based on media_type:
    - image       → gpu_image (FluxClient)
    - video_clip  → gpu_video (CogVideoX/Wan2.1)
    - animation   → gpu_image (AnimateDiff) or composition (Remotion)
    """
    config = WorkerConfig()

    job_id = dispatch_input.get("job_id", "")
    project_id = dispatch_input.get("project_id", "")
    scenes = dispatch_input.get("scenes", [])

    log = logger.bind(
        job_id=job_id,
        project_id=project_id,
        total_scenes=len(scenes),
    )
    log.info("media_generation_dispatch_starting")

    # Group scenes by media type
    image_scenes: List[Dict[str, Any]] = []
    video_scenes: List[Dict[str, Any]] = []
    animation_scenes: List[Dict[str, Any]] = []

    for scene in scenes:
        media_type = scene.get("media_type", "image")
        if media_type == "image":
            image_scenes.append(scene)
        elif media_type == "video_clip":
            video_scenes.append(scene)
        elif media_type == "animation":
            animation_scenes.append(scene)
        else:
            image_scenes.append(scene)  # Default to image

    dispatched: List[Dict[str, Any]] = []

    # Track total expected completions in Redis/DB
    total_media_tasks = 0

    # Dispatch image generation
    if image_scenes:
        task_input = {
            "job_id": job_id,
            "project_id": project_id,
            "project_name": dispatch_input.get("project_name", ""),
            "target_audience": dispatch_input.get("target_audience", "general"),
            "language_code": dispatch_input.get("language_code", "en-US"),
            "scenes": image_scenes,
            "enable_dedup": True,
        }
        result = celery_app.send_task(
            STAGE_TASK_MAP[PipelineStage.IMAGE_GENERATION.value],
            kwargs={"task_input_dict": task_input},
            queue="gpu_image",
        )
        dispatched.append({
            "stage": PipelineStage.IMAGE_GENERATION.value,
            "celery_task_id": result.id,
            "scene_count": len(image_scenes),
        })
        total_media_tasks += 1

    # Dispatch video generation
    if video_scenes:
        task_input = {
            "job_id": job_id,
            "project_id": project_id,
            "project_name": dispatch_input.get("project_name", ""),
            "target_audience": dispatch_input.get("target_audience", "general"),
            "language_code": dispatch_input.get("language_code", "en-US"),
            "scenes": video_scenes,
            "enable_dedup": True,
        }
        result = celery_app.send_task(
            STAGE_TASK_MAP[PipelineStage.VIDEO_GENERATION.value],
            kwargs={"task_input_dict": task_input},
            queue="gpu_video",
        )
        dispatched.append({
            "stage": PipelineStage.VIDEO_GENERATION.value,
            "celery_task_id": result.id,
            "scene_count": len(video_scenes),
        })
        total_media_tasks += 1

    # Dispatch animation generation (route to image queue)
    if animation_scenes:
        task_input = {
            "job_id": job_id,
            "project_id": project_id,
            "project_name": dispatch_input.get("project_name", ""),
            "target_audience": dispatch_input.get("target_audience", "general"),
            "language_code": dispatch_input.get("language_code", "en-US"),
            "scenes": animation_scenes,
            "enable_dedup": True,
        }
        result = celery_app.send_task(
            STAGE_TASK_MAP[PipelineStage.ANIMATION_GENERATION.value],
            kwargs={"task_input_dict": task_input},
            queue="gpu_image",
        )
        dispatched.append({
            "stage": PipelineStage.ANIMATION_GENERATION.value,
            "celery_task_id": result.id,
            "scene_count": len(animation_scenes),
        })
        total_media_tasks += 1

    # Store expected completion count for tracking
    _store_media_task_count(job_id, total_media_tasks, config)

    log.info(
        "media_generation_dispatched",
        image_scenes=len(image_scenes),
        video_scenes=len(video_scenes),
        animation_scenes=len(animation_scenes),
        total_tasks=total_media_tasks,
    )

    return {
        "job_id": job_id,
        "action": "media_generation_dispatched",
        "dispatched": dispatched,
        "total_tasks": total_media_tasks,
    }


# ---------------------------------------------------------------------------
# Composition manifest task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.pipeline_orchestrator_v2.build_composition_manifest",
    queue="default",
    max_retries=2,
    soft_time_limit=120,
)
def build_composition_manifest(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build and lock composition manifest from storyboard + generated assets.

    Stage 4 per §6.1: Runs after all media generation completes.
    """
    config = WorkerConfig()

    job_id = task_input_dict.get("job_id", "")
    project_id = task_input_dict.get("project_id", "")
    log = logger.bind(job_id=job_id, project_id=project_id)

    log.info("composition_manifest_building")
    update_job_status(
        job_id, "running",
        stage=PipelineStage.COMPOSITION_MANIFEST.value,
    )

    try:
        # Fetch storyboard scenes and their generated assets from API
        scenes_data = _fetch_project_scenes(project_id, config)
        talking_head = _fetch_talking_head_asset(project_id, config)

        from services.manifest_builder import ManifestBuilder

        builder = ManifestBuilder(
            api_base_url=config.pipeline_api.full_base_url,
            service_token=config.pipeline_api.service_token,
        )

        manifest = builder.build_manifest(
            project_id=project_id,
            language_code=task_input_dict.get("language_code", "en-US"),
            scenes=scenes_data,
            talking_head_asset=talking_head,
        )

        # Validate checksums
        asset_checksums = _fetch_asset_checksums(project_id, config)
        errors = builder.validate_manifest(manifest, asset_checksums)

        if errors:
            log.warning("manifest_validation_errors", errors=errors)
            # Non-fatal: proceed with warning
            manifest.metadata["validation_warnings"] = errors

        # Lock manifest
        manifest = builder.lock_manifest(manifest)

        # Save to database
        import asyncio
        loop = asyncio.new_event_loop()
        save_result = loop.run_until_complete(builder.save_manifest(manifest))
        loop.close()

        manifest_id = save_result.get("id", manifest.manifest_id)

        save_checkpoint(
            job_id=job_id,
            stage=PipelineStage.COMPOSITION_MANIFEST.value,
            checkpoint_data={
                "manifest_id": manifest_id,
                "scene_count": manifest.scene_count,
                "total_duration": manifest.total_duration_seconds,
            },
        )

        log.info(
            "composition_manifest_complete",
            manifest_id=manifest_id,
            scene_count=manifest.scene_count,
            duration=manifest.total_duration_seconds,
        )

        output = {
            "job_id": job_id,
            "project_id": project_id,
            "stage": PipelineStage.COMPOSITION_MANIFEST.value,
            "status": StageStatus.SUCCESS.value,
            "manifest_id": manifest_id,
            "scene_count": manifest.scene_count,
            "total_duration": manifest.total_duration_seconds,
        }

        # Dispatch stage completion
        celery_app.send_task(
            "tasks.pipeline_orchestrator_v2.handle_stage_completion",
            kwargs={"stage_output_dict": output},
            queue="default",
        )

        return output

    except Exception as e:
        log.error("composition_manifest_error", error=str(e))
        update_job_status(
            job_id, "failed",
            error_message=f"Composition manifest error: {e}",
        )
        return {
            "job_id": job_id,
            "project_id": project_id,
            "stage": PipelineStage.COMPOSITION_MANIFEST.value,
            "status": StageStatus.FAILED.value,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _handle_media_generation_completion(
    completed_stage: str,
    stage_output: Dict[str, Any],
    config: WorkerConfig,
    log: Any,
) -> Dict[str, Any]:
    """
    Handle completion of a media generation stage.

    Media generation runs in parallel (image, video, animation).
    We need all media tasks to complete before advancing to Stage 4.
    """
    job_id = stage_output.get("job_id", "")

    # Decrement remaining count
    remaining = _decrement_media_task_count(job_id, config)

    log.info(
        "media_stage_completed",
        stage=completed_stage,
        remaining_tasks=remaining,
    )

    if remaining <= 0:
        # All media generation complete → dispatch Stage 4 (Composition Manifest)
        log.info("all_media_generation_complete_advancing")

        next_stage = PipelineStage.COMPOSITION_MANIFEST.value
        task_name = STAGE_TASK_MAP[next_stage]

        task_input = _build_stage_input(
            next_stage, None, config, stage_output,
        )

        result = celery_app.send_task(
            task_name,
            kwargs={"task_input_dict": task_input},
            queue=STAGE_QUEUE_MAP.get(next_stage, "default"),
        )

        return {
            "job_id": job_id,
            "action": "dispatched",
            "next_stage": next_stage,
            "celery_task_id": result.id,
            "message": "All media generation complete",
        }

    return {
        "job_id": job_id,
        "action": "waiting",
        "completed_stage": completed_stage,
        "remaining_tasks": remaining,
        "message": f"Waiting for {remaining} more media task(s)",
    }


def _determine_gate_status(completed_stage: str) -> str:
    """Determine job status at a user gate."""
    if completed_stage == PipelineStage.STORYBOARD_GENERATION.value:
        return "storyboard_review"
    elif completed_stage == PipelineStage.PROTOTYPE_DRAFT.value:
        return "user_review"
    elif completed_stage == PipelineStage.FINAL_RENDER.value:
        return "completed"
    return "pending_review"


def _get_priority(priority: str) -> int:
    """Convert priority string to Celery priority integer."""
    return {"urgent": 9, "normal": 5, "batch": 2}.get(priority, 5)


def _build_stage_input(
    stage: str,
    job_context: Optional[PipelineJobContext],
    config: WorkerConfig,
    previous_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build task input dict for a given stage."""
    context = (
        job_context.model_dump(mode="json")
        if job_context
        else _extract_context(previous_output)
    )

    base_input = {
        "job_id": context.get("job_id", ""),
        "project_id": context.get("project_id", ""),
        "project_name": context.get("project_name", ""),
        "language_code": context.get("language_code", "en-US"),
    }

    if stage == PipelineStage.TRANSCRIPT_REFINEMENT.value:
        return {**base_input, "transcripts": []}

    elif stage == PipelineStage.STORYBOARD_GENERATION.value:
        refined = (previous_output or {}).get("refined_transcripts", [])
        return {**base_input, "refined_transcripts": refined}

    elif stage == PipelineStage.COMPOSITION_MANIFEST.value:
        return base_input

    elif stage == PipelineStage.TTS_AUDIO.value:
        return {
            **base_input,
            "scenes": _fetch_scenes_for_tts(
                base_input["project_id"], config,
            ),
        }

    elif stage == PipelineStage.TALKING_HEAD_RENDER.value:
        project_id = base_input["project_id"]
        return {
            **base_input,
            "reference_clip_asset_id": _fetch_reference_clip_id(project_id, config),
            "scene_audio_refs": _fetch_scene_audio_refs(project_id, config),
        }

    elif stage == PipelineStage.PROTOTYPE_DRAFT.value:
        project_id = base_input["project_id"]
        manifest = _fetch_latest_manifest(project_id, config)
        return {
            **base_input,
            "manifest_id": manifest.get("manifest_id", ""),
            "talking_head_asset_id": manifest.get("talking_head_asset_id"),
            "scenes": manifest.get("scenes", []),
        }

    elif stage == PipelineStage.FINAL_RENDER.value:
        project_id = base_input["project_id"]
        manifest = _fetch_latest_manifest(project_id, config)
        return {
            **base_input,
            "manifest_id": manifest.get("manifest_id", ""),
            "talking_head_asset_id": manifest.get("talking_head_asset_id"),
            "scenes": manifest.get("scenes", []),
            "render_profiles": ["1080p", "4k"],
        }

    return base_input


def _extract_context(output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract job context from a stage output dict."""
    if not output:
        return {}
    return {
        "job_id": output.get("job_id", ""),
        "project_id": output.get("project_id", ""),
        "project_name": output.get("project_name", ""),
        "language_code": output.get("language_code", "en-US"),
    }


def _update_job_celery_task_id(
    job_id: str, celery_task_id: str, config: WorkerConfig,
) -> None:
    """Update the render job with the Celery task ID."""
    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            client.patch(
                f"{config.pipeline_api.full_base_url}/jobs/{job_id}",
                json={"celery_task_id": celery_task_id},
            )
    except Exception as e:
        logger.warning("job_celery_task_id_update_failed", job_id=job_id, error=str(e))


# ---------------------------------------------------------------------------
# Redis-based media task counter
# ---------------------------------------------------------------------------

def _store_media_task_count(
    job_id: str, count: int, config: WorkerConfig,
) -> None:
    """Store expected media task count in Redis."""
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        r.set(f"ivgs:media_tasks:{job_id}", count, ex=86400)
    except Exception as e:
        logger.warning("redis_store_media_count_failed", error=str(e))


def _decrement_media_task_count(
    job_id: str, config: WorkerConfig,
) -> int:
    """Decrement and return remaining media task count."""
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        remaining = r.decr(f"ivgs:media_tasks:{job_id}")
        return max(0, remaining)
    except Exception as e:
        logger.warning("redis_decrement_media_count_failed", error=str(e))
        return 0


# ---------------------------------------------------------------------------
# API fetch helpers
# ---------------------------------------------------------------------------

def _fetch_project_scenes(
    project_id: str, config: WorkerConfig,
) -> List[Dict[str, Any]]:
    """Fetch project scenes with asset references from Pipeline API."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/scenes",
                params={"include_assets": "true"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("items", [])
    except Exception as e:
        logger.warning("fetch_scenes_failed", error=str(e))
    return []


def _fetch_talking_head_asset(
    project_id: str, config: WorkerConfig,
) -> Optional[Dict[str, Any]]:
    """Fetch talking head asset reference."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets",
                params={"asset_type": "talking_head", "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("items", [])
                return items[0] if items else None
    except Exception as e:
        logger.warning("fetch_talking_head_failed", error=str(e))
    return None


def _fetch_asset_checksums(
    project_id: str, config: WorkerConfig,
) -> Dict[str, str]:
    """Fetch all asset checksums for a project."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets",
                params={"fields": "id,content_hash"},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("items", [])
                return {
                    item["id"]: item.get("content_hash", "")
                    for item in items
                    if item.get("content_hash")
                }
    except Exception as e:
        logger.warning("fetch_checksums_failed", error=str(e))
    return {}


def _fetch_scenes_for_tts(
    project_id: str, config: WorkerConfig,
) -> List[Dict[str, Any]]:
    """Fetch scenes formatted for TTS input."""
    scenes = _fetch_project_scenes(project_id, config)
    return [
        {
            "scene_id": s.get("scene_id", s.get("id", "")),
            "scene_index": s.get("scene_index", 0),
            "narration_text": s.get("narration_text", ""),
            "duration_seconds": s.get("duration_seconds", 10.0),
            "scene_title": s.get("scene_title", ""),
            "language_code": s.get("language_code", "en-US"),
        }
        for s in scenes
    ]


def _fetch_reference_clip_id(
    project_id: str, config: WorkerConfig,
) -> str:
    """Fetch the user-uploaded reference clip asset ID."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets",
                params={"asset_type": "reference_clip", "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("items", [])
                if items:
                    return items[0].get("id", "")
    except Exception as e:
        logger.warning("fetch_reference_clip_failed", error=str(e))
    return ""


def _fetch_scene_audio_refs(
    project_id: str, config: WorkerConfig,
) -> List[Dict[str, Any]]:
    """Fetch scene audio asset references for talking head concatenation."""
    scenes = _fetch_project_scenes(project_id, config)
    return [
        {
            "scene_id": s.get("scene_id", s.get("id", "")),
            "scene_index": s.get("scene_index", 0),
            "audio_asset_id": s.get("audio_asset_id", ""),
            "duration_seconds": s.get("duration_seconds", 10.0),
        }
        for s in scenes
        if s.get("audio_asset_id")
    ]


def _fetch_latest_manifest(
    project_id: str, config: WorkerConfig,
) -> Dict[str, Any]:
    """Fetch the latest locked manifest for a project."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/manifests",
                params={"status": "locked", "limit": 1, "sort": "-created_at"},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("items", [])
                if items:
                    return items[0]
    except Exception as e:
        logger.warning("fetch_manifest_failed", error=str(e))
    return {}
