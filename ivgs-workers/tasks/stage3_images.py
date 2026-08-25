"""
IVGS v5 — Stage 3: Scene Image Generation Task
==================================================

Pipeline Stage 3 per §6.1:
- Trigger: Storyboard generation (Stage 2) completed
- Input: Storyboard scenes with visual descriptions
- Processing per scene:
    1. Generate FLUX.1-compatible prompt via vLLM Mistral 24B
    2. Submit to ComfyUI FLUX.1-schnell (1024×1024, 4 steps)
    3. Upscale to 1920×1080 via PIL (LANCZOS)
    4. Validate: resolution, format, corruption, CLIP score
    5. SHA-256 dedup check before upload
    6. Store PNG to SeaweedFS: /ivgs/images/{project_id}/scenes/{scene_id}/
    7. Update scene.image_asset_id in database
    8. Save checkpoint per scene

- GPU: FLUX.1-schnell requires 16GB VRAM (node-04)
- CogVideoX 5B for video_clip scenes: 24GB VRAM (node-02/03)
- Timeout: 300s per image (FLUX), 1800s per video clip (CogVideoX)
- Retry: 2 retries with 10s→30s backoff (image), 2 retries 30s→90s (video)
- Quality: CLIP score via Phase 4 Quality Scores API
- Fallback: SDXL on node-05 if FLUX fails
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
import structlog
from jinja2 import BaseLoader, Environment, select_autoescape

from celery_app import IVGSBaseTask, celery_app
from clients.flux_client import (
    FluxGenerationParams,
    FluxModel,
)
from clients.cogvideox_client import (
    CogVideoXGenerationParams,
    CogVideoXModel,
)
from clients.vllm_client import VLLMClient
from config import WorkerConfig
from models.task_result import (
    MediaType,
    PipelineStage,
    StageStatus,
)
from providers import ensure_registered
from providers._common import engine_model_id
from shared.providers.binding import ModelBinding
from shared.providers.factory import build_provider, get_binding
from utils.error_handler import (
    save_checkpoint,
    update_job_status,
)
from utils.gpu_utils import acquire_gpu_reservation
from utils.image_validator import ImageValidator
from utils.llm_binding import resolve_text_llm_binding
from utils.quality_reporting import submit_quality_score as _submit_quality_score
from utils.media_converter import (
    ImageConverter,
    asset_storage_path,
    find_duplicate_or_none,
    compute_asset_sha256,
)

logger = structlog.get_logger("ivgs.stage3.images")

jinja_env = Environment(loader=BaseLoader(), autoescape=select_autoescape(default_for_string=False, default=False))


# ---------------------------------------------------------------------------
# Pydantic models for Stage 3
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class SceneImageInput(BaseModel):
    """Input for a single scene image generation."""
    scene_id: str
    scene_index: int
    visual_description: str
    media_type: str = "image"
    narration_text: str = ""
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None


class Stage3Input(BaseModel):
    """Input for Stage 3: Scene Image Generation."""
    job_id: str
    project_id: str
    project_name: str = ""
    project_description: str = ""
    target_audience: str = "general"
    visual_style: str = "professional, clean, modern"
    scenes: List[SceneImageInput] = Field(min_length=1)
    flux_model: str = "flux1-schnell-fp8.safetensors"
    tier: str = "prototype"
    target_width: int = 1920
    target_height: int = 1080
    enable_clip_scoring: bool = True
    enable_dedup: bool = True
    # WP-39. This task serves TWO pipeline stages: STAGE_TASK_MAP maps both
    # image_generation and animation_generation to it. The media join counts one
    # report per dispatched stage and de-duplicates on (job_id, stage), so a run
    # dispatched as the animation stage MUST report as animation_generation or
    # its completion is swallowed as a duplicate of the image run's and the join
    # never closes (job bd99fe37, 2026-08-23). The orchestrator sets this;
    # absent, this is the image stage, as it always was.
    join_stage: Optional[str] = None


class SceneImageResult(BaseModel):
    """Result for a single scene image generation."""
    scene_id: str
    scene_index: int
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    quality_score: float = 0.0
    quality_decision: str = ""
    clip_score: Optional[float] = None
    # WP-44. `clip_score: None` used to mean three different things — not
    # requested, service unreachable, and "scored zero" — and the first e2e run
    # recorded sixteen of them next to a quality_score of 1.0. The status field
    # is what disambiguates: "scored" | "unavailable" | "not_requested". A
    # reader must never have to infer which from a null.
    clip_status: str = "not_requested"
    # Which checks did NOT run, and how much of the scoring weight did. A
    # quality_score computed with checks missing has to say so on its face.
    checks_missing: List[str] = Field(default_factory=list)
    check_coverage: float = 0.0
    quality_score_complete: bool = False
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    errors: List[str] = Field(default_factory=list)
    status: str = "success"


class Stage3Output(BaseModel):
    """Output from Stage 3: Scene Image Generation."""
    job_id: str
    project_id: str
    # WP-39: set from Stage3Input.join_stage at construction. The default is the
    # image stage, so a caller that does not set join_stage behaves exactly as
    # before.
    stage: str = PipelineStage.IMAGE_GENERATION.value
    status: StageStatus = StageStatus.SUCCESS
    scene_results: List[SceneImageResult] = Field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    total_generation_time_seconds: float = 0.0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load Stage 3 system prompt template."""
    config = WorkerConfig()
    path = os.path.join(config.prompt_template_dir, "stage3_system.j2")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Stage 3 system prompt not found: {path}")


