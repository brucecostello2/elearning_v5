"""WP-IVGS-12c — every outcome is served AND assessed, structurally or loudly.

RC-Q9b: with RC-Q9 closed by structure, three consecutive generations still
produced 3, 2 and 2 hard refusals, dominated by `OUTCOME_UNASSESSED` — the
designer serves an outcome and no scene ever assesses it — while
`EVIDENCE_MAP_DISAGREES` FLAGGED on nearly every outcome of every generation.
The map claimed evidence the scenes did not support, and the flag let it pass.

The ruling closes it structurally with the belt promoted, and these tests pin
both halves plus the seam between them:

  THE SCHEMA   `evidence_map` requires one key per outcome id holding 1..4
               scene indices. "Nothing assesses this" stops being an emittable
               sentence. Measured enforced on the pinned engine first — see
               `design_core.contract.MIN_EVIDENCE_SCENES` for the verdict table
               and for the whitespace hang the lower bound makes reachable.

  THE BELT     `EVIDENCE_MAP_DISAGREES` is promoted FLAG -> REFUSE. A scene
               named as evidence for LO-x must itself declare LO-x in
               `serves_outcomes` AND an `instructional_event` in
               {practice, assess}.

  THE LIMIT    ⛔ pinned deliberately in `TestWhatThisCannotDo`. A mislabelled
               scene passes both. That is the reviewer's judgment at the gate,
               and a test that pretended otherwise would be the lie.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _contract():
    sys.path.insert(0, str(REPO / "ivgs-workers"))
    from design_core import contract
    return contract


def _scene(idx, **kw):
    base = {
        "scene_index": idx, "serves_outcomes": ["LO-1"],
        "instructional_event": "present", "bloom_level": "apply",
        "scene_origin": "designed", "source_refs": None, "rewrite_of": None,
        "media_type": "image", "media_rationale": "framing",
        "generation_params": None, "narration_text": "One.",
        "signal_spec": None,
    }
    base.update(kw)
    return base


OUTCOME = {"id": "LO-1", "text": "compute the product",
           "measurable": True, "bloom_level": "apply"}


def _codes(findings, severity):
    return sorted({f.code for f in findings if f.severity == severity})


# ---------------------------------------------------------------------------
# (2) THE STRUCTURE — the schema no longer admits "nothing assesses this"
# ---------------------------------------------------------------------------

class TestTheEvidenceMapCannotBeEmpty:
    def test_every_outcome_id_is_a_required_key_holding_at_least_one_scene(self):
        c = _contract()
        ids = ["LO-1", "LO-2", "LO-3"]
        em = c.design_contract_schema(outcome_ids=ids)["properties"]["evidence_map"]
        assert em["required"] == ids
        assert em["additionalProperties"] is False
        for oid in ids:
            arr = em["properties"][oid]
            assert arr["minItems"] == c.MIN_EVIDENCE_SCENES == 1, (
                "the LOWER bound is the load-bearing one: `[]` was the legal "
                "way to say 'nothing assesses this outcome' and it is RC-Q9b"
            )
            assert arr["maxItems"] == c.MAX_EVIDENCE_SCENES == 4

    def test_the_bound_survives_the_no_ids_degradation(self):
        """A project whose operator stated no outcomes has no ids to key by, so
        the object opens. An entry that DOES appear is still bounded — and
        `design_review` carries the whole weight on that path."""
        c = _contract()
        em = c.design_contract_schema(outcome_ids=[])["properties"]["evidence_map"]
        assert "required" not in em
        assert em["additionalProperties"]["minItems"] == 1
        assert em["additionalProperties"]["maxItems"] == 4

    def test_every_array_in_the_contract_is_still_bounded_above(self):
        """RC-Q12's regression guard, re-run over the shape 12c changed. An
        array with no `maxItems` is an infinite legal continuation."""
        c = _contract()

        def unbounded(node, path="$"):
            bad = []
            if isinstance(node, dict):
                if node.get("type") == "array" and "maxItems" not in node:
                    bad.append(path)
                for k, v in node.items():
                    bad += unbounded(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    bad += unbounded(v, f"{path}[{i}]")
            return bad

        for ids in (["LO-1", "LO-2"], []):
            assert unbounded(c.design_contract_schema(outcome_ids=ids)) == []

    def test_the_contract_version_records_the_shape_change(self):
        """The stored brief must say which parse produced it: a contract-2 row
        carries no evidence guarantee and a contract-3 row does."""
        assert _contract().CONTRACT_VERSION == "design-contract-3"

    def test_the_schema_still_carries_no_outcome_text(self):
        """RC-Q9's cure, regression-checked at the new shape. 12c touches the
        evidence map; if outcome TEXT came back with it, the paraphrase comes
        back too and no wording stops it."""
        c = _contract()
        blob = json.dumps(c.design_contract_schema(outcome_ids=["LO-1", "LO-2"]))
        assert '"text"' not in blob


# ---------------------------------------------------------------------------
# (3) THE BELT, PROMOTED — a claim the scenes contradict is now a refusal
# ---------------------------------------------------------------------------

class TestTheBeltIsAHardRefusal:
    def test_an_empty_map_is_refused(self):
        """⛳ CANNOT FIRE WHEN THE SCHEMA ARMED — contract-3 forbids it. It
        fires on the paths the schema does not reach: no stated outcomes, an
        older brief, a row that arrived by another route."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess")],
            outcomes=[OUTCOME], evidence_map={"LO-1": []})
        assert "EVIDENCE_MAP_NAMES_NOTHING" in _codes(findings, "refuse")

    def test_a_missing_map_is_refused(self):
        from app.services.design_review import review
        findings, _ = review(scenes=[_scene(0, instructional_event="assess")],
                             outcomes=[OUTCOME], evidence_map={})
        assert "EVIDENCE_MAP_NAMES_NOTHING" in _codes(findings, "refuse")

    def test_a_named_scene_that_does_not_serve_the_outcome_is_REFUSED(self):
        """Half one of the promoted rule. Scene 1 assesses, but it assesses
        something else — the map points at it anyway."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess"),
                    _scene(1, serves_outcomes=["LO-2"],
                           instructional_event="assess")],
            outcomes=[OUTCOME, {"id": "LO-2", "text": "explain the zero"}],
            evidence_map={"LO-1": [1], "LO-2": [1]})
        bad = [f for f in findings if f.code == "EVIDENCE_MAP_DISAGREES"]
        assert bad and bad[0].severity == "refuse"
        assert bad[0].outcome_id == "LO-1"
        assert bad[0].detail["not_serving"] == [1]

    def test_a_named_scene_that_is_not_an_assessing_event_is_REFUSED(self):
        """Half two. Scene 1 serves LO-1 and the map calls it the evidence, but
        the scene's own event is `present`. Pointing at the nearest scene is
        exactly what the three generations did."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0), _scene(1, instructional_event="present")],
            outcomes=[OUTCOME], evidence_map={"LO-1": [1]})
        bad = [f for f in findings if f.code == "EVIDENCE_MAP_DISAGREES"]
        assert bad and bad[0].severity == "refuse"
        assert bad[0].detail["not_assessing"] == [1]

    def test_the_two_halves_are_reported_separately(self):
        """They have different fixes — one scene is pointed at the wrong
        outcome, the other is labelled the wrong event — so the refusal names
        which, rather than saying 'disagrees' and leaving the reviewer to
        bisect it."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess"),
                    _scene(1, instructional_event="present"),
                    _scene(2, serves_outcomes=["LO-2"],
                           instructional_event="assess")],
            outcomes=[OUTCOME, {"id": "LO-2", "text": "explain the zero"}],
            evidence_map={"LO-1": [1, 2], "LO-2": [2]})
        bad = next(f for f in findings
                   if f.code == "EVIDENCE_MAP_DISAGREES" and f.outcome_id == "LO-1")
        assert bad.detail["not_assessing"] == [1]
        assert bad.detail["not_serving"] == [2]
        assert "serves_outcomes" in bad.message and "instructional_event" in bad.message

    def test_practice_counts_as_evidence_as_well_as_assess(self):
        """{practice, assess} is the operator's set and it is `ASSESSING_EVENTS`
        — one definition, not a second copy in this module."""
        from app.services.design_review import review
        from shared.models.enums import ASSESSING_EVENTS
        assert ASSESSING_EVENTS == {"practice", "assess"}
        findings, rows = review(
            scenes=[_scene(0), _scene(1, instructional_event="practice")],
            outcomes=[OUTCOME], evidence_map={"LO-1": [1]})
        assert "EVIDENCE_MAP_DISAGREES" not in _codes(findings, "refuse")
        assert rows[0].assessed_by == [1]

    def test_a_phantom_scene_is_still_refused_and_is_not_confused_with_disagreement(self):
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess")],
            outcomes=[OUTCOME], evidence_map={"LO-1": [0, 99]})
        assert "EVIDENCE_MAP_PHANTOM_SCENE" in _codes(findings, "refuse")
        assert "EVIDENCE_MAP_DISAGREES" not in _codes(findings, "refuse"), (
            "scene 99 does not exist, so it cannot disagree with itself; "
            "reporting both would make one defect look like two"
        )

    def test_an_agreeing_map_passes_clean(self):
        from app.services.design_review import review, split
        findings, rows = review(
            scenes=[_scene(0, instructional_event="hook"),
                    _scene(1, instructional_event="guide"),
                    _scene(2, instructional_event="assess")],
            outcomes=[OUTCOME], evidence_map={"LO-1": [2]})
        refusals, _ = split(findings)
        assert refusals == [], [f.code for f in refusals]
        assert rows[0].served and rows[0].assessed

    def test_a_non_numeric_entry_does_not_crash_the_gate(self):
        """A stored brief is JSONB. The gate exists to report on a bad brief;
        a gate that 500s on one is no gate."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess")],
            outcomes=[OUTCOME], evidence_map={"LO-1": ["0", None, "x"]})
        assert "EVIDENCE_MAP_DISAGREES" not in _codes(findings, "refuse")
        assert "EVIDENCE_MAP_NAMES_NOTHING" not in _codes(findings, "refuse")


