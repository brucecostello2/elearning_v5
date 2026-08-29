"""WP-IVGS-12d — backward design becomes the EMISSION ORDER.

RC-Q9c: with the evidence map required and its contradictions promoted to hard
refusals, three generations still produced 5, 6, 5. The model named `present`
scenes as evidence while its own `practice` scenes sat unnamed, and in one
generation wrote a map while containing no assessing scene at all. Every one of
those was the model being asked, AFTER designing a lesson, to describe evidence
inside it — and answering with a plausible sentence rather than a true one.

The ruling closes it with three moves, and these tests pin each:

  ORDER    `assessment_plan` is the FIRST property of the schema, so the model
           commits to the evidence before a scene exists. This rests on a
           MEASURED fact — declaration order binds generation order on the
           pinned engine — and the test pins the position, because a reorder
           for tidiness would silently turn the commitment back into a
           rationalisation and no membership check would notice.

  DERIVE   `evidence_map` is gone from the model's schema; code computes it.
           Three refusals deleted, and `OUTCOME_UNASSESSED` computed from the
           derived map is the one true check.

  REALIZE  `PLAN_ENTRY_UNREALIZED` — the one refusal this package adds. Every
           plan entry must be delivered by a scene serving that outcome and
           declaring that EXACT evidence_kind.
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


OUTCOME = {"id": "LO-1", "text": "compute the product", "measurable": True}


def _codes(findings, severity):
    return sorted({f.code for f in findings if f.severity == severity})


# ---------------------------------------------------------------------------
# ORDER — the measured fact everything else rests on
# ---------------------------------------------------------------------------

class TestThePlanIsEmittedBeforeAnyScene:
    def test_assessment_plan_is_the_FIRST_property(self):
        """⛔ POSITION, NOT MEMBERSHIP, AND THAT IS THE WHOLE TEST.

        Declaration order binds generation order on the pinned engine — measured
        in both directions against a prompt explicitly ordering the model to
        emit `scenes` first, and `properties` is the controlling list
        (`required` order does not matter). So a plan declared first is written
        while the scene list is empty, and a plan declared anywhere else is a
        rationalisation of scenes already designed.

        A test asserting only that `assessment_plan` EXISTS would pass on a
        schema that has quietly moved it below `scenes` and lost the property
        the package is named for.
        """
        c = _contract()
        props = list(c.design_contract_schema(
            outcome_ids=["LO-1", "LO-2", "LO-3"])["properties"].keys())
        assert props[0] == "assessment_plan", props
        assert props.index("assessment_plan") < props.index("scenes")

    def test_the_plan_requires_one_entry_per_outcome_and_admits_no_other(self):
        c = _contract()
        ids = ["LO-1", "LO-2", "LO-3"]
        plan = c.design_contract_schema(
            outcome_ids=ids)["properties"]["assessment_plan"]
        assert plan["required"] == ids
        assert plan["additionalProperties"] is False
        entry = plan["properties"]["LO-2"]
        assert entry["required"] == ["evidence_kind", "learner_does"]
        assert entry["additionalProperties"] is False

    def test_evidence_kind_is_closed_to_the_assessing_events(self):
        """One definition. The gate matches this value against a scene's
        `instructional_event`, so a third spelling here would be unrealizable."""
        from shared.models.enums import ASSESSING_EVENTS
        c = _contract()
        entry = c.design_contract_schema(
            outcome_ids=["LO-1"])["properties"]["assessment_plan"]["properties"]["LO-1"]
        assert set(entry["properties"]["evidence_kind"]["enum"]) == set(ASSESSING_EVENTS)

    def test_learner_does_is_bounded(self):
        """RC-Q12 in its string form: every unbounded region of a
        grammar-constrained emission is somewhere the decoder can run."""
        c = _contract()
        entry = c.design_contract_schema(
            outcome_ids=["LO-1"])["properties"]["assessment_plan"]["properties"]["LO-1"]
        field = entry["properties"]["learner_does"]
        assert field["maxLength"] == c.MAX_LEARNER_DOES_CHARS
        assert field["minLength"] == 1

    def test_no_ids_means_no_plan_rather_than_an_unsatisfiable_one(self):
        """A project whose operator stated no outcomes has nothing to promise
        evidence FOR. An empty required-key object would be a grammar with no
        legal completion — the RC-Q9b empty-enum trap in a new place."""
        c = _contract()
        s = c.design_contract_schema(outcome_ids=[])
        assert "assessment_plan" not in s["properties"]
        assert "assessment_plan" not in s["required"]

    def test_every_array_in_the_contract_is_still_bounded_above(self):
        """RC-Q12's standing guard, re-run over the shape 12d changed."""
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


