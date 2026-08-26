"""One dispatch path for every "regenerate this scene" surface (WP-45 Task 3).

Three endpoints ask for the same thing in three different words:

* ``POST /projects/{id}/scenes/{sid}/regenerate`` — the Regen button on a scene
  card (WP-43 D-3, the original finding).
* ``POST /assets/{id}/regenerate`` — the Regen button on an asset card.
* ``POST /quality-scores/{id}/reject?regenerate=true`` — a reviewer rejecting a
  flagged asset and asking for another take.

All three created a ``render_jobs`` row, returned 202, and dispatched **nothing**.
The row sat at ``pending`` forever, the UI showed a job starting, and nine such
rows accumulated on the reference project alone. A green surface over an empty
action is worse than a disabled button, because the operator has no way to learn
the difference.

The semantics are the ones ruled for WP-45:

    scene regen        = re-run that scene's media generation, consuming the
                         scene's CURRENT fields (narration, visual description,
                         media type, duration, and the five WP-43 D-2 fields).
    asset regenerate   = the same, for the scene the asset belongs to.

That is deliberately a re-run of the *scene*, not a replay of the original task
arguments: the operator pressing Regen has usually just edited the scene, and
replaying the old arguments would regenerate exactly what they were trying to
change.

Dispatch goes through ``dispatch_media_generation`` rather than straight to
``stage3_images`` / ``video_generation_task`` / ``animation_generation_task``.
That is load-bearing, not tidiness: the media tasks report completion to
``handle_stage_completion``, which decrements a media-join counter. Dispatching a
media task without arming that counter makes the report land on an unarmed join,
which returns JOIN_UNKNOWN, retries three times and lands in the DLQ (WP-06 /
P1.1). ``dispatch_media_generation`` arms the join for exactly the stages it
dispatches, so a one-scene regeneration drains correctly and flows on into a
fresh composition manifest.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene

logger = logging.getLogger(__name__)

DISPATCH_MEDIA_TASK = "tasks.pipeline_orchestrator_v2.dispatch_media_generation"
DISPATCH_PIPELINE_TASK = "tasks.pipeline_orchestrator_v2.dispatch_pipeline"
ORCHESTRATOR_QUEUE = "default"

# storyboard_scenes.media_type -> the render_jobs.job_type enum value that names
# the work. The job row is what the Jobs tab and the tracker read, so it must say
# which branch actually ran rather than defaulting everything to images.
MEDIA_TYPE_JOB_TYPE = {
    "image": "image_generation",
    "video_clip": "video_generation",
    "animation": "animation_generation",
}

# assets.asset_type -> the media_type its scene is regenerated as, when the scene
# row itself does not say. An audio asset has no media branch of its own here;
# its regeneration is a TTS re-run, which is not this path.
ASSET_TYPE_MEDIA_TYPE = {
    "image": "image",
    "video": "video_clip",
}


class RegenerationError(RuntimeError):
    """A regeneration could not be dispatched, and no job row was left behind.

    Raised rather than returned. The whole point of WP-45 Task 3 is that a
    caller must never be told "queued" by something that queued nothing, and a
    silent ``None`` return is how that happened the first time.
    """


def scene_payload(scene: StoryboardScene) -> Dict[str, Any]:
    """The scene dict the media tasks consume, from the scene's current fields."""
    payload: Dict[str, Any] = {
        "scene_id": str(scene.id),
        "scene_index": scene.scene_index,
        "narration_text": scene.narration_text,
        "visual_description": scene.visual_description,
        "media_type": scene.media_type or "image",
        "duration_seconds": scene.duration_seconds,
    }
    # WP-43 D-2 fields, now that they exist (migration 0028). Sent only when set,
    # so a scene that never had them looks exactly as it did before.
    for field in (
        "camera_angle",
        "transition_type",
        "effects",
        "timing_offset_ms",
        "generation_params",
    ):
        value = getattr(scene, field, None)
        if value is not None:
            payload[field] = value
    return payload


def project_facts(project: Optional[Project], tier: str = "prototype") -> Dict[str, Any]:
    """The IVGS-0.1 project facts every dispatch must carry."""
    facts: Dict[str, Any] = {
        "project_name": getattr(project, "name", "") or "",
        "project_description": getattr(project, "description", "") or "",
        "target_audience": getattr(project, "target_audience", "") or "general",
        "language_code": getattr(project, "language_code", "en-US") or "en-US",
        "priority": "normal",
        "tier": tier,
    }
    max_runtime = getattr(project, "max_runtime_seconds", None)
    if max_runtime is not None:
        facts["max_runtime_seconds"] = int(max_runtime)
    return facts


