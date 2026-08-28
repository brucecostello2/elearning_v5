"""WP-IVGS-09b — the scene model picker, per MEDIUM.

THE DEFECT, AS REPORTED AND AS MEASURED. A scene switched to
``motion_graphics`` in the GUI offered no motion-graphics model: the picker kept
saying ``image_generation`` and listed the two FLUX rows. Measured live through
the GUI path on 2026-08-28, before the fix:

    GET /api/v1/projects/{pid}/model-selections/scene/{sid}
        ?media_type=motion_graphics&tier=production
    -> 200  stage="image_generation"  candidates=[flux1-schnell, FLUX.1-dev]

``selection_panel.MEDIA_TYPE_STAGE`` had three entries and the lookup was
``.get(media_type, IMAGE_GENERATION)``. ``motion_graphics`` was not one of them,
so it fell back — silently, with no warning anywhere — and ``maths-motion``
(approved, enabled, and the only thing that can render such a scene) could never
be offered.

THE SAME MEASUREMENT FOUND THE MIRROR DEFECT. The ``animation`` picker was
already listing ``maths-motion`` as SELECTABLE, because ``_candidates_for``
filtered on ``(stage, tier)`` with no family dimension and both media types
share ``animation_generation``. Wan2.2-Animate cannot render a diagram and a
template renderer cannot animate a person; each was being offered the other's
model.

These tests pin BOTH directions, because a fix for one that widens the other
would pass a test written only for the first.
"""
from __future__ import annotations

import pytest

from app.services import selection_panel
from shared.models.model_store import (
    Model,
    ModelEngine,
    ModelStage,
    ModelState,
    ModelTier,
)


async def _animation_stage_as_it_is_live(db):
    """The `animation_generation` stage in the shape the live store holds it.

    Wan carries the one `is_default` flag; `maths-motion` is approved, enabled
    and has none — which is the exact configuration that resolved a
    motion-graphics scene to Wan.
    """
    import uuid

    for name, engine, is_default in (
        ("wan-default", ModelEngine.COMFYUI, True),
        ("maths-motion-test", ModelEngine.MOTION_GRAPHICS, False),
    ):
        db.add(
            Model(
                id=uuid.uuid4(), name=name, display_name=name,
                stage=ModelStage.ANIMATION_GENERATION, engine=engine,
                tier=ModelTier.BOTH, state=ModelState.APPROVED,
                is_default=is_default, enabled=True,
                dynamically_loadable=True,
            )
        )
    await db.flush()


class TestEveryMediaTypeMapsToAStage:
    """The map is the thing that was incomplete."""

    def test_motion_graphics_maps_to_animation_generation(self):
        """MBCP's taxonomy, not a second opinion: WP-67 registers `maths_motion`
        on `animation_generation` and the Model Store row says the same."""
        assert (
            selection_panel.stage_for_media_type("motion_graphics")
            is ModelStage.ANIMATION_GENERATION
        )

    @pytest.mark.parametrize(
        "media_type,stage",
        [
            ("image", ModelStage.IMAGE_GENERATION),
            ("video_clip", ModelStage.VIDEO_GENERATION),
            ("animation", ModelStage.ANIMATION_GENERATION),
            ("motion_graphics", ModelStage.ANIMATION_GENERATION),
        ],
    )
    def test_the_other_three_are_unchanged(self, media_type, stage):
        assert selection_panel.stage_for_media_type(media_type) is stage

    def test_every_value_of_the_MediaType_ENUM_is_mapped(self):
        """⛔ THE TEST THAT WOULD HAVE CAUGHT THIS.

        `MediaType` gained `motion_graphics` in migration 0041 (WP-68) and this
        map was never extended. Nothing connected the two, so nothing failed.
        A new media type now cannot be added without either mapping it or
        turning this red."""
        from shared.models.enums import MEDIA_TYPES

        missing = [m for m in MEDIA_TYPES if m not in selection_panel.MEDIA_TYPE_STAGE]
        assert not missing, (
            f"media types with no stage mapping: {missing}. The picker would "
            f"silently offer image-generation models for them."
        )

    def test_an_unmapped_media_type_is_refused_by_name_not_defaulted(self):
        """The default is what made the defect silent. A wrong answer delivered
        with no warning is worse than no answer."""
        with pytest.raises(ValueError) as exc:
            selection_panel.stage_for_media_type("no_such_medium")
        assert "no_such_medium" in str(exc.value)
        assert "motion_graphics" in str(exc.value)  # it lists the known ones


