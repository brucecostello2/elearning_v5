"""
IVGS v5 — Stage 7: Prototype Draft Assembly Task
====================================================

Pipeline Stage 7 per §6.1:
- Trigger: Stage 6 (Talking Head) completed
- Input: Composition manifest with all asset references
- Processing:
    1. Load locked composition manifest
    2. Download all required assets from SeaweedFS
    3. Render lower-third overlays via Remotion
    4. Generate caption files (SRT) from WhisperX timestamps
    5. Compose each scene with FFmpeg layer stack (Table 6-3)
    6. Concatenate all scenes into 720p draft
    7. Run corruption detection on output
    8. Upload draft to SeaweedFS at /ivgs/drafts/{project_id}/draft_720p.mp4
    9. Transition project state to USER_REVIEW
    10. Dispatch stage completion (pipeline pauses for user review)

- Resolution: 1280×720 (draft quality, CRF 23)
- Compositor: FFmpeg on node-06 (primary), node-05 (overflow)
- Queue: composition
- Timeout: 900 seconds
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog
from pydantic import BaseModel, Field

from celery_app import IVGSBaseTask, celery_app
from clients.ffmpeg_client import (
    CompositionTimeline,
    FFmpegClient,
    PiPPosition,
    RenderProfile,
    SceneLayer,
    TimelineScene,
)
from clients.remotion_client import RemotionClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from services.caption_service import CaptionService
from utils.error_handler import save_checkpoint, update_job_status
from utils.media_converter import compute_asset_sha256
from validators.corruption_detector import CorruptionDetector

logger = structlog.get_logger("ivgs.stage7.prototype_draft")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ManifestSceneAsset(BaseModel):
    """Asset reference within a manifest scene."""
    asset_id: str
    asset_type: str  # image, video_clip, animation, audio, talking_head
    seaweedfs_path: str = ""
    duration_seconds: float = 0.0
    content_hash: str = ""


class ManifestScene(BaseModel):
    """A scene in the composition manifest."""
    scene_id: str
    scene_index: int
    scene_title: str = ""
    narration_text: str = ""
    duration_seconds: float = 10.0
    media_type: str = "image"
    background_asset: Optional[ManifestSceneAsset] = None
    audio_asset: Optional[ManifestSceneAsset] = None
    talking_head_position: str = "bottom_right"
    talking_head_scale: float = 0.25
    show_lower_third: bool = True
    caption_timestamps: List[Dict[str, Any]] = Field(default_factory=list)


class Stage7Input(BaseModel):
    """Input for Stage 7: Prototype Draft Assembly."""
    job_id: str
    project_id: str
    project_name: str = ""
    language_code: str = "en-US"
    manifest_id: str
    talking_head_asset_id: Optional[str] = None
    scenes: List[ManifestScene] = Field(min_length=1)
    enable_lower_thirds: bool = True
    enable_captions: bool = True
    enable_talking_head: bool = True


class Stage7Output(BaseModel):
    """Output from Stage 7: Prototype Draft Assembly."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.PROTOTYPE_DRAFT.value
    status: StageStatus = StageStatus.SUCCESS
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 30
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    scene_count: int = 0
    scenes_composed: int = 0
    scenes_failed: int = 0
    render_time_seconds: float = 0.0
    corruption_check_passed: bool = False
    errors: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _download_asset(asset_id: str, config: WorkerConfig) -> bytes:
    """Download asset from SeaweedFS via Pipeline API."""
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


async def _download_asset_to_file(
    asset_id: str,
    dest_path: str,
    config: WorkerConfig,
) -> str:
    """Download asset and write to file."""
    data = await _download_asset(asset_id, config)
    with open(dest_path, "wb") as f:
        f.write(data)
    return dest_path


