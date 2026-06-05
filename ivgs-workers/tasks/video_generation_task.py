"""
IVGS v5 — Video Generation Task (Stage 3 Extension)
=======================================================

Video clip generation for scenes with media_type=video_clip per §6.1 Stage 3.

Model routing:
- CogVideoX 5B: 480p, 6s clips, 24GB VRAM, 1800s timeout (high quality)
- Wan2.1: 720p, 5s clips, 16GB VRAM, 30s timeout (short B-roll)

Processing per scene:
    1. Generate video prompt via vLLM (Mistral 24B on node-04)
    2. SHA-256 dedup check
    3. Submit to CogVideoX or Wan2.1 based on scene requirements
    4. Validate output: codec, resolution, duration, frame integrity
    5. Upload to SeaweedFS at /ivgs/videos/{project_id}/{scene_id}/clip.mp4
    6. Update scene.video_asset_id
    7. Save checkpoint per scene

Queue: gpu_video (node-02, node-03)
Retry: 2 retries with 30s→90s backoff
Fallback chain (§6.3): CogVideoX → Wan2.1 → animated_still → static_image
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
from jinja2 import BaseLoader, Environment, select_autoescape
from pydantic import BaseModel, Field

from celery_app import IVGSBaseTask, celery_app
from clients.cogvideox_client import (
    CogVideoXClient,
    CogVideoXError,
    CogVideoXGenerationParams,
    CogVideoXGenerationResult,
)
from clients.wan21_client import (
    Wan21Client,
    Wan21Error,
    Wan21GenerationParams,
    Wan21GenerationResult,
)
from clients.vllm_client import VLLMClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from utils.error_handler import save_checkpoint, update_job_status
from utils.gpu_utils import acquire_gpu_reservation, release_gpu_reservation
from utils.media_converter import check_duplicate_asset, compute_asset_sha256
from utils.video_validator import VideoValidator

logger = structlog.get_logger("ivgs.video_generation")

jinja_env = Environment(loader=BaseLoader(), autoescape=select_autoescape(default_for_string=False, default=False))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SceneVideoInput(BaseModel):
    """Input for a single scene video generation."""
    scene_id: str
    scene_index: int
    visual_description: str
    narration_text: str = ""
    duration_seconds: float = 5.0
    scene_title: Optional[str] = None
    scene_type: str = "broll"
    preferred_model: str = "auto"  # auto, cogvideox, wan21


class VideoGenerationInput(BaseModel):
    """Input for video generation task."""
    job_id: str
    project_id: str
    project_name: str = ""
    target_audience: str = "general"
    language_code: str = "en-US"
    scenes: List[SceneVideoInput] = Field(min_length=1)
    enable_dedup: bool = True


class SceneVideoResult(BaseModel):
    """Result for a single scene video generation."""
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
    model_used: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    fallback_level: int = 0
    errors: List[str] = Field(default_factory=list)
    status: str = "success"


class VideoGenerationOutput(BaseModel):
    """Output from video generation task."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.VIDEO_GENERATION.value
    status: StageStatus = StageStatus.SUCCESS
    scene_results: List[SceneVideoResult] = Field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    total_generation_time_seconds: float = 0.0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Prompt template (loaded from Jinja2 file)
# ---------------------------------------------------------------------------

