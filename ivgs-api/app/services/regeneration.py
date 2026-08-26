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
    # WP-64 Task 6(c). The storyboard gate's `regenerate` decision dispatches
    # `dispatch_pipeline` with `resume_from_stage=storyboard_generation` through
    # THIS builder, so a re-run must see the outcomes the first run saw.
    # Omitted when absent rather than sent empty.
    outcomes = (getattr(project, "learning_outcomes", None) or "").strip()
    if outcomes:
        facts["learning_outcomes"] = outcomes
    return facts


async def dispatch_scene_media_regeneration(
    db: AsyncSession,
    scene: StoryboardScene,
    reason: str,
    tier: str = "prototype",
) -> RenderJob:
    """One scene, through the multi-scene choke point below.

    Kept as the name three routes already call. It is a wrapper, not a second
    implementation: WP-45's whole point was that the three surfaces share one
    dispatch, and WP-63 adds a fourth (the batch route) without splitting it.
    """
    return await dispatch_scene_media_regenerations(
        db, [scene], reason=reason, tier=tier,
    )


async def dispatch_scene_media_regenerations(
    db: AsyncSession,
    scenes: List[StoryboardScene],
    reason: str,
    tier: str = "prototype",
) -> RenderJob:
    """Create ONE job row and dispatch these scenes' media generation.

    WP-63 Task 7. ONE JOB FOR N SCENES, AND THAT IS FORCED BY THE GUARD RATHER
    THAN CONVENIENT. The in-flight refusal below is armed the moment the first
    job row goes `running`, so regenerating three scenes as three calls fails on
    the second — which is exactly what an operator recovering the three rejected
    scenes of the 2026-08-26 incident has to do. The media join is armed once,
    for however many stages this dispatch produces, so N scenes in one dispatch
    drain correctly and flow on into a fresh composition manifest; N separate
    dispatches would arm N joins against one job and strand all but the first.

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

    if not scenes:
        raise RegenerationError(
            "A regeneration was requested for no scenes at all. Nothing was "
            "dispatched and no job row was created."
        )

    project_ids = {s.project_id for s in scenes}
    if len(project_ids) != 1:
        raise RegenerationError(
            "A regeneration must name scenes of ONE project; these span "
            f"{len(project_ids)}. One job row cannot belong to two projects, "
            "and the media join is keyed on the job."
        )
    project_id = scenes[0].project_id

    await GateService(db).require_storyboard_approval(project_id)

    running = await active_job(db, project_id)
    if running is not None:
        raise PipelineAlreadyRunningError(
            f"Project {project_id} already has a {running.status} "
            f"{running.job_type} run (job {running.id}). Regenerating a scene "
            "while a run is in flight dispatches media work into a pipeline "
            "that is already producing it, and the join counter that pairs "
            "them is armed once. Wait for it to finish, or cancel it.",
            job_id=running.id,
            job_type=running.job_type,
            status=running.status,
        )

    project = await db.scalar(select(Project).where(Project.id == project_id))

    media_types = [s.media_type or "image" for s in scenes]
    # The job row's type names the work. With a mixed batch there is no single
    # true answer, so it names the branch of the FIRST scene and the log below
    # carries the full list -- an honest approximation beats defaulting a video
    # regeneration to `image_generation`, which is what the pre-WP-45 row did.
    job_type = MEDIA_TYPE_JOB_TYPE.get(media_types[0], "image_generation")

    job = RenderJob(
        project_id=project_id,
        job_type=job_type,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    dispatch_input: Dict[str, Any] = {
        "job_id": str(job.id),
        "project_id": str(project_id),
        **project_facts(project, tier=tier),
        "scenes": [scene_payload(s) for s in scenes],
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
            "Scene regeneration dispatch FAILED: scenes=%s job=%s error=%s",
            [str(s.id) for s in scenes], job.id, exc,
        )
        raise RegenerationError(
            "Could not dispatch regeneration for scene(s) "
            f"{', '.join(str(s.id) for s in scenes)}: {exc}"
        ) from exc

    job.celery_task_id = dispatch.id
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)

    logger.info(
        "Scene regeneration dispatched: scenes=%s indexes=%s media_types=%s "
        "job=%s celery_task=%s reason=%s",
        [str(s.id) for s in scenes], [s.scene_index for s in scenes],
        media_types, job.id, dispatch.id, reason,
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


# ---------------------------------------------------------------------------
# Gate `regenerate` — WP-63 Task 8
# ---------------------------------------------------------------------------
#
# WHAT THE DECISION DID, MEASURED. Project 14f71729, 2026-08-26:
#
#   15:17:25.362931Z  gate_decision ... gate=storyboard decision=regenerate
#                     version=sb-9-dba2b2244a87ac6f... by=admin   -> 200 OK
#   15:17:29.616325Z  the same line again, because nothing had happened and the
#                     operator pressed it a second time                -> 200 OK
#
# Two rows in `project_gate_decisions`, two audit entries, zero broker
# messages. §6.4 says the gates "additionally accept reject / regenerate
# signals"; the decision was recorded faithfully and released nothing, so the
# button was a note-taking device.
#
# RULED SEMANTICS (WP-63 Task 8):
#
#   storyboard gate, regenerate  ->  re-run storyboard_generation for the
#                                    project; the gate then re-opens on the new
#                                    artifact version.
#   draft gate, regenerate       ->  re-run the draft assembly (prototype_draft).
#
# BOTH GO THROUGH THE EXISTING TRIGGER LAYER, and neither is a full-pipeline
# run. `dispatch_pipeline` has read `resume_from_stage` off the job context
# since it was written, and `STAGE_TASK_MAP` resolves both stage names, so a
# single stage is dispatchable standalone -- this is the identical mechanism
# `CheckpointService.resume_from_checkpoint` uses, and it was proven live on
# job b3df6eb6 (WP-45 report S4.6). Each stage reports to
# `handle_stage_completion`, which finds no next stage after either of them and
# pauses at the gate; so the re-run ends where it should, at a human.
#
# The job row is RUN-TYPED (`storyboard_generation` / `prototype_draft`) rather
# than borrowing `final_render` as a sentinel the way the resume route does.
# WP-60's six-dispatch storm was diagnosed off `job_type`, and a row that
# misnames its own work is how a fleet-wide guard gets pointed at the wrong
# thing.

#: gate -> the stage its `regenerate` decision re-runs, and the job type that
#: names that work honestly.
GATE_REGENERATE_STAGE = {
    "storyboard": ("storyboard_generation", "storyboard_generation"),
    "draft": ("prototype_draft", "prototype_draft"),
}


async def dispatch_gate_regeneration(
    db: AsyncSession,
    project_id: UUID,
    gate: str,
    reason: str,
    tier: str = "prototype",
) -> RenderJob:
    """Re-run the stage that produced the artifact this gate reviews.

    Guarded exactly as every other dispatch on this fleet is: refuses while a
    run holds the project, before any job row exists, so a refused decision
    leaves no `pending` row to be counted, retried or resumed. The gate
    decision itself has already been recorded by the caller and STANDS either
    way -- a human's decision must not be rolled back because a scheduler
    condition refused to act on it (the rule `_gate_decision` already applies
    to an approval whose release is refused).

    Deliberately NOT behind `require_storyboard_approval`: this IS the gate,
    and a regeneration is the decision a reviewer takes when they do not want
    to approve. Requiring an approval to ask for a re-generation would make the
    decision unreachable in exactly the state it exists for.
    """
    from app.services.project_service import PipelineAlreadyRunningError, active_job

    if gate not in GATE_REGENERATE_STAGE:
        raise RegenerationError(
            f"There is no regeneration defined for the {gate!r} gate. "
            f"Known gates: {sorted(GATE_REGENERATE_STAGE)}."
        )
    stage, job_type = GATE_REGENERATE_STAGE[gate]

    running = await active_job(db, project_id)
    if running is not None:
        raise PipelineAlreadyRunningError(
            f"Project {project_id} already has a {running.status} "
            f"{running.job_type} run (job {running.id}). Re-running "
            f"{stage} now would put a second pipeline over the same project. "
            "Wait for it to finish, or cancel it.",
            job_id=running.id,
            job_type=running.job_type,
            status=running.status,
        )

    project = await db.scalar(select(Project).where(Project.id == project_id))

    job = RenderJob(
        project_id=project_id,
        job_type=job_type,
        resume_from_stage=stage,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    job_context: Dict[str, Any] = {
        "job_id": str(job.id),
        "project_id": str(project_id),
        **project_facts(project, tier=tier),
        "current_stage": stage,
        "resume_from_stage": stage,
    }

    from app.services.celery_producer import celery_app as pipeline_celery

    try:
        dispatch = pipeline_celery.send_task(
            DISPATCH_PIPELINE_TASK,
            kwargs={"job_context_dict": job_context},
            queue=ORCHESTRATOR_QUEUE,
        )
    except Exception as exc:
        job.status = "failed"
        job.error_message = f"Gate regeneration dispatch failed: {exc}"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.error(
            "Gate regeneration dispatch FAILED: project=%s gate=%s stage=%s "
            "job=%s error=%s",
            project_id, gate, stage, job.id, exc,
        )
        raise RegenerationError(
            f"Could not dispatch the {gate} gate's regeneration "
            f"(stage {stage}) for project {project_id}: {exc}"
        ) from exc

    job.celery_task_id = dispatch.id
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)

    logger.info(
        "Gate regeneration dispatched: project=%s gate=%s stage=%s job=%s "
        "celery_task=%s reason=%s",
        project_id, gate, stage, job.id, dispatch.id, reason,
    )
    return job
