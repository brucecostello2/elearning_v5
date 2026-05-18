"""Motion graphics (Ken Burns / zoom-pan / static) rendering task."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.motion_graphics import MotionGraphicsService, EffectType
from app.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

WORKDIR = os.getenv("WORKDIR", "/mnt/workdir")


@shared_task(
    name="tasks.motion_graphics.render_motion_graphics_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def render_motion_graphics_task(self, job_id: int) -> None:
    """Render animated video segments for non-talking-head scenes.

    Processes all scenes except scene_type='talking_head' (handled by
    talking_head_task). Applies Ken Burns or zoom/pan effects based on
    the storyboard's motion_effect field.

    Args:
        job_id: The job to process.
    """
    logger.info("render_motion_graphics_task: job=%d", job_id)
    db = SessionLocal()
    mg_svc = MotionGraphicsService(workdir=WORKDIR)
    policy = RetryPolicy(db)

    try:
        cp_svc = CheckpointService(db)
        storyboard = cp_svc.get_stage_output(job_id, "storyboard",
                                              "storyboard_scenes") or []
        scene_images = cp_svc.get_stage_output(job_id, "image_gen",
                                               "scene_images") or []
        scene_audio = cp_svc.get_stage_output(job_id, "tts",
                                              "scene_audio") or []

        image_map = {s["scene_index"]: s.get("image_path")
                     for s in scene_images}
        audio_map = {s["scene_index"]: s for s in scene_audio}

        output_dir = Path(WORKDIR) / str(job_id) / "motion_graphics"
        output_dir.mkdir(parents=True, exist_ok=True)

        mg_results: List[Dict[str, Any]] = []

        for scene in storyboard:
            scene_idx = scene.get("scene_index", 0)
            scene_type = scene.get("scene_type", "broll")

            if scene_type == "talking_head":
                continue  # Already handled

            image_path = image_map.get(scene_idx)
            audio_info = audio_map.get(scene_idx, {})
            audio_path = audio_info.get("audio_path")
            duration_s = scene.get("duration_seconds", 10.0)
            motion_effect = scene.get("motion_effect", "ken_burns")
            output_video = str(output_dir / f"scene_{scene_idx:03d}.mp4")
            output_muxed = str(output_dir / f"scene_{scene_idx:03d}_final.mp4")

            if not image_path or not os.path.exists(image_path):
                logger.warning("No image for scene %d — using static", scene_idx)
                image_path = _get_placeholder_image()

            try:
                effect = EffectType(motion_effect)
            except ValueError:
                effect = EffectType.KEN_BURNS

            try:
                if effect == EffectType.KEN_BURNS:
                    mg_svc.create_ken_burns(image_path, output_video, duration_s)
                elif effect in (EffectType.ZOOM_IN, EffectType.ZOOM_OUT,
                                EffectType.PAN_LEFT, EffectType.PAN_RIGHT):
                    mg_svc.create_zoom_pan(image_path, output_video,
                                           duration_s, effect=effect)
                else:
                    mg_svc.create_static_video(image_path, output_video, duration_s)

                # Mux audio if available
                if audio_path and os.path.exists(audio_path):
                    _mux_audio_ffmpeg(output_video, audio_path, output_muxed)
                    final_path = output_muxed
                else:
                    final_path = output_video

                mg_results.append({
                    "scene_index": scene_idx,
                    "video_path": final_path,
                    "effect": effect.value,
                    "duration_s": duration_s,
                })

            except Exception as exc:
                logger.error("MG render failed: scene=%d error=%s", scene_idx, exc)
                mg_results.append({"scene_index": scene_idx, "video_path": None,
                                   "error": str(exc)})

        cp_svc.save_checkpoint(
            job_id=job_id, stage="motion_graphics", stage_index=5,
            data={"scene_count": len(mg_results)},
            outputs={"mg_scenes": mg_results},
        )
        db.commit()

        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "motion_graphics"])

    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "motion_graphics", str(exc), failure_type]
        )
    finally:
        db.close()


def _mux_audio_ffmpeg(video_path: str, audio_path: str,
                       output_path: str) -> None:
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-shortest", output_path],
        check=True, capture_output=True,
    )


def _get_placeholder_image() -> str:
    """Return path to a black placeholder PNG (created if not exists)."""
    path = "/tmp/ivgs_placeholder_black.png"
    if not os.path.exists(path):
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1920x1080",
             "-frames:v", "1", path],
            capture_output=True,
        )
    return path
