"""
IVGS v5 — Celery Application Factory
=====================================

Central Celery app definition with:
- Redis broker for task queuing
- PostgreSQL result backend for durable result storage
- Multi-queue routing per §6.4 Table 6-7
- Production-hardened settings: acks_late, prefetch=1, reject_on_worker_lost
- Worker heartbeat configuration (10s interval, §6.2)
- Celery Beat schedule for periodic operational tasks

Queues (§6.4 Table 6-7):
    default         — node-01: orchestration, admin, periodic tasks
    gpu_llm         — node-02/03/04: vLLM inference (transcript, storyboard)
    gpu_image       — node-04/05: ComfyUI image + animation generation
    gpu_video       — node-02/03: CogVideoX / Wan2.1 video generation
    gpu_tts         — node-04: Coqui XTTS v2, Kokoro TTS, WhisperX
    gpu_talking_head — node-04: LatentSync, SadTalker
    composition     — node-05/06: FFmpeg, Remotion

All vLLM calls use task_acks_late=True so that if a worker dies mid-inference,
the message is automatically re-delivered to another worker (§6.4).
"""

from __future__ import annotations

import logging
import os
import ssl
from datetime import timedelta
from typing import Any, Dict, Optional

from celery import Celery, signals
from celery.app.task import Task as CeleryTask
from celery.schedules import crontab
from kombu import Exchange, Queue

from config import WorkerConfig

logger = logging.getLogger("ivgs.celery")

# ---------------------------------------------------------------------------
# Queue / exchange definitions
# ---------------------------------------------------------------------------

default_exchange = Exchange("default", type="direct")
gpu_exchange = Exchange("gpu", type="direct")
composition_exchange = Exchange("composition", type="direct")

TASK_QUEUES = (
    Queue(
        "default",
        exchange=default_exchange,
        routing_key="default",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "gpu_llm",
        exchange=gpu_exchange,
        routing_key="gpu.llm",
        queue_arguments={
            "x-max-priority": 10,
            "x-message-ttl": 600_000,
        },
    ),
    Queue(
        "gpu_image",
        exchange=gpu_exchange,
        routing_key="gpu.image",
        queue_arguments={
            "x-max-priority": 10,
            "x-message-ttl": 900_000,
        },
    ),
    Queue(
        "gpu_video",
        exchange=gpu_exchange,
        routing_key="gpu.video",
        queue_arguments={
            "x-max-priority": 10,
            "x-message-ttl": 3_600_000,
        },
    ),
    Queue(
        "gpu_tts",
        exchange=gpu_exchange,
        routing_key="gpu.tts",
        queue_arguments={
            "x-max-priority": 10,
            "x-message-ttl": 600_000,
        },
    ),
    Queue(
        "gpu_talking_head",
        exchange=gpu_exchange,
        routing_key="gpu.talking_head",
        queue_arguments={
            "x-max-priority": 10,
            "x-message-ttl": 1_200_000,
        },
    ),
    Queue(
        "composition",
        exchange=composition_exchange,
        routing_key="composition",
        queue_arguments={
            "x-max-priority": 10,
            "x-message-ttl": 1_800_000,
        },
    ),
)

# ---------------------------------------------------------------------------
# Task routing rules
# ---------------------------------------------------------------------------

TASK_ROUTES: Dict[str, Dict[str, str]] = {
    # Keys match the registered task NAME (Celery routes by name), which for
    # several modules differs from the filename (H.0 WI-4 finding):
    #   stage5_voiceover.py       -> tasks.stage4_voiceover.*
    #   stage6_talking_head.py    -> tasks.stage5_talking_head.*
    #   stage7_prototype_draft.py -> tasks.prototype_draft_task.*
    #   stage8_final_render.py    -> tasks.final_render_task.*
    # The orchestrator dispatches each stage with an explicit queue= (its
    # STAGE_QUEUE_MAP), so these routes are the fallback.
    "tasks.stage1_transcript.*": {
        "queue": "gpu_llm",
        "routing_key": "gpu.llm",
    },
    "tasks.stage2_storyboard.*": {
        "queue": "gpu_llm",
        "routing_key": "gpu.llm",
    },
    "tasks.stage3_images.*": {
        "queue": "gpu_image",
        "routing_key": "gpu.image",
    },
    "tasks.video_generation_task.*": {
        "queue": "gpu_video",
        "routing_key": "gpu.video",
    },
    "tasks.stage4_manifest.*": {
        "queue": "default",
        "routing_key": "default",
    },
    "tasks.stage4_voiceover.*": {
        "queue": "gpu_tts",
        "routing_key": "gpu.tts",
    },
    "tasks.stage5_talking_head.*": {
        "queue": "gpu_talking_head",
        "routing_key": "gpu.talking_head",
    },
    "tasks.talking_head_task.*": {
        "queue": "gpu_talking_head",
        "routing_key": "gpu.talking_head",
    },
    "tasks.prototype_draft_task.*": {
        "queue": "composition",
        "routing_key": "composition",
    },
    "tasks.final_render_task.*": {
        "queue": "composition",
        "routing_key": "composition",
    },
    "tasks.pipeline_orchestrator.*": {
        "queue": "default",
        "routing_key": "default",
    },
    "tasks.pipeline_orchestrator_v2.*": {
        "queue": "default",
        "routing_key": "default",
    },
}

