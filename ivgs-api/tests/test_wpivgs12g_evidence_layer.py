"""WP-IVGS-12g — the evidence layer is structural, completely.

⛔ THE MEASUREMENT THESE TESTS PROTECT

design-contract-5 put ONE evidence kind behind a grammar and left the other in
`scenes[]`, and RC-Q9f measured both halves of what that cost:

  limb 1  SIX generations of six refused `PLAN_ENTRY_UNREALIZED` on LO-2. The
          assessment plan was byte-identical every time —
          `{"LO-1":"assess","LO-2":"practice","LO-3":"assess"}` — and no
          `practice` scene was ever built. The forced kind appeared every time;
          the unforced kind never did.
  limb 2  with `assess` forced elsewhere, the model began writing EXTRA `assess`
          scenes INTO `scenes[]` — four generations of six, the first `designed`
          scenes ever emitted into that array on the operator's script — and the
          merge placed the mandated one immediately after its near-identical
          twin:

              "Now it's your turn to try. Multiply 43 by 27 using the standard
               column algorithm."
              "Now it's your turn to try. Multiply 43 by 27 using the standard
               column algorithm."

Four packages have now measured one law: **the model's plan predicts nothing on
this stack and only the grammar is causal.** 12g applies it ONCE to the whole
evidence layer rather than chasing it kind by kind. These tests pin the four
moves:

  FORCE   BOTH kinds are REQUIRED per-outcome sections — `assessment_scenes`
          (exactly 1) and `practice_scenes` (1..2). An emission missing either
          for any outcome is not parseable.
  NARROW  `scenes[].instructional_event` loses `practice` and `assess`. There is
          no shared slot for sourced material to out-compete authored material
          in, and nowhere to write a duplicate. Measured ENFORCED on the pinned
          engine before it shipped (`wpivgs12g-evidence/probe12g.json`).
  FREE    origin is the model's choice in both sections — 12f's one reversal —
          because B1 showed the model finding a real "now you try" span and
          using it, and that is legitimate evidence.
  ORDER   emission order is backward design complete: plan, assessment,
          practice, scenes. Placement is code's: practice after the last
          present/guide serving its outcome, assessment after that practice.

  BELT    `PLAN_ENTRY_UNREALIZED` becomes unreachable for BOTH kinds, and
          `OUTCOME_ASSESSED_TWICE` is born unreachable. Asserted here directly,
          against hostile inputs, and NEITHER CHECK IS DELETED — a structural
          guarantee is a claim about a schema, a merge and a decoder, all three
          editable by someone who does not know why they are shaped this way.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _contract():
    sys.path.insert(0, str(REPO / "ivgs-workers"))
    from design_core import contract
    return contract


IDS = ["LO-1", "LO-2", "LO-3"]

OUTCOMES = [
    {"id": "LO-1", "text": "compute the product", "measurable": True},
    {"id": "LO-2", "text": "explain the placeholder zero", "measurable": True},
    {"id": "LO-3", "text": "check their own work", "measurable": True},
]

SECTIONS = (("assessment_scenes", "assess"), ("practice_scenes", "practice"))


def _designed(oid, event, **kw):
    base = {
        "provenance": {"origin": "designed",
                       "rationale": "the script contains no unaided attempt"},
        "instructional_event": event,
        "serves_outcomes": [oid],
        "narration_text": f"Now work out 45 times 12. ({oid}/{event})",
        "visual_description": "a blank column layout",
        "media_type": "image",
        "media_rationale": "an attempt moment",
        "duration_seconds": 30,
        "bloom_level": "apply",
        "text_carried_by": None,
        "generation_params": None,
        "signal_spec": None,
    }
    base.update(kw)
    return base


def _sourced(oid, event="present", **kw):
    base = {
        "serves_outcomes": [oid],
        "instructional_event": event,
        "bloom_level": "understand",
        "narration_text": "One step.",
        "visual_description": "a column",
        "media_type": "image",
        "media_rationale": "static structure",
        "duration_seconds": 8,
        "text_carried_by": None,
        "generation_params": None,
        "signal_spec": None,
        "provenance": {"origin": "sourced",
                       "source_refs": [{"transcript_id": None, "start": 0,
                                        "end": 10, "quote": "x"}],
                       "rewrite_of": None},
    }
    base.update(kw)
    return base


def _emission(scenes=None, assessments=None, practice=None, plan_kind="assess"):
    """A whole contract-6 emission, of the shape the decoder would accept."""
    return {
        "assessment_plan": {
            oid: {"evidence_kind": plan_kind, "learner_does": "does the thing"}
            for oid in IDS
        },
        "assessment_scenes": dict(
            assessments if assessments is not None
            else {oid: [_designed(oid, "assess")] for oid in IDS}),
        "practice_scenes": dict(
            practice if practice is not None
            else {oid: [_designed(oid, "practice")] for oid in IDS}),
        "outcome_notes": {oid: {"bloom_level": "apply", "measurable": True,
                                "proposed_refinement": None} for oid in IDS},
        "scenes": list(scenes if scenes is not None
                       else [_sourced("LO-1"), _sourced("LO-2"), _sourced("LO-3")]),
        "dropped_beats": [],
        "design_notes": "an arc",
    }


# ---------------------------------------------------------------------------
# NARROW — `scenes[]` is the expository arc and nothing else
# ---------------------------------------------------------------------------

class TestScenesCannotDeclareEvidence:

    def test_the_scene_enum_is_seven_events_and_names_neither_evidence_kind(self):
        """⛳ THE LINE RC-Q9f's SECOND LIMB DIES ON.

        Contract-5 taught the model the shape of an authored assessment and did
        not tell it the shape was already provided, so it wrote a second one
        into `scenes[]` in four generations of six. This enum is why it cannot
        any more.
        """
        from shared.models.enums import ASSESSING_EVENTS, INSTRUCTIONAL_EVENTS

        schema = _contract().design_contract_schema(outcome_ids=IDS)
        events = schema["properties"]["scenes"]["items"]["properties"][
            "instructional_event"]["enum"]
        assert len(events) == 7
        assert set(events) == set(INSTRUCTIONAL_EVENTS) - ASSESSING_EVENTS
        assert "practice" not in events and "assess" not in events
        # Arc order is preserved: the Merrill cross-check asks its question by
        # INDEX, and a reordered vocabulary would answer it wrongly in silence.
        assert events == [e for e in INSTRUCTIONAL_EVENTS if e in set(events)]

    def test_feedback_stays_because_it_follows_an_attempt_rather_than_being_one(self):
        """`feedback` is an APPLICATION event and not an ASSESSING one.

        Removing it would also make `MERRILL_NO_APPLICATION` unreachable for the
        wrong reason — by emptying the set it tests rather than by satisfying it.
        """
        from shared.models.enums import APPLICATION_EVENTS, EXPOSITORY_EVENTS

        assert "feedback" in EXPOSITORY_EVENTS
        assert APPLICATION_EVENTS & set(EXPOSITORY_EVENTS) == {"feedback"}

    def test_the_narrowed_enum_holds_on_the_degraded_no_outcomes_path(self):
        """A project whose owner wrote no outcomes has no evidence layer, so it
        cannot reach `practice` or `assess` at all and every one of its designs
        is flagged `MERRILL_NO_APPLICATION`. That is the honest report of a
        lesson nobody said what to assess — widening the enum back here would
        let the model label an attempt it was never asked to serve anything."""
        schema = _contract().design_contract_schema(outcome_ids=[])
        events = schema["properties"]["scenes"]["items"]["properties"][
            "instructional_event"]["enum"]
        assert "practice" not in events and "assess" not in events
        assert "assessment_scenes" not in schema["properties"]
        assert "practice_scenes" not in schema["properties"]


# ---------------------------------------------------------------------------
# FORCE — both kinds, bounded, one key per outcome
# ---------------------------------------------------------------------------

class TestBothKindsAreForced:

    @pytest.mark.parametrize("section,event", SECTIONS)
    def test_the_section_is_required_for_every_outcome(self, section, event):
        schema = _contract().design_contract_schema(outcome_ids=IDS)
        assert section in schema["required"]
        block = schema["properties"][section]
        assert sorted(block["required"]) == sorted(IDS)
        assert block["additionalProperties"] is False
        for oid in IDS:
            arr = block["properties"][oid]
            assert arr["minItems"] >= 1
            assert arr["items"]["properties"]["instructional_event"]["enum"] == [event]

    def test_the_bounds_are_asymmetric_and_the_asymmetry_is_foundation_two(self):
        """One independent attempt; one or two supported ones.

        A second `assess` is RC-Q9f limb 2 — the duplicate — and there is no
        design at this scale in which two unaided attempts at one outcome is
        right. A second `practice` is the fading sequence: a complete worked
        example and then a faded one are two supported attempts, and a ceiling
        of 1 would forbid what Foundation §2 prescribes.
        """
        c = _contract()
        schema = c.design_contract_schema(outcome_ids=IDS)
        a = schema["properties"]["assessment_scenes"]["properties"]["LO-1"]
        p = schema["properties"]["practice_scenes"]["properties"]["LO-1"]
        assert (a["minItems"], a["maxItems"]) == (1, 1)
        assert (p["minItems"], p["maxItems"]) == (1, 2)
        assert c.ASSESSMENT_SCENES_PER_OUTCOME == 1
        assert (c.MIN_PRACTICE_SCENES_PER_OUTCOME,
                c.MAX_PRACTICE_SCENES_PER_OUTCOME) == (1, 2)

    def test_every_array_in_the_evidence_layer_carries_a_maximum(self):
        """RC-Q12. `minItems` with no maximum is a measured runaway on this
        engine: the enum was honoured perfectly while the array grew to the
        token limit."""
        schema = _contract().design_contract_schema(outcome_ids=IDS)

        def walk(node, path):
            if isinstance(node, dict):
                if node.get("type") == "array":
                    assert "maxItems" in node, f"unbounded array at {path}"
                for k, v in node.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")

        for section, _ in SECTIONS:
            walk(schema["properties"][section], section)

    def test_every_string_in_the_evidence_layer_that_can_run_is_bounded(self):
        """⛳ 12f's NAMED RESIDUE, CLOSED — and only because 12g made it
        load-bearing. 12f left the `designed` branch's `rationale` unbounded
        deliberately (that branch was untouched contract-4 surface). Contract-6
        routes every evidence scene's provenance through that same `oneOf`, so
        an unbounded string now sits in the one place a runaway costs a whole
        generation. `maxLength` is the string-shaped `maxItems`."""
        c = _contract()
        branches = {b["properties"]["origin"]["enum"][0]: b
                    for b in c._provenance_branches()}
        rationale = branches["designed"]["properties"]["rationale"]
        assert rationale["maxLength"] == c.MAX_DESIGNED_RATIONALE_CHARS
        assert rationale["minLength"] == 1


# ---------------------------------------------------------------------------
# ORDER — backward design, complete
# ---------------------------------------------------------------------------

class TestTheEmissionOrderIsBackwardDesign:

    def test_the_property_order_is_plan_assessment_practice_scenes(self):
        """⛔ THE ORDER IS THE ARGUMENT, and it reads backwards on purpose.

        Declaration order binds generation order (12d, measured in BOTH
        directions against a prompt ordering otherwise), so this is the sequence
        the model actually thinks in: what would prove the outcome, then the
        independent attempt, then the supported attempt that leads to it, then
        the exposition that prepares both. The model poses the assessment while
        it has no worked example of its own to lift numbers out of.
        """
        order = list(_contract().design_contract_schema(
            outcome_ids=IDS)["properties"])
        assert order[:4] == ["assessment_plan", "assessment_scenes",
                             "practice_scenes", "scenes"]

    @pytest.mark.parametrize("section,_event", SECTIONS)
    def test_the_model_is_never_asked_where_any_of_it_goes(self, section, _event):
        entry = (_contract().design_contract_schema(outcome_ids=IDS)
                 ["properties"][section]["properties"]["LO-1"]["items"])
        assert "scene_index" not in entry["properties"]
        assert "scene_index" not in entry["required"]


# ---------------------------------------------------------------------------
# FREE — origin is the model's choice, in both sections
# ---------------------------------------------------------------------------

class TestOriginIsFree:

    @pytest.mark.parametrize("section,_event", SECTIONS)
    def test_both_provenance_branches_are_offered(self, section, _event):
        """⛔ 12f's ONE REVERSAL. B1 handed the model a script containing
        *"Now you try. … Work out 63 minus 48. Pause here. Do not read on
        yet."* and it found that span and anchored to it in both runs. Pinning
        `origin: "designed"` would force an invented substitute for a real
        teacher's real practice item, plus a rationale asserting its absence."""
        prov = (_contract().design_contract_schema(outcome_ids=IDS)
                ["properties"][section]["properties"]["LO-1"]["items"]
                ["properties"]["provenance"])
        assert sorted(b["properties"]["origin"]["enum"][0]
                      for b in prov["oneOf"]) == ["designed", "sourced"]

    @pytest.mark.parametrize("section,_event", SECTIONS)
    def test_the_xor_is_the_same_one_every_other_scene_uses(self, section, _event):
        """One `oneOf`, not a second copy — so migration 0048's CHECK constraint
        holds an evidence scene exactly as it holds an expository one."""
        c = _contract()
        prov = (c.design_contract_schema(outcome_ids=IDS)
                ["properties"][section]["properties"]["LO-1"]["items"]
                ["properties"]["provenance"])
        assert prov["oneOf"] == c._provenance_branches()

    def test_a_sourced_evidence_scene_parses_and_keeps_its_spans(self):
        c = _contract()
        emission = _emission(practice={
            oid: [_sourced(oid, "practice")] for oid in IDS})
        rows = c.parse_contract(emission)["scenes"]
        practice = [r for r in rows if r["instructional_event"] == "practice"]
        assert len(practice) == 3
        assert all(r["scene_origin"] == "sourced" for r in practice)
        assert all(r["source_refs"] for r in practice)
        # ⚠ The parse writes `designed_rationale` only on the designed branch;
        # `_clean` fills every SCENE_DESIGN_FIELD before storing, so a sourced
        # row reaches the table with NULL rather than with a stale value. That
        # is 12b's "write the declaration whole" and it is asserted on the
        # stored ROW in the round-trip test below, which is where it matters.
        assert all(r.get("designed_rationale") is None for r in practice)


