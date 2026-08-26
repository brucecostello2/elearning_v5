"""WP-66 Task 5 — a model selection change invalidates the DRAFT gate only.

THE RULING, and the reasoning it carries, because the asymmetry is the point:

The storyboard artifact is narration, visual descriptions and media types. A
model choice does not alter any of them, and invalidating the storyboard
approval would refuse the very regeneration the user is picking a model FOR --
the same asymmetry WP-63 D-1 resolved for regeneration. The draft, by contrast,
IS what the models produced: approving a draft and then changing the model that
made it must re-open that decision.

HOW IT IS IMPLEMENTED, and why the implementation is the proof. Not by a new
invalidation path -- by composition. ``draft_upstream_version`` already read
``storyboard_version + scene_media_version``; it now also reads
``model_selection_version``. ``storyboard_version`` is UNTOUCHED, so a
storyboard approval CANNOT be affected by a selection change -- not "is not",
cannot be, because the selection rows are not among its inputs. And nothing
writes an invalidation: the fingerprint moves and the approval stops being
current on the next read, which is how every other gate in this module already
behaves (``gate_service.py:37-41``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.models.project_gate import GATE_DRAFT, GATE_STORYBOARD
from app.services import model_selection as planner
from app.services.gate_service import GateService
from shared.models.model_store import (
    Model,
    ModelEngine,
    ModelStage,
    ModelState,
    ModelTier,
)

_FETCHABLE = "https://serving.mbcp.internal/weights/{}/manifest?tier=certified"


class TestSelectionInvalidatesTheDraftGateOnly:
    async def _approved_both(self, db_session, operator_token):
        """A project with BOTH gates approved, so each can be checked after.

        The gate state is created programmatically on a project this test owns.
        No gate is pressed through the UI: WP-63 D-2 stands and the human half
        of a review gate is the operator's.
        """
        from app.core.security import decode_token
        from app.models.checkpoint import PipelineCheckpoint
        from app.models.project import Project
        from app.models.render_job import RenderJob
        from app.models.storyboard_scene import StoryboardScene
        from app.models.user import User
        from sqlalchemy import select as sa_select

        owner_id = uuid.UUID(decode_token(operator_token)["sub"])
        owner = (
            await db_session.execute(sa_select(User).where(User.id == owner_id))
        ).scalar_one()
        now = datetime.now(timezone.utc)

        project = Project(
            id=uuid.uuid4(), name="WP-66 invalidation", state="USER_REVIEW",
            created_by=owner_id, created_at=now, updated_at=now,
        )
        db_session.add(project)
        await db_session.flush()

        scene = StoryboardScene(
            id=uuid.uuid4(), project_id=project.id, scene_index=1,
            narration_text="n", visual_description="a ruled line with one row",
            media_type="image", duration_seconds=10.0,
            created_at=now, updated_at=now,
        )
        db_session.add(scene)
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id,
            job_type="transcript_refinement", status="success",
            created_at=now, completed_at=now,
        )
        db_session.add(job)
        await db_session.flush()
        db_session.add(
            PipelineCheckpoint(
                id=uuid.uuid4(), job_id=job.id, stage_name="prototype_draft",
                stage_index=7, status="complete", created_at=now,
            )
        )
        await db_session.commit()

        svc = GateService(db_session)
        await svc.decide(project.id, GATE_STORYBOARD, "approved", actor=owner)
        await svc.decide(project.id, GATE_DRAFT, "approved", actor=owner)
        await db_session.commit()

        for gate in (GATE_STORYBOARD, GATE_DRAFT):
            assert (await svc.status(project.id, gate)).approved, gate
        return {"project_id": project.id, "owner": owner, "scene_id": scene.id}

    async def _select(self, db_session, project_id, model_id, scene_id=None):
        await planner.manual_override(
            db_session, project_id=project_id, scene_id=scene_id,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=model_id, rationale="operator selection",
        )
        await db_session.commit()

    async def _model(self, db_session, name):
        row = Model(
            id=uuid.uuid4(), name=name, display_name=name,
            stage=ModelStage.IMAGE_GENERATION, engine=ModelEngine.COMFYUI,
            tier=ModelTier.BOTH, state=ModelState.APPROVED,
            weights_ref=_FETCHABLE.format(uuid.uuid4()),
        )
        db_session.add(row)
        await db_session.flush()
        return row

    async def test_a_project_selection_invalidates_the_held_draft_approval(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        pid = approved_both["project_id"]
        m = await self._model(db_session, "wp66-inv-1")
        await self._select(db_session, pid, m.id)

        status = await GateService(db_session).status(pid, GATE_DRAFT)
        assert not status.approved
        assert status.open
        assert "upstream" in (status.reason or "").lower() or "no longer" in (
            status.reason or ""
        ).lower(), status.reason

    async def test_the_same_change_leaves_the_storyboard_approval_standing(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """The other half, and the one that matters more: invalidating this
        would refuse the regeneration the user is selecting a model for."""
        pid = approved_both["project_id"]
        m = await self._model(db_session, "wp66-inv-2")
        await self._select(db_session, pid, m.id)

        status = await GateService(db_session).status(pid, GATE_STORYBOARD)
        assert status.approved, status.reason

    async def test_a_scene_scoped_override_also_invalidates_the_draft(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """Overriding one scene's model changes what the next draft contains
        just as surely as changing the project's, so the fingerprint covers
        scene_id."""
        pid = approved_both["project_id"]
        m = await self._model(db_session, "wp66-inv-3")
        await self._select(db_session, pid, m.id, scene_id=approved_both["scene_id"])

        svc = GateService(db_session)
        assert not (await svc.status(pid, GATE_DRAFT)).approved
        assert (await svc.status(pid, GATE_STORYBOARD)).approved

    async def test_the_storyboard_fingerprint_does_not_read_selections_at_all(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """Not "does not change" -- CANNOT change. The proof is the input set,
        not an observation, because an observation could be a coincidence."""
        import inspect

        src = inspect.getsource(GateService.storyboard_version)
        assert "ProjectModelSelection" not in src
        assert "StoryboardScene" in src

    async def test_the_draft_upstream_fingerprint_reads_all_three_inputs(
        self, db_session
    ):
        import inspect

        src = inspect.getsource(GateService.draft_upstream_version)
        for part in (
            "storyboard_version", "scene_media_version", "model_selection_version",
        ):
            assert part in src

    async def test_re_approving_after_the_change_makes_it_current_again(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """The invalidation must be recoverable, or it is a trap rather than a
        gate."""
        pid = approved_both["project_id"]
        owner = approved_both["owner"]
        m = await self._model(db_session, "wp66-inv-4")
        await self._select(db_session, pid, m.id)

        svc = GateService(db_session)
        assert not (await svc.status(pid, GATE_DRAFT)).approved
        await svc.decide(pid, GATE_DRAFT, "approved", actor=owner)
        await db_session.commit()
        assert (await svc.status(pid, GATE_DRAFT)).approved

    async def test_selecting_the_same_model_twice_does_not_re_invalidate(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """The fingerprint is over (scene, stage, tier, model) -- not over the
        rationale or created_at. Re-selecting the same model with different
        prose is not a different draft, and re-approving over it would be
        noise."""
        pid = approved_both["project_id"]
        owner = approved_both["owner"]
        m = await self._model(db_session, "wp66-inv-5")
        await self._select(db_session, pid, m.id)

        svc = GateService(db_session)
        await svc.decide(pid, GATE_DRAFT, "approved", actor=owner)
        await db_session.commit()
        assert (await svc.status(pid, GATE_DRAFT)).approved

        await planner.manual_override(
            db_session, project_id=pid, scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=m.id, rationale="a completely different explanation",
        )
        await db_session.commit()
        assert (await svc.status(pid, GATE_DRAFT)).approved

    async def test_a_project_with_no_selections_has_a_stable_version(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """"No explicit selections" is a real, stable binding on is_default
        models -- not an absence, and it must not read as ABSENT."""
        pid = approved_both["project_id"]
        svc = GateService(db_session)
        assert await svc.model_selection_version(pid) == "sel-0"
        assert (await svc.status(pid, GATE_DRAFT)).approved

    async def test_clearing_a_scene_override_also_moves_the_fingerprint(
        self, db_session, operator_token
    ):
        approved_both = await self._approved_both(db_session, operator_token)
        """Removing an override changes what the next draft contains exactly as
        much as adding one did."""
        pid = approved_both["project_id"]
        owner = approved_both["owner"]
        m = await self._model(db_session, "wp66-inv-6")
        await self._select(db_session, pid, m.id, scene_id=approved_both["scene_id"])

        svc = GateService(db_session)
        await svc.decide(pid, GATE_DRAFT, "approved", actor=owner)
        await db_session.commit()
        assert (await svc.status(pid, GATE_DRAFT)).approved

        await planner.clear_selection(
            db_session, project_id=pid, scene_id=approved_both["scene_id"],
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        await db_session.commit()
        assert not (await svc.status(pid, GATE_DRAFT)).approved
        assert (await svc.status(pid, GATE_STORYBOARD)).approved


class TestTheReasonNamesEveryCause:
    """A reason that lists the wrong causes sends the reader to the wrong
    place, which is worse than a vague one.

    `draft_upstream_version` gained a third input in WP-66 and the sentence
    shown to the operator still named two -- caught by reading the live
    acceptance output, not by a test, which is why this one now exists.
    """

    async def test_the_stale_upstream_reason_mentions_model_selection(self):
        import inspect

        from app.services.gate_service import GateService

        src = inspect.getsource(GateService.status)
        assert "model selection has changed" in src

    async def test_it_still_mentions_the_other_two(self):
        import inspect

        from app.services.gate_service import GateService

        src = inspect.getsource(GateService.status)
        assert "storyboard has been re-run" in src
        # The sentence wraps across source lines, so match the words that
        # survive wrapping rather than a phrase that happens to sit on one.
        assert "regenerated" in src
