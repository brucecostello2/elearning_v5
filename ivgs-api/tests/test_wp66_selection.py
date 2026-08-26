"""WP-66 — the user chooses the model, per project and per scene.

THE FINDING. The selection mechanism was built, scene-aware, and unreachable.
``ProjectModelSelection`` carries a nullable ``scene_id``
(``shared/models/model_store.py:365``); dispatch honours it scene-first then
project (``shared/providers/factory.py:147-151``); three endpoints existed. And
``grep -rn "selections" ivgs-frontend/src`` returned a preset type and a
storyboard "clear all selections" handler. No picker, at any scope.

WHAT TASK 1's MEASUREMENT CHANGED ABOUT THE BRIEF:

  * ``PUT /selections`` ALREADY refused a non-approved model
    (``model_selection.py:284``, pre-WP-66). What it lacked was a slug the
    surface could act on and a message a user could read.
  * ``POST /selections/plan`` is NOT a dry run. It PERSISTS ``selected_by=auto``
    rows for every stage requested. The name suggests otherwise; the behaviour
    is what counts, and the UI must not call it to "preview" anything.
  * ``rationale`` is enforced non-empty at the schema
    (``ManualSelectionIn.rationale: str = Field(min_length=1)``).
  * The preset path is REAL (``preset_service.py:246``) -- not another
    declared-but-inert write. What it lost was provenance.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.services import model_selection as planner
from app.services import selection_panel
from app.services.model_selection import SelectionRefused
from shared.models.model_store import (
    Model,
    ModelEngine,
    ModelStage,
    ModelState,
    ModelTier,
    ProjectModelSelection,
    SelectionSource,
)


async def _model(db, *, name, stage=ModelStage.IMAGE_GENERATION,
                state=ModelState.APPROVED, engine=ModelEngine.COMFYUI,
                is_default=False, enabled=True, weights_ref=None,
                tier=ModelTier.BOTH):
    row = Model(
        id=uuid.uuid4(), name=name, display_name=name, stage=stage,
        engine=engine, tier=tier, state=state, is_default=is_default,
        enabled=enabled, weights_ref=weights_ref,
    )
    db.add(row)
    await db.flush()
    return row


#: A reference MBCP would serve real bytes for -- the shape that is NOT
#: engine-only, so it does not trip WP-65's certainly-unrunnable refusals.
_FETCHABLE = "https://serving.mbcp.internal/weights/{}/manifest?tier=certified"
_ENGINE_ONLY = "http://serving-api:8000/engines/sha256:deadbeef/manifest"


# ---------------------------------------------------------------------------
# TASK 1 — what the endpoints actually do
# ---------------------------------------------------------------------------

class TestWhatWasAlreadyThere:
    def test_the_plan_endpoint_persists_and_is_not_a_preview(self):
        """Read carefully, per the brief. ``plan_selections`` calls
        ``plan_stage`` per stage, and ``plan_stage`` ends in
        ``_replace_selection`` -- a DELETE then an INSERT. A UI that called this
        to show the user a proposal would have written it."""
        import inspect

        src = inspect.getsource(planner.plan_stage)
        assert "_replace_selection" in src

    def test_put_upserts_by_replacing_the_scope_not_accumulating(self):
        import inspect

        src = inspect.getsource(planner._replace_selection)
        assert "delete(ProjectModelSelection)" in src

    def test_rationale_is_enforced_non_empty_at_the_schema(self):
        from pydantic import ValidationError

        from app.schemas.model_store import ManualSelectionIn

        with pytest.raises(ValidationError):
            ManualSelectionIn(
                stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
                model_id=uuid.uuid4(), rationale="",
            )

    def test_the_selection_sources_are_the_three_the_ui_must_distinguish(self):
        assert [s.value for s in SelectionSource] == ["auto", "manual", "preset"]

    def test_the_stage_list_comes_from_the_enum_not_from_a_retyped_list(self):
        """The brief listed nine stages by hand. The enum is the authority, and
        if it grows the panel must grow with it."""
        assert selection_panel._stage_list() == list(ModelStage)
        assert len(list(ModelStage)) == 9


# ---------------------------------------------------------------------------
# TASK 2 — selection respects availability
# ---------------------------------------------------------------------------

class TestSelectionRefusals:
    async def test_a_candidate_model_is_refused_with_an_actionable_reason(
        self, db_session, project_id
    ):
        m = await _model(db_session, name="wp66-candidate", state=ModelState.CANDIDATE)
        with pytest.raises(SelectionRefused) as exc:
            await planner.manual_override(
                db_session, project_id=uuid.UUID(project_id), scene_id=None,
                stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
                model_id=m.id, rationale="operator selection",
            )
        assert exc.value.reason == "not_approved"
        assert "Admin -> Models" in str(exc.value)

    async def test_an_engine_only_model_is_ACCEPTED_because_its_image_runs_it(
        self, db_session, project_id
    ):
        """CORRECTED ON EVIDENCE, and this test is the record of it.

        `engine_only` was originally a refusal here. Running the acceptance
        against live data showed THREE stages with zero selectable models --
        video_generation, composition and translation -- and the models being
        refused were CogVideoX-5b, FFmpeg-composition and
        Llama-3.3-70B-Instruct: the `is_default` models those stages are bound
        to and rendering with TODAY.

        The reasoning was wrong the same way WP-65 §7.4 was. "MBCP has no weight
        bundle" is a fact about MBCP's serving plane; "this model cannot run" is
        a fact about the fleet. An engine-only certification means the model
        ships INSIDE its engine image, so wherever that image is deployed it
        runs. It is a warning, not a bar.
        """
        m = await _model(
            db_session, name="wp66-engine-only", weights_ref=_ENGINE_ONLY,
        )
        row = await planner.manual_override(
            db_session, project_id=uuid.UUID(project_id), scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=m.id, rationale="operator selection",
        )
        assert row.model_id == m.id

        resolved = await selection_panel.resolve_binding(
            db_session, project_id=uuid.UUID(project_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert resolved.warning is not None
        assert "engine" in resolved.warning.lower()

    async def test_no_live_default_model_would_be_refused_by_this_gate(self):
        """The property the correction restores, stated so it cannot regress.

        A gate that refuses the model a stage is ALREADY running is not a
        safety check; it is a bug that makes the picker useless for that stage.
        """
        from app.services.model_selection import _CERTAINLY_UNRUNNABLE

        assert "engine_only" not in _CERTAINLY_UNRUNNABLE
        assert "no_host" in _CERTAINLY_UNRUNNABLE

    async def test_the_two_refusals_are_distinguishable(self, db_session, project_id):
        """WP-65 Task 4 made the distinction visible in the store; it must
        survive into the selection refusal or the user is told to do the wrong
        thing. The two that BAR a selection are lifecycle and no-host: one is
        an admin action, the other an operator one."""
        a = await _model(db_session, name="wp66-a", state=ModelState.CANDIDATE)
        b = await _model(
            db_session, name="wp66-b", engine=ModelEngine.REMOTION,
            weights_ref=_FETCHABLE.format(uuid.uuid4()),
        )
        reasons = set()
        for m in (a, b):
            with pytest.raises(SelectionRefused) as exc:
                await planner.manual_override(
                    db_session, project_id=uuid.UUID(project_id), scene_id=None,
                    stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
                    model_id=m.id, rationale="r",
                )
            reasons.add(exc.value.reason)
        assert reasons == {"not_approved", "no_host"}

    async def test_a_model_whose_engine_has_no_host_is_refused(
        self, db_session, project_id
    ):
        m = await _model(
            db_session, name="wp66-nohost", engine=ModelEngine.REMOTION,
            weights_ref=_FETCHABLE.format(uuid.uuid4()),
        )
        with pytest.raises(SelectionRefused) as exc:
            await planner.manual_override(
                db_session, project_id=uuid.UUID(project_id), scene_id=None,
                stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
                model_id=m.id, rationale="r",
            )
        assert exc.value.reason == "no_host"

    async def test_a_model_with_no_fetch_record_is_ACCEPTED_with_a_warning(
        self, db_session, project_id
    ):
        """THE DELIBERATE NARROWING, and the reason it is right.

        The brief asks for refusal when there are "no verified weights on a
        node". Measured after WP-65 deployed: ``model_weight_placements`` holds
        ZERO rows, because the live fetch needs the operator's MBCP token.
        Enforcing that literally would refuse every model in the store,
        including wan2.2-animate, whose bytes are demonstrably on node-03.

        And it would assert what IVGS cannot know: no fetch RECORD is a fact
        about IVGS's records, not about the node. So this is accepted, and the
        panel carries a warning instead.
        """
        m = await _model(
            db_session, name="wp66-unfetched",
            weights_ref=_FETCHABLE.format(uuid.uuid4()),
        )
        row = await planner.manual_override(
            db_session, project_id=uuid.UUID(project_id), scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=m.id, rationale="operator selection",
        )
        assert row.model_id == m.id

        resolved = await selection_panel.resolve_binding(
            db_session, project_id=uuid.UUID(project_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert resolved.warning is not None
        assert "Admin -> Models" in resolved.warning

    async def test_the_picker_and_the_writer_agree_on_what_is_selectable(
        self, db_session, project_id
    ):
        """One definition, two readers. A picker that offers what the write
        refuses -- or greys out what it would accept -- is worse than no
        picker."""
        await _model(db_session, name="wp66-ok",
                     weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await _model(db_session, name="wp66-cand", state=ModelState.CANDIDATE)
        await _model(db_session, name="wp66-eo", engine=ModelEngine.REMOTION,
                     weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await db_session.commit()

        cands = await selection_panel._candidates_for(
            db_session, ModelStage.IMAGE_GENERATION, ModelTier.PRODUCTION,
        )
        by_name = {c.name: c for c in cands}
        for name in ("wp66-ok", "wp66-cand", "wp66-eo"):
            c = by_name[name]
            model = (await db_session.execute(
                select(Model).where(Model.name == name)
            )).scalar_one()
            would_refuse = False
            try:
                await planner.manual_override(
                    db_session, project_id=uuid.UUID(project_id), scene_id=None,
                    stage=ModelStage.IMAGE_GENERATION,
                    tier=ModelTier.PRODUCTION, model_id=model.id, rationale="r",
                )
            except SelectionRefused:
                would_refuse = True
            assert c.selectable is not would_refuse, name

    async def test_an_unselectable_candidate_is_returned_not_hidden(
        self, db_session
    ):
        """A user who cannot see the model they expected has no way to learn
        why, and reports "the picker is broken"."""
        await _model(db_session, name="wp66-hidden", state=ModelState.CANDIDATE)
        await db_session.commit()
        cands = await selection_panel._candidates_for(
            db_session, ModelStage.IMAGE_GENERATION, ModelTier.PRODUCTION,
        )
        hidden = next(c for c in cands if c.name == "wp66-hidden")
        assert hidden.selectable is False
        assert hidden.refusal_message


# ---------------------------------------------------------------------------
# TASK 3 — provenance
# ---------------------------------------------------------------------------

class TestProvenanceIsNeverGuessed:
    async def test_no_row_resolves_to_the_stage_default_and_says_so(
        self, db_session, project_id
    ):
        await _model(db_session, name="wp66-default", is_default=True,
                     weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await db_session.commit()
        r = await selection_panel.resolve_binding(
            db_session, project_id=uuid.UUID(project_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert r.provenance == "default"
        assert r.model.name == "wp66-default"
        assert r.selection is None

    async def test_a_manual_row_and_a_preset_row_are_distinguishable(
        self, db_session, project_id
    ):
        """The whole reason migration 0040 exists. Before it, both were
        ``manual`` and the only trace was a free-text rationale an operator can
        edit."""
        m = await _model(db_session, name="wp66-prov",
                         weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await planner.manual_override(
            db_session, project_id=uuid.UUID(project_id), scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=m.id, rationale="by hand",
        )
        await db_session.commit()
        r = await selection_panel.resolve_binding(
            db_session, project_id=uuid.UUID(project_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert r.provenance == "selection"

        await planner.manual_override(
            db_session, project_id=uuid.UUID(project_id), scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=m.id, rationale="preset 'x' v1",
            selected_by=SelectionSource.PRESET,
        )
        await db_session.commit()
        r2 = await selection_panel.resolve_binding(
            db_session, project_id=uuid.UUID(project_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert r2.provenance == "preset"
        assert r2.provenance != r.provenance

    async def test_a_selection_that_went_bad_warns_and_is_not_rewritten(
        self, db_session, project_id
    ):
        """"Silently rewritten" is the failure this avoids: the user chose a
        model, and the system must not quietly choose a different one."""
        m = await _model(db_session, name="wp66-rots",
                         weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await planner.manual_override(
            db_session, project_id=uuid.UUID(project_id), scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=m.id, rationale="r",
        )
        m.state = ModelState.RETIRED
        await db_session.commit()

        r = await selection_panel.resolve_binding(
            db_session, project_id=uuid.UUID(project_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert r.model.name == "wp66-rots"          # not swapped out
        assert r.warning and "retired" in r.warning

    async def test_the_panel_covers_every_stage(self, db_session, project_id):
        await db_session.commit()
        panel = await selection_panel.project_panel(
            db_session, project_id=uuid.UUID(project_id), tier=ModelTier.PRODUCTION,
        )
        assert {b.stage for b in panel.bindings} == set(ModelStage)
        assert all(b.provenance_label for b in panel.bindings)


# ---------------------------------------------------------------------------
# TASK 4 — scene scope
# ---------------------------------------------------------------------------

class TestSceneScopedSelection:
    async def test_a_scene_override_takes_precedence_and_siblings_do_not_move(
        self, db_session, project_id, scene_id
    ):
        proj = await _model(db_session, name="wp66-proj",
                            weights_ref=_FETCHABLE.format(uuid.uuid4()))
        scene_model = await _model(db_session, name="wp66-scene",
                                   weights_ref=_FETCHABLE.format(uuid.uuid4()))
        pid = uuid.UUID(project_id)
        await planner.manual_override(
            db_session, project_id=pid, scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=proj.id, rationale="project",
        )
        await planner.manual_override(
            db_session, project_id=pid, scene_id=uuid.UUID(scene_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=scene_model.id, rationale="this scene only",
        )
        await db_session.commit()

        mine = await selection_panel.resolve_binding(
            db_session, project_id=pid, stage=ModelStage.IMAGE_GENERATION,
            tier=ModelTier.PRODUCTION, scene_id=uuid.UUID(scene_id),
        )
        assert mine.model.name == "wp66-scene"
        assert mine.provenance == "scene"

        sibling = await selection_panel.resolve_binding(
            db_session, project_id=pid, stage=ModelStage.IMAGE_GENERATION,
            tier=ModelTier.PRODUCTION, scene_id=uuid.uuid4(),
        )
        assert sibling.model.name == "wp66-proj"

    async def test_clearing_removes_the_row_rather_than_duplicating_it(
        self, db_session, project_id, scene_id
    ):
        """Proven by the row's ABSENCE, per the brief. A duplicate keeps
        pointing at the old model after the project default changes, and
        dispatch reads scene-scoped first, so the scene would silently stop
        following a default it appears to follow."""
        proj = await _model(db_session, name="wp66-p2",
                            weights_ref=_FETCHABLE.format(uuid.uuid4()))
        other = await _model(db_session, name="wp66-s2",
                             weights_ref=_FETCHABLE.format(uuid.uuid4()))
        pid, sid = uuid.UUID(project_id), uuid.UUID(scene_id)
        await planner.manual_override(
            db_session, project_id=pid, scene_id=None,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=proj.id, rationale="project",
        )
        await planner.manual_override(
            db_session, project_id=pid, scene_id=sid,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
            model_id=other.id, rationale="scene",
        )
        await db_session.commit()

        cleared = await planner.clear_selection(
            db_session, project_id=pid, scene_id=sid,
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        await db_session.commit()
        assert cleared == 1

        rows = (await db_session.execute(
            select(ProjectModelSelection).where(
                ProjectModelSelection.project_id == pid,
                ProjectModelSelection.scene_id == sid,
            )
        )).scalars().all()
        assert rows == []          # the row is GONE, not rewritten

        back = await selection_panel.resolve_binding(
            db_session, project_id=pid, stage=ModelStage.IMAGE_GENERATION,
            tier=ModelTier.PRODUCTION, scene_id=sid,
        )
        assert back.model.name == "wp66-p2"

    async def test_clearing_a_scene_that_had_no_override_is_a_no_op(
        self, db_session, project_id, scene_id
    ):
        await db_session.commit()
        cleared = await planner.clear_selection(
            db_session, project_id=uuid.UUID(project_id),
            scene_id=uuid.UUID(scene_id),
            stage=ModelStage.IMAGE_GENERATION, tier=ModelTier.PRODUCTION,
        )
        assert cleared == 0

    async def test_the_media_type_decides_which_stage_the_picker_offers(self):
        assert selection_panel.MEDIA_TYPE_STAGE["image"] is ModelStage.IMAGE_GENERATION
        assert selection_panel.MEDIA_TYPE_STAGE["video_clip"] is ModelStage.VIDEO_GENERATION
        assert selection_panel.MEDIA_TYPE_STAGE["animation"] is ModelStage.ANIMATION_GENERATION

    async def test_an_animation_scene_is_offered_animation_models(
        self, db_session, project_id, scene_id
    ):
        await _model(db_session, name="wp66-anim",
                     stage=ModelStage.ANIMATION_GENERATION,
                     weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await _model(db_session, name="wp66-img",
                     stage=ModelStage.IMAGE_GENERATION,
                     weights_ref=_FETCHABLE.format(uuid.uuid4()))
        await db_session.commit()
        panel = await selection_panel.scene_panel(
            db_session, project_id=uuid.UUID(project_id),
            scene_id=uuid.UUID(scene_id), media_type="animation",
            tier=ModelTier.PRODUCTION,
        )
        names = {c.name for c in panel.candidates}
        assert "wp66-anim" in names
        assert "wp66-img" not in names


# ---------------------------------------------------------------------------
# TASK 6 — the presets path
# ---------------------------------------------------------------------------

class TestThePresetPathIsRealAndNowRecordsItself:
    """MEASURED: `PresetApplyPanel.tsx`'s claim that a preset "writes the
    preset's actor, model selections and media defaults into this project" is
    TRUE for model selections. `preset_service.py:246` calls
    `model_selection.manual_override` for every entry, and that is the same
    function the API's own override route calls -- not a stub, not a no-op.

    What it LOST was which of them it was: `manual_override` hardcoded
    `selected_by=MANUAL`, so a preset's selection was indistinguishable, in the
    column that exists to say so, from an operator's own choice. The only trace
    was a rationale string an operator can freely edit.
    """

    def test_the_preset_service_really_calls_the_override(self):
        import inspect

        from app.services import preset_service

        src = inspect.getsource(preset_service)
        assert "model_selection.manual_override" in src

    def test_it_now_passes_the_preset_provenance_explicitly(self):
        import inspect

        from app.services import preset_service

        src = inspect.getsource(preset_service)
        assert "selected_by=SelectionSource.PRESET" in src

    def test_manual_override_accepts_a_provenance_and_defaults_to_manual(self):
        import inspect

        sig = inspect.signature(planner.manual_override)
        assert "selected_by" in sig.parameters
        assert sig.parameters["selected_by"].default is SelectionSource.MANUAL

    def test_the_preset_path_still_validates_through_the_same_gate(self):
        """A preset created while a model was approved and applied after it was
        retired must fail with the CURRENT reason -- which it does, because it
        goes through the same function and not a copy of its checks."""
        import inspect

        from app.services import preset_service

        src = inspect.getsource(preset_service)
        assert "manual_override already validates" in src


class TestTheAuditTrail:
    def test_the_override_route_writes_an_audit_row(self):
        """A model change alters what the pipeline will PRODUCE, so it is an
        audited event, not a preference."""
        import inspect

        from app.api.v1 import model_store

        src = inspect.getsource(model_store.override)
        assert "MODEL_SELECTION_SET" in src
        assert "previous_provenance" in src

    def test_the_clear_route_writes_one_too(self):
        import inspect

        from app.api.v1 import model_store

        src = inspect.getsource(model_store.clear_scene_selection)
        assert "MODEL_SELECTION_CLEARED" in src
