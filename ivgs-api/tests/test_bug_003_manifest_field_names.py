"""
Test exposing BUG-003: Wrong column names in manifests raw SQL.

Bug: app/api/v1/manifests.py lines 99-100, 227-229
  - SQL references ``timeline_json`` → actual column is ``timeline``
  - SQL references ``scene_count`` → column does not exist
  - SQL references ``created_at`` → column does not exist in composition_manifests

Both GET and POST/generate endpoints crash with
``UndefinedColumn: column "timeline_json" does not exist``.
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-003: manifests.py uses timeline_json/scene_count/created_at — columns don't exist",
    strict=True,
)
async def test_get_manifest_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """GET /api/v1/manifests/{job_id}/manifest should succeed when
    a manifest exists, but currently crashes because the raw SQL
    references ``timeline_json`` instead of ``timeline``.
    """
    # Create project → render_job → composition_manifest using correct column names
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    manifest_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    from app.models.user import User
    from app.core.security import decode_token

    payload = decode_token(operator_token)
    user_id = payload["sub"]

    await db_session.execute(
        text(
            "INSERT INTO users (id, username, password_hash, role, is_active, created_at) "
            "VALUES (:id, :u, 'x', 'operator', true, :now)"
        ),
        {"id": user_id, "u": f"manifest_test_{uuid.uuid4().hex[:8]}", "now": now},
    )
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
            "VALUES (:id, :pid, 'full_pipeline', 'completed', :now)"
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
            "tl": '{"version":"1.0","scenes":[]}',
        },
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/manifests/{job_id}/manifest",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    # Should be 200, but BUG-003 causes 500 (UndefinedColumn)
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. "
        "BUG-003: raw SQL references timeline_json which does not exist."
    )


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-003: manifest/generate INSERT uses timeline_json/scene_count/created_at",
    strict=True,
)
async def test_generate_manifest_uses_correct_column_names(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """POST /api/v1/manifests/{job_id}/manifest/generate should succeed,
    but crashes because the INSERT references ``timeline_json`` and
    ``scene_count`` — columns that don't exist.
    """
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    scene_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    from app.core.security import decode_token

    payload = decode_token(operator_token)
    user_id = payload["sub"]

    await db_session.execute(
        text(
            "INSERT INTO users (id, username, password_hash, role, is_active, created_at) "
            "VALUES (:id, :u, 'x', 'operator', true, :now)"
        ),
        {"id": user_id, "u": f"gen_test_{uuid.uuid4().hex[:8]}", "now": now},
    )
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
            "VALUES (:id, :pid, 'full_pipeline', 'pending', :now)"
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
        f"/api/v1/manifests/{job_id}/manifest/generate",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"render_params": None},
    )

    # Should be 200/201, but BUG-003 causes 500
    assert response.status_code in (200, 201), (
        f"Expected 200/201 but got {response.status_code}. "
        "BUG-003: INSERT references timeline_json/scene_count/created_at."
    )
