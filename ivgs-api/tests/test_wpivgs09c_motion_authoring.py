"""WP-IVGS-09c — a motion scene can be authored after the storyboard exists.

THE MEASURED CHAIN, on project 9c29b1d1 during RUN-2:

  six scenes flipped to motion_graphics in the GUI  -> generation_params = {}
  per-scene Regen                                   -> re-render path; no prompt
  media dispatch                                    -> all six refused by name
  stage failed -> partial-advance -> talking_head_render -> LatentSync OOM

Only v6's RULE 8 ever authored a template, and it only runs while the whole
storyboard is being written. `adapt-description`, the other medium-aware
prompt, DELIBERATELY excludes this medium and a WP-68 test pins the exclusion.
"""
from __future__ import annotations

import pytest

from app.services.motion_authoring import (
    MotionAuthoringError,
    build_prompt,
    has_motion_spec,
    parse_and_validate,
    template_catalogue,
)


class TestTheCatalogueComesFromTheRenderer:
    def test_it_is_the_templates_module_not_a_copy(self):
        from shared.motion.templates import template_names

        assert set(template_catalogue()) == set(template_names())

    def test_the_prompt_names_every_template_and_its_real_parameters(self):
        """A prompt that offered a template the renderer lacks, or a parameter
        spelled differently, would author specs that cannot be drawn."""
        from shared.motion.templates import template_names, template_spec

        prompt = build_prompt(
            narration="twenty-three times fourteen",
            visual_description="a hand with a pencil",
            project_name="two by two multiplication",
            project_description="for a 9 year old",
        )
        for name in template_names():
            assert name in prompt
            for param in template_spec(name)["params"]:
                assert f'"{param}"' in prompt

    def test_the_prompt_carries_the_scene_and_the_lesson(self):
        prompt = build_prompt(
            narration="NARRATION-MARKER", visual_description="VISUAL-MARKER",
            project_name="TITLE-MARKER", project_description="ABOUT-MARKER",
        )
        for marker in ("NARRATION-MARKER", "VISUAL-MARKER", "TITLE-MARKER", "ABOUT-MARKER"):
            assert marker in prompt

    def test_the_worked_counter_example_survives_the_f_string(self):
        """⛔ THIS EXACT BUG WAS SHIPPED AND CAUGHT LIVE, not by pytest.

        `build_prompt` is an f-string and the instruction below contains literal
        JSON. Unescaped, `{"top": 23, ...}` is read as a format field and every
        authoring call dies with
        `ValueError: Invalid format specifier ' 23, "bottom": 14, "step": 0'`.
        The suite already called `build_prompt` and would have caught it on the
        next run; it was deployed before that run happened. Pinned on the exact
        literal so the escaping cannot be lost again.

        WP-IVGS-09f moved the worked example OFF this lesson's numbers, and the
        literals below moved with it. THE ASSERTION IS UNCHANGED IN KIND — that
        literal JSON survives the f-string — and it is deliberately still pinned
        to exact text. Why the numbers changed: the example used to be stated on
        23 x 14, which IS this lesson's sum, and at TEMPERATURE 0.1 the model
        returned the example instead of reading the scene. Measured: five scenes,
        five identical answers, four of them wrong. The illustration is now 47 x
        36 so that copying it is visibly wrong rather than quietly plausible."""
        prompt = build_prompt(
            narration="n", visual_description="v", project_name="p",
            project_description="d",
        )
        assert '{"top": 47, "bottom": 36, "step": 0}' in prompt
        assert '{"top": 7, "bottom": 6}' in prompt
        # And the old numbers must NOT be handed to the model as an answer.
        assert '{"top": 23, "bottom": 14, "step": 0}' not in prompt

    def test_it_says_the_parameters_are_the_whole_numbers_not_the_step_digits(self):
        """The measured failure: given "multiply 4 times 3" for a 23 x 14
        lesson, the model authored {top: 14, bottom: 3} — arithmetically correct
        (14 x 3 = 42) and pedagogically wrong. The template's own parameter
        descriptions already said "the multiplicand" / "the multiplier"; the
        prompt now says what that means for a narration describing one step."""
        prompt = build_prompt(
            narration="n", visual_description="v", project_name="p",
            project_description="d",
        )
        assert "NOT THE DIGITS THIS STEP" in prompt

    def test_it_says_the_numbers_must_be_the_lesson_s_own(self):
        """The one instruction that matters: nothing downstream checks the
        arithmetic until M3.3, so a convenient number is a taught mistake.

        WP-IVGS-09f narrows the wording from "THIS LESSON" to THIS SCENE. A
        lesson works more than one sum -- 9c29b1d1 does 23 x 14 and then
        32 x 21 -- so "the lesson's numbers" was satisfied by scene 10 being
        authored against 23 x 14 while its words worked 32 x 21. Strictly
        stronger: the scene's numbers are a subset of the lesson's."""
        prompt = build_prompt(
            narration="n", visual_description="v", project_name="p",
            project_description="d", scene_index=10,
        )
        assert "THE NUMBERS MUST BE THE ONES SCENE 10 ACTUALLY WORKS" in prompt
        assert "Do not choose round or convenient numbers" in prompt


