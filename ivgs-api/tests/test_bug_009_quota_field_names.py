"""
Test for BUG-009 + BUG-010: Wrong column names in quotas API (FIXED).

BUG-009: quota_bytes → max_bytes in SQL
BUG-010: used_bytes → current_bytes in row access
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
async def test_get_quota_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """GET /api/v1/quotas/{entity_type}/{entity_id} should return quota info."""
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

    assert response.status_code == 200
    data = response.json()
    assert data["quota_bytes"] == 10737418240
    assert data["used_bytes"] == 1073741824
    assert data["available_bytes"] == 10737418240 - 1073741824


@pytest.mark.asyncio
async def test_set_quota_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    admin_token: str,
):
    """PUT /api/v1/quotas/{entity_type}/{entity_id} should upsert a quota."""
    entity_id = str(uuid.uuid4())

    response = await client.put(
        f"/api/v1/quotas/project/{entity_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"quota_bytes": 21474836480, "alert_threshold_pct": 85.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["quota_bytes"] == 21474836480

    # Verify in DB using correct column name
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
