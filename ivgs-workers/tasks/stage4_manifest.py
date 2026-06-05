"""
IVGS v5 — Stage 4: Composition Manifest Generation
====================================================

Celery task for building the composition manifest per §6.1 Stage 4 / §5.2.5.

The composition manifest is built **server-side by the Pipeline API**: the API
collects the locked storyboard and the generated, scene-linked Stage-3 assets,
assembles the timeline, and persists it to composition_manifests. This task is a
thin, idempotent driver that calls the API's manifest endpoints with the
pipeline service token:

    GET  /api/v1/jobs/{id}/manifest            (reuse if present)
    POST /api/v1/jobs/{id}/manifest/generate   (build draft from storyboard+assets)
    POST /api/v1/jobs/{id}/manifest/validate   (verify asset refs + checksums)
    POST /api/v1/jobs/{id}/manifest/lock        (freeze timeline)

Queue: default (CPU-only, no GPU required).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

import httpx

from celery import shared_task

from celery_app import celery_app
from config import WorkerConfig
from models.task_result import PipelineStage

logger = logging.getLogger(__name__)


def _check(resp: httpx.Response, step: str) -> Dict[str, Any]:
    """2xx -> JSON; 4xx -> ValueError (deterministic); 5xx -> RuntimeError (transient)."""
    if resp.status_code in (200, 201):
        return resp.json()
    if 400 <= resp.status_code < 500:
        raise ValueError(f"manifest {step} rejected: HTTP {resp.status_code} — {resp.text[:300]}")
    raise RuntimeError(f"manifest {step} failed: HTTP {resp.status_code} — {resp.text[:300]}")


async def _drive_manifest(job_id: str, config: WorkerConfig) -> Dict[str, Any]:
    """
    Drive the API manifest lifecycle: (reuse | generate) -> validate -> lock.

    Idempotent and retry-safe: an already-locked manifest is returned as-is, and
    an existing draft is reused rather than re-generated (composition_manifests
    is UNIQUE per job, so a second generate would conflict).
    """
    base = f"{config.pipeline_api.full_base_url}/jobs/{job_id}/manifest"
    headers = {"Authorization": f"Bearer {config.pipeline_api.service_token}"}

    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        existing = await client.get(base)
        if existing.status_code == 200:
            manifest = existing.json()
            if manifest.get("status") == "locked":
                return manifest  # already complete
        elif existing.status_code == 404:
            manifest = _check(await client.post(f"{base}/generate", json={}), "generate")
        elif 400 <= existing.status_code < 500:
            raise ValueError(
                f"manifest lookup rejected: HTTP {existing.status_code} — {existing.text[:300]}"
            )
        else:
            raise RuntimeError(f"manifest lookup failed: HTTP {existing.status_code}")

        validation = _check(await client.post(f"{base}/validate", json={}), "validate")
        if not validation.get("valid", False):
            errors = validation.get("errors", [])
            raise ValueError(f"manifest validation failed: {len(errors)} error(s): {errors[:5]}")

        return _check(await client.post(f"{base}/lock", json={}), "lock")


@shared_task(
    name="tasks.stage4_manifest.build_composition_manifest",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="default",
)
def build_composition_manifest(self: Any, task_input_dict: Dict[str, Any]) -> Dict[str, Any]:
    """§6.1 Stage 4 — build + lock the composition manifest via the Pipeline API (§5.2.5)."""
    job_id = task_input_dict.get("job_id", "")
    project_id = task_input_dict.get("project_id", "")
    config = WorkerConfig()

    logger.info("stage4_manifest_start", extra={"job_id": job_id, "project_id": project_id})
    start_time = time.monotonic()

    try:
        loop = asyncio.new_event_loop()
        try:
            manifest = loop.run_until_complete(_drive_manifest(job_id, config))
        finally:
            loop.close()

        logger.info(
            "stage4_manifest_complete",
            extra={
                "job_id": job_id,
                "manifest_id": manifest.get("id"),
                "status": manifest.get("status"),
                "scene_count": manifest.get("scene_count"),
                "total_duration_ms": manifest.get("total_duration_ms"),
                "elapsed_s": round(time.monotonic() - start_time, 2),
            },
        )

        output_dict = {
            "job_id": job_id,
            "project_id": project_id,
            "manifest_id": manifest.get("id", ""),
            "status": manifest.get("status", "locked"),
            "total_duration_ms": manifest.get("total_duration_ms", 0),
            "scene_count": manifest.get("scene_count", 0),
            "stage": PipelineStage.COMPOSITION_MANIFEST.value,
        }
        celery_app.send_task(
            "tasks.pipeline_orchestrator_v2.handle_stage_completion",
            kwargs={"stage_output_dict": output_dict},
            queue="default",
        )
        return output_dict

    except Exception as exc:
        logger.error(
            "stage4_manifest_failed",
            extra={
                "job_id": job_id,
                "error": str(exc),
                "elapsed_s": round(time.monotonic() - start_time, 2),
            },
        )
        # Retry transient failures (5xx / network). Deterministic failures
        # (4xx, validation) are ValueError -> fail the job without retrying.
        if not isinstance(exc, ValueError) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        output_dict = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "failed",
            "error": str(exc),
            "stage": PipelineStage.COMPOSITION_MANIFEST.value,
        }
        celery_app.send_task(
            "tasks.pipeline_orchestrator_v2.handle_stage_completion",
            kwargs={"stage_output_dict": output_dict},
            queue="default",
        )
        return output_dict
