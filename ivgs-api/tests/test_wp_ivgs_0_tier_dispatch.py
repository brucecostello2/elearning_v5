"""
WP-IVGS-0.3 — tier must be dispatched, not assumed.

Neither dispatch payload set ``tier``, so PipelineJobContext defaulted to
"prototype" and production was unreachable. Tier belongs to the RUN, not the
project, so it is a dispatch parameter defaulting to prototype.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text

from app.services.project_service import ProjectService
from app.services.user_service import create_user
from app.schemas.project import ProjectCreate

from tests.test_wp_ivgs_0_dispatch_context import recorder  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _make_user(db_session, username, role="operator"):
    return await create_user(db_session, username, "Str0ngP@ss1", role)


async def _triggerable(db_session, user, name):
    from app.models.transcript import Transcript

    svc = ProjectService(db_session)
    resp = await svc.create_project(ProjectCreate(name=name), user)
    db_session.add(
        Transcript(
            id=uuid4(),
            project_id=resp.id,
            sequence_order=0,
            refined_text="text",
            language_code="en-US",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    return svc, resp


class TestTierDispatch:
    async def test_production_tier_reaches_the_payload(self, db_session, recorder):
        user = await _make_user(db_session, "wp0_tier_prod")
        svc, proj = await _triggerable(db_session, user, "Tier Prod")

        await svc.trigger_pipeline(proj.id, user, tier="production")

        ctx = recorder.calls[0]["kwargs"]["job_context_dict"]
        assert ctx["tier"] == "production"

    async def test_default_is_prototype(self, db_session, recorder):
        user = await _make_user(db_session, "wp0_tier_default")
        svc, proj = await _triggerable(db_session, user, "Tier Default")

        await svc.trigger_pipeline(proj.id, user)

        ctx = recorder.calls[0]["kwargs"]["job_context_dict"]
        assert ctx["tier"] == "prototype"

    async def test_an_unknown_tier_is_refused_not_coerced(self, db_session, recorder):
        user = await _make_user(db_session, "wp0_tier_bad")
        svc, proj = await _triggerable(db_session, user, "Tier Bad")

        with pytest.raises(ValueError, match="Invalid render tier"):
            await svc.trigger_pipeline(proj.id, user, tier="staging")
        assert recorder.calls == []

    async def test_storyboard_approval_carries_the_tier(self, db_session, recorder):
        from app.models.render_job import RenderJob
        from app.models.storyboard_scene import StoryboardScene

        user = await _make_user(db_session, "wp0_tier_resume")
        svc = ProjectService(db_session)
        proj = await svc.create_project(ProjectCreate(name="Tier Resume"), user)
        db_session.add(
            RenderJob(
                id=uuid4(), project_id=proj.id,
                job_type="storyboard_generation", status="success",
                created_at=datetime.now(timezone.utc),
            )
        )
        db_session.add(
            StoryboardScene(
                id=uuid4(), project_id=proj.id, scene_index=0,
                narration_text="n", visual_description="v", media_type="image",
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

        await svc.approve_storyboard(proj.id, user, tier="production")

        payload = recorder.calls[0]["kwargs"]["dispatch_input"]
        assert payload["tier"] == "production"
