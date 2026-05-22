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
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog
from jinja2 import BaseLoader, Environment, select_autoescape

from celery_app import IVGSBaseTask, celery_app
from clients.flux_client import (
    FluxClient,
    FluxError,
    FluxGenerationParams,
    FluxGenerationResult,
    FluxModel,
    MODEL_PRESETS,
)
from clients.cogvideox_client import (
    CogVideoXClient,
    CogVideoXError,
    CogVideoXGenerationParams,
)
from clients.vllm_client import VLLMClient, VLLMError
from config import WorkerConfig
from models.task_result import (
    MediaType,
    PipelineStage,
    StageStatus,
    StoryboardScene,
)
from utils.error_handler import (
    classify_exception,
    save_checkpoint,
    update_job_status,
)
from utils.gpu_utils import acquire_gpu_reservation, release_gpu_reservation
from utils.image_validator import ImageQualityDecision, ImageValidator
from utils.media_converter import (
    ImageConverter,
    check_duplicate_asset,
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
    flux_model: str = "flux1-dev-fp8.safetensors"
    target_width: int = 1920
    target_height: int = 1080
    enable_clip_scoring: bool = True
    enable_dedup: bool = True


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
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    errors: List[str] = Field(default_factory=list)
    status: str = "success"


class Stage3Output(BaseModel):
    """Output from Stage 3: Scene Image Generation."""
    job_id: str
    project_id: str
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

    response = await vllm_client.chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=vllm_config["model"],
        base_url=vllm_config["base_url"],
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
) -> Tuple[str, str]:
    """
    Upload image to SeaweedFS and register asset in database.

    Returns (asset_id, seaweedfs_path).
    """
    seaweedfs_path = f"/ivgs/images/{project_id}/scenes/{scene_id}/image.png"

    async with httpx.AsyncClient(
        timeout=60.0,
        headers={
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        # Upload to SeaweedFS via API
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/assets/upload",
            files={
                "file": ("image.png", image_data, "image/png"),
            },
            data={
                "project_id": project_id,
                "asset_type": "image",
                "storage_path": seaweedfs_path,
                "sha256": compute_asset_sha256(image_data),
                "file_size": str(len(image_data)),
            },
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"SeaweedFS upload failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )

        data = resp.json()
        return data.get("asset_id", data.get("id", "")), seaweedfs_path


async def _update_scene_asset(
    project_id: str,
    scene_id: str,
    asset_id: str,
    config: WorkerConfig,
) -> None:
    """Update scene record with generated image asset_id."""
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = await client.patch(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/scenes/{scene_id}",
            json={"image_asset_id": asset_id},
        )
        if resp.status_code != 200:
            logger.warning(
                "scene_asset_update_failed",
                scene_id=scene_id,
                status_code=resp.status_code,
            )


async def _submit_quality_score(
    asset_id: str,
    quality_score: float,
    quality_decision: str,
    scoring_details: Dict[str, Any],
    config: WorkerConfig,
) -> None:
    """Submit quality score to Phase 4 Quality Scores API."""
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        try:
            await client.post(
                f"{config.pipeline_api.full_base_url}/quality-scores",
                json={
                    "asset_id": asset_id,
                    "quality_score": quality_score,
                    "decision": quality_decision,
                    "scoring_details": scoring_details,
                },
            )
        except Exception as e:
            logger.warning("quality_score_submit_failed", error=str(e))


# ---------------------------------------------------------------------------
# Per-scene processing
# ---------------------------------------------------------------------------

async def _process_single_scene(
    scene: SceneImageInput,
    task_input: Stage3Input,
    vllm_client: VLLMClient,
    flux_client: FluxClient,
    cogvideox_client: CogVideoXClient,
    image_validator: ImageValidator,
    config: WorkerConfig,
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
            config=config,
        )

        # 2. Generate image based on media type
        image_data: bytes
        model_used: str

        if scene.media_type == MediaType.VIDEO_CLIP.value:
            # Generate video keyframe via CogVideoX
            log.info("generating_video_keyframe")
            params = CogVideoXGenerationParams(prompt=positive_prompt)
            keyframe = await cogvideox_client.generate_keyframe(params)
            if keyframe:
                image_data = keyframe
                model_used = "cogvideox-5b-keyframe"
            else:
                # Fallback to FLUX image
                log.warning("cogvideox_keyframe_failed_using_flux_fallback")
                flux_params = FluxGenerationParams(
                    prompt=positive_prompt,
                    negative_prompt=negative_prompt,
                    model=FluxModel(task_input.flux_model),
                )
                flux_result = await flux_client.generate_image(flux_params)
                image_data = flux_result.image_data
                model_used = flux_result.model_used
        else:
            # Standard image generation via FLUX
            log.info("generating_scene_image")
            flux_params = FluxGenerationParams(
                prompt=positive_prompt,
                negative_prompt=negative_prompt,
                model=FluxModel(task_input.flux_model),
            )
            flux_result = await flux_client.generate_image(flux_params)
            image_data = flux_result.image_data
            model_used = flux_result.model_used

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
        validator = ImageValidator(clip_api_url=clip_api_url)
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
                quality_score=validation.quality_score,
                quality_decision=validation.decision.value,
                clip_score=validation.clip_score,
                model_used=model_used,
                generation_time_seconds=round(time.monotonic() - start_time, 3),
                errors=validation.errors,
                status="failed",
            )

        # 5. SHA-256 dedup check
        sha256_hash = compute_asset_sha256(final_image)
        was_deduplicated = False

        if task_input.enable_dedup:
            existing = check_duplicate_asset(
                sha256_hash=sha256_hash,
                api_base_url=config.pipeline_api.full_base_url,
                service_token=config.pipeline_api.service_token,
            )
            if existing:
                log.info(
                    "image_deduplicated",
                    existing_asset_id=existing.get("id"),
                )
                was_deduplicated = True
                asset_id = existing.get("id", "")
                seaweedfs_path = existing.get("storage_path", "")

                # Update scene with existing asset
                await _update_scene_asset(
                    task_input.project_id, scene.scene_id, asset_id, config
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
                    quality_score=validation.quality_score,
                    quality_decision=validation.decision.value,
                    clip_score=validation.clip_score,
                    model_used=model_used,
                    generation_time_seconds=round(time.monotonic() - start_time, 3),
                    was_deduplicated=True,
                    status="success",
                )

        # 6. Upload to SeaweedFS
        log.info("uploading_to_seaweedfs")
        asset_id, seaweedfs_path = await _upload_to_seaweedfs(
            image_data=final_image,
            project_id=task_input.project_id,
            scene_id=scene.scene_id,
            config=config,
        )

        # 7. Update scene record
        await _update_scene_asset(
            task_input.project_id, scene.scene_id, asset_id, config
        )

        # 8. Submit quality score
        if task_input.enable_clip_scoring:
            await _submit_quality_score(
                asset_id=asset_id,
                quality_score=validation.quality_score,
                quality_decision=validation.decision.value,
                scoring_details={
                    "clip_score": validation.clip_score,
                    "resolution_ok": validation.resolution_ok,
                    "format_ok": validation.format_ok,
                    "corruption_ok": validation.corruption_ok,
                    "prompt_used": positive_prompt[:200],
                },
                config=config,
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
            quality_score=validation.quality_score,
            quality_decision=validation.decision.value,
            clip_score=validation.clip_score,
            model_used=model_used,
            generation_time_seconds=elapsed,
            was_deduplicated=was_deduplicated,
            status="success",
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

    log = self.structured_logger.bind(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        total_scenes=len(task_input.scenes),
    )
    log.info("stage3_starting")

    # Update job status
    update_job_status(task_input.job_id, "running")

    # GPU reservation for FLUX.1 (16GB for schnell)
    reservation_id = None
    if config.enable_gpu_reservation:
        try:
            reservation = acquire_gpu_reservation(
                job_id=task_input.job_id,
                model_name="flux1-schnell",
                vram_requirement_mb=16384,
                estimated_duration_s=len(task_input.scenes) * 60,
            )
            reservation_id = reservation.get("reservation_id")
            self._gpu_reservation_id = reservation_id
        except Exception as gpu_err:
            log.warning("gpu_reservation_failed", error=str(gpu_err))

    # Idempotency check
    if config.enable_idempotency_check:
        params_hash = self.compute_idempotency_hash({
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
        # Initialize clients
        flux_client = FluxClient(
            base_url=os.getenv("IVGS_COMFYUI_URL", "http://node-04:8188"),
            fallback_url=os.getenv("IVGS_COMFYUI_FALLBACK_URL", "http://node-05:8188"),
            timeout=config.timeouts.comfyui_timeout,
        )
        cogvideox_client = CogVideoXClient(
            base_url=os.getenv("IVGS_COGVIDEOX_URL", "http://node-02:8200"),
            fallback_url=os.getenv("IVGS_COGVIDEOX_FALLBACK_URL", "http://node-03:8200"),
            timeout=config.timeouts.cogvideox_timeout,
        )
        vllm_client = VLLMClient(config.vllm)
        image_validator = ImageValidator()

        for scene in task_input.scenes:
            result = loop.run_until_complete(
                _process_single_scene(
                    scene=scene,
                    task_input=task_input,
                    vllm_client=vllm_client,
                    flux_client=flux_client,
                    cogvideox_client=cogvideox_client,
                    image_validator=image_validator,
                    config=config,
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
        loop.run_until_complete(flux_client.close())
        loop.run_until_complete(cogvideox_client.close())
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
            stage_name=PipelineStage.IMAGE_GENERATION.value,
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

    return output.model_dump(mode="json")
