"""Transcript refinement Celery task."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from celery import shared_task

from app.database import SessionLocal
from app.middleware.checkpoint import CheckpointService
from app.services.idempotency import IdempotencyGuard
from app.services.timeout_manager import TimeoutManager, TimeoutError
from app.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

# OpenAI client (initialised lazily)
_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        import openai
        _openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


REFINEMENT_PROMPT = """You are a video script editor. Refine the following raw transcript
into a polished instructional video script. Return a JSON object with:
{
  "scenes": [
    {
      "index": 0,
      "scene_type": "intro|talking_head|broll|title_card|action",
      "narration": "...",
      "visual_description": "...",
      "duration_seconds": 15.0,
      "transition": "cut|fade|dissolve"
    }
  ],
  "total_duration_seconds": 180.0,
  "title": "...",
  "target_audience": "..."
}
Only return the JSON object, no other text."""


@shared_task(
    name="tasks.transcript.refine_transcript_task",
    bind=True,
    acks_late=True,
    max_retries=0,  # Retry handled by orchestrator
)
def refine_transcript_task(self, job_id: int) -> None:
    """Refine raw transcript using GPT-4o and save as checkpoint.

    Fetches raw transcript from jobs table, calls GPT-4o with structured
    output schema, parses JSON response, and saves to pipeline checkpoint.

    Args:
        job_id: The job to process.
    """
    logger.info("refine_transcript_task: job=%d", job_id)
    db = SessionLocal()
    tm = TimeoutManager()
    policy = RetryPolicy(db)

    try:
        # Fetch raw transcript from jobs table
        from sqlalchemy import text
        row = db.execute(
            text("SELECT raw_transcript FROM jobs WHERE id = :id"),
            {"id": job_id}
        ).first()
        if not row or not row[0]:
            raise ValueError(f"No raw_transcript found for job {job_id}")

        raw_transcript = row[0]
        params = {"raw_transcript": raw_transcript, "job_id": job_id}

        guard = IdempotencyGuard(db)
        output_refs = guard.check_or_execute(
            job_id=job_id,
            stage="transcript",
            stage_index=0,
            params=params,
            executor=lambda: _execute_refinement(raw_transcript, tm),
        )

        logger.info("Transcript refined: job=%d scenes=%d",
                    job_id, len(output_refs.get("scenes", [])))

        # Advance pipeline to next stage
        from tasks.orchestrator_task import stage_completed_task
        stage_completed_task.apply_async(args=[job_id, "transcript"])

    except TimeoutError as exc:
        failure_type = "transient"
        logger.error("Transcript timeout: job=%d error=%s", job_id, exc)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "transcript", str(exc), failure_type]
        )
    except Exception as exc:
        failure_type = policy.classify_failure(exc)
        logger.error("Transcript failed: job=%d error=%s type=%s",
                     job_id, exc, failure_type)
        from tasks.orchestrator_task import stage_failed_task
        stage_failed_task.apply_async(
            args=[job_id, "transcript", str(exc), failure_type]
        )
    finally:
        db.close()


def _execute_refinement(raw_transcript: str, tm: TimeoutManager) -> Dict[str, Any]:
    """Call GPT-4o and parse structured scene output."""
    client = _get_openai()

    def _call() -> str:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": REFINEMENT_PROMPT},
                {"role": "user", "content": raw_transcript},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=4096,
        )
        return response.choices[0].message.content

    raw_json = tm.call_with_timeout(
        _call,
        model="gpt4o",
        operation="transcript",
        timeout_seconds=120,
    )

    parsed = json.loads(raw_json)
    return {
        "scenes": parsed.get("scenes", []),
        "total_duration_seconds": parsed.get("total_duration_seconds", 0),
        "title": parsed.get("title", ""),
        "target_audience": parsed.get("target_audience", ""),
        "raw_json": raw_json,
    }
