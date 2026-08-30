"""WP-IVGS-12f — the excerpter is FORCED to design.

⛔ THE MEASUREMENT THESE TESTS PROTECT

Six generations under two prompt versions produced 83 scenes: 83 `sourced`,
0 `designed`, 0 `assess` (RC-Q9e). The prompt had invited invention since v8 and
the invitation was declined 83 times out of 83.

⛳ AND THE 12f MEASUREMENT CHANGED THE DIAGNOSIS, WHICH IS WHY THESE TESTS EXIST
IN THIS SHAPE. Two more scripts, same stack, same prompt v5:

    B1  contains an EXPLICIT unaided problem ("Now you try. Work out 63 minus
        48. Pause here.") -> 21 scenes, 21 sourced, 0 designed, 0 assess. The
        model FOUND the span and anchored three scenes to it — and labelled them
        `practice`.
    B2  SPARSE: teaches a procedure, no practice material at all -> 15 scenes,
        10 sourced, 5 DESIGNED, 1 assess. The first designed scenes and the first
        `assess` event this project has recorded.

So the model can invent and does invent — when there is nothing to excerpt.
Given anything anchorable it anchors. Contract-4 put sourced and designed
material in one `scenes[]` array where they compete for the same slots, and
sourced won every time.

Contract-5 removes the competition instead of arguing with it. These tests pin
the three moves:

  FORCE   `designed_assessments` is REQUIRED, one key per outcome,
          `additionalProperties: false`, and each value's grammar pins
          origin/event/serves. An emission without one invented unaided scene
          per outcome is not parseable.

  PLACE   the model is never asked WHERE. `shared.design.merge` inserts each
          after the LAST scene serving its outcome and re-indexes the sequence.
          12b's principle, third application.

  BELT    `PLAN_ENTRY_UNREALIZED(assess)` and `OUTCOME_UNASSESSED` become
          structurally unreachable — asserted here directly — and BOTH CHECKS
          STAY, because a structural guarantee is a claim about code that some
          later edit can quietly falsify.
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


def _designed(oid, **kw):
    """One designed assessment as the grammar constrains it."""
    base = {
        "provenance": {"origin": "designed",
                       "rationale": "the script contains no unaided attempt"},
        "instructional_event": "assess",
        "serves_outcomes": [oid],
        "narration_text": f"Now work out 45 times 12 on your own. ({oid})",
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


def _emission(scenes=None, designed=None, plan_kind="assess"):
    """A whole contract-5 emission, of the shape the decoder would accept."""
    return {
        "assessment_plan": {
            oid: {"evidence_kind": plan_kind, "learner_does": "does the thing"}
            for oid in IDS
        },
        "designed_assessments": dict(
            designed if designed is not None else {oid: _designed(oid) for oid in IDS}
        ),
        "outcome_notes": {oid: {"bloom_level": "apply", "measurable": True,
                                "proposed_refinement": None} for oid in IDS},
        "scenes": list(scenes if scenes is not None
                       else [_sourced("LO-1"), _sourced("LO-2"), _sourced("LO-3")]),
        "dropped_beats": [],
        "design_notes": "an arc",
    }


# ---------------------------------------------------------------------------
# FORCE — the grammar does not ask, it demands
# ---------------------------------------------------------------------------

class TestTheExcerpterCannotDecline:

    def test_designed_assessments_is_required_with_one_key_per_outcome(self):
        schema = _contract().design_contract_schema(outcome_ids=IDS)
        assert "designed_assessments" in schema["required"]
        block = schema["properties"]["designed_assessments"]
        assert sorted(block["required"]) == sorted(IDS)
        assert sorted(block["properties"]) == sorted(IDS)
        # RC-Q12: the construct measured ENFORCED in 12c, reused not re-invented.
        assert block["additionalProperties"] is False

    @pytest.mark.parametrize("oid", IDS)
    def test_the_three_pins_are_single_value_enums(self, oid):
        """origin, event and the served outcome are NOT the model's decisions.

        Single-value `enum` and not `const`: both were measured implemented and
        ENFORCED on the pinned engine for this package, under a prompt ordering
        each one broken, so the order's tie-break applies and the proven
        construct wins.
        """
        entry = (_contract().design_contract_schema(outcome_ids=IDS)
                 ["properties"]["designed_assessments"]["properties"][oid])
        props = entry["properties"]
        assert props["instructional_event"]["enum"] == ["assess"]
        assert props["provenance"]["properties"]["origin"]["enum"] == ["designed"]
        assert props["serves_outcomes"]["items"]["enum"] == [oid]

    def test_the_designed_branch_cannot_cite_a_span(self):
        entry = (_contract().design_contract_schema(outcome_ids=IDS)
                 ["properties"]["designed_assessments"]["properties"]["LO-1"])
        prov = entry["properties"]["provenance"]
        assert sorted(prov["properties"]) == ["origin", "rationale"]
        assert prov["additionalProperties"] is False
        assert "source_refs" not in entry["properties"]

    def test_the_model_is_not_asked_where_it_goes(self):
        """12b's principle: never ask the model for what code can compute."""
        entry = (_contract().design_contract_schema(outcome_ids=IDS)
                 ["properties"]["designed_assessments"]["properties"]["LO-1"])
        assert "scene_index" not in entry["properties"]
        assert "scene_index" not in entry["required"]

    def test_every_array_is_bounded(self):
        """RC-Q12. `minItems` with no maximum is a runaway on this engine."""
        entry = (_contract().design_contract_schema(outcome_ids=IDS)
                 ["properties"]["designed_assessments"]["properties"]["LO-1"])
        for name, prop in entry["properties"].items():
            if prop.get("type") == "array":
                assert "maxItems" in prop, f"{name} is an unbounded array"

    def test_declared_second_so_it_is_generated_before_any_scene(self):
        """Declaration order binds generation order (12d, measured).

        Second, not last: the model authors the unaided attempt while `scenes`
        is still empty, so it has no worked example of its own to lift numbers
        out of. Moving this down the properties dict would silently turn an
        authored assessment into a rationalised one and no membership check
        would notice — which is exactly what happened to `outcome_notes` in 12c.
        """
        order = list(_contract().design_contract_schema(
            outcome_ids=IDS)["properties"])
        assert order[0] == "assessment_plan"
        assert order[1] == "designed_assessments"
        assert order.index("designed_assessments") < order.index("scenes")

    def test_no_outcomes_means_nothing_to_force(self):
        """An empty required-key object is a grammar demanding a key set that
        does not exist. The degraded path keeps its 12b/12d behaviour."""
        schema = _contract().design_contract_schema(outcome_ids=[])
        assert "designed_assessments" not in schema["properties"]
        assert "designed_assessments" not in schema["required"]