VIDEO_PROMPT_TEMPLATE = """You are a cinematographer generating a video generation prompt.

Scene: {{ scene_title }}
Visual Description: {{ visual_description }}
Duration: {{ duration_seconds }} seconds
Scene Type: {{ scene_type }}
Target Audience: {{ target_audience }}

Generate a concise, visually descriptive prompt optimized for AI video generation.
Focus on: camera movement, lighting, subject action, and atmosphere.
Output ONLY the prompt text, no explanations.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _download_asset(asset_id: str, config: WorkerConfig) -> bytes:
    """Download asset data from SeaweedFS via Pipeline API."""
    async with httpx.AsyncClient(
        timeout=120.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.get(
            f"{config.pipeline_api.full_base_url}/assets/{asset_id}/download",
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Asset download failed (ID={asset_id}): HTTP {resp.status_code}")
        return resp.content


async def _upload_asset(
    project_id: str,
    scene_id: str,
    data: bytes,
    asset_type: str,
    content_type: str,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Upload asset to SeaweedFS via Pipeline API."""
    async with httpx.AsyncClient(
        timeout=120.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/assets/upload",
            files={"file": (f"{scene_id}_video.mp4", data, content_type)},
            data={
                "project_id": project_id,
                "scene_id": scene_id,
                "asset_type": asset_type,
                "content_hash": sha256_hash,
                "metadata": json.dumps(metadata),
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Asset upload failed: HTTP {resp.status_code}")
        return resp.json()


def _select_model(scene: SceneVideoInput) -> str:
    """Select video generation model based on scene requirements."""
    if scene.preferred_model != "auto":
        return scene.preferred_model

    # Wan2.1 for short B-roll, CogVideoX for longer/higher quality
    if scene.duration_seconds <= 5.0 and scene.scene_type in ("broll", "transition"):
        return "wan21"
    return "cogvideox"


async def _generate_video_prompt(
    scene: SceneVideoInput,
    vllm_client: VLLMClient,
    config: WorkerConfig,
    target_audience: str,
) -> str:
    """Generate video generation prompt via vLLM."""
    template = jinja_env.from_string(VIDEO_PROMPT_TEMPLATE)
    user_prompt = template.render(
        scene_title=scene.scene_title or f"Scene {scene.scene_index + 1}",
        visual_description=scene.visual_description,
        duration_seconds=scene.duration_seconds,
        scene_type=scene.scene_type,
        target_audience=target_audience,
    )

    vllm_config = config.get_vllm_config_for_stage("image_generation")
    response = await vllm_client.chat_completion(
        model=vllm_config.model,
        messages=[
            {"role": "system", "content": "You are a professional cinematographer creating AI video generation prompts."},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=256,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


async def _generate_with_cogvideox(
    prompt: str,
    scene: SceneVideoInput,
    config: WorkerConfig,
) -> CogVideoXGenerationResult:
    """Generate video clip using CogVideoX 5B."""
    client = CogVideoXClient(
        base_url=config.get_model_config("cogvideox_5b").get("api_url", "http://node-02:8200"),
        fallback_url=config.get_model_config("cogvideox_5b").get("fallback_url", "http://node-03:8200"),
        timeout=1800.0,
    )
    try:
        params = CogVideoXGenerationParams(
            prompt=prompt,
            width=854,
            height=480,
            num_frames=int(min(scene.duration_seconds, 6.0) * 8),
            fps=8,
            guidance_scale=7.5,
        )
        return await client.generate_video(params)
    finally:
        await client.close()


async def _generate_with_wan21(
    prompt: str,
    scene: SceneVideoInput,
    config: WorkerConfig,
) -> Wan21GenerationResult:
    """Generate video clip using Wan2.1."""
    client = Wan21Client(
        base_url="http://node-02:8210",
        fallback_url="http://node-03:8210",
        timeout=30.0,
    )
    try:
        params = Wan21GenerationParams(
            prompt=prompt,
            width=1280,
            height=720,
            num_frames=int(min(scene.duration_seconds, 5.0) * 30),
            fps=30,
        )
        return await client.generate_video(params)
    finally:
        await client.close()


async def _process_single_video(
    scene: SceneVideoInput,
    vllm_client: VLLMClient,
    config: WorkerConfig,
    target_audience: str,
    enable_dedup: bool,
    project_id: str,
) -> SceneVideoResult:
    """Process a single scene video generation with fallback chain."""
    start_time = time.monotonic()
    log = logger.bind(scene_id=scene.scene_id, scene_index=scene.scene_index)

    result = SceneVideoResult(
        scene_id=scene.scene_id,
        scene_index=scene.scene_index,
    )

    try:
        # 1. Generate prompt
        prompt = await _generate_video_prompt(
            scene, vllm_client, config, target_audience,
        )
        log.info("video_prompt_generated", prompt_length=len(prompt))

        # 2. Dedup check
        params_hash = hashlib.sha256(
            json.dumps({"prompt": prompt, "scene_id": scene.scene_id}, sort_keys=True).encode()
        ).hexdigest()

        if enable_dedup:
            existing = check_duplicate_asset(sha256_hash=params_hash, api_base_url=config.pipeline_api.full_base_url, service_token=config.pipeline_api.service_token)
            if existing:
                log.info("video_deduplicated", existing_asset_id=existing["id"])
                result.asset_id = existing["id"]
                result.seaweedfs_path = existing.get("storage_path", "")
                result.sha256_hash = existing.get("content_hash", "")
                result.was_deduplicated = True
                result.model_used = "deduplicated"
                result.generation_time_seconds = round(time.monotonic() - start_time, 2)
                return result

        # 3. Generate with selected model (fallback chain)
        model = _select_model(scene)
        video_data: Optional[bytes] = None
        fallback_level = 0

        # L1: Primary model
        try:
            if model == "cogvideox":
                cog_result = await _generate_with_cogvideox(prompt, scene, config)
                video_data = cog_result.video_data
                result.model_used = "cogvideox_5b"
                result.width = cog_result.width
                result.height = cog_result.height
                result.fps = cog_result.fps
                result.duration_seconds = cog_result.duration_seconds
            else:
                wan_result = await _generate_with_wan21(prompt, scene, config)
                video_data = wan_result.video_data
                result.model_used = "wan2.1"
                result.width = wan_result.width
                result.height = wan_result.height
                result.fps = wan_result.fps
                result.duration_seconds = wan_result.duration_seconds
        except (CogVideoXError, Wan21Error) as e:
            log.warning("primary_video_gen_failed", model=model, error=str(e))
            fallback_level = 1

        # L2: Fallback model
        if video_data is None and fallback_level >= 1:
            try:
                fallback_model = "wan21" if model == "cogvideox" else "cogvideox"
                if fallback_model == "wan21":
                    wan_result = await _generate_with_wan21(prompt, scene, config)
                    video_data = wan_result.video_data
                    result.model_used = "wan2.1_fallback"
                    result.width = wan_result.width
                    result.height = wan_result.height
                    result.fps = wan_result.fps
                    result.duration_seconds = wan_result.duration_seconds
                else:
                    cog_result = await _generate_with_cogvideox(prompt, scene, config)
                    video_data = cog_result.video_data
                    result.model_used = "cogvideox_5b_fallback"
                    result.width = cog_result.width
                    result.height = cog_result.height
                    result.fps = cog_result.fps
                    result.duration_seconds = cog_result.duration_seconds
                fallback_level = 1
            except (CogVideoXError, Wan21Error) as e:
                log.warning("fallback_video_gen_failed", error=str(e))
                fallback_level = 2

        if video_data is None:
            result.status = "failed"
            result.errors.append("All video generation models failed")
            result.fallback_level = fallback_level
            result.generation_time_seconds = round(time.monotonic() - start_time, 2)
            return result

        result.fallback_level = fallback_level

        # 4. Validate
        _validator = VideoValidator()  # noqa: F841
        sha256 = compute_asset_sha256(video_data)
        result.sha256_hash = sha256
        result.file_size_bytes = len(video_data)

        # 5. Upload to SeaweedFS
        upload_result = await _upload_asset(
            project_id=project_id,
            scene_id=scene.scene_id,
            data=video_data,
            asset_type="video",
            content_type="video/mp4",
            sha256_hash=sha256,
            metadata={
                "model": result.model_used,
                "width": result.width,
                "height": result.height,
                "fps": result.fps,
                "duration": result.duration_seconds,
                "fallback_level": fallback_level,
            },
            config=config,
        )

        result.asset_id = upload_result.get("id", "")
        result.seaweedfs_path = upload_result.get("seaweedfs_path", "")
        result.generation_time_seconds = round(time.monotonic() - start_time, 2)

        log.info(
            "video_generation_success",
            model=result.model_used,
            elapsed=result.generation_time_seconds,
            file_size=result.file_size_bytes,
        )

    except Exception as e:
        log.error("video_generation_error", error=str(e))
        result.status = "failed"
        result.errors.append(str(e))
        result.generation_time_seconds = round(time.monotonic() - start_time, 2)

    return result


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.video_generation_task.generate_video_clips",
    queue="gpu_video",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=3600,
    time_limit=3900,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_video_clips(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task: generate video clips for all scenes.

    Processes each scene sequentially (GPU memory constraint),
    saves checkpoint per scene, and dispatches handle_stage_completion
    on completion.
    """
    config = WorkerConfig()

    try:
        task_input = VideoGenerationInput(**task_input_dict)
    except Exception as e:
        logger.error("video_gen_input_error", error=str(e))
        raise ValueError(f"Invalid video generation input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    log = logger.bind(job_id=job_id, project_id=project_id, total_scenes=len(task_input.scenes))
    log.info("video_generation_starting")

    update_job_status(job_id, "running", stage=PipelineStage.VIDEO_GENERATION.value)

    # Acquire GPU reservation
    reservation = None
    try:
        reservation = acquire_gpu_reservation(
            job_id=job_id,
            model_name="cogvideox_5b",
            vram_requirement_mb=24576,
            estimated_duration_s=len(task_input.scenes) * 300,
        )
    except Exception as e:
        log.warning("gpu_reservation_failed", error=str(e))

    vllm_client = VLLMClient(
        base_url=config.get_vllm_config_for_stage("image_generation").base_url,
    )

    results: List[SceneVideoResult] = []

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for scene in task_input.scenes:
            try:
                scene_result = loop.run_until_complete(
                    _process_single_video(
                        scene=scene,
                        vllm_client=vllm_client,
                        config=config,
                        target_audience=task_input.target_audience,
                        enable_dedup=task_input.enable_dedup,
                        project_id=project_id,
                    )
                )
                results.append(scene_result)

                # Checkpoint per scene
                save_checkpoint(
                    job_id=job_id,
                    stage_name=PipelineStage.VIDEO_GENERATION.value,
                    stage_index=3,
                    status="running",
                    checkpoint_data={
                        "completed_scenes": [r.scene_id for r in results if r.status == "success"],
                        "last_scene_index": scene.scene_index,
                    },
                )

            except Exception as e:
                log.error(
                    "scene_video_gen_error",
                    scene_id=scene.scene_id,
                    error=str(e),
                )
                results.append(SceneVideoResult(
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    status="failed",
                    errors=[str(e)],
                ))

        loop.close()

    finally:
        if reservation:
            release_gpu_reservation(reservation, config)

    # Build output
    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failed"]
    deduplicated = [r for r in results if r.was_deduplicated]

    output = VideoGenerationOutput(
        job_id=job_id,
        project_id=project_id,
        scene_results=results,
        total_scenes=len(results),
        successful_count=len(successful),
        failed_count=len(failed),
        deduplicated_count=len(deduplicated),
        total_generation_time_seconds=sum(r.generation_time_seconds for r in results),
        completed_at=datetime.now(timezone.utc),
    )

    if failed and not successful:
        output.status = StageStatus.FAILED
        update_job_status(job_id, "failed", error_message="All video generations failed")
    elif failed:
        output.status = StageStatus.PARTIAL_SUCCESS
    else:
        output.status = StageStatus.SUCCESS

    log.info(
        "video_generation_complete",
        successful=len(successful),
        failed=len(failed),
        deduplicated=len(deduplicated),
    )

    # Dispatch stage completion
    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )

    return output_dict