# ---------------------------------------------------------------------------
# PLACE — the fading order, derived
# ---------------------------------------------------------------------------

class TestPlacementIsTheFadingOrder:

    def test_practice_lands_after_the_last_present_or_guide_and_assess_after_it(self):
        """Foundation §2, as an insertion rule.

        12f anchored to the last scene SERVING the outcome. That was right when
        there was one evidence scene and nothing to order it against; with two,
        the anchor has to be the end of the TEACHING so the block reads
        present/guide → practice → assess.
        """
        from shared.design.merge import merged_scene_sequence

        merged = merged_scene_sequence(_emission(scenes=[
            _sourced("LO-1", "hook"),
            _sourced("LO-1", "present"),
            _sourced("LO-1", "guide"),
            _sourced("LO-2", "present"),
            _sourced("LO-3", "present"),
            _sourced("LO-1", "transfer"),
        ]))
        assert [s["instructional_event"] for s in merged] == [
            "hook", "present", "guide", "practice", "assess",
            "present", "practice", "assess",
            "present", "practice", "assess",
            "transfer",
        ]
        assert [s["scene_index"] for s in merged] == list(range(len(merged)))

    def test_each_outcomes_evidence_is_contiguous_not_interleaved(self):
        """Outcome-major, then section order. Interleaving would scatter one
        outcome's fading sequence through another's."""
        from shared.design.merge import merged_scene_sequence

        merged = merged_scene_sequence(_emission(scenes=[
            _sourced("LO-1", "present"), _sourced("LO-2", "present"),
            _sourced("LO-3", "present"),
        ]))
        assert [(s["serves_outcomes"][0], s["instructional_event"])
                for s in merged] == [
            ("LO-1", "present"), ("LO-1", "practice"), ("LO-1", "assess"),
            ("LO-2", "present"), ("LO-2", "practice"), ("LO-2", "assess"),
            ("LO-3", "present"), ("LO-3", "practice"), ("LO-3", "assess"),
        ]

    def test_two_practice_scenes_both_land_before_the_assessment(self):
        from shared.design.merge import merged_scene_sequence

        merged = merged_scene_sequence(_emission(
            scenes=[_sourced("LO-1", "present")],
            assessments={"LO-1": [_designed("LO-1", "assess")]},
            practice={"LO-1": [_designed("LO-1", "practice"),
                               _designed("LO-1", "practice")]}))
        assert [s["instructional_event"] for s in merged] == [
            "present", "practice", "practice", "assess"]

    def test_an_outcome_the_lesson_never_teaches_goes_to_the_tail_and_is_flagged(self):
        """The anchor is -1 and the evidence goes to the end. That is a real
        defect in the lesson and the merge does not hide it — the gate names it
        `PRACTICE_NOT_PREPARED`, which is now the ONLY limb still asking whether
        a lesson teaches what it assesses."""
        from app.services.design_review import review, split
        from shared.design.merge import merged_scene_sequence

        emission = _emission(scenes=[_sourced("LO-1", "present")])
        merged = merged_scene_sequence(emission)
        # LO-2's and LO-3's evidence has no teaching to sit behind.
        assert [s["serves_outcomes"][0] for s in merged[-4:]] == [
            "LO-2", "LO-2", "LO-3", "LO-3"]
        findings, _ = review(
            scenes=_rows(merged), outcomes=OUTCOMES,
            assessment_plan=emission["assessment_plan"],
            learning_outcomes="\n".join(f"{o['id']}: {o['text']}" for o in OUTCOMES))
        refusals, flags = split(findings)
        assert [f.code for f in refusals] == []
        assert [f.code for f in flags].count("PRACTICE_NOT_PREPARED") == 4

    def test_a_contract_five_brief_keeps_contract_five_placement(self):
        """⚠ STORED BRIEFS DO NOT MOVE. A contract-5 emission had no practice to
        sit after, so its assessment still anchors to the last scene serving its
        outcome. Re-deriving old briefs under the new rule would silently
        relocate scenes in records the gate has already been reviewed against."""
        from shared.design.merge import merged_scene_sequence

        legacy = {
            "scenes": [_sourced("LO-1", "present"), _sourced("LO-1", "transfer")],
            "designed_assessments": {"LO-1": _designed("LO-1", "assess")},
        }
        merged = merged_scene_sequence(legacy)
        assert [s["instructional_event"] for s in merged] == [
            "present", "transfer", "assess"]

    def test_a_pre_contract_five_emission_is_the_identity_case(self):
        from shared.design.merge import merged_scene_sequence

        merged = merged_scene_sequence(
            {"scenes": [_sourced("LO-1"), _sourced("LO-2")]})
        assert [s["scene_index"] for s in merged] == [0, 1]

    def test_the_emitted_scenes_are_never_edited(self):
        """The caller's `raw_contract` is the verbatim evidence limb and is
        stored as one. Copies out, no mutation in."""
        from shared.design.merge import merged_scene_sequence

        emission = _emission()
        before = [dict(s) for s in emission["scenes"]]
        merged_scene_sequence(emission)
        assert emission["scenes"] == before