# ---------------------------------------------------------------------------
# PLACE — the merge, and it is code
# ---------------------------------------------------------------------------

class TestPlacementIsDerivedNeverAuthored:

    def test_each_assessment_lands_after_the_last_scene_serving_its_outcome(self):
        from shared.design.merge import merged_scene_sequence

        merged = merged_scene_sequence(_emission(scenes=[
            _sourced("LO-1", narration_text="a"),
            _sourced("LO-2", narration_text="b"),
            _sourced("LO-1", event="guide", narration_text="c"),
            _sourced("LO-3", narration_text="d"),
        ]))
        shape = [(s["instructional_event"], s["serves_outcomes"][0])
                 for s in merged]
        assert shape == [
            ("present", "LO-1"),
            ("present", "LO-2"),
            ("assess", "LO-2"),     # LO-2's last serving scene is index 1
            ("guide", "LO-1"),
            ("assess", "LO-1"),     # LO-1's last serving scene is index 2
            ("present", "LO-3"),
            ("assess", "LO-3"),
        ]

    def test_the_sequence_is_reindexed_contiguously(self):
        from shared.design.merge import merged_scene_sequence

        merged = merged_scene_sequence(_emission())
        assert [s["scene_index"] for s in merged] == list(range(len(merged)))

    def test_an_unserved_outcome_puts_its_assessment_at_the_end(self):
        """No fading sequence to end, so it goes last — and the gate flags it
        as an attempt at something the lesson never taught."""
        from shared.design.merge import anchor_positions, merged_scene_sequence

        emission = _emission(scenes=[_sourced("LO-1")])
        assert anchor_positions(emission["scenes"], IDS) == {
            "LO-1": 0, "LO-2": -1, "LO-3": -1}
        merged = merged_scene_sequence(emission)
        assert [s["serves_outcomes"][0] for s in merged] == [
            "LO-1", "LO-1", "LO-2", "LO-3"]

    def test_the_models_own_scenes_are_not_edited(self):
        from shared.design.merge import merged_scene_sequence

        emission = _emission()
        before = [dict(s) for s in emission["scenes"]]
        merged_scene_sequence(emission)
        assert emission["scenes"] == before

    def test_a_contract_without_designed_assessments_is_the_identity(self):
        """Every pre-contract-5 brief still round-trips, re-indexed only."""
        from shared.design.merge import merged_scene_sequence

        emission = _emission()
        del emission["designed_assessments"]
        merged = merged_scene_sequence(emission)
        assert len(merged) == 3
        assert all(s["provenance"]["origin"] == "sourced" for s in merged)

    def test_the_parse_returns_the_merged_sequence(self):
        payload = _contract().parse_contract(_emission())
        assert payload["contract_version"] == "design-contract-5"
        assert len(payload["scenes"]) == 6
        designed = [s for s in payload["scenes"]
                    if s["scene_origin"] == "designed"]
        assert len(designed) == 3
        assert all(s["instructional_event"] == "assess" for s in designed)
        assert all(s["designed_rationale"] for s in designed)
        # The evidence limb is the model's OWN emission and is not merged.
        assert len(payload["raw_contract"]["scenes"]) == 3

    def test_the_derived_evidence_map_names_the_merged_indices(self):
        payload = _contract().parse_contract(_emission())
        from shared.design.evidence import derive_evidence_map

        by_index = {s["scene_index"]: s for s in payload["scenes"]}
        for oid, indices in derive_evidence_map(payload["scenes"], IDS).items():
            assert indices, f"{oid} has no evidence"
            for i in indices:
                assert oid in by_index[i]["serves_outcomes"]
                assert by_index[i]["instructional_event"] == "assess"


