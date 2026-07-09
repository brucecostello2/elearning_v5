"""
Test for BUG-003: Wrong column names in manifests raw SQL (FIXED).

Fixes applied:
- timeline_json → timeline in SQL
- scene_count removed from SQL (computed from timeline JSON)
- created_at removed from INSERT (not in composition_manifests)
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
async def test_get_manifest_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """GET /api/v1/manifests/{job_id}/manifest should succeed with correct columns."""
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    manifest_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    from app.core.security import decode_token

    payload = decode_token(operator_token)
    user_id = payload["sub"]

    # User already created by operator_token fixture — just insert project data
    await db_session.execute(
        text(
            "INSERT INTO projects (id, name, state, created_by, created_at, updated_at) "
            "VALUES (:id, 'P', 'DRAFT', :uid, :now, :now)"
        ),
        {"id": project_id, "uid": user_id, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO render_jobs (id, project_id, job_type, status, created_at) "
            "VALUES (:id, :pid, 'final_render', 'success', :now)"
        ),
        {"id": job_id, "pid": project_id, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO composition_manifests (id, job_id, timeline, status, total_duration_ms, locked_at) "
            "VALUES (:id, :jid, :tl, 'draft', 5000, NULL)"
        ),
        {
            "id": manifest_id,
            "jid": job_id,
            "tl": '{"version":"1.0","scenes":[{"scene_index":1},{"scene_index":2}]}',
        },
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/jobs/{job_id}/manifest",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "draft"
    assert data["scene_count"] == 2  # computed from timeline JSON
    assert "timeline_json" in data
    assert data["timeline_json"]["version"] == "1.0"


@pytest.mark.asyncio
async def test_generate_manifest_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """POST /api/v1/manifests/{job_id}/manifest/generate should succeed."""
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    scene_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    from app.core.security import decode_token

    payload = decode_token(operator_token)
    user_id = payload["sub"]

    # User already created by operator_token fixture — just insert project data
    await db_session.execute(
        text(
            "INSERT INTO projects (id, name, state, created_by, created_at, updated_at) "
            "VALUES (:id, 'P', 'DRAFT', :uid, :now, :now)"
        ),
        {"id": project_id, "uid": user_id, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO render_jobs (id, project_id, job_type, status, created_at) "
            "VALUES (:id, :pid, 'final_render', 'pending', :now)"
        ),
        {"id": job_id, "pid": project_id, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO storyboard_scenes "
            "(id, project_id, scene_index, narration_text, visual_description, "
            "media_type, duration_seconds, created_at, updated_at) "
            "VALUES (:id, :pid, 1, 'Hello', 'A test', 'image', 10.0, :now, :now)"
        ),
        {"id": scene_id, "pid": project_id, "now": now},
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/jobs/{job_id}/manifest/generate",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"render_params": None},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "draft"
    assert data["scene_count"] == 1
    assert data["total_duration_ms"] == 10000
