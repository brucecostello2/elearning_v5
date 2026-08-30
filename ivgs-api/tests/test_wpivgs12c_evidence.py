"""WP-IVGS-12c, RE-AIMED BY 12d — every outcome served AND assessed.

⛔ WHY THIS WHOLE FILE MOVED, AND WHAT DID NOT.

12c made `evidence_map` a required, 1..4-bounded field the MODEL wrote, and
promoted `EVIDENCE_MAP_DISAGREES` to a hard refusal so a map contradicting its
own scenes could not pass. The refusal fired on every outcome of every
generation (RC-Q9c). **The check was right and the question was wrong** — asking
a model to assemble a list its own `serves_outcomes` and `instructional_event`
declarations already imply is asking it to transcribe, and a transcription can
always drift from its source. That is RC-Q9 one layer up.

So contract-4 REMOVES `evidence_map` from the model's schema and derives it in
code, which makes three of this file's assertions meaningless — not wrong, but
about a field that no longer exists:

    test_every_outcome_id_is_a_required_key…   the model has no such key
    test_an_empty_map_is_refused                nothing authors an empty map
    test_a_named_scene_that_…_is_REFUSED        nothing names a scene

**The RISK each of them guarded is re-asserted below at the new shape**, which is
the standing rule for a re-aim: an outcome must still be served and assessed, a
`present` scene must still not count as evidence, and the gate must still not
call a design clean when nothing proves an outcome. What changed is that these
are now properties of a DERIVATION rather than verdicts on a claim — so several
of them cannot fail by construction, and the tests say so where that is true.

12d's own additions live in `test_wpivgs12d_assessment_plan.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _contract():
    sys.path.insert(0, str(REPO / "ivgs-workers"))
    from design_core import contract
    return contract


_NARRATIONS = (
    "Welcome back. Today we tackle something new.",
    "Line the digits up in their columns, ones under ones.",
    "Work out 71 times 36 on your own, then check it.",
    "Notice what the placeholder zero is doing for us.",
    "Try one more, and this time nothing is on screen to help.",
)


def _scene(idx, **kw):
    # ⚠ RE-AIMED BY WP-IVGS-12h, AND NOTHING IS WEAKENED. Every scene this
    # helper builds used to carry the identical narration `"One."`, which was
    # harmless while nothing at the gate read narration. WP-IVGS-12h's
    # `EVIDENCE_NEAR_DUPLICATE` does read it, and it correctly refuses a design
    # whose `assess` scene says word for word what its `guide` scene said —
    # which is what a fixture of identical strings is. The narration is now
    # per-scene so the fixtures say what they always MEANT: three different
    # scenes. Every assertion in this file is unchanged.
    base = {
        "scene_index": idx, "serves_outcomes": ["LO-1"],
        "instructional_event": "present", "bloom_level": "apply",
        "scene_origin": "designed", "source_refs": None, "rewrite_of": None,
        "media_type": "image", "media_rationale": "framing",
        "generation_params": None,
        # ⚠ GENUINELY DIFFERENT SENTENCES AND NOT AN INDEX ON ONE TEMPLATE. The
        # first attempt at this re-aim was `f"Scene {idx}: a distinct thing is
        # said here."` and the belt refused THAT too, at containment 0.83 —
        # correctly, because two sentences differing only in a number are two
        # sentences differing only in a number. That is worth recording: the
        # measure does not care that a human can see the index.
        "narration_text": _NARRATIONS[idx % len(_NARRATIONS)],
        "signal_spec": None,
    }
    base.update(kw)
    return base


OUTCOME = {"id": "LO-1", "text": "compute the product",
           "measurable": True, "bloom_level": "apply"}
PLAN = {"LO-1": {"evidence_kind": "assess", "learner_does": "does it unaided"}}


def _codes(findings, severity):
    return sorted({f.code for f in findings if f.severity == severity})


# ---------------------------------------------------------------------------
# The model no longer writes the map — the risk moves to the derivation
# ---------------------------------------------------------------------------

class TestTheModelDoesNotAuthorTheEvidence:
    def test_evidence_map_is_gone_from_the_contract_entirely(self):
        """The 12c field, removed. If it ever comes back, so does RC-Q9c: a
        second authored account of what the scenes already say."""
        c = _contract()
        s = c.design_contract_schema(outcome_ids=["LO-1", "LO-2"])
        assert "evidence_map" not in s["properties"]
        assert "evidence_map" not in s["required"]
        assert "evidence_map" not in json.dumps(s)

    #: Shape markers, and the version each one first required. A schema
    #: carrying the marker must carry at least that version.
    #:
    #: -4 removed `evidence_map` (12d); -5 added `designed_assessments` (12f);
    #: -6 split that into `assessment_scenes` + `practice_scenes` and narrowed
    #: `scenes[].instructional_event` to seven events (12g).
    SHAPE_MARKERS = (
        ("assessment_plan", 4),
        ("assessment_scenes", 6),
        ("practice_scenes", 6),
    )

    def test_the_contract_version_records_the_shape_change(self):
        """The version moves whenever the SHAPE does.

        A stored brief's `contract_version` is how a reader knows which shape
        produced it, so a shape change that forgets to bump this is the defect.

        ⚠ RE-AIMED BY WP-IVGS-12g, AND THE REASON IS A DRIFT 12f LEFT BEHIND.
        12f's report says this test was re-aimed to "the current version, and it
        is past -3" so that a shape change with no bump still fails loudly
        without every package editing one line. **The docstring was rewritten
        and the assertion was not** — it still pinned the literal `-5`, so the
        test measured nothing except which package had last edited it, and it
        failed on 12g for the only reason it was supposed to stop failing for.

        This is the check the docstring always described: the version is tied to
        MARKERS IN THE SCHEMA ITSELF, so a shape change that forgets the bump
        fails, and a legitimate bump does not need this line edited.
        """
        c = _contract()
        version = c.CONTRACT_VERSION
        assert version.startswith("design-contract-")
        number = int(version.rsplit("-", 1)[-1])
        schema = c.design_contract_schema(outcome_ids=["LO-1", "LO-2"])
        for marker, required_from in self.SHAPE_MARKERS:
            if marker in schema["properties"]:
                assert number >= required_from, (
                    f"the schema carries {marker!r}, which arrived in "
                    f"design-contract-{required_from}, but CONTRACT_VERSION is "
                    f"{version!r} — a shape change without a version bump"
                )
        # `evidence_map` left the model's schema in -4 and has not come back.
        assert "evidence_map" not in schema["properties"]
        assert number >= 4

    def test_the_derived_map_cannot_disagree_with_the_scenes(self):
        """⛳ THE POINT OF THE WHOLE PACKAGE, as an assertion.

        12c needed a hard refusal because a map could contradict its scenes.
        There is no input to this function that makes it disagree with them —
        it IS them. So the property is checked by construction over a design
        built to be maximally awkward: duplicate indices, a scene serving two
        outcomes, an unknown id, and a present scene that must not count.
        """
        from shared.design.evidence import derive_evidence_map
        scenes = [
            _scene(1, instructional_event="present"),
            _scene(2, serves_outcomes=["LO-1", "LO-2"], instructional_event="practice"),
            _scene(2, instructional_event="practice"),
            _scene(9, serves_outcomes=["LO-9"], instructional_event="assess"),
        ]
        derived = derive_evidence_map(scenes, ["LO-1", "LO-2", "LO-3"])
        assert derived == {"LO-1": [2], "LO-2": [2], "LO-3": []}
        for oid, indices in derived.items():
            for index in indices:
                match = [s for s in scenes if s["scene_index"] == index]
                assert any(oid in s["serves_outcomes"]
                           and s["instructional_event"] in ("practice", "assess")
                           for s in match), (
                    f"{oid} -> scene {index} was derived from nothing that says so"
                )

    def test_an_unserved_outcome_gets_an_explicit_empty_entry(self):
        """12c refused an empty array because the MODEL wrote it. Derived, an
        empty entry is the honest answer and the finding, not a gap."""
        from shared.design.evidence import derive_evidence_map
        assert derive_evidence_map([_scene(0)], ["LO-1"]) == {"LO-1": []}


# ---------------------------------------------------------------------------
# The risks 12c's deleted refusals guarded, re-asserted at the new shape
# ---------------------------------------------------------------------------

class TestTheRisksTheDeletedRefusalsGuarded:
    def test_a_present_scene_still_does_not_count_as_evidence(self):
        """Was EVIDENCE_MAP_DISAGREES' `not_assessing` half. Now it simply
        cannot enter the map, and OUTCOME_UNASSESSED is what the reviewer sees."""
        from app.services.design_review import review
        findings, rows = review(scenes=[_scene(0), _scene(1)], outcomes=[OUTCOME])
        assert rows[0].assessed_by == []
        assert "OUTCOME_UNASSESSED" in _codes(findings, "refuse")

    def test_a_scene_serving_a_different_outcome_still_does_not_count(self):
        """Was EVIDENCE_MAP_DISAGREES' `not_serving` half."""
        from app.services.design_review import review
        findings, rows = review(
            scenes=[_scene(0),
                    _scene(1, serves_outcomes=["LO-2"], instructional_event="assess")],
            outcomes=[OUTCOME, {"id": "LO-2", "text": "explain the zero"}])
        by_id = {r.outcome_id: r for r in rows}
        assert by_id["LO-1"].assessed_by == []
        assert by_id["LO-2"].assessed_by == [1]
        assert "OUTCOME_UNASSESSED" in _codes(findings, "refuse")

    def test_the_gate_still_refuses_to_call_an_unproven_design_clean(self):
        """Was EVIDENCE_MAP_NAMES_NOTHING. It was OUTCOME_UNASSESSED wearing a
        second name, which is why it went."""
        from app.services.design_review import review, split
        findings, _ = review(scenes=[_scene(0, instructional_event="guide")],
                             outcomes=[OUTCOME])
        refusals, _ = split(findings)
        assert "OUTCOME_UNASSESSED" in [f.code for f in refusals]

    def test_no_phantom_index_can_be_derived(self):
        """Was EVIDENCE_MAP_PHANTOM_SCENE. A derived index came from a scene, so
        there is nothing to check — asserted so the absence is deliberate."""
        from shared.design.evidence import derive_evidence_map
        scenes = [_scene(3, instructional_event="assess")]
        derived = derive_evidence_map(scenes, ["LO-1"])
        existing = {s["scene_index"] for s in scenes}
        assert all(i in existing for i in derived["LO-1"])

    def test_practice_counts_as_evidence_as_well_as_assess(self):
        from app.services.design_review import review
        from shared.models.enums import ASSESSING_EVENTS
        assert ASSESSING_EVENTS == {"practice", "assess"}
        findings, rows = review(
            scenes=[_scene(0), _scene(1, instructional_event="practice")],
            outcomes=[OUTCOME],
            assessment_plan={"LO-1": {"evidence_kind": "practice",
                                      "learner_does": "attempts one"}})
        assert "OUTCOME_UNASSESSED" not in _codes(findings, "refuse")
        assert rows[0].assessed_by == [1]

    def test_a_clean_design_produces_no_refusals(self):
        from app.services.design_review import review, split
        findings, rows = review(
            scenes=[_scene(0, instructional_event="hook"),
                    _scene(1, instructional_event="guide"),
                    _scene(2, instructional_event="assess")],
            outcomes=[OUTCOME], assessment_plan=PLAN)
        refusals, _ = split(findings)
        assert refusals == [], [f.code for f in refusals]
        assert rows[0].served and rows[0].assessed


