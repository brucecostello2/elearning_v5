"""WP-IVGS-12i3 — the three exits, the invariant, and the widened vocabulary.

The operator's principle of 2026-08-30, which this suite exists to pin:

    a correctly completed storyboard stage arrives at the gate with ZERO
    mechanical refusals — only judgment flags.

and its amendment, which governs HOW that is reached:

    CONTENT MUST NOT BE LOST — dilution to pass validation is a worse defect
    than a refusal.

Ruled exit order: **(a)** author the whole scene as motion_graphics; **(c)**
split where the narration mixes content and context; **(b)** redescribe ONLY
where the text demand is incidental. A scene surviving all three fails the
stage — never dilute to green.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene

OUTCOMES = [{"id": "LO-1", "text": "learn how to multiply two double digit numbers"}]

#: The operator's own opener: a warm welcome to an anxious nine-year-old AND a
#: worked operand. The canonical exit-(c) shape.
MIXED = (
    "Hi! Today, we're going to learn how to multiply two-digit numbers. "
    "That might sound tricky, but don't worry. "
    "By the end, you'll be able to solve a problem like 23 times 14 all by "
    "yourself."
)


# ===========================================================================
# RC-T3 — the guard's vocabulary, measured against the Foundation
# ===========================================================================

class TestPlaceValueVocabulary:
    """⛳ WIDEN WHERE FOUNDATION-GENERAL, REFUSE WHERE SCRIPT-SPECIFIC."""

    def _accepts(self, narration: str) -> bool:
        from app.services.motion_authoring import _PLACE_WORDS
        words = narration.lower()
        return any(w in words for w in _PLACE_WORDS)

    def test_the_operators_place_value_question_is_now_accepted(self):
        """Scenes 9/10: "identify the unit numbers and 10's in the number 45".

        A place-value question in the operator's own words, refused before this
        package because the guard wanted the token "place" beside the place's
        name. Foundation §3, the Gagné event-3 row, names these places itself:
        *"ones/tens place value; single-digit facts"*.
        """
        assert self._accepts(
            "Can you identify the unit numbers and 10's in the number 45?"
        )

    def test_an_objective_scene_is_still_refused(self):
        """⛔ THE REFUSAL THAT MUST SURVIVE THE WIDENING.

        Scene 1 — "Today we will learn how to multiply two double-digit
        numbers" — has no place-value content at all. The model reaching for
        `place_value_split` there is simply wrong, and a lexicon wide enough to
        rescue it would be the tuning this order forbids. It goes to exit (b).
        """
        assert not self._accepts(
            "Today we will learn how to multiply two double-digit numbers."
        )

    def test_the_terms_refused_on_purpose_are_absent(self):
        """⛔ "digit" and "number" would make the check satisfied by everything.

        A necessary condition that every arithmetic narration meets is not a
        check. Script literals are refused for the same reason in reverse.
        """
        from app.services.motion_authoring import _PLACE_WORDS
        for word in ("digit", "digits", "number", "numbers", "45", "10's",
                     "hundreds", "thousands"):
            assert word not in _PLACE_WORDS, word

    def test_the_foundation_line_the_widening_cites_still_says_it(self):
        """⛔ THE CITATION IS CHECKED, NOT ASSERTED. If the Foundation is
        rewritten, the justification for this lexicon has to be revisited."""
        from pathlib import Path
        foundation = (
            Path(__file__).resolve().parents[2]
            / "dev" / "design"
            / "Instructional_Design_Foundation_for_IVGS_2026-08-29.md"
        )
        assert "ones/tens place value" in foundation.read_text()


# ===========================================================================
# RC-T1(b) — redescription, and the narrowing that governs it
# ===========================================================================

class TestRedescriptionLegality:
    """⛔ THE AMENDMENT'S TEETH. Decided from the contract, before any call."""

    def test_a_content_scene_over_digit_narration_may_NOT_be_redescribed(self):
        from app.services.visual_redescribe import redescription_is_legal
        for event in ("present", "guide", "practice", "assess"):
            legal, why = redescription_is_legal(
                instructional_event=event,
                narration_text="Multiply 4 times 3 and write the 2 underneath.",
                media_rationale=None,
            )
            assert not legal, event
            assert "IS the content" in why or "dilution" in why

    def test_an_incidental_demand_on_a_staging_scene_may_be_redescribed(self):
        """Scene 1's shape: an `objective` scene whose narration states no
        written or numeric content, whose DESCRIPTION happened to ask for a
        'multiplication problem' on a whiteboard."""
        from app.services.visual_redescribe import redescription_is_legal
        legal, why = redescription_is_legal(
            instructional_event="objective",
            narration_text="Today we will learn how to multiply two double-digit numbers.",
            media_rationale="Sets up the lesson.",
        )
        assert legal
        assert "incidental" in why

    def test_a_rationale_that_says_the_learner_must_SEE_it_forbids_it(self):
        """If the designer wrote it down, it is not incidental."""
        from app.services.visual_redescribe import redescription_is_legal
        legal, why = redescription_is_legal(
            instructional_event="hook",
            narration_text="Here is what we are going to do.",
            media_rationale="The learner must see the worked example on screen.",
        )
        assert not legal
        assert "media_rationale" in why


