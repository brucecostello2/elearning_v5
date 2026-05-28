"""
Test for BUG-005: storage_path → backup_path mismatch (FIXED).

Fix: All storage_path references changed to backup_path in backup.py
Also covers BUG-006 (error_message column now exists).
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
async def test_list_backup_records_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """GET /api/v1/backup/records should list records correctly."""
    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await db_session.execute(
        text(
            "INSERT INTO backup_records "
            "(id, backup_type, status, backup_path, error_message, started_at, completed_at) "
            "VALUES (:id, 'full_database', 'completed', '/mnt/backup/test', NULL, :now, :now)"
        ),
        {"id": backup_id, "now": now},
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/backup/records",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["data"]) >= 1

    record = data["data"][0]
    assert record["id"] == backup_id
    assert record["backup_path"] == "/mnt/backup/test"
    assert record["error_message"] is None
