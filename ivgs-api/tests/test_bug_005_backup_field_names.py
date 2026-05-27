"""
Test exposing BUG-005: storage_path → backup_path mismatch in backup API.

Bug: app/api/v1/backup.py lines 141, 268
  - Pydantic schema and raw SQL use ``storage_path``
  - Actual DB column is ``backup_path`` (from model backup_record.py:41)
  - GET /backup/records crashes with AttributeError on ``r.storage_path``
  - Background _run_backup UPDATE crashes with UndefinedColumn

Also exposes BUG-006: ``error_message`` column referenced in SQL
but does not exist in the model or DB at all.
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-005: backup.py uses storage_path — actual column is backup_path",
    strict=True,
)
async def test_list_backup_records_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """GET /api/v1/backup/records should list records correctly, but
    crashes because code accesses ``r.storage_path`` and ``r.error_message``
    which don't exist — actual columns are ``backup_path`` (and no
    error_message column at all).
    """
    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await db_session.execute(
        text(
            "INSERT INTO backup_records "
            "(id, backup_type, status, backup_path, started_at, completed_at) "
            "VALUES (:id, 'full_db', 'completed', '/mnt/backup/test', :now, :now)"
        ),
        {"id": backup_id, "now": now},
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/backup/records",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    # Should be 200 with records, but BUG-005 causes 500
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. "
        "BUG-005: code reads r.storage_path but column is backup_path."
    )
    data = response.json()
    assert data["total"] >= 1
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == backup_id
