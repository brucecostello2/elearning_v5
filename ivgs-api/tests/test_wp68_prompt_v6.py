"""WP-68 Task 4 — storyboard v6 asks for motion graphics as STRUCTURED DATA.

WHY THIS IS A FOURTH MEDIA TYPE AND NOT AN ANIMATION SUBTYPE. The two are told
apart by what they NEED, and WP-67's capability contracts state both:

    animation (wan_animate)   requires prompt, reference_image,
                              person_in_reference, reference_clip
    motion_graphics           requires structured_scene_data -- and no image,
                              and no person

A subtype would have put two incompatible input contracts behind one value the
orchestrator routes by, and the routing is what decides which worker gets the
scene.

AND WHY THE PROMPT MAY CHOOSE IT WHILE THE EDITOR MAY NOT OFFER IT. WP-64
removed a Media Type dropdown option advertising "Motion graphics via
Remotion/AnimateDiff", a pathway that did not exist. Adding one back before a
renderer is deployed would be the same defect. The prompt choosing it produces a
recorded, structured, honest intention that the orchestrator HOLDS by name; an
operator choosing it in the editor would produce a scene they expect to render.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_wp63_storyboard_prompt import check_visuals

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "seed" / "default_prompts" / "storyboard_generation.j2"
)


def _scene(index, media_type="motion_graphics", params=None, visual=None):
    return {
        "scene_index": index,
        "media_type": media_type,
        "visual_description": visual or (
            "the carry travelling from the units column to the tens column "
            "above a ruled line, warm desk lamp, illustration style"
        ),
        "generation_params": params,
    }


class TestV6AsksForTheChoice:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def test_the_criterion_names_what_earns_motion_graphics(self, text):
        assert "NUMERIC OR STRUCTURAL TRANSFORMATION THE VIEWER MUST SEE" in text

    def test_rule_8_exists_and_says_it_is_not_prose(self, text):
        assert 'RULE 8 — A "motion_graphics" SCENE IS STRUCTURED DATA' in text

    def test_all_four_templates_are_named_with_their_parameters(self, text):
        from shared.motion.templates import template_names

        for name in template_names():
            assert f'"template": "{name}"' in text, name

    def test_the_prompt_names_no_template_that_does_not_exist(self, text):
        """A prompt that offers a template the renderer does not serve produces
        a scene that cannot be rendered at all."""
        import re

        from shared.motion.templates import template_names

        offered = set(re.findall(r'"template": "([a-z_]+)"', text))
        assert offered <= set(template_names()), offered - set(template_names())

    def test_the_person_criterion_survives_for_animation(self, text):
        """WP-64 D-2 stays: Wan is still Wan, and the two capabilities must be
        chosen between deliberately rather than blurred."""
        assert "ONLY if a person is" in text
        assert "pose reenactment" in text

    def test_the_two_are_stated_to_be_non_interchangeable(self, text):
        assert '"animation" AND "motion_graphics" ARE NOT INTERCHANGEABLE' in text
        assert "can never be \"animation\", however much it moves" in text

    def test_rule_1_is_scoped_rather_than_contradicted(self, text):
        """The parameters ARE digits, and they are drawn rather than generated
        -- so RULE 1 has to be told it does not apply to them, or the model is
        given two rules that contradict."""
        assert "RULE 1's ban on digits therefore does NOT apply to these" in text
        assert "NO TEXT IN THE VISUAL" in text          # and RULE 1 survives

    def test_the_numbers_must_be_the_lessons_numbers(self, text):
        assert "MUST be the numbers this lesson actually uses" in text

    def test_the_stale_no_pathway_sentence_is_gone(self, text):
        """v4 told the model 'There is no motion-graphics pathway in this
        pipeline yet.' Leaving that in while adding RULE 8 would be a prompt
        that contradicts itself."""
        assert "no motion-graphics pathway in this pipeline yet" not in text


class TestTheCheckerCatchesABadMotionScene:
    """RED-GREEN: every one of these findings is absent for a well-formed
    scene and present for a malformed one."""

    def test_a_well_formed_motion_scene_is_clean(self):
        findings = check_visuals([
            _scene(0, params={"template": "column_addition_carry",
                              "top": 27, "bottom": 15}),
        ])
        assert not [f for f in findings if "motion" in f or "template" in f
                    or "generation_params" in f], findings

    def test_a_motion_scene_with_no_params_is_caught(self):
        findings = check_visuals([_scene(0, params=None)])
        assert any("carries no generation_params" in f for f in findings)

    def test_a_template_that_does_not_exist_is_caught(self):
        findings = check_visuals([
            _scene(0, params={"template": "number_go_brrr", "number": 23}),
        ])
        assert any("does not exist" in f for f in findings)

    def test_a_parameter_the_template_does_not_take_is_caught(self):
        findings = check_visuals([
            _scene(0, params={"template": "place_value_split",
                              "number": 23, "colour": "red"}),
        ])
        assert any("does not take" in f and "colour" in f for f in findings)

    def test_a_stringly_typed_number_is_caught(self):
        """A string '23' reaches the renderer as text and is drawn as one,
        which is the exact failure this media type exists to avoid."""
        findings = check_visuals([
            _scene(0, params={"template": "place_value_split", "number": "23"}),
        ])
        assert any("not an integer" in f for f in findings)

    def test_a_missing_template_key_is_caught(self):
        findings = check_visuals([_scene(0, params={"number": 23})])
        assert any("names no 'template'" in f for f in findings)

    def test_the_known_template_list_comes_from_the_renderer(self):
        """Not retyped. A template added or renamed in the module cannot leave
        this checker validating a name nobody serves."""
        from tests.test_wp63_storyboard_prompt import _motion_templates
        from shared.motion.templates import template_names

        assert set(_motion_templates()) == set(template_names())

    def test_rule_1_still_applies_to_a_motion_scenes_visual(self):
        """The PARAMETERS may carry digits; the description may not. It is
        still shown as a caption and still read by a human."""
        findings = check_visuals([
            _scene(0, params={"template": "place_value_split", "number": 23},
                   visual="the number 23 splitting above a ruled line"),
        ])
        assert any("contains digits" in f for f in findings)

    def test_the_other_media_types_are_unaffected(self):
        """A change to one branch of the checker must not move another."""
        findings = check_visuals([
            {"scene_index": 0, "media_type": "image",
             "visual_description": (
                 "a hand resting a pencil at the foot of a two-row column "
                 "addition on lined paper, both partial-product rows written "
                 "above a ruled horizontal line"
             )},
        ])
        assert not any("generation_params" in f or "template" in f
                       for f in findings)


class TestTheFourthValueExistsEverywhereItHasTo:
    """FOUND BY THE ACCEPTANCE RUN, NOT BY A TEST, WHICH IS WHY THIS EXISTS.

    Migration 0041 added `motion_graphics` to the PostgreSQL type and the two
    API validators were updated -- and the ORM COLUMN's own literal list was
    missed. The result was worse than a plain failure: the INSERT succeeded
    against the PostgreSQL type, and every SELECT afterwards raised
    `LookupError: 'motion_graphics' is not among the defined enum values`. The
    row was written and could not be read back.

    There is now ONE list (`shared.models.enums.MEDIA_TYPES`), read by the
    model, by the schema and by the checker.
    """

    def test_the_orm_column_accepts_it(self):
        from app.models.storyboard_scene import StoryboardScene

        assert "motion_graphics" in StoryboardScene.__table__.c.media_type.type.enums

    def test_the_orm_and_the_api_schema_read_the_same_list(self):
        from app.models.storyboard_scene import StoryboardScene
        from app.schemas.storyboard import MEDIA_TYPES

        assert tuple(
            StoryboardScene.__table__.c.media_type.type.enums
        ) == tuple(MEDIA_TYPES)

    def test_the_python_enum_agrees_too(self):
        from shared.models.enums import MEDIA_TYPES, MediaType

        assert MEDIA_TYPES == tuple(m.value for m in MediaType)

    def test_the_checkers_list_agrees(self):
        from tests.test_wp63_storyboard_prompt import MEDIA_TYPES as CHECKER
        from shared.models.enums import MEDIA_TYPES

        assert set(CHECKER) == set(MEDIA_TYPES)

    def test_adaptation_targets_are_deliberately_a_SHORTER_list(self):
        """Not an oversight: `Adapt description` rewrites PROSE for a medium,
        and a motion graphic takes structured parameters, not prose. Asserted
        so a future tidy-up does not 'fix' it into agreement."""
        from app.services.adaptation_service import MEDIA_TYPES as ADAPT
        from shared.models.enums import MEDIA_TYPES

        assert set(ADAPT) < set(MEDIA_TYPES)
        assert "motion_graphics" not in ADAPT
