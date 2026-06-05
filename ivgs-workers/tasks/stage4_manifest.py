"""
IVGS v5 — Stage 4: Composition Manifest Generation
====================================================

Celery task for building the composition manifest per §6.1 Stage 4.

This stage runs after media generation (Stage 3) completes. It:
1. Collects all generated assets (images, videos, animations)
2. Validates checksums against the storyboard specification
3. Builds a timeline layout with scene boundaries and layer assignments
4. Locks the manifest for downstream rendering stages

The manifest is the single source of truth for:
- Stage 7 (Prototype Draft)
- Stage 8 (Final Render)

Input:
- Locked storyboard (from Stage 2)
- All generated scene assets (from Stage 3)

Output:
- Composition manifest (JSONB in composition_manifests table)
- Manifest status: draft → locked

Queue: default (CPU-only, no GPU required)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

from celery import shared_task

from celery_app import celery_app
from models.task_result import PipelineStage

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.stage4_manifest.build_composition_manifest",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="default",
)
def build_composition_manifest(
    self: Any,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build and lock a composition manifest for the given job.

    §6.1 Stage 4 — Composition Manifest Generation:
    - Gathers all assets produced by Stage 3 (Media Generation)
    - Validates asset checksums against storyboard specs
    - Constructs timeline with scene boundaries and layer assignments
    - Locks the manifest (immutable after lock)

    Args:
        task_input_dict: Contains job_id, project_id, and stage context.

    Returns:
        Dict with manifest_id, status, and checksums for audit.
    """
    job_id = task_input_dict.get("job_id", "")
    project_id = task_input_dict.get("project_id", "")

    log = logger
    log.info(
        "stage4_manifest_start",
        extra={"job_id": job_id, "project_id": project_id},
    )

    start_time = time.monotonic()

    try:
        # Import service lazily to avoid circular imports at module load
        from services.manifest_builder import ManifestBuilder

        builder = ManifestBuilder()

        # Step 1: Collect assets for all scenes in this job
        log.info(
            "stage4_collecting_assets",
            extra={"job_id": job_id},
        )
        assets = builder.collect_assets(project_id=project_id, job_id=job_id)

        # Step 2: Validate checksums
        log.info(
            "stage4_validating_checksums",
            extra={"job_id": job_id, "asset_count": len(assets)},
        )
        validation = builder.validate_checksums(assets)
        if not validation.all_valid:
            raise ValueError(
                f"Checksum validation failed for {len(validation.failures)} assets: "
                f"{[f.asset_id for f in validation.failures]}"
            )

        # Step 3: Build the manifest
        log.info(
            "stage4_building_manifest",
            extra={"job_id": job_id},
        )
        manifest = builder.build_manifest(
            project_id=project_id,
            job_id=job_id,
            assets=assets,
        )

        # Step 4: Lock the manifest
        log.info(
            "stage4_locking_manifest",
            extra={"job_id": job_id, "manifest_id": str(manifest.id)},
        )
        locked = builder.lock_manifest(manifest_id=manifest.id)

        elapsed = time.monotonic() - start_time
        log.info(
            "stage4_manifest_complete",
            extra={
                "job_id": job_id,
                "manifest_id": str(locked.id),
                "duration_ms": locked.total_duration_ms,
                "scene_count": len(assets),
                "elapsed_s": round(elapsed, 2),
            },
        )

        output_dict = {
            "job_id": job_id,
            "project_id": project_id,
            "manifest_id": str(locked.id),
            "status": "locked",
            "total_duration_ms": locked.total_duration_ms,
            "checksum": locked.checksum,
            "scene_count": len(assets),
            "stage": PipelineStage.COMPOSITION_MANIFEST.value,
        }
        celery_app.send_task(
            "tasks.pipeline_orchestrator_v2.handle_stage_completion",
            kwargs={"stage_output_dict": output_dict},
            queue="default",
        )
        return output_dict

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        log.error(
            "stage4_manifest_failed",
            extra={
                "job_id": job_id,
                "error": str(exc),
                "elapsed_s": round(elapsed, 2),
            },
        )

        # Retry transient errors
        if self.request.retries < self.max_retries:
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
