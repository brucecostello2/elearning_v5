"""
Stub activity bodies for the shadow (WP-41 Task 1).

**No GPU call, no engine client, no Pipeline API, no database, no SeaweedFS.**
Each body sleeps, heartbeats, and produces the output shape its stage really
produces. What is *not* stubbed is the part the migration has to get right:

  * the **idempotency binding** — every writing activity routes its effect
    through ``IdempotentEffectStore.apply`` on its ``(job_id, stage,
    scene_index)`` key, so a second delivery converges instead of duplicating
    (AD-05 Draft 2 §6, from WP-31 Lane C's measurement);
  * **heartbeating** — AD-05 §9 makes it a requirement on the wrapper, not an
    option, so the stubs heartbeat on the same cadence the policy declares;
  * the **execution ledger** — every body records start and complete with pid
    and attempt, fsync'd, because the worker running it is going to be
    SIGKILLed on purpose and the ledger is the only witness that survives
    independently of anything Temporal reports.

The ledger and the effect store are two separate counts on purpose. WP-31's
first evidence run reported a false PASS over an empty table; the pair
"N bodies executed" against "M effects exist" cannot be trivially true.

Image and animation used to share ONE implementation under TWO registered
activity names — the honest shape while they were one Celery task on one
engine. WP-46 gave animation its own task, its own engine (Wan2.2-Animate on
the Wan ComfyUI) and its own queue, so they are now two implementations with
two input shapes. What has not changed is the rule underneath: ``ctx.label``
and ``ctx.idempotency_key`` arrive from the DagNode, so neither run can be
mistaken for the other — which is exactly what happened on 2026-08-23 when
``Stage3Output.stage`` defaulted to a hardcoded ``image_generation`` and a
12-scene animation completion was dropped as a duplicate.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict

from temporalio import activity
from temporalio.exceptions import ApplicationError

from temporal_pipeline.idempotency import IdempotentEffectStore
from temporal_pipeline.payloads import (
    ActivityContext,
    AssembleDraftInput,
    AssembleDraftOutput,
    BuildManifestInput,
    BuildManifestOutput,
    GenerateStoryboardInput,
    GenerateStoryboardOutput,
    GenerateVoiceoverInput,
    GenerateVoiceoverOutput,
    ProfileRenderResult,
    RefineTranscriptInput,
    RefineTranscriptOutput,
    RefinedTranscript,
    RenderFinalInput,
    RenderFinalOutput,
    RenderSceneAnimationInput,
    RenderSceneAnimationOutput,
    RenderSceneImageInput,
    RenderSceneImageOutput,
    RenderSceneVideoInput,
    RenderSceneVideoOutput,
    RenderTalkingHeadInput,
    RenderTalkingHeadOutput,
    Reservation,
    ReservationRequest,
    SceneVoiceoverResult,
)

# One directory per job, under a root the worker chooses. Nothing here is a
# pipeline path: the shadow writes only to its own state root.
STATE_ROOT = Path(os.environ.get("IVGS_TEMPORAL_SHADOW_STATE", "/tmp/ivgs-temporal-shadow"))


class StubTransientError(Exception):
    """A stub failure the retry policy is allowed to retry."""


class StubPermanentError(Exception):
    """A stub failure the retry policy must not retry (non_retryable_error_types)."""


# The workflow cannot pass per-run failure instructions into an activity
# without changing its input shape, and the input shapes are mirrors that must
# not grow test-only fields. The worker sets this from its own CLI instead.
_FAIL_SCENES: Dict[str, list] = {}


def set_fail_scenes(job_id: str, scene_indexes: list) -> None:
    """Test/demo hook: make named scenes fail, to exercise partial-advance."""
    _FAIL_SCENES[job_id] = list(scene_indexes)


# ---------------------------------------------------------------------------
# Per-job state
# ---------------------------------------------------------------------------

def job_root(job_id: str) -> Path:
    return STATE_ROOT / job_id


def store_for(job_id: str) -> IdempotentEffectStore:
    return IdempotentEffectStore(job_root(job_id))


def _ledger_path(job_id: str) -> Path:
    return job_root(job_id) / "bodies.jsonl"


def record_body(job_id: str, key: str, event: str, attempt: int, **extra: Any) -> None:
    """
    Append-and-fsync one line of the execution ledger.

    Written by the activity, in the worker process, before and after the body
    does its work -- so it survives the worker being killed between the two.
    """
    path = _ledger_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": round(time.time(), 3),
            "event": event,
            "key": key,
            "attempt": attempt,
            "pid": os.getpid(),
            **extra,
        }
    )
    with path.open("a") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


async def _work(seconds: float, heartbeat_every: float = 2.0) -> None:
    """Sleep, heartbeating throughout. AD-05 §9: a long render is long, not hung."""
    waited = 0.0
    while waited < seconds:
        step = min(heartbeat_every, seconds - waited)
        await asyncio.sleep(step)
        waited += step
        try:
            activity.heartbeat(f"{waited:.1f}/{seconds:.1f}s")
        except RuntimeError:
            # Called outside an activity context (unit test). Not a failure.
            pass


def _attempt(default: int = 1) -> int:
    """
    The server's attempt number, or ``default`` outside an activity context.

    The fallback matters: the duplicate-delivery demonstration calls these
    bodies directly, and reporting attempt 1 for a second delivery would make
    the evidence read as if the redelivery had never been asked for.
    """
    try:
        return activity.info().attempt
    except RuntimeError:
        return default


def _run_once(
    ctx: ActivityContext,
    produce: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    The idempotency binding, in one place.

    Draft 2 §6 requirement 2 -- an activity wrapper MUST NOT assume single
    execution. So no wrapper calls ``produce`` directly; they all come through
    here, and the store decides whether this delivery is the one that does the
    work.
    """
    store = store_for(ctx.job_id)
    outcome = store.apply(ctx.idempotency_key, produce, attempt=ctx.attempt)
    record_body(
        ctx.job_id,
        ctx.idempotency_key,
        "effect",
        ctx.attempt,
        created=outcome.created,
        deliveries=outcome.deliveries,
        label=ctx.label,
    )
    return outcome.record


