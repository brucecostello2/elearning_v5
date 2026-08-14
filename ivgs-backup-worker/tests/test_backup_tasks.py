"""Backup worker task — failure-status invariant (BUG-001, worker half).

``run_full_database_backup`` must mark the backup record 'failed' with the
error preserved when the backup script fails. Driven by an empty SCRIPTS_DIR
(backup.sh missing -> non-zero return -> failure path). Complements the API
dispatch-failure test in ivgs-api/tests/test_bug_001_backup_error_handler.py.

Also covers the two invariants that let a broken backup subsystem look healthy
for 75 days:

  * a failed run must leave the Celery task in state FAILURE, not SUCCESS
  * a failed *verification* must not rewrite the backup's status or move its
    completed_at, which is what produced 110,502-minute durations in the GUI
"""
import os
import uuid
from datetime import UTC, datetime

import psycopg2
import pytest

DSN = os.environ["POSTGRES_DSN_SYNC"]


def _conn():
    return psycopg2.connect(DSN)


@pytest.fixture
def running_record():
    bid = str(uuid.uuid4())
    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO backup_records (id, backup_type, status, started_at) "
            "VALUES (%s::uuid, 'full_database', 'running', %s)",
            (bid, datetime.now(UTC)),
        )
    conn.close()
    yield bid
    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM backup_records WHERE id = %s::uuid", (bid,))
    conn.close()


def _fetch(bid):
    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, error_message FROM backup_records WHERE id = %s::uuid",
            (bid,),
        )
        row = cur.fetchone()
    conn.close()
    return row


def test_backup_script_failure_marks_record_failed(running_record):
    from tasks.backup_tasks import run_full_database_backup

    # Run the task synchronously (handles bind=True self); the missing script
    # makes it take the failure path.
    run_full_database_backup.apply(args=[running_record])

    status, error_message = _fetch(running_record)
    assert status == "failed"
    assert error_message  # the script error is preserved, not dropped


def test_backup_script_failure_fails_the_celery_task(running_record):
    """The task must RAISE, not return {'status': 'failed'}.

    Returning made Celery log "Task ... succeeded" for a failed backup, so
    nothing downstream of Celery could alert on it.
    """
    from tasks.backup_tasks import BackupTaskError, run_full_database_backup

    result = run_full_database_backup.apply(args=[running_record])

    assert result.state == "FAILURE"
    assert isinstance(result.result, BackupTaskError)


@pytest.fixture
def completed_record():
    """A backup that completed months ago and has never been verified."""
    bid = str(uuid.uuid4())
    started = datetime(2026, 5, 29, 21, 37, 40, tzinfo=UTC)
    completed = datetime(2026, 5, 29, 21, 37, 48, tzinfo=UTC)
    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO backup_records "
            "  (id, backup_type, status, started_at, completed_at) "
            "VALUES (%s::uuid, 'full_database', 'completed', %s, %s)",
            (bid, started, completed),
        )
    conn.close()
    yield bid, started, completed
    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM backup_records WHERE id = %s::uuid", (bid,))
    conn.close()


def test_verification_failure_preserves_backup_status_and_completed_at(
    completed_record,
):
    """A failed verification describes the verification, not the backup.

    The old behaviour marked the row 'failed' and set completed_at = now(),
    which on a row started in May and verified in August rendered as a
    110,502-minute backup.
    """
    from tasks.backup_tasks import BackupTaskError, run_verification

    bid, _started, completed = completed_record

    # Missing verify_backup.sh drives the earliest failure path.
    result = run_verification.apply(args=[bid, "2026-05-29"])

    assert result.state == "FAILURE"
    assert isinstance(result.result, BackupTaskError)

    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, completed_at, verified_at, error_message "
            "FROM backup_records WHERE id = %s::uuid",
            (bid,),
        )
        status, completed_at, verified_at, error_message = cur.fetchone()
    conn.close()

    assert status == "completed", "verification failure must not fail the backup"
    assert completed_at == completed, "completed_at must not move"
    assert verified_at is None
    assert error_message, "the verification error is still recorded"


def test_failed_backup_does_not_overwrite_an_existing_completed_at(
    completed_record,
):
    """_update_record_failed COALESCEs completed_at rather than assigning it."""
    from tasks.backup_tasks import _update_record_failed

    bid, _started, completed = completed_record

    _update_record_failed(bid, "some later failure")

    conn = _conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT completed_at FROM backup_records WHERE id = %s::uuid",
            (bid,),
        )
        (completed_at,) = cur.fetchone()
    conn.close()

    assert completed_at == completed