class TestRedescriptionPostCheck:
    """⛔ THE MODEL IS NEVER TRUSTED TO HAVE COMPLIED. COMPLIANCE IS MEASURED."""

    def test_the_post_check_uses_the_extractor_that_produced_the_refusal(self):
        from app.services.visual_redescribe import surviving_demands
        assert surviving_demands(
            "A worksheet showing the problem 23 x 14 and the calculations"
        )
        assert surviving_demands("the numbers written in the margin")
        assert surviving_demands(
            "A ruled working surface with the units column and the tens column "
            "marked, the answer row still empty"
        ) == []

    async def test_a_non_compliant_redescription_is_DISCARDED_not_retried(
        self, db_session, model_store_project, monkeypatch
    ):
        """⛔ ONE CALL, NO RETRY. The check, not a second attempt, is what makes
        a bounded call safe."""
        from app.services import adaptation_service
        from app.services.visual_redescribe import (
            RedescribeRefused, redescribe_scene,
        )

        calls = []

        async def _fake(prompt, **kwargs):
            calls.append(kwargs.get("response_format"))
            return {"content": '{"visual_description": "A worksheet with 23 x 14 on it"}'}

        async def _binding(db, pid):
            return {"endpoint": "http://x", "model": "m", "binding": "b"}

        monkeypatch.setattr(adaptation_service, "_call_model", _fake)
        monkeypatch.setattr(adaptation_service, "_resolve_binding", _binding)

        with pytest.raises(RedescribeRefused) as exc:
            await redescribe_scene(
                db_session, project_id=model_store_project.id,
                narration="Here is the lesson.",
                visual_description="A whiteboard with the multiplication problem.",
                scene_index=1,
            )
        assert "STILL asks for on-screen text" in str(exc.value)
        assert len(calls) == 1, "exactly one call — a retry would be a loop"
        assert calls[0]["type"] == "json_schema", (
            "RC-Q1: guided_json is accepted with HTTP 200 and silently ignored "
            "on this fleet; json_schema is the mechanism of record"
        )
        assert calls[0]["json_schema"]["strict"] is True


# ===========================================================================
# RC-T1(c) — the split
# ===========================================================================

class TestScenePartition:

    def test_the_operators_opener_partitions_at_the_digit_sentence(self):
        from app.services.scene_split import partition_narration
        part = partition_narration(MIXED)
        assert part.is_mixed
        # "Hi!" is its own sentence: four in total, three of them context.
        assert len(part.context_sentences) == 3
        assert part.digit_sentences == [
            "By the end, you'll be able to solve a problem like 23 times 14 "
            "all by yourself."
        ]

    def test_no_word_is_lost_or_altered_by_the_partition(self):
        """⛔ THE PROMISE OF EXIT (c): it MOVES sentences, it never edits them."""
        from app.services.scene_split import partition_narration, sentences
        part = partition_narration(MIXED)
        assert sorted(part.context_sentences + part.digit_sentences) == sorted(
            sentences(MIXED)
        )

    def test_an_all_digit_or_all_context_scene_is_not_splittable(self):
        """Splitting either would manufacture an empty scene."""
        from app.services.scene_split import partition_narration
        assert not partition_narration("Multiply 4 times 3 and write 12.").is_mixed
        assert not partition_narration("Great job, you have finished!").is_mixed

    def test_durations_split_proportionally_and_sum_to_the_parent(self):
        from app.services.scene_split import partition_narration, split_durations
        part = partition_narration(MIXED)
        context, digit = split_durations(30.0, part)
        assert round(context + digit, 2) == 30.0
        assert context > digit, "two sentences of context, one of digits"

    def test_a_split_assess_keeps_assess_on_ONE_child_only(self):
        """⛔ RC-S1's INVARIANT MUST SURVIVE A SPLIT. Putting `assess` on both
        children would re-create OUTCOME_ASSESSED_TWICE from inside the repair."""
        from app.services.scene_split import child_events
        assert child_events("assess") == ("guide", "assess")
        assert child_events("guide") == ("guide", "guide")
        assert child_events("hook") == ("hook", "hook")


