"""
WP-70 — CONSUMER FIXES 1: the API side of the nine WP-69 §2 defects.

Each test was written before its fix and fails on the pre-fix tree (the
report records the failing run). Frontend-side checks live in
ivgs-frontend/src/lib/__tests__/wp70-consumer-fixes.test.mjs.
"""
import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── S11: DLQMessageResponse must carry the timestamp the table renders ────

@pytest.mark.asyncio
class TestS11DLQEnteredAt:
    async def test_every_listed_message_carries_entered_dlq_at(
        self, client: AsyncClient, operator_token: str, dlq_messages: list
    ):
        """The DLQ table's "Entered DLQ" column reads `entered_dlq_at`.
        The row has a timestamp (`created_at`); the response must expose it
        under the name the consumer reads, equal to the row's own value."""
        r = await client.get("/api/v1/dlq/messages", headers=_auth(operator_token))
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) >= len(dlq_messages)
        for row in rows:
            assert "entered_dlq_at" in row, f"missing on {sorted(row)}"
            assert row["entered_dlq_at"] == row["created_at"]


# ── S6: the upload call the hook now makes returns 2xx ───────────────────

@pytest.mark.asyncio
class TestS6UploadPath:
    async def test_post_to_assets_upload_returns_2xx_on_a_fixture_project(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        """useAssets.uploadAsset now POSTs multipart form data to
        /projects/{id}/assets/upload. This is that call, made from the API's
        own test client, on a fixture project."""
        import io
        r = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("clip.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\0" * 64), "image/png")},
            data={"asset_type": "image"},
            headers=_auth(operator_token),
        )
        assert 200 <= r.status_code < 300, r.text
        assert r.json()["asset_type"] == "image"

    async def test_post_to_the_list_path_is_405_which_is_what_the_hook_used_to_do(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        """The pre-fix hook POSTed to the GET-only list path."""
        import io
        r = await client.post(
            f"/api/v1/projects/{project_id}/assets",
            files={"file": ("clip.png", io.BytesIO(b"x"), "image/png")},
            data={"asset_type": "image"},
            headers=_auth(operator_token),
        )
        assert r.status_code == 405, r.text

    async def test_the_assets_page_form_without_asset_type_is_refused_422(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        """WP-70 Decision D-2, pinned as the API contract: `asset_type` is
        `Form(...)` (required) on the upload route. The project Assets page
        (app/projects/[id]/assets/page.tsx) appends only `file` and
        `project_id`, so its upload will be refused with 422 even after the
        hook's path is corrected. That page is outside this package's file
        list and is reported, not edited."""
        import io
        r = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("clip.png", io.BytesIO(b"x"), "image/png")},
            data={"project_id": project_id},
            headers=_auth(operator_token),
        )
        assert r.status_code == 422, r.text


# ── S4: POST /api/v1/retention/run ───────────────────────────────────────

RETENTION_BEAT_TASK = "ivgs_workers.tasks.periodic_tasks.run_retention_migration"


@pytest.fixture
def retention_send_task(monkeypatch):
    """Record every send_task on the API's Celery producer; push nothing."""
    from app.services import celery_producer

    calls = []

    def _stub(name, args=None, kwargs=None, queue=None, **extra):
        calls.append({"name": name, "args": args, "kwargs": kwargs, "queue": queue, **extra})

        class _R:
            id = "wp70-stub-task-id"

        return _R()

    monkeypatch.setattr(celery_producer.celery_app, "send_task", _stub)
    return calls


@pytest.mark.asyncio
class TestS4RetentionRun:
    async def test_the_route_exists_and_refuses_a_viewer(
        self, client: AsyncClient, viewer_token: str, retention_send_task: list
    ):
        r = await client.post("/api/v1/retention/run", headers=_auth(viewer_token))
        assert r.status_code == 403, f"{r.status_code} {r.text}"
        assert retention_send_task == []

    async def test_the_route_refuses_an_operator(
        self, client: AsyncClient, operator_token: str, retention_send_task: list
    ):
        r = await client.post("/api/v1/retention/run", headers=_auth(operator_token))
        assert r.status_code == 403, f"{r.status_code} {r.text}"
        assert retention_send_task == []

    async def test_an_admin_enqueues_the_retention_beat_task_exactly_once(
        self, client: AsyncClient, admin_token: str, retention_send_task: list
    ):
        r = await client.post("/api/v1/retention/run", headers=_auth(admin_token))
        assert r.status_code == 202, f"{r.status_code} {r.text}"
        assert r.json() == {"task_id": "wp70-stub-task-id"}
        assert len(retention_send_task) == 1, retention_send_task
        call = retention_send_task[0]
        assert call["name"] == RETENTION_BEAT_TASK
        assert call["queue"] == "default"
        # The beat entry's own kwargs (celery_app.py "retention-migration"):
        # a manual run is the nightly run, not a dry run.
        assert call["kwargs"] == {"dry_run": False, "max_transitions": 500}

    async def test_a_broker_failure_is_a_503_not_a_500(
        self, client: AsyncClient, admin_token: str, monkeypatch
    ):
        from app.services import celery_producer

        def _boom(*a, **kw):
            raise ConnectionError("broker down")

        monkeypatch.setattr(celery_producer.celery_app, "send_task", _boom)
        r = await client.post("/api/v1/retention/run", headers=_auth(admin_token))
        assert r.status_code == 503, f"{r.status_code} {r.text}"


# ── S10: preset apply writes the actor clip under the member Stage 6 reads ──

