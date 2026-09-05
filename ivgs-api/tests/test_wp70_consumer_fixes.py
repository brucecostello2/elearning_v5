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
