"""Individual segment rendering task.

Each segment is a 30-second chunk of the final video rendered
independently by a composition worker. Allows segment-level retry
without full recomposition.

Queue: composition (runs on node-01 which has access to all assets via NFS)
"""

import logging
from celery import shared_task

from app.database import get_db_context
from app.services.segment_renderer import SegmentRenderer
from app.services.render_progress import RenderProgressTracker
from app.models.manifest import CompositionManifest

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.segment_render_task.render_segment_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="composition",
    acks_late=True,
    time_limit=360,     # 6 minutes hard limit
    soft_time_limit=300,
)
def render_segment_task(
    self,
    job_id: str,
    segment_index: int,
) -> dict:
    """Render a single segment for a job.

    Returns dict with segment_index, status, output_path.
    """
    worker_id = self.request.id or "unknown"
    logger.info(
        "Rendering segment %d for job %s (worker=%s)",
        segment_index, job_id, worker_id
    )

    with get_db_context() as db:
        renderer = SegmentRenderer(db)

        try:
            segment = renderer.render_segment(
                job_id=job_id,
                segment_index=segment_index,
                worker_id=worker_id,
            )

            if segment.status == 'complete':
                # Update progress
                _update_progress(db, job_id, segment_index)
                return {
                    "segment_index": segment_index,
                    "status": "complete",
                    "output_path": segment.output_path,
                    "render_duration_s": segment.render_duration_seconds,
                }
            elif segment.status == 'failed':
                # Re-raise for Celery retry
                raise RuntimeError(
                    f"Segment {segment_index} render failed: "
                    f"{segment.last_error}"
                )
            else:
                return {"segment_index": segment_index,
                        "status": segment.status}

        except Exception as exc:
            logger.error(
                "Segment render task failed (job=%s, seg=%d): %s",
                job_id, segment_index, exc
            )
            try:
                self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                return {
                    "segment_index": segment_index,
                    "status": "failed",
                    "error": str(exc),
                }


@shared_task(
    name="tasks.segment_render_task.assemble_segments_task",
    bind=True,
    max_retries=1,
    queue="composition",
    time_limit=900,   # 15 minutes for full assembly
)
def assemble_segments_task(self, job_id: str) -> dict:
    """Assemble all complete segments into final video.

    Called after all segment tasks have completed successfully.
    """
    logger.info("Assembling segments for job %s", job_id)
    with get_db_context() as db:
        renderer = SegmentRenderer(db)
        final_path = renderer.assemble_segments(job_id)
        # Update manifest as rendered
        manifest = (db.query(CompositionManifest)
                    .filter(CompositionManifest.job_id == job_id)
                    .first())
        if manifest:
            manifest.mark_rendered()
            db.commit()
        return {"status": "assembled", "output_path": final_path}


def _update_progress(db, job_id: str, completed_segment_index: int) -> None:
    """Update render progress after a segment completes."""
    try:
        from app.models.segment import RenderSegment
        from sqlalchemy import func
        total = db.query(func.count(RenderSegment.id)).filter(
            RenderSegment.job_id == job_id
        ).scalar()
        done = db.query(func.count(RenderSegment.id)).filter(
            RenderSegment.job_id == job_id,
            RenderSegment.status == 'complete'
        ).scalar()
        manifest = (db.query(CompositionManifest)
                    .filter(CompositionManifest.job_id == job_id)
                    .first())
        total_ms = manifest.total_duration_ms if manifest else 0
        tracker = RenderProgressTracker(job_id, total_ms)
        pct = (done / total * 100) if total > 0 else 0
        tracker.redis.hset(
            f"render_progress:{job_id}",
            mapping={"percentage": round(pct, 1),
                     "segments_done": done,
                     "segments_total": total}
        )
    except Exception:
        pass
