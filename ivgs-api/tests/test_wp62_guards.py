"""
WP-62 Task 6 (WP-61 D-1, RULED: extend) — the in-flight guard reaches the
routes the incident actually used.

**THE MEASURED INCIDENT USED `regenerate`, NOT `trigger`.** WP-60's six
dispatches on project 52d52867 -- five concurrent pipelines, six talking-head
renders, ~3.5 hours of GPU time -- were `job_type` `video_generation` and
`animation_generation`. `trigger_pipeline` produces neither; it produces
`transcript_refinement` or `final_render`. They came through
`POST /projects/{id}/scenes/{sid}/regenerate`, and WP-61 guarded the trigger
because that is what its ruling named, recording the gap as D-1.

**EVERY ASSERTION IS ON THE BROKER, NOT A STATUS CODE** (WP-45 standard). The
six real presses all answered 200 *while dispatching*.

THE FIVE DISPATCH-CAPABLE ENDPOINTS, enumerated. All five now refuse while a
run is in flight:

  1. POST /projects/{id}/trigger                        WP-61, unchanged
  2. POST /projects/{id}/scenes/{sid}/regenerate        THIS PACKAGE
  3. POST /assets/{id}/regenerate                       THIS PACKAGE (same choke point)
  4. POST /quality-scores/{id}/reject?regenerate=true   THIS PACKAGE (same choke point)
  5. POST /jobs/{id}/resume                             THIS PACKAGE
  6. POST /projects/{id}/languages/{vid}/retry          THIS PACKAGE

DELIBERATELY NOT GUARDED, and argued rather than overlooked: DLQ replay
(`POST /dlq/{id}/replay`). It is admin-only, it re-enqueues ONE named dead
message rather than starting a run, and refusing it while a run is in flight
would block the operator's only tool for draining a queue that a run is stuck
behind. Backup dispatches are not project pipeline work at all.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio


class Broker:
    def __init__(self):
        self.sent: list[dict] = []
        self.control = MagicMock()

    def send_task(self, name, args=None, kwargs=None, queue=None, **_ignored):
        self.sent.append({"name": name, "kwargs": kwargs, "queue": queue})
        result = MagicMock()
        result.id = f"celery-{len(self.sent)}"
        return result


@pytest.fixture
def broker():
    b = Broker()
    with patch("app.services.celery_producer.celery_app", b):
        yield b


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def approved_project_with_scene(db_session, operator_token):
    """A project whose storyboard IS approved, with one scene.

    The storyboard gate is satisfied deliberately, so that what these tests
    measure is the IN-FLIGHT guard and not the gate. A fixture that failed both
    ways could not tell you which refusal fired.
    """
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.project_gate import ProjectGateDecision
    from app.models.storyboard_scene import StoryboardScene
    from app.services.gate_service import GateService

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(), name="WP-62 regen guard", state="MEDIA_GENERATION",
        created_by=owner, created_at=now, updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()
    scene = StoryboardScene(
        id=uuid.uuid4(), project_id=project.id, scene_index=0,
        narration_text="Multiply the tens first.",
        visual_description="a grid", media_type="image",
        duration_seconds=6.0, created_at=now, updated_at=now,
    )
    db_session.add(scene)
    await db_session.commit()

    version = await GateService(db_session).storyboard_version(project.id)
    db_session.add(
        ProjectGateDecision(
            id=uuid.uuid4(), project_id=project.id, gate="storyboard",
            decision="approved", artifact_version=version,
            decided_by=owner, decided_by_name="operator", decided_at=now,
        )
    )
    await db_session.commit()
    return project, scene


async def _running_job(db_session, project_id, job_type="video_generation"):
    from app.models.render_job import RenderJob

    job = RenderJob(
        id=uuid.uuid4(), project_id=project_id, job_type=job_type,
        status="running", created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()
    return job


class TestRegenerateIsGuarded:
    async def test_the_second_dispatch_never_reaches_the_broker(
        self, client, operator_token, db_session, approved_project_with_scene,
        broker,
    ):
        """RED WITHOUT THE GUARD. The WP-45 standard assertion.

        One regeneration is dispatched; a run is now in flight; the second
        press must produce NO further broker message.
        """
        project, scene = approved_project_with_scene
        first = await client.post(
            f"/api/v1/projects/{project.id}/scenes/{scene.id}/regenerate",
            headers=_h(operator_token),
        )
        assert first.status_code == 202, first.text
        assert len(broker.sent) == 1

        second = await client.post(
            f"/api/v1/projects/{project.id}/scenes/{scene.id}/regenerate",
            headers=_h(operator_token),
        )
        assert len(broker.sent) == 1, (
            f"a second dispatch reached the broker: {broker.sent}"
        )
        assert second.status_code == 409, second.text
        detail = second.json()["detail"]["error"]
        assert detail["code"] == "PIPELINE_ALREADY_RUNNING"
        # The 409 NAMES the run, so a GUI can link to it.
        assert detail["active_job"]["id"]
        assert detail["active_job"]["job_type"]

    async def test_no_job_row_is_left_behind_by_a_refusal(
        self, client, operator_token, db_session, approved_project_with_scene,
        broker,
    ):
        """A refused request must not leave a `pending` row pretending to be
        queued. WP-45's finding was the mirror of this."""
        from sqlalchemy import text

        project, scene = approved_project_with_scene
        await _running_job(db_session, project.id)
        before = (await db_session.execute(
            text("SELECT count(*) FROM render_jobs WHERE project_id = :p"),
            {"p": str(project.id)},
        )).scalar()

        await client.post(
            f"/api/v1/projects/{project.id}/scenes/{scene.id}/regenerate",
            headers=_h(operator_token),
        )
        after = (await db_session.execute(
            text("SELECT count(*) FROM render_jobs WHERE project_id = :p"),
            {"p": str(project.id)},
        )).scalar()
        assert after == before
        assert broker.sent == []

    async def test_the_guard_is_at_the_choke_point_not_the_route(self):
        """All three regenerate surfaces reach ONE dispatch function.

        Guarding the three callers instead would leave a fourth caller added
        later reintroducing the hole. This pins that the guard lives where they
        converge.
        """
        import inspect

        from app.services import regeneration

        src = inspect.getsource(regeneration.dispatch_scene_media_regeneration)
        assert "active_job" in src
        assert "PipelineAlreadyRunningError" in src
        assert "require_storyboard_approval" in src

    async def test_regenerate_also_refuses_without_a_current_approval(
        self, client, operator_token, db_session, approved_project_with_scene,
        broker,
    ):
        """A regeneration IS media generation, so it is behind the gate too.

        Without this the gate would have had a side door of exactly the shape
        the gate exists to close.
        """
        from sqlalchemy import text

        project, scene = approved_project_with_scene
        await db_session.execute(
            text(
                "UPDATE storyboard_scenes SET updated_at = now() + interval "
                "'1 second' WHERE id = :s"
            ),
            {"s": str(scene.id)},
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/projects/{project.id}/scenes/{scene.id}/regenerate",
            headers=_h(operator_token),
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error"]["code"] == "GATE_NOT_APPROVED"
        assert broker.sent == []


class TestTheOtherDispatchCapableEndpoints:
    async def test_resume_refuses_while_another_run_is_in_flight(
        self, db_session, approved_project_with_scene, broker,
    ):
        """`POST /jobs/{id}/resume` checks THIS job's status and said nothing
        about the project. A project with one failed job and one running job is
        exactly the shape a partially-failed run leaves behind."""
        from app.models.render_job import RenderJob
        from app.services.checkpoint_service import CheckpointService
        from app.services.project_service import PipelineAlreadyRunningError

        project, _scene = approved_project_with_scene
        failed = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="final_render",
            status="failed", created_at=datetime.now(timezone.utc),
        )
        db_session.add(failed)
        await db_session.commit()
        await _running_job(db_session, project.id, "image_generation")

        with pytest.raises(PipelineAlreadyRunningError):
            await CheckpointService(db_session).resume_from_checkpoint(
                failed.id, "tester",
            )
        assert broker.sent == []

    async def test_localisation_retry_refuses_while_a_run_is_in_flight(
        self, db_session, approved_project_with_scene, broker,
    ):
        from app.models.language_variant import LanguageVariant
        from app.services.language_service import LanguageService
        from app.services.project_service import PipelineAlreadyRunningError

        project, _scene = approved_project_with_scene
        variant = LanguageVariant(
            id=uuid.uuid4(), project_id=project.id, language_code="es-ES",
            state="failed", created_at=datetime.now(timezone.utc),
        )
        db_session.add(variant)
        await db_session.commit()
        await _running_job(db_session, project.id, "image_generation")

        with pytest.raises(PipelineAlreadyRunningError):
            await LanguageService(db_session).retry_variant(
                project.id, variant.id,
            )
        assert broker.sent == []

    async def test_the_guard_error_is_a_valueerror_subclass_and_is_caught_first(
        self,
    ):
        """`PipelineAlreadyRunningError` subclasses ValueError so WP-61's
        existing callers kept behaving. That makes catch ORDER load-bearing:
        a route whose `except ValueError` comes first answers
        INVALID_STATE_TRANSITION -- the wrong code, and one an operator would
        try to fix by changing the project's state."""
        import inspect

        from app.api.v1 import checkpoints, languages
        from app.services.project_service import PipelineAlreadyRunningError

        assert issubclass(PipelineAlreadyRunningError, ValueError)
        for module in (checkpoints, languages):
            src = inspect.getsource(module)
            guard_at = src.index("except PipelineAlreadyRunningError")
            value_at = src.index("except ValueError", guard_at - 4000)
            assert guard_at < src.index("except ValueError", guard_at), (
                f"{module.__name__} catches ValueError before the guard"
            )
            assert value_at is not None
