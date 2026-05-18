"""Celery task for AI video generation with GPU scheduling + fallback."""
import os
import time
import logging
from typing import Optional, Dict, Any
from celery import Task
from ivgs_workers.celeryconfig import app as celery_app
from app.services.video_fallback_chain import VideoFallbackChain
from app.services.cogvideox_service import CogVideoXService
from app.services.wan21_service import Wan21Service
from app.services.timeout_manager import TimeoutManager
from app.services.corruption_detector import CorruptionDetector
from app.services.quality_validator import QualityValidator
from app.middleware.checkpoint import CheckpointService

logger = logging.getLogger(__name__)

SCHEDULER_URL = os.environ.get("SCHEDULER_URL", "http://node-01:8001")
COGVIDEOX_MODEL_PATH = os.environ.get("COGVIDEOX_MODEL_PATH", "")
WAN21_MODEL_PATH = os.environ.get("WAN21_MODEL_PATH", "")
WORKDIR = os.environ.get("WORKDIR", "/mnt/workdir")


def _build_fallback_chain(gpu_device: str) -> VideoFallbackChain:
    timeout_mgr = TimeoutManager()
    corruption = CorruptionDetector()
    cogvideox = CogVideoXService(
        model_path=COGVIDEOX_MODEL_PATH,
        timeout_manager=timeout_mgr,
        corruption_detector=corruption,
        device=gpu_device,
    )
    wan21 = Wan21Service(
        model_path=WAN21_MODEL_PATH,
        timeout_manager=timeout_mgr,
        corruption_detector=corruption,
        device=gpu_device,
    )
    return VideoFallbackChain(
        cogvideox=cogvideox,
        wan21=wan21,
    )


@celery_app.task(
    name="tasks.generate_ai_video",
    queue="gpu_video",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=1,
    default_retry_delay=60,
    time_limit=2400,   # Hard kill after 40 min
    soft_time_limit=2100,
)
def generate_ai_video_task(
    job_id: str,
    scene_id: str,
    prompt: str,
    model_preference: str = "cogvideox",
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate AI video for a single scene.
    1. Request GPU allocation from scheduler
    2. Build fallback chain on the allocated GPU
    3. Run L1→L4 chain
    4. Quality-score the result
    5. Checkpoint success / mark failure
    """
    params = params or {}
    duration_s = params.get("duration_s", 5)
    resolution = params.get("resolution", "720p")
    scene_type = params.get("scene_type", "broll")
    seed = params.get("seed", None)

    output_path = os.path.join(WORKDIR, job_id, "ai_video",
                               f"{scene_id}.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ── Step 1: Request GPU reservation ─────────────────────────────
    import requests as req
    gpu_device = "cuda:0"
    reservation_id = None
    try:
        resp = req.post(f"{SCHEDULER_URL}/schedule", json={
            "job_id": job_id,
            "model_name": model_preference,
            "vram_requirement_mb": 24576,
            "estimated_duration_s": duration_s + 120,
        }, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            gpu_device = f"cuda:{data.get('gpu_index', 0)}"
            reservation_id = data.get("reservation_id")
            logger.info("GPU allocated: %s (reservation=%s)",
                        gpu_device, reservation_id)
        else:
            logger.warning("Scheduler unavailable (%d) — using cuda:0",
                           resp.status_code)
    except Exception as exc:
        logger.warning("Scheduler request failed: %s — using cuda:0", exc)

    # ── Step 2: Build chain and run ──────────────────────────────────
    try:
        chain = _build_fallback_chain(gpu_device)
        t0 = time.monotonic()
        result = chain.execute(
            job_id=job_id,
            scene_id=scene_id,
            prompt=prompt,
            output_path=output_path,
            scene_type=scene_type,
            duration_s=duration_s,
            resolution=resolution,
            seed=seed,
        )
        elapsed = time.monotonic() - t0
        logger.info("Fallback chain complete in %.1fs: level=%d",
                    elapsed, result["level_used"])
    except Exception as exc:
        logger.error("Fallback chain crashed: %s", exc)
        result = {"output_path": None, "level_used": 0,
                  "fallback_reason": str(exc)}
    finally:
        # ── Release GPU reservation ─────────────────────────────────
        if reservation_id:
            try:
                req.delete(
                    f"{SCHEDULER_URL}/reservations/{reservation_id}",
                    timeout=10)
            except Exception:
                pass

    # ── Step 3: Quality validation ───────────────────────────────────
    output = result.get("output_path")
    quality_score = None
    if output and os.path.exists(output):
        try:
            validator = QualityValidator()
            quality_score = validator.validate_video(
                asset_id=None, video_path=output)
            logger.info("Quality score: %.3f", quality_score or 0)
        except Exception as exc:
            logger.warning("Quality validation skipped: %s", exc)

    # ── Step 4: Checkpoint ───────────────────────────────────────────
    cp_service = CheckpointService()
    if output and os.path.exists(output):
        cp_service.save_checkpoint(
            job_id=job_id,
            stage=f"ai_video_{scene_id}",
            data={
                "level_used": result["level_used"],
                "model_used": result.get("model_used", "unknown"),
                "fallback_reason": result.get("fallback_reason"),
                "quality_score": quality_score,
            },
            outputs={"video_path": output},
        )
        return {
            "success": True,
            "output_path": output,
            "level_used": result["level_used"],
            "quality_score": quality_score,
        }
    else:
        cp_service.save_checkpoint(
            job_id=job_id,
            stage=f"ai_video_{scene_id}",
            data={"error": result.get("fallback_reason", "unknown")},
            outputs={},
            status="failed",
        )
        raise RuntimeError(
            f"AI video generation failed for scene {scene_id}: "
            f"{result.get('fallback_reason')}")