class TestNothingIsInventedOnTheModelSBehalf:
    def test_a_clean_object_is_accepted(self):
        assert parse_and_validate('{"template": "place_value_split", "number": 23}') == {
            "template": "place_value_split", "number": 23,
        }

    def test_a_code_fence_is_tolerated(self):
        """The common, harmless deviation. Tolerated because it changes nothing
        about what was asked for — unlike everything below."""
        out = parse_and_validate(
            '```json\n{"template": "column_addition_carry", "top": 27, "bottom": 15}\n```'
        )
        assert out["template"] == "column_addition_carry"

    def test_a_numeric_string_is_coerced_but_a_word_is_not(self):
        assert parse_and_validate(
            '{"template": "place_value_split", "number": "23"}'
        )["number"] == 23

    def test_an_unknown_template_is_refused_not_matched_to_the_nearest(self):
        with pytest.raises(MotionAuthoringError) as exc:
            parse_and_validate('{"template": "place_value", "number": 23}')
        assert "does not exist" in str(exc.value)
        assert "place_value_split" in str(exc.value)

    def test_a_missing_parameter_is_refused_not_defaulted(self):
        """⛔ The one that matters most. A defaulted parameter draws arithmetic
        nobody asked for, and no gate reads the frame until M3.3."""
        with pytest.raises(MotionAuthoringError) as exc:
            parse_and_validate('{"template": "place_value_split"}')
        assert "omitted" in str(exc.value)

    def test_an_invented_parameter_is_refused_not_dropped(self):
        with pytest.raises(MotionAuthoringError) as exc:
            parse_and_validate(
                '{"template": "place_value_split", "number": 23, "colour": "red"}'
            )
        assert "invented" in str(exc.value)

    def test_prose_with_no_object_is_refused(self):
        with pytest.raises(MotionAuthoringError) as exc:
            parse_and_validate("I think you want place_value_split with 23.")
        assert "no JSON object" in str(exc.value)

    def test_a_spec_the_templates_module_refuses_is_refused_here(self):
        """The renderer is the final authority, asked before dispatch rather
        than after. Cheap: the templates module is pure data."""
        with pytest.raises(MotionAuthoringError):
            parse_and_validate(
                '{"template": "column_multiplication_step", "top": "x", '
                '"bottom": "y", "step": "z"}'
            )


