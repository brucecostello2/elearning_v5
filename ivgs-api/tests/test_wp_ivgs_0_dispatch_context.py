"""
WP-IVGS-0.1 / 0.3 — the dispatch payload must carry the user's project facts.

Defect: the dispatch payloads omitted ``max_runtime_seconds`` (and, on the
storyboard-approval path, ``description`` and ``priority``), so
``PipelineJobContext`` fell back to its 600-second default and every Stage 1/2
prompt told the model "600 seconds" no matter what the user asked for.
``tier`` was never sent at all, so ``get_binding`` always resolved prototype.

These tests assert on the payload actually handed to ``send_task``.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text

from app.services.project_service import ProjectService
from app.services.user_service import create_user
from app.schemas.project import ProjectCreate

pytestmark = pytest.mark.asyncio


async def _make_user(db_session, username, role="operator"):
    return await create_user(db_session, username, "Str0ngP@ss1", role)


class _Recorder:
    """Stands in for the Celery app: records send_task instead of dispatching."""

    def __init__(self):
        self.calls = []

    def send_task(self, name, kwargs=None, queue=None, **extra):
        self.calls.append({"name": name, "kwargs": kwargs or {}, "queue": queue})

        class _R:
            id = "test-task-id"

        return _R()


@pytest.fixture
def recorder(monkeypatch):
    """Patch the celery app the service imports at dispatch time."""
    rec = _Recorder()
    import app.services.celery_producer as cp

    monkeypatch.setattr(cp, "celery_app", rec)
    return rec


async def _project_with_transcript(db_session, user, **create_kwargs):
    """Create a project plus one transcript so trigger_pipeline is allowed."""
    from app.models.transcript import Transcript

    svc = ProjectService(db_session)
    resp = await svc.create_project(ProjectCreate(**create_kwargs), user)
    db_session.add(
        Transcript(
            id=uuid4(),
            project_id=resp.id,
            sequence_order=0,
            refined_text="Some source narration text.",
            language_code="en-US",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    return svc, resp


class TestPipelineStartDispatch:
    async def test_runtime_and_description_reach_the_payload(
        self, db_session, recorder
    ):
        user = await _make_user(db_session, "wp0_start_ok")
        svc, proj = await _project_with_transcript(
            db_session,
            user,
            name="Runtime Project",
            description="A course on reactor safety interlocks.",
            max_runtime_seconds=1800,
        )

        await svc.trigger_pipeline(proj.id, user)

        assert len(recorder.calls) == 1
        ctx = recorder.calls[0]["kwargs"]["job_context_dict"]
        assert ctx["max_runtime_seconds"] == 1800
        assert ctx["project_description"] == (
            "A course on reactor safety interlocks."
        )
        assert ctx["project_name"] == "Runtime Project"

    async def test_negative_control_no_runtime_means_no_key(
        self, db_session, recorder
    ):
        """The 600 default must come from PipelineJobContext, not the API.

        A project with no runtime set sends no key at all, so the default is
        visible in exactly one place instead of being silently baked in here.
        """
        user = await _make_user(db_session, "wp0_start_none")
        svc, proj = await _project_with_transcript(
            db_session, user, name="No Runtime Project"
        )

        await svc.trigger_pipeline(proj.id, user)

        ctx = recorder.calls[0]["kwargs"]["job_context_dict"]
        assert "max_runtime_seconds" not in ctx


class TestMediaResumeDispatch:
    async def test_storyboard_approval_carries_the_same_facts(
        self, db_session, recorder
    ):
        user = await _make_user(db_session, "wp0_resume_ok")
        svc = ProjectService(db_session)
        proj = await svc.create_project(
            ProjectCreate(
                name="Resume Project",
                description="Second-half project facts.",
                max_runtime_seconds=1800,
            ),
            user,
        )
        # A render job and one persisted scene are the approval preconditions.
        from app.models.render_job import RenderJob
        from app.models.storyboard_scene import StoryboardScene

        db_session.add(
            RenderJob(
                id=uuid4(),
                project_id=proj.id,
                job_type="storyboard_generation",
                status="success",
                created_at=datetime.now(timezone.utc),
            )
        )
        db_session.add(
            StoryboardScene(
                id=uuid4(),
                project_id=proj.id,
                scene_index=0,
                narration_text="narration",
                visual_description="visual",
                media_type="image",
                duration_seconds=10,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db_session.execute(
            text("UPDATE projects SET state = 'STORYBOARD_GENERATION' WHERE id = :pid"),
            {"pid": proj.id},
        )
        await db_session.commit()

        # WP-62 Task 2(c). `approve_storyboard` is the RELEASE half now; the
        # decision is recorded first (by the gate route, or here by the shared
        # helper) and the release refuses without a current one. Before this
        # package the method WAS the gate, which is why nothing could ask
        # whether an approval existed and nothing refused for want of one.
        from tests.conftest import record_storyboard_approval

        await record_storyboard_approval(db_session, proj.id, user.id)

        await svc.approve_storyboard(proj.id, user)

        assert len(recorder.calls) == 1
        payload = recorder.calls[0]["kwargs"]["dispatch_input"]
        assert payload["max_runtime_seconds"] == 1800
        assert payload["project_description"] == "Second-half project facts."
        assert payload["project_name"] == "Resume Project"