def _rows(merged):
    """The scene ROWS the parse produces, from a merged sequence."""
    out = []
    for s in merged:
        prov = s.get("provenance") or {}
        out.append({
            "scene_index": s["scene_index"],
            "serves_outcomes": s["serves_outcomes"],
            "instructional_event": s["instructional_event"],
            "bloom_level": s.get("bloom_level"),
            "scene_origin": prov.get("origin"),
            "source_refs": prov.get("source_refs"),
            "narration_text": s.get("narration_text"),
            "media_type": s.get("media_type"),
            "generation_params": s.get("generation_params"),
            "duration_seconds": s.get("duration_seconds"),
        })
    return out


# ---------------------------------------------------------------------------
# BELT — the refusals that can no longer fire, and are not deleted
# ---------------------------------------------------------------------------

class TestTheBeltIsUnreachableAndStillThere:

    def _review(self, emission):
        from app.services.design_review import review
        from shared.design.merge import merged_scene_sequence

        return review(
            scenes=_rows(merged_scene_sequence(emission)),
            outcomes=OUTCOMES,
            assessment_plan=emission.get("assessment_plan", {}),
            dropped_beats=emission.get("dropped_beats", []),
            learning_outcomes="\n".join(
                f"{o['id']}: {o['text']}" for o in OUTCOMES))

    @pytest.mark.parametrize("kind", ["assess", "practice"])
    def test_plan_entry_unrealized_cannot_fire_for_either_kind(self, kind):
        """⛔ RC-Q9f LIMB 1, AS AN ASSERTION.

        Contract-5 forced `assess` and this refusal fired on `practice` in six
        generations of six. Whichever kind the plan names, the scene that
        realizes it now exists before the plan is read.
        """
        findings, _ = self._review(_emission(plan_kind=kind))
        assert not [f for f in findings if f.code == "PLAN_ENTRY_UNREALIZED"]

    @pytest.mark.parametrize("kind", ["assess", "practice"])
    def test_it_cannot_fire_even_for_a_pure_lecture(self, kind):
        """The hostile case: `scenes[]` teaches and nothing else. Under
        contract-4 this was three refusals every time."""
        findings, _ = self._review(_emission(
            plan_kind=kind,
            scenes=[_sourced("LO-1", "present"), _sourced("LO-2", "present"),
                    _sourced("LO-3", "present")]))
        refused = [f.code for f in findings
                   if f.code in ("PLAN_ENTRY_UNREALIZED", "OUTCOME_UNASSESSED",
                                 "OUTCOME_UNSERVED", "OUTCOME_ASSESSED_TWICE")]
        assert refused == []

    def test_outcome_assessed_twice_cannot_fire(self):
        """⛔ RC-Q9f LIMB 2, AS AN ASSERTION. `scenes[]` cannot declare `assess`
        and the section holds exactly one, so the count is always one."""
        findings, _ = self._review(_emission())
        assert not [f for f in findings if f.code == "OUTCOME_ASSESSED_TWICE"]

    def test_but_it_does_fire_when_the_guarantee_is_broken_by_hand(self):
        """⛳ THE BELT IS A BELT ONLY IF IT STILL WORKS.

        A schema, a merge and a decoder are three pieces of code someone can
        edit without knowing why they are shaped this way, and this lineage is a
        record of guarantees that turned out narrower than believed —
        `guided_json` returning 200 and doing nothing is the purest example, and
        contract-5's `assess`-only forcing is the most recent. So the check is
        driven directly, past the grammar, exactly as it would be on the day the
        grammar stopped holding.
        """
        from app.services.design_review import review, split

        rows = _rows([
            dict(_sourced("LO-1", "present"), scene_index=0),
            dict(_designed("LO-1", "assess"), scene_index=1),
            dict(_designed("LO-1", "assess"), scene_index=2),
        ])
        findings, _ = review(
            scenes=rows, outcomes=[OUTCOMES[0]], assessment_plan={},
            learning_outcomes="LO-1: compute the product")
        refusals, _ = split(findings)
        twice = [f for f in refusals if f.code == "OUTCOME_ASSESSED_TWICE"]
        assert len(twice) == 1
        assert twice[0].detail["assess_scene_indices"] == [1, 2]

    def test_plan_entry_unrealized_still_fires_when_driven_past_the_grammar(self):
        """The same belt test for limb 1. The comparison is not weakened by one
        character: 12d declined loosening it with the number on the record and
        12e made it a standing rule — evidence kinds are never collapsed to
        green a check."""
        from app.services.design_review import review, split

        rows = _rows([dict(_sourced("LO-1", "present"), scene_index=0)])
        findings, _ = review(
            scenes=rows, outcomes=[OUTCOMES[0]],
            assessment_plan={"LO-1": {"evidence_kind": "practice",
                                      "learner_does": "attempts it"}},
            learning_outcomes="LO-1: compute the product")
        refusals, _ = split(findings)
        assert "PLAN_ENTRY_UNREALIZED" in [f.code for f in refusals]

    def test_none_of_the_checks_were_deleted(self):
        """A check that can never fire costs one comparison per outcome and is
        the only thing that will say so out loud when the guarantee stops
        holding."""
        import inspect

        from app.services import design_review

        src = inspect.getsource(design_review)
        for code in ("OUTCOME_UNASSESSED", "OUTCOME_UNSERVED",
                     "PLAN_ENTRY_UNREALIZED", "OUTCOME_ASSESSED_TWICE",
                     "PRACTICE_NOT_PREPARED"):
            assert code in src, code

    def test_the_derived_map_reads_the_merged_sequence(self):
        """Every outcome assessed, from the scenes' own declarations, over the
        list the API stores and the frozen body renders."""
        from shared.design.evidence import derive_evidence_map
        from shared.design.merge import merged_scene_sequence

        em = derive_evidence_map(
            _rows(merged_scene_sequence(_emission())), IDS)
        assert sorted(em) == IDS
        assert all(len(v) == 2 for v in em.values())   # its practice AND assess


