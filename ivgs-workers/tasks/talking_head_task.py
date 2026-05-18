"""Talking-head video generation task with timeout and fallback."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.idempotency import IdempotencyGuard
from app.services.timeout_manager import TimeoutManager, TimeoutError
from app.services.retry_policy import RetryPolicy
from app.services.motion_graphics import MotionGraphicsService, EffectType

logger = logging.getLogger(__name__)

WORKDIR = os.getenv("WORKDIR", "/mnt/workdir")
TH_PROVIDER = os.getenv("TALKING_HEAD_PROVIDER", "did")  # "did" or "synthesia"
DID_API_KEY = os.getenv("DID_API_KEY", "")
DID_BASE_URL = "https://api.d-id.com"


@shared_task(
    name="tasks.talking_head.generate_talking_head_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def generate_talking_head_task(self, job_id: int) -> None:
    """Generate talking-head video for scenes that require it.

    Only processes scenes where scene_type == 'talking_head'. Other
    scene types are handled by motion_graphics_task.

    Falls back to animated still (Ken Burns) if D-ID/Synthesia fails.

    Args:
        job_id: The job to process.
    """
    logger.info("generate_talking_head_task: job=%d", job_id)
    db = SessionLocal()
    tm = TimeoutManager()
    policy = RetryPolicy(db)
    mg_svc = MotionGraphicsService(workdir=WORKDIR)

    try:
        cp_svc = CheckpointService(db)
        storyboard = cp_svc.get_stage_output(job_id, "storyboard",
                                              "storyboard_scenes")
        scene_images = cp_svc.get_stage_output(job_id, "image_gen",
                                               "scene_images") or []
        scene_audio = cp_svc.get_stage_output(job_id, "tts",
                                              "scene_audio") or []

        image_map = {s["scene_index"]: s.get("image_path")
                     for s in scene_images}
        audio_map = {s["scene_index"]: s for s in scene_audio}

        output_dir = Path(WORKDIR) / str(job_id) / "talking_head"
        output_dir.mkdir(parents=True, exist_ok=True)

        th_results: List[Dict[str, Any]] = []

        for scene in (storyboard or []):
            scene_idx = scene.get("scene_index", 0)
            scene_type = scene.get("scene_type", "broll")

            if scene_type != "talking_head":
                # Will be handled by motion_graphics_task
                continue

            audio_info = audio_map.get(scene_idx, {})
            audio_path = audio_info.get("audio_path")
            image_path = image_map.get(scene_idx)
            duration_s = scene.get("duration_seconds", 10.0)
            output_path = str(output_dir / f"scene_{scene_idx:03d}.mp4")

            if not audio_path or not image_path:
                logger.warning("Missing audio/image for TH scene %d", scene_idx)
                th_results.append({"scene_index": scene_idx,
                                   "video_path": None, "level_used": 4})
                continue

            result = _generate_th_with_fallback(
                job_id, scene_idx, image_path, audio_path,
                duration_s, output_path, tm, mg_svc
            )
            th_results.append(result)

        cp_svc.save_checkpoint(
            job_id=job_id, stage="talking_head", stage_index=4,
            data={"provider": TH_PROVIDER},
            outputs={"th_scenes": th_results},
        )
        db.commit()

        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "talking_head"])

    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "talking_head", str(exc), failure_type]
        )
    finally:
        db.close()


def _generate_th_with_fallback(
    job_id, scene_idx, image_path, audio_path,
    duration_s, output_path, tm, mg_svc
) -> Dict[str, Any]:
    """Try D-ID/Synthesia, fall back to Ken Burns on failure."""
    try:
        video_path = _generate_did(image_path, audio_path, output_path, tm)
        return {"scene_index": scene_idx, "video_path": video_path, "level_used": 1}
    except Exception as exc:
        logger.warning("TH generation failed (level 1): scene=%d error=%s",
                       scene_idx, exc)

    # Fallback to Ken Burns with audio
    try:
        anim_path = output_path.replace(".mp4", "_anim.mp4")
        mg_svc.create_ken_burns(image_path, anim_path, duration_s)
        # Mux audio into animated still
        muxed_path = output_path.replace(".mp4", "_muxed.mp4")
        _mux_audio(anim_path, audio_path, muxed_path)
        return {"scene_index": scene_idx, "video_path": muxed_path, "level_used": 2}
    except Exception as exc2:
        logger.error("TH fallback (L2) also failed: %s", exc2)

    # Ultimate fallback: static video with audio
    try:
        static_path = output_path.replace(".mp4", "_static.mp4")
        mg_svc.create_static_video(image_path, static_path, duration_s)
        _mux_audio(static_path, audio_path, output_path)
        return {"scene_index": scene_idx, "video_path": output_path, "level_used": 4}
    except Exception as exc3:
        return {"scene_index": scene_idx, "video_path": None,
                "level_used": -1, "error": str(exc3)}


def _generate_did(image_path: str, audio_path: str,
                   output_path: str, tm: TimeoutManager) -> str:
    """Generate talking-head video via D-ID API."""
    import base64

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()

    def _submit():
        resp = requests.post(
            f"{DID_BASE_URL}/talks",
            headers={"Authorization": f"Basic {DID_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "source_url": f"data:image/png;base64,{img_b64}",
                "script": {
                    "type": "audio",
                    "audio_url": f"data:audio/mp3;base64,{audio_b64}",
                },
                "config": {"stitch": True},
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    talk_id = tm.call_with_timeout(
        _submit, model="did", operation="rendering", timeout_seconds=600
    )

    # Poll for completion (max 10 minutes)
    deadline = time.time() + 600
    while time.time() < deadline:
        poll = requests.get(
            f"{DID_BASE_URL}/talks/{talk_id}",
            headers={"Authorization": f"Basic {DID_API_KEY}"},
            timeout=10,
        )
        poll.raise_for_status()
        data = poll.json()
        if data["status"] == "done":
            video_url = data["result_url"]
            video_bytes = requests.get(video_url, timeout=60).content
            IdempotencyGuard.atomic_write(video_bytes, output_path)
            return output_path
        elif data["status"] == "error":
            raise RuntimeError(f"D-ID error: {data.get('error')}")
        time.sleep(5)

    raise TimeoutError("D-ID polling timed out after 600s")


def _mux_audio(video_path: str, audio_path: str, output_path: str) -> None:
    """Add audio track to silent video."""
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-shortest", output_path],
        check=True, capture_output=True,
    )
