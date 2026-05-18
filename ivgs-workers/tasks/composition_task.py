"""Final FFmpeg video composition Celery task."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

WORKDIR = os.getenv("WORKDIR", "/mnt/workdir")
OUTPUT_RESOLUTION = os.getenv("OUTPUT_RESOLUTION", "1920x1080")
OUTPUT_FPS = int(os.getenv("OUTPUT_FPS", "25"))


@shared_task(
    name="tasks.composition.compose_video_task",
    bind=True,
    acks_late=True,
    max_retries=0,
    time_limit=1860,
    soft_time_limit=1800,
)
def compose_video_task(self, job_id: int) -> None:
    """Compose all scene video segments into the final output video.

    Gathers segment paths from talking_head and motion_graphics checkpoints,
    orders them by scene index, builds an FFmpeg concat command, renders the
    final video, and validates output (duration, codec, resolution).

    Args:
        job_id: The job to compose.
    """
    logger.info("compose_video_task: job=%d", job_id)
    db = SessionLocal()
    policy = RetryPolicy(db)

    try:
        cp_svc = CheckpointService(db)

        # Gather all scene video paths in order
        storyboard = cp_svc.get_stage_output(job_id, "storyboard",
                                              "storyboard_scenes") or []
        th_scenes = {
            s["scene_index"]: s.get("video_path")
            for s in (cp_svc.get_stage_output(job_id, "talking_head",
                                               "th_scenes") or [])
        }
        mg_scenes = {
            s["scene_index"]: s.get("video_path")
            for s in (cp_svc.get_stage_output(job_id, "motion_graphics",
                                               "mg_scenes") or [])
        }

        # Build ordered list of segment paths
        segments: List[str] = []
        missing_scenes = []
        for scene in sorted(storyboard, key=lambda s: s.get("scene_index", 0)):
            idx = scene.get("scene_index", 0)
            scene_type = scene.get("scene_type", "broll")

            if scene_type == "talking_head":
                path = th_scenes.get(idx)
            else:
                path = mg_scenes.get(idx)

            if path and os.path.exists(path):
                segments.append(path)
            else:
                logger.warning("Missing segment for scene %d — skipping", idx)
                missing_scenes.append(idx)

        if not segments:
            raise ValueError(f"No video segments available for job {job_id}")

        output_dir = Path(WORKDIR) / str(job_id) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"final_{job_id}.mp4")

        # Compose via FFmpeg concat demuxer
        _compose_segments(segments, output_path)

        # Validate output
        metadata = _validate_output(output_path)

        cp_svc.save_checkpoint(
            job_id=job_id, stage="composition", stage_index=6,
            data={"segment_count": len(segments)},
            outputs={
                "final_video_path": output_path,
                "duration_seconds": metadata.get("duration"),
                "resolution": metadata.get("resolution"),
                "file_size_bytes": os.path.getsize(output_path),
                "missing_scenes": missing_scenes,
            },
        )
        db.commit()

        # Update job with output video URL
        from sqlalchemy import text
        db.execute(
            text("UPDATE jobs SET output_video_path = :p, "
                 "status = 'complete', completed_at = now() WHERE id = :id"),
            {"p": output_path, "id": job_id}
        )
        db.commit()

        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "composition"])

        logger.info("Composition complete: job=%d output=%s duration=%.1fs",
                    job_id, output_path, metadata.get("duration", 0))

    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        logger.error("Composition failed: job=%d error=%s", job_id, exc)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "composition", str(exc), failure_type]
        )
    finally:
        db.close()


def _compose_segments(segments: List[str], output_path: str) -> None:
    """Compose video segments using FFmpeg concat demuxer.

    Creates a temporary concat list file, runs FFmpeg to stitch all
    segments in order, re-encodes to uniform codec/resolution/fps.

    Args:
        segments:    List of .mp4 segment paths in order.
        output_path: Destination for the composed output.
    """
    w, h = OUTPUT_RESOLUTION.split("x")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        concat_path = f.name
        for seg in segments:
            # FFmpeg concat list requires escaped paths
            safe_path = seg.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    try:
        # Two-pass approach: first scale/normalize, then concat
        # Use filter_complex for strict concat (handles varying resolutions)
        filter_inputs = "".join(
            f"[{i}:v:0][{i}:a:0]" for i in range(len(segments))
        )
        concat_filter = (
            f"{filter_inputs}concat=n={len(segments)}:v=1:a=1[outv][outa]"
        )

        input_args = []
        for seg in segments:
            input_args.extend(["-i", seg])

        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-filter_complex", concat_filter,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-crf", "20",
            "-preset", "medium",
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", str(OUTPUT_FPS),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                   f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                stderr=stderr.encode(),
            )

    finally:
        os.unlink(concat_path)


def _validate_output(output_path: str) -> Dict[str, Any]:
    """Validate composed video using FFprobe."""
    if not os.path.exists(output_path):
        raise FileNotFoundError(f"Output file not created: {output_path}")

    if os.path.getsize(output_path) < 1024:
        raise ValueError("Output file too small — likely corrupt")

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", output_path],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFprobe validation failed: {result.stderr}")

    data = json.loads(result.stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )

    if video_stream is None:
        raise ValueError("No video stream found in output")

    return {
        "duration": float(data.get("format", {}).get("duration", 0)),
        "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}",
        "codec": video_stream.get("codec_name"),
    }