class TestWhichScenesAreUnauthored:
    """`{}` is the shape the GUI flip leaves — an object that exists and says
    nothing. A truthiness test would have been right by accident."""

    @pytest.mark.parametrize("params", [None, {}, {"seed": 7}, {"template": ""}, "not a dict"])
    def test_these_need_authoring(self, params):
        assert not has_motion_spec(params)

    def test_a_real_spec_does_not(self):
        assert has_motion_spec({"template": "place_value_split", "number": 23})

    def test_a_scene_v6_authored_is_left_alone(self):
        """Regen re-renders from the scene's CURRENT fields. Silently
        re-authoring a spec the operator or v6 chose would break that promise."""
        assert has_motion_spec({"template": "column_addition_carry", "top": 27, "bottom": 15})


class TestTheOtherMediumAwarePromptIsStillExcluded:
    def test_adapt_description_still_refuses_motion_graphics(self):
        """This module is the separate thing that was missing, NOT a widening
        of the one that was right. WP-68 excluded motion_graphics from
        `adapt-description` on purpose — prose for a renderer that reads none —
        and this fix must not have quietly undone it."""
        from app.services.adaptation_service import MEDIA_TYPES as ADAPT

        assert "motion_graphics" not in ADAPT


class TestOneRowCannotServeTwoScenes:
    """WP-IVGS-09d. A composition layer is keyed on (scene, asset).

    `asset_service.upload_asset` deduped on content-or-params within a project
    and said nothing about the scene, so two scenes producing the same bytes
    collapsed onto one row and the second got none. `manifests.py` groups assets
    by `scene_id` to build layers, so that scene had no background and stage 7
    refused the whole draft — three consecutive times on project 9c29b1d1,
    while every render reported success.
    """

    async def test_the_same_bytes_for_a_SECOND_scene_get_their_own_row(
        self, db_session, model_store_project
    ):
        import uuid as _uuid

        from app.models.storyboard_scene import StoryboardScene
        from app.services.asset_service import AssetService

        scenes = []
        for i in range(2):
            sc = StoryboardScene(
                id=_uuid.uuid4(), project_id=model_store_project.id,
                scene_index=i, media_type="motion_graphics",
                narration_text="n", visual_description="v", duration_seconds=5.0,
            )
            db_session.add(sc)
            scenes.append(sc)
        await db_session.flush()

        svc = AssetService(db_session)
        payload = b"identical rendered bytes for both scenes"
        first, dedup_a = await svc.upload_asset(
            project_id=model_store_project.id, file_content=payload,
            filename="a.mp4", content_type="video/mp4", asset_type="video",
            scene_id=scenes[0].id,
        )
        second, dedup_b = await svc.upload_asset(
            project_id=model_store_project.id, file_content=payload,
            filename="b.mp4", content_type="video/mp4", asset_type="video",
            scene_id=scenes[1].id,
        )

        assert first.id != second.id, (
            "the second scene was handed the first scene's asset row; it will "
            "have no background layer and stage 7 will refuse the draft"
        )
        assert second.scene_id == scenes[1].id
        assert dedup_b is False, (
            "reporting was_deduplicated=True for a row that was created is the "
            "sentence that hid this defect"
        )
        # The bytes are still stored once.
        assert second.seaweedfs_fid == first.seaweedfs_fid
        assert second.content_hash == first.content_hash

    async def test_the_same_scene_uploading_twice_STILL_dedups(
        self, db_session, model_store_project
    ):
        """The behaviour the dedup exists for is unchanged: a re-run of ONE
        scene re-references rather than duplicating."""
        import uuid as _uuid

        from app.models.storyboard_scene import StoryboardScene
        from app.services.asset_service import AssetService

        sc = StoryboardScene(
            id=_uuid.uuid4(), project_id=model_store_project.id, scene_index=0,
            media_type="motion_graphics", narration_text="n",
            visual_description="v", duration_seconds=5.0,
        )
        db_session.add(sc)
        await db_session.flush()

        svc = AssetService(db_session)
        payload = b"one scene, uploaded twice"
        first, _ = await svc.upload_asset(
            project_id=model_store_project.id, file_content=payload,
            filename="a.mp4", content_type="video/mp4", asset_type="video",
            scene_id=sc.id,
        )
        second, deduped = await svc.upload_asset(
            project_id=model_store_project.id, file_content=payload,
            filename="a.mp4", content_type="video/mp4", asset_type="video",
            scene_id=sc.id,
        )
        assert second.id == first.id
        assert deduped is True
        assert second.reference_count == 2