# ---------------------------------------------------------------------------
# Celery Beat schedule
# ---------------------------------------------------------------------------

CELERY_BEAT_SCHEDULE: Dict[str, Any] = {
    "heartbeat-supervision": {
        "task": "tasks.pipeline_orchestrator.supervise_worker_heartbeats",
        "schedule": timedelta(seconds=30),
        "options": {"queue": "default", "priority": 9},
    },
    "dlq-processor": {
        "task": "tasks.pipeline_orchestrator.process_dead_letter_queue",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "default", "priority": 5},
    },
    "orphan-cleanup": {
        "task": "tasks.pipeline_orchestrator.run_orphan_cleanup",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "default", "priority": 2},
    },
    "retention-migration": {
        "task": "tasks.pipeline_orchestrator.run_retention_migration",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "default", "priority": 2},
    },
    "backup-verification": {
        "task": "tasks.pipeline_orchestrator.run_backup_verification",
        "schedule": crontab(hour=5, minute=0),
        "options": {"queue": "default", "priority": 1},
    },
    "gpu-fleet-metrics": {
        "task": "tasks.pipeline_orchestrator.collect_gpu_fleet_metrics",
        "schedule": timedelta(seconds=60),
        "options": {"queue": "default", "priority": 3},
    },
}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_celery_app(config: Optional[WorkerConfig] = None) -> Celery:
    """
    Create and configure the Celery application.

    Parameters
    ----------
    config : WorkerConfig, optional
        Worker configuration. Loaded from environment if not provided.

    Returns
    -------
    Celery
        Fully configured Celery application instance.
    """
    if config is None:
        config = WorkerConfig()

    app = Celery("ivgs-workers")

    # Broker (Redis)
    broker_url = config.celery_broker_url
    app.conf.broker_url = broker_url
    app.conf.broker_transport_options = {
        "visibility_timeout": config.broker_visibility_timeout,
        "queue_order_strategy": "priority",
        "sep": ":",
        "priority_steps": list(range(10)),
        # Kombu 5.4+ requires these for pidbox control commands to work with
        # Redis broker.  Without them, `celery inspect ping` (and the
        # healthcheck that depends on it) crash with:
        #   ValueError: not enough values to unpack (expected 3, got 1)
        # in kombu/transport/virtual/exchange.py lookup().
        "fanout_prefix": True,
        "fanout_patterns": True,
        # Namespace this worker's keys so they don't collide with the
        # ivgs-backup-worker's keys (both share the same Redis instance,
        # different DB index = 0).
        "global_keyprefix": "ivgs_workers_",
    }
    # Quiet a Celery 5.4 deprecation warning. Behavior remains the same.
    app.conf.broker_connection_retry_on_startup = True

    if config.broker_use_ssl:
        app.conf.broker_use_ssl = {
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
            "ssl_ca_certs": config.broker_ssl_ca_certs,
        }

    # Result backend (PostgreSQL)
    app.conf.result_backend = config.celery_result_backend
    app.conf.result_backend_transport_options = {
        "retry_policy": {"timeout": 10.0},
    }
    app.conf.result_expires = config.result_expires_seconds
    app.conf.result_extended = True

    # Serialization
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]
    app.conf.event_serializer = "json"

    # Task execution (§6.4)
    app.conf.task_acks_late = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.task_reject_on_worker_lost = True
    app.conf.task_track_started = True
    app.conf.task_time_limit = config.task_hard_time_limit
    app.conf.task_soft_time_limit = config.task_soft_time_limit
    app.conf.worker_max_tasks_per_child = config.worker_max_tasks_per_child
    app.conf.worker_max_memory_per_child = config.worker_max_memory_per_child

    # Concurrency
    app.conf.worker_concurrency = config.worker_concurrency
    app.conf.worker_pool = "prefork"

    # Queues and routing
    app.conf.task_queues = TASK_QUEUES
    app.conf.task_routes = TASK_ROUTES
    app.conf.task_default_queue = "default"
    app.conf.task_default_exchange = "default"
    app.conf.task_default_routing_key = "default"
    app.conf.task_default_priority = 5

    # Beat schedule
    app.conf.beat_schedule = CELERY_BEAT_SCHEDULE
    app.conf.beat_schedule_filename = "/tmp/ivgs-celerybeat-schedule"

    # Events
    app.conf.worker_send_task_events = True
    app.conf.task_send_sent_event = True

    # Task imports
    app.conf.include = [
        "tasks.stage1_transcript",
        "tasks.stage2_storyboard",
        "tasks.stage3_images",
        "tasks.stage4_manifest",
        "tasks.stage5_voiceover",
        "tasks.stage6_talking_head",
        "tasks.stage7_prototype_draft",
        "tasks.stage8_final_render",
        "tasks.video_generation_task",
        "tasks.talking_head_task",
        "tasks.pipeline_orchestrator",
        "tasks.pipeline_orchestrator_v2",
    ]

    # Timezone
    app.conf.timezone = "UTC"
    app.conf.enable_utc = True

    logger.info(
        "Celery app configured: broker=%s result_backend=%s concurrency=%d",
        _mask_url(broker_url),
        _mask_url(config.celery_result_backend),
        config.worker_concurrency,
    )

    return app


