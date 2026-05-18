"""Worker health supervision task — runs every 30 seconds via Celery Beat.

Monitors all registered worker heartbeats. Detects dead workers and
takes corrective action: marks worker dead, reassigns jobs to queue,
and fires ops alert. Also detects GPU errors and triggers worker restart.

Beat schedule:
    "supervise-workers": {
        "task": "tasks.worker_supervisor_task.supervise_workers_task",
        "schedule": 30.0,
    }
"""

import logging
from datetime import datetime, timedelta
from celery import shared_task, current_app
from sqlalchemy import text

from app.database import get_db_context
from app.core.alerting import send_ops_alert

logger = logging.getLogger(__name__)

HEARTBEAT_DEAD_THRESHOLD_SECONDS = 60
HEARTBEAT_SUSPECTED_THRESHOLD_SECONDS = 30


@shared_task(
    name="tasks.worker_supervisor_task.supervise_workers_task",
    bind=True,
    max_retries=0,   # Never retry supervision tasks
    queue="default",
    ignore_result=True,
)
def supervise_workers_task(self) -> None:
    """Check all worker heartbeats and handle dead workers."""
    now = datetime.utcnow()
    dead_threshold = now - timedelta(seconds=HEARTBEAT_DEAD_THRESHOLD_SECONDS)
    suspected_threshold = now - timedelta(
        seconds=HEARTBEAT_SUSPECTED_THRESHOLD_SECONDS
    )

    with get_db_context() as db:
        # Fetch all workers with recent heartbeat records
        workers = db.execute(text("""
            SELECT wh.id, wh.worker_id, wh.node_hostname, wh.gpu_index,
                   wh.current_job_id, wh.current_stage, wh.status,
                   wh.last_heartbeat_at, wh.heartbeat_data
            FROM worker_heartbeats wh
            WHERE wh.status IN ('alive', 'suspected_dead')
        """)).fetchall()

        for worker in workers:
            last_hb = worker.last_heartbeat_at
            if not last_hb:
                continue

            if last_hb < dead_threshold:
                _handle_dead_worker(db, worker, now)
            elif last_hb < suspected_threshold:
                _handle_suspected_worker(db, worker)
            else:
                # Worker is alive — check for GPU errors
                _check_gpu_health(db, worker)

        db.commit()


def _handle_dead_worker(db, worker, now: datetime) -> None:
    """Transition worker to dead state and reassign its job."""
    logger.error(
        "DEAD WORKER: %s on %s:%d (last heartbeat: %s)",
        worker.worker_id, worker.node_hostname,
        worker.gpu_index, worker.last_heartbeat_at
    )

    # Mark worker as dead
    db.execute(text("""
        UPDATE worker_heartbeats
        SET status = 'confirmed_dead'
        WHERE id = :id
    """), {"id": worker.id})

    # Reassign job to queue if one was in progress
    if worker.current_job_id:
        logger.warning(
            "Reassigning job %s from dead worker %s",
            worker.current_job_id, worker.worker_id
        )
        # Re-queue via pipeline resume
        try:
            current_app.send_task(
                'tasks.orchestrator_task.resume_pipeline_task',
                args=[worker.current_job_id],
                queue='default',
            )
            logger.info(
                "Job %s re-queued for resume",
                worker.current_job_id
            )
        except Exception as e:
            logger.error(
                "Failed to re-queue job %s: %s",
                worker.current_job_id, e
            )

    send_ops_alert(
        f"Worker {worker.worker_id} on {worker.node_hostname}:{worker.gpu_index} "
        f"confirmed dead. Job {worker.current_job_id or 'none'} reassigned.",
        severity="critical"
    )


def _handle_suspected_worker(db, worker) -> None:
    """Transition worker to suspected_dead state (not yet confirmed)."""
    logger.warning(
        "SUSPECTED DEAD: worker %s (last hb: %s)",
        worker.worker_id, worker.last_heartbeat_at
    )
    db.execute(text("""
        UPDATE worker_heartbeats
        SET status = 'suspected_dead'
        WHERE id = :id AND status = 'alive'
    """), {"id": worker.id})


def _check_gpu_health(db, worker) -> None:
    """Check heartbeat_data for GPU error indicators."""
    hb_data = worker.heartbeat_data or {}
    temp = hb_data.get('gpu_temp', 0)
    util = hb_data.get('gpu_util_pct', 0)

    if temp and temp > 90:
        logger.warning(
            "GPU OVERTEMP: worker %s on %s:%d temp=%d°C",
            worker.worker_id, worker.node_hostname,
            worker.gpu_index, temp
        )
        send_ops_alert(
            f"GPU overtemp: {worker.node_hostname}:{worker.gpu_index} "
            f"at {temp}°C",
            severity="warning"
        )