# ---------------------------------------------------------------------------
# BELT — unreachable, and kept anyway
# ---------------------------------------------------------------------------

class TestTheRefusalsThatCanNoLongerFire:

    def _review(self, emission):
        from app.services.design_review import review

        payload = _contract().parse_contract(emission)
        scenes = []
        for row, raw in zip(payload["scenes"],
                            __import__("shared.design.merge", fromlist=["x"])
                            .merged_scene_sequence(emission)):
            scenes.append({**row,
                           "narration_text": raw.get("narration_text"),
                           "media_type": raw.get("media_type"),
                           "media_rationale": raw.get("media_rationale"),
                           "generation_params": raw.get("generation_params")})
        return review(scenes=scenes, outcomes=OUTCOMES,
                      assessment_plan=emission["assessment_plan"],
                      dropped_beats=[], source_text="", learning_outcomes="\n".join(
                          f"{o['id']}: {o['text']}" for o in OUTCOMES))

    def test_plan_entry_unrealized_is_unreachable_for_assess(self):
        findings, _ = self._review(_emission(plan_kind="assess"))
        assert not [f for f in findings if f.code == "PLAN_ENTRY_UNREALIZED"]

    def test_outcome_unassessed_is_unreachable(self):
        findings, rows = self._review(_emission())
        assert not [f for f in findings if f.code == "OUTCOME_UNASSESSED"]
        assert all(r.assessed for r in rows)

    def test_it_holds_even_when_no_emitted_scene_assesses_anything(self):
        """The hostile case: a pure lecture in `scenes`. Under contract-4 this
        was three OUTCOME_UNASSESSED refusals every time (RC-Q9d)."""
        findings, rows = self._review(_emission(scenes=[
            _sourced(oid, event="present") for oid in IDS]))
        assert not [f for f in findings
                    if f.code in ("OUTCOME_UNASSESSED", "PLAN_ENTRY_UNREALIZED")]
        assert all(r.assessed for r in rows)

    def test_the_practice_branch_still_refuses(self):
        """Contract-5 forces an `assess` scene, NOT a `practice` one. A plan
        promising guided practice and never building it is refused exactly as
        it was under contract-4 — the check is not weakened, only bypassed for
        the one kind the grammar now guarantees."""
        findings, _ = self._review(_emission(plan_kind="practice"))
        codes = [f.code for f in findings if f.severity == "refuse"]
        assert codes.count("PLAN_ENTRY_UNREALIZED") == 3

    def test_the_check_is_still_in_the_code(self):
        """⛔ The belt. Deleting an unreachable check is how the guarantee stops
        being measurable the day someone edits the schema."""
        import inspect

        from app.services import design_review

        assert "PLAN_ENTRY_UNREALIZED" in inspect.getsource(design_review)
        assert "OUTCOME_UNASSESSED" in inspect.getsource(design_review)

    def test_an_untaught_outcome_is_flagged_not_silently_passed(self):
        """⚠ 12f's OWN COST, pinned rather than left to be discovered.

        `OUTCOME_UNSERVED` asks whether any scene declares the outcome, and a
        designed assessment declares it — so an outcome the lesson never TEACHES
        is no longer unserved. `PRACTICE_NOT_PREPARED` is what remains and it
        names exactly that shape. It is a FLAG; promoting it is an operator
        ruling this package did not take."""
        findings, _ = self._review(_emission(scenes=[_sourced("LO-1")]))
        codes = [f.code for f in findings]
        assert "OUTCOME_UNSERVED" not in codes
        assert codes.count("PRACTICE_NOT_PREPARED") == 2   # LO-2 and LO-3


