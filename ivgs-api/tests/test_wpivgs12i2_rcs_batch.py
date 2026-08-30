"""WP-IVGS-12i2 — the RC-S batch: stale rows, fidelity, arithmetic, duplication.

Four defects the operator's second watch found on one regenerated design, and
the checks that would have caught each. Every number quoted here was measured on
the live project `680d9e4c` read-only, 2026-08-30, and is reproduced as a fixture
so a regression fails here rather than at a gate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene

OUTCOMES = [
    {"id": "LO-1", "text": "learn how to multiply two double digit numbers"},
    {"id": "LO-2", "text": "learn the difference between unit numbers and 10's"},
    {"id": "LO-3", "text": "be able to manually multiply, unsupervised"},
]


def _scene(oid, event, narration, index, origin="designed", **extra):
    base = dict(
        scene_index=index,
        instructional_event=event,
        serves_outcomes=[oid],
        narration_text=narration,
        visual_description="the working surface, part done",
        media_type="image",
        scene_origin=origin,
        media_rationale="because",
        # These narrations quote real operands, so without the carrier
        # declaration every one of them is a `NARRATION_TEXT_UNDECLARED`
        # refusal and the repair pass would reach for an authoring call. This
        # suite is about the prune, the spans, the arithmetic and the
        # duplicates; RC-R4's own suite covers the repair.
        text_carried_by="narration",
    )
    base.update(extra)
    return base


# ===========================================================================
# RC-S4 — the equation lint
# ===========================================================================

class TestEquationLint:
    """⛳ THE OPERATOR'S CATCH. Nothing in this pipeline has ever asked whether
    what a scene says about mathematics is TRUE."""

    def test_a_complete_true_claim_passes(self):
        from shared.design.equations import false_claims
        for text in ("4 times 3 equals 12", "23 x 14 = 322", "9 plus 3 is 12",
                     "23 times 10 equals 230", "32 plus 640 equals 672"):
            assert false_claims(text) == [], text

    def test_a_complete_false_claim_is_caught(self):
        from shared.design.equations import false_claims
        (bad,) = false_claims("Now multiply 4 times 3. 4 times 3 equals 13.")
        assert bad.left == 4 and bad.right == 3
        assert bad.stated == 13 and bad.computed == 12
        assert "is 12, not 13" in str(bad)

    def test_an_incomplete_statement_is_never_a_claim(self):
        """⛔ THE PROPERTY THAT MAKES THIS SAFE TO HARD-REFUSE.

        A check that guesses at what a half-sentence asserts would refuse sound
        designs. Every one of these is ordinary, correct narration from the
        operator's own script.
        """
        from shared.design.equations import parse_claims
        for text in (
            "Now multiply 4 times 3.",
            "Write the 2 underneath and carry the 1.",
            "Our problem is 23 times 14.",
            "Multiply 34 by 21.",
            "Our first answer is 92.",
            "Now it's your turn to try.",
        ):
            assert parse_claims(text) == [], text

    def test_the_method_prose_half_is_NOT_caught_and_that_is_declared(self):
        """⛔ SCENE 4 OF THE OPERATOR'S OWN REGENERATED DESIGN.

        "To multiply two double-digit numbers, we need to multiply the tens and
        the units separately" is the classic misconception taught as method —
        a learner computes 23x14 as 20x10 + 3x4 = 212. It contains no numerals
        and states no equation, so it is NOT deterministically lintable, and
        this test pins that limitation so nobody reads the presence of an
        arithmetic check as a guarantee that the maths was checked.

        That half stays at the human gate until the L7 checker (M3.3). RC-S2's
        fidelity rule is its primary guard: a design anchored to a correct
        script cannot state a wrong method.
        """
        from shared.design.equations import parse_claims
        assert parse_claims(
            "To multiply two double-digit numbers, we need to multiply the "
            "tens and the units separately."
        ) == []

    def test_the_operators_whole_script_passes_clean(self):
        """CALIBRATION, and the number is the point.

        ⛳ The operator's real 3,138-character upload was measured 2026-08-30
        and carries **17 complete arithmetic claims, all 17 true** — the lint
        passes a correct script cleanly, which is the half of the calibration
        that matters most for a hard refusal. The fixture below is that script
        with its repeated sentences collapsed, so it carries 15 of the 17; the
        banked evidence holds the full measurement.
        """
        from shared.design.equations import parse_claims, false_claims
        script = (
            "First, multiply 4 times 3. 4 times 3 equals 12. "
            "Now multiply 4 times 2. 4 times 2 equals 8. 8 plus 1 equals 9. "
            "23 times 4 equals 92. 1 times 3 equals 3. 1 times 2 equals 2. "
            "23 times 10 equals 230. 2 plus 0 equals 2. 9 plus 3 equals 12. "
            "1 plus 2 equals 3. 23 times 14 equals 322. "
            "2 times 2 equals 4. 2 times 3 equals 6. 32 plus 640 equals 672. "
            "32 times 21 equals 672."
        )
        assert len(parse_claims(script)) == 15
        assert false_claims(script) == []

    def test_the_gate_hard_refuses_a_false_claim_naming_scene_and_claim(self):
        from app.services.design_review import review, split
        scenes = [
            _scene("LO-1", "guide", "First, multiply 4 times 3. 4 times 3 equals 13.", 0),
            _scene("LO-1", "practice", "Try 12 times 11 on your own.", 1),
            _scene("LO-1", "assess", "Multiply 56 by 23 with a pencil.", 2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        refusals, _ = split(findings)
        bad = next(f for f in refusals if f.code == "NARRATION_ARITHMETIC_FALSE")
        assert bad.scene_index == 0
        assert "4 times 3 equals 13" in bad.message
        assert bad.detail["claim"]["computed"] == 12

    def test_a_motion_scenes_template_numbers_are_quoted_in_the_refusal(self):
        """The renderer's numbers beside the false sentence — evidence, not a
        second rule: producibility is `verify_spec_against_narration`'s job."""
        from app.services.design_review import review, split
        scenes = [
            _scene("LO-1", "guide", "4 times 3 equals 13.", 0,
                   media_type="motion_graphics",
                   generation_params={"template": "column_multiplication_step",
                                      "top": 23, "bottom": 14, "step": 0,
                                      "phase": "full"}),
            _scene("LO-1", "practice", "Try 12 times 11.", 1),
            _scene("LO-1", "assess", "Multiply 56 by 23.", 2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        refusals, _ = split(findings)
        bad = next(f for f in refusals if f.code == "NARRATION_ARITHMETIC_FALSE")
        assert bad.detail["template_operands"] == [23, 14]
        assert "draws [23, 14]" in bad.message


# ===========================================================================
# RC-S2(a) — the fidelity loophole
# ===========================================================================

class TestFidelitySpanRule:
    """⛔ ONE THROWAWAY DECLARED DROP USED TO DEFEAT THE WHOLE CHECK."""

    SCRIPT = ("A" * 200) + (" beat two. " * 40) + ("B" * 2800)

    def _design(self, refs, drops):
        return [dict(_scene("LO-1", "guide", "Some narration.", 0),
                     source_refs=refs)], drops

    def test_an_undeclared_span_refuses_even_when_other_drops_exist(self):
        """THE LOOPHOLE, CLOSED. The old rule was `gap >= 400 AND
        dropped_beats empty`, and the second clause is GLOBAL where the first
        is PER-SPAN — so one drop anywhere made every hole soft."""
        from app.services.design_review import review, split
        scenes, drops = self._design(
            refs=[{"start": 0, "end": 200}],
            drops=[{"span": {"start": 0, "end": 200}, "summary": "x",
                    "reason": "a throwaway drop, declared elsewhere"}],
        )
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]],
                             source_text=self.SCRIPT, dropped_beats=drops)
        refusals, _ = split(findings)
        gap = next(f for f in refusals if f.code == "UNDECLARED_SPAN_OVER_THRESHOLD")
        assert "covered by no declared drop" in gap.message
        assert "1 beat(s) are declared dropped elsewhere" in gap.message

    def test_a_span_a_drop_actually_covers_does_not_refuse(self):
        """⛳ AND IT NEEDED NO NEW BOOKKEEPING: a drop's span is already merged
        into the coverage, so a stretch that survives as a gap is by
        construction one that no drop declared."""
        from app.services.design_review import review, split
        scenes, drops = self._design(
            refs=[{"start": 0, "end": 640}],
            drops=[{"span": {"start": 640, "end": len(self.SCRIPT)},
                    "summary": "the tail", "reason": "out of scope for v1"}],
        )
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]],
                             source_text=self.SCRIPT, dropped_beats=drops)
        refusals, _ = split(findings)
        assert not [f for f in refusals if f.code == "UNDECLARED_SPAN_OVER_THRESHOLD"]

    def test_connective_tissue_below_the_threshold_still_only_flags(self):
        from app.services.design_review import review, split
        script = "x" * 1000
        scenes = [dict(_scene("LO-1", "guide", "n", 0),
                       source_refs=[{"start": 0, "end": 700},
                                    {"start": 900, "end": 1000}])]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]],
                             source_text=script, dropped_beats=[])
        refusals, flags = split(findings)
        assert not [f for f in refusals if f.code == "UNDECLARED_SPAN_OVER_THRESHOLD"]
        assert [f for f in flags if f.code == "UNDECLARED_SCRIPT_GAP"]

    def test_both_live_designs_refuse_under_the_new_rule(self):
        """CALIBRATION AGAINST BOTH LIVE DESIGNS, as the order requires.

        WATCH-1 covered 1,622 of 3,138 chars (51.7%) with 2 drops declared and
        left the script's whole "Step 4: Add the Two Answers" section — 1,473
        chars — uncovered. WATCH-2's regen covered 110 (3.5%) with 1 drop and
        left 2,968 uncovered. **Old rule: zero refusals for both. New rule:
        both refuse**, and both correctly — a 1,473-character teaching section
        nobody used and nobody declared is a lost beat whether or not some
        other beat was declared.
        """
        from app.services.design_review import review, split
        script = "s" * 3138
        for covered_to, drops, gap in ((1622, 2, 1516), (110, 1, 3028)):
            scenes = [dict(_scene("LO-1", "guide", "n", 0),
                           source_refs=[{"start": 0, "end": covered_to}])]
            beats = [{"span": {"start": 0, "end": 10}, "summary": "s",
                      "reason": "r"} for _ in range(drops)]
            findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]],
                                 source_text=script, dropped_beats=beats)
            refusals, _ = split(findings)
            hit = [f for f in refusals if f.code == "UNDECLARED_SPAN_OVER_THRESHOLD"]
            assert hit, f"coverage to {covered_to} must refuse"
            assert hit[0].detail["end"] - hit[0].detail["start"] == gap