# ---------------------------------------------------------------------------
# WP-IVGS-09f — the narration guard
#
# RUN-2 review finding: the draft rendered, the operator watched it, and every
# motion scene's calculation was wrong for its narration. Five scenes carried
# the identical spec {"top": 23, "bottom": 14, "step": 1} while their words
# walked five different steps of TWO DIFFERENT SUMS.
#
# These tests pin the mechanical half of the fix. They use project 9c29b1d1's
# real narrations verbatim, because a paraphrase would be a test of a sentence
# I wrote rather than of the one that shipped.
# ---------------------------------------------------------------------------
import pytest

from app.services.motion_authoring import (
    MotionAuthoringError,
    narration_numbers,
    producible_numbers,
    verify_spec_against_narration,
)

#: Verbatim from project 9c29b1d1, scenes 2-10.
NARR = {
    2: "We start by multiplying by the ones digit, which is 4 in 14. Multiply 4 "
       "times 3, which equals 12. Write the 2 underneath the ones column and "
       "carry the 1 above the tens column.",
    3: "Next, multiply 4 times 2, which equals 8. Add the carried 1 to get 9. "
       "So, our first answer is 92.",
    4: "Now, we multiply by the tens digit, which is 1 in 14. Remember, this 1 "
       "means 10 because it's in the tens place. Put a zero in the ones place "
       "as a placeholder.",
    5: "Multiply 1 times 3, which equals 3, and 1 times 2, which equals 2. Our "
       "second answer is 230.",
    7: "Then, 1 plus 2 equals 3. Our final answer is 322. So, 23 times 14 "
       "equals 322.",
    10: "Now, move to the tens digit, 2. Remember to start with a zero. "
        "Multiply 2 times 2, which equals 4, and 2 times 3, which equals 6. Our "
        "second answer is 640.",
}

#: The lesson's other scenes, which is where a second example's operands live.
CONTEXT = (
    "By the end, you'll be able to solve a problem like 23 times 14 on your own. "
    "Now, we add the two answers together: 92 and 230. "
    "Let's try another one: 32 times 21. Write 32 on top and 21 underneath. "
    "Add 32 plus 640, which equals 672. So, 32 times 21 equals 672."
)

#: What the six scenes ACTUALLY carried when the operator watched the draft.
AS_SHIPPED = {
    2: {"template": "column_multiplication_step", "top": 14, "bottom": 3, "step": 0},
    3: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
    4: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
    5: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
    7: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
    10: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
}

#: What the narrations actually describe.
CORRECT = {
    2: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 0},
    3: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 0},
    4: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
    5: {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 1},
    7: {"template": "column_addition_carry", "top": 230, "bottom": 92},
    10: {"template": "column_multiplication_step", "top": 32, "bottom": 21, "step": 1},
}


def _check(index, spec):
    verify_spec_against_narration(
        spec, NARR[index], context_text=CONTEXT, scene_index=index,
    )