class TestAStageIsNotAMedium:
    """`animation` and `motion_graphics` share one stage and must not share a
    candidate list."""

    def test_motion_graphics_offers_only_the_motion_graphics_engine(self):
        stage = selection_panel.stage_for_media_type("motion_graphics")
        assert selection_panel.engines_for_media_type("motion_graphics", stage) == frozenset(
            {"motion_graphics"}
        )

    def test_animation_offers_only_the_comfyui_engine(self):
        """The mirror half. Before this fix the animation picker listed
        `maths-motion` as selectable — a template renderer offered for a scene
        that needs a person reenacted."""
        stage = selection_panel.stage_for_media_type("animation")
        engines = selection_panel.engines_for_media_type("animation", stage)
        assert engines == frozenset({"comfyui"})
        assert "motion_graphics" not in engines

    def test_the_two_lists_are_disjoint(self):
        stage = ModelStage.ANIMATION_GENERATION
        a = selection_panel.engines_for_media_type("animation", stage)
        m = selection_panel.engines_for_media_type("motion_graphics", stage)
        assert a and m and not (a & m)

    @pytest.mark.parametrize("media_type", ["image", "video_clip"])
    def test_media_types_that_do_not_share_a_stage_are_NOT_narrowed(self, media_type):
        """⛔ THE NO-WIDENING-AND-NO-NARROWING GUARD.

        `talking_head`, `video_generation` and `voiceover_tts` all serve several
        families too — but each serves exactly ONE medium, so narrowing them
        would change a list nobody reported. `None` means "every model on the
        stage", which is what they got before this package."""
        stage = selection_panel.stage_for_media_type(media_type)
        assert selection_panel.engines_for_media_type(media_type, stage) is None

    def test_the_engine_set_comes_from_the_registry_not_a_second_list(self):
        """One definition. A hardcoded "which engines are animation engines"
        beside the registry is a second definition, free to drift."""
        from shared.providers.client_registry import engines_for_families

        for media_type, families in selection_panel.MEDIA_TYPE_FAMILIES.items():
            stage = selection_panel.stage_for_media_type(media_type)
            assert selection_panel.engines_for_media_type(
                media_type, stage
            ) == engines_for_families(stage.value, families)

    def test_a_family_the_registry_does_not_know_RAISES_rather_than_widening(
        self, monkeypatch
    ):
        """An empty engine set and `None` are different answers. Falling back to
        every engine on the stage is exactly how a scene gets offered a model
        that cannot render it."""
        monkeypatch.setitem(
            selection_panel.MEDIA_TYPE_FAMILIES, "motion_graphics",
            frozenset({"no_such_family"}),
        )
        with pytest.raises(ValueError) as exc:
            selection_panel.engines_for_media_type(
                "motion_graphics", ModelStage.ANIMATION_GENERATION
            )
        assert "no_such_family" in str(exc.value)


class TestTheDefaULTIsAlsoPerMedium:
    """⛔ THE HALF THAT WAS STILL WRONG AFTER THE CANDIDATE FILTER LANDED.

    With candidates narrowed but `resolve_binding` left stage-wide, a
    `motion_graphics` scene with no selection of its own resolved to
    **`wan2.2-animate`** — measured in exactly that state. The panel offered one
    model, `maths-motion`, and announced underneath it that the scene was
    currently bound to a model that cannot render it. `is_default` is one flag
    per stage, and on `animation_generation` it belongs to the animation medium.
    """

    async def test_a_motion_graphics_scene_does_not_resolve_to_the_animation_default(
        self, db_session, model_store_project
    ):
        """Seeded to the shape the live store is in: Wan is the stage default,
        maths-motion is approved with no default flag of its own."""
        from app.services import selection_panel as sp

        await _animation_stage_as_it_is_live(db_session)

        stage = sp.stage_for_media_type("motion_graphics")
        resolved = await sp.resolve_binding(
            db_session, project_id=model_store_project.id, stage=stage,
            tier=ModelTier.PRODUCTION, scene_id=None,
            engines=sp.engines_for_media_type("motion_graphics", stage),
        )
        assert resolved.model is not None, "the sole servable model should resolve"
        assert resolved.model.engine is ModelEngine.MOTION_GRAPHICS, (
            f"a motion_graphics scene resolved to {resolved.model.name!r} on "
            f"engine {resolved.model.engine.value!r}"
        )
        assert resolved.provenance == "only_candidate"

    async def test_the_animation_default_is_unchanged(
        self, db_session, model_store_project
    ):
        """The no-regression half: narrowing must not move the medium that owns
        the `is_default` flag."""
        from app.services import selection_panel as sp

        await _animation_stage_as_it_is_live(db_session)

        stage = sp.stage_for_media_type("animation")
        resolved = await sp.resolve_binding(
            db_session, project_id=model_store_project.id, stage=stage,
            tier=ModelTier.PRODUCTION, scene_id=None,
            engines=sp.engines_for_media_type("animation", stage),
        )
        assert resolved.model is not None
        assert resolved.model.name == "wan-default"
        assert resolved.provenance == "default"

    def test_only_candidate_is_not_called_default(self):
        """Nobody chose it. Calling it `default` would assert a decision that
        was never made — the provenance field exists precisely to stop that."""
        from app.services import selection_panel as sp

        assert sp._ONLY_CANDIDATE_PROVENANCE[0] == "only_candidate"
        assert sp._ONLY_CANDIDATE_PROVENANCE[0] != sp._DEFAULT_PROVENANCE[0]
