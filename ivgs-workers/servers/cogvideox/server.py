"""
IVGS v5 — CogVideoX / Wan2.1 Model Server (REFERENCE WRAPPER)

Async-job HTTP server matching the deployed cogvideox_client.py contract:
  POST /generate          -> {"job_id"}
  GET  /status/{job_id}   -> {"status","duration","error"}
  GET  /download/{job_id} -> raw mp4 bytes
  GET  /health            -> 200 when model loaded, else 503
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import numpy as np

MODEL_VARIANT = os.environ.get("MODEL_VARIANT", "cogvideox")
MODEL_PATH = os.environ.get("MODEL_PATH", "/mnt/models/cogvideox-5b")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/ivgs-video-out"))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))
DEVICE = os.environ.get("DEVICE", "cuda")
PORT = int(os.environ.get("PORT", "8200"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cogvideox-server")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    num_frames: int = Field(default=49, le=49)
    width: int = 720
    height: int = 480
    fps: int = 24
    guidance_scale: float = 6.0
    num_inference_steps: int = 50
    seed: Optional[int] = None


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.pending
    created_at: float = field(default_factory=time.time)
    duration: float = 0.0
    output_path: Optional[Path] = None
    error: Optional[str] = None


JOBS: dict[str, Job] = {}
app = FastAPI(title=f"IVGS {MODEL_VARIANT} model server")
_MODEL: Any = None


def load_model() -> Any:
    import torch

    if MODEL_VARIANT == "cogvideox":
        from diffusers import CogVideoXPipeline

        pipe = CogVideoXPipeline.from_pretrained(MODEL_PATH, torch_dtype=torch.bfloat16)
        pipe.to(DEVICE)
        pipe.vae.enable_tiling()
        logger.info("CogVideoX pipeline loaded from %s", MODEL_PATH)
        return pipe

    if MODEL_VARIANT == "wan21":
        # IMPLEMENT-ON-NODE: confirm the exact Wan2.1 diffusers class + repo before enabling.
        logger.warning("wan21 load not implemented — verify diffusers class on-node")
        return None

    logger.error("unknown MODEL_VARIANT=%s", MODEL_VARIANT)
    return None


# ---------------------------------------------------------------------------
# ENCODE — pinned explicitly, because the vendored default is NOT composable.
#
# RC-M5. This server used to hand frames to `diffusers.utils.export_to_video`
# and accept whatever it produced. What it produced was **mpeg4**, which stage
# 7's codec allowlist (`ivgs-workers/utils/video_validator.py:85` —
# h264/h265/hevc/vp9) correctly refuses, so every video_clip scene rendered
# here was rejected before upload and its scene reached composition with no
# background layer.
#
# The mpeg4 is NOT ours and never was — it is a vendored dependency's default,
# reached down a branch we never knew we were on:
#
#   diffusers/utils/export_utils.py:168  `if not is_imageio_available():`
#                                :176    `return _legacy_export_to_video(...)`
#                                :130    `fourcc = cv2.VideoWriter_fourcc(*"mp4v")`
#
# `mp4v` is MPEG-4 Part 2 == `mpeg4`. We land on that branch because the
# `imageio` PACKAGE is absent from this image: `requirements.txt` asks for
# `imageio-ffmpeg`, which is only the ffmpeg BINARY wheel and does not satisfy
# `is_imageio_available()`. Measured in the running cogvideox-pilot-1 image:
# diffusers 0.38.0, imageio-ffmpeg 0.6.0, opencv-python-headless 4.13.0.92,
# `is_imageio_available() = False`.
#
# Merely `pip install imageio` would also stop the mpeg4 — the other branch
# defaults to h264 — but it would be an accident, one `pip` resolution away
# from silently reverting, and it would still leave pix_fmt and faststart to a
# library default. So we do not call `export_to_video` at all. We drive
# imageio-ffmpeg ourselves and name every parameter that composition depends on.
#
# Do NOT "fix" this by widening the allowlist or transcoding at composition.
# The allowlist is right; the producer was wrong. This is the producer.
VIDEO_CODEC = "libx264"      # -> ffprobe codec_name "h264"
VIDEO_PIX_FMT = "yuv420p"    # the 4:2:0 profile every downstream player/filter assumes
VIDEO_QUALITY = 8.0          # imageio-ffmpeg 1..10 -> -crf 10 at 8.0 (visually near-lossless)


def _frames_to_uint8_rgb(frames: Any) -> "list[np.ndarray]":
    """Normalise pipeline output (PIL images, or float/uint8 arrays) to uint8 RGB.

    diffusers' own exporter assumes any ndarray is float 0..1 and multiplies by
    255 unconditionally, which destroys an already-uint8 frame. We branch on
    dtype instead.
    """
    out: list[np.ndarray] = []
    for frame in frames:
        arr = frame if isinstance(frame, np.ndarray) else np.asarray(frame)
        if arr.dtype != np.uint8:
            arr = (np.clip(arr, 0.0, 1.0) * 255.0).round().astype(np.uint8)
        if arr.ndim == 3 and arr.shape[2] == 4:   # RGBA -> RGB
            arr = arr[:, :, :3]
        out.append(np.ascontiguousarray(arr))
    return out


def _probe_codec(path: Path) -> str:
    """ffprobe the file we just wrote. Returns codec_name, or '' if unprobeable."""
    import subprocess

    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        return proc.stdout.strip().lower()
    except Exception:  # noqa: BLE001 - probe failure must not mask the encode
        logger.exception("ffprobe failed for %s", path)
        return ""


def encode_h264(frames: Any, out_path: Path, fps: int) -> None:
    """Encode frames to a composable H.264 mp4: yuv420p, +faststart.

    Every parameter the allowlist and the compositor care about is named here,
    not inherited. Asserts the result so a wrong codec fails the JOB rather than
    travelling downstream to be rejected at stage 7 — where the cost is a whole
    draft, not one render.
    """
    import imageio_ffmpeg

    norm = _frames_to_uint8_rgb(frames)
    if not norm:
        raise RuntimeError("encode_h264: pipeline returned zero frames")

    height, width = norm[0].shape[:2]

    writer = imageio_ffmpeg.write_frames(
        str(out_path),
        (width, height),
        pix_fmt_in="rgb24",
        pix_fmt_out=VIDEO_PIX_FMT,
        fps=fps,
        codec=VIDEO_CODEC,
        quality=VIDEO_QUALITY,
        macro_block_size=16,       # pad odd dimensions; yuv420p cannot do odd
        ffmpeg_log_level="warning",
        output_params=[
            "-movflags", "+faststart",   # moov atom first: streamable, seekable
            "-profile:v", "high",
            "-level", "4.0",
        ],
    )
    writer.send(None)              # prime the generator (spawns ffmpeg)
    try:
        for frame in norm:
            writer.send(frame.tobytes())
    finally:
        writer.close()

    actual = _probe_codec(out_path)
    if actual and actual != "h264":
        raise RuntimeError(
            f"encode produced codec '{actual}', expected 'h264' — "
            f"refusing to publish a video stage 7 will reject"
        )
    logger.info(
        "encoded %s: %dx%d @%dfps codec=%s pix_fmt=%s faststart=yes (probed: %s)",
        out_path.name, width, height, fps, VIDEO_CODEC, VIDEO_PIX_FMT, actual or "unprobed",
    )


def run_generation(job: Job, req: GenerateRequest) -> None:
    t0 = time.time()
    try:
        job.status = JobStatus.processing
        if _MODEL is None:
            raise RuntimeError(f"model not loaded for variant={MODEL_VARIANT}")

        import torch

        generator = (
            torch.Generator(device=DEVICE).manual_seed(req.seed)
            if req.seed is not None
            else None
        )
        result = _MODEL(
            prompt=req.prompt,
            num_videos_per_prompt=1,
            num_frames=req.num_frames,
            num_inference_steps=req.num_inference_steps,
            guidance_scale=req.guidance_scale,
            generator=generator,
        )
        frames = result.frames[0]

        out_path = OUTPUT_DIR / f"{job.job_id}.mp4"
        encode_h264(frames, out_path, fps=req.fps)

        job.output_path = out_path
        job.duration = round(req.num_frames / max(req.fps, 1), 2)
        job.status = JobStatus.completed
        logger.info("job %s completed in %.1fs", job.job_id, time.time() - t0)
    except Exception as exc:
        job.status = JobStatus.failed
        job.error = str(exc)
        logger.exception("job %s failed", job.job_id)


def _gc_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for jid in [j for j, job in JOBS.items() if job.created_at < cutoff]:
        job = JOBS.pop(jid)
        if job.output_path and job.output_path.exists():
            try:
                job.output_path.unlink()
            except OSError:
                pass


@app.on_event("startup")
async def _startup() -> None:
    global _MODEL
    logger.info("loading model variant=%s from %s", MODEL_VARIANT, MODEL_PATH)
    _MODEL = load_model()


@app.get("/health")
async def health() -> JSONResponse:
    ok = _MODEL is not None
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "healthy" if ok else "model_not_loaded", "variant": MODEL_VARIANT},
    )


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict[str, str]:
    _gc_jobs()
    job = Job(job_id=str(uuid.uuid4()))
    JOBS[job.job_id] = job
    asyncio.get_event_loop().run_in_executor(None, run_generation, job, req)
    return {"job_id": job.job_id}


@app.get("/status/{job_id}")
async def status(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    return {"status": job.status.value, "duration": job.duration, "error": job.error}


@app.get("/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    if job.status is not JobStatus.completed or not job.output_path:
        raise HTTPException(status_code=409, detail=f"job not ready: {job.status.value}")
    if not job.output_path.exists():
        raise HTTPException(status_code=410, detail="output expired")
    return FileResponse(str(job.output_path), media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
