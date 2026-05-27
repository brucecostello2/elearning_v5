"""
Test exposing BUG-001: NameError in backup error handler.

Bug: app/api/v1/backup.py line 299
  - Exception caught as ``_exc`` but referenced as ``exc``
  - When _run_backup() encounters an exception, the error handler itself
    crashes with NameError, leaving the backup stuck in 'running' status.

The test directly invokes _run_backup() with conditions that force an
exception, then checks whether the backup_records row was updated to
'failed' (expected) or remains 'running' (bug behaviour).
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import text


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-001: NameError in backup.py:299 — references 'exc' instead of '_exc'",
    strict=True,
)
async def test_backup_error_handler_updates_status_on_exception(
    db_session,
):
    """When _run_backup hits an exception, the record should be set to 'failed'.

    Currently the except block crashes with ``NameError: name 'exc' is not
    defined`` so the UPDATE never executes and the record stays 'running'.
    """
    backup_id = str(uuid.uuid4())

    # Seed a backup record in 'running' state
    await db_session.execute(
        text(
            "INSERT INTO backup_records (id, backup_type, status, started_at) "
            "VALUES (:id, 'full_db', 'running', :now)"
        ),
        {"id": backup_id, "now": datetime.now(timezone.utc)},
    )
    await db_session.commit()

    # Import the background function
    from app.api.v1.backup import _run_backup

    # Patch create_subprocess_shell to raise an exception
    with patch("asyncio.create_subprocess_shell", side_effect=OSError("disk full")):
        # _run_backup should catch the OSError and update the record.
        # Due to BUG-001 it will raise NameError instead.
        await _run_backup(backup_id, "full_db", db_session)

    # Verify the record was updated to 'failed'
    row = (
        await db_session.execute(
            text("SELECT status FROM backup_records WHERE id = :id"),
            {"id": backup_id},
        )
    ).fetchone()

    assert row is not None
    assert row.status == "failed", (
        f"Expected status='failed' but got '{row.status}'. "
        "BUG-001: NameError in error handler prevents status update."
    )
