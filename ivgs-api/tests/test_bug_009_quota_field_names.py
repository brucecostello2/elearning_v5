"""
Test exposing BUG-009 + BUG-010: Wrong column names in quotas API.

BUG-009: app/api/v1/quotas.py line 61 and 96
  - Uses ``quota_bytes`` → actual column is ``max_bytes``
  - INSERT/UPSERT fails with UndefinedColumn

BUG-010: app/api/v1/quotas.py line 60
  - Uses ``used_bytes`` → actual column is ``current_bytes``
  - GET attribute access fails with AttributeError
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-009/010: quotas.py uses quota_bytes/used_bytes — actual columns are max_bytes/current_bytes",
    strict=True,
)
async def test_get_quota_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """GET /api/v1/quotas/{entity_type}/{entity_id} should return quota
    info, but crashes because raw SQL row has ``max_bytes`` / ``current_bytes``
    while code reads ``quota_bytes`` / ``used_bytes``.
    """
    entity_id = str(uuid.uuid4())

    await db_session.execute(
        text(
            "INSERT INTO storage_quotas "
            "(id, entity_type, entity_id, max_bytes, current_bytes, alert_threshold_pct, created_at, updated_at) "
            "VALUES (:id, 'project', :eid, 10737418240, 1073741824, 80, :now, :now)"
        ),
        {"id": str(uuid.uuid4()), "eid": entity_id, "now": datetime.now(timezone.utc)},
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/quotas/project/{entity_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    # Should be 200, but BUG-009/010 cause AttributeError or 500
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. "
        "BUG-009/010: code reads quota_bytes/used_bytes but columns are max_bytes/current_bytes."
    )
    data = response.json()
    assert data["quota_bytes"] == 10737418240
    assert data["used_bytes"] == 1073741824
    assert data["available_bytes"] == 10737418240 - 1073741824


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-009: quotas.py PUT uses quota_bytes in INSERT — column is max_bytes",
    strict=True,
)
async def test_set_quota_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    admin_token: str,
):
    """PUT /api/v1/quotas/{entity_type}/{entity_id} should upsert a quota,
    but the INSERT SQL uses ``quota_bytes`` which does not exist — actual
    column is ``max_bytes``.
    """
    entity_id = str(uuid.uuid4())

    response = await client.put(
        f"/api/v1/quotas/project/{entity_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"quota_bytes": 21474836480, "alert_threshold_pct": 85.0},
    )

    # Should be 200, but BUG-009 causes 500 (UndefinedColumn)
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. "
        "BUG-009: INSERT uses quota_bytes but column is max_bytes."
    )
    data = response.json()
    assert data["quota_bytes"] == 21474836480

    # Verify in DB
    row = (
        await db_session.execute(
            text(
                "SELECT max_bytes FROM storage_quotas "
                "WHERE entity_type = 'project' AND entity_id = :eid"
            ),
            {"eid": entity_id},
        )
    ).fetchone()
    assert row is not None
    assert row.max_bytes == 21474836480
