"""
IVGS v5 — Celery Beat Periodic Tasks
========================================

Celery Beat task definitions per §6.4.

Schedule (from specification):
- DLQ processing:        every 5 minutes
- Heartbeat supervision: every 30 seconds
- Orphan cleanup:        daily at 02:00 UTC
- Retention migration:   daily at 03:00 UTC
- Backup verification:   daily at 04:00 UTC

All periodic tasks run on the 'default' queue (node-01) per Table 6-7.

Celery Beat configuration:
- task_acks_late = True
- worker_prefetch_multiplier = 1
- task_reject_on_worker_lost = True

Integration:
- DLQService.process_pending_messages() — auto-replay transient failures
- OrphanCleanupService.run_cleanup() — 3 scan types + quarantine
- RetentionService.run_migration() — tier transitions
- HeartbeatSupervisor — dead worker detection (60s threshold)
- BackupVerifier — integrity verification of most recent backup
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from celery import shared_task


logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Celery Beat Schedule Configuration
# ---------------------------------------------------------------------------

def get_beat_schedule() -> dict[str, dict[str, Any]]:
    """The live Celery Beat schedule. WP-61 Task 7.

    **THIS FUNCTION USED TO BE A SECOND, DRIFTING COPY OF THE SCHEDULE, AND IT
    IS EXACTLY THE DEFECT THIS PACKAGE'S TASKS 6 AND 7 ARE ABOUT.**

    It returned a hand-written dict of six entries. Nothing called it -- the
    real schedule is ``celery_app.CELERY_BEAT_SCHEDULE``, assigned at
    ``celery_app.py`` under ``app.conf.beat_schedule`` -- and being uncalled is
    the only reason it never did any harm. What it contained, read on
    2026-08-26:

        "orphan-cleanup-daily"     -> run_orphan_cleanup, DAILY at 02:00,
                                      with NO kwargs
        "retention-migration-daily"-> run_retention_migration, NO kwargs,
                                      hour driven by a RETENTION_JOB_CRON env
                                      var nothing sets

    Both rulings this package implements live in kwargs. An orphan entry with
    no kwargs is a nightly sweep that can reach permanent deletion and that
    runs the zero-coverage Type-1 scan; a retention entry with no kwargs is an
    uncapped dry run. So one `app.conf.beat_schedule = get_beat_schedule()` --
    the very line this docstring used to suggest -- would have silently
    replaced both rulings with their opposites, and every test that reads
    `celery_app.py` would still have passed.

    It now returns the one real schedule. There is no second statement of what
    somebody believed the schedule was.

    The import is function-level because ``celery_app`` imports this module's
    tasks; a module-level import would be circular.
    """
    from celery_app import CELERY_BEAT_SCHEDULE

    return CELERY_BEAT_SCHEDULE


# ---------------------------------------------------------------------------
# DLQ Processing Task
# ---------------------------------------------------------------------------

@shared_task(
    name="ivgs_workers.tasks.periodic_tasks.process_dlq",
    bind=True,
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=240,
    soft_time_limit=220,
)
def process_dlq(self: Any) -> dict[str, Any]:
    """
    Periodic DLQ processing — runs every 5 minutes per §6.4.

    Auto-replays transient failures younger than 1 hour.
    Flags stale messages older than 24 hours.

    Returns:
        Dict with processing statistics.
    """
    task_log = logger.bind(
        task_name="process_dlq",
        celery_task_id=self.request.id,
    )
    task_log.info("dlq_processing_started")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from services.dlq_service import DLQService
            from shared.database import async_session_factory

            dlq_service = DLQService(
                db_session_factory=async_session_factory,
                celery_app=self.app,
            )

            result = loop.run_until_complete(
                dlq_service.process_pending_messages(
                    auto_replay_transient=True,
                    max_auto_replays=10,
                )
            )

            task_log.info(
                "dlq_processing_completed",
                auto_replayed=result["auto_replayed"],
                flagged_stale=result["flagged_stale"],
                total_pending=result["total_pending"],
            )

            return result

        finally:
            loop.close()

    except Exception as exc:
        task_log.error("dlq_processing_failed", error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Heartbeat Supervision Task
# ---------------------------------------------------------------------------

@shared_task(
    name="ivgs_workers.tasks.periodic_tasks.supervise_heartbeats",
    bind=True,
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=25,
    soft_time_limit=20,
)
def supervise_heartbeats(self: Any) -> dict[str, Any]:
    """
    Heartbeat supervision — runs every 30 seconds per §6.2.

    Checks worker heartbeats. Workers missing > 60 seconds are marked
    'suspected_dead'. Workers missing > 120 seconds are marked
    'confirmed_dead' and their active jobs are rescheduled.

    Returns:
        Dict with supervision statistics.
    """
    task_log = logger.bind(
        task_name="supervise_heartbeats",
        celery_task_id=self.request.id,
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from shared.database import async_session_factory
            from sqlalchemy import text

            db_factory = async_session_factory
            now = datetime.now(timezone.utc)
            suspected_threshold = now - timedelta(seconds=60)
            confirmed_threshold = now - timedelta(seconds=120)

            async def _supervise() -> dict[str, Any]:
                suspected_count = 0
                confirmed_count = 0
                rescheduled_jobs: list[str] = []

                async with db_factory() as session:
                    # Mark suspected_dead (60s threshold)
                    result = await session.execute(
                        text(
                            "UPDATE worker_heartbeats "
                            "SET status = 'suspected_dead' "
                            "WHERE status = 'alive' "
                            "AND last_heartbeat_at < :threshold "
                            "RETURNING worker_id"
                        ),
                        {"threshold": suspected_threshold},
                    )
                    suspected_rows = result.fetchall()
                    suspected_count = len(suspected_rows)

                    for row in suspected_rows:
                        task_log.warning(
                            "worker_suspected_dead",
                            worker_id=row[0],
                        )

                    # Mark confirmed_dead (120s threshold)
                    result = await session.execute(
                        text(
                            "UPDATE worker_heartbeats "
                            "SET status = 'confirmed_dead' "
                            "WHERE status = 'suspected_dead' "
                            "AND last_heartbeat_at < :threshold "
                            "RETURNING worker_id, current_job_id"
                        ),
                        {"threshold": confirmed_threshold},
                    )
                    confirmed_rows = result.fetchall()
                    confirmed_count = len(confirmed_rows)

                    for row in confirmed_rows:
                        worker_id = row[0]
                        job_id = row[1]

                        task_log.error(
                            "worker_confirmed_dead",
                            worker_id=worker_id,
                            current_job_id=str(job_id) if job_id else None,
                        )

                        # Reschedule active job via GPU scheduler
                        if job_id:
                            rescheduled_jobs.append(str(job_id))
                            await session.execute(
                                text(
                                    "UPDATE render_jobs "
                                    "SET status = 'pending', "
                                    "node_id = NULL "
                                    "WHERE id = :job_id "
                                    "AND status = 'running'"
                                ),
                                {"job_id": str(job_id)},
                            )

                    await session.commit()

                return {
                    "suspected_dead": suspected_count,
                    "confirmed_dead": confirmed_count,
                    "rescheduled_jobs": rescheduled_jobs,
                    "checked_at": now.isoformat(),
                }

            result = loop.run_until_complete(_supervise())

            if result["suspected_dead"] > 0 or result["confirmed_dead"] > 0:
                task_log.info(
                    "heartbeat_supervision_completed",
                    **result,
                )

            return result

        finally:
            loop.close()

    except Exception as exc:
        task_log.error("heartbeat_supervision_failed", error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Orphan Cleanup Task
# ---------------------------------------------------------------------------

class OrphanCleanupError(RuntimeError):
    """An orphan cleanup run did not do what it was asked.

    WP-60 Task 10. Same treatment as RetentionMigrationError below and as
    WP-00 gave the backup tasks: the task RAISES, so a broken scan is a failure
    in the result backend and the DLQ rather than a green row above an unread
    list of errors.
    """


def _report_orphan_cleanup_metrics(report: Any, task_log: Any) -> None:
    """One greppable line for the weekly sweep. WP-61 Task 7.

    Same treatment WP-60 gave the nightly tier migration, and for the same
    reason: a scheduled job whose only trace is a structured log line among
    thousands is a job nobody can tell has stopped working. Three months of
    `run_orphan_cleanup` reporting SUCCESS from a stub is what that looks like.

    NEVER RAISES, and it is defined ABOVE the decorator that follows rather
    than between a decorator and its function -- WP-60 S21.2 records inserting
    a helper into exactly that gap, which handed the `@shared_task` to the
    helper and left the task unregistered.
    """
    try:
        task_log.info(
            "orphan_cleanup_weekly_result",
            dry_run=report.dry_run,
            status=report.status,
            type1=report.type1_seaweedfs_without_db,
            type2=report.type2_db_without_seaweedfs,
            type3=report.type3_zero_reference_count,
            quarantined=report.newly_quarantined,
            permanently_deleted=report.permanently_deleted,
            preserved=report.preserved,
            coverage=report.coverage,
            errors=report.errors,
            summary=(
                f"dry_run={report.dry_run} "
                f"type2={report.type2_db_without_seaweedfs} "
                f"type3={report.type3_zero_reference_count} "
                f"quarantined={report.newly_quarantined} "
                f"deleted={report.permanently_deleted} "
                f"preserved={report.preserved} status={report.status}"
            ),
        )
    except Exception as exc:  # pragma: no cover - reporting must not break the run
        logger.warning("orphan_cleanup_result_line_failed", error=str(exc))


@shared_task(
    name="ivgs_workers.tasks.periodic_tasks.run_orphan_cleanup",
    bind=True,
    max_retries=1,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def run_orphan_cleanup(
    self: Any,
    dry_run: bool | None = None,
    quarantine_only: bool = False,
    exclude_scans: list[str] | None = None,
) -> dict[str, Any]:
    """
    Orphan cleanup per §10.6. WP-60 Task 10 (WP-59 D-2), WP-61 Task 7.

    THE SCHEDULE IS ON, WEEKLY, AND IT CANNOT DELETE. WP-60 left this off with
    the mechanism repaired, guarded and proven on constructed cases; WP-61's
    ruling turns it on under three constraints, all set explicitly by the beat
    entry rather than inherited from a default:

        dry_run=False        it genuinely acts
        quarantine_only=True the permanent-deletion pass does not run
        exclude_scans=[type1] zero-coverage scan skipped, and SAID so

    Quarantine is reversible for QUARANTINE_DAYS and every move is audited.
    Permanent deletion is not reversible by anything, so it is not reachable
    from a schedule.

    What it was before: `celery beat` dispatched
    ``tasks.pipeline_orchestrator.run_orphan_cleanup``, a stub logging
    "Orphan cleanup — stub (Phase 8)", while THIS task -- the real one -- was
    not wired. And the service behind it was inert three times over: two of its
    three scans named ``assets.storage_path``, which does not exist; the
    marking wrote ``assets.status``, which does not exist either; and its
    Type-1 scan reads a filer namespace that is empty.

    ``dry_run`` defaults to TRUE. Passing False is deliberately explicit:
    this service QUARANTINES and then PERMANENTLY DELETES binaries, and there
    must be no way to destroy an object by omitting an argument.

    Args:
        dry_run: None uses the service default (True).
        quarantine_only: WP-61 Task 7. Skip the quarantine-expiry pass, which
            is the only path here that permanently destroys bytes. The weekly
            schedule sets True.
        exclude_scans: WP-61 Task 7. Scan names to skip; each is RECORDED in
            `report.coverage` rather than silently omitted. The weekly schedule
            passes ["type1"] -- it has zero coverage on this fleet (the filer
            namespace is empty; every object is a fid) and returns 0 whether or
            not such orphans exist, which is false assurance. A design decision
            about fid enumeration is owed (WP-60 S12.2).

    Returns:
        CleanupReport as dict.

    Raises:
        OrphanCleanupError: when any scan failed. The report's ``status`` is no
            longer swallowed into a success.
    """
    task_log = logger.bind(
        task_name="run_orphan_cleanup",
        celery_task_id=self.request.id,
    )
    task_log.info(
        "orphan_cleanup_started",
        dry_run=dry_run,
        quarantine_only=quarantine_only,
        exclude_scans=list(exclude_scans or []),
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from services.orphan_cleanup import (
                OrphanCleanupService,
            )
            from shared.database import async_session_factory

            service = OrphanCleanupService(
                db_session_factory=async_session_factory,
                dry_run=True if dry_run is None else bool(dry_run),
                quarantine_only=bool(quarantine_only),
                exclude_scans=exclude_scans or (),
            )

            report = loop.run_until_complete(service.run_cleanup())
            loop.run_until_complete(service.close())

            result = report.model_dump(mode="json")

            # WP-61 Task 7. ONE GREPPABLE LINE CARRYING THE NUMBERS, the same
            # treatment WP-60 gave the nightly tier migration. A weekly job
            # whose only trace is a structured log among thousands is a job
            # nobody can tell has stopped working.
            _report_orphan_cleanup_metrics(report, task_log)

            task_log.info(
                "orphan_cleanup_completed",
                dry_run=report.dry_run,
                quarantine_only=bool(quarantine_only),
                status=report.status,
                type1=report.type1_seaweedfs_without_db,
                type2=report.type2_db_without_seaweedfs,
                type3=report.type3_zero_reference_count,
                quarantined=report.newly_quarantined,
                deleted=report.permanently_deleted,
                preserved=report.preserved,
                coverage=report.coverage,
                errors=report.errors,
                duration_seconds=report.duration_seconds,
            )

            # WP-60 Task 10 / swallow-register entry 29 CLOSED. `report.errors`
            # was appended to and nothing read it: the task returned the report
            # as a success whatever happened, which is how three broken scans
            # recorded SUCCESS nightly.
            if report.status != "ok":
                raise OrphanCleanupError(
                    f"orphan cleanup finished with status={report.status}; "
                    f"errors={report.errors}"
                )

            return result

        finally:
            loop.close()

    except Exception as exc:
        task_log.error("orphan_cleanup_failed", error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Retention Migration Task
# ---------------------------------------------------------------------------


class RetentionMigrationError(RuntimeError):
    """A retention migration run did not do what it was asked.

    WP-59 Task 7 / swallowed-failures register. The previous shape returned the
    report dict whatever happened, so a run whose every tier raised recorded
    Celery SUCCESS. This is the same treatment WP-00 gave the backup tasks:
    the task raises, so the failure is a FAILURE in the result backend and the
    DLQ, not a green row with a list nobody reads.
    """


def _would_move_assets(report: Any) -> int:
    """Total assets a dry run says it would move, across all tier hops.

    WP-60 Task 8. `would_move` is a MAPPING, not a count -- it looks like
    ``{"hot->warm": {"assets": 39, "bytes": 109966042}}`` -- and the first
    version of the gauge did `int(report.would_move or 0)`, which raises
    TypeError on a dict. The push failed on the very first live dispatch.

    Worth recording rather than quietly correcting, because it is the one place
    this package's own design was tested against itself: the failure was
    LOUD. `retention_migration_metrics_push_failed` appeared in the log with
    the TypeError named, which is exactly why that except logs at WARNING with
    the error type instead of shrugging. A swallowed push would have left the
    gauge silently absent -- the defect this task exists to prevent, in the
    mechanism built to prevent it.
    """
    raw = getattr(report, "would_move", None)
    if isinstance(raw, dict):
        total = 0
        for hop in raw.values():
            if isinstance(hop, dict):
                try:
                    total += int(hop.get("assets", 0) or 0)
                except (TypeError, ValueError):
                    continue
            else:
                try:
                    total += int(hop)
                except (TypeError, ValueError):
                    continue
        return total
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _report_retention_migration_metrics(report: Any, task_log: Any) -> None:
    """One greppable line and two gauges, per WP-60 Task 8.

    Never raises. A metrics push that fails must not fail the migration, but it
    must also not be silent -- the whole point of this function is that a
    nightly run which stops working stops being invisible, and a swallowed
    exception here would recreate that in the reporting layer itself.
    """
    try:
        # The line. Deliberately one event name, deliberately flat, so
        # `grep retention_migration_nightly_result` over the worker log is the
        # whole answer to "has the nightly dry run been working?".
        task_log.info(
            "retention_migration_nightly_result",
            dry_run=report.dry_run,
            status=report.status,
            policy_source=getattr(report, "policy_source", None),
            policy_load_error=getattr(report, "policy_load_error", None),
            assets_scanned=report.assets_scanned,
            would_move=getattr(report, "would_move", None),
            transitions_performed=report.transitions_performed,
            assets_deleted=report.assets_deleted,
            errors=report.errors,
            summary=(
                f"dry_run={report.dry_run} scanned={report.assets_scanned} "
                f"would_move={getattr(report, 'would_move', None)} "
                f"moved={report.transitions_performed} "
                f"deleted={report.assets_deleted} status={report.status}"
            ),
        )
    except Exception as exc:  # pragma: no cover - reporting must not break the run
        logger.warning(
            "retention_migration_result_line_failed", error=str(exc)
        )

    # The gauges. Same names, same shape and the same pushgateway job as the
    # four backup writers (scripts/backup.sh:193), so the existing staleness
    # alerting can reach this without a new mechanism.
    try:
        import time as _time
        import urllib.request

        gateway = os.getenv(
            "PROMETHEUS_PUSHGATEWAY", "http://pushgateway:9091"
        ).rstrip("/")
        status_value = 1 if report.status == "ok" else 0
        lines = [
            "# TYPE ivgs_retention_migration_last_status gauge",
            (
                "ivgs_retention_migration_last_status"
                f'{{dry_run="{str(report.dry_run).lower()}"}} '
                f"{status_value}"
            ),
            "# TYPE ivgs_retention_migration_last_timestamp gauge",
            f"ivgs_retention_migration_last_timestamp {int(_time.time())}",
            "# TYPE ivgs_retention_migration_assets_scanned gauge",
            f"ivgs_retention_migration_assets_scanned "
            f"{int(report.assets_scanned or 0)}",
            "# TYPE ivgs_retention_migration_would_move gauge",
            f"ivgs_retention_migration_would_move {_would_move_assets(report)}",
        ]
        body = ("\n".join(lines) + "\n").encode()

        request = urllib.request.Request(
            f"{gateway}/metrics/job/ivgs_retention/instance/node-01",
            data=body,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                raise RuntimeError(f"pushgateway HTTP {response.status}")
    except Exception as exc:
        # Logged at WARNING, not swallowed: if this line appears every night
        # the gauges are stale and the alert family is blind, which is worth
        # knowing before the migration itself needs watching.
        logger.warning(
            "retention_migration_metrics_push_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )


@shared_task(
    name="ivgs_workers.tasks.periodic_tasks.run_retention_migration",
    bind=True,
    max_retries=1,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def run_retention_migration(
    self: Any,
    dry_run: bool | None = None,
    max_transitions: int | None = None,
    allow_delete: bool = False,
) -> dict[str, Any]:
    """
    Retention tier migration per §10.3. WP-59 Task 7.

    WP-61 TASK 6: THE NIGHTLY RUN IS NOW LIVE, CAPPED AT 500, AND CANNOT
    DELETE. The operator's attended runs met every precondition -- a dry run
    reporting 44 would-move and 0 delete, then a capped live pass moving
    exactly 5 with the bytes untouched and all 5 fids still serving HTTP 200.
    The beat entry therefore passes `dry_run=False, max_transitions=500` and
    does NOT pass `allow_delete`, so the destructive hop stays closed.

    THE REAL ONE. There are two tasks with this name on this fleet and until
    this package the SCHEDULED one was the other: Celery beat dispatched
    ``tasks.pipeline_orchestrator.run_retention_migration``, a Phase-5 stub
    that logs a line and returns ``{'status': 'ok', 'message': 'Retention
    migration — stub (Phase 8)'}``. It is in the result backend saying exactly
    that, twice, on 2026-08-24 and 2026-08-25 at 04:00 (``celery_taskmeta``,
    read 2026-08-26). ``services/retention_migration.py`` has therefore never
    executed at all -- WP-57 §3.1 attributed the standstill to that module's
    swallowed ``UndefinedColumn``, and the column defect is real and is fixed,
    but it was never reached. Both had to be repaired for one to matter.

    THE TASK STILL DEFAULTS TO DRY RUN. That has not changed and must not:
    an accidental bare dispatch must report rather than act. What changed in
    WP-61 is that the SCHEDULE now passes `dry_run=False` explicitly, which is
    a visible, reviewable edit in the beat entry rather than a default anyone
    could acquire by omission.

    Args:
        dry_run: None uses the service default (True). Pass False for a real
            pass -- deliberately explicit; there is no way to move an asset by
            omitting an argument.
        max_transitions: Hard ceiling for a capped live pass, and the standing
            cap on the nightly LIVE run (WP-61 Task 6: 500).
        allow_delete: WP-61 Task 6. DEFAULTS TO FALSE and the schedule does not
            set it. The `archived -> deleted` hop is the only one that destroys
            bytes; without this it is refused whatever `retention_policies`
            says. Today all three policy rows have NULL `delete_after_days`, so
            deletion is also unreachable by configuration -- but that is a
            property of DATA, one UPDATE away from changing, with nothing in
            any diff. This makes it a property of CODE.

    Returns:
        MigrationReport as dict.

    Raises:
        RetentionMigrationError: when any tier pass failed. The report's
            ``status`` is no longer swallowed into an ``ok``.
    """
    task_log = logger.bind(
        task_name="run_retention_migration",
        celery_task_id=self.request.id,
    )
    task_log.info(
        "retention_migration_started",
        dry_run=dry_run,
        max_transitions=max_transitions,
        allow_delete=allow_delete,
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from services.retention_migration import (
                RetentionService,
            )
            from shared.database import async_session_factory

            service = RetentionService(
                db_session_factory=async_session_factory,
                dry_run=True if dry_run is None else bool(dry_run),
                max_transitions=max_transitions,
                allow_delete=bool(allow_delete),
            )

            report = loop.run_until_complete(service.run_migration())
            loop.run_until_complete(service.close())

            result = report.model_dump(mode="json")

            task_log.info(
                "retention_migration_completed",
                dry_run=report.dry_run,
                status=report.status,
                scanned=report.assets_scanned,
                transitions=report.transitions_performed,
                deleted=report.assets_deleted,
                preserved=report.assets_preserved,
                capped=report.capped,
                would_move=report.would_move,
                duration_seconds=report.duration_seconds,
            )

            # WP-60 Task 8 — THE NIGHTLY DRY RUN HAS TO BE VISIBLE.
            #
            # WP-59 §7.6 step 3 was a `sed` that uncommented the beat entry and
            # nothing else. That would have put a nightly task on the schedule
            # whose only trace is a structured log line among thousands -- and
            # a dry run that quietly stops scanning looks exactly like a dry
            # run that found nothing to move. That is the WP-57 D-1 hole in
            # miniature: three months of a mechanism reporting health it did
            # not have, because nobody could see it not working.
            #
            # Two things close it. One greppable line carrying the numbers that
            # matter, and the same `ivgs_*_last_*` gauge pair the four backup
            # jobs already push -- so `ivgs_retention_migration_last_timestamp`
            # going stale is visible to the alert family that already exists,
            # rather than needing a new one nobody has wired.
            _report_retention_migration_metrics(report, task_log)

            # WP-59 Task 7: a failed tier pass must RECORD failure, not silence.
            # The report is returned in the exception's payload as well as
            # logged, so the operator loses nothing by the raise.
            if report.status != "ok":
                raise RetentionMigrationError(
                    f"retention migration finished with status={report.status}; "
                    f"errors={report.errors}"
                )

            return result

        finally:
            loop.close()

    except Exception as exc:
        task_log.error(
            "retention_migration_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise


# ---------------------------------------------------------------------------
# Backup Verification Task
# ---------------------------------------------------------------------------

@shared_task(
    name="ivgs_workers.tasks.periodic_tasks.verify_latest_backup",
    bind=True,
    max_retries=1,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def verify_latest_backup(self: Any) -> dict[str, Any]:
    """
    Backup verification — runs daily at 04:00 UTC per §6.4.

    Verifies the integrity of the most recent backup by checking:
    - Backup file exists at recorded path
    - File size matches recorded size
    - SHA-256 checksum matches verification_checksum
    - Updates backup_records table with verification result

    Returns:
        Verification result dict.
    """
    task_log = logger.bind(
        task_name="verify_latest_backup",
        celery_task_id=self.request.id,
    )
    task_log.info("backup_verification_started")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from shared.database import async_session_factory
            from sqlalchemy import text
            import hashlib

            db_factory = async_session_factory

            async def _verify() -> dict[str, Any]:
                async with db_factory() as session:
                    # Get most recent backup record
                    result = await session.execute(
                        text(
                            "SELECT id, backup_type, backup_path, "
                            "size_bytes, verification_checksum "
                            "FROM backup_records "
                            "WHERE status = 'completed' "
                            "ORDER BY completed_at DESC LIMIT 1"
                        )
                    )
                    row = result.fetchone()

                    if row is None:
                        task_log.warning("no_backup_records_found")
                        return {
                            "status": "no_backups",
                            "message": "No completed backups found",
                        }

                    backup_id = str(row[0])
                    backup_type = row[1]
                    backup_path = row[2]
                    expected_size = row[3]
                    expected_checksum = row[4]

                    # Verify file exists and check size
                    import os

                    if not os.path.exists(backup_path):
                        verification_result = "failed"
                        failure_reason = "Backup file not found"
                    else:
                        actual_size = os.path.getsize(backup_path)

                        if expected_size and actual_size != expected_size:
                            verification_result = "failed"
                            failure_reason = (
                                f"Size mismatch: expected {expected_size}, "
                                f"got {actual_size}"
                            )
                        elif expected_checksum:
                            # Compute SHA-256
                            sha256 = hashlib.sha256()
                            with open(backup_path, "rb") as f:
                                for chunk in iter(
                                    lambda: f.read(8192), b""
                                ):
                                    sha256.update(chunk)
                            actual_checksum = sha256.hexdigest()

                            if actual_checksum != expected_checksum:
                                verification_result = "failed"
                                failure_reason = "Checksum mismatch"
                            else:
                                verification_result = "verified"
                                failure_reason = ""
                        else:
                            verification_result = "verified"
                            failure_reason = ""

                    # Update backup record
                    now = datetime.now(timezone.utc)
                    await session.execute(
                        text(
                            "UPDATE backup_records "
                            "SET verified_at = :now, "
                            "status = CASE "
                            "  WHEN :result = 'verified' THEN 'verified' "
                            "  ELSE 'verification_failed' END "
                            "WHERE id = :id"
                        ),
                        {
                            "now": now,
                            "result": verification_result,
                            "id": backup_id,
                        },
                    )
                    await session.commit()

                    if verification_result == "failed":
                        task_log.error(
                            "backup_verification_failed",
                            backup_id=backup_id,
                            backup_type=backup_type,
                            reason=failure_reason,
                        )
                    else:
                        task_log.info(
                            "backup_verification_passed",
                            backup_id=backup_id,
                            backup_type=backup_type,
                        )

                    return {
                        "backup_id": backup_id,
                        "backup_type": backup_type,
                        "verification_result": verification_result,
                        "failure_reason": failure_reason,
                        "verified_at": now.isoformat(),
                    }

            return loop.run_until_complete(_verify())

        finally:
            loop.close()

    except Exception as exc:
        task_log.error("backup_verification_failed", error=str(exc))
        raise


# ---------------------------------------------------------------------------
# M2-3: ModelNodeAvailability poller (ARCH-1 factory node-aware routing)
# ---------------------------------------------------------------------------


async def _reconcile_availability(residency: dict[str, set]) -> dict[str, Any]:
    """Reconcile PG ``model_node_availability`` to the fleet snapshot.

    ``residency`` maps node_id -> set(model_name) for alive, non-draining
    nodes. Servable models present on a node become AVAILABLE; previously-
    AVAILABLE rows no longer backed by residency become UNAVAILABLE (kept, not
    deleted — the factory ignores non-AVAILABLE rows). The scheduler tracks by
    model_name == Model.name (the store name used in reservations).
    """
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from shared.config import settings
    from shared.models.model_store import (
        Model,
        ModelNodeAvailability,
        ModelState,
        NodeAvailabilityStatus,
    )

    servable_states = (ModelState.APPROVED, ModelState.DEPRECATED)
    now = datetime.now(timezone.utc)

    # The task spins a fresh event loop each beat; a module-level async engine
    # would keep connections bound to a prior loop (asyncpg loop-affinity), so
    # bind a dedicated engine to *this* loop and dispose it on the way out.
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(Model.id, Model.name).where(Model.state.in_(servable_states))
                )
            ).all()
            name_to_id = {name: mid for mid, name in rows}

            desired: set = set()
            for node_id, models in residency.items():
                for model_name in models:
                    mid = name_to_id.get(model_name)
                    if mid is not None:
                        desired.add((mid, node_id))

            made = 0
            for mid, node_id in desired:
                stmt = (
                    pg_insert(ModelNodeAvailability)
                    .values(
                        model_id=mid,
                        node_id=node_id,
                        status=NodeAvailabilityStatus.AVAILABLE,
                        served=True,
                        last_health_check=now,
                    )
                    .on_conflict_do_update(
                        constraint="uq_availability_model_node",
                        set_={
                            "status": NodeAvailabilityStatus.AVAILABLE,
                            "served": True,
                            "last_health_check": now,
                        },
                    )
                )
                await session.execute(stmt)
                made += 1

            current = (
                await session.execute(
                    select(ModelNodeAvailability).where(
                        ModelNodeAvailability.status == NodeAvailabilityStatus.AVAILABLE
                    )
                )
            ).scalars().all()
            cleared = 0
            for row in current:
                if (row.model_id, row.node_id) not in desired:
                    row.status = NodeAvailabilityStatus.UNAVAILABLE
                    row.last_health_check = now
                    cleared += 1

            await session.commit()
            return {"nodes": len(residency), "available": made, "cleared": cleared}
    finally:
        await engine.dispose()


@shared_task(
    name="ivgs_workers.tasks.periodic_tasks.poll_model_node_availability",
    bind=True,
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=25,
    soft_time_limit=20,
)
def poll_model_node_availability(self: Any) -> dict[str, Any]:
    """M2-3: project the GPU scheduler's fleet residency into PG
    ``model_node_availability`` — the table the ARCH-1 provider factory's
    ``_pick_node`` reads. One ``GET /fleet`` snapshot -> reconcile.
    """
    import httpx

    from config import WorkerConfig

    cfg = WorkerConfig()
    if not cfg.enable_availability_poller:
        return {"skipped": "disabled"}

    base = cfg.gpu_scheduler.base_url.rstrip("/")
    try:
        resp = httpx.get(
            f"{base}/fleet", timeout=cfg.gpu_scheduler.timeout_seconds
        )
        resp.raise_for_status()
        fleet = resp.json()
    except Exception as exc:
        logger.warning("availability_poll_fleet_unreachable", error=str(exc))
        return {"error": "fleet_unreachable"}

    residency: dict[str, set] = {}
    for node in fleet.get("nodes", []):
        if node.get("is_alive") and not node.get("is_draining"):
            residency[node["node_id"]] = set(node.get("loaded_models", []))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        summary = loop.run_until_complete(_reconcile_availability(residency))
    finally:
        loop.close()

    logger.info("availability_poll_complete", **summary)
    return summary
