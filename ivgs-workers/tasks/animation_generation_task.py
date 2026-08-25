"""
IVGS v5 — Animation Generation Task (Stage 3, animation branch)
================================================================

WP-46. Scenes with ``media_type=animation`` used to be handed to
``tasks.stage3_images.generate_scene_images_task`` — the image task — so an
"animation" was a still. WP-39 gave the branch its own identity (its own
``join_stage`` label, its own checkpoint row, its own Temporal node); this
module gives it its own body.

The model is **Wan2.2-Animate** (MBCP certification
``eb032794-e46e-4787-a399-b45a548c52e5``), served by a ComfyUI instance
carrying kijai's ``WanVideoWrapper`` + ``WanAnimatePreprocess`` + VHS custom
nodes. Engine key is ``comfyui`` — MBCP's SSOT value — so the endpoint comes
from ``resolve_endpoint('comfyui')`` i.e. ``IVGS_COMFYUI_URL``, whose value is
per-worker: node-04's worker points at the image ComfyUI, node-03's at the Wan
ComfyUI. That is the whole of the routing, and it is why this task must only
ever be consumed by the worker that sits with the Wan engine.

What makes this branch different from image and video
-----------------------------------------------------

Wan2.2-Animate is **pose reenactment**, not text-to-video: it needs a
reference image *and* a driving video, and it has no prompt-only mode. Neither
lives on a storyboard scene, so this task resolves them from project assets:

  * ``reference_image`` — the scene's own ``image`` asset (the still the image
    branch already produced for it), or an explicit ``reference_image_asset_id``;
  * ``driving_video`` — the project's ``reference_clip`` asset, or an explicit
    ``driving_video_asset_id``.

Either missing is a **refusal that names the gap before any GPU time**, not a
silent fallback to a still. A still is exactly the defect this package exists
to end.

Processing per scene:
    1. Resolve reference image + driving video (refuse loudly if absent)
    2. SHA-256 dedup on (params, inputs) — an idempotent re-run re-links
    3. Render on the Wan ComfyUI instance via the certified workflow graph
    4. Upload to SeaweedFS, scene-linked, with the content hash
    5. Checkpoint under join_stage

Queue: gpu_animation (node-03, alongside gpu_video on the same worker)
Retry: 2 retries with 30s→90s backoff
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
from clients.wan_animate_client import (
    WanAnimateClient,
    WanAnimateError,
    WanAnimateInputError,
    WanAnimateParams,
    WanAnimateResult,
)
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from providers import ensure_registered
from providers._common import engine_model_id
from shared.providers.binding import ModelBinding, resolve_endpoint
from shared.providers.factory import get_binding
from utils.error_handler import save_checkpoint, update_job_status
from utils.gpu_utils import acquire_gpu_reservation, release_acquired_reservation
from utils.media_converter import check_duplicate_asset, compute_asset_sha256
from utils.person_detector import PersonDetector, PersonPresence
from utils.quality_reporting import submit_quality_score
from utils.video_validator import VideoValidator

logger = structlog.get_logger("ivgs.animation_generation")

#: MBCP's measured peak for this model on the certified configuration
#: (certificate eb032794, run 7d958e88, result 661c5cd1):
#: measured_vram_gb 44.392578125 at 768x1408 / 77 frames. Used as the
#: reservation ask so the scheduler never places it somewhere it cannot fit.
#: The store row's ``vram_gb`` overrides this once the operator fills it in.
CERTIFIED_VRAM_MB = 45458  # ceil(44.392578125 * 1024)

#: The node classes the certified graph needs. A stock ComfyUI answers ``{}``
#: for every one of them, so checking first turns "opaque /prompt validation
#: error" into "you reached the image engine, not the Wan engine".
REQUIRED_NODE_TYPES = (
    "WanVideoModelLoader",
    "WanVideoAnimateEmbeds",
    "WanVideoSampler",
    "OnnxDetectionModelLoader",
    "PoseAndFaceDetection",
    "VHS_LoadVideo",
    "VHS_VideoCombine",
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SceneAnimationInput(BaseModel):
    """Input for a single scene animation."""
    scene_id: str
    scene_index: int
    visual_description: str
    narration_text: str = ""
    duration_seconds: float = 5.0
    scene_title: Optional[str] = None
    # Explicit input overrides. Absent, the task resolves them from the
    # project's assets (scene image / project reference_clip).
    reference_image_asset_id: Optional[str] = None
    driving_video_asset_id: Optional[str] = None


class AnimationGenerationInput(BaseModel):
    """Input for the animation generation task."""
    job_id: str
    project_id: str
    project_name: str = ""
    project_description: str = ""
    target_audience: str = "general"
    language_code: str = "en-US"
    max_runtime_seconds: int = 0
    tier: str = "prototype"
    scenes: List[SceneAnimationInput] = Field(min_length=1)
    enable_dedup: bool = True
    # WP-39: the media join keys each report on its stage label, and this task
    # is dispatched under animation_generation. Carried explicitly so the
    # label travels with the work rather than being re-derived at the end.
    join_stage: Optional[str] = None
    # Pre-approval proof path (WP-46 Task 4). When the store row is still a
    # CANDIDATE, get_binding cannot resolve animation_generation — by design.
    # A harness may then name the engine directly. Never set by the
    # orchestrator; recorded in the output as binding_source so a run made this
    # way can never be mistaken for a bound one.
    engine_endpoint_override: Optional[str] = None
    engine_model_override: Optional[str] = None


class SceneAnimationResult(BaseModel):
    """Result for a single scene animation.

    Field-for-field the shape ``video_generation_task.SceneVideoResult``
    returns, so the composition manifest and the media join read an animation
    scene exactly as they read a video scene.
    """
    scene_id: str
    scene_index: int
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    quality_score: float = 0.0
    quality_decision: str = ""
    # WP-44. Same fields as SceneVideoResult so the review queue reads an
    # animation exactly as it reads a video clip, including what was NOT
    # measured.
    checks_missing: List[str] = Field(default_factory=list)
    check_coverage: float = 0.0
    quality_score_complete: bool = False
    #: The WP-44 Task-5 input guard's verdict on the reference image:
    #: present | absent | unavailable. Recorded even on success, so a render
    #: made while the detector was unavailable is distinguishable afterwards
    #: from one made against a verified subject.
    reference_person_check: str = "not_run"
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    fallback_level: int = 0
    errors: List[str] = Field(default_factory=list)
    status: str = "success"


class AnimationGenerationOutput(BaseModel):
    """Output from the animation generation task."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.ANIMATION_GENERATION.value
    status: StageStatus = StageStatus.SUCCESS
    scene_results: List[SceneAnimationResult] = Field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    total_generation_time_seconds: float = 0.0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------

