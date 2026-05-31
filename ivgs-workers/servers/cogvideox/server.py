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


def run_generation(job: Job, req: GenerateRequest) -> None:
    t0 = time.time()
    try:
        job.status = JobStatus.processing
        if _MODEL is None:
            raise RuntimeError(f"model not loaded for variant={MODEL_VARIANT}")

        import torch
        from diffusers.utils import export_to_video

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
        export_to_video(frames, str(out_path), fps=req.fps)

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