# ===========================================================================
# RC-S3 — the same-outcome duplicate belt, widened
# ===========================================================================

class TestSameOutcomeDuplicates:

    def test_the_live_guide_practice_pair_flags(self):
        """⛔ THE MUST-FLAG CASE, FROM THE OPERATOR'S REGENERATED DESIGN.

        LO-2's `guide` scene 10 and `practice` scene 11 carry byte-identical
        narration. Neither is an `assess`, so the 12h belt could not see them.
        """
        from app.services.design_review import review, split
        text = "Can you identify the units and tens in the number 45?"
        scenes = [
            _scene("LO-2", "guide", text, 10),
            _scene("LO-2", "practice", text, 11),
            _scene("LO-2", "assess",
                   "Explain why 93 has a 9 in the tens place.", 12),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[1]])
        refusals, flags = split(findings)
        dup = next(f for f in flags if f.code == "SAME_OUTCOME_NEAR_DUPLICATE")
        assert dup.detail["scene_indices"] == [10, 11]
        assert dup.detail["events"] == ["guide", "practice"]
        assert not [f for f in refusals if f.code == "SAME_OUTCOME_NEAR_DUPLICATE"], (
            "flag-level elsewhere — hard only where 12h's ruling made it hard"
        )

    def test_the_assessment_limb_stays_hard_and_is_not_double_reported(self):
        """⛔ ONE COMPLAINT PER SENTENCE. A flag beside a refusal about the
        same two scenes leaves a reviewer to work out which to fix."""
        from app.services.design_review import review, split
        text = "Multiply 43 by 25 using the standard column algorithm."
        scenes = [
            _scene("LO-1", "guide", "Here is how we set out 23 times 14.", 0),
            _scene("LO-1", "practice", text, 1),
            _scene("LO-1", "assess", text, 2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        refusals, flags = split(findings)
        assert [f for f in refusals if f.code == "EVIDENCE_NEAR_DUPLICATE"]
        overlapping = [
            f for f in flags
            if f.code == "SAME_OUTCOME_NEAR_DUPLICATE"
            and set(f.detail["scene_indices"]) == {1, 2}
        ]
        assert overlapping == []

    def test_distinct_scenes_in_one_outcome_are_left_alone(self):
        from app.services.design_review import review, split
        scenes = [
            _scene("LO-1", "guide", "Here is how we set out 23 times 14.", 0),
            _scene("LO-1", "practice", "Now try 56 by 23 with the workspace.", 1),
            _scene("LO-1", "assess", "Multiply 75 and 32 with a pencil.", 2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        _, flags = split(findings)
        assert not [f for f in flags if f.code == "SAME_OUTCOME_NEAR_DUPLICATE"]


# ===========================================================================
# RC-S1 — the stale rows that broke the per-outcome guarantee
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
            updated_at=spec.pop("_updated_at", datetime.now(timezone.utc)),
            **spec,
        ))
    await db_session.commit()


#: The live shape, reduced: a 17-scene design whose rows still carry 18 and 19
#: from the generation before it, one of them an `assess` for LO-3.
def _live_shape():
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    kept = [
        dict(_scene("LO-3", "guide", "Now try multiplying 56 by 23.", 13),
             duration_seconds=5.0),
        dict(_scene("LO-3", "practice", "Now try 56 by 23 on your own.", 14),
             duration_seconds=5.0),
        dict(_scene("LO-3", "assess", "Multiply 75 and 32 using a pencil.", 15),
             duration_seconds=5.0),
    ]
    stale = [
        dict(_scene("LO-3", "practice",
                    "Now it's your turn to try. Multiply 32 and 21.", 17),
             duration_seconds=5.0, _updated_at=old),
        dict(_scene("LO-3", "assess",
                    "Multiply 67 and 39 using a pencil and paper.", 18),
             duration_seconds=5.0, _updated_at=old),
    ]
    return kept, stale


def _designs(kept):
    """The contract entries for the kept scenes.

    ⚠ FULL ENTRIES, NOT BARE INDICES, and the reason is a real behaviour of
    `DesignBriefService.record`: `_clean` seeds every `SCENE_DESIGN_FIELDS` key
    to None, so recording a design that omits `instructional_event` NULLs it on
    the row. A real contract always carries them; a fixture that did not would
    be testing the prune against scenes the brief had just blanked.
    """
    return [
        {
            "scene_index": s["scene_index"],
            "instructional_event": s["instructional_event"],
            "serves_outcomes": s["serves_outcomes"],
            "scene_origin": s["scene_origin"],
        }
        for s in kept
    ]


class TestSurplusRowsFromRegeneration:

    async def test_the_stale_assess_row_is_what_breaks_the_guarantee(
        self, db_session, model_store_project
    ):
        """⛳ THE MECHANISM, PINNED BEFORE THE FIX IS APPLIED.

        Call 2 was innocent: the live contract emitted exactly one `assess` per
        outcome. The database stopped matching the contract.
        """
        from app.services.design_review import review, split
        kept, stale = _live_shape()
        findings, _ = review(scenes=kept + stale, outcomes=[OUTCOMES[2]])
        refusals, _ = split(findings)
        twice = next(f for f in refusals if f.code == "OUTCOME_ASSESSED_TWICE")
        assert twice.detail["assess_scene_indices"] == [15, 18]

    async def test_the_prune_removes_only_rows_outside_the_design_of_record(
        self, db_session, model_store_project
    ):
        from app.services.design_brief_service import DesignBriefService
        from app.services.storyboard_repair import prune_scenes_not_in_design
        from sqlalchemy import select

        kept, stale = _live_shape()
        await _seed(db_session, model_store_project,
                    [dict(s) for s in kept + stale])
        await DesignBriefService(db_session).record(
            model_store_project.id,
            {"contract_version": "design-contract-7",
             "scenes": _designs(kept)},
        )

        pruned, skipped = await prune_scenes_not_in_design(
            db_session, model_store_project.id)
        assert skipped is None
        assert sorted(p.scene_index for p in pruned) == [17, 18]
        assert pruned[1].instructional_event == "assess"
        assert pruned[1].serves_outcomes == ["LO-3"]
        assert pruned[1].narration_text, "the removed row's words are recorded"

        rows = list((await db_session.scalars(
            select(StoryboardScene).where(
                StoryboardScene.project_id == model_store_project.id))).all())
        assert sorted(r.scene_index for r in rows) == [13, 14, 15]

    async def test_per_outcome_assess_is_exactly_one_after_the_prune(
        self, db_session, model_store_project
    ):
        """THE ACCEPTANCE: a regeneration yields per-LO assess == 1."""
        from collections import Counter
        from sqlalchemy import select
        from app.services.design_brief_service import DesignBriefService
        from app.services.design_review import review, split
        from app.services.storyboard_repair import prune_scenes_not_in_design

        kept, stale = _live_shape()
        await _seed(db_session, model_store_project,
                    [dict(s) for s in kept + stale])
        await DesignBriefService(db_session).record(
            model_store_project.id,
            {"contract_version": "design-contract-7",
             "scenes": _designs(kept)},
        )
        await prune_scenes_not_in_design(db_session, model_store_project.id)

        rows = list((await db_session.scalars(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == model_store_project.id)
            .order_by(StoryboardScene.scene_index))).all())
        per_lo = Counter(
            oid for r in rows if r.instructional_event == "assess"
            for oid in (r.serves_outcomes or [])
        )
        assert per_lo == {"LO-3": 1}
        findings, _ = review(scenes=rows, outcomes=[OUTCOMES[2]])
        refusals, _ = split(findings)
        assert not [f for f in refusals if f.code == "OUTCOME_ASSESSED_TWICE"]

    async def test_it_prunes_NOTHING_when_it_cannot_know_the_design(
        self, db_session, model_store_project
    ):
        """⛔ IT REFUSES TO GUESS, and says which of the two silences it is.

        A pre-v8 storyboard has no brief. Trimming it on a scene count would be
        deleting an operator's rows on an assumption.
        """
        from sqlalchemy import select
        from app.services.storyboard_repair import prune_scenes_not_in_design

        kept, stale = _live_shape()
        await _seed(db_session, model_store_project,
                    [dict(s) for s in kept + stale])
        pruned, skipped = await prune_scenes_not_in_design(
            db_session, model_store_project.id)
        assert pruned == []
        assert skipped and "no active design brief" in skipped
        rows = list((await db_session.scalars(
            select(StoryboardScene).where(
                StoryboardScene.project_id == model_store_project.id))).all())
        assert len(rows) == 5, "nothing was deleted"

    async def test_the_prune_is_declared_on_the_brief(
        self, db_session, model_store_project, monkeypatch
    ):
        from app.services import motion_authoring
        from app.services.design_brief_service import DesignBriefService
        from app.services.storyboard_repair import repair_and_declare

        async def _never(db, **kwargs):                      # no scene needs it
            raise AssertionError("no authoring should have been required")
        monkeypatch.setattr(motion_authoring, "author_params_for_scene", _never)

        kept, stale = _live_shape()
        await _seed(db_session, model_store_project,
                    [dict(s) for s in kept + stale])
        await DesignBriefService(db_session).record(
            model_store_project.id,
            {"contract_version": "design-contract-7",
             "scenes": _designs(kept)},
        )
        result = await repair_and_declare(db_session, model_store_project.id,
                                          model_store_project)
        assert [p.scene_index for p in result.pruned] == [17, 18]
        brief = await DesignBriefService(db_session).get_active(
            model_store_project.id)
        declared = brief.system_corrections
        assert [p["scene_index"] for p in declared["pruned"]] == [17, 18]
        assert declared["prune_skipped_because"] is None
        assert declared["pruned"][1]["instructional_event"] == "assess"

    def test_the_flag_does_not_call_either_scene_the_assessment(self):
        """⛔ MEASURED ON THE 12i2 ACCEPTANCE RUN, and fixed.

        This limb first shipped reusing `duplication.explain`, whose sentences
        are written for the assessment-anchored limb and begin "the
        assessment". The live gate then reported *"the assessment restates that
        scene"* about a `guide`/`practice` pair, in which neither scene is an
        assessment. A message that misnames what it is about is a message a
        reviewer cannot act on.
        """
        from app.services.design_review import review, split
        text = "Can you identify the units and tens in the number 45?"
        scenes = [
            _scene("LO-2", "guide", text, 10),
            _scene("LO-2", "practice", text, 11),
            _scene("LO-2", "assess", "Explain why 93 has a 9 in the tens.", 12),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[1]])
        _, flags = split(findings)
        dup = next(f for f in flags if f.code == "SAME_OUTCOME_NEAR_DUPLICATE")
        assert "the assessment" not in dup.message
        assert "restate each other" in dup.message or "same numbers" in dup.message
