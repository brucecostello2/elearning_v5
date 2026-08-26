"""
IVGS v5 — Backup Celery Tasks
==============================

Four Celery tasks corresponding to the four backup operations:

    run_full_database_backup(backup_id=None)   → invokes backup.sh
    run_asset_backup(backup_id=None)           → invokes asset_backup.sh
    run_config_backup(backup_id=None)          → invokes config_backup.sh
    run_verification(backup_id, verify_date)   → invokes verify_backup.sh

The first three take backup_id optionally.  Given one (the API path), the task
updates that row as a backstop.  Given none (the Celery beat path), the script
mints its own UUID and owns the row end to end — beat schedules static
arguments and cannot mint a UUID per firing.

Each task:
  1. Updates backup_records.status to 'running' on entry
  2. Spawns the backup shell script as a subprocess (passing --backup-id)
  3. Parses the script's KEY=VALUE stdout (backup_id, size_bytes, backup_path,
     checksum, record_write) to capture authoritative results
  4. Updates backup_records to 'completed' (success) or 'failed' on exit
  5. On 'failed', writes error_message with last ~2000 chars of stderr, then
     RAISES BackupTaskError

Point 5 is load-bearing.  These tasks used to *return* {'status': 'failed'},
so Celery logged "Task ... succeeded" for a failed backup and no alert
downstream of Celery could fire.  A failure must leave the task in state
FAILURE; the DB row is detail, not the signal.

The backup_records row itself is written by the shell scripts (see
scripts/lib/backup_record.sh), so cron and direct `docker exec` runs are
recorded too.  The updates here are the API path's belt-and-braces: they also
cover the case where the script died before it could write anything.

Tasks ARE idempotent via the backup_id: if a task is re-delivered (Celery
acks_late + worker death), the second invocation finds an existing record
and updates it; no duplicate rows.  The shell scripts themselves use locks
so concurrent invocation on the same date is blocked.

Spec ref: §14.1 (backup operations), §14.2 (verification),
          §6.4 Table 6-7 (task queue routing).
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Dict, NoReturn, Optional

from celery import shared_task
from celery_app import celery_app  # noqa: F401  - ensures app is configured

import psycopg2
import psycopg2.extras

logger = logging.getLogger("ivgs.backup_worker.tasks")


class BackupTaskError(RuntimeError):
    """
    A backup or verification run did not succeed.

    Raised — never returned — so that Celery records the task as FAILURE.
    Returning {'status': 'failed'} made Celery log "Task ... succeeded", which
    is how a 75-day gap in database backups went unnoticed: every alerting
    surface downstream of Celery saw an unbroken run of successes.
    """


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPTS_DIR = os.environ.get("SCRIPTS_DIR", "/scripts")

# Postgres connection (sync — Celery doesn't play well with async DB).
# DSN env var matches the existing IVGS pattern.
DB_DSN = os.environ.get(
    "POSTGRES_DSN_SYNC",
    "postgresql://ivgs:Costello0359@postgres:5432/ivgs",
)


# ---------------------------------------------------------------------------
# Status update helpers (sync — Celery tasks block on these)
# ---------------------------------------------------------------------------

def _get_db_connection():
    """Open a fresh psycopg2 connection per task invocation."""
    return psycopg2.connect(DB_DSN)


def _update_record_running(backup_id: str) -> None:
    """Mark a backup record as running (worker has picked it up)."""
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backup_records "
                "SET status = 'running' "
                "WHERE id = %s::uuid",
                (backup_id,),
            )
        conn.commit()


def _update_record_success(
    backup_id: str,
    size_bytes: int,
    backup_path: str,
    completed_at: datetime,
) -> None:
    """
    Mark a backup record as 'completed' with final size/path.

    Note: the DB enum uses 'completed' (not 'success' as the Pydantic model
    suggests).  See pg_enum check during Phase 1 design discussion.
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backup_records "
                "SET status = 'completed', "
                "    size_bytes = %s, "
                "    backup_path = %s, "
                "    completed_at = %s "
                "WHERE id = %s::uuid",
                (size_bytes, backup_path, completed_at, backup_id),
            )
        conn.commit()


