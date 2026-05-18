"""Image generation Celery task with timeout, retry, and idempotency."""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.idempotency import IdempotencyGuard
from app.services.timeout_manager import TimeoutManager, TimeoutError
from app.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

WORKDIR = os.getenv("WORKDIR", "/mnt/workdir")
PROVIDER = os.getenv("IMAGE_PROVIDER", "dalle3")  # "dalle3" or "sdxl"


@shared_task(
    name="tasks.image_generation.generate_images_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def generate_images_task(self, job_id: int) -> None:
    """Generate still images for all scenes in a job.

    Reads storyboard from checkpoint. For each scene, generates an image
    using the configured provider (DALL-E 3 or SDXL). Saves image paths
    to 'image_gen' checkpoint. Uses idempotency guard to skip scenes
    with existing valid outputs.

    Args:
        job_id: The job to process.
    """
    logger.info("generate_images_task: job=%d provider=%s", job_id, PROVIDER)
    db = SessionLocal()
    tm = TimeoutManager()
    policy = RetryPolicy(db)

    try:
        cp_svc = CheckpointService(db)
        storyboard = cp_svc.get_stage_output(job_id, "storyboard",
                                              "storyboard_scenes")
        if not storyboard:
            raise ValueError(f"Storyboard checkpoint missing for job {job_id}")

        output_dir = Path(WORKDIR) / str(job_id) / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        scene_image_paths: List[Dict[str, Any]] = []
        all_success = True

        for scene in storyboard:
            scene_idx = scene.get("scene_index", 0)
            prompt = scene.get("image_prompt", "")
            style = scene.get("image_style", "photorealistic")
            output_path = str(output_dir / f"scene_{scene_idx:03d}.png")

            params = {
                "prompt": prompt,
                "style": style,
                "provider": PROVIDER,
                "output_path": output_path,
            }

            guard = IdempotencyGuard(db)
            try:
                result = guard.check_or_execute(
                    job_id=job_id,
                    stage=f"image_gen_scene_{scene_idx}",
                    stage_index=2,
                    params=params,
                    executor=lambda p=prompt, s=style, o=output_path:
                        _generate_image(p, s, o, tm),
                    validate=lambda r: os.path.exists(r.get("image_path", "")),
                )
                scene_image_paths.append({
                    "scene_index": scene_idx,
                    "image_path": result["image_path"],
                    "provider": PROVIDER,
                })
            except Exception as exc:
                logger.error("Image gen failed: scene=%d error=%s",
                             scene_idx, exc)
                all_success = False
                # Store placeholder so pipeline can continue with fallback
                scene_image_paths.append({
                    "scene_index": scene_idx,
                    "image_path": None,
                    "error": str(exc),
                })

        # Save aggregate results to image_gen checkpoint
        cp_svc.save_checkpoint(
            job_id=job_id,
            stage="image_gen",
            stage_index=2,
            data={"provider": PROVIDER, "scene_count": len(storyboard)},
            outputs={
                "scene_images": scene_image_paths,
                "success_count": sum(1 for s in scene_image_paths
                                     if s["image_path"]),
                "all_success": all_success,
            },
        )
        db.commit()

        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "image_gen"])

    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        logger.error("image_generation_task failed: job=%d error=%s", job_id, exc)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "image_gen", str(exc), failure_type]
        )
    finally:
        db.close()


def _generate_image(
    prompt: str,
    style: str,
    output_path: str,
    tm: TimeoutManager,
) -> Dict[str, Any]:
    """Generate a single image using configured provider."""
    if PROVIDER == "dalle3":
        return _generate_dalle3(prompt, style, output_path, tm)
    else:
        return _generate_sdxl(prompt, style, output_path, tm)


def _generate_dalle3(
    prompt: str,
    style: str,
    output_path: str,
    tm: TimeoutManager,
) -> Dict[str, Any]:
    """Generate image using DALL-E 3 API."""
    import openai
    import requests

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    enhanced_prompt = f"{prompt}. Style: {style}. High quality, detailed, cinematic."

    def _call():
        return client.images.generate(
            model="dall-e-3",
            prompt=enhanced_prompt,
            size="1792x1024",
            quality="hd",
            n=1,
        )

    response = tm.call_with_timeout(
        _call, model="dalle", operation="generation", timeout_seconds=300
    )

    image_url = response.data[0].url
    img_data = requests.get(image_url, timeout=60).content
    IdempotencyGuard.atomic_write(img_data, output_path)

    return {"image_path": output_path, "size": "1792x1024", "provider": "dalle3"}


def _generate_sdxl(
    prompt: str,
    style: str,
    output_path: str,
    tm: TimeoutManager,
) -> Dict[str, Any]:
    """Generate image using local SDXL via vLLM or ComfyUI endpoint."""
    import requests

    sdxl_url = os.getenv("SDXL_ENDPOINT", "http://node-04:7860")

    def _call():
        payload = {
            "prompt": f"{prompt}. {style} style, 8K, highly detailed.",
            "negative_prompt": "blurry, low quality, watermark",
            "width": 1792, "height": 1024,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
        }
        r = requests.post(f"{sdxl_url}/sdapi/v1/txt2img", json=payload,
                          timeout=300)
        r.raise_for_status()
        return r.json()

    resp = tm.call_with_timeout(
        _call, model="sdxl", operation="generation", timeout_seconds=300
    )

    img_bytes = base64.b64decode(resp["images"][0])
    IdempotencyGuard.atomic_write(img_bytes, output_path)
    return {"image_path": output_path, "size": "1792x1024", "provider": "sdxl"}
