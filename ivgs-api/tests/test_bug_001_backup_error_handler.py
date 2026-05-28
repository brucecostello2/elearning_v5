"""
Test for BUG-001: NameError in backup error handler (FIXED).

Bug was: app/api/v1/backup.py line 299 — exc → _exc
Fix: Changed str(exc) to str(_exc)
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import text


@pytest.mark.asyncio
async def test_backup_error_handler_updates_status_on_exception(
    db_session,
):
    """When _run_backup hits an exception, the record should be set to 'failed'."""
    backup_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            "INSERT INTO backup_records (id, backup_type, status, started_at) "
            "VALUES (:id, 'full_database', 'running', :now)"
        ),
        {"id": backup_id, "now": datetime.now(timezone.utc)},
    )
    await db_session.commit()

    from app.api.v1.backup import _run_backup

    with patch("asyncio.create_subprocess_shell", side_effect=OSError("disk full")):
        await _run_backup(backup_id, "full_database", db_session)

    row = (
        await db_session.execute(
            text("SELECT status, error_message FROM backup_records WHERE id = :id"),
            {"id": backup_id},
        )
    ).fetchone()

    assert row is not None
    assert row.status == "failed"
    assert "disk full" in row.error_message