def _update_record_failed(backup_id: str, error_message: str) -> None:
    """
    Mark a backup record as failed with error_message preserved.

    completed_at is COALESCEd rather than assigned. A row that already carries
    a genuine completion time must keep it: stamping now() on a row started
    months earlier is what produced the 110,502-minute durations in the GUI,
    which derives duration as completed_at - started_at.
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backup_records "
                "SET status = 'failed', "
                "    error_message = %s, "
                "    completed_at = COALESCE(completed_at, %s) "
                "WHERE id = %s::uuid",
                (error_message[:2000], datetime.now(timezone.utc), backup_id),
            )
        conn.commit()


def _update_record_verification_failed(backup_id: str, error_message: str) -> None:
    """
    Record that a verification attempt failed, without rewriting the backup.

    A failed verification says something about the verification run, not about
    the dump on the NAS. Marking the record 'failed' destroyed the status of
    backups that had completed — and, for rows verified months earlier, moved
    completed_at forward to now(). Both are why every row in the GUI read
    'failed'.

    So this touches error_message only:
      - status stays 'completed' or 'verified' (the API already gates verify
        to those two states, backup.py:346)
      - completed_at is left alone
      - verified_at is left alone; the success path is the only writer, and a
        historical successful verification is not erased by a later failure

    The Celery task still raises, which is the signal that the attempt failed.
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backup_records "
                "SET error_message = %s "
                "WHERE id = %s::uuid",
                (error_message[:2000], backup_id),
            )
        conn.commit()


def _update_record_verified(
    backup_id: str,
    verification_checksum: str,
    verified_at: datetime,
) -> None:
    """Mark a backup as 'verified' and record the checksum + timestamp."""
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backup_records "
                "SET status = 'verified', "
                "    verification_checksum = %s, "
                "    verified_at = %s, "
                # Clear any error left by an earlier failed attempt, so the
                # row does not carry a stale message alongside a pass.
                "    error_message = NULL "
                "WHERE id = %s::uuid",
                (verification_checksum, verified_at, backup_id),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Stdout parsing
# ---------------------------------------------------------------------------

KV_LINE_RE = re.compile(r"^([a-z_][a-z0-9_]*)=(.+)$")


def _parse_kv_stdout(stdout: str) -> Dict[str, str]:
    """
    Parse KEY=VALUE lines from script stdout.

    The Phase 14 backup scripts (backup.sh, asset_backup.sh, config_backup.sh)
    each emit lines like:
        backup_id=<uuid>
        size_bytes=<int>
        backup_path=<path>
        checksum=<sha256>   # full DB backup only

    Lines not matching KEY=VALUE are silently ignored (JSON log lines, rsync
    progress, etc.).
    """
    result: Dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        m = KV_LINE_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            # Last value wins if duplicate keys appear (shouldn't happen, but
            # tolerate gracefully)
            result[key] = value
    return result


def _safe_int(value: Optional[str], default: int = 0) -> int:
    """Convert a string to int, returning a default on failure."""
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Generic script runner
# ---------------------------------------------------------------------------