# ---------------------------------------------------------------------------
# The prompt, and the storage
# ---------------------------------------------------------------------------

class TestThePromptAndTheStorage:

    def _prompt(self):
        return (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_design_system.j2").read_text(encoding="utf-8")

    def test_v6_says_the_assessments_are_the_designers_own_work(self):
        text = self._prompt()
        for phrase in ("THE ASSESSMENTS ARE YOURS TO AUTHOR",
                       "designed_assessments",
                       "ONE ENTRY PER OUTCOME ID",
                       "POSE THE PROBLEM COLD, IN FRESH NUMBERS THE SCRIPT NEVER WORKED",
                       "AND YOU DO NOT PLACE THEM"):
            assert phrase in text, phrase

    def test_v6_removed_nothing_v5_gated(self):
        """The 12e discipline: this package earns its keep by adding.

        Every phrase the publisher gated before 12f must still be present —
        read from the publisher itself so the two lists cannot drift.
        """
        src = (REPO / "ivgs-api" / "app" / "scripts"
               / "wpivgs12_publish_design_prompts.py").read_text(encoding="utf-8")
        segment = src[src.index("DESIGN_PHRASES"):src.index("#: The extraction prompt")]
        namespace: dict = {}
        exec(compile(segment.replace("DESIGN_PHRASES: Tuple[str, ...] =",
                                     "DESIGN_PHRASES =", 1), "phrases", "exec"),
             namespace)
        text = self._prompt()
        assert [p for p in namespace["DESIGN_PHRASES"] if p in text] == \
            list(namespace["DESIGN_PHRASES"])

    def test_the_rationale_reaches_the_scene_row(self):
        """Migration 0052. `scene_origin='designed'` with no account of itself
        is the silent-invention defect one layer down."""
        from app.models.storyboard_scene import StoryboardScene
        from app.services.design_brief_service import SCENE_DESIGN_FIELDS, _clean

        assert hasattr(StoryboardScene, "designed_rationale")
        assert "designed_rationale" in SCENE_DESIGN_FIELDS
        cleaned = _clean(_contract().parse_contract(_emission())["scenes"][1])
        assert cleaned["scene_origin"] == "designed"
        assert cleaned["designed_rationale"]
        assert cleaned["source_refs"] is None

    def test_a_sourced_scene_never_keeps_a_stale_rationale(self):
        """`_clean` writes the declaration WHOLE — the 12b lesson that cost a
        CHECK violation and a whole brief."""
        from app.services.design_brief_service import _clean

        assert _clean({"scene_index": 0, "scene_origin": "sourced",
                       "source_refs": [{"start": 0, "end": 1}],
                       "designed_rationale": "left over"}
                      )["designed_rationale"] is None

    def test_the_worker_transform_hands_the_merged_list_to_the_frozen_body(self):
        """Without this the assessment is designed, stored, reviewed — and never
        rendered, because the frozen body builds rows from `scenes`."""
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core import capture

        capture._armed.set({"task_name": capture.STORYBOARD_TASK, "job_id": "j",
                            "project_id": "p", "stage": "storyboard", "seen": False})
        try:
            out = capture.transform_document(_emission())
            assert len(out["scenes"]) == 6
            assert sum(1 for s in out["scenes"]
                       if s["provenance"]["origin"] == "designed") == 3
            # Anything it does not recognise passes through untouched.
            assert capture.transform_document({"scenes": []}) == {"scenes": []}
            assert capture.transform_document("not a document") == "not a document"
        finally:
            capture._armed.set(None)

    def test_the_transform_is_inert_when_the_stage_is_not_storyboard(self):
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core import capture

        capture._armed.set(None)
        emission = _emission()
        assert capture.transform_document(emission) is emission


# ---------------------------------------------------------------------------
# The storage round trip, against the database — the 12d lesson, kept
# ---------------------------------------------------------------------------

class TestTheContractFiveRoundTrip:
    """⛔ 12d LEARNED THIS THE EXPENSIVE WAY AND 12f DOES NOT RE-LEARN IT.

    Contract-5 changes the worker's parse AND adds a column the ingest writes,
    so "the storage round-trip was not re-exercised" would be a caveat covering
    the exact seam most likely to break. This drives a real contract-5 emission
    through the worker's parse, the API's service and the gate, against the
    database, in one pass — including the merged indices, which are what
    `apply_scene_design` matches scene ROWS on.
    """

    async def test_a_contract_five_emission_survives_parse_store_and_gate(
        self, db_session,
    ):
        import uuid as _uuid

        from app.models.project import Project
        from app.models.storyboard_scene import StoryboardScene
        from app.services.design_brief_service import DesignBriefService
        from app.services.design_review import review, split
        from sqlalchemy import select

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import parse_contract
        from shared.design.merge import merged_scene_sequence

        outcomes_text = "\n".join(f"{o['id']}: {o['text']}." for o in OUTCOMES)
        project = Project(id=_uuid.uuid4(), name="12f round trip", state="DRAFT",
                          learning_outcomes=outcomes_text)
        db_session.add(project)
        await db_session.flush()

        emission = _emission(scenes=[
            _sourced("LO-1", narration_text="teach it"),
            _sourced("LO-2", event="guide", narration_text="guide it"),
            _sourced("LO-3", narration_text="show the check"),
        ])

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
        assert payload["contract_version"] == "design-contract-5"
        brief = await DesignBriefService(db_session).record(project.id, payload)
        await db_session.refresh(brief)

        # ── the brief, IN THE DATABASE ──
        assert len(brief.scene_designs) == 6
        assert brief.evidence_map == {"LO-1": [1], "LO-2": [3], "LO-3": [5]}
        # VERBATIM, including the full stop this test's `outcomes_text` added —
        # the operator's line is what lands in `text`, never a normalisation of it.
        assert [o["text"] for o in brief.outcomes] == [
            f"{o['text']}." for o in OUTCOMES]
        assert all(o["authored_by"] == "operator" for o in brief.outcomes)

        # ── the SCENE ROWS carry the declarations, matched by merged index ──
        rows = list((await db_session.execute(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == project.id)
            .order_by(StoryboardScene.scene_index))).scalars().all())
        assert [r.instructional_event for r in rows] == [
            "present", "assess", "guide", "assess", "present", "assess"]
        assert [r.scene_origin for r in rows] == [
            "sourced", "designed", "sourced", "designed", "sourced", "designed"]
        # ⛔ migration 0052: the invented scene arrives WITH its reason, and the
        # sourced ones carry none.
        assert all(r.designed_rationale for r in rows if r.scene_origin == "designed")
        assert all(r.designed_rationale is None
                   for r in rows if r.scene_origin == "sourced")
        assert all(r.source_refs is None
                   for r in rows if r.scene_origin == "designed")

        # ── and the gate reads it clean off the ROWS, not off the payload ──
        findings, coverage = review(
            scenes=rows, outcomes=brief.outcomes,
            assessment_plan=brief.assessment_plan,
            learning_outcomes=outcomes_text)
        refusals, _ = split(findings)
        assert [f.code for f in refusals] == [], [f.code for f in refusals]
        assert all(r.served and r.assessed for r in coverage)

    async def test_a_regenerate_clears_a_stale_designed_rationale(
        self, db_session,
    ):
        """The RC-Q10 shape, for the field 12f adds: a scene that was designed
        in one generation and sourced in the next must not keep the old reason
        readable and false on the row."""
        import uuid as _uuid

        from app.models.project import Project
        from app.models.storyboard_scene import StoryboardScene
        from app.services.design_brief_service import DesignBriefService
        from sqlalchemy import select

        project = Project(id=_uuid.uuid4(), name="12f regenerate", state="DRAFT",
                          learning_outcomes="LO-1: compute the product.")
        db_session.add(project)
        db_session.add(StoryboardScene(project_id=project.id, scene_index=0,
                                       narration_text="n", media_type="image"))
        await db_session.flush()

        service = DesignBriefService(db_session)
        await service.apply_scene_design(project.id, {
            "scene_index": 0, "scene_origin": "designed",
            "source_refs": None, "designed_rationale": "invented for the check"})
        row = await db_session.scalar(
            select(StoryboardScene).where(StoryboardScene.project_id == project.id))
        await db_session.refresh(row)
        assert row.designed_rationale == "invented for the check"

        await service.apply_scene_design(project.id, {
            "scene_index": 0, "scene_origin": "sourced",
            "source_refs": [{"transcript_id": None, "start": 0, "end": 4,
                             "quote": "text"}]})
        await db_session.refresh(row)
        assert row.scene_origin == "sourced"
        assert row.designed_rationale is None
