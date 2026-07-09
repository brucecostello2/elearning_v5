"""Backup worker task — failure-status invariant (BUG-001, worker half).

``run_full_database_backup`` must mark the backup record 'failed' with the
error preserved when the backup script fails. Driven by an empty SCRIPTS_DIR
(backup.sh missing -> non-zero return -> failure path). Complements the API
dispatch-failure test in ivgs-api/tests/test_bug_001_backup_error_handler.py.
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