def _mask_url(url: str) -> str:
    """Mask passwords in URLs for safe logging."""
    if "@" in url:
        scheme_end = url.index("://") + 3
        at_pos = url.index("@")
        return url[:scheme_end] + "***:***@" + url[at_pos + 1:]
    return url


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

@signals.worker_init.connect
def on_worker_init(sender: Any = None, **kwargs: Any) -> None:
    """
    Called once when a worker process starts.
    Initializes structured logging and registers with GPU registry.
    """
    import structlog

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(
                os.getenv("IVGS_LOG_LEVEL", "INFO").upper()
            )
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    slog = structlog.get_logger("ivgs.worker.init")
    slog.info(
        "worker_initializing",
        hostname=sender.hostname if sender else "unknown",
        queues=[q.name for q in (sender.app.conf.task_queues or [])],
    )


@signals.worker_ready.connect
def on_worker_ready(sender: Any = None, **kwargs: Any) -> None:
    """Log when worker is ready to accept tasks."""
    import structlog
    slog = structlog.get_logger("ivgs.worker.ready")
    slog.info(
        "worker_ready",
        hostname=sender.hostname if sender else "unknown",
        pid=os.getpid(),
    )


@signals.worker_shutting_down.connect
def on_worker_shutdown(
    sender: Any = None, sig: Any = None, **kwargs: Any
) -> None:
    """Graceful shutdown: release GPU reservations, send final heartbeat."""
    import structlog
    slog = structlog.get_logger("ivgs.worker.shutdown")
    slog.warning(
        "worker_shutting_down",
        hostname=sender.hostname if sender else "unknown",
        signal=str(sig),
    )


@signals.task_prerun.connect
def on_task_prerun(
    sender: Any = None,
    task_id: Optional[str] = None,
    task: Optional[CeleryTask] = None,
    args: Any = None,
    kwargs: Any = None,
    **extra: Any,
) -> None:
    """Attach task_id and job_id to structlog context for tracing."""
    import structlog
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=task_id,
        task_name=sender.name if sender else "unknown",
    )
    if kwargs and "job_id" in kwargs:
        structlog.contextvars.bind_contextvars(job_id=kwargs["job_id"])


