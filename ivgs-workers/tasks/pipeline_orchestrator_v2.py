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

from typing import Any, Dict, List, Optional

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
        "tasks.stage3_images.generate_scene_images_task"
    ),
    PipelineStage.VIDEO_GENERATION.value: (
        "tasks.video_generation_task.generate_video_clips"
    ),
    PipelineStage.ANIMATION_GENERATION.value: (
        "tasks.stage3_images.generate_scene_images_task"  # Animations via same Stage 3
    ),
    PipelineStage.COMPOSITION_MANIFEST.value: (
        "tasks.stage4_manifest.build_composition_manifest"
    ),
    PipelineStage.TTS_AUDIO.value: (
        "tasks.stage4_voiceover.generate_voiceover_task"
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
    start_stage = job_context.current_stage or PipelineStage.TRANSCRIPT_REFINEMENT.value
    if job_context.resume_from_stage:
        start_stage = job_context.resume_from_stage
        log.info("pipeline_resuming", resume_from=start_stage)

    update_job_status(job_id, "running")

    # IVGS-0.1: stash the full context before anything is dispatched. Every
    # later stage reads it back; _extract_context is no longer a source of
    # project facts.
    _store_job_context(job_id, job_context.model_dump(mode="json"), config)

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
        priority=_get_priority(job_context.priority),
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

    # Handle failure, but NOT for media stages. A failed media scene must still
    # flow through the media-join below so it decrements the counter and the
    # pipeline drains to Stage 4 with whatever rendered (partial-advance), instead
    # of fail-fasting the whole job and stranding it in MEDIA_GENERATION.
    if status in (StageStatus.FAILED.value, "failed") and completed_stage not in MEDIA_GENERATION_STAGES:
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
        try:
            return _handle_media_generation_completion(
                completed_stage=completed_stage,
                stage_output=stage_output_dict,
                config=config,
                log=log,
            )
        except MediaJoinUnknownError as exc:
            # WP-06 / P1.1. The join could not tell us how many media tasks are
            # outstanding. Retry rather than guess; IVGSBaseTask sets no
            # autoretry_for, so without this the task would simply fail and the
            # report would be lost. After max_retries it goes to the DLQ, which
            # is the loud outcome - the quiet one was dispatching Stage 4 over
            # incomplete footage.
            log.warning(
                "media_join_unknown_retrying",
                stage=completed_stage,
                retries=self.request.retries,
                max_retries=self.max_retries,
            )
            raise self.retry(exc=exc, countdown=10) from exc

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
        # job_status is the execution-lifecycle enum (pending/running/success/failed);
        # the review/gate state belongs to projects.state per spec 4.3, not job_status.
        # The stage's job succeeded and the pipeline pauses here, so persist success and
        # keep gate_status in the log/return below for observability.
        update_job_status(job_id, "success")

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

    # IVGS-0.1: this is the second entry point into the pipeline (storyboard
    # approval resumes at media generation), so it must seed the job context
    # exactly as dispatch_pipeline does. Unknown keys in dispatch_input are
    # dropped by the model; absent ones fall back to the model's defaults.
    _resume_context = PipelineJobContext(
        **{
            k: v
            for k, v in dispatch_input.items()
            if k in PipelineJobContext.model_fields and k != "current_stage"
        },
        current_stage=PipelineStage.IMAGE_GENERATION.value,
    )
    _store_job_context(job_id, _resume_context.model_dump(mode="json"), config)

    # Stash the minimal context the media-join watchdog needs to rebuild the
    # composition-manifest input if a crashed media task strands this join.
    _store_media_join_context(
        job_id,
        {
            "job_id": job_id,
            "project_id": project_id,
            "project_name": dispatch_input.get("project_name", ""),
            "language_code": dispatch_input.get("language_code", "en-US"),
        },
        config,
    )

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

    # IVGS-0.1: description and runtime budget travel with every media task, so
    # Stage 3's prompt writer sees the real project rather than empty strings.
    _media_facts = {
        "project_name": _resume_context.project_name,
        "project_description": _resume_context.project_description,
        "target_audience": _resume_context.target_audience or "general",
        "language_code": _resume_context.language_code,
        "max_runtime_seconds": _resume_context.max_runtime_seconds,
        "tier": _resume_context.tier,
    }

    # Dispatch image generation
    if image_scenes:
        task_input = {
            "job_id": job_id,
            "project_id": project_id,
            **_media_facts,
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
            **_media_facts,
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
            **_media_facts,
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

    # Arm the join. Raises MediaJoinStoreError if the counter could not be
    # written - deliberately NOT swallowed (WP-06 / P1.1). An unarmed counter
    # makes DECR return -1 on a missing key, which the old caller read as
    # "all media reported" and acted on. Letting this propagate retries the
    # dispatch (max_retries=2) instead of starting a join nothing can report to.
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

    All media tasks must report (success OR failure) before advancing to Stage 4.
    A failed scene is drained: it decrements the join counter and is recorded, so
    one bad scene cannot strand the pipeline. The composition manifest then
    proceeds with whatever rendered (partial-advance).
    """
    job_id = stage_output.get("job_id", "")
    status = stage_output.get("status", "")
    failed = status in (StageStatus.FAILED.value, "failed")

    # Always report: every media task reporting in moves the join forward,
    # success or failure (partial-advance, commit 35d9226). The guard is inside
    # the report, so a duplicate delivery of THIS stage's completion decrements
    # exactly once.
    outcome, remaining = _decrement_media_task_count(job_id, completed_stage, config)

    if outcome == JOIN_DUPLICATE:
        # The callback fires before the ack (stage3_images.py:757,
        # video_generation_task.py:576) and acks_late + task_reject_on_worker_lost
        # requeue the media task if the worker dies in that window. The re-run
        # sends a second completion for the same (job_id, stage); it must not
        # decrement again.
        log.warning(
            "media_stage_duplicate_report_ignored",
            stage=completed_stage,
            note="already counted; join not advanced",
        )
        return {
            "job_id": job_id,
            "action": "duplicate_ignored",
            "completed_stage": completed_stage,
            "message": "This media stage already reported; join unchanged",
        }

    if outcome == JOIN_UNKNOWN:
        # NOT a value the caller may read as completion. Raising lets
        # handle_stage_completion retry (bind=True, max_retries=3). If the
        # retries are exhausted the task goes to the DLQ - loud - rather than
        # dispatching Stage 4 over footage that may still be rendering.
        log.error(
            "media_join_state_unknown",
            stage=completed_stage,
            note="join state could not be established; retrying, not advancing",
        )
        raise MediaJoinUnknownError(
            f"media-join state for job {job_id} could not be established while "
            f"reporting stage {completed_stage}. Not advancing to Stage 4 - "
            "'unknown' is not 'complete'."
        )

    if failed:
        failures = _record_media_failure(job_id, config)
        log.warning(
            "media_stage_failed_continuing",
            stage=completed_stage,
            remaining_tasks=remaining,
            failures_so_far=failures,
        )
    else:
        log.info(
            "media_stage_completed",
            stage=completed_stage,
            remaining_tasks=remaining,
        )

    if remaining <= 0:
        # All media generation complete -> dispatch Stage 4 (Composition Manifest)
        failed_count = _get_media_failure_count(job_id, config)
        if failed_count > 0:
            log.warning("all_media_reported_advancing_with_failures", failed_count=failed_count)
        else:
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
            "failed_count": failed_count,
            "message": "All media generation reported",
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
    # IVGS-0.1: precedence is (1) the context handed in, (2) the context stored
    # at dispatch, (3) — only if both are missing — the four keys that survive
    # in the previous stage's output. (3) is a degraded mode and says so.
    if job_context is not None:
        context = job_context.model_dump(mode="json")
    else:
        stored = _get_job_context(
            (previous_output or {}).get("job_id", ""), config,
        )
        if stored is not None:
            context = stored
        else:
            context = _extract_context(previous_output)
            logger.error(
                "job_context_store_miss",
                stage=stage,
                job_id=context.get("job_id", ""),
                detail=(
                    "no stored job context; falling back to the previous "
                    "stage output. project_description, max_runtime_seconds "
                    "and tier are LOST for this stage."
                ),
            )

    base_input = {
        "job_context": context,
        "job_id": context.get("job_id", ""),
        "project_id": context.get("project_id", ""),
        "project_name": context.get("project_name", ""),
        "language_code": context.get("language_code", "en-US"),
        # IVGS-0.1: stages whose input model is a flat dict (3, 5, video) read
        # these off the top level, not out of job_context. Without them the
        # stage falls back to its own field defaults and the user's project
        # facts never arrive.
        "project_description": context.get("project_description", ""),
        "target_audience": context.get("target_audience", "") or "general",
        "max_runtime_seconds": context.get("max_runtime_seconds", 600),
        # IVGS-0.3: the flat-input stages (3, 5, 6) read tier off the top level.
        # Without it every get_binding call resolved prototype regardless of
        # what the run asked for.
        "tier": context.get("tier", "prototype"),
    }

    if stage == PipelineStage.TRANSCRIPT_REFINEMENT.value:
        return {**base_input, "transcripts": _fetch_transcripts(base_input["project_id"], config)}

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
        manifest = _fetch_latest_manifest(base_input["job_id"], config)
        _th = _fetch_talking_head_asset(project_id, config)
        return {
            **base_input,
            "manifest_id": manifest.get("id", ""),
            "talking_head_asset_id": (_th.get("id") if _th else None),
            "scenes": _build_manifest_scenes(project_id, manifest, config),
            "enable_lower_thirds": False,
            "enable_captions": False,
            "enable_talking_head": True,
        }

    elif stage == PipelineStage.FINAL_RENDER.value:
        project_id = base_input["project_id"]
        manifest = _fetch_latest_manifest(base_input["job_id"], config)
        _th = _fetch_talking_head_asset(project_id, config)
        return {
            **base_input,
            "manifest_id": manifest.get("id", ""),
            "talking_head_asset_id": (_th.get("id") if _th else None),
            "scenes": _build_manifest_scenes(project_id, manifest, config),
            "enable_talking_head": True,
            "render_profiles": ["1080p", "4k"],
        }

    return base_input


def _extract_context(output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Last-resort context salvage from a stage output dict.

    IVGS-0.1: this is NOT a source of project facts. A stage output carries
    four keys; project_description, max_runtime_seconds and tier are not among
    them. Only _build_stage_input calls this, and only after the stored job
    context has been shown to be missing — which it logs as an error.
    """
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

# TTL on every per-job media-join key, written once at dispatch. The watchdog
# derives a counter's age from it (age = MEDIA_JOIN_TTL_SECONDS - ttl), so this
# value and the watchdog deadline are read together.
MEDIA_JOIN_TTL_SECONDS = 86400

# Default media-join watchdog deadline. A join counter still > 0 and older than
# this is treated as stranded (a media task whose worker crashed and never
# reported). MUST stay above the longest media task hard time_limit
# (video generate_video_clips = 3900s) plus dispatch/queue slack. Age is
# measured from dispatch and video serializes on the single gpu_video worker,
# so for concurrent projects raise IVGS_MEDIA_JOIN_TIMEOUT_SECONDS to cover the
# queue depth (~video hard limit * concurrent projects + buffer). Default ~2h.
MEDIA_JOIN_DEFAULT_TIMEOUT_SECONDS = 7200


# IVGS-0.1: the job context is the single source of project facts for every
# stage of a job. It is written once at dispatch and read back by
# _build_stage_input for every subsequent stage, because handle_stage_completion
# only ever sees the previous stage's output dict. TTL matches the media-join
# TTL: a job that outlives it has bigger problems than a stale context.
JOB_CONTEXT_TTL_SECONDS = MEDIA_JOIN_TTL_SECONDS


def _store_job_context(
    job_id: str, context: Dict[str, Any], config: WorkerConfig,
) -> None:
    """Persist the job context for the life of the job.

    Deliberately NOT best-effort. ``config.redis_url`` IS the Celery broker
    (config.py:293-295), so a Redis that cannot take this write cannot take the
    dispatch either — failing here fails the dispatch loudly instead of letting
    the pipeline run on a context rebuilt from four keys.
    """
    import json
    import redis

    r = redis.Redis.from_url(config.redis_url)
    r.set(
        f"ivgs:job_context:{job_id}",
        json.dumps(context),
        ex=JOB_CONTEXT_TTL_SECONDS,
    )


def _get_job_context(
    job_id: str, config: WorkerConfig,
) -> Optional[Dict[str, Any]]:
    """Return the stored job context for ``job_id`` (None if absent)."""
    if not job_id:
        return None
    try:
        import json
        import redis
        r = redis.Redis.from_url(config.redis_url)
        val = r.get(f"ivgs:job_context:{job_id}")
        return json.loads(val) if val is not None else None
    except Exception as e:
        logger.error("job_context_read_failed", job_id=job_id, error=str(e))
        return None


class MediaJoinStoreError(RuntimeError):
    """The media-join counter could not be armed.

    Ledger P1.1 / WP-06. This used to be logged and swallowed, returning None
    either way. The counter key then did not exist, `DECR` on a missing key
    returns -1, `max(0, -1)` is 0, and the FIRST media stage to report collapsed
    the join and dispatched Stage 4 over a third of the footage. Raising lets
    dispatch_media_generation retry instead of arming a join that was never armed.
    """


class MediaJoinUnknownError(RuntimeError):
    """The join's remaining count could not be established.

    Ledger P1.1 / WP-06. Deliberately NOT a value the caller can read as
    completion. Raised so handle_stage_completion retries; a transient Redis
    error must never advance the pipeline on incomplete footage.
    """


# Outcomes of one join report. Kept as an explicit tri-state rather than an int,
# because the whole defect this package closes was an int that meant three
# different things - "none left", "clamped negative", and "I have no idea".
JOIN_DECREMENTED = "decremented"
JOIN_DUPLICATE = "duplicate"
JOIN_UNKNOWN = "unknown"


# Guard + decrement in ONE server-side step.
#
# The two-step version (SETNX, then DECR, then delete the guard if the DECR
# failed) has a hole: if the undo also fails, the guard is stuck set, the task's
# retry looks like a duplicate, and the join stalls forever. Atomic means a Redis
# failure leaves NOTHING done, so the retry is clean.
#
# KEYS[1] = ivgs:media_tasks:{job_id}          the join counter
# KEYS[2] = ivgs:media_join_seen:{job_id}:{stage}   the per-report guard
# ARGV[1] = guard TTL in seconds
_MEDIA_JOIN_REPORT_LUA = """
if redis.call('SETNX', KEYS[2], '1') == 0 then
    return {1, 0}
end
redis.call('EXPIRE', KEYS[2], ARGV[1])
if redis.call('EXISTS', KEYS[1]) == 0 then
    return {2, 0}
end
return {0, redis.call('DECR', KEYS[1])}
"""


def _media_join_seen_key(job_id: str, stage: str) -> str:
    """Idempotency key for one media stage's completion report.

    NOT (job_id, scene_id). The WP-06 brief says scene_id, but the join does not
    count scenes: dispatch_media_generation increments total_media_tasks once per
    media STAGE dispatched (image / video / animation, lines 471, 491, 512), so
    the counter's maximum is 3. Each stage sends exactly one whole-stage
    completion and carries no scene_id. (job_id, stage) is the real granularity.
    """
    return f"ivgs:media_join_seen:{job_id}:{stage}"


def _store_media_task_count(
    job_id: str, count: int, config: WorkerConfig,
) -> None:
    """Arm the media-join counter. Raises MediaJoinStoreError if it cannot.

    Also clears the per-stage guards, so a re-dispatch of the same job re-arms a
    join that can actually be reported against.
    """
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        r.set(f"ivgs:media_tasks:{job_id}", count, ex=MEDIA_JOIN_TTL_SECONDS)
        r.delete(f"ivgs:media_failures:{job_id}")
        for stage in MEDIA_GENERATION_STAGES:
            r.delete(_media_join_seen_key(job_id, stage))
    except Exception as e:
        logger.error(
            "redis_store_media_count_failed",
            job_id=job_id,
            count=count,
            error=str(e),
        )
        raise MediaJoinStoreError(
            f"could not arm the media-join counter for job {job_id} "
            f"(expected {count} media task(s)): {e}. Not advancing - an unarmed "
            "counter reads as complete on the first stage to report."
        ) from e


def _decrement_media_task_count(
    job_id: str, stage: str, config: WorkerConfig,
) -> tuple:
    """Report one media stage against the join. Returns (outcome, remaining).

    ``outcome`` is one of JOIN_DECREMENTED / JOIN_DUPLICATE / JOIN_UNKNOWN.
    ``remaining`` is meaningful only for JOIN_DECREMENTED.

    Never returns a bare int. The pre-WP-06 signature returned ``max(0, remaining)``
    and returned 0 from its exception handler, so "Redis is down" and "all media
    reported" were the same value to the caller.
    """
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        result = r.eval(
            _MEDIA_JOIN_REPORT_LUA,
            2,
            f"ivgs:media_tasks:{job_id}",
            _media_join_seen_key(job_id, stage),
            MEDIA_JOIN_TTL_SECONDS,
        )
    except Exception as e:
        logger.error(
            "redis_decrement_media_count_failed",
            job_id=job_id,
            stage=stage,
            error=str(e),
            outcome=JOIN_UNKNOWN,
        )
        return (JOIN_UNKNOWN, 0)

    code = int(result[0])
    value = int(result[1])
    if code == 1:
        return (JOIN_DUPLICATE, 0)
    if code == 2:
        # Counter key absent: never armed, TTL expired, or the watchdog claimed
        # the job and deleted it. All three are "unknown", none is "complete".
        logger.error(
            "media_join_counter_missing",
            job_id=job_id,
            stage=stage,
            outcome=JOIN_UNKNOWN,
            note="counter absent - never armed, expired, or watchdog-claimed",
        )
        return (JOIN_UNKNOWN, 0)
    return (JOIN_DECREMENTED, max(0, value))


def _record_media_failure(job_id: str, config: WorkerConfig) -> int:
    """Increment and return the media-failure count for this job."""
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        failures = r.incr(f"ivgs:media_failures:{job_id}")
        r.expire(f"ivgs:media_failures:{job_id}", MEDIA_JOIN_TTL_SECONDS)
        return int(failures)
    except Exception as e:
        # Same "unknown != zero" shape as the counter, far smaller blast radius:
        # this only makes failed_count under-report, it does not advance the
        # pipeline. Not raised, because stranding a job over a cosmetic counter
        # would be a worse trade. Logged at error with unknown=True so the
        # partial-advance line below is not mistaken for a clean run. WP-06 F5.
        logger.error(
            "redis_record_media_failure_failed",
            job_id=job_id,
            error=str(e),
            unknown=True,
        )
        return 0


def _get_media_failure_count(job_id: str, config: WorkerConfig) -> int:
    """Return the media-failure count for this job (0 if none/unavailable)."""
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        val = r.get(f"ivgs:media_failures:{job_id}")
        return int(val) if val is not None else 0
    except Exception as e:
        # See _record_media_failure: the 0 here means "could not read", not
        # "no failures". Reported as unknown=True so it is legible in the log.
        # WP-06 F5.
        logger.error(
            "redis_get_media_failure_failed",
            job_id=job_id,
            error=str(e),
            unknown=True,
        )
        return 0


def _store_media_join_context(
    job_id: str, ctx: Dict[str, Any], config: WorkerConfig,
) -> None:
    """Stash minimal job context so the watchdog can advance a stranded join."""
    try:
        import json
        import redis
        r = redis.Redis.from_url(config.redis_url)
        r.set(
            f"ivgs:media_join_ctx:{job_id}",
            json.dumps(ctx),
            ex=MEDIA_JOIN_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning("redis_store_media_ctx_failed", error=str(e))


def _get_media_join_context(
    job_id: str, config: WorkerConfig,
) -> Optional[Dict[str, Any]]:
    """Return the stashed media-join context for a job (None if absent)."""
    try:
        import json
        import redis
        r = redis.Redis.from_url(config.redis_url)
        val = r.get(f"ivgs:media_join_ctx:{job_id}")
        return json.loads(val) if val is not None else None
    except Exception as e:
        logger.warning("redis_get_media_ctx_failed", error=str(e))
        return None


def _cleanup_media_join_keys(job_id: str, config: WorkerConfig) -> None:
    """Delete every per-job media-join key (counter, failures, context)."""
    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
        r.delete(
            f"ivgs:media_tasks:{job_id}",
            f"ivgs:media_failures:{job_id}",
            f"ivgs:media_join_ctx:{job_id}",
        )
    except Exception as e:
        logger.warning("redis_cleanup_media_join_failed", error=str(e))


@celery_app.task(
    name="tasks.pipeline_orchestrator_v2.media_join_watchdog",
    queue="default",
    soft_time_limit=180,
)
def media_join_watchdog() -> Dict[str, Any]:
    """
    Recover media-generation joins stranded by a crashed worker.

    Fix #2 drains any media task that reports failure. A task whose worker
    hard-crashes never calls handle_stage_completion, so its join counter never
    decrements and the project hangs in MEDIA_GENERATION. This periodic sweep
    finds any counter still > 0 that is older than the deadline, atomically
    claims it, counts the vanished task(s) toward failed_count, and advances to
    the composition manifest (partial-advance) just like the reported-failure
    path. Counters at <= 0 (joins that completed normally) are skipped.
    """
    import os

    config = WorkerConfig()
    log = logger.bind(task="media_join_watchdog")

    timeout_s = int(
        os.getenv(
            "IVGS_MEDIA_JOIN_TIMEOUT_SECONDS",
            str(MEDIA_JOIN_DEFAULT_TIMEOUT_SECONDS),
        )
    )
    # A counter's TTL counts down from MEDIA_JOIN_TTL_SECONDS; a ttl below this
    # threshold means the counter is older than the deadline.
    min_ttl = MEDIA_JOIN_TTL_SECONDS - timeout_s

    swept = 0
    advanced = 0
    failed = 0
    skipped_recent = 0

    try:
        import redis
        r = redis.Redis.from_url(config.redis_url)
    except Exception as e:
        log.warning("media_join_watchdog_redis_unavailable", error=str(e))
        return {"status": "error", "reason": "redis_unavailable"}

    for raw_key in r.scan_iter(match="ivgs:media_tasks:*", count=100):
        swept += 1
        key = raw_key.decode() if isinstance(raw_key, (bytes, bytearray)) else raw_key
        job_id = key.split("ivgs:media_tasks:", 1)[-1]

        try:
            val = r.get(key)
            ttl = r.ttl(key)
        except Exception as e:
            log.warning("media_join_watchdog_read_failed", job_id=job_id, error=str(e))
            continue

        remaining = int(val) if val is not None else 0
        if remaining <= 0:
            continue
        if ttl is None or ttl < 0 or ttl >= min_ttl:
            skipped_recent += 1
            continue

        # Atomically claim: only the run that reads a > 0 value here owns the job.
        pipe = r.pipeline()
        pipe.get(key)
        pipe.delete(key)
        claimed_val, _ = pipe.execute()
        claimed = int(claimed_val) if claimed_val is not None else 0
        if claimed <= 0:
            continue

        existing_failures = _get_media_failure_count(job_id, config)
        total_failed = existing_failures + claimed
        ctx = _get_media_join_context(job_id, config)

        log.warning(
            "media_join_watchdog_stranded_job",
            job_id=job_id,
            vanished_tasks=claimed,
            recorded_failures=existing_failures,
            total_failed=total_failed,
            timeout_seconds=timeout_s,
            have_context=bool(ctx),
        )

        if not ctx:
            try:
                update_job_status(
                    job_id, "failed",
                    error_message=(
                        "media-generation join stranded (worker crash); no "
                        "dispatch context available to advance"
                    ),
                )
            except Exception as e:
                log.warning(
                    "media_join_watchdog_fail_update_error",
                    job_id=job_id, error=str(e),
                )
            failed += 1
            _cleanup_media_join_keys(job_id, config)
            continue

        try:
            next_stage = PipelineStage.COMPOSITION_MANIFEST.value
            task_name = STAGE_TASK_MAP[next_stage]
            task_input = _build_stage_input(next_stage, None, config, ctx)
            result = celery_app.send_task(
                task_name,
                kwargs={"task_input_dict": task_input},
                queue=STAGE_QUEUE_MAP.get(next_stage, "default"),
            )
            advanced += 1
            log.warning(
                "media_join_watchdog_advanced_with_failures",
                job_id=job_id,
                next_stage=next_stage,
                celery_task_id=result.id,
                failed_count=total_failed,
            )
        except Exception as e:
            log.error("media_join_watchdog_advance_failed", job_id=job_id, error=str(e))
            try:
                update_job_status(
                    job_id, "failed",
                    error_message=f"media-join watchdog advance failed: {e}",
                )
            except Exception:
                pass
            failed += 1
        finally:
            _cleanup_media_join_keys(job_id, config)

    return {
        "status": "ok",
        "swept": swept,
        "advanced": advanced,
        "failed": failed,
        "skipped_recent": skipped_recent,
    }


# ---------------------------------------------------------------------------
# API fetch helpers
# ---------------------------------------------------------------------------

def _fetch_transcripts(
    project_id: str, config: WorkerConfig,
) -> List[Dict[str, Any]]:
    """Fetch raw transcripts for a project from the Pipeline API.

    On upload the extracted source text is stored in Transcript.refined_text
    (dual-purpose: raw until the refinement stage overwrites it), so it maps to
    the worker TranscriptRecord.original_text here.
    """
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/transcripts",
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                return [
                    {
                        "id": str(t.get("id", "")),
                        "project_id": str(t.get("project_id", "")),
                        "sequence_order": t.get("sequence_order", 0),
                        "original_text": t.get("refined_text") or "",
                        "language_code": t.get("language_code") or "en-US",
                    }
                    for t in items
                ]
    except Exception as e:
        logger.warning("fetch_transcripts_failed", error=str(e))
    return []


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
                return data if isinstance(data, list) else data.get("data", [])
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
                items = data if isinstance(data, list) else data.get("data", [])
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
                items = data if isinstance(data, list) else data.get("data", [])
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
                items = data if isinstance(data, list) else data.get("data", [])
                if items:
                    return items[0].get("id", "")
    except Exception as e:
        logger.warning("fetch_reference_clip_failed", error=str(e))
    return ""


def _fetch_scene_audio_refs(
    project_id: str, config: WorkerConfig,
) -> List[Dict[str, Any]]:
    """Fetch per-scene audio asset references for talking-head concatenation.

    Mirrors _build_manifest_scenes' audio binding: the composition manifest is
    locked before TTS, so per-scene audio lives only in the assets table keyed by
    scene_id (not on the scene row, and not in the manifest timeline). Re-runs can
    leave multiple audio rows per scene; keep the latest per scene (by created_at)
    and emit one ref per scene in scene_index order.
    """
    scenes = _fetch_project_scenes(project_id, config)
    audio_by_scene: Dict[str, Dict[str, Any]] = {}
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets",
                params={"asset_type": "audio", "per_page": 100},
            )
        audios = (resp.json() or {}).get("data", []) if resp.status_code == 200 else []
        audios.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        for a in audios:
            sid = a.get("scene_id")
            if sid and sid not in audio_by_scene:
                audio_by_scene[sid] = a
    except Exception as e:
        logger.warning("fetch_scene_audio_failed", error=str(e))
    refs: List[Dict[str, Any]] = []
    for s in scenes:
        scene_id = s.get("id") or s.get("scene_id", "")
        au = audio_by_scene.get(scene_id)
        if not au or not au.get("id"):
            continue
        refs.append({
            "scene_id": scene_id,
            "scene_index": s.get("scene_index", 0),
            "audio_asset_id": au["id"],
            "duration_seconds": (
                float(au.get("duration_seconds") or 0.0)
                or float(s.get("duration_seconds") or 10.0)
            ),
        })
    refs.sort(key=lambda r: r["scene_index"])
    return refs


def _fetch_latest_manifest(
    job_id: str, config: WorkerConfig,
) -> Dict[str, Any]:
    """Fetch the locked composition manifest for a job (GET /jobs/{job_id}/manifest)."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/jobs/{job_id}/manifest",
            )
            if resp.status_code == 200:
                return resp.json() or {}
            logger.warning(
                "fetch_manifest_non_200", status=resp.status_code, job_id=job_id,
            )
    except Exception as e:
        logger.warning("fetch_manifest_failed", error=str(e))
    return {}


def _build_manifest_scenes(
    project_id: str, manifest: Dict[str, Any], config: WorkerConfig,
) -> List[Dict[str, Any]]:
    """Build Stage-7/8 ManifestScene dicts from a locked manifest. Backgrounds come
    from the manifest timeline; per-scene audio is bound from the scene-linked
    Stage-5 assets (the manifest is locked before audio exists)."""
    timeline = manifest.get("timeline_json") or {}
    raw_scenes = timeline.get("scenes") or []

    meta_by_index: Dict[int, Dict[str, Any]] = {}
    for s in _fetch_project_scenes(project_id, config):
        idx = s.get("scene_index")
        if idx is not None:
            meta_by_index[idx] = s

    audio_by_scene: Dict[str, Dict[str, Any]] = {}
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets",
                params={"asset_type": "audio", "per_page": 100},
            )
        audios = (resp.json() or {}).get("data", []) if resp.status_code == 200 else []
        audios.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        for a in audios:
            sid = a.get("scene_id")
            if sid and sid not in audio_by_scene:
                audio_by_scene[sid] = a
    except Exception as e:
        logger.warning("fetch_scene_audio_failed", error=str(e))

    scenes: List[Dict[str, Any]] = []
    for rs in raw_scenes:
        idx = rs.get("scene_index", 0)
        meta = meta_by_index.get(idx, {})
        scene_id = meta.get("id") or f"scene-{idx}"
        media_type = meta.get("media_type") or "image"
        dur = ((rs.get("end_time_ms", 0) - rs.get("start_time_ms", 0)) / 1000.0) or float(
            meta.get("duration_seconds") or 0.0
        ) or 10.0

        background_asset = None
        for layer in (rs.get("layers") or []):
            if layer.get("layer_type") == "background" and layer.get("asset_id"):
                background_asset = {
                    "asset_id": layer["asset_id"],
                    "asset_type": media_type,
                    "seaweedfs_path": layer.get("seaweedfs_fid", "") or "",
                    "content_hash": layer.get("checksum", "") or "",
                    "duration_seconds": dur,
                }
                break

        audio_asset = None
        au = audio_by_scene.get(scene_id)
        audio_dur = float(au.get("duration_seconds") or 0.0) if au else 0.0
        if au and au.get("id"):
            audio_asset = {
                "asset_id": au["id"],
                "asset_type": "audio",
                "seaweedfs_path": au.get("seaweedfs_path", "") or "",
                "content_hash": au.get("content_hash", "") or "",
                "duration_seconds": float(au.get("duration_seconds") or 0.0),
            }

        scenes.append({
            "scene_id": scene_id,
            "scene_index": idx,
            "scene_title": "",
            "narration_text": meta.get("narration_text", "") or "",
            "duration_seconds": (audio_dur or dur),
            "media_type": media_type,
            "background_asset": background_asset,
            "audio_asset": audio_asset,
        })

    scenes.sort(key=lambda s: s["scene_index"])
    return scenes