async def _upload_draft(
    project_id: str,
    language_code: str,
    data: bytes,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Upload draft video to SeaweedFS."""
    async with httpx.AsyncClient(
        timeout=180.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/assets",
            files={
                "file": (
                    f"draft_720p_{language_code}.mp4",
                    data,
                    "video/mp4",
                ),
            },
            data={
                "project_id": project_id,
                "asset_type": "draft_render",
                "content_hash": sha256_hash,
                "metadata": json.dumps(metadata),
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Draft upload failed: HTTP {resp.status_code}")
        return resp.json()


async def _render_lower_third_for_scene(
    scene: ManifestScene,
    remotion: RemotionClient,
    temp_dir: str,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
) -> Optional[str]:
    """Render lower-third overlay for a scene and save to temp file."""
    if not scene.show_lower_third or not scene.scene_title:
        return None

    try:
        result = await remotion.render_lower_third(
            title=scene.scene_title,
            subtitle="",
            duration_seconds=min(scene.duration_seconds, 5.0),
            width=width,
            height=height,
            fps=fps,
        )
        lt_path = os.path.join(temp_dir, f"lt_{scene.scene_id}.webm")
        with open(lt_path, "wb") as f:
            f.write(result.asset_data)
        return lt_path
    except Exception as e:
        logger.warning(
            "lower_third_render_failed",
            scene_id=scene.scene_id,
            error=str(e),
        )
        return None


async def _prepare_scene_layers(
    scene: ManifestScene,
    talking_head_path: Optional[str],
    lower_third_path: Optional[str],
    caption_path: Optional[str],
    temp_dir: str,
    config: WorkerConfig,
) -> List[SceneLayer]:
    """Prepare all layers for a scene composition."""
    layers: List[SceneLayer] = []

    # Background layer
    if scene.background_asset:
        bg_path = os.path.join(temp_dir, f"bg_{scene.scene_id}.bin")
        await _download_asset_to_file(
            scene.background_asset.asset_id, bg_path, config,
        )
        # Rename based on type
        if scene.media_type == "image":
            final_bg = bg_path + ".png"
        else:
            final_bg = bg_path + ".mp4"
        os.rename(bg_path, final_bg)

        layers.append(SceneLayer(
            layer_type="background",
            file_path=final_bg,
            duration=scene.duration_seconds,
        ))

    # Talking head layer
    if talking_head_path and scene.background_asset:
        pos_map = {
            "bottom_right": PiPPosition.BOTTOM_RIGHT,
            "bottom_left": PiPPosition.BOTTOM_LEFT,
            "top_right": PiPPosition.TOP_RIGHT,
            "top_left": PiPPosition.TOP_LEFT,
            "full_screen": PiPPosition.FULL_SCREEN,
        }
        layers.append(SceneLayer(
            layer_type="talking_head",
            file_path=talking_head_path,
            duration=scene.duration_seconds,
            position=pos_map.get(
                scene.talking_head_position,
                PiPPosition.BOTTOM_RIGHT,
            ),
            scale=scene.talking_head_scale,
        ))

    # Lower third layer
    if lower_third_path:
        layers.append(SceneLayer(
            layer_type="lower_third",
            file_path=lower_third_path,
            duration=min(scene.duration_seconds, 5.0),
            has_alpha=True,
        ))

    # Caption layer
    if caption_path:
        layers.append(SceneLayer(
            layer_type="caption",
            file_path=caption_path,
        ))

    # Audio layer
    if scene.audio_asset:
        audio_path = os.path.join(temp_dir, f"audio_{scene.scene_id}.wav")
        await _download_asset_to_file(
            scene.audio_asset.asset_id, audio_path, config,
        )
        layers.append(SceneLayer(
            layer_type="audio",
            file_path=audio_path,
            duration=scene.duration_seconds,
        ))

    return layers


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.prototype_draft_task.assemble_prototype_draft",
    queue="composition",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=900,
    time_limit=960,
    acks_late=True,
    reject_on_worker_lost=True,
)
def assemble_prototype_draft(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task: assemble 720p prototype draft.

    Composes all scenes with layer stacking, concatenates, validates,
    and uploads for user review.
    """
    config = WorkerConfig()

    try:
        task_input = Stage7Input(**task_input_dict)
    except Exception as e:
        logger.error("stage7_input_error", error=str(e))
        raise ValueError(f"Invalid Stage 7 input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    log = logger.bind(
        job_id=job_id,
        project_id=project_id,
        scene_count=len(task_input.scenes),
    )
    log.info("stage7_prototype_draft_starting")

    update_job_status(job_id, "running", stage=PipelineStage.PROTOTYPE_DRAFT.value)

    output = Stage7Output(
        job_id=job_id,
        project_id=project_id,
        scene_count=len(task_input.scenes),
    )

    temp_dir = tempfile.mkdtemp(prefix="ivgs_stage7_")
    start_time = time.monotonic()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        ffmpeg = FFmpegClient(temp_dir=temp_dir)
        remotion = RemotionClient()

        # Download talking head if available
        talking_head_path: Optional[str] = None
        if task_input.enable_talking_head and task_input.talking_head_asset_id:
            th_path = os.path.join(temp_dir, "talking_head.mp4")
            loop.run_until_complete(
                _download_asset_to_file(
                    task_input.talking_head_asset_id, th_path, config,
                )
            )
            talking_head_path = th_path

        # Generate captions
        caption_service = CaptionService()
        caption_path: Optional[str] = None
        if task_input.enable_captions:
            all_timestamps: List[Dict[str, Any]] = []
            cumulative_offset = 0.0
            for scene in sorted(task_input.scenes, key=lambda s: s.scene_index):
                for ts in scene.caption_timestamps:
                    adjusted = {**ts}
                    adjusted["start"] = ts.get("start", 0) + cumulative_offset
                    adjusted["end"] = ts.get("end", 0) + cumulative_offset
                    all_timestamps.append(adjusted)
                cumulative_offset += scene.duration_seconds

            if all_timestamps:
                caption_path = os.path.join(temp_dir, "captions.srt")
                caption_service.write_srt(all_timestamps, caption_path)

        # Build timeline
        timeline_scenes: List[TimelineScene] = []
        cumulative_time = 0.0
        scenes_composed = 0
        scenes_failed = 0

        for scene in sorted(task_input.scenes, key=lambda s: s.scene_index):
            try:
                # Render lower third
                lt_path = loop.run_until_complete(
                    _render_lower_third_for_scene(
                        scene, remotion, temp_dir,
                        width=1280, height=720, fps=30,
                    )
                ) if task_input.enable_lower_thirds else None

                # Prepare layers
                layers = loop.run_until_complete(
                    _prepare_scene_layers(
                        scene=scene,
                        talking_head_path=talking_head_path,
                        lower_third_path=lt_path,
                        caption_path=caption_path,
                        temp_dir=temp_dir,
                        config=config,
                    )
                )

                timeline_scene = TimelineScene(
                    scene_id=scene.scene_id,
                    scene_index=scene.scene_index,
                    start_time=cumulative_time,
                    duration=scene.duration_seconds,
                    layers=layers,
                )
                timeline_scenes.append(timeline_scene)
                cumulative_time += scene.duration_seconds
                scenes_composed += 1

                # Checkpoint per scene
                save_checkpoint(
                    job_id=job_id,
                    stage=PipelineStage.PROTOTYPE_DRAFT.value,
                    checkpoint_data={
                        "scenes_composed": scenes_composed,
                        "last_scene_index": scene.scene_index,
                    },
                )

            except Exception as e:
                log.error(
                    "scene_preparation_failed",
                    scene_id=scene.scene_id,
                    error=str(e),
                )
                scenes_failed += 1

        loop.run_until_complete(remotion.close())

        if not timeline_scenes:
            output.status = StageStatus.FAILED
            output.errors.append("No scenes could be composed")
            update_job_status(job_id, "failed", error_message="Stage 7: No scenes composed")
            output.completed_at = datetime.now(timezone.utc)
            output_dict = output.model_dump(mode="json")
            celery_app.send_task(
                "tasks.pipeline_orchestrator.handle_stage_completion",
                kwargs={"stage_output_dict": output_dict},
                queue="default",
            )
            return output_dict

        # Compose full timeline
        timeline = CompositionTimeline(
            project_id=project_id,
            scenes=timeline_scenes,
            total_duration=cumulative_time,
            profile=RenderProfile.DRAFT,
        )

        draft_output_path = os.path.join(
            temp_dir, f"draft_{project_id}_720p.mp4"
        )

        render_result = ffmpeg.compose_timeline(
            timeline=timeline,
            output_path=draft_output_path,
            timeout=600.0,
        )

        # Corruption detection
        detector = CorruptionDetector()
        corruption_result = detector.validate_video(
            file_path=draft_output_path,
            expected_codec="h264",
            expected_width=1280,
            expected_height=720,
            expected_duration=cumulative_time,
            duration_tolerance=0.15,
        )
        output.corruption_check_passed = corruption_result.is_valid

        # Read output file and upload
        with open(draft_output_path, "rb") as f:
            draft_data = f.read()

        sha256 = compute_asset_sha256(draft_data)

        upload_result = loop.run_until_complete(
            _upload_draft(
                project_id=project_id,
                language_code=task_input.language_code,
                data=draft_data,
                sha256_hash=sha256,
                metadata={
                    "resolution": "720p",
                    "scene_count": scenes_composed,
                    "duration": render_result.duration_seconds,
                    "render_time": render_result.render_time_seconds,
                    "corruption_check": corruption_result.is_valid,
                },
                config=config,
            )
        )

        loop.close()

        output.asset_id = upload_result.get("id", "")
        output.seaweedfs_path = upload_result.get("storage_path", "")
        output.sha256_hash = sha256
        output.duration_seconds = render_result.duration_seconds
        output.file_size_bytes = render_result.file_size_bytes
        output.scenes_composed = scenes_composed
        output.scenes_failed = scenes_failed
        output.render_time_seconds = round(time.monotonic() - start_time, 2)
        output.completed_at = datetime.now(timezone.utc)

        if scenes_failed > 0 and scenes_composed > 0:
            output.status = StageStatus.PARTIAL_SUCCESS
        elif scenes_composed == 0:
            output.status = StageStatus.FAILED

        log.info(
            "stage7_prototype_draft_complete",
            duration=output.duration_seconds,
            file_size=output.file_size_bytes,
            scenes_composed=scenes_composed,
            scenes_failed=scenes_failed,
            elapsed=output.render_time_seconds,
        )

        save_checkpoint(
            job_id=job_id,
            stage=PipelineStage.PROTOTYPE_DRAFT.value,
            checkpoint_data={
                "asset_id": output.asset_id,
                "duration": output.duration_seconds,
                "scenes_composed": scenes_composed,
            },
        )

    except Exception as e:
        log.error("stage7_unexpected_error", error=str(e))
        output.status = StageStatus.FAILED
        output.errors.append(str(e))
        output.completed_at = datetime.now(timezone.utc)
        update_job_status(job_id, "failed", error_message=f"Stage 7 error: {e}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Dispatch stage completion
    output_dict = output.model_dump(mode="json")
    celery_app.send_task(
        "tasks.pipeline_orchestrator.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )

    return output_dict