async def _list_assets(
    project_id: str,
    config: WorkerConfig,
    *,
    scene_id: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Project assets, optionally filtered by scene and type."""
    params: Dict[str, Any] = {"per_page": 100}
    if scene_id:
        params["scene_id"] = scene_id
    if asset_type:
        params["asset_type"] = asset_type
    async with httpx.AsyncClient(
        timeout=60.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.get(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets",
            params=params,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Asset listing failed for project {project_id}: HTTP {resp.status_code}"
            )
        return resp.json().get("data", []) or []


async def _download_asset(asset_id: str, config: WorkerConfig) -> bytes:
    """Download asset bytes from SeaweedFS via the Pipeline API."""
    async with httpx.AsyncClient(
        timeout=300.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.get(
            f"{config.pipeline_api.full_base_url}/assets/{asset_id}/download",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Asset download failed (ID={asset_id}): HTTP {resp.status_code}"
            )
        return resp.content


async def _upload_asset(
    project_id: str,
    scene_id: str,
    data: bytes,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Upload the rendered animation to SeaweedFS, linked to its scene."""
    async with httpx.AsyncClient(
        timeout=300.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets/upload",
            files={"file": (f"{scene_id}_animation.mp4", data, "video/mp4")},
            data={
                "project_id": project_id,
                "scene_id": scene_id,
                "asset_type": "video",
                "content_hash": sha256_hash,
                "metadata": json.dumps(metadata),
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Asset upload failed: HTTP {resp.status_code}")
        return resp.json()


async def _resolve_inputs(
    scene: SceneAnimationInput,
    project_id: str,
    config: WorkerConfig,
    log: Any,
) -> tuple[bytes, bytes, Dict[str, str]]:
    """The reference still and the driving clip for one scene.

    Explicit ids win. Otherwise: the reference image is the scene's own
    ``image`` asset, and the driving video is the project's ``reference_clip``.
    A missing input raises ``WanAnimateInputError`` naming which one and where
    it was looked for — the model cannot substitute a still for a motion source
    and neither will this task.
    """
    ref_id = scene.reference_image_asset_id
    if not ref_id:
        scene_images = await _list_assets(
            project_id, config, scene_id=scene.scene_id, asset_type="image"
        )
        if scene_images:
            ref_id = scene_images[0].get("id")
    if not ref_id:
        raise WanAnimateInputError(
            f"scene {scene.scene_index} ({scene.scene_id}) has no reference image: "
            f"no 'image' asset is linked to it and no reference_image_asset_id was "
            f"supplied. Wan2.2-Animate animates a reference subject; it cannot "
            f"start from a description alone."
        )

    drv_id = scene.driving_video_asset_id
    if not drv_id:
        clips = await _list_assets(project_id, config, asset_type="reference_clip")
        if clips:
            drv_id = clips[0].get("id")
    if not drv_id:
        raise WanAnimateInputError(
            f"scene {scene.scene_index} ({scene.scene_id}) has no driving video: "
            f"project {project_id} has no 'reference_clip' asset and no "
            f"driving_video_asset_id was supplied. Wan2.2-Animate is pose "
            f"reenactment — the motion has to come from somewhere."
        )

    log.info("animation_inputs_resolved", reference_image=ref_id, driving_video=drv_id)
    reference_image = await _download_asset(ref_id, config)
    driving_video = await _download_asset(drv_id, config)
    return reference_image, driving_video, {
        "reference_image_asset_id": str(ref_id),
        "driving_video_asset_id": str(drv_id),
    }


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def _params_from_binding(
    binding: Optional[ModelBinding], scene: SceneAnimationInput
) -> WanAnimateParams:
    """Render parameters: certified defaults, overlaid by the store row.

    ARCH-1: a model's parameters are data. Anything the operator puts in the
    row's ``default_params`` (other than the ``engine_model`` bridge and the
    housekeeping keys MBCP's export stamps) overrides the certified default of
    the same name.
    """
    overrides: Dict[str, Any] = {}
    if binding is not None:
        skip = {"engine_model", "timeout_seconds", "provenance", "weight_tier",
                "engine_version", "quantization"}
        allowed = set(WanAnimateParams.__dataclass_fields__)
        overrides = {
            k: v
            for k, v in (binding.default_params or {}).items()
            if k in allowed and k not in skip
        }
    # The scene's own prompt is its visual description — the thing the
    # storyboard actually says this scene shows.
    if scene.visual_description:
        overrides.setdefault("prompt", scene.visual_description)
    return WanAnimateParams(**overrides)


async def _resolve_binding(
    task_input: AnimationGenerationInput,
    scene: SceneAnimationInput,
    log: Any,
) -> tuple[Optional[ModelBinding], str, str, str]:
    """(binding, endpoint, engine_model, binding_source).

    The normal path is AD-01: ``get_binding('animation_generation')`` resolves
    the selection or the approved default and carries the endpoint with it.
    Before the operator approves the row there is no such model — that is the
    gate working, not a bug — so a harness may name the engine explicitly. The
    source is returned so the caller can record which one happened.
    """
    if task_input.engine_endpoint_override:
        log.warning(
            "animation_binding_overridden",
            endpoint=task_input.engine_endpoint_override,
            reason="explicit override supplied — NOT an AD-01 binding",
        )
        return (
            None,
            task_input.engine_endpoint_override,
            task_input.engine_model_override
            or WanAnimateParams().served_model_name,
            "explicit-override",
        )

    ensure_registered()
    binding = await get_binding(
        PipelineStage.ANIMATION_GENERATION.value,
        project_id=task_input.project_id,
        tier=task_input.tier,
        scene_id=scene.scene_id,
    )
    log.info("model_bound", binding=binding.describe())
    endpoint = binding.endpoint or resolve_endpoint(binding.engine)
    return binding, endpoint, engine_model_id(binding), "ad01-binding"


# ---------------------------------------------------------------------------
# Per-scene render
# ---------------------------------------------------------------------------

async def _process_single_animation(
    scene: SceneAnimationInput,
    client: WanAnimateClient,
    binding: Optional[ModelBinding],
    config: WorkerConfig,
    enable_dedup: bool,
    project_id: str,
    job_id: str = "",
) -> SceneAnimationResult:
    """Render one animated scene end to end."""
    start_time = time.monotonic()
    log = logger.bind(scene_id=scene.scene_id, scene_index=scene.scene_index)

    result = SceneAnimationResult(
        scene_id=scene.scene_id,
        scene_index=scene.scene_index,
    )

    try:
        reference_image, driving_video, input_ids = await _resolve_inputs(
            scene, project_id, config, log
        )

        # --- WP-44 Task 5: the input guard ---
        # Wan2.2-Animate transfers a driver's pose onto the subject of the
        # reference image. If the reference has no subject the model does not
        # refuse — it invents a body. The reference project's storyboard sent
        # equation cards to this branch (scenes 2, 4, 5 … carry "numbers and
        # calculations appearing on screen" and no person at all), which is the
        # run that paid for this check.
        #
        # It runs BEFORE _params_from_binding, before the dedup lookup and
        # before any GPU reservation, because the whole point is to spend
        # ~1.3 s of CPU instead of ~256 s of a 48 GB card.
        detection = PersonDetector().detect(reference_image)
        result.reference_person_check = detection.presence.value
        log.info(
            "animation_reference_person_check",
            presence=detection.presence.value,
            person_count=detection.person_count,
            best_confidence=round(detection.best_confidence, 4),
            elapsed_ms=round(detection.elapsed_ms, 1),
            reason=detection.reason,
        )
        if detection.presence is PersonPresence.ABSENT:
            raise WanAnimateInputError(
                f"reference image contains no person to animate: scene "
                f"{scene.scene_index} ({scene.scene_id}) reference asset "
                f"{input_ids['reference_image_asset_id']} has no person "
                f"detection above {detection.confidence_threshold} "
                f"(best {detection.best_confidence:.3f}, model "
                f"{detection.model}). Wan2.2-Animate is pose reenactment: with "
                f"no subject in the reference it does not decline, it "
                f"hallucinates one. Route this scene to media_type 'image', or "
                f"supply a reference_image_asset_id that contains a character."
            )
        if detection.presence is PersonPresence.UNAVAILABLE:
            # "We could not look" is not "there is nobody there". The render
            # proceeds exactly as it did before this guard existed, and the
            # fact that the check did not run travels with the result.
            log.warning(
                "animation_reference_person_check_unavailable",
                reason=detection.reason,
            )

        params = _params_from_binding(binding, scene)

        # Idempotency. The key covers the parameters AND the exact input bytes,
        # so a re-run of the same scene with the same inputs re-links the asset
        # already in SeaweedFS instead of burning five minutes of GPU to
        # produce it again. Changing either input changes the key.
        params_hash = hashlib.sha256(
            json.dumps(
                {
                    "params": params.compute_hash(),
                    "scene_id": scene.scene_id,
                    "reference_image": hashlib.sha256(reference_image).hexdigest(),
                    "driving_video": hashlib.sha256(driving_video).hexdigest(),
                    "model": client.model or params.served_model_name,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if enable_dedup:
            existing = check_duplicate_asset(
                sha256_hash=params_hash,
                api_base_url=config.pipeline_api.full_base_url,
                service_token=config.pipeline_api.service_token,
            )
            if existing:
                log.info("animation_deduplicated", existing_asset_id=existing["id"])
                result.asset_id = existing["id"]
                result.seaweedfs_path = existing.get("storage_path", "")
                result.sha256_hash = existing.get("content_hash", "")
                result.was_deduplicated = True
                result.model_used = "deduplicated"
                result.generation_time_seconds = round(time.monotonic() - start_time, 2)
                return result

        render: WanAnimateResult = await client.generate_animation(
            reference_image=reference_image,
            driving_video=driving_video,
            params=params,
            input_key=f"{scene.scene_id}",
        )

        result.width = render.width
        result.height = render.height
        result.fps = int(round(render.fps))
        result.duration_seconds = render.duration_seconds
        result.model_used = binding.name if binding is not None else render.model_used
        result.file_size_bytes = len(render.video_data)
        result.sha256_hash = compute_asset_sha256(render.video_data)

        # --- WP-44 Task 3: validate the rendered clip ---
        # expect_audio=False — the certified Wan graph emits a video-only MP4.
        # The distinctness check is the WP-46 addendum's 77/77 measurement made
        # standing: it is what separates an animation from a still in a
        # container, and this branch exists precisely because "animation"
        # used to mean "a PNG".
        validator = VideoValidator()
        validation = validator.validate_bytes(
            render.video_data,
            expected_duration=scene.duration_seconds,
            expected_width=render.width or None,
            expected_height=render.height or None,
            expect_audio=False,
        )
        result.quality_score = validation.quality_score
        result.quality_decision = validation.decision.value
        result.checks_missing = list(validation.checks_missing)
        result.check_coverage = validation.check_coverage
        result.quality_score_complete = validation.quality_score_complete
        log.info(
            "animation_validated",
            decision=validation.decision.value,
            quality_score=validation.quality_score,
            complete=validation.quality_score_complete,
            missing=validation.checks_missing,
            distinct_frames=(validation.distinctness or {}).get("distinct_frames"),
            frames_decoded=(validation.distinctness or {}).get("frames_decoded"),
        )
        if not validation.is_valid:
            log.warning("animation_validation_rejected", errors=validation.errors)
            result.status = "failed"
            result.errors.extend(validation.errors)
            result.generation_time_seconds = round(time.monotonic() - start_time, 2)
            return result

        upload_result = await _upload_asset(
            project_id=project_id,
            scene_id=scene.scene_id,
            data=render.video_data,
            sha256_hash=params_hash,
            metadata={
                "model": result.model_used,
                "engine": "comfyui",
                "engine_model": client.model or render.model_used,
                "media_type": "animation",
                "stage": PipelineStage.ANIMATION_GENERATION.value,
                "width": render.width,
                "height": render.height,
                "fps": render.fps,
                "num_frames": render.num_frames,
                "duration": render.duration_seconds,
                "content_sha256": result.sha256_hash,
                "prompt_id": render.prompt_id,
                "generation_time_seconds": render.generation_time_seconds,
                **input_ids,
            },
            config=config,
        )

        result.asset_id = upload_result.get("id", "")
        result.seaweedfs_path = upload_result.get("seaweedfs_path", "")
        result.generation_time_seconds = round(time.monotonic() - start_time, 2)

        # Record the verdict in the review queue (WP-44). The reference-image
        # check travels with it, so a reviewer can see whether the subject was
        # verified or merely assumed.
        details = validation.scoring_details()
        details["reference_person_check"] = detection.to_dict()
        await submit_quality_score(
            asset_id=result.asset_id,
            quality_score=validation.quality_score,
            quality_decision=validation.decision.value,
            scoring_details=details,
            config=config,
            job_id=job_id,
        )

        log.info(
            "animation_generation_success",
            model=result.model_used,
            prompt_id=render.prompt_id,
            elapsed=result.generation_time_seconds,
            engine_elapsed=render.generation_time_seconds,
            file_size=result.file_size_bytes,
        )

    except (WanAnimateError, Exception) as e:  # noqa: B014 — WanAnimateError first for clarity
        log.error("animation_generation_error", error=str(e), error_type=type(e).__name__)
        result.status = "failed"
        result.errors.append(f"{type(e).__name__}: {e}")
        result.generation_time_seconds = round(time.monotonic() - start_time, 2)

    return result


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.animation_generation_task.generate_scene_animations",
    queue="gpu_animation",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=3600,
    time_limit=3900,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_scene_animations(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Celery task: render the animation scenes of one job.

    Scenes are processed sequentially — one 14B diffusion render at a time is
    all the card has room for, and the worker is concurrency=1 anyway.
    """
    config = WorkerConfig()

    try:
        task_input = AnimationGenerationInput(**task_input_dict)
    except Exception as e:
        logger.error("animation_gen_input_error", error=str(e))
        raise ValueError(f"Invalid animation generation input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    # WP-39: the label this dispatch reports under. Defaulted to the stage's
    # own name rather than to whatever task happens to be running.
    join_stage = task_input.join_stage or PipelineStage.ANIMATION_GENERATION.value
    log = logger.bind(
        job_id=job_id, project_id=project_id, total_scenes=len(task_input.scenes)
    )
    log.info("animation_generation_starting", join_stage=join_stage)

    update_job_status(
        job_id, "running", stage=PipelineStage.ANIMATION_GENERATION.value
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    results: List[SceneAnimationResult] = []
    binding_source = "unresolved"
    reservation = None
    client: Optional[WanAnimateClient] = None

    try:
        # Bind once for the batch: every scene of a job renders on the same
        # model, and resolving per scene would ask the same question N times.
        binding, endpoint, engine_model, binding_source = loop.run_until_complete(
            _resolve_binding(task_input, task_input.scenes[0], log)
        )

        vram_mb = CERTIFIED_VRAM_MB
        if binding is not None and binding.vram_requirement_mb:
            vram_mb = int(binding.vram_requirement_mb)

        # GPU reservation. FAIL-OPEN, deliberately, exactly as the other seven
        # call sites: acquire RAISES (gpu_utils.py:202) and the registry is
        # still empty, so making this fatal would fail every render. Flipping
        # it is AD-05 O-3, after P2.6. Do not "fix" this by raising.
        # The id is stored on the task so IVGSBaseTask.on_success/on_failure
        # can release it if this body does not get there (WP-08).
        try:
            reservation = acquire_gpu_reservation(
                job_id=job_id,
                model_name=binding.name if binding is not None else "Wan2.2-Animate",
                vram_requirement_mb=vram_mb,
                estimated_duration_s=len(task_input.scenes) * 300,
            )
            self._gpu_reservation_id = reservation.get("reservation_id")
        except Exception as e:
            log.warning(
                "gpu_reservation_unavailable",
                stage=PipelineStage.ANIMATION_GENERATION.value,
                model=binding.name if binding is not None else "Wan2.2-Animate",
                vram_mb=vram_mb,
                error_type=type(e).__name__,
                error=str(e),
                fail_open=True,
            )

        client = WanAnimateClient(
            base_url=endpoint,
            model=engine_model,
            default_params=(binding.default_params if binding is not None else None),
        )

        # Capability gate. Both ComfyUI instances answer to the same engine key
        # and the same env var; only one of them can run this graph. Say which
        # one we reached before spending a scene finding out.
        #
        # A mismatch is NOT raised. Raising would retry a deterministic wrong
        # answer twice and then die without reporting, leaving the media join
        # armed and the job hung with nothing to explain it — which is exactly
        # the WP-39 shape. Instead every scene fails with the reason, the
        # terminal checkpoint records it, and the join closes. A *connection*
        # error still propagates from available_node_types(), because an engine
        # that is merely down is worth retrying.
        available = loop.run_until_complete(client.available_node_types())
        absent = [n for n in REQUIRED_NODE_TYPES if n not in available]
        if absent:
            setup_error = (
                f"the ComfyUI at {endpoint} cannot run the wan_animate graph: "
                f"missing node types {absent} (it reports {len(available)} node "
                f"types). IVGS_COMFYUI_URL on this worker points at an image "
                f"ComfyUI, not the Wan engine."
            )
            log.error("animation_engine_incapable", endpoint=endpoint, missing=absent)
            results = [
                SceneAnimationResult(
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    status="failed",
                    errors=[setup_error],
                )
                for scene in task_input.scenes
            ]
            task_input.scenes = []

        for scene in task_input.scenes:
            try:
                scene_result = loop.run_until_complete(
                    _process_single_animation(
                        scene=scene,
                        client=client,
                        binding=binding,
                        config=config,
                        enable_dedup=task_input.enable_dedup,
                        project_id=project_id,
                        job_id=job_id,
                    )
                )
                results.append(scene_result)

                # WP-39: keyed on join_stage, not on a hardcoded stage name.
                # The hardcoded label is the exact defect that let the
                # animation run overwrite the image run's checkpoint row.
                save_checkpoint(
                    job_id=job_id,
                    stage_name=join_stage,
                    stage_index=3,
                    status="running",
                    checkpoint_data={
                        "completed_scenes": [
                            r.scene_id for r in results if r.status == "success"
                        ],
                        "last_scene_index": scene.scene_index,
                    },
                )
            except Exception as e:
                log.error(
                    "scene_animation_gen_error",
                    scene_id=scene.scene_id,
                    error=str(e),
                )
                results.append(
                    SceneAnimationResult(
                        scene_id=scene.scene_id,
                        scene_index=scene.scene_index,
                        status="failed",
                        errors=[str(e)],
                    )
                )
    finally:
        if client is not None:
            try:
                loop.run_until_complete(client.close())
            except Exception:  # noqa: BLE001 — closing must not mask the real error
                pass
        loop.close()
        # WP-08: release_acquired_reservation takes the dict acquire returned.
        # Clearing the id afterwards stops on_success releasing it twice.
        if reservation:
            release_acquired_reservation(reservation, log)
            self._gpu_reservation_id = None

    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failed"]
    deduplicated = [r for r in results if r.was_deduplicated]

    output = AnimationGenerationOutput(
        job_id=job_id,
        project_id=project_id,
        stage=join_stage,
        scene_results=results,
        total_scenes=len(results),
        successful_count=len(successful),
        failed_count=len(failed),
        deduplicated_count=len(deduplicated),
        total_generation_time_seconds=sum(
            r.generation_time_seconds for r in results
        ),
        completed_at=datetime.now(timezone.utc),
    )

    if failed and not successful:
        output.status = StageStatus.FAILED
        update_job_status(
            job_id, "failed", error_message="All animation generations failed"
        )
    elif failed:
        output.status = StageStatus.PARTIAL_SUCCESS
    else:
        output.status = StageStatus.SUCCESS

    # WP-39 ledger (c): the terminal checkpoint. Without it the row stays at
    # the last per-scene write — status "running", checkpoint_status 'pending'
    # — and nothing in the database distinguishes "rendering" from "done".
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
                "total_generation_time": output.total_generation_time_seconds,
                "binding_source": binding_source,
            },
        )

    log.info(
        "animation_generation_complete",
        successful=len(successful),
        failed=len(failed),
        deduplicated=len(deduplicated),
        binding_source=binding_source,
    )

    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )

    return output_dict