async def _generate_image_prompt(
    scene: SceneImageInput,
    project_context: Dict[str, Any],
    vllm_client: VLLMClient,
    prompt_binding: ModelBinding,
    config: WorkerConfig,
) -> Tuple[str, str]:
    """
    Generate a FLUX.1-compatible image prompt from scene description
    using vLLM Mistral 24B.

    Returns (positive_prompt, negative_prompt).
    """
    vllm_config = config.get_vllm_config_for_stage("image_generation")

    system_template = _load_system_prompt()
    system_prompt = jinja_env.from_string(system_template).render(
        project_title=project_context.get("project_name", ""),
        project_description=project_context.get("project_description", ""),
        target_audience=project_context.get("target_audience", "general"),
        visual_style=project_context.get("visual_style", "professional, clean, modern"),
    )

    user_prompt = (
        f"Generate an image prompt for this educational video scene:\n\n"
        f"Scene {scene.scene_index + 1}: {scene.scene_title or 'Untitled'}\n"
        f"Visual Description: {scene.visual_description}\n"
        f"Narration Context: {scene.narration_text[:500]}\n"
        f"Duration: {scene.duration_seconds}s\n"
    )

    # IVGS-0.2: the prompt writer runs on the AD-01 binding, not the env
    # profile. Same pattern as Stage 2.
    response = await vllm_client.chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=engine_model_id(prompt_binding),
        base_url=prompt_binding.endpoint,
        max_tokens=512,
        temperature=0.7,
        timeout=vllm_config["timeout"],
    )

    content = response.content.strip()

    # Parse positive and negative prompts
    positive_prompt = content
    negative_prompt = "blurry, low quality, watermark, text, distorted, ugly, dark, grainy"

    if "NEGATIVE:" in content:
        parts = content.split("NEGATIVE:", 1)
        positive_prompt = parts[0].strip()
        negative_prompt = parts[1].strip()

    return positive_prompt, negative_prompt


