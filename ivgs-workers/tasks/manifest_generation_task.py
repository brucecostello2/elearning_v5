"""Manifest generation and locking task.

Called by the orchestrator after all asset generation stages complete.
Generates manifest from checkpoints, validates timing, locks it,
and then plans + dispatches segment rendering tasks.
"""

import logging
from celery import shared_task, group

from app.database import get_db_context
from app.services.manifest_service import ManifestService
from app.services.timeline_authority import TimelineAuthority
from app.services.segment_renderer import SegmentRenderer

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.manifest_generation_task.generate_manifest_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
    acks_late=True,
)
def generate_manifest_task(self, job_id: str) -> dict:
    """Build, validate, and lock the composition manifest for a job.

    After locking, plans render segments and dispatches segment tasks.
    """
    logger.info("Generating manifest for job %s", job_id)

    with get_db_context() as db:
        manifest_svc = ManifestService(db)
        timeline_auth = TimelineAuthority(db)
        segment_renderer = SegmentRenderer(db)

        try:
            # Step 1: Generate draft manifest
            manifest = manifest_svc.generate_manifest(job_id)
            logger.info(
                "Manifest draft: %d scenes, %dms total",
                len(manifest.get_timeline().get('scenes', [])),
                manifest.total_duration_ms
            )

            # Step 2: Validate all timing
            timing_report = timeline_auth.validate_all_timing(job_id)
            rejected = timing_report.get('rejected', [])
            if rejected:
                raise ValueError(
                    f"Manifest validation failed — {len(rejected)} scenes "
                    f"have unacceptable timing drift: "
                    f"{[r['scene_id'] for r in rejected]}"
                )

            flagged = timing_report.get('flagged', [])
            if flagged:
                logger.warning(
                    "Manifest has %d flagged timing scenes (proceeding): %s",
                    len(flagged), [f['scene_id'] for f in flagged]
                )

            # Step 3: Lock manifest
            manifest = manifest_svc.lock_manifest(job_id)
            logger.info(
                "Manifest locked: job=%s checksum=%s",
                job_id, manifest.checksum
            )

            # Step 4: Plan render segments
            segments = segment_renderer.plan_segments(job_id)
            logger.info(
                "Planned %d render segments for job %s",
                len(segments), job_id
            )

            # Step 5: Dispatch segment render tasks
            from tasks.segment_render_task import render_segment_task
            task_group = group(
                render_segment_task.s(job_id, seg.segment_index)
                for seg in segments
            )
            task_group.apply_async()

            return {
                "status": "locked",
                "job_id": job_id,
                "total_duration_ms": manifest.total_duration_ms,
                "segment_count": len(segments),
                "checksum": manifest.checksum,
            }

        except Exception as exc:
            logger.error("Manifest generation failed for %s: %s", job_id, exc)
            try:
                self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                return {"status": "failed", "error": str(exc)}
