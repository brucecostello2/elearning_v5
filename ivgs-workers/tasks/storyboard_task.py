"""Storyboard generation Celery task."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.idempotency import IdempotencyGuard
from app.services.timeout_manager import TimeoutManager, TimeoutError
from app.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

STORYBOARD_PROMPT = """Create a detailed visual storyboard from the following scene data.
For each scene provide:
{
  "scene_index": 0,
  "image_prompt": "Detailed DALL-E image generation prompt (100-200 words)",
  "image_style": "photorealistic|illustration|diagram|mixed",
  "motion_effect": "ken_burns|zoom_in|zoom_out|pan_left|pan_right|static",
  "motion_intensity": "subtle|moderate|dramatic",
  "duration_seconds": 15.0,
  "caption_text": "Short display caption (max 80 chars)"
}
Return JSON array of scene objects. No other text."""


@shared_task(
    name="tasks.storyboard.generate_storyboard_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def generate_storyboard_task(self, job_id: int) -> None:
    """Generate a visual storyboard from refined transcript scenes.

    Reads scene data from the 'transcript' checkpoint, generates detailed
    image prompts and motion effect specifications for each scene, saves
    storyboard JSON to the 'storyboard' checkpoint.

    Args:
        job_id: The job to process.
    """
    logger.info("generate_storyboard_task: job=%d", job_id)
    db = SessionLocal()
    tm = TimeoutManager()
    policy = RetryPolicy(db)

    try:
        cp_svc = CheckpointService(db)
        transcript_outputs = cp_svc.get_stage_output(job_id, "transcript", "scenes")
        if not transcript_outputs:
            raise ValueError(f"Transcript checkpoint missing for job {job_id}")

        params = {"scenes": transcript_outputs, "job_id": job_id}

        guard = IdempotencyGuard(db)
        output_refs = guard.check_or_execute(
            job_id=job_id,
            stage="storyboard",
            stage_index=1,
            params=params,
            executor=lambda: _generate_storyboard(transcript_outputs, tm),
        )

        logger.info("Storyboard generated: job=%d scenes=%d",
                    job_id, len(output_refs.get("storyboard_scenes", [])))

        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "storyboard"])

    except TimeoutError as exc:
        _fail(job_id, "storyboard", str(exc), "transient")
    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        _fail(job_id, "storyboard", str(exc), failure_type)
    finally:
        db.close()


def _generate_storyboard(
    scenes: List[Dict[str, Any]],
    tm: TimeoutManager,
) -> Dict[str, Any]:
    """Call GPT-4o to produce detailed storyboard from scene descriptions."""
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    scenes_json = json.dumps(scenes, indent=2)

    def _call():
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": STORYBOARD_PROMPT},
                {"role": "user", "content": scenes_json},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=8192,
        )
        return resp.choices[0].message.content

    raw = tm.call_with_timeout(_call, model="gpt4o", operation="storyboard",
                                timeout_seconds=120)
    parsed = json.loads(raw)
    storyboard_scenes = parsed if isinstance(parsed, list) else parsed.get("scenes", [])
    return {
        "storyboard_scenes": storyboard_scenes,
        "scene_count": len(storyboard_scenes),
    }


def _fail(job_id: int, stage: str, error: str, failure_type: str) -> None:
    logger.error("%s failed: job=%d error=%s", stage, job_id, error)
    from tasks.orchestrator_task import stage_failed_task
    stage_failed_task.apply_async(args=[job_id, stage, error, failure_type])