class TestTheGuardRefusesWhatTheOperatorHadToWatch:
    """Each of these is a scene that RENDERED and was wrong on screen."""

    @pytest.mark.parametrize("index", [2, 3, 7, 10])
    def test_the_shipped_spec_is_refused(self, index):
        with pytest.raises(MotionAuthoringError):
            _check(index, AS_SHIPPED[index])

    def test_scene_2_is_caught_because_the_operands_are_INVERTED(self):
        """"the ones digit, which is 4 in 14" makes 14 the MULTIPLIER."""
        with pytest.raises(MotionAuthoringError, match="wrong way round"):
            _check(2, AS_SHIPPED[2])

    def test_scene_3_is_caught_by_the_ANNOUNCED_RESULT(self):
        """step=1 draws 230; the words say "our first answer is 92".

        92 is SMALLER than 230, so a ceiling test alone lets this through. The
        announced-result assertion is what separates step 0 from step 1."""
        with pytest.raises(MotionAuthoringError, match="announces 92"):
            _check(3, AS_SHIPPED[3])

    def test_scene_7_wanted_ADDITION_and_got_multiplication(self):
        with pytest.raises(MotionAuthoringError, match="322"):
            _check(7, AS_SHIPPED[7])

    def test_scene_10_was_pointed_at_a_DIFFERENT_SUM(self):
        """Its words work 32 x 21; its spec worked 23 x 14."""
        with pytest.raises(MotionAuthoringError, match="640"):
            _check(10, AS_SHIPPED[10])


class TestTheGuardDoesNotRefuseCorrectSpecs:
    """A guard that refuses right answers is worse than no guard: it would have
    blocked the fix as loudly as it blocks the defect."""

    @pytest.mark.parametrize("index", sorted(CORRECT))
    def test_the_narrations_own_spec_passes(self, index):
        _check(index, CORRECT[index])

    def test_scenes_4_and_5_were_ALREADY_right_and_stay_accepted(self):
        """Two of the six were correct. Re-authoring them would have been
        churn, and refusing them would have been a false positive."""
        assert AS_SHIPPED[4] == CORRECT[4]
        assert AS_SHIPPED[5] == CORRECT[5]
        _check(4, AS_SHIPPED[4])
        _check(5, AS_SHIPPED[5])


class TestWhatTheGuardCanAndCannotSee:
    """⛔ Stated as tests so the limit is not mistaken for a checker."""

    def test_it_is_not_an_arithmetic_checker_only_a_contradiction_detector(self):
        """A spec whose numbers are all spoken and whose results are never
        announced passes — because nothing in the words contradicts it. That is
        the honest limit: WP62-L7's checker is human eyes until M3.3."""
        silent = "Now we multiply the next column, carefully and slowly."
        verify_spec_against_narration(
            {"template": "column_multiplication_step",
             "top": 23, "bottom": 14, "step": 0},
            silent, context_text=CONTEXT, scene_index=99,
        )

    def test_an_operand_spoken_NOWHERE_is_refused_as_invented(self):
        with pytest.raises(MotionAuthoringError, match="invented"):
            verify_spec_against_narration(
                {"template": "column_addition_carry", "top": 77, "bottom": 88},
                "Then we add them together to get the answer.",
                context_text=CONTEXT, scene_index=99,
            )

    def test_an_operand_spoken_only_by_a_NEIGHBOUR_is_accepted(self):
        """Scene 10 never says 32 or 21; scene 8 does. Requiring the scene's own
        words would refuse the only correct spec it can have."""
        assert 32 not in narration_numbers(NARR[10])
        assert 21 not in narration_numbers(NARR[10])
        _check(10, CORRECT[10])


class TestProducibleNumbersMatchesTheRenderersArithmetic:
    """The guard's numbers are derived, not restated. If these drift from
    `shared.motion.templates`, the guard is checking a fiction."""

    def test_the_ones_row_of_23x14_produces_92(self):
        out = producible_numbers(CORRECT[3])
        assert 92 in out and 230 not in out

    def test_the_tens_row_of_23x14_produces_230_with_its_placeholder_shift(self):
        out = producible_numbers(CORRECT[5])
        assert 230 in out

    def test_the_tens_row_of_32x21_produces_640(self):
        out = producible_numbers(CORRECT[10])
        assert 640 in out

    def test_addition_produces_its_total(self):
        assert 322 in producible_numbers(CORRECT[7])

    def test_numbers_are_whole_words_not_substrings(self):
        """"322" must not also yield 32 or 22, or the ceiling test would accept
        a spec that merely reaches a fragment of the spoken number."""
        assert narration_numbers("our final answer is 322") == {322}
