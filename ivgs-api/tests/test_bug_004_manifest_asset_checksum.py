"""
Test exposing BUG-004: sha256_hash → content_hash mismatch in manifests.

Bug: app/api/v1/manifests.py lines 176, 201, 345, 354, 359
  - Asset queries use ``sha256_hash`` but actual column is ``content_hash``
  - Manifest generation and validation both crash with
    ``UndefinedColumn: column "sha256_hash" does not exist``

NOTE: BUG-003 (timeline_json) fires first in the generate flow, so this
test isolates the asset-fetch step by seeding a manifest and testing
the validate endpoint which queries assets independently.
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="BUG-004: manifests.py validate uses sha256_hash — actual column is content_hash",
    strict=True,
)
async def test_validate_manifest_uses_content_hash(
    client: AsyncClient,
    db_session,
    operator_token: str,
):
    """POST /api/v1/manifests/{job_id}/manifest/validate should check asset
    checksums, but the SQL selects ``sha256_hash`` which does not exist.
    """
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    manifest_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
    scene_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    from app.core.security import decode_token

    payload = decode_token(operator_token)
    user_id = payload["sub"]

    # Seed user, project, job, scene, asset, manifest
    await db_session.execute(
        text(
            "INSERT INTO users (id, username, password_hash, role, is_active, created_at) "
            "VALUES (:id, :u, 'x', 'operator', true, :now)"
        ),
        {"id": user_id, "u": f"val_test_{uuid.uuid4().hex[:8]}", "now": now},
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

    # Create manifest with timeline referencing the asset
    import json

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

    # Should return validation results, but BUG-004 causes 500
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. "
        "BUG-004: SQL references sha256_hash instead of content_hash."
    )
    data = response.json()
    assert "valid" in data
