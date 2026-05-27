"""
Test for BUG-004: sha256_hash → content_hash mismatch (FIXED).

Fix: All sha256_hash references changed to content_hash in manifests.py
"""

import json
import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
async def test_validate_manifest_uses_content_hash(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """POST /api/v1/manifests/{job_id}/manifest/validate should check checksums correctly."""
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    manifest_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
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
            "VALUES (:id, :pid, 'full_pipeline', 'completed', :now)"
        ),
        {"id": job_id, "pid": project_id, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO storyboard_scenes "
            "(id, project_id, scene_index, narration_text, visual_description, "
            "media_type, duration_seconds, created_at, updated_at) "
            "VALUES (:id, :pid, 1, 'Narration', 'Visual', 'image', 5.0, :now, :now)"
        ),
        {"id": scene_id, "pid": project_id, "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO assets (id, project_id, scene_id, asset_type, "
            "storage_tier, content_hash, seaweedfs_fid, created_at) "
            "VALUES (:id, :pid, :sid, 'image', 'hot', 'abc123', '1,01abc', :now)"
        ),
        {"id": asset_id, "pid": project_id, "sid": scene_id, "now": now},
    )

    timeline = {
        "version": "1.0",
        "scenes": [
            {
                "scene_index": 1,
                "start_time_ms": 0,
                "end_time_ms": 5000,
                "layers": [
                    {
                        "layer_type": "background",
                        "asset_id": asset_id,
                        "seaweedfs_fid": "1,01abc",
                        "checksum": "abc123",
                        "start_time_ms": 0,
                        "end_time_ms": 5000,
                    }
                ],
            }
        ],
    }
    await db_session.execute(
        text(
            "INSERT INTO composition_manifests (id, job_id, timeline, status, total_duration_ms) "
            "VALUES (:id, :jid, :tl, 'draft', 5000)"
        ),
        {"id": manifest_id, "jid": job_id, "tl": json.dumps(timeline)},
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/manifests/{job_id}/manifest/validate",
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["total_assets_checked"] == 1
    assert data["checksum_matches"] == 1
    assert len(data["errors"]) == 0
