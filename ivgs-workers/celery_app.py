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
    gpu_animation   — node-03: Wan2.2-Animate pose-guided scene animation
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
import sys
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
        # WP-46: animation gets a queue of its own. It shares node-03's worker
        # with gpu_video (one card, concurrency=1, so they serialise either
        # way), but a separate queue is what lets the operator move the
        # animation engine to another node later without touching video, and
        # it keeps the WP-39 identity split true at the transport layer too.
        "gpu_animation",
        exchange=gpu_exchange,
        routing_key="gpu.animation",
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
    "tasks.animation_generation_task.*": {
        "queue": "gpu_animation",
        "routing_key": "gpu.animation",
    },
    "tasks.stage4_manifest.*": {
        "queue": "default",
        "routing_key": "default",
    },
    "tasks.stage4_voiceover.*": {
        "queue": "gpu_tts",
        "routing_key": "gpu.tts",
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
    # WP-59 Task 2 — the same phantom, one schedule up.
    #
    # `tasks.pipeline_orchestrator.run_orphan_cleanup` is ALSO a stub
    # ("Orphan cleanup — stub (Phase 8)"), and it too is in celery_taskmeta
    # recording SUCCESS at 03:00. The real `OrphanCleanupService` has never run
    # either -- which matters to this package specifically, because Task 2
    # names orphan_cleanup as the backstop for anything the binary purge
    # misses. It cannot be a backstop while the thing on the schedule is a
    # stub, and its own three scans query `assets.storage_path` and
    # `assets.status`, NEITHER OF WHICH EXISTS (verified live 2026-08-26).
    #
    # Left pointing at the stub deliberately: repairing OrphanCleanupService is
    # a package of its own -- it QUARANTINES and then permanently DELETES
    # binaries, and it has no shared-object guard, so switching it on today
    # would let it delete a library asset's bytes out from under every project
    # referencing them (WP-59 Task 4 is exactly that guard). Recorded as a
    # decision in the WP-59 report rather than switched on here.
    # WP-60 Task 10 (WP-59 D-2, RULED) — OFF, AND NOW ACTUALLY OFF.
    #
    # This entry dispatched `tasks.pipeline_orchestrator.run_orphan_cleanup`
    # nightly at 03:00. That task is a Phase-5 STUB: it logs one line and
    # returns {'status': 'ok'}, and `celery_taskmeta` holds it saying
    # "Orphan cleanup - stub (Phase 8)" under SUCCESS, most recently
    # 2026-08-26 03:00:00. So the schedule was not off - it was running
    # something that reported health it did not have, every night, which is
    # precisely the family of defect this package exists to close.
    #
    # The RULING is that the schedule stays off until a future one turns it on.
    # "Off" has to mean nothing runs, not "a stub runs and says ok". So the
    # entry is commented out rather than left pointing at the stub.
    #
    # WP-60 repaired the real service behind it and gave it the shared-object
    # guard WP-59 D-2 made a precondition (services/orphan_cleanup.py,
    # SharedObjectGuard).
    #
    # WP-61 Task 7 (WP-59 D-2 / WP-60 D-2, RULED): ON, WEEKLY, AND IT CANNOT
    # DELETE.
    #
    # Read the three kwargs below as one sentence, because they are the whole
    # ruling and every one of them is passed EXPLICITLY rather than inherited
    # from a default. A schedule that relies on a default is one refactor away
    # from meaning something else, and this particular default governs whether
    # binaries are destroyed.
    #
    #   dry_run=False          It genuinely acts. A weekly dry run would report
    #                          the same numbers forever and quarantine nothing,
    #                          which is the "mechanism reporting health it does
    #                          not have" pattern this series exists to end.
    #
    #   quarantine_only=True   The permanent-deletion pass does NOT run. This
    #                          is the difference between reversible and not:
    #                          quarantine is undoable for QUARANTINE_DAYS and
    #                          every move is audited; permanent deletion is
    #                          undoable by nothing. A schedule may do the
    #                          first. A human decides the second.
    #
    #   exclude_scans=["type1"] LEDGERED DEBT, NOT TIDYING. Type 1 looks for
    #                          storage objects no database row claims, by
    #                          listing the filer namespace -- which is EMPTY on
    #                          this fleet. Every object here is a volume object
    #                          addressed by fid and there is no supported way
    #                          to enumerate the fid namespace, so Type 1 has
    #                          ZERO COVERAGE and returns 0 whether or not such
    #                          orphans exist (WP-60 S12.2). Running it produces
    #                          false assurance; the service records the reason
    #                          in `report.coverage["type1"]` on every run. A
    #                          design decision about fid enumeration is OWED,
    #                          and until it is made this sweep is a Type-2 and
    #                          Type-3 backstop and must not be described as a
    #                          complete one.
    #
    # WEEKLY, not nightly. Monday 03:30 UTC. The sweep is a backstop, not a
    # control loop: the paths that create orphans are deletion and failed
    # renders, both of which are individually audited. Seven days of drift is
    # the exposure, and a weekly cadence keeps each run's output small enough
    # that a human actually reads it.
    "orphan-cleanup-weekly": {
        "task": "ivgs_workers.tasks.periodic_tasks.run_orphan_cleanup",
        "schedule": crontab(day_of_week=1, hour=3, minute=30),
        "kwargs": {
            "dry_run": False,
            "quarantine_only": True,
            "exclude_scans": ["type1"],
        },
        "options": {"queue": "default", "priority": 2},
    },
    # WP-59 Task 7 — SHIPPED DISABLED, AND POINTED AT THE REAL TASK.
    #
    # This entry used to name `tasks.pipeline_orchestrator.run_retention_migration`,
    # which is a Phase-5 STUB: it logs one line and returns
    # {'status': 'ok', 'message': 'Retention migration — stub (Phase 8)'}.
    # That string is in the result backend under this schedule's dispatches on
    # 2026-08-24 and 2026-08-25 at 04:00 (celery_taskmeta, read 2026-08-26), so
    # `services/retention_migration.py` has never executed once in the three
    # months the surface has been reporting a migration mechanism.
    #
    # It now names the real task -- and it is COMMENTED OUT, because enabling
    # both repairs at once would put the first tier migration this fleet has
    # ever performed on 158 live assets at 04:00, unattended. The package
    # instruction is explicit that this is an attended event. The operator
    # enables it by uncommenting these five lines after a dry run and a capped
    # live pass have both behaved (WP-59 report, Task 7 operator block).
    #
    # Note the dry_run kwarg is NOT set to False here even when re-enabled: the
    # task defaults to dry-run, so uncommenting this alone gives a nightly
    # REPORT, not a nightly migration. Turning off dry-run is a second,
    # separate, deliberate edit.
    # WP-60 Task 8. ENABLED, and it is a nightly DRY RUN.
    #
    # WP-59 §7.6 step 3, executed here after its preconditions were met: the
    # operator's dry run scanned 161 and reported would_move 44 hot->warm with
    # policy_source=database and zero errors, and the capped live pass then
    # moved exactly 5 (capped=True, 0 deleted, all 5 fids still HTTP 200).
    #
    # WP-61 Task 6 (WP-60 D-1, RULED). THE NIGHTLY RUN IS NOW LIVE.
    #
    # WP-60 left this entry passing NO kwargs so the task's own dry-run default
    # governed, and said a future ruling would turn it live. This is that
    # ruling, and its preconditions were met by the operator's attended runs:
    # the dry run was honest (161 scanned, 44 would-move hot->warm,
    # 109,966,042 bytes, policy_source=database, 0 errors) and the capped live
    # pass was exact (5 moved, 0 deleted, bytes untouched, all 5 fids still
    # serving HTTP 200).
    #
    # THREE THINGS ARE TRUE OF THE KWARGS BELOW AND EACH IS DELIBERATE.
    #
    #   dry_run=False        Explicit. The task still DEFAULTS to dry run, so
    #                        an accidental bare dispatch still only reports;
    #                        what turns the nightly job live is this visible
    #                        line, not a default anyone could acquire by
    #                        omission.
    #
    #   max_transitions=500  A standing cap, not a first-pass cap. The nightly
    #                        job has no operator watching it, and the sane
    #                        failure mode for a migration that suddenly finds
    #                        thousands eligible -- a policy edit, a clock skew,
    #                        a backfill -- is to move 500 and set `capped=True`
    #                        in a report someone reads, rather than to move
    #                        everything and be discovered afterwards.
    #
    #   allow_delete IS ABSENT, and that is the load-bearing omission.
    #                        `archived -> deleted` is the only hop that
    #                        destroys bytes. It is refused structurally when
    #                        `allow_delete` is not set, whatever
    #                        `retention_policies` says -- so the property does
    #                        not rest on all three policy rows happening to
    #                        have NULL `delete_after_days` today. That is data;
    #                        one UPDATE changes it and nothing appears in any
    #                        diff. This is code.
    #
    # Visibility is `_report_retention_migration_metrics` (WP-60 Task 8): one
    # greppable `retention_migration_nightly_result` line carrying transitions
    # and errors, plus the `ivgs_retention_migration_last_*` gauge pair the
    # backup jobs' staleness alerting already covers.
    "retention-migration": {
        "task": "ivgs_workers.tasks.periodic_tasks.run_retention_migration",
        "schedule": crontab(hour=4, minute=0),
        "kwargs": {"dry_run": False, "max_transitions": 500},
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
    # M2-3: project scheduler fleet residency -> model_node_availability
    "model-availability-poll": {
        "task": "ivgs_workers.tasks.periodic_tasks.poll_model_node_availability",
        "schedule": timedelta(seconds=30),
        "options": {"queue": "default", "priority": 3},
    },
    "media-join-watchdog": {
        "task": "tasks.pipeline_orchestrator_v2.media_join_watchdog",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "default", "priority": 4},
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
        "tasks.stage7_prototype_draft",
        "tasks.stage8_final_render",
        "tasks.video_generation_task",
        "tasks.animation_generation_task",
        "tasks.talking_head_task",
        "tasks.pipeline_orchestrator",
        "tasks.pipeline_orchestrator_v2",
        "tasks.periodic_tasks",
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



# ---------------------------------------------------------------------------
# Broker visibility-timeout invariant (ledger P0.1, WP-05)
# ---------------------------------------------------------------------------

class VisibilityTimeoutError(RuntimeError):
    """The broker would redeliver a message while its task is still running.

    Raised at worker startup, deliberately fatal. A worker that consumes with
    ``task_acks_late`` under a visibility timeout shorter than its own hard
    ``time_limit`` will re-run long tasks - and on a queue with two consumers
    (``gpu_video`` is bound to node-02 and node-03 in tracked compose) it will run
    two copies at once. That is not a condition to log and continue past.
    """


def check_visibility_timeout(
    visibility_timeout: int,
    task_time_limits: Dict[str, int],
) -> None:
    """Raise if any task's hard time limit meets or exceeds the visibility timeout.

    Pure: takes the two numbers, knows nothing about Celery. ``task_time_limits``
    maps task name -> hard ``time_limit`` in seconds. Tasks with no hard limit are
    the caller's job to resolve (see the app-level wrapper) and must not appear here
    as ``None``.

    The comparison is ``>=``, not ``>``: equal values are a coin-flip race, not a
    pass.
    """
    if not visibility_timeout or visibility_timeout <= 0:
        raise VisibilityTimeoutError(
            "broker visibility_timeout is unset or non-positive "
            f"({visibility_timeout!r}); refusing to start. Set "
            "IVGS_BROKER_VISIBILITY_TIMEOUT above the longest task time_limit."
        )

    offenders = {
        name: limit
        for name, limit in task_time_limits.items()
        if limit is not None and limit >= visibility_timeout
    }
    if not offenders:
        return

    worst_name, worst_limit = max(offenders.items(), key=lambda kv: kv[1])
    listed = ", ".join(
        f"{name}={limit}s" for name, limit in sorted(
            offenders.items(), key=lambda kv: -kv[1]
        )
    )
    raise VisibilityTimeoutError(
        "broker visibility_timeout ("
        f"{visibility_timeout}s) does not cover the hard time_limit of "
        f"{len(offenders)} task(s): {listed}. "
        f"The longest is {worst_name} at {worst_limit}s. With task_acks_late the "
        f"broker will redeliver a {worst_name} message at t={visibility_timeout}s "
        f"while the original is still running, up to t={worst_limit}s. "
        "Raise IVGS_BROKER_VISIBILITY_TIMEOUT above "
        f"{worst_limit}s with margin (7200 is the ledger P0.1 recommendation), "
        "or lower the task's time_limit. Refusing to start."
    )


def collect_task_time_limits(app: Celery) -> Dict[str, int]:
    """Hard time limit per registered task, resolving the app default.

    A task that declares no ``time_limit`` inherits ``app.conf.task_time_limit``,
    so the effective limit - not the declared one - is what gets checked. Celery's
    own internal ``celery.*`` tasks are skipped; they are not ours and carry no
    render-length limits.

    Forces ``app.conf.include`` to be imported first. Without this the registry is
    empty until the worker's own loader runs, and an empty registry means no
    offenders means the gate silently passes - a check that cannot fail is worse
    than no check, because it reads as protection. Re-importing an already-imported
    module is a ``sys.modules`` hit, so this is cheap and idempotent.
    """
    try:
        app.loader.import_default_modules()
    except Exception:  # pragma: no cover - a broken task module surfaces elsewhere
        # Deliberately swallowed HERE and only here: if a task module cannot be
        # imported, the worker fails on that with a far better message than this
        # gate could produce. The emptiness check below still fires.
        logger.exception("visibility_timeout gate could not import task modules")

    default_limit = app.conf.task_time_limit
    limits: Dict[str, int] = {}
    for name, task in (app.tasks or {}).items():
        if name.startswith("celery."):
            continue
        limit = getattr(task, "time_limit", None)
        if limit is None:
            limit = default_limit
        if limit is not None:
            limits[name] = int(limit)
    return limits


def assert_visibility_timeout_covers_time_limits(app: Celery) -> None:
    """Startup gate. Reads the live app's transport options and task registry."""
    transport_options = app.conf.broker_transport_options or {}
    limits = collect_task_time_limits(app)
    if not limits:
        raise VisibilityTimeoutError(
            "the visibility-timeout gate found no registered tasks, so it cannot "
            "establish the invariant. Refusing to start rather than passing "
            "vacuously. Check app.conf.include."
        )
    check_visibility_timeout(
        transport_options.get("visibility_timeout"),
        limits,
    )


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

@signals.celeryd_after_setup.connect
def on_celeryd_after_setup(sender: Any = None, instance: Any = None, **kwargs: Any) -> None:
    """Fail fast if the broker would redeliver a task while it is still running.

    Ledger P0.1 / WP-05. This signal fires after the worker has imported its task
    modules - so ``app.tasks`` is populated and the check sees real, effective hard
    limits - and before the consumer starts, so a violation aborts startup instead
    of being discovered by a duplicate render three thousand seconds in.

    Raising here is deliberate, and it raises SystemExit rather than the error
    itself. MEASURED 2026-08-23 (WP-05): celery/utils/dispatch/signal.py:276 wraps
    every receiver in `except Exception`, logs it, and carries on - a probe worker
    raised VisibilityTimeoutError from this handler, printed the full message, and
    then went right on to start its consumer. A gate that only logs is not a gate.
    SystemExit derives from BaseException, so that `except Exception` does not
    catch it and the worker actually stops.
    """
    app = getattr(instance, "app", None) or celery_app
    try:
        assert_visibility_timeout_covers_time_limits(app)
    except VisibilityTimeoutError as exc:
        import structlog

        structlog.get_logger("ivgs.worker.init").critical(
            "visibility_timeout_invariant_violated",
            error=str(exc),
            remedy="raise IVGS_BROKER_VISIBILITY_TIMEOUT; see ledger P0.1",
        )
        # Also to stderr: structlog may not be configured this early on every path,
        # and a worker that dies silently is the failure mode this package exists
        # to remove.
        print(f"FATAL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


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
    """Log readiness and self-register this node with the GPU scheduler (M2-1)."""
    import structlog
    slog = structlog.get_logger("ivgs.worker.ready")
    slog.info(
        "worker_ready",
        hostname=sender.hostname if sender else "unknown",
        pid=os.getpid(),
    )
    # WP-55 (P2.64): the liveness beacon `WorkerDown` needs. UNCONDITIONAL and
    # deliberately first — before the GPU registration below, which skips on any
    # worker with no GPU identity and so has never covered node-01's
    # default-worker or composition-worker. A critical alert cannot be built on
    # a heartbeat that only some workers send.
    try:
        from config import WorkerConfig as _Cfg
        from utils.liveness import start_liveness_beacon

        _cfg = _Cfg()
        start_liveness_beacon(
            worker_id=sender.hostname if sender else _cfg.node_hostname,
            node_hostname=_cfg.node_hostname,
        )
    except Exception as exc:
        slog.warning("worker_liveness_beacon_failed", error=str(exc))

    # M2-1: register the node with the GPU scheduler and keep it alive. Skips
    # cleanly on non-GPU workers (no GPU identity) — see register_node.
    try:
        from config import WorkerConfig
        from utils.gpu_utils import register_node, start_heartbeat_loop

        node_id = register_node()
        if node_id is not None:
            cfg = WorkerConfig()
            start_heartbeat_loop(
                worker_id=sender.hostname if sender else cfg.node_hostname,
                node_hostname=cfg.node_hostname,
                gpu_index=int(os.environ.get("IVGS_GPU_INDEX", "0")),
            )
    except Exception as exc:
        slog.warning("node_registration_bootstrap_failed", error=str(exc))


@signals.worker_shutting_down.connect
def on_worker_shutdown(
    sender: Any = None, sig: Any = None, **kwargs: Any
) -> None:
    """Graceful shutdown: release GPU reservations, send final heartbeat."""
    import structlog
    slog = structlog.get_logger("ivgs.worker.shutdown")

    # WP-55: stop writing, but LEAVE the last-seen record in place. A worker
    # that is stopped and not restarted must trip WorkerDown five minutes
    # later; deleting the record here would make an intentional stop and a
    # crash produce identical evidence.
    try:
        from utils.liveness import stop_liveness_beacon

        stop_liveness_beacon()
    except Exception:  # noqa: BLE001 - shutdown path, never block on this
        pass
    slog.warning(
        "worker_shutting_down",
        hostname=sender.hostname if sender else "unknown",
        signal=str(sig),
    )
    # M2-1: stop the node keepalive so the scheduler ages this node out.
    try:
        from utils.gpu_utils import stop_heartbeat_loop

        stop_heartbeat_loop()
    except Exception:
        pass


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
        # WP-08 F5: on_success and on_failure both release; on_retry did not. The
        # retry acquires again and overwrites _gpu_reservation_id, orphaning the
        # previous reservation until its TTL. Release it here so a task that
        # retries four times holds one reservation, not four.
        self._release_gpu_reservation()

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
