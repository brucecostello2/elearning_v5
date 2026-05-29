"""
IVGS v5 — Backup Celery Tasks
==============================

Four Celery tasks corresponding to the four backup operations:

    run_full_database_backup(backup_id)   → invokes backup.sh
    run_asset_backup(backup_id)            → invokes asset_backup.sh
    run_config_backup(backup_id)           → invokes config_backup.sh
    run_verification(backup_id, verify_date) → invokes verify_backup.sh

Each task:
  1. Updates backup_records.status to 'running' on entry
  2. Spawns the backup shell script as a subprocess (passing --backup-id)
  3. Parses the script's KEY=VALUE stdout (backup_id, size_bytes, backup_path,
     checksum) to capture authoritative results
  4. Updates backup_records to 'completed' (success) or 'failed' on exit
  5. On 'failed', writes error_message with last ~2000 chars of stderr

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
from typing import Dict, Optional

from celery import shared_task
from celery_app import celery_app  # noqa: F401  - ensures app is configured

import psycopg2
import psycopg2.extras

logger = logging.getLogger("ivgs.backup_worker.tasks")

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
    """Mark a backup record as failed with error_message preserved."""
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backup_records "
                "SET status = 'failed', "
                "    error_message = %s, "
                "    completed_at = %s "
                "WHERE id = %s::uuid",
                (error_message[:2000], datetime.now(timezone.utc), backup_id),
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
                "    verified_at = %s "
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
    backup_id: str,
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

    cmd = [script_path, f"--backup-id={backup_id}"]
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
def run_full_database_backup(self, backup_id: str) -> Dict:
    """
    Invoke /scripts/backup.sh --backup-id=<uuid>.

    Returns a dict that Celery stores in the result backend.  The DB row is
    the source of truth — the returned dict is for debugging / Flower / etc.
    """
    logger.info("run_full_database_backup START", extra={"backup_id": backup_id})

    try:
        _update_record_running(backup_id)
    except Exception as exc:
        logger.exception("Failed to mark record as running",
                         extra={"backup_id": backup_id})
        return {"backup_id": backup_id, "status": "error",
                "error": f"DB pre-update failed: {exc}"}

    result = _run_backup_script(backup_id, "backup.sh")

    if result["returncode"] == 0:
        size = _safe_int(result["kv"].get("size_bytes"), 0)
        path = result["kv"].get("backup_path", "")
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
            return {"backup_id": backup_id, "status": "error",
                    "error": f"DB post-update failed: {exc}",
                    "script_kv": result["kv"]}
        logger.info("run_full_database_backup OK", extra={
            "backup_id": backup_id, "size_bytes": size, "backup_path": path,
        })
        return {
            "backup_id": backup_id,
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
    try:
        _update_record_failed(backup_id, err)
    except Exception:
        logger.exception("Failed to mark record as failed",
                         extra={"backup_id": backup_id})
    return {"backup_id": backup_id, "status": "failed",
            "returncode": result["returncode"], "stderr_tail": err[-500:]}


# ---------------------------------------------------------------------------
# Task: Asset backup
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_asset_backup",
    bind=True,
    autoretry_for=(),
    max_retries=0,
)
def run_asset_backup(self, backup_id: str) -> Dict:
    """Invoke /scripts/asset_backup.sh --backup-id=<uuid>."""
    logger.info("run_asset_backup START", extra={"backup_id": backup_id})
    try:
        _update_record_running(backup_id)
    except Exception as exc:
        return {"backup_id": backup_id, "status": "error",
                "error": f"DB pre-update failed: {exc}"}

    result = _run_backup_script(backup_id, "asset_backup.sh")

    if result["returncode"] == 0:
        size = _safe_int(result["kv"].get("size_bytes"), 0)
        path = result["kv"].get("backup_path", "")
        _update_record_success(backup_id, size, path,
                               datetime.now(timezone.utc))
        return {"backup_id": backup_id, "status": "completed",
                "size_bytes": size, "backup_path": path}

    err = result["stderr"] or f"script exited {result['returncode']}"
    _update_record_failed(backup_id, err)
    return {"backup_id": backup_id, "status": "failed",
            "returncode": result["returncode"], "stderr_tail": err[-500:]}


# ---------------------------------------------------------------------------
# Task: Config backup
# ---------------------------------------------------------------------------

@shared_task(
    name="tasks.backup_tasks.run_config_backup",
    bind=True,
    autoretry_for=(),
    max_retries=0,
)
def run_config_backup(self, backup_id: str) -> Dict:
    """Invoke /scripts/config_backup.sh --backup-id=<uuid>."""
    logger.info("run_config_backup START", extra={"backup_id": backup_id})
    try:
        _update_record_running(backup_id)
    except Exception as exc:
        return {"backup_id": backup_id, "status": "error",
                "error": f"DB pre-update failed: {exc}"}

    result = _run_backup_script(backup_id, "config_backup.sh")

    if result["returncode"] == 0:
        size = _safe_int(result["kv"].get("size_bytes"), 0)
        path = result["kv"].get("backup_path", "")
        _update_record_success(backup_id, size, path,
                               datetime.now(timezone.utc))
        return {"backup_id": backup_id, "status": "completed",
                "size_bytes": size, "backup_path": path}

    err = result["stderr"] or f"script exited {result['returncode']}"
    _update_record_failed(backup_id, err)
    return {"backup_id": backup_id, "status": "failed",
            "returncode": result["returncode"], "stderr_tail": err[-500:]}


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
    OR
      - status                 -> 'failed' with error_message
    """
    import json
    from pathlib import Path

    logger.info("run_verification START", extra={
        "backup_id": backup_id, "verify_date": verify_date,
    })

    nas_base = os.environ.get("BACKUP_NAS_PATH", "/mnt/backup/ivgs")
    backup_dir = Path(nas_base) / "db" / verify_date
    record_path = backup_dir / "backup_record.json"
    checksum_path = backup_dir / "ivgs_backup.sha256"

    script_path = os.path.join(SCRIPTS_DIR, "verify_backup.sh")
    if not os.path.isfile(script_path):
        err = f"Script not found: {script_path}"
        _update_record_failed(backup_id, err)
        return {"backup_id": backup_id, "status": "error", "error": err}

    cmd = [script_path, verify_date]
    logger.info("Spawning verify subprocess",
                extra={"backup_id": backup_id, "cmd": " ".join(cmd)})

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if proc.returncode != 0:
        err = proc.stderr or f"verify script exited {proc.returncode}"
        logger.error("verify_backup.sh FAILED", extra={
            "backup_id": backup_id, "returncode": proc.returncode,
            "stderr_tail": err[-500:],
        })
        _update_record_failed(backup_id, f"Verification failed: {err}")
        return {"backup_id": backup_id, "status": "failed",
                "returncode": proc.returncode,
                "stderr_tail": err[-500:]}

    # Script reported success.  Confirm the durable artifacts exist.

    # 1. Verification block must be in backup_record.json on disk.
    if not record_path.is_file():
        err = (
            f"verify_backup.sh exited 0 but backup_record.json is missing "
            f"at {record_path}.  The script claimed success but didn't "
            f"persist its verification block."
        )
        logger.error("Durability check failed (record missing)",
                     extra={"backup_id": backup_id, "path": str(record_path)})
        _update_record_failed(backup_id, err)
        return {"backup_id": backup_id, "status": "failed", "error": err}

    try:
        with open(record_path) as f:
            record_data = json.load(f)
    except Exception as exc:
        err = f"backup_record.json unreadable/unparseable: {exc}"
        logger.error("Durability check failed (record unreadable)",
                     extra={"backup_id": backup_id, "path": str(record_path)})
        _update_record_failed(backup_id, err)
        return {"backup_id": backup_id, "status": "failed", "error": err}

    verification = record_data.get("verification")
    if not verification or verification.get("status") != "passed":
        err = (
            f"verify_backup.sh exited 0 but backup_record.json does not "
            f"have verification.status == 'passed'.  Actual verification "
            f"block: {verification!r}"
        )
        logger.error("Durability check failed (block missing or wrong status)",
                     extra={"backup_id": backup_id})
        _update_record_failed(backup_id, err)
        return {"backup_id": backup_id, "status": "failed", "error": err}

    # 2. Canonical checksum file must exist.
    if not checksum_path.is_file():
        err = (
            f"verify_backup.sh exited 0 but ivgs_backup.sha256 is missing "
            f"at {checksum_path}."
        )
        logger.error("Durability check failed (checksum file missing)",
                     extra={"backup_id": backup_id, "path": str(checksum_path)})
        _update_record_failed(backup_id, err)
        return {"backup_id": backup_id, "status": "failed", "error": err}

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
        err = f"Failed to read/parse sha256 file: {exc}"
        logger.error("Durability check failed (checksum unreadable)",
                     extra={"backup_id": backup_id})
        _update_record_failed(backup_id, err)
        return {"backup_id": backup_id, "status": "failed", "error": err}

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