async def dispatch_scene_media_regeneration(
    db: AsyncSession,
    scene: StoryboardScene,
    reason: str,
    tier: str = "prototype",
) -> RenderJob:
    """Create a job row and dispatch that one scene's media generation.

    The job row is committed **before** the broker message so the message can
    carry a real ``job_id``, and the celery task id is written back afterwards.
    If the dispatch raises, the job row is marked failed with the reason rather
    than left at ``pending`` pretending to be queued.

    TWO REFUSALS RUN FIRST, AND THEY RUN BEFORE THE JOB ROW.

    WP-62 Task 6 (WP-61 D-1, RULED: extend). THE IN-FLIGHT GUARD REACHES HERE
    NOW. WP-60's six-dispatch storm -- five concurrent pipelines, six
    talking-head renders, about 3.5 hours of GPU time on project 52d52867 --
    was `video_generation` and `animation_generation` job types, and
    `trigger_pipeline` produces neither. Those six came through the scene
    regenerate route. WP-61 guarded the trigger endpoint, which is what its
    ruling named, and recorded in D-1 that the route the measured incident
    ACTUALLY USED was still open. This is that route, and the two others that
    reach the same dispatch: `POST /assets/{id}/regenerate` and
    `POST /quality-scores/{id}/reject?regenerate=true`. Guarding the choke
    point rather than the three callers means a fourth caller added later
    inherits the guard instead of reintroducing the hole.

    WP-62 Task 2(c). THE STORYBOARD GATE REACHES HERE TOO. A regeneration IS
    media generation -- it dispatches `dispatch_media_generation` -- so a
    project whose storyboard is not currently approved cannot start GPU work
    through it. Without this the gate would have had a side door of exactly
    the shape the gate exists to close.

    Both refuse BEFORE the job row is inserted. WP-45's finding was that a
    surface must never be told "queued" by something that queued nothing; the
    mirror of it is that a refused request must not leave a `pending` row
    behind to be counted, retried or resumed.
    """
    from app.services.gate_service import GateService
    from app.services.project_service import PipelineAlreadyRunningError, active_job

    await GateService(db).require_storyboard_approval(scene.project_id)

    running = await active_job(db, scene.project_id)
    if running is not None:
        raise PipelineAlreadyRunningError(
            f"Project {scene.project_id} already has a {running.status} "
            f"{running.job_type} run (job {running.id}). Regenerating a scene "
            "while a run is in flight dispatches media work into a pipeline "
            "that is already producing it, and the join counter that pairs "
            "them is armed once. Wait for it to finish, or cancel it.",
            job_id=running.id,
            job_type=running.job_type,
            status=running.status,
        )

    project = await db.scalar(select(Project).where(Project.id == scene.project_id))

    media_type = scene.media_type or "image"
    job_type = MEDIA_TYPE_JOB_TYPE.get(media_type, "image_generation")

    job = RenderJob(
        project_id=scene.project_id,
        job_type=job_type,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    dispatch_input: Dict[str, Any] = {
        "job_id": str(job.id),
        "project_id": str(scene.project_id),
        **project_facts(project, tier=tier),
        "scenes": [scene_payload(scene)],
    }

    from app.services.celery_producer import celery_app as pipeline_celery

    try:
        dispatch = pipeline_celery.send_task(
            DISPATCH_MEDIA_TASK,
            kwargs={"dispatch_input": dispatch_input},
            queue=ORCHESTRATOR_QUEUE,
        )
    except Exception as exc:
        job.status = "failed"
        job.error_message = f"Regeneration dispatch failed: {exc}"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.error(
            "Scene regeneration dispatch FAILED: scene=%s job=%s error=%s",
            scene.id, job.id, exc,
        )
        raise RegenerationError(
            f"Could not dispatch regeneration for scene {scene.id}: {exc}"
        ) from exc

    job.celery_task_id = dispatch.id
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)

    logger.info(
        "Scene regeneration dispatched: scene=%s media_type=%s job=%s "
        "celery_task=%s reason=%s",
        scene.id, media_type, job.id, dispatch.id, reason,
    )
    return job


async def scene_for_asset(
    db: AsyncSession, asset_scene_id: Optional[UUID], asset_id: UUID,
) -> StoryboardScene:
    """The scene an asset belongs to, or a RegenerationError naming why not."""
    if asset_scene_id is None:
        raise RegenerationError(
            f"Asset {asset_id} is not linked to a storyboard scene, so there is "
            "no scene to regenerate. Project-level assets (reference clips, "
            "transcripts, final renders) are not regenerated this way."
        )
    scene = await db.scalar(
        select(StoryboardScene).where(StoryboardScene.id == asset_scene_id)
    )
    if scene is None:
        raise RegenerationError(
            f"Asset {asset_id} references scene {asset_scene_id}, which no "
            "longer exists."
        )
    return scene