@signals.task_postrun.connect
def on_task_postrun(
    sender: Any = None,
    task_id: Optional[str] = None,
    retval: Any = None,
    state: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Clear structlog context after task completes."""
    import structlog
    slog = structlog.get_logger("ivgs.task.postrun")
    slog.info("task_completed", state=state, task_name=sender.name if sender else "unknown")
    structlog.contextvars.clear_contextvars()


@signals.task_failure.connect
def on_task_failure(
    sender: Any = None,
    task_id: Optional[str] = None,
    exception: Optional[BaseException] = None,
    traceback: Any = None,
    **kwargs: Any,
) -> None:
    """Log task failure with full exception details."""
    import structlog
    slog = structlog.get_logger("ivgs.task.failure")
    slog.error(
        "task_failed",
        task_name=sender.name if sender else "unknown",
        exception_type=type(exception).__name__ if exception else None,
        exception_msg=str(exception) if exception else None,
    )


@signals.task_retry.connect
def on_task_retry(
    sender: Any = None,
    request: Any = None,
    reason: Any = None,
    **kwargs: Any,
) -> None:
    """Log task retry with reason."""
    import structlog
    slog = structlog.get_logger("ivgs.task.retry")
    slog.warning(
        "task_retrying",
        task_name=sender.name if sender else "unknown",
        reason=str(reason),
    )


# ---------------------------------------------------------------------------
# Singleton app instance
# ---------------------------------------------------------------------------

celery_app = create_celery_app()


# ---------------------------------------------------------------------------
# Custom base task class
# ---------------------------------------------------------------------------

class IVGSBaseTask(celery_app.Task):  # type: ignore[misc]
    """
    Base task class for all IVGS pipeline tasks.

    Provides:
    - Automatic structured logging context
    - GPU reservation lifecycle management
    - Checkpoint save/load helpers
    - Idempotency guard via generation_params_hash (§6.2)
    - Exponential backoff retry defaults
    - DLQ routing on max retries exceeded
    """

    abstract = True

    autoretry_for: tuple = ()
    max_retries: int = 4
    default_retry_delay: int = 5
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True

    soft_time_limit: int = 120
    time_limit: int = 150

    _db_session: Any = None
    _gpu_reservation_id: Optional[str] = None

    @property
    def structured_logger(self) -> Any:
        """Get a structlog logger bound to this task's context."""
        import structlog
        return structlog.get_logger(f"ivgs.task.{self.name}")

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        self.structured_logger.info(
            "task_starting",
            task_id=task_id,
            retry_count=self.request.retries,
        )

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        self.structured_logger.info("task_succeeded", task_id=task_id)
        self._release_gpu_reservation()

    def on_failure(
        self, exc: BaseException, task_id: str, args: tuple, kwargs: dict, einfo: Any,
    ) -> None:
        """Route failed task to DLQ after all retries exhausted."""
        self.structured_logger.error(
            "task_failed_final",
            task_id=task_id,
            exception_type=type(exc).__name__,
            exception_msg=str(exc),
            retries_exhausted=self.request.retries,
        )
        self._release_gpu_reservation()
        self._route_to_dlq(exc, task_id, args, kwargs)

    def on_retry(
        self, exc: BaseException, task_id: str, args: tuple, kwargs: dict, einfo: Any,
    ) -> None:
        self.structured_logger.warning(
            "task_retrying",
            task_id=task_id,
            retry_number=self.request.retries + 1,
            max_retries=self.max_retries,
            exception_type=type(exc).__name__,
        )

    def _release_gpu_reservation(self) -> None:
        """Release any held GPU reservation."""
        if self._gpu_reservation_id:
            try:
                from utils.gpu_utils import release_gpu_reservation
                release_gpu_reservation(self._gpu_reservation_id)
                self.structured_logger.info(
                    "gpu_reservation_released",
                    reservation_id=self._gpu_reservation_id,
                )
            except Exception as release_err:
                self.structured_logger.error(
                    "gpu_reservation_release_failed",
                    reservation_id=self._gpu_reservation_id,
                    error=str(release_err),
                )
            finally:
                self._gpu_reservation_id = None

    def _route_to_dlq(
        self, exc: BaseException, task_id: str, args: tuple, kwargs: dict,
    ) -> None:
        """Route failed task to the Dead Letter Queue."""
        try:
            from utils.error_handler import route_to_dead_letter_queue
            route_to_dead_letter_queue(
                task_name=self.name,
                task_id=task_id,
                args=args,
                kwargs=kwargs,
                exception=exc,
                retry_count=self.request.retries,
            )
        except Exception as dlq_err:
            self.structured_logger.critical(
                "dlq_routing_failed", task_id=task_id, error=str(dlq_err),
            )

    def compute_idempotency_hash(self, params: dict) -> str:
        """
        Compute SHA-256 hash of generation parameters for idempotency.
        Per §6.2: skip re-execution if matching completed asset exists.
        """
        import hashlib
        import json
        canonical = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
