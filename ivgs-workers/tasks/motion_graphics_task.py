"""
IVGS v5 — Motion-Graphics Generation Task (Stage 3, motion_graphics branch)
===========================================================================

WP-IVGS-09 Task 1, executing ledger **RC-I1** and closing **WP-68 L-1/L-2/L-4**.

WP-68 built the templates, the engine row, the capability contract and the
prompt that asks for them, then stopped at the one thing it was forbidden to do:
stand up a renderer. Its orchestrator branch therefore **held** every
``motion_graphics`` scene by name rather than dispatching it (L-4) — the honest
outcome, and one this file now replaces with a render.

WHY THIS IS A NEW FILE AND NOT AN EDIT
--------------------------------------

``dev/CLAUDE.md`` §3 freezes "the eight stage task bodies during the
orchestration migration", and AD-05 §8 makes the boundary binding: the eight
bodies and their services are *"preserve, effectively untouched"*. This is a
NINTH body for a media branch that had none, in the same way WP-46 gave
``animation`` its own body rather than editing ``stage3_images``. Nothing frozen
is touched. ``pipeline_orchestrator_v2.py``, which routes to it, is explicitly
in AD-05 §8's **Replace** column ("the coordination layer only") and is not
frozen.

WHY IT IS NOT AN ENGINE CLIENT CALL IN THE ANIMATION BODY
---------------------------------------------------------

``animation_generation_task`` runs Wan2.2-Animate, which is pose reenactment: it
needs a person in a reference still and a driving clip. WP-68 measured that a
motion graphic has neither, and that pointing the Wan body at one *"would fail
deep in a worker"*. The two branches share a stage in MBCP's taxonomy
(``animation_generation``, which is why WP-67 registers ``maths_motion`` there)
and share nothing at all in their inputs.

WHERE IT RUNS, AND WHY node-01
------------------------------

Queue ``default`` — node-01, the same node as the renderer (RC-I1's placement
ruling: CPU-only, agent-deployable, no GPU contention). The task and the service
therefore talk over the container network with no hop off the node, and no GPU
queue is occupied by work that needs no GPU. **No GPU reservation is taken**:
the other seven media call sites acquire one and fail open (P1.3), and adding an
eighth acquire for a job that will never touch a card would put a fabricated
row in the reservation registry.

WHAT IT PRODUCES, MEASURED AGAINST WHAT STAGE 7 CONSUMES
--------------------------------------------------------

An asset of ``asset_type="video"``, scene-linked. Traced, not assumed:

* ``ivgs-api/app/api/v1/manifests.py:430-435`` — ``_ASSET_TYPE_TO_LAYER`` maps
  ``image`` and ``video`` to ``background``. **Anything else is dropped from the
  timeline entirely** (correctly — WP-27's instance-15 defect was the opposite
  default). An ``animation``-typed asset would not become a layer, and the scene
  would be reported in ``scenes_without_background``.
* ``ivgs-workers/tasks/stage7_prototype_draft.py:258-262`` — the background file
  is named ``.png`` when ``scene.media_type == "image"`` and ``.mp4`` otherwise.
  ``motion_graphics`` takes the ``.mp4`` branch, which is what the renderer
  emits.
* ``ivgs-workers/clients/ffmpeg_client.py:445`` — a background shorter than the
  scene is padded with ``tpad=stop_mode=clone``, holding its final frame. A
  column-arithmetic template's final frame is the answer, so a short template
  ends on the answer and stays there for the rest of the narration.

DEDUP AND IDEMPOTENCY
---------------------

The same template with the same parameters is the same picture, and the renderer
proves it (``X-IVGS-Frames-Digest``). So a re-run re-links the existing asset
instead of uploading a second copy, on the same ``find_duplicate_or_none``
machinery the image and animation branches use. This matters beyond tidiness:
WP-31 Lane C proved Temporal activities must be idempotent, and M3.3-R3 will
wrap this body as one.

FAILURE IS NAMED, NEVER SUBSTITUTED
-----------------------------------

There is no branch here that produces a still, a blank frame, or an asset from
a different render when the renderer refuses. A scene that cannot be rendered
is recorded ``failed`` with the renderer's own words and reports to the media
join, so the pipeline advances with one scene short and **says so** — rather
than composing a draft with a picture nobody asked for.

Queue: default (node-01, CPU-only)
Retry: 2 retries with 30s backoff
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog
from pydantic import BaseModel, Field

from celery_app import IVGSBaseTask, celery_app
from clients.motion_graphics_client import (
    MotionGraphicsClient,
    MotionGraphicsError,
    MotionRenderResult,
)
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from shared.providers.binding import resolve_endpoint
from shared.providers.errors import EndpointResolutionError
from utils.error_handler import save_checkpoint, update_job_status
from utils.media_converter import (
    asset_storage_path,
    compute_asset_sha256,
    find_duplicate_or_none,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SceneMotionInput(BaseModel):
    """One motion_graphics scene, as the dispatcher sends it."""

    scene_id: str
    scene_index: int = 0
    narration_text: Optional[str] = None
    visual_description: Optional[str] = None
    duration_seconds: Optional[float] = None
    #: The structured parameters WP-68 RULE 8 makes the storyboard write.
    #:
    #: ONE OBJECT is the real shape --- `SceneCreate.generation_params` is a
    #: `Dict` (`ivgs-api/app/schemas/storyboard.py:66`) and WP-68 §5.1 measured
    #: one per scene. `Any` rather than `dict` because the column is JSON and a
    #: list HAS been written to it by hand; `_params_for_scene` accepts a list
    #: and says so in the log rather than failing on a shape the database will
    #: happily store.
    generation_params: Any = None


class MotionGraphicsInput(BaseModel):
    """Input for the motion_graphics media branch."""

    job_id: str
    project_id: str
    scenes: List[SceneMotionInput] = Field(default_factory=list)
    enable_dedup: bool = True
    #: WP-39. The label this dispatch reports under, carried rather than
    #: derived, so a branch cannot report under another branch's name.
    join_stage: Optional[str] = None
    # Media facts travel with every media task; unused here but accepted so the
    # dispatcher does not need a special case.
    project_name: str = ""
    project_description: str = ""
    target_audience: str = "general"
    language_code: str = "en-US"
    max_runtime_seconds: Optional[int] = None
    tier: Optional[str] = None


class SceneMotionResult(BaseModel):
    scene_id: str
    scene_index: int = 0
    template: str = ""
    asset_id: str = ""
    seaweedfs_path: str = ""
    frames: int = 0
    duration_seconds: float = 0.0
    frames_digest: str = ""
    renderer_build: str = ""
    file_size_bytes: int = 0
    was_deduplicated: bool = False
    render_time_seconds: float = 0.0
    status: str = "success"
    errors: List[str] = Field(default_factory=list)


class MotionGraphicsOutput(BaseModel):
    job_id: str
    project_id: str
    stage: str = PipelineStage.MOTION_GRAPHICS.value
    status: StageStatus = StageStatus.SUCCESS
    scene_results: List[SceneMotionResult] = Field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    total_render_time_seconds: float = 0.0
    renderer_endpoint: str = ""
    renderer_build: str = ""
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _params_for_scene(scene: SceneMotionInput) -> List[Dict[str, Any]]:
    """The template invocations a scene asks for.

    ``generation_params`` is stored as JSON and WP-68 §5.1 measured it arriving
    as a LIST of objects. A single object is accepted too — a scene that shows
    one step is the common case and rejecting it would be pedantry — but
    anything else is refused by name rather than coerced, because coercing an
    unexpected shape is how a scene renders something nobody asked for.
    """
    raw = scene.generation_params
    if raw in (None, "", [], {}):
        raise ValueError(
            f"scene {scene.scene_id} is media_type=motion_graphics but carries no "
            f"generation_params. WP-68 RULE 8 requires the storyboard to write "
            f"the structured parameters ({{'template': ..., ...}}); prose cannot "
            f"be rendered by a template."
        )
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"scene {scene.scene_id}: generation_params is a string that is "
                f"not JSON ({exc})"
            ) from exc
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        return list(raw)
    raise ValueError(
        f"scene {scene.scene_id}: generation_params must be an object or a list "
        f"of objects, got {type(raw).__name__}"
    )


def _params_hash(invocations: List[Dict[str, Any]]) -> str:
    """A stable idempotency key over what was asked for.

    ``sort_keys`` so two dicts that differ only in insertion order do not look
    like two different renders.
    """
    return hashlib.sha256(
        json.dumps(invocations, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _upload_asset(
    project_id: str,
    scene_id: str,
    data: bytes,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
    generation_params_hash: str = "",
) -> Dict[str, Any]:
    """Upload the rendered MP4, scene-linked, as ``asset_type="video"``.

    ``video``, not ``animation``: ``manifests.py``'s layer map has four keys and
    ``animation`` is not one of them, so an ``animation``-typed asset would be
    excluded from the timeline with a log line and the scene would compose with
    no picture. The same reasoning WP-45 applied to the Wan branch, which uploads
    ``video`` for the same reason.

    ``content_hash`` is a claim about the BYTES; ``generation_params_hash`` is a
    caller-owned idempotency key. They travel in their own fields — sending one
    under the other's name is the defect WP-45 fixed on the animation branch.
    """
    form = {
        "scene_id": scene_id,
        "asset_type": "video",
        "content_hash": sha256_hash,
        "metadata": json.dumps(metadata),
    }
    if generation_params_hash:
        form["generation_params_hash"] = generation_params_hash
    async with httpx.AsyncClient(
        timeout=300.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets/upload",
            files={"file": (f"{scene_id}_motion.mp4", data, "video/mp4")},
            data=form,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Asset upload failed: HTTP {resp.status_code} — {resp.text[:300]}"
            )
        return resp.json()


async def _render_one_scene(
    scene: SceneMotionInput,
    project_id: str,
    client: MotionGraphicsClient,
    config: WorkerConfig,
    enable_dedup: bool,
    log: Any,
) -> SceneMotionResult:
    """Render one scene's template(s) and register the result.

    A scene with several invocations renders the FIRST and records the rest as
    unrendered, by name. Concatenating them would need a decision about ordering
    and timing that nothing has made, and inventing one here would put a
    composition rule in a media task. Stated rather than silently dropped —
    ``multi_invocation_scene_rendered_first_only`` is greppable.
    """
    started = time.monotonic()
    result = SceneMotionResult(scene_id=scene.scene_id, scene_index=scene.scene_index)

    try:
        invocations = _params_for_scene(scene)
    except ValueError as exc:
        result.status = "failed"
        result.errors.append(str(exc))
        result.render_time_seconds = round(time.monotonic() - started, 2)
        log.error("motion_scene_params_invalid", scene_id=scene.scene_id, error=str(exc))
        return result

    if len(invocations) > 1:
        log.warning(
            "multi_invocation_scene_rendered_first_only",
            scene_id=scene.scene_id,
            invocations=len(invocations),
            rendered=invocations[0],
            note=(
                "this scene asks for more than one template step; nothing in "
                "this system decides how to sequence them, so the first is "
                "rendered and the rest are named here rather than dropped"
            ),
        )

    params = invocations[0]
    result.template = str(params.get("template", ""))
    params_hash = _params_hash(invocations)

    # Idempotent re-run: the same parameters are the same picture. Probed on
    # the PARAMS hash, before rendering — a content hash is only knowable after
    # the render, which is the work being avoided. `find_duplicate_or_none`
    # fails open under one greppable event (WP-45); that is its documented
    # contract, so there is no second `except` here pretending to add safety.
    if enable_dedup:
        existing = find_duplicate_or_none(
            sha256_hash=params_hash,
            api_base_url=config.pipeline_api.full_base_url,
            service_token=config.pipeline_api.service_token,
            hash_kind="params",
            project_id=project_id,
        )
        if existing:
            result.asset_id = str(existing.get("id", ""))
            result.seaweedfs_path = asset_storage_path(existing)
            result.file_size_bytes = int(existing.get("file_size_bytes", 0) or 0)
            result.was_deduplicated = True
            result.render_time_seconds = round(time.monotonic() - started, 2)
            log.info(
                "motion_scene_deduplicated",
                scene_id=scene.scene_id,
                asset_id=result.asset_id,
                params_hash=params_hash,
            )
            return result

    try:
        rendered: MotionRenderResult = await client.render(params)
    except MotionGraphicsError as exc:
        result.status = "failed"
        result.errors.append(str(exc))
        result.render_time_seconds = round(time.monotonic() - started, 2)
        # Named, and NOT substituted. The scene composes with no picture and the
        # manifest reports it in `scenes_without_background`.
        log.error(
            "motion_scene_render_refused",
            scene_id=scene.scene_id,
            template=result.template,
            error=str(exc),
        )
        return result

    content_hash = compute_asset_sha256(rendered.data)
    metadata = {
        "engine": "motion_graphics",
        "family": "maths_motion",
        "template": rendered.template,
        "template_params": {k: v for k, v in params.items() if k != "template"},
        "frames": rendered.frames,
        "fps": rendered.fps,
        "duration_seconds": rendered.duration_seconds,
        # The determinism claim, banked on the asset. A later run with the same
        # parameters must produce this digest; if it does not, either the
        # templates or the renderer moved, and the asset says which build drew it.
        "frames_digest": rendered.frames_digest,
        "renderer_build_ref": rendered.build_ref,
        "generation_params_hash": params_hash,
    }
    if len(invocations) > 1:
        metadata["unrendered_invocations"] = invocations[1:]

    upload = await _upload_asset(
        project_id=project_id,
        scene_id=scene.scene_id,
        data=rendered.data,
        sha256_hash=content_hash,
        metadata=metadata,
        config=config,
        generation_params_hash=params_hash,
    )

    result.asset_id = str(upload.get("id", ""))
    result.seaweedfs_path = str(upload.get("seaweedfs_path", "") or "")
    result.frames = rendered.frames
    result.duration_seconds = rendered.duration_seconds
    result.frames_digest = rendered.frames_digest
    result.renderer_build = rendered.build_ref
    result.file_size_bytes = len(rendered.data)
    result.render_time_seconds = round(time.monotonic() - started, 2)

    log.info(
        "motion_scene_rendered",
        scene_id=scene.scene_id,
        template=rendered.template,
        asset_id=result.asset_id,
        frames=rendered.frames,
        duration_seconds=rendered.duration_seconds,
        frames_digest=rendered.frames_digest,
        bytes=result.file_size_bytes,
    )
    return result


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.motion_graphics_task.render_scene_motion_graphics",
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    # A 128-frame template rasterises in seconds. These are generous by two
    # orders of magnitude and exist so a hung HTTP call cannot occupy the
    # default queue indefinitely, not as a performance estimate.
    soft_time_limit=600,
    time_limit=900,
    acks_late=True,
    reject_on_worker_lost=True,
)
def render_scene_motion_graphics(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Celery task: render the motion_graphics scenes of one job."""
    config = WorkerConfig()

    try:
        task_input = MotionGraphicsInput(**task_input_dict)
    except Exception as e:
        logger.error("motion_graphics_input_error", error=str(e))
        raise ValueError(f"Invalid motion graphics input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    join_stage = task_input.join_stage or PipelineStage.MOTION_GRAPHICS.value
    log = logger.bind(
        job_id=job_id, project_id=project_id, total_scenes=len(task_input.scenes),
    )
    log.info("motion_graphics_starting", join_stage=join_stage)

    update_job_status(job_id, "running", stage=PipelineStage.MOTION_GRAPHICS.value)

    results: List[SceneMotionResult] = []
    endpoint = ""
    renderer_build = "unknown"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client: Optional[MotionGraphicsClient] = None

    try:
        # Resolve the endpoint ONCE for the batch. An unset
        # IVGS_MOTION_GRAPHICS_URL raises EndpointResolutionError by name — the
        # WP-68 design — rather than defaulting to a service that would answer
        # 400 (the `animatediff` failure WP-65 measured).
        endpoint = resolve_endpoint("motion_graphics")
        client = MotionGraphicsClient(endpoint)

        # Ask the renderer what it is before asking it to draw. This is the one
        # place a fabricated frame could enter — a renderer with no font or no
        # ffmpeg answers /healthz 503 — so every scene fails with THAT reason
        # rather than each discovering it separately.
        health = loop.run_until_complete(client.health())
        renderer_build = str(health.get("build_ref", "unknown"))
        log.info(
            "motion_renderer_ready",
            endpoint=endpoint,
            build_ref=renderer_build,
            templates=health.get("templates"),
        )

        for scene in sorted(task_input.scenes, key=lambda s: s.scene_index):
            results.append(
                loop.run_until_complete(
                    _render_one_scene(
                        scene, project_id, client, config,
                        task_input.enable_dedup, log,
                    )
                )
            )

    except (EndpointResolutionError, MotionGraphicsError) as e:
        # The renderer is absent, unreachable or not ready. EVERY scene fails
        # with the reason, and the task still reports to the media join.
        #
        # Raising instead would retry a deterministic answer twice and then die
        # without reporting, leaving the join armed and the job hung with
        # nothing to explain it — the WP-39 shape, and the same reasoning the
        # Wan body's capability gate records.
        log.error(
            "motion_graphics_unavailable",
            endpoint=endpoint or "(unresolved)",
            error=str(e),
            error_type=type(e).__name__,
        )
        results = [
            SceneMotionResult(
                scene_id=s.scene_id,
                scene_index=s.scene_index,
                status="failed",
                errors=[f"{type(e).__name__}: {e}"],
            )
            for s in sorted(task_input.scenes, key=lambda s: s.scene_index)
        ]
    except Exception as e:  # noqa: BLE001 — one scene's crash must not hide the report
        log.error(
            "motion_graphics_error", error=str(e), error_type=type(e).__name__,
        )
        done = {r.scene_id for r in results}
        results.extend(
            SceneMotionResult(
                scene_id=s.scene_id,
                scene_index=s.scene_index,
                status="failed",
                errors=[f"{type(e).__name__}: {e}"],
            )
            for s in task_input.scenes
            if s.scene_id not in done
        )
    finally:
        if client is not None:
            try:
                loop.run_until_complete(client.close())
            except Exception:  # noqa: BLE001 — closing must not mask the real error
                pass
        loop.close()

    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failed"]
    deduplicated = [r for r in results if r.was_deduplicated]

    output = MotionGraphicsOutput(
        job_id=job_id,
        project_id=project_id,
        stage=join_stage,
        scene_results=results,
        total_scenes=len(results),
        successful_count=len(successful),
        failed_count=len(failed),
        deduplicated_count=len(deduplicated),
        total_render_time_seconds=round(
            sum(r.render_time_seconds for r in results), 2
        ),
        renderer_endpoint=endpoint,
        renderer_build=renderer_build,
        completed_at=datetime.now(timezone.utc),
    )

    if failed and not successful:
        output.status = StageStatus.FAILED
        update_job_status(
            job_id, "failed",
            error_message=(
                "All motion_graphics renders failed: "
                + "; ".join(sorted({e for r in failed for e in r.errors}))[:400]
            ),
        )
    elif failed:
        output.status = StageStatus.PARTIAL_SUCCESS
    else:
        output.status = StageStatus.SUCCESS

    # WP-39 ledger (c): the terminal checkpoint, so the row distinguishes
    # "rendering" from "done" instead of resting at the last per-scene write.
    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=job_id,
            stage_name=join_stage,
            stage_index=3,
            status=output.status.value,
            checkpoint_data={
                "successful_count": len(successful),
                "failed_count": len(failed),
                "deduplicated_count": len(deduplicated),
                "renderer_endpoint": endpoint,
                "renderer_build": renderer_build,
            },
        )

    log.info(
        "motion_graphics_complete",
        successful=len(successful),
        failed=len(failed),
        deduplicated=len(deduplicated),
        renderer_build=renderer_build,
    )

    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )
    return output_dict
