"""WP-45 Task 3 — the eight sites that returned 202 and dispatched nothing.

**Every test here asserts a BROKER MESSAGE, not a status code.** That is the
whole point and it is the acceptance criterion the work package set, because a
202 is exactly what all eight endpoints already returned while doing nothing.
A test that checked the status would have passed against the defect.

The eight sites, and what each used to do instead of dispatching:

    1 scene regenerate    inserted a storyboard_generation row
    2 asset regenerate    inserted a row typed from the asset
    3 job cancel          marked the row cancelled, left the GPU running
    4 DLQ replay + bulk   marked messages replayed, replayed none
    5 localisation retry  named pipeline.localise, a task registered nowhere
    6 quality reject      logged "(stub - Phase 8)"
    7 job resume          named pipeline.execute_stage, also not a task
    8 Prompt Playground   returned a hand-written placeholder string

`send_task` is patched at `app.services.celery_producer.celery_app`, which is
the single producer every one of these paths imports. Patching there rather than
per-module means a site that stops going through the producer fails these tests
rather than passing them by accident.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text


class SentTask:
    """One captured send_task call."""

    def __init__(self, name, args, kwargs, queue):
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.queue = queue

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<SentTask {self.name} queue={self.queue}>"


class Broker:
    """A stand-in for the Celery producer that records what was published."""

    def __init__(self):
        self.sent: list[SentTask] = []
        self.revoked: list[tuple] = []
        self.control = MagicMock()
        self.control.revoke.side_effect = self._revoke

    def _revoke(self, task_id, **kwargs):
        self.revoked.append((task_id, kwargs))

    def send_task(self, name, args=None, kwargs=None, queue=None, **_ignored):
        self.sent.append(SentTask(name, args, kwargs, queue))
        result = MagicMock()
        result.id = f"celery-{len(self.sent)}"
        return result

    @property
    def names(self):
        return [t.name for t in self.sent]


@pytest.fixture
def broker():
    """Patch the one producer every dispatch path imports."""
    b = Broker()
    with patch("app.services.celery_producer.celery_app", b):
        yield b


# ---------------------------------------------------------------------------
# Fixtures: the rows each site needs
# ---------------------------------------------------------------------------

@pytest.fixture
async def scene_project(db_session, operator_token):
    """A project with one image scene, owned by the operator."""
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.storyboard_scene import StoryboardScene

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="WP-45 dispatch project",
        description="a project that expects things to actually run",
        state="MEDIA_GENERATION",
        created_by=owner,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    scene = StoryboardScene(
        id=uuid.uuid4(),
        project_id=project.id,
        scene_index=0,
        narration_text="Multiply the tens first.",
        visual_description="A worked sum on a board",
        media_type="image",
        duration_seconds=12.0,
        camera_angle="wide",
    )
    db_session.add(scene)
    await db_session.flush()
    await db_session.commit()

    # WP-62 Task 2(c). Media generation is now blocking on a recorded, CURRENT
    # storyboard approval, and a regeneration IS media generation. This fixture
    # always implied an approved storyboard -- the project is in
    # MEDIA_GENERATION -- and there was nowhere to record one until now.
    from tests.conftest import record_storyboard_approval

    await record_storyboard_approval(db_session, project.id, owner)
    return {"project_id": str(project.id), "scene_id": str(scene.id)}


@pytest.fixture
async def scene_asset(db_session, scene_project):
    """An image asset linked to that scene."""
    from app.models.asset import Asset

    asset = Asset(
        id=uuid.uuid4(),
        project_id=uuid.UUID(scene_project["project_id"]),
        scene_id=uuid.UUID(scene_project["scene_id"]),
        asset_type="image",
        seaweedfs_fid="3,01abcdef",
        seaweedfs_path="/ivgs/images/x/image.png",
        mime_type="image/png",
        file_size_bytes=1024,
        content_hash="a" * 64,
        storage_tier="hot",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    await db_session.commit()
    return {**scene_project, "asset_id": str(asset.id)}


# ---------------------------------------------------------------------------
# Site 1 — scene regenerate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite1SceneRegenerate:

    async def test_a_broker_message_is_produced(
        self, client: AsyncClient, operator_token, scene_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{scene_project['project_id']}"
            f"/scenes/{scene_project['scene_id']}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 202, resp.text

        # THE ASSERTION. The old code returned exactly this 202 with an empty
        # broker, and no test noticed for as long as the defect existed.
        assert len(broker.sent) == 1, (
            "a 202 with no broker message is the defect this test exists for"
        )
        sent = broker.sent[0]
        assert sent.name == "tasks.pipeline_orchestrator_v2.dispatch_media_generation"
        assert sent.queue == "default"

    async def test_the_message_carries_that_scene_and_its_current_fields(
        self, client: AsyncClient, operator_token, scene_project, broker,
    ):
        await client.post(
            f"/api/v1/projects/{scene_project['project_id']}"
            f"/scenes/{scene_project['scene_id']}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        payload = broker.sent[0].kwargs["dispatch_input"]
        assert payload["project_id"] == scene_project["project_id"]
        assert len(payload["scenes"]) == 1
        scene = payload["scenes"][0]
        assert scene["scene_id"] == scene_project["scene_id"]
        # Ruled semantics: the scene's CURRENT fields, not a replay of whatever
        # produced the asset being replaced.
        assert scene["narration_text"] == "Multiply the tens first."
        assert scene["media_type"] == "image"
        assert scene["camera_angle"] == "wide"

    async def test_the_job_row_names_the_work_that_will_run(
        self, client: AsyncClient, operator_token, scene_project, broker,
    ):
        # It used to insert job_type='storyboard_generation', which is the LLM
        # stage, not the media re-render a Regen button performs.
        resp = await client.post(
            f"/api/v1/projects/{scene_project['project_id']}"
            f"/scenes/{scene_project['scene_id']}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.json()["job_type"] == "image_generation"

    async def test_the_dispatched_job_id_is_the_row_that_was_created(
        self, client: AsyncClient, operator_token, scene_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{scene_project['project_id']}"
            f"/scenes/{scene_project['scene_id']}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # Without this the worker reports completion against a job nobody is
        # watching, which is how rows end up stranded at 'pending' forever.
        assert broker.sent[0].kwargs["dispatch_input"]["job_id"] == resp.json()["id"]

    async def test_a_missing_scene_dispatches_nothing(
        self, client: AsyncClient, operator_token, scene_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{scene_project['project_id']}"
            f"/scenes/{uuid.uuid4()}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 404
        assert broker.sent == []


# ---------------------------------------------------------------------------
# Site 2 — asset regenerate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite2AssetRegenerate:

    async def test_a_broker_message_is_produced(
        self, client: AsyncClient, operator_token, scene_asset, broker,
    ):
        resp = await client.post(
            f"/api/v1/assets/{scene_asset['asset_id']}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 202, resp.text
        assert len(broker.sent) == 1
        assert broker.sent[0].name == (
            "tasks.pipeline_orchestrator_v2.dispatch_media_generation"
        )

    async def test_it_regenerates_the_assets_scene(
        self, client: AsyncClient, operator_token, scene_asset, broker,
    ):
        await client.post(
            f"/api/v1/assets/{scene_asset['asset_id']}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        scenes = broker.sent[0].kwargs["dispatch_input"]["scenes"]
        assert [s["scene_id"] for s in scenes] == [scene_asset["scene_id"]]

    async def test_an_asset_with_no_scene_refuses_instead_of_pretending(
        self, client: AsyncClient, operator_token, db_session, scene_project, broker,
    ):
        from app.models.asset import Asset

        orphan = Asset(
            id=uuid.uuid4(),
            project_id=uuid.UUID(scene_project["project_id"]),
            scene_id=None,
            asset_type="reference_clip",
            storage_tier="hot",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(orphan)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/assets/{orphan.id}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 409
        assert broker.sent == []


# ---------------------------------------------------------------------------
# Site 3 — job cancel (a live operator-facing bug)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite3JobCancel:

    async def _job_with_task(self, db_session, operator_token):
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        project = Project(
            id=uuid.uuid4(), name="cancel me", state="MEDIA_GENERATION",
            created_by=owner,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="image_generation",
            status="running", celery_task_id="task-on-a-gpu",
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()
        return job

    async def test_the_running_task_is_revoked(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        job = await self._job_with_task(db_session, operator_token)
        resp = await client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        # THE ASSERTION. The row was always marked cancelled; the GPU work
        # carried on to completion because the revoke was a comment.
        assert len(broker.revoked) == 1, "cancel must reach the running task"
        task_id, kwargs = broker.revoked[0]
        assert task_id == "task-on-a-gpu"

    async def test_revoke_terminates_rather_than_only_preventing_a_start(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        job = await self._job_with_task(db_session, operator_token)
        await client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        _task_id, kwargs = broker.revoked[0]
        # Without terminate=True, revoke only stops a task that has not started
        # - which is exactly the case a Cancel button is NOT for.
        assert kwargs.get("terminate") is True
        # SIGTERM so IVGSBaseTask.on_failure runs and the GPU reservation is
        # released rather than leaked (WP-08).
        assert kwargs.get("signal") == "SIGTERM"

    async def test_a_job_with_no_task_says_so_instead_of_claiming_a_revoke(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        project = Project(
            id=uuid.uuid4(), name="never dispatched", state="DRAFT",
            created_by=owner,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="final_render",
            status="pending", celery_task_id=None,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert broker.revoked == []
        # "cancelled" and "cancelled, and nothing was running" are different
        # facts and the row says which.
        assert "not revoked" in resp.json()["error_message"]


# ---------------------------------------------------------------------------
# Site 4 — DLQ replay, single and bulk (a live operator-facing bug)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite4DlqReplay:

    async def test_single_replay_produces_a_broker_message(
        self, client: AsyncClient, operator_token, dlq_messages, broker,
    ):
        resp = await client.post(
            f"/api/v1/dlq/messages/{dlq_messages[0]['id']}/replay",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert len(broker.sent) == 1
        assert broker.sent[0].name == dlq_messages[0]["task_name"]

    async def test_it_replays_onto_the_original_queue(
        self, client: AsyncClient, operator_token, dlq_messages, broker,
    ):
        await client.post(
            f"/api/v1/dlq/messages/{dlq_messages[0]['id']}/replay",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert broker.sent[0].queue == "celery"

    async def test_a_failed_dispatch_leaves_the_message_unresolved(
        self, client: AsyncClient, operator_token, dlq_messages, db_session,
    ):
        # The old order marked the row replayed and dispatched nothing, so a
        # message that had NOT been re-run dropped out of the unresolved list.
        # The DLQ's one job is to retain what failed.
        exploding = Broker()
        exploding.send_task = MagicMock(side_effect=RuntimeError("broker down"))
        with patch("app.services.celery_producer.celery_app", exploding):
            resp = await client.post(
                f"/api/v1/dlq/messages/{dlq_messages[0]['id']}/replay",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 502

        row = await db_session.execute(
            text("SELECT resolution FROM dead_letter_messages WHERE id = :i"),
            {"i": dlq_messages[0]["id"]},
        )
        assert row.scalar() is None, (
            "a message that was not re-enqueued must stay in the DLQ"
        )

    async def test_bulk_replay_produces_one_message_per_row(
        self, client: AsyncClient, operator_token, dlq_messages, broker,
    ):
        resp = await client.post(
            "/api/v1/dlq/bulk-replay",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["replayed_count"] == len(dlq_messages)
        assert len(broker.sent) == len(dlq_messages)

    async def test_bulk_replayed_count_counts_dispatches_not_rows_touched(
        self, client: AsyncClient, operator_token, dlq_messages, db_session, broker,
    ):
        # One row with no task_name cannot be re-enqueued. It must be counted as
        # skipped, not folded into replayed_count - the old count was the size
        # of the filter, not the size of the action.
        await db_session.execute(
            text(
                "UPDATE dead_letter_messages SET task_name = NULL WHERE id = :i"
            ),
            {"i": dlq_messages[0]["id"]},
        )
        await db_session.commit()

        resp = await client.post(
            "/api/v1/dlq/bulk-replay",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={},
        )
        body = resp.json()
        assert body["replayed_count"] == len(dlq_messages) - 1
        assert body["skipped_count"] == 1
        assert len(broker.sent) == len(dlq_messages) - 1


# ---------------------------------------------------------------------------
# Site 5 — localisation retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite5LocalisationRetry:

    async def _failed_variant(self, db_session, operator_token):
        from app.core.security import decode_token
        from app.models.language_variant import LanguageVariant
        from app.models.project import Project

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        project = Project(
            id=uuid.uuid4(), name="localise me", state="COMPLETE",
            created_by=owner,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        variant = LanguageVariant(
            id=uuid.uuid4(), project_id=project.id,
            language_code="fr-FR", state="failed",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(variant)
        await db_session.commit()
        return project, variant

    async def test_a_broker_message_is_produced(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        project, variant = await self._failed_variant(db_session, operator_token)
        resp = await client.post(
            f"/api/v1/projects/{project.id}/languages/{variant.id}/retry",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 202, resp.text
        assert len(broker.sent) == 1

    async def test_it_names_a_task_that_is_actually_registered(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        project, variant = await self._failed_variant(db_session, operator_token)
        await client.post(
            f"/api/v1/projects/{project.id}/languages/{variant.id}/retry",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # The stub named "pipeline.localise", which is registered nowhere in
        # ivgs-workers. This one is the orchestrator's real entry point.
        assert broker.sent[0].name == (
            "tasks.pipeline_orchestrator_v2.dispatch_pipeline"
        )

    async def test_the_target_language_travels_with_the_run(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        project, variant = await self._failed_variant(db_session, operator_token)
        await client.post(
            f"/api/v1/projects/{project.id}/languages/{variant.id}/retry",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        ctx = broker.sent[0].kwargs["job_context_dict"]
        assert ctx["language_code"] == "fr-FR"
        # The back half, not the whole pipeline: TTS onward is what a
        # localisation re-run consists of.
        assert ctx["current_stage"] == "tts_audio"

    async def test_the_job_row_records_which_language_it_renders(
        self, client: AsyncClient, operator_token, db_session, broker,
    ):
        # Task 6(c): without this attribution there is no join from a variant to
        # its checkpoints, and per-language progress cannot be derived at all.
        project, variant = await self._failed_variant(db_session, operator_token)
        resp = await client.post(
            f"/api/v1/projects/{project.id}/languages/{variant.id}/retry",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.json()["language_code"] == "fr-FR"


# ---------------------------------------------------------------------------
# Site 6 — quality reject -> regenerate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite6QualityRejectRegenerate:

    async def _flagged_score(self, db_session, scene_asset):
        from app.models.quality_score import AssetQualityScore

        score = AssetQualityScore(
            id=uuid.uuid4(),
            asset_id=uuid.UUID(scene_asset["asset_id"]),
            quality_score=0.41,
            decision="flagged",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(score)
        await db_session.commit()
        return score

    async def test_rejecting_with_regenerate_produces_a_broker_message(
        self, client: AsyncClient, admin_token, db_session, scene_asset, broker,
    ):
        # Admin only, per the route's RBAC contract.
        score = await self._flagged_score(db_session, scene_asset)
        resp = await client.post(
            f"/api/v1/quality/{score.id}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"notes": "the subject is not in frame", "regenerate": True},
        )
        assert resp.status_code == 200, resp.text
        assert len(broker.sent) == 1, (
            "this used to log '(stub - Phase 8)' and dispatch nothing"
        )
        assert resp.json()["regeneration_note"]

    async def test_service_level_reject_dispatches_and_reports_what_happened(
        self, db_session, scene_asset, broker,
    ):
        from app.services.quality_service import QualityService

        score = await self._flagged_score(db_session, scene_asset)
        service = QualityService(db_session)
        result = await service.reject_score(
            score.id, reviewed_by="operator", notes="off-prompt", regenerate=True,
        )

        assert len(broker.sent) == 1, (
            "this used to log '(stub - Phase 8)' and dispatch nothing"
        )
        assert broker.sent[0].name == (
            "tasks.pipeline_orchestrator_v2.dispatch_media_generation"
        )
        # The reviewer is told which of the two things happened, rather than
        # reading "rejected" and assuming both.
        assert result.regeneration_note is not None
        assert "dispatched" in result.regeneration_note

    async def test_regenerate_false_dispatches_nothing(
        self, db_session, scene_asset, broker,
    ):
        from app.services.quality_service import QualityService

        score = await self._flagged_score(db_session, scene_asset)
        result = await QualityService(db_session).reject_score(
            score.id, reviewed_by="operator", notes="n", regenerate=False,
        )
        assert broker.sent == []
        assert result.regeneration_note is None

    async def test_the_rejection_stands_even_when_regeneration_cannot_run(
        self, db_session, scene_project, broker,
    ):
        # A reviewer's verdict is theirs. What must not happen is reporting a
        # regeneration as queued when it was not.
        from app.models.asset import Asset
        from app.models.quality_score import AssetQualityScore
        from app.services.quality_service import QualityService

        orphan = Asset(
            id=uuid.uuid4(),
            project_id=uuid.UUID(scene_project["project_id"]),
            scene_id=None, asset_type="image", storage_tier="hot",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(orphan)
        await db_session.flush()
        score = AssetQualityScore(
            id=uuid.uuid4(), asset_id=orphan.id, decision="flagged",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(score)
        await db_session.commit()

        result = await QualityService(db_session).reject_score(
            score.id, reviewed_by="operator", notes="n", regenerate=True,
        )
        assert result.decision == "rejected"
        assert broker.sent == []
        assert "NOT dispatched" in result.regeneration_note


# ---------------------------------------------------------------------------
# Site 7 — checkpoint resume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite7JobResume:

    async def test_a_broker_message_is_produced(
        self, client: AsyncClient, operator_token, failed_job_with_checkpoints, broker,
    ):
        resp = await client.post(
            f"/api/v1/jobs/{failed_job_with_checkpoints['job_id']}/resume",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code in (200, 202), resp.text
        assert len(broker.sent) == 1

    async def test_it_names_a_task_that_is_actually_registered(
        self, client: AsyncClient, operator_token, failed_job_with_checkpoints, broker,
    ):
        await client.post(
            f"/api/v1/jobs/{failed_job_with_checkpoints['job_id']}/resume",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # The stub named "pipeline.execute_stage", registered nowhere.
        assert broker.sent[0].name == (
            "tasks.pipeline_orchestrator_v2.dispatch_pipeline"
        )

    async def test_the_resume_stage_reaches_the_field_the_orchestrator_reads(
        self, client: AsyncClient, operator_token, failed_job_with_checkpoints, broker,
    ):
        resp = await client.post(
            f"/api/v1/jobs/{failed_job_with_checkpoints['job_id']}/resume",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        ctx = broker.sent[0].kwargs["job_context_dict"]
        # dispatch_pipeline: "if job_context.resume_from_stage: start_stage = ..."
        # That branch has existed the whole time with nothing to feed it.
        assert ctx["resume_from_stage"] == resp.json()["resume_from_stage"]
        assert ctx["job_id"] == resp.json()["new_job_id"]


# ---------------------------------------------------------------------------
# Site 8 — the Prompt Playground
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSite8PromptPlayground:

    PROMPT = "Write one sentence about {{ topic }}."

    async def test_the_model_is_actually_called(
        self, client: AsyncClient, operator_token,
    ):
        captured = {}

        async def fake_completion(prompt, model_id, engine, parameters):
            captured["prompt"] = prompt
            captured["model_id"] = model_id
            return {
                "model_response": "Long division is repeated subtraction.",
                "usage": {"prompt_tokens": 9, "completion_tokens": 7, "total_tokens": 16},
                "engine": engine,
                "endpoint": "http://vllm.test:8000",
                "finish_reason": "stop",
            }

        with patch("app.services.prompt_service.run_completion", fake_completion):
            resp = await client.post(
                "/api/v1/prompts/test",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "prompt_text": self.PROMPT,
                    "model_id": "llama-3.3-70b",
                    "template_variables": {"topic": "long division"},
                },
            )
        assert resp.status_code == 200, resp.text
        # THE ASSERTION: the rendered prompt reached a model call.
        assert captured["prompt"] == "Write one sentence about long division."
        assert captured["model_id"] == "llama-3.3-70b"

    async def test_the_response_is_the_models_and_not_a_placeholder(
        self, client: AsyncClient, operator_token,
    ):
        async def fake_completion(prompt, model_id, engine, parameters):
            return {
                "model_response": "Long division is repeated subtraction.",
                "usage": {"prompt_tokens": 9, "completion_tokens": 7, "total_tokens": 16},
                "engine": engine, "endpoint": "http://vllm.test:8000",
                "finish_reason": "stop",
            }

        with patch("app.services.prompt_service.run_completion", fake_completion):
            resp = await client.post(
                "/api/v1/playground/execute",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"prompt_text": "hello", "model_id": "llama-3.3-70b"},
            )
        body = resp.json()
        assert body["model_response"] == "Long division is repeated subtraction."
        # The exact string the stub used to return, in this exact field.
        assert "[Phase 3 stub]" not in body["model_response"]
        assert "placeholder" not in body["model_response"].lower()
        # Real token counts, not a word count dressed up as usage.
        assert body["usage"]["completion_tokens"] == 7
        assert body["engine"] and body["endpoint"]

    async def test_an_unreachable_model_is_a_502_not_a_plausible_string(
        self, client: AsyncClient, operator_token,
    ):
        from app.services.llm_playground import PlaygroundError

        async def boom(prompt, model_id, engine, parameters):
            raise PlaygroundError("could not reach vllm at http://vllm.test:8000")

        with patch("app.services.prompt_service.run_completion", boom):
            resp = await client.post(
                "/api/v1/prompts/test",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"prompt_text": "hello", "model_id": "llama-3.3-70b"},
            )
        assert resp.status_code == 502
        assert "could not reach" in resp.text

    async def test_a_jinja_error_is_still_a_400_before_any_model_call(
        self, client: AsyncClient, operator_token,
    ):
        called = []

        async def fake_completion(**kwargs):
            called.append(kwargs)
            return {}

        with patch("app.services.prompt_service.run_completion", fake_completion):
            resp = await client.post(
                "/api/v1/prompts/test",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"prompt_text": "{% for x in %}", "model_id": "llama-3.3-70b"},
            )
        assert resp.status_code == 400
        assert called == [], "a syntax error must not cost a GPU call"


# ---------------------------------------------------------------------------
# Resume stage arithmetic — swallow-register entry 17's second half
# ---------------------------------------------------------------------------

class TestResumeComputesTheStageAfter:
    """The stage AFTER the last completed one, in the orchestrator's vocabulary.

    Register entry 17 documented this on 2026-08-23 as latent behind the dead
    resume endpoint: the old list was in the eight SPEC stage names while
    `save_checkpoint` writes the WORKER names the orchestrator dispatches by, so
    three of eight did not match and the fallback resumed from
    `last_checkpoint.stage_name` — the stage that had just completed.

    It fired on the first real resume (job b3df6eb6, 2026-08-25): the last
    complete checkpoint was `image_generation`, which is not in the spec list, so
    the resume re-ran image generation. These pin the arithmetic.
    """

    def test_the_worker_vocabulary_resolves(self):
        from app.services.checkpoint_service import _next_stage_after

        # The three that did NOT match, which is the whole defect.
        assert _next_stage_after("image_generation") == "composition_manifest"
        assert _next_stage_after("composition_manifest") == "tts_audio"
        assert _next_stage_after("tts_audio") == "talking_head_render"

    def test_the_other_two_media_branches_share_the_media_position(self):
        # They run in parallel; a checkpoint from any of them means the same
        # thing about where the pipeline has got to.
        from app.services.checkpoint_service import _next_stage_after

        assert _next_stage_after("video_generation") == "composition_manifest"
        assert _next_stage_after("animation_generation") == "composition_manifest"

    def test_the_spec_vocabulary_still_resolves(self):
        # Rows written before this fix, and any future writer using the spec
        # names, must still resolve rather than falling through.
        from app.services.checkpoint_service import _next_stage_after

        assert _next_stage_after("media_generation") == "composition_manifest"
        assert _next_stage_after("manifest_generation") == "tts_audio"
        assert _next_stage_after("audio_generation") == "talking_head_render"

    def test_the_rest_of_the_chain(self):
        from app.services.checkpoint_service import _next_stage_after

        assert _next_stage_after("transcript_refinement") == "storyboard_generation"
        assert _next_stage_after("storyboard_generation") == "image_generation"
        assert _next_stage_after("talking_head_render") == "prototype_draft"
        assert _next_stage_after("prototype_draft") == "final_render"

    def test_it_never_returns_the_stage_that_just_completed(self):
        # THE DEFECT, stated as an invariant over the whole chain.
        from app.services.checkpoint_service import RESUME_ORDER, _next_stage_after

        for stage in RESUME_ORDER[:-1]:
            assert _next_stage_after(stage) != stage, stage

    def test_the_last_stage_has_nothing_after_it(self):
        from app.services.checkpoint_service import _next_stage_after

        assert _next_stage_after("final_render") == "final_render"

    def test_an_unknown_stage_restarts_rather_than_guessing(self):
        from app.services.checkpoint_service import _next_stage_after

        # Re-running the whole pipeline is wasteful but correct; resuming from a
        # stage whose name nothing understands is a guess.
        assert _next_stage_after("quality_assurance") == "transcript_refinement"

    def test_every_resume_target_is_a_stage_the_orchestrator_can_dispatch(self):
        # The value goes to dispatch_pipeline and is looked up in STAGE_TASK_MAP.
        # A name that is not a PipelineStage value is a dead dispatch.
        from app.services.checkpoint_service import RESUME_ORDER

        pipeline_stage_values = {
            "transcript_refinement", "storyboard_generation", "image_generation",
            "video_generation", "animation_generation", "composition_manifest",
            "tts_audio", "talking_head_render", "prototype_draft", "final_render",
        }
        for stage in RESUME_ORDER:
            assert stage in pipeline_stage_values, stage