class TestServedAndAssessedIsClosed:
    def test_the_deleted_refusals_are_really_gone(self):
        """A deletion nobody can see is a deletion that comes back."""
        from app.services import design_review as dr
        source = Path(dr.__file__).read_text()
        for code in ("EVIDENCE_MAP_DISAGREES", "EVIDENCE_MAP_PHANTOM_SCENE",
                     "EVIDENCE_MAP_NAMES_NOTHING"):
            assert f'"{code}"' not in source, f"{code} still constructs a Finding"

    def test_dropping_an_outcome_is_not_available_to_the_designer(self):
        """⛔ THE OPERATOR'S RULING, unchanged since 12c. Dropping an outcome is
        an operator act at the gate; there is no `dropped_outcomes` mechanism."""
        c = _contract()
        blob = json.dumps(c.design_contract_schema(outcome_ids=["LO-1"]))
        assert "dropped_outcomes" not in blob
        assert "dropped_beats" in blob
        import app.services.design_review as dr
        assert "dropped_outcomes" not in Path(dr.__file__).read_text()


class TestWhatThisStillCannotDo:
    def test_a_mislabelled_scene_still_passes(self):
        """⛔ THE RESIDUE, CARRIED FORWARD FROM 12c AND STILL TRUE.

        Scene 1 is a recap. Its narration says so. It is labelled `assess`, it
        declares the outcome, the derived map picks it up and the plan promised
        `assess`. Every mechanical check passes. Deriving the map removed a
        BOOKKEEPING failure; it cannot remove a MISLABELLING one, because the
        only evidence of the lie is the narration and judging narration against
        a label is judgment. That is the reviewer's call at the gate — read the
        docstring before 'fixing' this test.
        """
        from app.services.design_review import review, split
        findings, rows = review(
            scenes=[_scene(0, instructional_event="present"),
                    _scene(1, instructional_event="assess",
                           narration_text="So that is how we multiply. Well done!")],
            outcomes=[OUTCOME], assessment_plan=PLAN)
        refusals, _ = split(findings)
        assert refusals == [], (
            "if this starts refusing, something began judging narration against "
            "a label — read the docstring"
        )
        assert rows[0].assessed is True
