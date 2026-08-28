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
        literal so the escaping cannot be lost again."""
        prompt = build_prompt(
            narration="n", visual_description="v", project_name="p",
            project_description="d",
        )
        assert '{"top": 23, "bottom": 14, "step": 0}' in prompt
        assert '{"top": 14, "bottom": 3}' in prompt

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
        arithmetic until M3.3, so a convenient number is a taught mistake."""
        prompt = build_prompt(
            narration="n", visual_description="v", project_name="p",
            project_description="d",
        )
        assert "NUMBERS MUST BE THE ONES THIS LESSON ACTUALLY USES" in prompt


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