# ---------------------------------------------------------------------------
# DERIVE — one function, two trees
# ---------------------------------------------------------------------------

class TestTheMapIsDerivedInOnePlace:
    def test_the_worker_parse_derives_it_rather_than_reading_it(self):
        """The model may still emit an `evidence_map` — a stale prompt, a
        replayed contract. It must be IGNORED, not trusted."""
        c = _contract()
        raw = {
            "assessment_plan": {"LO-1": {"evidence_kind": "assess",
                                         "learner_does": "unaided"}},
            "evidence_map": {"LO-1": [99]},        # a lie, from an older prompt
            "scenes": [
                {"scene_index": 1, "serves_outcomes": ["LO-1"],
                 "instructional_event": "assess",
                 "provenance": {"origin": "designed", "rationale": "r"}},
            ],
            "dropped_beats": [], "design_notes": "x",
            "outcome_notes": {"LO-1": {}},
        }
        parsed = c.parse_contract(raw)
        assert parsed["evidence_map"] == {"LO-1": [1]}, (
            "the model's own map must not survive the parse"
        )
        assert parsed["raw_contract"]["evidence_map"] == {"LO-1": [99]}, (
            "and the lie must still be visible in the evidence limb"
        )

    def test_the_gate_and_the_worker_use_the_same_function(self):
        import app.services.design_review as dr
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        import design_core.contract as cc
        assert "derive_evidence_map" in Path(dr.__file__).read_text()
        assert "derive_evidence_map" in Path(cc.__file__).read_text()

    def test_the_gate_ignores_a_stored_map_and_recomputes_from_the_rows(self):
        """`review` takes no `evidence_map`. A reviewer editing a scene's event
        at the gate must see the consequence immediately, and a map derived at
        capture is stale the moment they do."""
        import inspect
        from app.services.design_review import review
        assert "evidence_map" not in inspect.signature(review).parameters


# ---------------------------------------------------------------------------
# REALIZE — the one refusal 12d adds
# ---------------------------------------------------------------------------

class TestThePlanMustBeRealized:
    def test_a_promise_no_scene_keeps_is_REFUSED_naming_the_outcome_and_kind(self):
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0), _scene(1, instructional_event="practice")],
            outcomes=[OUTCOME],
            assessment_plan={"LO-1": {"evidence_kind": "assess",
                                      "learner_does": "multiplies 34 by 21 unaided"}})
        bad = [f for f in findings if f.code == "PLAN_ENTRY_UNREALIZED"]
        assert bad and bad[0].severity == "refuse"
        assert bad[0].outcome_id == "LO-1"
        assert bad[0].detail["evidence_kind"] == "assess"
        assert "multiplies 34 by 21 unaided" in bad[0].message

    def test_the_kind_is_matched_EXACTLY_not_merely_as_an_assessing_event(self):
        """⛔ A `practice` scene does NOT keep an `assess` promise.

        Both are in ASSESSING_EVENTS, so the outcome counts as assessed and
        `OUTCOME_UNASSESSED` is silent — this refusal is the only thing that
        notices the design quietly downgraded what it promised the learner
        would do unaided.
        """
        from app.services.design_review import review
        findings, rows = review(
            scenes=[_scene(0), _scene(1, instructional_event="practice")],
            outcomes=[OUTCOME],
            assessment_plan={"LO-1": {"evidence_kind": "assess",
                                      "learner_does": "unaided"}})
        assert rows[0].assessed is True
        assert "OUTCOME_UNASSESSED" not in _codes(findings, "refuse")
        assert "PLAN_ENTRY_UNREALIZED" in _codes(findings, "refuse")

    def test_a_kept_promise_passes(self):
        from app.services.design_review import review, split
        findings, _ = review(
            scenes=[_scene(0, instructional_event="guide"),
                    _scene(1, instructional_event="assess")],
            outcomes=[OUTCOME],
            assessment_plan={"LO-1": {"evidence_kind": "assess",
                                      "learner_does": "unaided"}})
        refusals, _ = split(findings)
        assert refusals == [], [f.code for f in refusals]

    def test_a_promise_kept_by_a_scene_serving_a_DIFFERENT_outcome_is_refused(self):
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0),
                    _scene(1, serves_outcomes=["LO-2"], instructional_event="assess")],
            outcomes=[OUTCOME, {"id": "LO-2", "text": "explain"}],
            assessment_plan={"LO-1": {"evidence_kind": "assess", "learner_does": "a"},
                             "LO-2": {"evidence_kind": "assess", "learner_does": "b"}})
        bad = [f for f in findings if f.code == "PLAN_ENTRY_UNREALIZED"]
        assert [f.outcome_id for f in bad] == ["LO-1"]

    def test_a_missing_plan_entry_FLAGS_rather_than_refusing_twice(self):
        """The schema requires an entry per id, so this is the degraded path.
        `OUTCOME_UNASSESSED` already refuses the case that harms the learner;
        refusing twice for one defect trains reviewers to skim."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess")],
            outcomes=[OUTCOME, {"id": "LO-2", "text": "explain"}],
            assessment_plan={"LO-1": {"evidence_kind": "assess", "learner_does": "a"}})
        assert "ASSESSMENT_PLAN_MISSING_OUTCOME" in _codes(findings, "flag")

    def test_no_plan_at_all_produces_no_plan_findings(self):
        """A contract-3 brief read by a contract-4 gate. It must not sprout
        refusals for a field its own generation never had."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess")],
            outcomes=[OUTCOME], assessment_plan={})
        assert not [f for f in findings if f.code.startswith(
            ("PLAN_", "ASSESSMENT_PLAN_"))]

    def test_a_junk_evidence_kind_flags_and_does_not_crash(self):
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, instructional_event="assess")], outcomes=[OUTCOME],
            assessment_plan={"LO-1": {"evidence_kind": "vibes", "learner_does": "a"}})
        assert "ASSESSMENT_PLAN_BAD_KIND" in _codes(findings, "flag")