def _maybe_fail(ctx: ActivityContext, fail_scene_indexes: list[int]) -> None:
    """
    AD-05 §12 test 4: a deliberately failed scene must drain and partial-advance.

    Raised BEFORE the effect is produced, so a failing scene leaves no artifact
    -- which is what makes the partial-advance count in the workflow honest.
    """
    if ctx.scene_index is not None and ctx.scene_index in fail_scene_indexes:
        raise ApplicationError(
            f"deliberate stub failure on scene {ctx.scene_index}",
            type=StubPermanentError.__name__,
            non_retryable=True,
        )


def _start(ctx: ActivityContext) -> ActivityContext:
    ctx.attempt = _attempt(default=ctx.attempt or 1)
    record_body(ctx.job_id, ctx.idempotency_key, "start", ctx.attempt, label=ctx.label)
    return ctx


def _done(ctx: ActivityContext) -> None:
    record_body(ctx.job_id, ctx.idempotency_key, "complete", ctx.attempt, label=ctx.label)


# ---------------------------------------------------------------------------
# Stage 1 — gpu_llm
# ---------------------------------------------------------------------------

@activity.defn
async def refine_transcript(inp: RefineTranscriptInput) -> RefineTranscriptOutput:
    ctx = _start(inp.ctx)
    await _work(2.0)

    def produce() -> Dict[str, Any]:
        return {
            "refined": [
                {
                    "transcript_id": t.id,
                    "sequence_order": t.sequence_order,
                    "refined_text": f"[stub-refined] {t.original_text[:60]}",
                }
                for t in inp.transcripts
            ]
        }

    record = _run_once(ctx, produce)
    _done(ctx)
    return RefineTranscriptOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        stage=ctx.label,
        status="success",
        refined_transcripts=[
            RefinedTranscript(
                transcript_id=r["transcript_id"],
                sequence_order=r["sequence_order"],
                refined_text=r["refined_text"],
            )
            for r in record.get("refined", [])
        ],
        total_transcripts=len(inp.transcripts),
        successful_count=len(inp.transcripts),
        model_used="stub",
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 2 — gpu_llm
# ---------------------------------------------------------------------------

@activity.defn
async def generate_storyboard(inp: GenerateStoryboardInput) -> GenerateStoryboardOutput:
    """
    The stub returns the storyboard the run was started with.

    That is not a shortcut around the design: the workflow recompiles its DAG
    from whatever this activity returns, so the media branches that appear
    downstream are genuinely derived from a storyboard rather than hardcoded.
    A run started with 4 image / 12 animation / 2 video scenes compiles three
    branches here because this activity said so.
    """
    ctx = _start(inp.ctx)
    await _work(2.0)

    def produce() -> Dict[str, Any]:
        return {"scene_count": len(inp.refined_transcripts)}

    _run_once(ctx, produce)
    _done(ctx)
    # The scenes themselves travel in the workflow's own input; the activity
    # confirms the count it "generated".
    return GenerateStoryboardOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        stage=ctx.label,
        status="success",
        model_used="stub",
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 3 — three labels, two activity names, one implementation
# ---------------------------------------------------------------------------

