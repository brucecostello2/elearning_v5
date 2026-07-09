"""BUG-001: the backup dispatch error-handler marks the record failed.

The original bug was a NameError in app/api/v1/backup.py's dispatch handler
(``str(exc)`` referenced as ``str(_exc)``). The inline ``_run_backup`` path the
old test imported was removed in the Celery refactor; the failure-status
invariant now lives in two places, each tested where it runs:
  * API dispatch (broker-dispatch failure -> record 'failed') — this test;
  * worker execution (backup script failure -> record 'failed') —
    ivgs-backup-worker/tests/test_backup_tasks.py.
Previously xfailed; un-xfailed now that the invariant is exercised against live
code rather than the removed inline path.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


class TestBackupDispatchErrorHandler:
    async def test_dispatch_failure_marks_record_failed(
        self, client: AsyncClient, admin_token, db_session
    ):
        from unittest.mock import patch

        with patch(
            "app.api.v1.backup.celery_client.send_task",
            side_effect=OSError("broker down"),
        ):
            r = await client.post(
                "/api/v1/backup/trigger",
                json={"backup_type": "full_database"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        # Dispatch failed -> handler marks the record failed and surfaces 503.
        assert r.status_code == 503

        row = (
            await db_session.execute(
                text(
                    "SELECT status, error_message FROM backup_records "
                    "WHERE backup_type = 'full_database' AND status = 'failed' "
                    "ORDER BY started_at DESC LIMIT 1"
                )
            )
        ).fetchone()
        assert row is not None
        assert row.status == "failed"
        assert "broker down" in row.error_message