class TestServedAndAssessedIsNowClosed:
    def test_passing_the_belt_with_a_named_scene_implies_the_outcome_is_assessed(self):
        """The seam between (2) and (3), and the reason the pair is complete.

        The map must name a scene (schema). Every named scene must serve the
        outcome AND carry an assessing event (belt). So a design that passes
        both has, for every outcome, at least one scene that serves and
        assesses it — which is exactly what `OUTCOME_UNASSESSED` asks. The two
        refusals cannot both be silent on a design that lacks one.
        """
        from app.services.design_review import review
        scenes = [_scene(0), _scene(1, instructional_event="present")]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOME],
                             evidence_map={"LO-1": [1]})
        refused = _codes(findings, "refuse")
        assert "OUTCOME_UNASSESSED" in refused
        assert "EVIDENCE_MAP_DISAGREES" in refused

        findings, _ = review(
            scenes=[_scene(0), _scene(1, instructional_event="assess")],
            outcomes=[OUTCOME], evidence_map={"LO-1": [1]})
        refused = _codes(findings, "refuse")
        assert "OUTCOME_UNASSESSED" not in refused
        assert "EVIDENCE_MAP_DISAGREES" not in refused

    def test_dropping_an_outcome_is_not_available_to_the_designer(self):
        """⛔ THE OPERATOR'S RULING. Dropping an outcome is an operator act at
        the gate, so there is no `dropped_outcomes` mechanism to build and none
        was built. An outcome the operator typed is served and assessed or the
        design is refused — the designer has no third answer.

        `dropped_beats` is the SCRIPT's drop mechanism and is unrelated: a beat
        is the teacher's material, an outcome is the owner's requirement.
        """
        c = _contract()
        blob = json.dumps(c.design_contract_schema(outcome_ids=["LO-1"]))
        assert "dropped_outcomes" not in blob
        assert "dropped_beats" in blob

        import app.services.design_review as dr
        assert "dropped_outcomes" not in Path(dr.__file__).read_text()

    def test_the_prompt_states_the_rule_the_gate_enforces(self):
        """A model judged on a contract nobody told it about is being tested on
        a secret. The publisher gates these phrases for the same reason."""
        text = (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_design_system.j2").read_text()
        assert "EVERY SCENE YOU NAME IS READ BACK AGAINST ITS OWN TWO DECLARATIONS" in text
        assert "`practice` or `assess`" in text
        assert "names AT LEAST ONE" in text


# ---------------------------------------------------------------------------
# (4) THE HONEST LIMIT — pinned, because it is the residue
# ---------------------------------------------------------------------------

class TestWhatThisCannotDo:
    def test_a_mislabelled_scene_passes_both_checks(self):
        """⛔ THE RESIDUE, RC-P14-class, and it is here on purpose.

        Scene 1 is a recap. Its narration says so. It is labelled `assess`, it
        declares the outcome, and the map points at it — so the schema is
        satisfied and the belt agrees. NOTHING mechanical can see that the
        label is a lie, because the only evidence that it is a lie is the
        narration, and judging narration against a label is judgment.

        What (2)+(3) changed is the SHAPE of the failure a reviewer meets:
        RC-Q9b used to arrive as an absent map, which reads as a machine fault;
        it now arrives as a scene whose event label does not match its own
        words, which reads as a wrong brief. That is the reviewer's call at the
        gate — Foundation §7 — and this test exists so nobody later mistakes
        the gate's silence here for a guarantee.
        """
        from app.services.design_review import review, split
        scenes = [
            _scene(0, instructional_event="present"),
            _scene(1, instructional_event="assess",
                   narration_text="So that is how we multiply. Well done!"),
        ]
        findings, rows = review(scenes=scenes, outcomes=[OUTCOME],
                                evidence_map={"LO-1": [1]})
        refusals, _ = split(findings)
        assert refusals == [], (
            "if this ever starts refusing, something began judging narration "
            "against a label — read the docstring before 'fixing' the test"
        )
        assert rows[0].assessed is True