async def _upload_to_seaweedfs(
    image_data: bytes,
    project_id: str,
    scene_id: str,
    config: WorkerConfig,
    metadata: Optional[Dict[str, Any]] = None,
    generation_params_hash: str = "",
) -> Tuple[str, str]:
    """
    Upload image to SeaweedFS and register asset in database.

    Returns (asset_id, seaweedfs_path).

    WP-45 Task 1: the form fields are the ones the route now declares. Three of
    the old ones — ``storage_path``, ``sha256``, ``file_size`` — were names the
    route never had, so FastAPI dropped them without complaint. ``content_hash``
    is verified server-side against the bytes, so sending it is a checksum on
    the transfer rather than a value the server takes on trust.
    """
    seaweedfs_path = f"/ivgs/images/{project_id}/scenes/{scene_id}/image.png"

    form: Dict[str, str] = {
        "asset_type": "image",
        "scene_id": scene_id,
        "content_hash": compute_asset_sha256(image_data),
    }
    if generation_params_hash:
        form["generation_params_hash"] = generation_params_hash
    if metadata:
        form["metadata"] = json.dumps(metadata)

    async with httpx.AsyncClient(
        timeout=60.0,
        headers={
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        # Upload to SeaweedFS via API
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets/upload",
            files={
                "file": ("image.png", image_data, "image/png"),
            },
            data=form,
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"SeaweedFS upload failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )

        data = resp.json()
        return (
            data.get("asset_id", data.get("id", "")),
            data.get("seaweedfs_path") or seaweedfs_path,
        )


def _quality_fields(validation: Any) -> Dict[str, Any]:
    """The quality half of a SceneImageResult, from one validation result.

    WP-44. Three call sites used to copy `quality_score` / `quality_decision` /
    `clip_score` by hand and none of them carried the fact that checks had been
    skipped. One helper, so a field added to the validator cannot be forgotten
    by two of three constructors.
    """
    return {
        "quality_score": validation.quality_score,
        "quality_decision": validation.decision.value,
        "clip_score": validation.clip_score,
        "clip_status": validation.clip_status,
        "checks_missing": list(validation.checks_missing),
        "check_coverage": validation.check_coverage,
        "quality_score_complete": validation.quality_score_complete,
    }


# ---------------------------------------------------------------------------
# Per-scene processing
# ---------------------------------------------------------------------------

async def _close_provider(provider: Any) -> None:
    """Close a per-scene provider's underlying HTTP client if it exposes one."""
    close = getattr(provider, "close", None)
    if close is not None:
        await close()


async def _process_single_scene(
    scene: SceneImageInput,
    task_input: Stage3Input,
    vllm_client: VLLMClient,
    prompt_binding: ModelBinding,
    image_validator: ImageValidator,
    config: WorkerConfig,
    *,
    project_id: str,
    tier: str,
) -> SceneImageResult:
    """Process a single scene: prompt gen → image gen → validate → upload."""
    start_time = time.monotonic()

    log = logger.bind(
        scene_id=scene.scene_id,
        scene_index=scene.scene_index,
        media_type=scene.media_type,
    )

    try:
        # 1. Generate image prompt via vLLM
        log.info("generating_image_prompt")
        positive_prompt, negative_prompt = await _generate_image_prompt(
            scene=scene,
            project_context={
                "project_name": task_input.project_name,
                "project_description": task_input.project_description,
                "target_audience": task_input.target_audience,
                "visual_style": task_input.visual_style,
            },
            vllm_client=vllm_client,
            prompt_binding=prompt_binding,
            config=config,
        )

        # 2. Generate image based on media type
        image_data: bytes
        model_used: str

        if scene.media_type == MediaType.VIDEO_CLIP.value:
            # ARCH-1: scene-scoped video-model selection.
            log.info("generating_video_keyframe")
            vid_binding = await get_binding(
                "video_generation",
                project_id=UUID(project_id),
                tier=tier,
                scene_id=UUID(scene.scene_id),
            )
            log.info("model_bound", binding=vid_binding.describe())
            params = CogVideoXGenerationParams(
                prompt=positive_prompt,
                model=CogVideoXModel(engine_model_id(vid_binding)),
            )
            cogvideox_client = build_provider(vid_binding)
            try:
                keyframe = await cogvideox_client.generate_keyframe(params)
            finally:
                await _close_provider(cogvideox_client)
            if keyframe:
                image_data = keyframe
                model_used = vid_binding.name
            else:
                # Fallback to a still image — resolve the image selection lazily
                # (a video-only project may carry no image default).
                log.warning("cogvideox_keyframe_failed_using_flux_fallback")
                img_binding = await get_binding(
                    "image_generation",
                    project_id=UUID(project_id),
                    tier=tier,
                    scene_id=UUID(scene.scene_id),
                )
                flux_params = FluxGenerationParams(
                    prompt=positive_prompt,
                    negative_prompt=negative_prompt,
                    model=FluxModel(engine_model_id(img_binding)),
                )
                flux_client = build_provider(img_binding)
                try:
                    flux_result = await flux_client.generate_image(flux_params)
                finally:
                    await _close_provider(flux_client)
                image_data = flux_result.image_data
                model_used = img_binding.name
        else:
            # ARCH-1: scene-scoped image-model selection.
            log.info("generating_scene_image")
            img_binding = await get_binding(
                "image_generation",
                project_id=UUID(project_id),
                tier=tier,
                scene_id=UUID(scene.scene_id),
            )
            log.info("model_bound", binding=img_binding.describe())
            flux_params = FluxGenerationParams(
                prompt=positive_prompt,
                negative_prompt=negative_prompt,
                model=FluxModel(engine_model_id(img_binding)),
            )
            flux_client = build_provider(img_binding)
            try:
                flux_result = await flux_client.generate_image(flux_params)
            finally:
                await _close_provider(flux_client)
            image_data = flux_result.image_data
            model_used = img_binding.name

        # 3. Upscale to 1920×1080
        log.info("upscaling_image")
        conversion = ImageConverter.resize_to_target(
            image_data=image_data,
            target_width=task_input.target_width,
            target_height=task_input.target_height,
            maintain_aspect=True,
            output_format="PNG",
        )
        final_image = conversion.output_data

        # 4. Validate image quality
        log.info("validating_image")
        clip_api_url = (
            f"{config.pipeline_api.base_url}/api/v1/clip"
            if task_input.enable_clip_scoring else None
        )
        validator = ImageValidator(
            clip_api_url=clip_api_url,
            # The scoring route is service-token authenticated like every other
            # worker->API route. Without this the call is a 403 and CLIP is
            # recorded "unavailable" — correct, and worthless.
            clip_auth_token=config.pipeline_api.service_token,
        )
        validation = validator.validate(
            image_data=final_image,
            prompt=positive_prompt,
            expected_width=task_input.target_width,
            expected_height=task_input.target_height,
        )

        if not validation.is_valid:
            log.warning(
                "image_validation_failed",
                errors=validation.errors,
                decision=validation.decision.value,
            )
            return SceneImageResult(
                scene_id=scene.scene_id,
                scene_index=scene.scene_index,
                model_used=model_used,
                generation_time_seconds=round(time.monotonic() - start_time, 3),
                errors=validation.errors,
                status="failed",
                **_quality_fields(validation),
            )

        # 5. SHA-256 dedup check
        sha256_hash = compute_asset_sha256(final_image)
        was_deduplicated = False

        if task_input.enable_dedup:
            # WP-45: the content hash of bytes that now exist. A hit saves the
            # upload and the duplicate row; the GPU time is already spent.
            existing = find_duplicate_or_none(
                sha256_hash=sha256_hash,
                api_base_url=config.pipeline_api.full_base_url,
                service_token=config.pipeline_api.service_token,
                hash_kind="content",
                project_id=task_input.project_id,
            )
            if existing:
                log.info(
                    "image_deduplicated",
                    existing_asset_id=existing.get("id"),
                )
                was_deduplicated = True
                asset_id = existing.get("id", "")
                seaweedfs_path = asset_storage_path(existing)

                return SceneImageResult(
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    asset_id=asset_id,
                    seaweedfs_path=seaweedfs_path,
                    sha256_hash=sha256_hash,
                    width=validation.actual_width,
                    height=validation.actual_height,
                    file_size_bytes=len(final_image),
                    model_used=model_used,
                    generation_time_seconds=round(time.monotonic() - start_time, 3),
                    was_deduplicated=True,
                    status="success",
                    **_quality_fields(validation),
                )

        # 6. Upload to SeaweedFS
        log.info("uploading_to_seaweedfs")
        asset_id, seaweedfs_path = await _upload_to_seaweedfs(
            image_data=final_image,
            project_id=task_input.project_id,
            scene_id=scene.scene_id,
            config=config,
            # WP-45 Task 1: per-asset generation provenance. Which engine, which
            # model, which prompt, at what size — the facts that let anyone
            # reconstruct how this frame was made once the worker log has rotated.
            metadata={
                "media_type": "image",
                "stage": PipelineStage.IMAGE_GENERATION.value,
                "engine": "comfyui",
                "model": model_used,
                "prompt": positive_prompt[:2000],
                "width": validation.actual_width,
                "height": validation.actual_height,
                "requested_width": task_input.target_width,
                "requested_height": task_input.target_height,
                "tier": getattr(task_input, "tier", "") or "",
                "job_id": task_input.job_id,
                "content_sha256": sha256_hash,
                "generation_time_seconds": round(time.monotonic() - start_time, 3),
            },
        )

        # 8. Submit quality score.
        # WP-44: unconditional. It used to be gated on `enable_clip_scoring`, so
        # turning CLIP off also turned off the whole quality record — the gate's
        # verdict vanished along with one of its metrics. The verdict is worth
        # recording whether or not CLIP contributed to it, and the details now
        # say which checks ran.
        details = validation.scoring_details()
        details["prompt_used"] = positive_prompt[:200]
        await _submit_quality_score(
            asset_id=asset_id,
            quality_score=validation.quality_score,
            quality_decision=validation.decision.value,
            scoring_details=details,
            config=config,
            job_id=task_input.job_id,
        )

        elapsed = round(time.monotonic() - start_time, 3)
        log.info(
            "scene_image_generated",
            asset_id=asset_id,
            quality_score=validation.quality_score,
            elapsed=elapsed,
        )

        return SceneImageResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            asset_id=asset_id,
            seaweedfs_path=seaweedfs_path,
            sha256_hash=sha256_hash,
            width=validation.actual_width,
            height=validation.actual_height,
            file_size_bytes=len(final_image),
            model_used=model_used,
            generation_time_seconds=elapsed,
            was_deduplicated=was_deduplicated,
            status="success",
            **_quality_fields(validation),
        )

    except Exception as e:
        elapsed = round(time.monotonic() - start_time, 3)
        log.error("scene_image_generation_failed", error=str(e))
        return SceneImageResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            generation_time_seconds=elapsed,
            errors=[str(e)],
            status="failed",
        )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.stage3_images.generate_scene_images_task",
    max_retries=2,
    default_retry_delay=10,
    soft_time_limit=1800,
    time_limit=2100,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_scene_images_task(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Stage 3 Celery task: Generate images for all storyboard scenes.

    Dispatched by the pipeline orchestrator after Stage 2 completion.
    Processes scenes sequentially (one GPU job at a time) with
    checkpoint saving after each scene.
    """
    start_time = time.monotonic()
    task_input = Stage3Input(**task_input_dict)
    config = WorkerConfig()

    # WP-39: the stage label this run reports under. image_generation unless the
    # orchestrator dispatched us as the animation stage.
    join_stage = task_input.join_stage or PipelineStage.IMAGE_GENERATION.value

    log = self.structured_logger.bind(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        total_scenes=len(task_input.scenes),
        join_stage=join_stage,
    )
    log.info("stage3_starting")

    # Update job status
    update_job_status(task_input.job_id, "running")

    # ARCH-1: register engine builders once for this worker process.
    ensure_registered()

    # GPU reservation is sized from a representative (project-level) image
    # selection below, on the same event loop that runs the scenes.
    reservation_id = None

    # Idempotency check
    if config.enable_idempotency_check:
        _params_hash = self.compute_idempotency_hash({  # noqa: F841
            "stage": "image_generation",
            "project_id": task_input.project_id,
            "scenes": [s.scene_id for s in task_input.scenes],
            "flux_model": task_input.flux_model,
        })
        # TODO: Check for existing completed result with same hash

    # Process scenes
    scene_results: List[SceneImageResult] = []
    successful = 0
    failed = 0
    deduplicated = 0

    loop = asyncio.new_event_loop()

    try:
        # GPU reservation — representative (project-level) image selection,
        # resolved on this loop (mixing loops would break the async engine).
        if config.enable_gpu_reservation:
            # Bound before the try: get_binding is inside it, so the except block
            # could otherwise reference an unassigned name and turn a fail-open
            # into a NameError.
            rep_binding = None
            try:
                rep_binding = loop.run_until_complete(
                    get_binding(
                        "image_generation",
                        project_id=UUID(task_input.project_id),
                        tier=task_input.tier,
                    )
                )
                reservation = acquire_gpu_reservation(
                    job_id=task_input.job_id,
                    model_name=rep_binding.name,
                    vram_requirement_mb=rep_binding.vram_requirement_mb or 16384,
                    estimated_duration_s=len(task_input.scenes) * 60,
                )
                reservation_id = reservation.get("reservation_id")
                self._gpu_reservation_id = reservation_id
            except Exception as gpu_err:
                # FAIL-OPEN, deliberately and for now - see AD-05 O-3 / P2.6.
                # acquire RAISES (gpu_utils.py:202); the stage proceeds unreserved.
                log.warning(
                    "gpu_reservation_unavailable",
                    stage=PipelineStage.IMAGE_GENERATION.value,
                    model=getattr(rep_binding, "name", "unknown"),
                    vram_mb=getattr(rep_binding, "vram_requirement_mb", None) or 16384,
                    error_type=type(gpu_err).__name__,
                    error=str(gpu_err),
                    fail_open=True,
                )

        # Prompt-generation LLM is constructed once; image/video providers are
        # resolved per scene inside _process_single_scene (ARCH-1 scene scope).
        vllm_client = VLLMClient(config.vllm)
        # IVGS-0.2: the prompt writer is a chat-LLM call and needs a chat-LLM
        # binding. The image binding is ComfyUI and cannot serve one, so the
        # writer borrows the storyboard-generation model — the stage whose work
        # (scene description -> creative visual text) it most resembles.
        prompt_binding = loop.run_until_complete(
            resolve_text_llm_binding(
                "storyboard_generation",
                project_id=task_input.project_id,
                tier=task_input.tier,
                purpose="Stage 3 image-prompt writer",
            )
        )
        image_validator = ImageValidator()

        for scene in task_input.scenes:
            result = loop.run_until_complete(
                _process_single_scene(
                    scene=scene,
                    task_input=task_input,
                    vllm_client=vllm_client,
                    prompt_binding=prompt_binding,
                    image_validator=image_validator,
                    config=config,
                    project_id=task_input.project_id,
                    tier=task_input.tier,
                )
            )

            scene_results.append(result)

            if result.status == "success":
                successful += 1
                if result.was_deduplicated:
                    deduplicated += 1
            else:
                failed += 1

            # Checkpoint after each scene
            if config.enable_checkpoint_saving:
                save_checkpoint(
                    job_id=task_input.job_id,
                    stage_name=PipelineStage.IMAGE_GENERATION.value,
                    stage_index=3,
                    status="running",
                    checkpoint_data={
                        "completed_scenes": [
                            r.scene_id for r in scene_results if r.status == "success"
                        ],
                        "failed_scenes": [
                            r.scene_id for r in scene_results if r.status == "failed"
                        ],
                        "total_processed": len(scene_results),
                    },
                )

            log.info(
                "scene_processed",
                scene_id=scene.scene_id,
                status=result.status,
                progress=f"{len(scene_results)}/{len(task_input.scenes)}",
            )

        # Cleanup clients
        loop.run_until_complete(vllm_client.close())

    except Exception as e:
        log.error("stage3_processing_error", error=str(e))
        raise self.retry(exc=e) if self.request.retries < self.max_retries else None
    finally:
        loop.close()

    # Build output
    total_time = round(time.monotonic() - start_time, 3)
    overall_status = StageStatus.SUCCESS if failed == 0 else StageStatus.FAILED

    output = Stage3Output(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        stage=join_stage,
        status=overall_status,
        scene_results=scene_results,
        total_scenes=len(task_input.scenes),
        successful_count=successful,
        failed_count=failed,
        deduplicated_count=deduplicated,
        total_generation_time_seconds=total_time,
        completed_at=datetime.now(timezone.utc),
    )

    # Final checkpoint
    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=task_input.job_id,
            # WP-39: checkpoints are upserted on (job_id, stage_name), so the
            # animation run writing under image_generation overwrote the image
            # run's row and one of the two stages had no checkpoint at all.
            stage_name=join_stage,
            stage_index=3,
            status=overall_status.value,
            checkpoint_data={
                "successful_count": successful,
                "failed_count": failed,
                "deduplicated_count": deduplicated,
                "total_generation_time": total_time,
            },
        )

    log.info(
        "stage3_completed",
        status=overall_status.value,
        successful=successful,
        failed=failed,
        deduplicated=deduplicated,
        total_time=total_time,
    )

    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )
    return output_dict