# ===========================================================================
# RC-T2 — the stage-complete invariant
# ===========================================================================

class TestStageCompleteInvariant:

    def _pass(self, **kw):
        from app.services.storyboard_repair import RepairPass
        base = dict(
            ran_at="now", scenes=3, refusals_before=1, refusals_after=0,
            mechanical_before=1, judgment_before=0, repaired=1,
            repair_refused=0, coverage_before=100, coverage_after=100,
            mechanical_after=0,
        )
        base.update(kw)
        return RepairPass(**base)

    def test_a_clean_pass_is_approvable(self):
        assert self._pass().stage_failure() is None

    def test_a_surviving_mechanical_refusal_fails_the_stage(self):
        from app.services.storyboard_repair import Correction
        result = self._pass(
            refusals_after=1, mechanical_after=1, repaired=0, repair_refused=1,
            survivors=[{
                "scene_index": 4,
                "code": "VISUAL_DEMANDS_ON_SCREEN_TEXT",
                "reason": "the visual_description asks for on-screen text",
            }],
            corrections=[Correction(
                scene_index=4, refusal_code="VISUAL_DEMANDS_ON_SCREEN_TEXT",
                refusal_reason="the visual_description asks for on-screen text",
                media_type_was="image", media_type_is="image", applied=False,
                exit_taken="none",
                repair_error="exit (a): no template fits  ||  exit (b): forbidden",
                redescribe_forbidden_because="this is a 'guide' scene",
            )],
        )
        message = result.stage_failure()
        assert message is not None
        assert "STAGE NOT APPROVABLE" in message
        assert "scene 4" in message
        assert "exit (a)" in message and "exit (b)" in message
        assert "this is a 'guide' scene" in message

    def test_a_coverage_DROP_fails_the_stage_even_with_zero_refusals(self):
        """⛔ A REPAIR MAY NOT BUY A CLEAN GATE BY LOSING CONTENT."""
        message = self._pass(coverage_before=1622, coverage_after=1100).stage_failure()
        assert message is not None
        assert "LOWERED script coverage from 1622 to 1100" in message

    def test_coverage_holding_or_rising_is_fine(self):
        assert self._pass(coverage_before=100, coverage_after=100).stage_failure() is None
        assert self._pass(coverage_before=100, coverage_after=140).stage_failure() is None

    def test_the_failure_names_every_scene_it_counts(self):
        """⛔ MEASURED ON THE ACCEPTANCE RUN, AND FIXED.

        The first cut derived survivors from "corrections that did not apply",
        so a scene that still refused but was never a correction's subject was
        COUNTED and not NAMED — the live message read "1 scene(s) survived"
        above an empty list. A message that states a count it cannot name is
        worse than no message. Survivors now come from the re-validation, so the
        count and the names are one fact.
        """
        from app.services.storyboard_repair import RepairPass
        result = RepairPass(
            ran_at="now", scenes=3, refusals_before=1, refusals_after=1,
            mechanical_before=1, judgment_before=0, repaired=1,
            repair_refused=0, coverage_before=40, coverage_after=40,
            mechanical_after=1,
            survivors=[{
                "scene_index": 7,
                "code": "NARRATION_TEXT_UNDECLARED",
                "reason": "the narration's content is written or numeric",
            }],
        )
        message = result.stage_failure()
        assert "1 scene(s) survived" in message
        assert "scene 7 (NARRATION_TEXT_UNDECLARED)" in message
        assert "no exit was attempted for this scene" in message

    def test_the_invariant_is_carried_on_the_wire(self):
        """The orchestrator reads `stage_failure` off the pass's own payload;
        a surface that has to re-derive it will disagree with it."""
        payload = self._pass(
            refusals_after=1, mechanical_after=1,
            survivors=[{"scene_index": 4, "code": "X", "reason": "y"}],
        ).as_dict()
        assert payload["mechanical_after"] == 1
        assert payload["stage_failure"] is not None
        assert payload["coverage_before"] == 100 and payload["coverage_after"] == 100


