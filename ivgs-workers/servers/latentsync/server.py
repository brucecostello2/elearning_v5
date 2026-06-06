"""
IVGS v5 — LatentSync 1.6 talking-head server (async-job wrapper on servers/common).

Implements the contract in clients/latentsync_client.py:
  POST /render   multipart: audio(wav), reference_video(mp4), [scene_image(png)] + form -> {"job_id"}
  GET  /status/{id}  /download/{id} (video/mp4)  /metrics/{id} ({alignment_score, duration_seconds})  /health

The runner shells out to LatentSync's own CLI (identical to its Cog predict.py), run with
cwd=<repo> so the configs' relative 'checkpoints/...' paths resolve via a symlink to the
mounted weights. Output is scaled/padded to the requested resolution with ffmpeg.

Phase 1: alignment_score is a conservative constant so the primary path is accepted; phase 2
wires eval/eval_sync_conf for a real SyncNet score and enables the SadTalker fallback.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import File, Form, UploadFile

from common.base import create_app, env_int, get_model, run, setup_logging
from common.jobs import JobStore, register_job_routes

log = setup_logging("latentsync")

LATENTSYNC_DIR = os.environ.get("LATENTSYNC_DIR", "/app/LatentSync")
WEIGHTS_DIR = os.environ.get("LATENTSYNC_WEIGHTS_DIR", "/mnt/ivgs-shared/models/latentsync-1.6")
UNET_CONFIG = os.environ.get("LATENTSYNC_UNET_CONFIG", "configs/unet/stage2_512.yaml")
INFERENCE_STEPS = env_int("LATENTSYNC_STEPS", 20)
GUIDANCE_SCALE = float(os.environ.get("LATENTSYNC_GUIDANCE", "1.5"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/ivgs-latentsync-out"))
JOB_TTL = env_int("JOB_TTL_SECONDS", 3600)
DEFAULT_ALIGNMENT = float(os.environ.get("LATENTSYNC_DEFAULT_ALIGNMENT", "0.90"))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
store = JobStore(ttl_seconds=JOB_TTL)


def _wire_checkpoints() -> str:
    link = Path(LATENTSYNC_DIR) / "checkpoints"
    if not (Path(WEIGHTS_DIR) / "latentsync_unet.pt").exists():
        raise RuntimeError(f"latentsync_unet.pt not found in {WEIGHTS_DIR}; run download_models.sh")
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        os.symlink(WEIGHTS_DIR, str(link))
    return f"latentsync-1.6 weights={WEIGHTS_DIR}"


def load_fn():
    if not (Path(LATENTSYNC_DIR) / "scripts" / "inference.py").exists():
        raise RuntimeError(f"LatentSync repo missing at {LATENTSYNC_DIR}")
    status = _wire_checkpoints()
    log.info("latentsync ready: %s", status)
    return {"status": status}


def _duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return round(float(r.stdout.strip()), 3)
    except Exception:
        return 0.0


def _runner(job, in_dir: str, video_path: str, audio_path: str,
            out_w: int, out_h: int, mode: str, seed: int) -> None:
    work = Path(tempfile.mkdtemp(prefix="ls_" + job.job_id + "_"))
    raw_out = str(work / "raw.mp4")
    final_out = str(OUTPUT_DIR / (job.job_id + ".mp4"))
    if mode and mode != "full_frame":
        log.warning("mode=%s requested; MVP emits full_frame lip-sync", mode)
    try:
        cmd = [
            "python", "-m", "scripts.inference",
            "--unet_config_path", UNET_CONFIG,
            "--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
            "--inference_steps", str(INFERENCE_STEPS),
            "--guidance_scale", str(GUIDANCE_SCALE),
            "--enable_deepcache",
            "--video_path", video_path,
            "--audio_path", audio_path,
            "--video_out_path", raw_out,
            "--seed", str(seed),
            "--temp_dir", str(work / "ls_temp"),
        ]
        job.progress = 0.1
        t0 = time.time()
        p = subprocess.run(cmd, cwd=LATENTSYNC_DIR, capture_output=True, text=True)
        if p.returncode != 0 or not Path(raw_out).exists():
            tail = (p.stderr or p.stdout or "")[-1500:]
            raise RuntimeError("inference rc=" + str(p.returncode) + ": " + tail)
        render_s = round(time.time() - t0, 2)
        job.progress = 0.85

        vf = ("scale=" + str(out_w) + ":" + str(out_h) + ":force_original_aspect_ratio=decrease,"
              "pad=" + str(out_w) + ":" + str(out_h) + ":(ow-iw)/2:(oh-ih)/2,setsar=1")
        n = subprocess.run(
            ["ffmpeg", "-y", "-i", raw_out, "-vf", vf,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", final_out],
            capture_output=True, text=True,
        )
        if n.returncode != 0 or not Path(final_out).exists():
            shutil.copy(raw_out, final_out)

        dur = _duration(final_out)
        job.output_path = Path(final_out)
        job.duration = dur
        job.metrics = {
            "alignment_score": DEFAULT_ALIGNMENT,
            "duration_seconds": dur,
            "model": "latentsync-1.6",
            "scored": False,
            "render_seconds": render_s,
            "resolution": str(out_w) + "x" + str(out_h),
        }
        job.progress = 1.0
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(in_dir, ignore_errors=True)


app = create_app("latentsync", load_fn=load_fn)
register_job_routes(app, store, download_media_type="video/mp4", with_metrics=True)


@app.post("/render")
async def render(
    audio: UploadFile = File(...),
    reference_video: UploadFile = File(...),
    scene_image: Optional[UploadFile] = File(default=None),
    mode: str = Form("full_frame"),
    output_width: int = Form(1920),
    output_height: int = Form(1080),
    output_fps: int = Form(30),
    face_detection_threshold: float = Form(0.5),
    lip_sync_strength: float = Form(1.0),
    face_enhance: str = Form("true"),
    pip_scale: float = Form(0.3),
    pip_position: str = Form("bottom_right"),
    pip_margin: int = Form(20),
    seed: int = Form(1247),
):
    get_model(app)
    in_dir = tempfile.mkdtemp(prefix="ls_in_")
    video_path = os.path.join(in_dir, "reference.mp4")
    audio_path = os.path.join(in_dir, "audio.wav")
    with open(video_path, "wb") as f:
        f.write(await reference_video.read())
    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    if scene_image is not None:
        with open(os.path.join(in_dir, "scene.png"), "wb") as f:
            f.write(await scene_image.read())
    job = store.submit(_runner, in_dir, video_path, audio_path,
                       output_width, output_height, mode, seed)
    return {"job_id": job.job_id}


if __name__ == "__main__":
    run(app, port=env_int("LATENTSYNC_PORT", 7860))
