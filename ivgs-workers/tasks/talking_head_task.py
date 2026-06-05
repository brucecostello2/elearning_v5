"""
IVGS v5 — Stage 6: Talking Head Rendering Task
===================================================

Pipeline Stage 6 per §6.1:
- Input: User-uploaded talking head reference clip + full concatenated audio track
- Primary: LatentSync on node-04 (lip-sync score threshold >0.85)
- Fallback: SadTalker on node-04
- Output: Full lip-synced talking head video at /ivgs/talking-heads/{project_id}/{language_code}.mp4
- Timeout: 600 seconds
- Retry: 2 retries with 30s→90s backoff

Processing:
    1. Download user-uploaded reference clip from SeaweedFS
    2. Concatenate all scene audio files into a single audio track
    3. Acquire GPU reservation (LatentSync: 16GB VRAM)
    4. Render lip-synced video via LatentSync
    5. Validate: alignment score >0.85 (§11.1)
    6. On LatentSync failure/low score: fallback to SadTalker (8GB VRAM)
    7. Run corruption detection (§11.2)
    8. Upload to SeaweedFS
    9. Update project talking_head_asset_id
    10. Save checkpoint and dispatch stage completion
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog
from pydantic import BaseModel, Field

from celery_app import IVGSBaseTask, celery_app
from clients.latentsync_client import (
    LatentSyncClient,
    LatentSyncError,
    LatentSyncMode,
    LatentSyncParams,
    LatentSyncResult,
)
from clients.ffmpeg_client import FFmpegClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from utils.error_handler import save_checkpoint, update_job_status
from utils.gpu_utils import acquire_gpu_reservation, release_gpu_reservation
from utils.media_converter import compute_asset_sha256
from validators.lipsync_validator import LipsyncValidator
from validators.corruption_detector import CorruptionDetector

logger = structlog.get_logger("ivgs.stage6.talking_head")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SceneAudioRef(BaseModel):
    """Reference to a scene audio asset for concatenation."""
    scene_id: str
    scene_index: int
    audio_asset_id: str
    duration_seconds: float


class Stage6Input(BaseModel):
    """Input for Stage 6: Talking Head Rendering."""
    job_id: str
    project_id: str
    project_name: str = ""
    language_code: str = "en-US"
    reference_clip_asset_id: str
    scene_audio_refs: List[SceneAudioRef] = Field(min_length=1)
    output_width: int = 1920
    output_height: int = 1080
    output_fps: int = 30
    alignment_threshold: float = 0.85
    latentsync_mode: str = "full_screen"
    pip_position: str = "bottom_right"
    pip_scale: float = 0.25
    enable_face_enhance: bool = True
    lip_sync_strength: float = 1.0


class Stage6Output(BaseModel):
    """Output from Stage 6: Talking Head Rendering."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.TALKING_HEAD_RENDER.value
    status: StageStatus = StageStatus.SUCCESS
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    alignment_score: float = 0.0
    model_used: str = ""
    render_mode: str = ""
    generation_time_seconds: float = 0.0
    corruption_check_passed: bool = False
    fallback_used: bool = False
    errors: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


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
    language_code: str,
    data: bytes,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Upload talking head video to SeaweedFS."""
    async with httpx.AsyncClient(
        timeout=180.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/assets",
            files={
                "file": (
                    f"talking_head_{language_code}.mp4",
                    data,
                    "video/mp4",
                ),
            },
            data={
                "project_id": project_id,
                "asset_type": "talking_head",
                "content_hash": sha256_hash,
                "metadata": json.dumps(metadata),
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Asset upload failed: HTTP {resp.status_code}")
        return resp.json()


async def _concatenate_scene_audio(
    scene_audio_refs: List[SceneAudioRef],
    config: WorkerConfig,
    temp_dir: str,
) -> str:
    """Download all scene audio files and concatenate into a single track."""
    ffmpeg = FFmpegClient(temp_dir=temp_dir)
    audio_paths: List[str] = []

    for ref in sorted(scene_audio_refs, key=lambda r: r.scene_index):
        audio_data = await _download_asset(ref.audio_asset_id, config)
        audio_path = os.path.join(temp_dir, f"scene_{ref.scene_index:04d}.wav")
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        audio_paths.append(audio_path)

    # Concatenate all audio into a single WAV
    concat_path = os.path.join(temp_dir, "full_audio.wav")
    ffmpeg.concat_audio(audio_paths, concat_path)

    return concat_path


async def _render_with_latentsync(
    reference_clip_path: str,
    audio_path: str,
    task_input: Stage6Input,
    config: WorkerConfig,
    temp_dir: str,
) -> LatentSyncResult:
    """Render lip-synced video using LatentSync."""
    latentsync_config = config.get_model_config("latentsync")
    client = LatentSyncClient(
        base_url=latentsync_config.get("api_url", "http://node-04:8300"),
        timeout=600.0,
    )

    try:
        mode = LatentSyncMode(task_input.latentsync_mode)
    except ValueError:
        mode = LatentSyncMode.FULL_SCREEN

    params = LatentSyncParams(
        reference_video_path=reference_clip_path,
        audio_path=audio_path,
        output_width=task_input.output_width,
        output_height=task_input.output_height,
        output_fps=task_input.output_fps,
        mode=mode,
        face_enhance=task_input.enable_face_enhance,
        lip_sync_strength=task_input.lip_sync_strength,
        pip_position=task_input.pip_position,
        pip_scale=task_input.pip_scale,
    )

    try:
        return await client.render(params)
    finally:
        await client.close()


async def _render_with_sadtalker(
    reference_clip_path: str,
    audio_path: str,
    task_input: Stage6Input,
    config: WorkerConfig,
    temp_dir: str,
) -> bytes:
    """Render lip-synced video using SadTalker (fallback)."""
    sadtalker_config = config.get_model_config("sadtalker")
    base_url = sadtalker_config.get("api_url", "http://node-04:8301")

    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(reference_clip_path, "rb") as ref_f, open(audio_path, "rb") as audio_f:
            resp = await client.post(
                f"{base_url}/generate",
                files={
                    "reference_video": ("reference.mp4", ref_f, "video/mp4"),
                    "audio": ("audio.wav", audio_f, "audio/wav"),
                },
                data={
                    "width": str(task_input.output_width),
                    "height": str(task_input.output_height),
                    "fps": str(task_input.output_fps),
                },
                timeout=300.0,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"SadTalker render failed: HTTP {resp.status_code}")

        return resp.content


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.talking_head_task.render_talking_head",
    queue="gpu_talking_head",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
    reject_on_worker_lost=True,
)
def render_talking_head(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task: render full talking head video.

    1. Download reference clip and concatenate audio
    2. Render with LatentSync (primary)
    3. Validate alignment score
    4. Fallback to SadTalker if needed
    5. Run corruption detection
    6. Upload result
    """
    config = WorkerConfig()

    try:
        task_input = Stage6Input(**task_input_dict)
    except Exception as e:
        logger.error("stage6_input_error", error=str(e))
        raise ValueError(f"Invalid Stage 6 input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    log = logger.bind(job_id=job_id, project_id=project_id)
    log.info("stage6_talking_head_starting")

    update_job_status(job_id, "running", stage=PipelineStage.TALKING_HEAD_RENDER.value)

    output = Stage6Output(job_id=job_id, project_id=project_id)

    temp_dir = tempfile.mkdtemp(prefix="ivgs_stage6_")
    reservation = None

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Download reference clip
        reference_data = loop.run_until_complete(
            _download_asset(task_input.reference_clip_asset_id, config)
        )
        reference_path = os.path.join(temp_dir, "reference.mp4")
        with open(reference_path, "wb") as f:
            f.write(reference_data)

        # 2. Concatenate all scene audio
        audio_path = loop.run_until_complete(
            _concatenate_scene_audio(
                task_input.scene_audio_refs, config, temp_dir,
            )
        )

        # 3. Acquire GPU reservation
        try:
            reservation = acquire_gpu_reservation(
                job_id=job_id,
                model_name="latentsync",
                vram_mb=16384,
                config=config,
            )
        except Exception as e:
            log.warning("gpu_reservation_failed", error=str(e))

        start_time = time.monotonic()
        video_data: Optional[bytes] = None
        alignment_score = 0.0
        model_used = ""
        fallback_used = False

        # 4. Render with LatentSync (primary)
        try:
            ls_result = loop.run_until_complete(
                _render_with_latentsync(
                    reference_path, audio_path, task_input, config, temp_dir,
                )
            )
            video_data = ls_result.video_data
            alignment_score = ls_result.alignment_score
            model_used = "latentsync"
            output.width = ls_result.width
            output.height = ls_result.height
            output.fps = ls_result.fps
            output.duration_seconds = ls_result.duration_seconds

            log.info(
                "latentsync_render_complete",
                alignment_score=alignment_score,
                duration=ls_result.duration_seconds,
            )

            # 5. Validate alignment score
            if alignment_score < task_input.alignment_threshold:
                log.warning(
                    "latentsync_low_alignment",
                    score=alignment_score,
                    threshold=task_input.alignment_threshold,
                )
                video_data = None  # Force fallback

        except (LatentSyncError, Exception) as e:
            log.warning("latentsync_render_failed", error=str(e))
            video_data = None

        # 6. Fallback to SadTalker
        if video_data is None:
            log.info("falling_back_to_sadtalker")
            fallback_used = True

            # Release LatentSync reservation, acquire SadTalker
            if reservation:
                release_gpu_reservation(reservation, config)
            try:
                reservation = acquire_gpu_reservation(
                    job_id=job_id,
                    model_name="sadtalker",
                    vram_mb=8192,
                    config=config,
                )
            except Exception:
                pass

            try:
                video_data = loop.run_until_complete(
                    _render_with_sadtalker(
                        reference_path, audio_path, task_input, config, temp_dir,
                    )
                )
                model_used = "sadtalker"

                # Probe output for metadata
                ffmpeg = FFmpegClient(temp_dir=temp_dir)
                sadtalker_path = os.path.join(temp_dir, "sadtalker_output.mp4")
                with open(sadtalker_path, "wb") as f:
                    f.write(video_data)
                probe = ffmpeg.probe(sadtalker_path)
                for stream in probe.get("streams", []):
                    if stream.get("codec_type") == "video":
                        output.width = int(stream.get("width", 0))
                        output.height = int(stream.get("height", 0))
                        fps_str = stream.get("r_frame_rate", "30/1")
                        if "/" in fps_str:
                            num, den = fps_str.split("/")
                            output.fps = int(int(num) / max(int(den), 1))
                        else:
                            output.fps = int(float(fps_str))
                output.duration_seconds = float(
                    probe.get("format", {}).get("duration", 0)
                )
                alignment_score = 0.80  # SadTalker doesn't report alignment

                log.info("sadtalker_render_complete", duration=output.duration_seconds)

            except Exception as e:
                log.error("sadtalker_render_failed", error=str(e))
                output.status = StageStatus.FAILED
                output.errors.append(f"Both LatentSync and SadTalker failed: {e}")
                output.generation_time_seconds = round(time.monotonic() - start_time, 2)
                output.completed_at = datetime.now(timezone.utc)

                update_job_status(
                    job_id, "failed",
                    error_message="Stage 6: All talking head renderers failed",
                )

                output_dict = output.model_dump(mode="json")
                celery_app.send_task(
                    "tasks.pipeline_orchestrator_v2.handle_stage_completion",
                    kwargs={"stage_output_dict": output_dict},
                    queue="default",
                )
                return output_dict

        # 7. Corruption detection
        corruption_detector = CorruptionDetector()
        video_path = os.path.join(temp_dir, "talking_head_final.mp4")
        with open(video_path, "wb") as f:
            f.write(video_data)

        corruption_result = corruption_detector.validate_video(
            file_path=video_path,
            expected_codec="h264",
            expected_width=output.width,
            expected_height=output.height,
            expected_duration=output.duration_seconds,
            duration_tolerance=0.10,
        )
        output.corruption_check_passed = corruption_result.is_valid

        if not corruption_result.is_valid:
            log.warning(
                "corruption_detected",
                errors=corruption_result.errors,
            )

        # 8. Lipsync validation
        lipsync_validator = LipsyncValidator()
        lipsync_result = lipsync_validator.validate(
            video_path=video_path,
            audio_path=audio_path,
            threshold=task_input.alignment_threshold,
        )
        output.alignment_score = lipsync_result.alignment_score

        # 9. Compute SHA-256 and upload
        sha256 = compute_asset_sha256(video_data)
        output.sha256_hash = sha256
        output.file_size_bytes = len(video_data)
        output.model_used = model_used
        output.render_mode = task_input.latentsync_mode
        output.fallback_used = fallback_used

        upload_result = loop.run_until_complete(
            _upload_asset(
                project_id=project_id,
                language_code=task_input.language_code,
                data=video_data,
                sha256_hash=sha256,
                metadata={
                    "model": model_used,
                    "alignment_score": alignment_score,
                    "width": output.width,
                    "height": output.height,
                    "fps": output.fps,
                    "duration": output.duration_seconds,
                    "fallback_used": fallback_used,
                    "corruption_check_passed": corruption_result.is_valid,
                },
                config=config,
            )
        )

        output.asset_id = upload_result.get("id", "")
        output.seaweedfs_path = upload_result.get("storage_path", "")
        output.generation_time_seconds = round(time.monotonic() - start_time, 2)
        output.completed_at = datetime.now(timezone.utc)

        loop.close()

        # Save checkpoint
        save_checkpoint(
            job_id=job_id,
            stage=PipelineStage.TALKING_HEAD_RENDER.value,
            checkpoint_data={
                "asset_id": output.asset_id,
                "alignment_score": output.alignment_score,
                "model_used": model_used,
            },
        )

        log.info(
            "stage6_talking_head_complete",
            model=model_used,
            alignment_score=output.alignment_score,
            elapsed=output.generation_time_seconds,
        )

    except Exception as e:
        log.error("stage6_unexpected_error", error=str(e))
        output.status = StageStatus.FAILED
        output.errors.append(str(e))
        output.completed_at = datetime.now(timezone.utc)
        update_job_status(job_id, "failed", error_message=f"Stage 6 error: {e}")

    finally:
        if reservation:
            release_gpu_reservation(reservation, config)
        # Cleanup temp files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Dispatch stage completion
    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )

    return output_dict