# ===========================================================================
# the exits in the ruled order, end to end over the database
# ===========================================================================

async def _seed(db_session, project, scenes):
    job = RenderJob(id=uuid.uuid4(), project_id=project.id,
                    job_type="storyboard_generation", status="success")
    db_session.add(job)
    await db_session.flush()
    for spec in scenes:
        db_session.add(StoryboardScene(
            id=uuid.uuid4(), project_id=project.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc), **spec,
        ))
    await db_session.commit()


class TestTheExitsInOrder:

    async def test_a_mixed_scene_SPLITS_rather_than_being_redescribed(
        self, db_session, model_store_project, monkeypatch
    ):
        """⛳ THE AMENDMENT'S CENTRAL CASE, AND THE GUARD IS A CONDITION.

        ⛔ Note what the authoring stub does here: it SUCCEEDS on the whole
        narration. That is the point. On the operator's own opener exit (a)
        genuinely succeeds — the words carry "multiply", 23 and 14 — and would
        render a warm welcome to an anxious nine-year-old as an animated column
        sum. "Where the template fits the WHOLE narration" is the test, and a
        mixed narration fails it, so the split runs FIRST rather than as a
        fallback. This test fails if a future refactor makes (c) a fallback
        again.
        """
        from sqlalchemy import select
        from app.services import adaptation_service, motion_authoring
        from app.services.design_brief_service import DesignBriefService
        from app.services.storyboard_repair import auto_repair_storyboard

        attempts = []

        async def _author(db, **kwargs):
            attempts.append(kwargs.get("narration"))
            return {"template": "column_multiplication_step",
                    "top": 23, "bottom": 14, "step": 0, "phase": "start"}

        async def _binding(db, pid):
            return {"endpoint": "http://x", "model": "m", "binding": "b"}

        async def _redescribe(prompt, **kwargs):
            return {"content": '{"visual_description": "A teacher beside a '
                               'ruled working surface, the answer row still '
                               'empty"}'}

        monkeypatch.setattr(motion_authoring, "author_params_for_scene", _author)
        monkeypatch.setattr(adaptation_service, "_resolve_binding", _binding)
        monkeypatch.setattr(adaptation_service, "_call_model", _redescribe)

        await _seed(db_session, model_store_project, [
            dict(scene_index=0, media_type="image", narration_text=MIXED,
                 visual_description="A teacher beside a whiteboard showing the "
                                    "multiplication problem",
                 instructional_event="hook", serves_outcomes=["LO-1"],
                 media_rationale="opens the lesson", scene_origin="sourced",
                 source_refs=[{"start": 0, "end": 200}], duration_seconds=30.0),
            dict(scene_index=1, media_type="image",
                 narration_text="Great job, you have finished.",
                 visual_description="a child smiling", duration_seconds=5.0,
                 instructional_event="transfer", serves_outcomes=["LO-1"],
                 media_rationale="closes", scene_origin="sourced",
                 source_refs=[{"start": 200, "end": 260}]),
        ])
        await DesignBriefService(db_session).record(
            model_store_project.id,
            {"contract_version": "design-contract-7", "scenes": [
                {"scene_index": 0, "instructional_event": "hook",
                 "serves_outcomes": ["LO-1"], "scene_origin": "sourced",
                 "source_refs": [{"start": 0, "end": 200}]},
                {"scene_index": 1, "instructional_event": "transfer",
                 "serves_outcomes": ["LO-1"], "scene_origin": "sourced"},
            ]},
        )

        result = await auto_repair_storyboard(
            db_session, model_store_project.id, model_store_project)

        # The split, then the context parent's leftover text demand — the
        # description said "showing the multiplication problem" and the split
        # does not touch descriptions.
        assert [x.exit_taken for x in result.corrections] == ["c", "b"]
        c = result.corrections[0]
        assert c.exit_taken == "c", (
            "a mixed narration goes to the split even though exit (a) would "
            "have succeeded — animating the welcome is the defect, not the fix"
        )
        assert attempts == [
            "By the end, you'll be able to solve a problem like 23 times 14 "
            "all by yourself."
        ], "the authoring call saw ONLY the digit half"
        assert c.applied is True
        assert c.split_into == [0, 1]

        rows = list((await db_session.scalars(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == model_store_project.id)
            .order_by(StoryboardScene.scene_index))).all())
        assert [r.scene_index for r in rows] == [0, 1, 2], "the tail shifted up"
        parent, child, tail = rows
        assert "don't worry" in parent.narration_text
        assert "23 times 14" in child.narration_text
        assert child.media_type == "motion_graphics"
        assert child.generation_params["template"] == "column_multiplication_step"
        assert tail.narration_text == "Great job, you have finished."

        # ⛳ the spans reunite, which is why coverage cannot fall — and the
        # child is `sourced` like its parent, because a split MOVES sentences
        # rather than writing them (migration 0048's XOR caught the first cut).
        assert child.scene_origin == parent.scene_origin == "sourced"
        assert child.source_refs == parent.source_refs == [{"start": 0, "end": 200}]
        assert round((parent.duration_seconds or 0) + (child.duration_seconds or 0), 2) == 30.0

        # ⛔ and the child is in the DESIGN OF RECORD, or RC-S1's prune eats it
        brief = await DesignBriefService(db_session).get_active(model_store_project.id)
        indices = sorted(d["scene_index"] for d in brief.scene_designs)
        assert indices == [0, 1, 2]

    async def test_a_split_child_survives_the_surplus_prune(
        self, db_session, model_store_project, monkeypatch
    ):
        """⛔ THE INTERACTION THAT WOULD HAVE UNDONE EXIT (c) SILENTLY.

        `prune_scenes_not_in_design` deletes every row the active contract does
        not contain. A split child that was not written into the contract would
        be deleted by the very next pass, and the repair would appear to have
        worked once and then quietly reverted.
        """
        from sqlalchemy import select
        from app.services import motion_authoring
        from app.services.design_brief_service import DesignBriefService
        from app.services.storyboard_repair import (
            auto_repair_storyboard, prune_scenes_not_in_design,
        )

        async def _author(db, **kwargs):
            return {"template": "column_multiplication_step",
                    "top": 23, "bottom": 14, "step": 0, "phase": "start"}

        monkeypatch.setattr(motion_authoring, "author_params_for_scene", _author)
        await _seed(db_session, model_store_project, [
            dict(scene_index=0, media_type="image", narration_text=MIXED,
                 visual_description="A teacher beside a whiteboard showing the "
                                    "multiplication problem",
                 instructional_event="hook", serves_outcomes=["LO-1"],
                 media_rationale="opens", scene_origin="sourced",
                 source_refs=[{"start": 0, "end": 200}],
                 duration_seconds=30.0),
        ])
        await DesignBriefService(db_session).record(
            model_store_project.id,
            {"contract_version": "design-contract-7", "scenes": [
                {"scene_index": 0, "instructional_event": "hook",
                 "serves_outcomes": ["LO-1"], "scene_origin": "sourced"}]},
        )
        await auto_repair_storyboard(
            db_session, model_store_project.id, model_store_project)

        pruned, skipped = await prune_scenes_not_in_design(
            db_session, model_store_project.id)
        assert pruned == [] and skipped is None
        rows = list((await db_session.scalars(
            select(StoryboardScene).where(
                StoryboardScene.project_id == model_store_project.id))).all())
        assert len(rows) == 2, "the split child survived the prune"

    async def test_a_content_scene_that_cannot_split_is_NOT_diluted(
        self, db_session, model_store_project, monkeypatch
    ):
        """⛔ THE WHOLE POINT OF THE AMENDMENT. An all-digit `guide` scene that
        exit (a) refuses is NOT redescribed into something that validates — it
        survives, and the stage fails."""
        from app.services import motion_authoring
        from app.services.storyboard_repair import auto_repair_storyboard

        async def _author(db, **kwargs):
            raise motion_authoring.MotionAuthoringError("no template fits")

        monkeypatch.setattr(motion_authoring, "author_params_for_scene", _author)
        await _seed(db_session, model_store_project, [
            dict(scene_index=0, media_type="image",
                 narration_text="Multiply 4 times 3 and write the 2 underneath.",
                 visual_description="A worksheet showing the problem 23 x 14",
                 instructional_event="guide", serves_outcomes=["LO-1"],
                 media_rationale="shows the step", scene_origin="sourced",
                 source_refs=[{"start": 0, "end": 60}],
                 text_carried_by="narration", duration_seconds=5.0),
        ])
        result = await auto_repair_storyboard(
            db_session, model_store_project.id, model_store_project)

        (c,) = result.corrections
        assert c.applied is False
        assert c.exit_taken == "none"
        assert c.redescribe_forbidden_because
        assert "IS the content" in c.redescribe_forbidden_because
        assert result.mechanical_after == 1
        assert result.stage_failure() is not None

    async def test_the_context_parent_is_repaired_too_after_a_split(
        self, db_session, model_store_project, monkeypatch
    ):
        """⛔ MEASURED ON THE ACCEPTANCE RUN AND FIXED.

        A split moves the digits out of the NARRATION and leaves the
        DESCRIPTION exactly as it was. Scene 6 of the acceptance storyboard
        narrated *"Do not worry, this is easier than it looks. Now multiply 4
        times 3…"* under *"A worksheet showing the multiplication problem and
        the calculations."* — so after a perfectly good split the parent went on
        refusing and the stage failed over a scene the pass had just repaired.

        ⛳ Re-examining the parent is NOT a retry: its narration changed, and the
        legality test now reads a context-only narration, which is exactly the
        case where a leftover text demand is incidental. One further call, at
        most, and never the same call twice.
        """
        from sqlalchemy import select
        from app.services import adaptation_service, motion_authoring
        from app.services.design_brief_service import DesignBriefService
        from app.services.storyboard_repair import auto_repair_storyboard

        async def _author(db, **kwargs):
            return {"template": "column_multiplication_step",
                    "top": 23, "bottom": 14, "step": 0, "phase": "start"}

        async def _binding(db, pid):
            return {"endpoint": "http://x", "model": "m", "binding": "b"}

        async def _redescribe(prompt, **kwargs):
            return {"content": '{"visual_description": "A ruled working surface '
                               'with the units column and the tens column marked, '
                               'the answer row still empty"}'}

        monkeypatch.setattr(motion_authoring, "author_params_for_scene", _author)
        monkeypatch.setattr(adaptation_service, "_resolve_binding", _binding)
        monkeypatch.setattr(adaptation_service, "_call_model", _redescribe)

        await _seed(db_session, model_store_project, [
            dict(scene_index=0, media_type="image",
                 # The operands are in the words: WP-IVGS-09f's guard refuses a
                 # parameter that appears nowhere in the scene's narration, and
                 # this suite runs that guard for real on the digit half.
                 narration_text=(
                     "Do not worry, this is easier than it looks. "
                     "Our problem is 23 times 14. "
                     "Now multiply 4 times 3."
                 ),
                 visual_description=(
                     "A worksheet showing the multiplication problem and the "
                     "calculations."
                 ),
                 instructional_event="guide", serves_outcomes=["LO-1"],
                 media_rationale="shows the step", scene_origin="sourced",
                 source_refs=[{"start": 0, "end": 120}], duration_seconds=20.0),
        ])
        await DesignBriefService(db_session).record(
            model_store_project.id,
            {"contract_version": "design-contract-7", "scenes": [
                {"scene_index": 0, "instructional_event": "guide",
                 "serves_outcomes": ["LO-1"], "scene_origin": "sourced",
                 "source_refs": [{"start": 0, "end": 120}]}]},
        )

        result = await auto_repair_storyboard(
            db_session, model_store_project.id, model_store_project)

        exits = [c.exit_taken for c in result.corrections]
        assert exits == ["c", "b"], (
            "the split first, then the context parent's leftover text demand"
        )
        assert result.mechanical_after == 0, "the stage is approvable"
        assert result.stage_failure() is None

        rows = list((await db_session.scalars(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == model_store_project.id)
            .order_by(StoryboardScene.scene_index))).all())
        parent, child = rows
        assert "multiplication problem" not in (parent.visual_description or "")
        assert child.media_type == "motion_graphics"
        assert round((parent.duration_seconds or 0) + (child.duration_seconds or 0), 2) == 20.0