async def _upload_reference_clip(client: AsyncClient, headers: dict) -> dict:
    r = await client.post(
        "/api/v1/library/assets",
        headers=headers,
        files={"file": ("sarah.mp4", b"SARAHCLIP", "video/mp4")},
        data={"kind": "reference_clip", "name": "Sarah plate", "owner_scope": "user"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
class TestS10PresetActorClip:
    async def test_after_apply_the_stage6_lookup_finds_the_clip_and_talking_head_is_null(
        self, client: AsyncClient, operator_user, project_id: str, db_session
    ):
        """Stage 6 fetches the actor clip with
        `GET /projects/{id}/assets?asset_type=reference_clip&limit=1`
        (pipeline_orchestrator_v2._fetch_reference_clip_id). The preset apply
        wrote it as `talking_head`, so the lookup was always empty and every
        preset-driven project skipped its talking head. And
        `projects.talking_head_asset_id` names the RENDERED head — apply must
        leave it null.

        The route's page-size parameter is `per_page`, not `limit`; `limit`
        is ignored by FastAPI. The query below sends both, as the orchestrator
        sends `limit`, and the assertion is on the FIRST row either way."""
        import uuid as _uuid
        from sqlalchemy import select
        from app.models.asset import Asset
        from app.models.project import Project
        from app.services.preset_service import PresetService
        from tests.conftest import make_auth_header

        user, _ = operator_user
        headers = make_auth_header(user)

        clip = await _upload_reference_clip(client, headers)
        actor = await client.post(
            "/api/v1/actors", headers=headers,
            json={"name": "Sarah — corporate", "reference_clip_id": clip["id"]},
        )
        assert actor.status_code == 201, actor.text
        preset = await client.post(
            "/api/v1/presets", headers=headers,
            json={"name": "Corporate 2026", "payload": {"actor_id": actor.json()["id"]}},
        )
        assert preset.status_code == 201, preset.text

        # The service, directly.
        result = await PresetService(db_session).apply_to_project(
            preset_id=_uuid.UUID(preset.json()["id"]),
            project_id=_uuid.UUID(project_id),
            actor_user_id=user.id,
        )
        assert any("Sarah" in a for a in result["applied"]), result

        # The lookup Stage 6 makes.
        r = await client.get(
            f"/api/v1/projects/{project_id}/assets?asset_type=reference_clip&limit=1&per_page=1",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) == 1, f"Stage 6's lookup found {len(rows)} reference_clip rows"
        assert rows[0]["asset_type"] == "reference_clip"

        # The row it found is the actor's clip, referenced not copied.
        found = await db_session.scalar(select(Asset).where(Asset.id == _uuid.UUID(rows[0]["id"])))
        assert str(found.library_asset_id) == clip["id"]

        # The rendered-head column stays null.
        project = await db_session.scalar(select(Project).where(Project.id == _uuid.UUID(project_id)))
        await db_session.refresh(project)
        assert project.talking_head_asset_id is None, (
            "talking_head_asset_id names the RENDERED head; preset apply must not set it"
        )


# ══ WP-70 v2 ═══════════════════════════════════════════════════════════════

# ── S5 + N3: the job-status socket's real authentication contract ─────────

def _ws_client():
    from starlette.testclient import TestClient
    from main import app
    return TestClient(app)


def _mock_redis_one_terminal_message():
    """redis.asyncio stand-in that delivers one COMPLETE frame then ends."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    frames = [{"type": "status", "job_id": "job-42", "status": "COMPLETE"}]

    async def get_message(**kw):
        if frames:
            return {"type": "message", "data": json.dumps(frames.pop(0)).encode()}
        raise RuntimeError("no more frames")

    pubsub.get_message = get_message
    r = MagicMock()
    r.pubsub.return_value = pubsub
    r.close = AsyncMock()
    return r


@pytest.mark.asyncio
class TestS5N3JobStatusSocketAuth:
    """The real `_authenticate_ws` (ws_logs.py), not the mock the older WS
    tests patch in: `?token=<access JWT>`, user must exist and be active."""

    async def test_a_valid_token_is_accepted(self, operator_user, db_session):
        from datetime import timedelta
        from unittest.mock import patch
        from starlette.websockets import WebSocketDisconnect
        from app.core.security import create_access_token

        user, _ = operator_user
        token = create_access_token(user_id=str(user.id), role=user.role,
                                    expires_delta=timedelta(minutes=5))
        with patch("redis.asyncio.from_url", return_value=_mock_redis_one_terminal_message()):
            with _ws_client() as c:
                with c.websocket_connect(f"/api/v1/ws/jobs/job-42/status?token={token}") as ws:
                    frame = ws.receive_json()
        assert frame["status"] == "COMPLETE", frame

    async def test_no_token_is_rejected_1008(self, operator_user):
        from starlette.websockets import WebSocketDisconnect
        with _ws_client() as c:
            with pytest.raises(WebSocketDisconnect) as ei:
                with c.websocket_connect("/api/v1/ws/jobs/job-42/status"):
                    pass
        assert ei.value.code == 1008

    async def test_an_expired_token_is_rejected_1008(self, operator_user):
        from datetime import timedelta
        from starlette.websockets import WebSocketDisconnect
        from app.core.security import create_access_token

        user, _ = operator_user
        expired = create_access_token(user_id=str(user.id), role=user.role,
                                      expires_delta=timedelta(seconds=-60))
        with _ws_client() as c:
            with pytest.raises(WebSocketDisconnect) as ei:
                with c.websocket_connect(f"/api/v1/ws/jobs/job-42/status?token={expired}"):
                    pass
        assert ei.value.code == 1008