class TestTheStorageAndThePrompt:
    def test_the_brief_stores_the_plan(self):
        from app.models.design_brief import StoryboardDesignBrief
        assert hasattr(StoryboardDesignBrief, "assessment_plan")

    def test_migration_0051_adds_it_additively(self):
        m = (REPO / "ivgs-api" / "migrations" / "versions"
             / "0051_wp_ivgs_12d_assessment_plan.py").read_text()
        assert 'down_revision = "0050"' in m
        assert "add_column" in m and "drop_column" in m
        assert "'{}'::jsonb" in m
        assert "UPDATE" not in m.upper().replace("UPDATED", ""), (
            "0051 must not rewrite existing briefs: a contract-3 brief's "
            "model-authored map is the evidence that RC-Q9c happened"
        )

    def test_the_prompt_teaches_the_order_the_contract_enforces(self):
        text = (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_design_system.j2").read_text()
        assert "DESIGN THE ASSESSMENT FIRST, THEN THE ARC THAT REALIZES IT" in text
        assert "THE FADING SEQUENCE" in text
        assert "a COMPLETE worked example" in text
        assert "an INDEPENDENT problem" in text
        assert "evidence_kind" in text and "learner_does" in text

    def test_the_prompt_no_longer_asks_for_an_evidence_map(self):
        """It cannot: the field is gone. A prompt still demanding it would be
        instructing the model to fill a key the grammar forbids."""
        text = (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_design_system.j2").read_text()
        assert "evidence_map" not in text

    def test_the_publisher_gates_the_new_load_bearing_phrases(self):
        from app.scripts.wpivgs12_publish_design_prompts import DESIGN_PHRASES
        text = (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_design_system.j2").read_text()
        assert "DESIGN THE ASSESSMENT FIRST, THEN THE ARC THAT REALIZES IT" in DESIGN_PHRASES
        assert not [p for p in DESIGN_PHRASES if p not in text]


class TestTheContractFourRoundTrip:
    """⛔ THE GAP §12d.8 WOULD OTHERWISE HAVE ONLY FLAGGED.

    12d changed `parse_contract` AND the ingest, so "the storage round-trip was
    not re-exercised" is a weaker caveat here than it was in 12c — weak enough
    that flagging it instead of closing it would be a choice, not a limit. This
    drives a real contract-4 emission through the worker's parse, the API's
    service and the gate, against the database, in one pass.
    """

    async def test_a_contract_four_emission_survives_parse_store_and_gate(
        self, db_session,
    ):
        import uuid as _uuid
        from app.models.project import Project
        from app.services.design_brief_service import DesignBriefService
        from app.services.design_review import review, split

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import parse_contract

        outcomes_text = "LO-1: compute the product.\nLO-2: explain the zero."
        project = Project(id=_uuid.uuid4(), name="12d round trip", state="DRAFT",
                          learning_outcomes=outcomes_text)
        db_session.add(project)
        await db_session.flush()

        emission = {
            "assessment_plan": {
                "LO-1": {"evidence_kind": "assess",
                         "learner_does": "multiplies 34 by 21 unaided"},
                "LO-2": {"evidence_kind": "practice",
                         "learner_does": "explains the placeholder zero"},
            },
            "scenes": [
                {"scene_index": 1, "serves_outcomes": ["LO-1", "LO-2"],
                 "instructional_event": "present", "bloom_level": "understand",
                 "provenance": {"origin": "designed", "rationale": "framing"}},
                {"scene_index": 2, "serves_outcomes": ["LO-1"],
                 "instructional_event": "assess", "bloom_level": "apply",
                 "provenance": {"origin": "designed", "rationale": "the check"}},
                {"scene_index": 3, "serves_outcomes": ["LO-2"],
                 "instructional_event": "practice", "bloom_level": "understand",
                 "provenance": {"origin": "designed", "rationale": "the attempt"}},
            ],
            "dropped_beats": [], "design_notes": "an arc",
            "outcome_notes": {"LO-1": {"bloom_level": "apply", "measurable": True,
                                       "proposed_refinement": None},
                              "LO-2": {"bloom_level": "understand", "measurable": True,
                                       "proposed_refinement": None}},
        }
        payload = parse_contract(emission)
        assert payload is not None
        assert payload["contract_version"] == "design-contract-4"

        brief = await DesignBriefService(db_session).record(project.id, payload)

        # ── it is IN THE DATABASE, not merely in the object we just built ──
        await db_session.refresh(brief)
        assert brief.assessment_plan["LO-1"]["evidence_kind"] == "assess"
        assert brief.assessment_plan["LO-2"]["learner_does"] == (
            "explains the placeholder zero")
        # keyed by the OPERATOR's ids and derived, not authored
        assert brief.evidence_map == {"LO-1": [2], "LO-2": [3]}
        # ── the operator's words, verbatim, still (RC-Q9 regression) ──
        # `text` is the outcome WITHOUT its "LO-n: " marker — the marker is
        # carried separately so `reconstruct(parse(x)) == x`. Asserting
        # `source` as well pins both halves of that, which is what makes the
        # 12b byte-compare belt meaningful.
        assert [o["text"] for o in brief.outcomes] == [
            "compute the product.", "explain the zero."]
        assert [o["source"] for o in brief.outcomes] == [
            "LO-1: compute the product.", "LO-2: explain the zero."]
        assert all(o["authored_by"] == "operator" for o in brief.outcomes)

        # ── and the gate reads it clean ──
        findings, rows = review(
            scenes=payload["scenes"], outcomes=brief.outcomes,
            assessment_plan=brief.assessment_plan,
            learning_outcomes=outcomes_text)
        refusals, _ = split(findings)
        assert refusals == [], [f.code for f in refusals]
        assert {r.outcome_id: r.assessed_by for r in rows} == {
            "LO-1": [2], "LO-2": [3]}

    async def test_a_broken_promise_survives_the_round_trip_as_a_refusal(
        self, db_session,
    ):
        """The same path with the assess scene downgraded to practice. If the
        refusal only fires on hand-built dicts and not on a stored brief, the
        check is decorative."""
        import uuid as _uuid
        from app.models.project import Project
        from app.services.design_brief_service import DesignBriefService
        from app.services.design_review import review, split

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import parse_contract

        project = Project(id=_uuid.uuid4(), name="12d broken promise",
                          state="DRAFT", learning_outcomes="LO-1: compute it.")
        db_session.add(project)
        await db_session.flush()

        payload = parse_contract({
            "assessment_plan": {"LO-1": {"evidence_kind": "assess",
                                         "learner_does": "unaided"}},
            "scenes": [
                {"scene_index": 1, "serves_outcomes": ["LO-1"],
                 "instructional_event": "guide", "bloom_level": "apply",
                 "provenance": {"origin": "designed", "rationale": "r"}},
                {"scene_index": 2, "serves_outcomes": ["LO-1"],
                 "instructional_event": "practice", "bloom_level": "apply",
                 "provenance": {"origin": "designed", "rationale": "r"}},
            ],
            "dropped_beats": [], "design_notes": "n",
            "outcome_notes": {"LO-1": {"bloom_level": "apply", "measurable": True,
                                       "proposed_refinement": None}},
        })
        brief = await DesignBriefService(db_session).record(project.id, payload)
        await db_session.refresh(brief)
        assert brief.evidence_map == {"LO-1": [2]}

        findings, _ = review(scenes=payload["scenes"], outcomes=brief.outcomes,
                             assessment_plan=brief.assessment_plan)
        refusals, _ = split(findings)
        assert [f.code for f in refusals] == ["PLAN_ENTRY_UNREALIZED"]