def _run_backup_script(
    backup_id: Optional[str],
    script_name: str,
    extra_args: Optional[list] = None,
) -> Dict:
    """
    Run a backup script and return a structured result.

    Returns:
        {
          "returncode": int,
          "kv": Dict[str, str],   # parsed KEY=VALUE pairs
          "stderr": str,          # truncated to 4000 chars
          "stdout_tail": str,     # last 1000 chars of stdout for debugging
        }
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.isfile(script_path):
        return {
            "returncode": 127,
            "kv": {},
            "stderr": f"Script not found: {script_path}",
            "stdout_tail": "",
        }

    # No backup_id means a scheduled (beat) run: omit the flag entirely and let
    # the script mint its own UUID and own its row end to end.  See
    # scripts/lib/backup_record.sh: ensure_backup_id.
    cmd = [script_path]
    if backup_id is not None:
        cmd.append(f"--backup-id={backup_id}")
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Spawning backup subprocess", extra={
        "backup_id": backup_id, "cmd": " ".join(cmd),
    })

    # Inherit POSTGRES_*, BACKUP_GPG_RECIPIENT, PROMETHEUS_PUSHGATEWAY etc.
    # from the worker container's env.  Same env that the script needs.
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        # No timeout here — Celery's task_time_limit kills us if we run too long.
        check=False,
    )

    return {
        "returncode": proc.returncode,
        "kv": _parse_kv_stdout(proc.stdout),
        "stderr": proc.stderr[-4000:],
        "stdout_tail": proc.stdout[-1000:],
    }


# ---------------------------------------------------------------------------
# Task: Full database backup
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_full_database_backup",
    bind=True,
    autoretry_for=(),   # do NOT auto-retry; we want manual control
    max_retries=0,
)
def run_full_database_backup(self, backup_id: Optional[str] = None) -> Dict:
    """
    Invoke /scripts/backup.sh, optionally with --backup-id=<uuid>.

    Two calling conventions:

      backup_id given (API path)
          The API has already inserted a 'running' row and needs the id back
          synchronously.  This task updates that row as a backstop, in case the
          script dies before it can write anything itself.

      backup_id omitted (Celery beat / scheduled path)
          The script mints its own UUID and owns the row end to end.  This task
          writes nothing to backup_records and only supervises the exit code.
          Beat schedules static arguments and cannot mint a UUID per firing,
          which is why this convention exists.

    Returns a dict that Celery stores in the result backend.  The DB row is
    the source of truth — the returned dict is for debugging / Flower / etc.

    Raises BackupTaskError on any failure, so the Celery task state is FAILURE.
    """
    logger.info("run_full_database_backup START", extra={"backup_id": backup_id})

    if backup_id is not None:
        try:
            _update_record_running(backup_id)
        except Exception as exc:
            logger.exception("Failed to mark record as running",
                             extra={"backup_id": backup_id})
            raise BackupTaskError(
                f"backup {backup_id}: DB pre-update failed: {exc}"
            ) from exc

    result = _run_backup_script(backup_id, "backup.sh")

    if result["returncode"] == 0:
        size = _safe_int(result["kv"].get("size_bytes"), 0)
        path = result["kv"].get("backup_path", "")
        # On the scheduled path the id is whatever the script minted; read it
        # back off stdout so the result payload still identifies the row.
        effective_id = backup_id or result["kv"].get("backup_id", "")
        if backup_id is not None:
            try:
                _update_record_success(
                    backup_id=backup_id,
                    size_bytes=size,
                    backup_path=path,
                    completed_at=datetime.now(timezone.utc),
                )
            except Exception as exc:
                logger.exception("Failed to mark record as completed",
                                 extra={"backup_id": backup_id})
                raise BackupTaskError(
                    f"backup {backup_id}: DB post-update failed: {exc}"
                ) from exc

        # The script writes its own row (see backup.sh "backup_records row
        # ownership"). If that write failed it exits 0 anyway — the dump is
        # good — but the run is not fully successful and must not be reported
        # as such.
        if result["kv"].get("record_write") == "failed":
            raise BackupTaskError(
                f"backup {effective_id}: dump succeeded but backup.sh could not "
                f"write its backup_records row; see /var/log/ivgs/backup.log"
            )

        logger.info("run_full_database_backup OK", extra={
            "backup_id": effective_id, "size_bytes": size, "backup_path": path,
        })
        return {
            "backup_id": effective_id,
            "status": "completed",
            "size_bytes": size,
            "backup_path": path,
            "checksum": result["kv"].get("checksum", ""),
        }

    # Failure path
    err = result["stderr"] or f"script exited {result['returncode']}"
    logger.error("run_full_database_backup FAILED",
                 extra={"backup_id": backup_id,
                        "returncode": result["returncode"],
                        "stderr_tail": err[-500:]})
    # On the scheduled path the script's EXIT trap has already marked its own
    # row failed; there is no id here to update.
    if backup_id is not None:
        try:
            _update_record_failed(backup_id, err)
        except Exception:
            # Best effort: the raise below is what makes the failure visible,
            # so a DB write problem here must not mask it.
            logger.exception("Failed to mark record as failed",
                             extra={"backup_id": backup_id})
    raise BackupTaskError(
        f"backup.sh exited {result['returncode']} for backup "
        f"{backup_id or '(scheduled)'}: {err[-500:]}"
    )


# ---------------------------------------------------------------------------
# Task: Physical base backup (WP-59 Task 8 / WP-57 D-2)
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_base_backup",
    bind=True,
    autoretry_for=(),   # same as the others: no auto-retry, manual control
    max_retries=0,
)
def run_base_backup(
    self,
    backup_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict:
    """
    Invoke /scripts/basebackup.sh — the weekly physical base for PITR.

    WHY THIS TASK EXISTS. WP-57 Task 6 established that point-in-time recovery
    was impossible here: the WAL archive was live and faithfully maintained and
    there was no physical base to replay it onto, because `backup.sh` takes a
    logical `pg_dump` and `pg_basebackup` appeared nowhere in the repository.
    WP-57 declined to build one on the grounds that shipping an unrehearsed
    second recovery mechanism creates a second thing nobody has proven (D-2).
    The operator has ruled: implement it. It is built here AND rehearsed —
    Task 10 restores into a scratch database and records the timings, so it
    ships proven rather than merely present.

    SAME PATTERN AS THE OTHER THREE BACKUP JOBS, deliberately. It goes through
    `_run_backup_script`, the script owns its `backup_records` row via
    `lib/backup_record.sh`, failure raises `BackupTaskError` so Celery records
    FAILURE rather than a green row over a broken backup (the WP-00 rule), and
    it pushes the same `ivgs_backup_last_status` / `ivgs_backup_last_timestamp`
    gauges the BackupFailed and BackupStale alerts read. A new backup type that
    invented its own reporting would be a fourth thing to keep in step.

    Args:
        backup_id: Pre-created row id (API path). Omitted on the scheduled path,
            where the script mints its own and owns the row end to end.
        dry_run: Run every pre-flight and report the space the base would need,
            writing nothing. No `backup_records` row is opened or closed.

    Returns:
        Dict of the script's KEY=VALUE output. The DB row is the source of
        truth; this is for Flower and debugging.

    Raises:
        BackupTaskError: on any failure.
    """
    logger.info("run_base_backup START",
                extra={"backup_id": backup_id, "dry_run": dry_run})

    extra_args = ["--dry-run"] if dry_run else None

    if backup_id is not None and not dry_run:
        try:
            _update_record_running(backup_id)
        except Exception as exc:
            logger.exception("Failed to mark base-backup record as running",
                             extra={"backup_id": backup_id})
            raise BackupTaskError(
                f"base backup {backup_id}: DB pre-update failed: {exc}"
            ) from exc

    result = _run_backup_script(backup_id, "basebackup.sh", extra_args)

    if result["returncode"] != 0:
        err = result["stderr"] or f"script exited {result['returncode']}"
        logger.error("run_base_backup FAILED",
                     extra={"backup_id": backup_id,
                            "returncode": result["returncode"],
                            "stderr_tail": err[-500:]})
        if backup_id is not None and not dry_run:
            try:
                _update_record_failed(backup_id, err)
            except Exception:
                logger.exception("Failed to mark base-backup record as failed",
                                 extra={"backup_id": backup_id})
        raise BackupTaskError(
            f"basebackup.sh exited {result['returncode']} for backup "
            f"{backup_id or '(scheduled)'}: {err[-500:]}"
        )

    kv = result["kv"]

    if dry_run:
        logger.info("run_base_backup DRY RUN OK", extra=dict(kv))
        return {
            "status": "dry_run",
            "would_write_to": kv.get("would_write_to", ""),
            "cluster_size_mb": _safe_int(kv.get("cluster_size_mb"), 0),
            "start_lsn": kv.get("start_lsn", ""),
        }

    size = _safe_int(kv.get("size_bytes"), 0)
    path = kv.get("backup_path", "")
    effective_id = backup_id or kv.get("backup_id", "")

    if backup_id is not None:
        try:
            _update_record_success(
                backup_id=backup_id,
                size_bytes=size,
                backup_path=path,
                completed_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.exception("Failed to mark base-backup record as completed",
                             extra={"backup_id": backup_id})
            raise BackupTaskError(
                f"base backup {backup_id}: DB post-update failed: {exc}"
            ) from exc

    # Same rule as the database backup: a base that exists but whose row could
    # not be written is not a fully successful run, because nothing will find it.
    if kv.get("record_write") == "failed":
        raise BackupTaskError(
            f"base backup {effective_id}: pg_basebackup succeeded but "
            f"basebackup.sh could not write its backup_records row; see "
            f"/var/log/ivgs/basebackup.log"
        )

    logger.info("run_base_backup OK", extra={
        "backup_id": effective_id, "size_bytes": size, "backup_path": path,
        "start_lsn": kv.get("start_lsn", ""),
    })
    return {
        "backup_id": effective_id,
        "status": "completed",
        "size_bytes": size,
        "backup_path": path,
        "start_lsn": kv.get("start_lsn", ""),
    }


# ---------------------------------------------------------------------------
# Task: Asset backup
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_asset_backup",
    bind=True,
    autoretry_for=(),
    max_retries=0,
)
def run_asset_backup(self, backup_id: Optional[str] = None) -> Dict:
    """
    Invoke /scripts/asset_backup.sh --backup-id=<uuid>.

    Raises BackupTaskError on any failure.
    """
    logger.info("run_asset_backup START", extra={"backup_id": backup_id})
    if backup_id is not None:
        try:
            _update_record_running(backup_id)
        except Exception as exc:
            raise BackupTaskError(
                f"asset backup {backup_id}: DB pre-update failed: {exc}"
            ) from exc

    result = _run_backup_script(backup_id, "asset_backup.sh")

    if result["returncode"] == 0:
        size = _safe_int(result["kv"].get("size_bytes"), 0)
        path = result["kv"].get("backup_path", "")
        effective_id = backup_id or result["kv"].get("backup_id", "")
        if backup_id is not None:
            _update_record_success(backup_id, size, path,
                                   datetime.now(timezone.utc))
        if result["kv"].get("record_write") == "failed":
            raise BackupTaskError(
                f"asset backup {effective_id}: archive succeeded but "
                f"asset_backup.sh could not write its backup_records row"
            )
        return {"backup_id": effective_id, "status": "completed",
                "size_bytes": size, "backup_path": path}

    err = result["stderr"] or f"script exited {result['returncode']}"
    logger.error("run_asset_backup FAILED",
                 extra={"backup_id": backup_id,
                        "returncode": result["returncode"],
                        "stderr_tail": err[-500:]})
    if backup_id is not None:
        try:
            _update_record_failed(backup_id, err)
        except Exception:
            logger.exception("Failed to mark record as failed",
                             extra={"backup_id": backup_id})
    raise BackupTaskError(
        f"asset_backup.sh exited {result['returncode']} for backup "
        f"{backup_id or '(scheduled)'}: {err[-500:]}"
    )


# ---------------------------------------------------------------------------
# Task: Config backup
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_config_backup",
    bind=True,
    autoretry_for=(),
    max_retries=0,
)
def run_config_backup(self, backup_id: Optional[str] = None) -> Dict:
    """
    Invoke /scripts/config_backup.sh --backup-id=<uuid>.

    Raises BackupTaskError on any failure.
    """
    logger.info("run_config_backup START", extra={"backup_id": backup_id})
    if backup_id is not None:
        try:
            _update_record_running(backup_id)
        except Exception as exc:
            raise BackupTaskError(
                f"config backup {backup_id}: DB pre-update failed: {exc}"
            ) from exc

    result = _run_backup_script(backup_id, "config_backup.sh")

    if result["returncode"] == 0:
        size = _safe_int(result["kv"].get("size_bytes"), 0)
        path = result["kv"].get("backup_path", "")
        effective_id = backup_id or result["kv"].get("backup_id", "")
        if backup_id is not None:
            _update_record_success(backup_id, size, path,
                                   datetime.now(timezone.utc))
        if result["kv"].get("record_write") == "failed":
            raise BackupTaskError(
                f"config backup {effective_id}: archive succeeded but "
                f"config_backup.sh could not write its backup_records row"
            )
        return {"backup_id": effective_id, "status": "completed",
                "size_bytes": size, "backup_path": path}

    err = result["stderr"] or f"script exited {result['returncode']}"
    logger.error("run_config_backup FAILED",
                 extra={"backup_id": backup_id,
                        "returncode": result["returncode"],
                        "stderr_tail": err[-500:]})
    if backup_id is not None:
        try:
            _update_record_failed(backup_id, err)
        except Exception:
            logger.exception("Failed to mark record as failed",
                             extra={"backup_id": backup_id})
    raise BackupTaskError(
        f"config_backup.sh exited {result['returncode']} for backup "
        f"{backup_id or '(scheduled)'}: {err[-500:]}"
    )


# ---------------------------------------------------------------------------
# Task: Verification
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_verification",
    bind=True,
    autoretry_for=(),
    max_retries=0,
)
def run_verification(self, backup_id: str, verify_date: str) -> Dict:
    """
    Invoke /scripts/verify_backup.sh <verify_date>.

    Stream B Phase 5 — durability-first verification:

    The worker does NOT trust the script's stdout to confirm verification
    succeeded.  After verify_backup.sh exits 0, the worker checks the NAS
    filesystem to confirm the script DURABLY wrote its verification block.

    Required files on the NAS for the worker to mark verified:
      1. /mnt/backup/ivgs/db/<date>/backup_record.json must contain a
         top-level "verification" key with status="passed".
      2. /mnt/backup/ivgs/db/<date>/ivgs_backup.sha256 must exist and
         contain a 64-char hex SHA-256 hash (standard sha256sum format).

    If either check fails after a "successful" script exit, the worker
    marks the row 'failed' with a clear error explaining what wasn't
    durable.  This prevents claiming success when the NAS write didn't
    actually land (process crash after script finished but before file
    flushed, NAS becoming read-only mid-write, JSON parse error in
    read-modify-write block of the script, etc.).

    Updates the backup_records row:
      - status                 -> 'verified' (durable success)
      - verification_checksum  -> SHA-256 from ivgs_backup.sha256 file
      - verified_at            -> now()
    OR, on failure:
      - error_message only.  See _update_record_verification_failed: a failed
        verification is not a failed backup, and must not rewrite the backup's
        status or its completed_at.  The raised BackupTaskError is the signal
        that the attempt failed.
    """
    import json
    from pathlib import Path

    def _fail(err: str) -> NoReturn:
        """Record the verification failure and raise so Celery sees FAILURE."""
        logger.error("run_verification FAILED",
                     extra={"backup_id": backup_id,
                            "verify_date": verify_date,
                            "error": err[-500:]})
        try:
            _update_record_verification_failed(backup_id, err)
        except Exception:
            logger.exception("Failed to record verification failure",
                             extra={"backup_id": backup_id})
        raise BackupTaskError(
            f"verification of backup {backup_id} ({verify_date}) failed: "
            f"{err[-500:]}"
        )

    logger.info("run_verification START", extra={
        "backup_id": backup_id, "verify_date": verify_date,
    })

    nas_base = os.environ.get("BACKUP_NAS_PATH", "/mnt/backup/ivgs")
    backup_dir = Path(nas_base) / "db" / verify_date
    record_path = backup_dir / "backup_record.json"
    checksum_path = backup_dir / "ivgs_backup.sha256"

    script_path = os.path.join(SCRIPTS_DIR, "verify_backup.sh")
    if not os.path.isfile(script_path):
        _fail(f"Script not found: {script_path}")

    cmd = [script_path, verify_date]
    logger.info("Spawning verify subprocess",
                extra={"backup_id": backup_id, "cmd": " ".join(cmd)})

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if proc.returncode != 0:
        err = proc.stderr or f"verify script exited {proc.returncode}"
        _fail(f"Verification failed: {err}")

    # Script reported success.  Confirm the durable artifacts exist.

    # 1. Verification block must be in backup_record.json on disk.
    if not record_path.is_file():
        _fail(
            f"verify_backup.sh exited 0 but backup_record.json is missing "
            f"at {record_path}.  The script claimed success but didn't "
            f"persist its verification block."
        )

    record_data = None
    try:
        with open(record_path) as f:
            record_data = json.load(f)
    except Exception as exc:
        _fail(f"backup_record.json unreadable/unparseable: {exc}")

    verification = record_data.get("verification")
    if not verification or verification.get("status") != "passed":
        _fail(
            f"verify_backup.sh exited 0 but backup_record.json does not "
            f"have verification.status == 'passed'.  Actual verification "
            f"block: {verification!r}"
        )

    # 2. Canonical checksum file must exist.
    if not checksum_path.is_file():
        _fail(
            f"verify_backup.sh exited 0 but ivgs_backup.sha256 is missing "
            f"at {checksum_path}."
        )

    try:
        checksum_line = checksum_path.read_text().strip()
        # Standard sha256sum format: "<hash>  <filename>"
        checksum = checksum_line.split()[0] if checksum_line else ""
        # SHA-256 hex is exactly 64 chars
        if not checksum or len(checksum) != 64:
            raise ValueError(
                f"Unexpected sha256 file contents: {checksum_line!r}"
            )
    except Exception as exc:
        _fail(f"Failed to read/parse sha256 file: {exc}")

    # All durable artifacts confirmed.  Mark verified.
    _update_record_verified(
        backup_id=backup_id,
        verification_checksum=checksum,
        verified_at=datetime.now(timezone.utc),
    )

    logger.info("run_verification OK", extra={
        "backup_id": backup_id,
        "verify_date": verify_date,
        "checksum": checksum,
        "verification_block": verification,
    })

    return {
        "backup_id": backup_id,
        "status": "verified",
        "verification_checksum": checksum,
        "verify_date": verify_date,
        "verification_block": verification,
    }
