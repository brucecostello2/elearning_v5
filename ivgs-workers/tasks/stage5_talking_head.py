"""
IVGS v5 — Stage 5: Talking Head Generation Task
===================================================

Pipeline Stage 5 (Talking Head Render) per §6.1:
- Trigger: Stage 4 (Voiceover) completed
- Input: Scene image (Stage 3) + voiceover audio (Stage 4) + reference clip
- Processing per scene:
    1. Download scene image from SeaweedFS
    2. Download voiceover audio from SeaweedFS
    3. Fetch user-uploaded talking head reference clip
    4. Optionally determine render mode via vLLM
    5. Render lip-synced video via LatentSync (1920×1080, 30fps)
    6. Validate: resolution, codec, duration, alignment score >0.85
    7. SHA-256 dedup check before upload
    8. Store MP4 to SeaweedFS: /ivgs/talking-heads/{project_id}/{scene_id}.mp4
    9. Update scene.talking_head_asset_id
    10. Save checkpoint per scene

- GPU: LatentSync requires 16GB VRAM (node-04)
- Timeout: 600s per scene
- Retry: 2 retries with 30s→90s backoff
- Fallback: SadTalker (8GB VRAM)
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
from jinja2 import BaseLoader, Environment

from celery_app import IVGSBaseTask, celery_app
from clients.latentsync_client import (
    LatentSyncClient,
    LatentSyncError,
    LatentSyncMode,
    LatentSyncParams,
    LatentSyncResult,
)
from clients.vllm_client import VLLMClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from utils.error_handler import save_checkpoint, update_job_status
from utils.gpu_utils import acquire_gpu_reservation, release_gpu_reservation
from utils.media_converter import (
    VideoConverter,
    check_duplicate_asset,
    compute_asset_sha256,
)
from utils.video_validator import VideoQualityDecision, VideoValidator

logger = structlog.get_logger("ivgs.stage5.talking_head")

jinja_env = Environment(loader=BaseLoader(), autoescape=False)


# ---------------------------------------------------------------------------
# Pydantic models for Stage 5
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class SceneTalkingHeadInput(BaseModel):
    """Input for a single scene talking head generation."""
    scene_id: str
    scene_index: int
    image_asset_id: str
    audio_asset_id: str
    visual_description: str = ""
    narration_duration_seconds: float = 10.0
    scene_title: Optional[str] = None
    scene_type: str = "narration"
    render_mode: Optional[str] = None  # Override auto-detection


class Stage5Input(BaseModel):
    """Input for Stage 5: Talking Head Generation."""
    job_id: str
    project_id: str
    project_name: str = ""
    scenes: List[SceneTalkingHeadInput] = Field(min_length=1)
    reference_clip_asset_id: str
    output_width: int = 1920
    output_height: int = 1080
    output_fps: int = 30
    auto_detect_mode: bool = True
    default_mode: str = "pip"
    default_pip_position: str = "bottom_right"
    default_pip_scale: float = 0.25
    alignment_threshold: float = 0.85
    enable_dedup: bool = True


class SceneTalkingHeadResult(BaseModel):
    """Result for a single scene talking head generation."""
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
    alignment_score: float = 0.0
    quality_score: float = 0.0
    quality_decision: str = ""
    model_used: str = ""
    render_mode: str = ""
    generation_time_seconds: float = 0.0
    was_deduplicated: bool = False
    errors: List[str] = Field(default_factory=list)
    status: str = "success"


class Stage5Output(BaseModel):
    """Output from Stage 5: Talking Head Generation."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.TALKING_HEAD_RENDER.value
    status: StageStatus = StageStatus.SUCCESS
    scene_results: List[SceneTalkingHeadResult] = Field(default_factory=list)
    total_scenes: int = 0
    successful_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0
    low_alignment_count: int = 0
    total_generation_time_seconds: float = 0.0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _download_asset(
    asset_id: str,
    config: WorkerConfig,
) -> bytes:
    """Download asset data from SeaweedFS via Pipeline API."""
    async with httpx.AsyncClient(
        timeout=120.0,
        headers={
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = await client.get(
            f"{config.pipeline_api.full_base_url}/assets/{asset_id}/download",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Asset download failed (ID={asset_id}): HTTP {resp.status_code}"
            )
        return resp.content


def _load_system_prompt() -> str:
    """Load Stage 5 system prompt template."""
    config = WorkerConfig()
    path = os.path.join(config.prompt_template_dir, "stage5_system.j2")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Stage 5 system prompt not found: {path}")


async def _detect_render_mode(
    scene: SceneTalkingHeadInput,
    vllm_client: VLLMClient,
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Use vLLM to determine optimal LatentSync render mode."""
    vllm_config = config.get_vllm_config_for_stage("image_generation")

    system_template = _load_system_prompt()
    system_prompt = jinja_env.from_string(system_template).render(
        scene_title=scene.scene_title or f"Scene {scene.scene_index + 1}",
        visual_description=scene.visual_description,
        narration_duration=scene.narration_duration_seconds,
        scene_type=scene.scene_type,
    )

    user_prompt = (
        f"Recommend talking head rendering parameters for this scene.\n"
        f"Scene type: {scene.scene_type}\n"
        f"Visual: {scene.visual_description[:300]}"
    )

    try:
        parsed, _ = await vllm_client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=vllm_config["model"],
            base_url=vllm_config["base_url"],
            max_tokens=256,
            temperature=0.3,
            timeout=30,
        )
        return parsed
    except Exception as e:
        logger.warning("render_mode_detection_failed", error=str(e))
        return {
            "mode": "pip",
            "pip_position": "bottom_right",
            "pip_scale": 0.25,
            "face_enhance": True,
            "lip_sync_strength": 1.0,
        }


async def _upload_video_to_seaweedfs(
    video_data: bytes,
    project_id: str,
    scene_id: str,
    config: WorkerConfig,
) -> Tuple[str, str]:
    """Upload talking head video to SeaweedFS."""
    seaweedfs_path = f"/ivgs/talking-heads/{project_id}/{scene_id}.mp4"

    async with httpx.AsyncClient(
        timeout=120.0,
        headers={
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/assets/upload",
            files={
                "file": (f"{scene_id}.mp4", video_data, "video/mp4"),
            },
            data={
                "project_id": project_id,
                "asset_type": "talking_head",
                "storage_path": seaweedfs_path,
                "sha256": compute_asset_sha256(video_data),
                "file_size": str(len(video_data)),
            },
        )

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Video upload failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )

        data = resp.json()
        return data.get("asset_id", data.get("id", "")), seaweedfs_path


async def _update_scene_talking_head(
    project_id: str,
    scene_id: str,
    asset_id: str,
    config: WorkerConfig,
) -> None:
    """Update scene record with talking head asset_id."""
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = await client.patch(
            f"{config.pipeline_api.full_base_url}/projects/{project_id}/scenes/{scene_id}",
            json={"talking_head_asset_id": asset_id},
        )
        if resp.status_code != 200:
            logger.warning(
                "scene_talking_head_update_failed",
                scene_id=scene_id,
                status_code=resp.status_code,
            )


# ---------------------------------------------------------------------------
# Per-scene processing
# ---------------------------------------------------------------------------

async def _process_single_talking_head(
    scene: SceneTalkingHeadInput,
    task_input: Stage5Input,
    reference_clip_data: bytes,
    latentsync_client: LatentSyncClient,
    vllm_client: Optional[VLLMClient],
    video_validator: VideoValidator,
    video_converter: VideoConverter,
    config: WorkerConfig,
) -> SceneTalkingHeadResult:
    """Process a single scene: download assets → render → validate → upload."""
    start_time = time.monotonic()

    log = logger.bind(
        scene_id=scene.scene_id,
        scene_index=scene.scene_index,
    )

    try:
        # 1. Download scene image and voiceover audio
        log.info("downloading_scene_assets")
        image_data, audio_data = await asyncio.gather(
            _download_asset(scene.image_asset_id, config),
            _download_asset(scene.audio_asset_id, config),
        )

        # 2. Determine render mode
        render_params: Dict[str, Any] = {
            "mode": task_input.default_mode,
            "pip_position": task_input.default_pip_position,
            "pip_scale": task_input.default_pip_scale,
            "face_enhance": True,
            "lip_sync_strength": 1.0,
        }

        if scene.render_mode:
            render_params["mode"] = scene.render_mode
        elif task_input.auto_detect_mode and vllm_client:
            try:
                detected = await _detect_render_mode(scene, vllm_client, config)
                render_params.update(detected)
            except Exception:
                pass  # Use defaults

        # 3. Render talking head via LatentSync
        log.info("rendering_talking_head", mode=render_params["mode"])

        mode_enum = LatentSyncMode(render_params["mode"])
        latentsync_params = LatentSyncParams(
            audio_data=audio_data,
            reference_video_data=reference_clip_data,
            scene_image_data=image_data,
            mode=mode_enum,
            output_width=task_input.output_width,
            output_height=task_input.output_height,
            output_fps=task_input.output_fps,
            lip_sync_strength=render_params.get("lip_sync_strength", 1.0),
            face_enhance=render_params.get("face_enhance", True),
            pip_scale=render_params.get("pip_scale", 0.25),
            pip_position=render_params.get("pip_position", "bottom_right"),
        )

        render_result = await latentsync_client.render(latentsync_params)
        video_data = render_result.video_data
        alignment_score = render_result.alignment_score

        # 4. Validate video
        log.info("validating_video")
        validation = video_validator.validate_bytes(
            video_data=video_data,
            expected_duration=scene.narration_duration_seconds,
            expected_width=task_input.output_width,
            expected_height=task_input.output_height,
        )

        if not validation.is_valid:
            log.warning(
                "video_validation_failed",
                errors=validation.errors,
            )
            return SceneTalkingHeadResult(
                scene_id=scene.scene_id,
                scene_index=scene.scene_index,
                alignment_score=alignment_score,
                quality_score=validation.quality_score,
                quality_decision=validation.decision.value,
                model_used=render_result.model_used,
                render_mode=render_params["mode"],
                generation_time_seconds=round(time.monotonic() - start_time, 3),
                errors=validation.errors,
                status="failed",
            )

        # Check alignment threshold
        if alignment_score < task_input.alignment_threshold:
            log.warning(
                "low_alignment_score",
                score=alignment_score,
                threshold=task_input.alignment_threshold,
            )
            # Continue with flagged status but still upload

        # 5. SHA-256 dedup
        sha256_hash = compute_asset_sha256(video_data)
        was_deduplicated = False

        if task_input.enable_dedup:
            existing = check_duplicate_asset(
                sha256_hash=sha256_hash,
                api_base_url=config.pipeline_api.full_base_url,
                service_token=config.pipeline_api.service_token,
            )
            if existing:
                log.info("video_deduplicated", existing_asset_id=existing.get("id"))
                was_deduplicated = True
                asset_id = existing.get("id", "")
                seaweedfs_path = existing.get("storage_path", "")

                await _update_scene_talking_head(
                    task_input.project_id, scene.scene_id, asset_id, config
                )

                return SceneTalkingHeadResult(
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    asset_id=asset_id,
                    seaweedfs_path=seaweedfs_path,
                    sha256_hash=sha256_hash,
                    width=task_input.output_width,
                    height=task_input.output_height,
                    fps=task_input.output_fps,
                    duration_seconds=render_result.duration_seconds,
                    file_size_bytes=len(video_data),
                    alignment_score=alignment_score,
                    quality_score=validation.quality_score,
                    quality_decision=validation.decision.value,
                    model_used=render_result.model_used,
                    render_mode=render_params["mode"],
                    generation_time_seconds=round(time.monotonic() - start_time, 3),
                    was_deduplicated=True,
                    status="success",
                )

        # 6. Upload to SeaweedFS
        log.info("uploading_talking_head")
        asset_id, seaweedfs_path = await _upload_video_to_seaweedfs(
            video_data=video_data,
            project_id=task_input.project_id,
            scene_id=scene.scene_id,
            config=config,
        )

        # 7. Update scene record
        await _update_scene_talking_head(
            task_input.project_id, scene.scene_id, asset_id, config
        )

        elapsed = round(time.monotonic() - start_time, 3)
        log.info(
            "talking_head_generated",
            asset_id=asset_id,
            alignment_score=alignment_score,
            mode=render_params["mode"],
            elapsed=elapsed,
        )

        return SceneTalkingHeadResult(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            asset_id=asset_id,
            seaweedfs_path=seaweedfs_path,
            sha256_hash=sha256_hash,
            width=task_input.output_width,
            height=task_input.output_height,
            fps=task_input.output_fps,
            duration_seconds=render_result.duration_seconds,
            file_size_bytes=len(video_data),
            alignment_score=alignment_score,
            quality_score=validation.quality_score,
            quality_decision=validation.decision.value,
            model_used=render_result.model_used,
            render_mode=render_params["mode"],
            generation_time_seconds=elapsed,
            was_deduplicated=was_deduplicated,
            status="success",
        )

    except Exception as e:
        elapsed = round(time.monotonic() - start_time, 3)
        log.error("talking_head_generation_failed", error=str(e))
        return SceneTalkingHeadResult(
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
    name="tasks.stage5_talking_head.generate_talking_head_task",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=3600,
    time_limit=4200,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_talking_head_task(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Stage 5 Celery task: Generate talking head videos for all scenes.

    Dispatched after Stage 4 completion. Downloads reference clip once,
    then processes scenes sequentially with checkpoint saving.
    """
    start_time = time.monotonic()
    task_input = Stage5Input(**task_input_dict)
    config = WorkerConfig()

    log = self.structured_logger.bind(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        total_scenes=len(task_input.scenes),
    )
    log.info("stage5_starting")

    update_job_status(task_input.job_id, "running")

    # GPU reservation for LatentSync (16GB)
    reservation_id = None
    if config.enable_gpu_reservation:
        try:
            reservation = acquire_gpu_reservation(
                job_id=task_input.job_id,
                model_name="latentsync",
                vram_requirement_mb=16384,
                estimated_duration_s=len(task_input.scenes) * 120,
            )
            reservation_id = reservation.get("reservation_id")
            self._gpu_reservation_id = reservation_id
        except Exception as gpu_err:
            log.warning("gpu_reservation_failed", error=str(gpu_err))

    scene_results: List[SceneTalkingHeadResult] = []
    successful = 0
    failed = 0
    deduplicated = 0
    low_alignment = 0

    loop = asyncio.new_event_loop()

    try:
        # Download reference clip once
        log.info("downloading_reference_clip")
        reference_clip_data = loop.run_until_complete(
            _download_asset(task_input.reference_clip_asset_id, config)
        )

        latentsync_client = LatentSyncClient(
            base_url=os.getenv("IVGS_LATENTSYNC_URL", "http://node-04:8300"),
            fallback_url=os.getenv("IVGS_SADTALKER_URL", "http://node-04:8301"),
            timeout=config.timeouts.latentsync_timeout,
            alignment_threshold=task_input.alignment_threshold,
        )
        video_validator = VideoValidator()
        video_converter = VideoConverter()

        vllm_client = None
        if task_input.auto_detect_mode:
            vllm_client = VLLMClient(config.vllm)

        for scene in task_input.scenes:
            result = loop.run_until_complete(
                _process_single_talking_head(
                    scene=scene,
                    task_input=task_input,
                    reference_clip_data=reference_clip_data,
                    latentsync_client=latentsync_client,
                    vllm_client=vllm_client,
                    video_validator=video_validator,
                    video_converter=video_converter,
                    config=config,
                )
            )

            scene_results.append(result)

            if result.status == "success":
                successful += 1
                if result.was_deduplicated:
                    deduplicated += 1
                if result.alignment_score < task_input.alignment_threshold:
                    low_alignment += 1
            else:
                failed += 1

            if config.enable_checkpoint_saving:
                save_checkpoint(
                    job_id=task_input.job_id,
                    stage_name=PipelineStage.TALKING_HEAD_RENDER.value,
                    stage_index=5,
                    status="running",
                    checkpoint_data={
                        "completed_scenes": [
                            r.scene_id for r in scene_results if r.status == "success"
                        ],
                        "total_processed": len(scene_results),
                        "low_alignment_count": low_alignment,
                    },
                )

            log.info(
                "talking_head_processed",
                scene_id=scene.scene_id,
                status=result.status,
                alignment=result.alignment_score,
                progress=f"{len(scene_results)}/{len(task_input.scenes)}",
            )

        loop.run_until_complete(latentsync_client.close())
        if vllm_client:
            loop.run_until_complete(vllm_client.close())

    except Exception as e:
        log.error("stage5_processing_error", error=str(e))
        raise self.retry(exc=e) if self.request.retries < self.max_retries else None
    finally:
        loop.close()

    total_time = round(time.monotonic() - start_time, 3)
    overall_status = StageStatus.SUCCESS if failed == 0 else StageStatus.FAILED

    output = Stage5Output(
        job_id=task_input.job_id,
        project_id=task_input.project_id,
        status=overall_status,
        scene_results=scene_results,
        total_scenes=len(task_input.scenes),
        successful_count=successful,
        failed_count=failed,
        deduplicated_count=deduplicated,
        low_alignment_count=low_alignment,
        total_generation_time_seconds=total_time,
        completed_at=datetime.now(timezone.utc),
    )

    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=task_input.job_id,
            stage_name=PipelineStage.TALKING_HEAD_RENDER.value,
            stage_index=5,
            status=overall_status.value,
            checkpoint_data={
                "successful_count": successful,
                "failed_count": failed,
                "low_alignment_count": low_alignment,
                "total_generation_time": total_time,
            },
        )

    log.info(
        "stage5_completed",
        status=overall_status.value,
        successful=successful,
        failed=failed,
        low_alignment=low_alignment,
        total_time=total_time,
    )

    return output.model_dump(mode="json")