async def _render_scene_image_impl(
    inp: RenderSceneImageInput, fail_scene_indexes: list[int]
) -> RenderSceneImageOutput:
    ctx = _start(inp.ctx)
    _maybe_fail(ctx, fail_scene_indexes)
    await _work(inp.duration_seconds if inp.duration_seconds < 8 else 4.0)

    def produce() -> Dict[str, Any]:
        return {
            "artifact": f"stub://{ctx.job_id}/{ctx.label}/scene{inp.scene_index}",
            "scene_id": inp.scene_id,
            "label": ctx.label,
        }

    record = _run_once(ctx, produce)
    _done(ctx)
    return RenderSceneImageOutput(
        scene_id=inp.scene_id,
        scene_index=inp.scene_index,
        asset_id=record["artifact"],
        seaweedfs_path=record["artifact"],
        model_used="stub",
        status="success",
        # From the DagNode, never from a default. This one line is WP-39.
        stage=ctx.label,
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


@activity.defn
async def render_scene_image(inp: RenderSceneImageInput) -> RenderSceneImageOutput:
    return await _render_scene_image_impl(inp, _FAIL_SCENES.get(inp.ctx.job_id, []))


@activity.defn
async def render_scene_animation(
    inp: RenderSceneAnimationInput,
) -> RenderSceneAnimationOutput:
    """
    The animation branch: its own shape, its own queue, its own engine.

    Kept a separate registered name since WP-39 so that "which stage ran" is
    answerable from the event history alone, without decoding a payload -- the
    question WP-39 could not answer for three hours. WP-46 made the separation
    real rather than nominal: this mirrors
    ``tasks.animation_generation_task``, which renders on Wan2.2-Animate from a
    reference image and a driving video.

    Still a shadow body (``stub://``) like every activity in this module --
    WP-41 is the migration's scaffolding, not its cutover.
    """
    ctx = _start(inp.ctx)
    _maybe_fail(ctx, _FAIL_SCENES.get(ctx.job_id, []))
    await _work(inp.duration_seconds if inp.duration_seconds < 8 else 4.0)

    def produce() -> Dict[str, Any]:
        return {
            "artifact": f"stub://{ctx.job_id}/{ctx.label}/scene{inp.scene_index}",
            "scene_id": inp.scene_id,
            "label": ctx.label,
        }

    record = _run_once(ctx, produce)
    _done(ctx)
    return RenderSceneAnimationOutput(
        scene_id=inp.scene_id,
        scene_index=inp.scene_index,
        asset_id=record["artifact"],
        seaweedfs_path=record["artifact"],
        model_used="stub",
        status="success",
        # From the DagNode, never from a default. This one line is WP-39.
        stage=ctx.label,
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


@activity.defn
async def render_scene_video(inp: RenderSceneVideoInput) -> RenderSceneVideoOutput:
    ctx = _start(inp.ctx)
    _maybe_fail(ctx, _FAIL_SCENES.get(ctx.job_id, []))
    await _work(inp.duration_seconds if inp.duration_seconds < 8 else 4.0)

    def produce() -> Dict[str, Any]:
        return {
            "artifact": f"stub://{ctx.job_id}/{ctx.label}/scene{inp.scene_index}",
            "scene_id": inp.scene_id,
            "label": ctx.label,
        }

    record = _run_once(ctx, produce)
    _done(ctx)
    return RenderSceneVideoOutput(
        scene_id=inp.scene_id,
        scene_index=inp.scene_index,
        asset_id=record["artifact"],
        seaweedfs_path=record["artifact"],
        model_used="stub",
        status="success",
        stage=ctx.label,
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 4 — default
# ---------------------------------------------------------------------------

@activity.defn
async def build_composition_manifest(inp: BuildManifestInput) -> BuildManifestOutput:
    ctx = _start(inp.ctx)
    await _work(2.0)

    def produce() -> Dict[str, Any]:
        return {"manifest_id": f"stub-manifest-{ctx.job_id}", "status": "locked"}

    record = _run_once(ctx, produce)
    _done(ctx)
    return BuildManifestOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        manifest_id=record["manifest_id"],
        status=record["status"],
        stage=ctx.label,
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 5 — gpu_tts
# ---------------------------------------------------------------------------

@activity.defn
async def generate_voiceover(inp: GenerateVoiceoverInput) -> GenerateVoiceoverOutput:
    ctx = _start(inp.ctx)
    await _work(3.0)

    def produce() -> Dict[str, Any]:
        return {
            "audio": [
                {"scene_id": s.scene_id, "scene_index": s.scene_index}
                for s in inp.scenes
            ]
        }

    record = _run_once(ctx, produce)
    _done(ctx)
    return GenerateVoiceoverOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        stage=ctx.label,
        status="success",
        scene_results=[
            SceneVoiceoverResult(
                scene_id=a["scene_id"],
                scene_index=a["scene_index"],
                asset_id=f"stub://{ctx.job_id}/tts/scene{a['scene_index']}",
                model_used="stub",
            )
            for a in record.get("audio", [])
        ],
        total_scenes=len(inp.scenes),
        successful_count=len(inp.scenes),
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 6 — gpu_talking_head
# ---------------------------------------------------------------------------

@activity.defn
async def render_talking_head(inp: RenderTalkingHeadInput) -> RenderTalkingHeadOutput:
    ctx = _start(inp.ctx)
    await _work(3.0)

    def produce() -> Dict[str, Any]:
        return {"asset_id": f"stub://{ctx.job_id}/head"}

    record = _run_once(ctx, produce)
    _done(ctx)
    return RenderTalkingHeadOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        stage=ctx.label,
        status="success",
        asset_id=record["asset_id"],
        model_used="stub",
        # alignment_scored=False on purpose: a stub measured nothing, and
        # ledger P1.4e is that alignment_score is not a quality signal even
        # when a real engine produces it.
        alignment_scored=False,
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 7 — composition
# ---------------------------------------------------------------------------

@activity.defn
async def assemble_prototype_draft(inp: AssembleDraftInput) -> AssembleDraftOutput:
    ctx = _start(inp.ctx)
    await _work(3.0)

    def produce() -> Dict[str, Any]:
        return {"asset_id": f"stub://{ctx.job_id}/draft"}

    record = _run_once(ctx, produce)
    _done(ctx)
    return AssembleDraftOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        stage=ctx.label,
        status="success",
        asset_id=record["asset_id"],
        scene_count=len(inp.scenes),
        scenes_composed=len(inp.scenes),
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# Stage 8 — composition
# ---------------------------------------------------------------------------

@activity.defn
async def render_final(inp: RenderFinalInput) -> RenderFinalOutput:
    ctx = _start(inp.ctx)
    await _work(3.0)

    def produce() -> Dict[str, Any]:
        return {"profiles": list(inp.render_profiles)}

    record = _run_once(ctx, produce)
    _done(ctx)
    return RenderFinalOutput(
        job_id=ctx.job_id,
        project_id=ctx.project_id,
        stage=ctx.label,
        status="success",
        profile_results=[
            ProfileRenderResult(
                profile=p,
                asset_id=f"stub://{ctx.job_id}/final/{p}",
                status="success",
            )
            for p in record.get("profiles", [])
        ],
        idempotency_key=ctx.idempotency_key,
        attempt=ctx.attempt,
    )


# ---------------------------------------------------------------------------
# GPU reservation (AD-05 §6, O-3)
# ---------------------------------------------------------------------------

@activity.defn
async def acquire_gpu_reservation(req: ReservationRequest) -> Reservation:
    """
    Stub for ``ivgs-scheduler``'s acquire.

    It grants unconditionally. The interesting half is in the workflow: the
    matching release lives in a ``finally``, so there is no call site that can
    forget it. D4 was seven acquires against three releases that raised
    TypeError -- an asymmetry only possible because release was something a
    stage body had to remember to do.
    """
    ctx = _start(req.ctx)
    reservation = Reservation(
        reservation_id=f"stub-res-{ctx.job_id}-{req.stage_label}",
        node_id="stub-node",
        granted=True,
    )
    # No _run_once: a reservation is not an artifact, and acquiring twice is
    # not something an effect store should paper over. Its key carries a
    # `-gpu` suffix precisely so it never lands in the same bucket as the
    # stage's own effect. The protection here is the release in the workflow's
    # `finally`, not idempotency.
    _done(ctx)
    return reservation


@activity.defn
async def release_gpu_reservation(reservation: Reservation) -> bool:
    """Stub for the release. One parameter, as ``gpu_utils.py:211`` declares."""
    return True


ALL_ACTIVITIES = [
    refine_transcript,
    generate_storyboard,
    render_scene_image,
    render_scene_animation,
    render_scene_video,
    build_composition_manifest,
    generate_voiceover,
    render_talking_head,
    assemble_prototype_draft,
    render_final,
    acquire_gpu_reservation,
    release_gpu_reservation,
]