# ---------------------------------------------------------------------------
# The prompt, the publisher, and the worker seam
# ---------------------------------------------------------------------------

class TestThePromptAndTheSeam:

    def _prompt(self):
        return (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_design_system.j2").read_text(encoding="utf-8")

    def test_v7_removed_nothing_v6_gated_except_the_one_audited_drop(self):
        """⛔ THE ONE DROP, AND IT IS THE ONLY ONE.

        12f gated the literal key `designed_assessments`, which contract-6
        deletes. Every other phrase 12b, 12d, 12e and 12f gated survives — read
        from the publisher's OWN tuple so the two lists cannot drift, which is
        the same construct 12f used and the reason this is checkable at all.
        """
        src = (REPO / "ivgs-api" / "app" / "scripts"
               / "wpivgs12_publish_design_prompts.py").read_text(encoding="utf-8")
        segment = src[src.index("DESIGN_PHRASES"):src.index("#: The extraction prompt")]
        namespace: dict = {}
        exec(compile(segment.replace("DESIGN_PHRASES: Tuple[str, ...] =",
                                     "DESIGN_PHRASES =", 1), "phrases", "exec"),
             namespace)
        phrases = namespace["DESIGN_PHRASES"]
        text = self._prompt()
        assert [p for p in phrases if p in text] == list(phrases)
        assert "designed_assessments" not in phrases
        assert "designed_assessments" not in text

    def test_the_prompt_names_both_sections_and_the_free_origin(self):
        text = self._prompt()
        for phrase in ("assessment_scenes", "practice_scenes",
                       "SO `scenes` IS THE EXPOSITORY ARC, AND ONLY THAT",
                       "THE PRACTICE MUST NOT BE THE ASSESSMENT WEARING A LABEL",
                       'origin: "sourced"', 'origin: "designed"',
                       "AND YOU DO NOT PLACE THEM"):
            assert phrase in text, phrase

    def test_the_prompt_renders_with_outcomes_and_without(self):
        """A template that raises at render time takes the stage down, and the
        stage is frozen."""
        from jinja2 import BaseLoader, Environment

        env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
        tpl = env.from_string(self._prompt())
        assert len(tpl.render(learning_outcomes="LO-1: x", source_kind="uploaded",
                              outcomes=[{"id": "LO-1", "text": "x"}])) > 1000
        assert len(tpl.render(learning_outcomes="", outcomes=[],
                              source_kind="generated")) > 1000

    def test_the_worker_transform_recognises_the_new_sections(self):
        """Without this the evidence is authored, stored, reviewed — and never
        rendered, because the frozen body builds its rows from `scenes`."""
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core import capture

        capture._armed.set({"task_name": capture.STORYBOARD_TASK, "job_id": "j",
                            "project_id": "p", "stage": "storyboard", "seen": False})
        try:
            out = capture.transform_document(_emission())
            assert len(out["scenes"]) == 9
            events = [s["instructional_event"] for s in out["scenes"]]
            assert events.count("practice") == 3 and events.count("assess") == 3
            # Anything it does not recognise passes through untouched.
            assert capture.transform_document({"scenes": []}) == {"scenes": []}
            assert capture.transform_document("not a document") == "not a document"
        finally:
            capture._armed.set(None)

    def test_the_transform_reads_the_merge_modules_own_section_list(self):
        """⛔ ONE LIST, NOT A SECOND COPY. Contract-6 turned one section name
        into three (two new plus the legacy one), and a second spelling of that
        list in the capture module is how a contract-7 would silently stop
        transforming while every test still passed."""
        import inspect

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core import capture
        from shared.design import merge

        src = inspect.getsource(capture.transform_document)
        assert "EVIDENCE_SECTIONS" in src and "LEGACY_SECTION" in src
        assert '"designed_assessments"' not in src
        assert merge.EVIDENCE_SECTIONS == ("practice_scenes", "assessment_scenes")


# ---------------------------------------------------------------------------
# The storage round trip, against the database — the 12d lesson, kept
# ---------------------------------------------------------------------------

class TestTheContractSixRoundTrip:
    """⛔ 12d LEARNED THIS THE EXPENSIVE WAY AND NOBODY RE-LEARNS IT.

    Contract-6 changes the worker's parse, the merge's placement rule and the
    scene rows' ORDER, so "the storage round-trip was not re-exercised" would be
    a caveat covering the exact seam most likely to break. This drives a real
    contract-6 emission through the worker's parse, the API's service and the
    gate, against the database, in one pass — including the merged indices,
    which are what `apply_scene_design` matches scene ROWS on.
    """

    async def test_a_contract_six_emission_survives_parse_store_and_gate(
        self, db_session,
    ):
        import uuid as _uuid

        from app.models.project import Project
        from app.models.storyboard_scene import StoryboardScene
        from app.services.design_brief_service import DesignBriefService
        from app.services.design_review import review, split
        from sqlalchemy import select

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import CONTRACT_VERSION, parse_contract
        from shared.design.merge import merged_scene_sequence

        outcomes_text = "\n".join(f"{o['id']}: {o['text']}." for o in OUTCOMES)
        project = Project(id=_uuid.uuid4(), name="12g round trip", state="DRAFT",
                          learning_outcomes=outcomes_text)
        db_session.add(project)
        await db_session.flush()

        emission = _emission(scenes=[
            _sourced("LO-1", narration_text="teach it"),
            _sourced("LO-2", event="guide", narration_text="guide it"),
            _sourced("LO-3", narration_text="show the check"),
        ], practice={
            # ⛳ ORIGIN FREE, exercised: LO-1's practice is the script's own
            # "now you try" span; the other two are invented.
            "LO-1": [_sourced("LO-1", "practice")],
            "LO-2": [_designed("LO-2", "practice")],
            "LO-3": [_designed("LO-3", "practice")],
        })

        # ── the scene rows the FROZEN stage body would have written, which is
        # the merged sequence handed to it by the document transform. They must
        # exist before the brief is recorded for `apply_scene_design` to match.
        for scene in merged_scene_sequence(emission):
            db_session.add(StoryboardScene(
                project_id=project.id, scene_index=scene["scene_index"],
                narration_text=scene["narration_text"],
                visual_description=scene["visual_description"],
                media_type=scene["media_type"],
                duration_seconds=scene["duration_seconds"]))
        await db_session.flush()

        payload = parse_contract(emission)
        assert payload["contract_version"] == CONTRACT_VERSION
        brief = await DesignBriefService(db_session).record(project.id, payload)
        await db_session.refresh(brief)

        # ── the brief, IN THE DATABASE ──
        assert len(brief.scene_designs) == 9
        assert brief.evidence_map == {"LO-1": [1, 2], "LO-2": [4, 5],
                                      "LO-3": [7, 8]}
        # VERBATIM, including the full stop this test's `outcomes_text` added —
        # the operator's line is what lands in `text`, never a normalisation.
        assert [o["text"] for o in brief.outcomes] == [
            f"{o['text']}." for o in OUTCOMES]

        # ── the SCENE ROWS carry the declarations, matched by merged index ──
        rows = list((await db_session.execute(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == project.id)
            .order_by(StoryboardScene.scene_index))).scalars().all())
        assert [r.instructional_event for r in rows] == [
            "present", "practice", "assess",
            "guide", "practice", "assess",
            "present", "practice", "assess"]
        assert [r.scene_origin for r in rows] == [
            "sourced", "sourced", "designed",
            "sourced", "designed", "designed",
            "sourced", "designed", "designed"]
        # ⛔ migration 0048's XOR, on rows the evidence layer wrote: a designed
        # scene carries its reason and no spans, a sourced one the reverse.
        assert all(r.designed_rationale for r in rows if r.scene_origin == "designed")
        assert all(r.source_refs is None
                   for r in rows if r.scene_origin == "designed")
        assert all(r.designed_rationale is None
                   for r in rows if r.scene_origin == "sourced")
        assert all(r.source_refs for r in rows if r.scene_origin == "sourced")

        # ── and the gate reads it clean off the ROWS, not off the payload ──
        findings, coverage = review(
            scenes=rows, outcomes=brief.outcomes,
            assessment_plan=brief.assessment_plan,
            learning_outcomes=outcomes_text)
        refusals, _ = split(findings)
        assert [f.code for f in refusals] == [], [f.code for f in refusals]
        assert all(r.served and r.assessed for r in coverage)
