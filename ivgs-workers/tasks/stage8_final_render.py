"""
IVGS v5 — Stage 8: Final Render Task (Segment-Based)
========================================================

Pipeline Stage 8 per §6.1:
- Trigger: User approval from USER_REVIEW state
- Processing:
    1. Load locked composition manifest
    2. Split manifest into 10–30 second segments (segment_planner)
    3. Create render_segments records in database
    4. Render each segment independently via FFmpeg
    5. Compute SHA-256 checksum per segment
    6. Failed segments retry independently (without discarding completed segments)
    7. Verify all segment checksums before final assembly
    8. Concatenate segments via FFmpeg concat demuxer
    9. Produce 1080p MP4 and 4K MP4 per Table 6-2
    10. Run corruption detection on final outputs
    11. Upload to SeaweedFS at /ivgs/final/{project_id}/renders/{language_code}/
    12. Update project with final render asset IDs

Output formats (Table 6-2):
    1080p: 1920×1080 H.264 CRF 18, VBV 8 Mbps, AAC 192 kbps 48kHz stereo, 30fps
    4K:    3840×2160 H.265 CRF 20, VBV 20 Mbps, AAC 256 kbps 48kHz stereo, 30fps

Queue: composition (node-05, node-06)
Timeout: 900 seconds per profile
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
    _compute_file_sha256,
)
from clients.remotion_client import RemotionClient
from config import WorkerConfig
from models.task_result import PipelineStage, StageStatus
from services.caption_service import CaptionService
from services.segment_planner import SegmentPlanner, RenderSegment
from utils.error_handler import save_checkpoint, update_job_status
from utils.media_converter import compute_asset_sha256
from validators.corruption_detector import CorruptionDetector

logger = structlog.get_logger("ivgs.stage8.final_render")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FinalRenderAsset(BaseModel):
    """Reference to an asset for composition."""
    asset_id: str
    asset_type: str
    seaweedfs_path: str = ""
    content_hash: str = ""


class FinalRenderScene(BaseModel):
    """A scene for final render composition."""
    scene_id: str
    scene_index: int
    scene_title: str = ""
    narration_text: str = ""
    duration_seconds: float = 10.0
    media_type: str = "image"
    background_asset: Optional[FinalRenderAsset] = None
    audio_asset: Optional[FinalRenderAsset] = None
    talking_head_position: str = "bottom_right"
    talking_head_scale: float = 0.25
    show_lower_third: bool = True
    caption_timestamps: List[Dict[str, Any]] = Field(default_factory=list)


class Stage8Input(BaseModel):
    """Input for Stage 8: Final Render."""
    job_id: str
    project_id: str
    project_name: str = ""
    language_code: str = "en-US"
    manifest_id: str
    talking_head_asset_id: Optional[str] = None
    scenes: List[FinalRenderScene] = Field(min_length=1)
    render_profiles: List[str] = Field(default=["1080p", "4k"])
    enable_lower_thirds: bool = True
    enable_captions: bool = True
    enable_talking_head: bool = True
    max_segment_duration: float = 30.0
    min_segment_duration: float = 10.0
    max_segment_retries: int = 2


class SegmentRenderResult(BaseModel):
    """Result for a single segment render."""
    segment_id: str
    segment_index: int
    start_time: float
    end_time: float
    duration: float
    output_path: str = ""
    sha256_hash: str = ""
    file_size_bytes: int = 0
    render_time_seconds: float = 0.0
    status: str = "pending"
    retry_count: int = 0
    errors: List[str] = Field(default_factory=list)


class ProfileRenderResult(BaseModel):
    """Result for a single profile (1080p or 4K)."""
    profile: str
    asset_id: Optional[str] = None
    seaweedfs_path: Optional[str] = None
    sha256_hash: str = ""
    width: int = 0
    height: int = 0
    fps: int = 30
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    render_time_seconds: float = 0.0
    segment_count: int = 0
    segments_succeeded: int = 0
    segments_failed: int = 0
    corruption_check_passed: bool = False
    status: str = "success"


class Stage8Output(BaseModel):
    """Output from Stage 8: Final Render."""
    job_id: str
    project_id: str
    stage: str = PipelineStage.FINAL_RENDER.value
    status: StageStatus = StageStatus.SUCCESS
    profile_results: List[ProfileRenderResult] = Field(default_factory=list)
    total_render_time_seconds: float = 0.0
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
    asset_id: str, dest_path: str, config: WorkerConfig,
) -> str:
    """Download asset and write to file."""
    data = await _download_asset(asset_id, config)
    with open(dest_path, "wb") as f:
        f.write(data)
    return dest_path


async def _upload_final_render(
    project_id: str,
    language_code: str,
    profile: str,
    data: bytes,
    sha256_hash: str,
    metadata: Dict[str, Any],
    config: WorkerConfig,
) -> Dict[str, Any]:
    """Upload final render to SeaweedFS."""
    async with httpx.AsyncClient(
        timeout=300.0,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = await client.post(
            f"{config.pipeline_api.full_base_url}/assets",
            files={
                "file": (
                    f"final_{profile}_{language_code}.mp4",
                    data,
                    "video/mp4",
                ),
            },
            data={
                "project_id": project_id,
                "asset_type": "final_render",
                "content_hash": sha256_hash,
                "metadata": json.dumps(metadata),
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Final render upload failed: HTTP {resp.status_code}")
        return resp.json()


async def _update_segment_status(
    job_id: str,
    segment_id: str,
    status: str,
    sha256_hash: str,
    config: WorkerConfig,
) -> None:
    """Update render_segments table via Pipeline API."""
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            await client.patch(
                f"{config.pipeline_api.full_base_url}/jobs/{job_id}/segments/{segment_id}",
                json={
                    "status": status,
                    "content_hash": sha256_hash,
                },
            )
    except Exception as e:
        logger.warning("segment_status_update_failed", segment_id=segment_id, error=str(e))


def _build_timeline_for_segment(
    segment: RenderSegment,
    scenes: List[FinalRenderScene],
    scene_file_map: Dict[str, Dict[str, str]],
    talking_head_path: Optional[str],
    caption_path: Optional[str],
    profile: RenderProfile,
) -> CompositionTimeline:
    """Build a CompositionTimeline for a single segment."""
    timeline_scenes: List[TimelineScene] = []

    for scene_ref in segment.scene_refs:
        scene = next(
            (s for s in scenes if s.scene_id == scene_ref["scene_id"]),
            None,
        )
        if not scene:
            continue

        files = scene_file_map.get(scene.scene_id, {})
        layers: List[SceneLayer] = []

        # Background
        bg_path = files.get("background")
        if bg_path:
            layers.append(SceneLayer(
                layer_type="background",
                file_path=bg_path,
                duration=scene_ref.get("duration", scene.duration_seconds),
            ))

        # Talking head
        if talking_head_path:
            pos_map = {
                "bottom_right": PiPPosition.BOTTOM_RIGHT,
                "bottom_left": PiPPosition.BOTTOM_LEFT,
                "top_right": PiPPosition.TOP_RIGHT,
                "full_screen": PiPPosition.FULL_SCREEN,
            }
            layers.append(SceneLayer(
                layer_type="talking_head",
                file_path=talking_head_path,
                duration=scene_ref.get("duration", scene.duration_seconds),
                position=pos_map.get(
                    scene.talking_head_position,
                    PiPPosition.BOTTOM_RIGHT,
                ),
                scale=scene.talking_head_scale,
            ))

        # Lower third
        lt_path = files.get("lower_third")
        if lt_path:
            layers.append(SceneLayer(
                layer_type="lower_third",
                file_path=lt_path,
                has_alpha=True,
            ))

        # Captions
        if caption_path:
            layers.append(SceneLayer(
                layer_type="caption",
                file_path=caption_path,
            ))

        # Audio
        audio_path = files.get("audio")
        if audio_path:
            layers.append(SceneLayer(
                layer_type="audio",
                file_path=audio_path,
                duration=scene_ref.get("duration", scene.duration_seconds),
            ))

        timeline_scenes.append(TimelineScene(
            scene_id=scene.scene_id,
            scene_index=scene.scene_index,
            start_time=scene_ref.get("offset", 0),
            duration=scene_ref.get("duration", scene.duration_seconds),
            layers=layers,
        ))

    return CompositionTimeline(
        project_id=segment.project_id,
        scenes=timeline_scenes,
        total_duration=segment.duration,
        profile=profile,
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.final_render_task.render_final",
    queue="composition",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=1800,
    time_limit=1860,
    acks_late=True,
    reject_on_worker_lost=True,
)
def render_final(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task: segment-based final render at 1080p and 4K.

    1. Plan segments (10-30s each)
    2. Download all assets
    3. Render each segment per profile
    4. Retry failed segments independently
    5. Verify checksums and concatenate
    6. Run corruption detection
    7. Upload final renders
    """
    config = WorkerConfig()

    try:
        task_input = Stage8Input(**task_input_dict)
    except Exception as e:
        logger.error("stage8_input_error", error=str(e))
        raise ValueError(f"Invalid Stage 8 input: {e}") from e

    job_id = task_input.job_id
    project_id = task_input.project_id
    log = logger.bind(
        job_id=job_id,
        project_id=project_id,
        profiles=task_input.render_profiles,
        scene_count=len(task_input.scenes),
    )
    log.info("stage8_final_render_starting")

    update_job_status(job_id, "running", stage=PipelineStage.FINAL_RENDER.value)

    output = Stage8Output(job_id=job_id, project_id=project_id)
    temp_dir = tempfile.mkdtemp(prefix="ivgs_stage8_")
    total_start = time.monotonic()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Plan segments
        planner = SegmentPlanner(
            max_segment_duration=task_input.max_segment_duration,
            min_segment_duration=task_input.min_segment_duration,
        )
        segments = planner.plan_segments(
            project_id=project_id,
            scenes=[{
                "scene_id": s.scene_id,
                "scene_index": s.scene_index,
                "duration_seconds": s.duration_seconds,
            } for s in task_input.scenes],
        )

        log.info("segments_planned", segment_count=len(segments))

        # 2. Download all assets
        scene_file_map: Dict[str, Dict[str, str]] = {}
        remotion = RemotionClient()

        for scene in task_input.scenes:
            files: Dict[str, str] = {}

            # Background
            if scene.background_asset:
                ext = ".png" if scene.media_type == "image" else ".mp4"
                bg_path = os.path.join(temp_dir, f"bg_{scene.scene_id}{ext}")
                loop.run_until_complete(
                    _download_asset_to_file(
                        scene.background_asset.asset_id, bg_path, config,
                    )
                )
                files["background"] = bg_path

            # Audio
            if scene.audio_asset:
                audio_path = os.path.join(temp_dir, f"audio_{scene.scene_id}.wav")
                loop.run_until_complete(
                    _download_asset_to_file(
                        scene.audio_asset.asset_id, audio_path, config,
                    )
                )
                files["audio"] = audio_path

            # Lower third (render at 1080p for highest quality, scale later)
            if task_input.enable_lower_thirds and scene.show_lower_third and scene.scene_title:
                try:
                    lt_result = loop.run_until_complete(
                        remotion.render_lower_third(
                            title=scene.scene_title,
                            duration_seconds=min(scene.duration_seconds, 5.0),
                            width=1920,
                            height=1080,
                        )
                    )
                    lt_path = os.path.join(temp_dir, f"lt_{scene.scene_id}.webm")
                    with open(lt_path, "wb") as f:
                        f.write(lt_result.asset_data)
                    files["lower_third"] = lt_path
                except Exception as e:
                    log.warning("lower_third_failed", scene_id=scene.scene_id, error=str(e))

            scene_file_map[scene.scene_id] = files

        loop.run_until_complete(remotion.close())

        # Download talking head
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
        caption_path: Optional[str] = None
        if task_input.enable_captions:
            caption_service = CaptionService()
            all_timestamps: List[Dict[str, Any]] = []
            offset = 0.0
            for scene in sorted(task_input.scenes, key=lambda s: s.scene_index):
                for ts in scene.caption_timestamps:
                    adjusted = {**ts}
                    adjusted["start"] = ts.get("start", 0) + offset
                    adjusted["end"] = ts.get("end", 0) + offset
                    all_timestamps.append(adjusted)
                offset += scene.duration_seconds
            if all_timestamps:
                caption_path = os.path.join(temp_dir, "captions.srt")
                caption_service.write_srt(all_timestamps, caption_path)

        # 3. Render each profile
        profile_map = {
            "1080p": RenderProfile.HD_1080P,
            "4k": RenderProfile.UHD_4K,
        }

        for profile_name in task_input.render_profiles:
            profile = profile_map.get(profile_name)
            if not profile:
                log.warning("unknown_profile", profile=profile_name)
                continue

            profile_start = time.monotonic()
            profile_result = ProfileRenderResult(
                profile=profile_name,
                segment_count=len(segments),
            )

            ffmpeg = FFmpegClient(
                temp_dir=os.path.join(temp_dir, f"render_{profile_name}"),
            )
            os.makedirs(ffmpeg._temp_dir, exist_ok=True)

            segment_results: Dict[int, SegmentRenderResult] = {}
            segment_checksums: Dict[str, str] = {}

            # Render each segment
            for segment in segments:
                seg_result = SegmentRenderResult(
                    segment_id=segment.segment_id,
                    segment_index=segment.segment_index,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    duration=segment.duration,
                )

                for attempt in range(task_input.max_segment_retries + 1):
                    try:
                        # Build timeline for this segment
                        seg_timeline = _build_timeline_for_segment(
                            segment=segment,
                            scenes=task_input.scenes,
                            scene_file_map=scene_file_map,
                            talking_head_path=talking_head_path,
                            caption_path=caption_path,
                            profile=profile,
                        )

                        seg_output_path = os.path.join(
                            ffmpeg._temp_dir,
                            f"segment_{segment.segment_index:04d}_{profile_name}.mp4",
                        )

                        seg_render = ffmpeg.compose_timeline(
                            timeline=seg_timeline,
                            output_path=seg_output_path,
                            timeout=300.0,
                        )

                        seg_sha256 = _compute_file_sha256(seg_output_path)

                        seg_result.output_path = seg_output_path
                        seg_result.sha256_hash = seg_sha256
                        seg_result.file_size_bytes = seg_render.file_size_bytes
                        seg_result.render_time_seconds = seg_render.render_time_seconds
                        seg_result.status = "completed"
                        seg_result.retry_count = attempt

                        segment_checksums[seg_output_path] = seg_sha256

                        # Update segment status in DB
                        loop.run_until_complete(
                            _update_segment_status(
                                job_id, segment.segment_id, "completed",
                                seg_sha256, config,
                            )
                        )

                        log.info(
                            "segment_rendered",
                            segment_index=segment.segment_index,
                            profile=profile_name,
                            attempt=attempt,
                            duration=seg_render.duration_seconds,
                        )
                        break  # Success, exit retry loop

                    except Exception as e:
                        seg_result.retry_count = attempt
                        seg_result.errors.append(f"Attempt {attempt}: {e}")
                        log.warning(
                            "segment_render_failed",
                            segment_index=segment.segment_index,
                            attempt=attempt,
                            error=str(e),
                        )

                        if attempt >= task_input.max_segment_retries:
                            seg_result.status = "failed"
                            loop.run_until_complete(
                                _update_segment_status(
                                    job_id, segment.segment_id, "failed",
                                    "", config,
                                )
                            )

                segment_results[segment.segment_index] = seg_result

            # Check segment results
            succeeded = [r for r in segment_results.values() if r.status == "completed"]
            failed = [r for r in segment_results.values() if r.status == "failed"]

            profile_result.segments_succeeded = len(succeeded)
            profile_result.segments_failed = len(failed)

            if failed:
                log.error(
                    "segments_failed",
                    profile=profile_name,
                    failed_count=len(failed),
                )
                if not succeeded:
                    profile_result.status = "failed"
                    output.profile_results.append(profile_result)
                    continue

            # 4. Verify checksums and concatenate
            ordered_segments = sorted(succeeded, key=lambda r: r.segment_index)
            segment_paths = [r.output_path for r in ordered_segments]

            final_output_path = os.path.join(
                temp_dir, f"final_{profile_name}_{project_id}.mp4"
            )

            try:
                concat_result = ffmpeg.concat_segments(
                    segment_paths=segment_paths,
                    output_path=final_output_path,
                    profile=profile,
                    verify_checksums=segment_checksums,
                    timeout=600.0,
                )
            except Exception as e:
                log.error("concat_failed", profile=profile_name, error=str(e))
                profile_result.status = "failed"
                output.profile_results.append(profile_result)
                continue

            # 5. Corruption detection
            detector = CorruptionDetector()
            from clients.ffmpeg_client import RENDER_PROFILES
            prof_config = RENDER_PROFILES[profile]
            corruption = detector.validate_video(
                file_path=final_output_path,
                expected_codec=prof_config.video_codec.replace("lib", ""),
                expected_width=prof_config.width,
                expected_height=prof_config.height,
            )
            profile_result.corruption_check_passed = corruption.is_valid

            # 6. Upload
            with open(final_output_path, "rb") as f:
                final_data = f.read()

            final_sha256 = compute_asset_sha256(final_data)

            upload = loop.run_until_complete(
                _upload_final_render(
                    project_id=project_id,
                    language_code=task_input.language_code,
                    profile=profile_name,
                    data=final_data,
                    sha256_hash=final_sha256,
                    metadata={
                        "profile": profile_name,
                        "width": prof_config.width,
                        "height": prof_config.height,
                        "video_codec": prof_config.video_codec,
                        "duration": concat_result.duration_seconds,
                        "segment_count": len(ordered_segments),
                        "corruption_check": corruption.is_valid,
                    },
                    config=config,
                )
            )

            profile_result.asset_id = upload.get("id", "")
            profile_result.seaweedfs_path = upload.get("storage_path", "")
            profile_result.sha256_hash = final_sha256
            profile_result.width = prof_config.width
            profile_result.height = prof_config.height
            profile_result.duration_seconds = concat_result.duration_seconds
            profile_result.file_size_bytes = len(final_data)
            profile_result.render_time_seconds = round(
                time.monotonic() - profile_start, 2
            )

            output.profile_results.append(profile_result)

            save_checkpoint(
                job_id=job_id,
                stage=PipelineStage.FINAL_RENDER.value,
                checkpoint_data={
                    "profile": profile_name,
                    "asset_id": profile_result.asset_id,
                    "status": "completed",
                },
            )

            log.info(
                "profile_render_complete",
                profile=profile_name,
                duration=profile_result.duration_seconds,
                file_size=profile_result.file_size_bytes,
                elapsed=profile_result.render_time_seconds,
            )

        loop.close()

        # Determine overall status
        all_failed = all(p.status == "failed" for p in output.profile_results)
        any_failed = any(p.status == "failed" for p in output.profile_results)

        if all_failed:
            output.status = StageStatus.FAILED
            update_job_status(job_id, "failed", error_message="All render profiles failed")
        elif any_failed:
            output.status = StageStatus.PARTIAL_SUCCESS
        else:
            output.status = StageStatus.SUCCESS
            update_job_status(job_id, "completed")

        output.total_render_time_seconds = round(time.monotonic() - total_start, 2)
        output.completed_at = datetime.now(timezone.utc)

        log.info(
            "stage8_final_render_complete",
            profiles_rendered=len(output.profile_results),
            total_elapsed=output.total_render_time_seconds,
        )

    except Exception as e:
        log.error("stage8_unexpected_error", error=str(e))
        output.status = StageStatus.FAILED
        output.errors.append(str(e))
        output.completed_at = datetime.now(timezone.utc)
        update_job_status(job_id, "failed", error_message=f"Stage 8 error: {e}")

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
