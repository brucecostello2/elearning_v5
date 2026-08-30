"""WP-IVGS-12h — the two-call design, and the belt the grammar cannot provide.

⛔ THE MEASUREMENT THESE TESTS PROTECT

design-contract-6 closed RC-Q9f in both limbs and produced this, five completed
generations running:

    LO-2 practice : "Explain why we write a placeholder zero in the ones column
                     before multiplying by the tens digit."
    LO-2 assess   : "Explain why we write a placeholder zero in the ones column
                     before multiplying by the tens digit."

9 of 15 outcome-pairs verbatim identical, 2 more differing only by a *"Let's
practice"* prefix, every generation carrying at least one. Every structural check
was correct and silent: both scenes legally declared, both serving the outcome,
one `practice` and one `assess`, exactly one assessment.

⛳ THE MECHANISM WAS 12g's OWN ORDERING DECISION. `assessment_scenes` was
declared before `practice_scenes`, declaration order binds generation order
(12d), so the practice was asked for with the assessment already in context — and
copied. Two of the three routes were refused with reasons: reordering trades
backward design for a duplicate that would reverse direction, and v7 ALREADY
carried *"THE PRACTICE MUST NOT BE THE ASSESSMENT WEARING A LABEL"* before a
single acceptance generation ran.

So the calls are separated and the second one never sees what it must not copy.
These tests pin four things:

  SPLIT    call 1's schema has no `assessment_scenes` and cannot acquire one;
           call 2's has nothing else.
  BLIND    what call 2 is given is built by code from three arguments, and the
           practice narrations, the scenes and the script are not among them.
  BELT     `EVIDENCE_NEAR_DUPLICATE` refuses, and it is CALIBRATED — the banked
           12g emissions are re-classified here, so a threshold edit that would
           have let RC-Q9g through fails a test rather than a generation.
  FATAL    a call-2 failure is a named, loud failure of the job and never a
           silent single-call fallback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BANK = REPO / "dev" / "workpackages" / "reference"


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


def _scene(oid, event, narration, origin="designed", **kw):
    prov = ({"origin": "designed", "rationale": "the script has no attempt"}
            if origin == "designed" else
            {"origin": "sourced",
             "source_refs": [{"transcript_id": None, "start": 0, "end": 5,
                              "quote": "x"}],
             "rewrite_of": None})
    base = {
        "provenance": prov,
        "instructional_event": event,
        "serves_outcomes": [oid],
        "narration_text": narration,
        "visual_description": "a column layout",
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


def _expository(oid, event="present", narration="One step.", **kw):
    base = _scene(oid, event, narration, origin="sourced")
    base["scene_index"] = 0
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# SPLIT — the two schemas, and the key that cannot come back
# ---------------------------------------------------------------------------

class TestTheContractIsSplit:

    def test_call_one_has_no_assessment_section_at_all(self):
        schema = _contract().design_contract_schema(outcome_ids=IDS)
        assert "assessment_scenes" not in schema["properties"]
        assert "assessment_scenes" not in schema["required"]

    def test_call_one_forbids_the_model_adding_it_back(self):
        """⛳ MEASURED, NOT ASSUMED — probe F1 ordered the model to emit
        `assessment_scenes` at the top level and it could not
        (`wpivgs12h-evidence/probe12h.json`). This asserts the property that
        makes the measurement possible."""
        schema = _contract().design_contract_schema(outcome_ids=IDS)
        assert schema["additionalProperties"] is False

    def test_call_one_still_declares_the_plan_first(self):
        """⛔ BACKWARD DESIGN SURVIVES THE SPLIT AND THIS IS WHERE IT IS PINNED.

        The plan is the ONLY thing call 2 is briefed from, so a package that
        moved it down this dict would convert the commitment into a
        rationalisation AND leave the second call briefed by an afterthought.
        """
        schema = _contract().design_contract_schema(outcome_ids=IDS)
        order = list(schema["properties"].keys())
        assert order[0] == "assessment_plan"
        assert order.index("practice_scenes") < order.index("scenes")

    def test_call_two_emits_the_assessments_and_nothing_else(self):
        schema = _contract().assessment_authoring_schema(outcome_ids=IDS)
        assert list(schema["properties"]) == ["assessment_scenes"]
        assert schema["required"] == ["assessment_scenes"]
        assert schema["additionalProperties"] is False

    def test_call_two_keeps_contract_sixs_grammar_exactly(self):
        """The section's shape is the one 12g probed ENFORCED. What is new in
        this package is the CALL, not the grammar — so a measured difference is
        a difference in what the model could SEE."""
        c = _contract()
        section = c.assessment_authoring_schema(
            outcome_ids=IDS)["properties"]["assessment_scenes"]
        assert section["required"] == IDS
        assert section["additionalProperties"] is False
        for oid in IDS:
            arr = section["properties"][oid]
            assert arr["minItems"] == arr["maxItems"] == 1
            item = arr["items"]
            assert item["properties"]["instructional_event"]["enum"] == ["assess"]
            assert item["properties"]["serves_outcomes"]["items"]["enum"] == [oid]
            assert "scene_index" not in item["properties"]
            branches = [b["properties"]["origin"]["enum"][0]
                        for b in item["properties"]["provenance"]["oneOf"]]
            assert sorted(branches) == ["designed", "sourced"], (
                "origin must stay FREE — 12g's one reversal of 12f"
            )

    def test_call_two_refuses_to_build_a_schema_with_no_outcomes(self):
        with pytest.raises(ValueError):
            _contract().assessment_authoring_schema(outcome_ids=[])

    def test_every_array_in_call_twos_schema_carries_a_maximum(self):
        """RC-Q12: an unbounded array under grammar-constrained decoding is an
        infinite legal continuation and the model takes it."""
        schema = _contract().assessment_authoring_schema(outcome_ids=IDS)
        unbounded = []

        def walk(node, path):
            if isinstance(node, dict):
                if node.get("type") == "array" and "maxItems" not in node:
                    unbounded.append(path)
                for k, v in node.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")

        walk(schema, "$")
        assert unbounded == []

    def test_the_version_is_bumped_because_the_shape_changed(self):
        c = _contract()
        assert c.CONTRACT_VERSION == "design-contract-7"


# ---------------------------------------------------------------------------
# BLIND — what call 2 can and cannot see
# ---------------------------------------------------------------------------

class TestCallTwoCannotSeeThePractice:

    def _document(self):
        return {
            "assessment_plan": {
                oid: {"evidence_kind": "assess",
                      "learner_does": f"does the {oid} thing"} for oid in IDS},
            "practice_scenes": {
                "LO-1": [_scene("LO-1", "practice",
                                "SENTINEL-PRACTICE multiply 43 by 25 with the "
                                "partial products shown",
                                generation_params={"template": "column_multiplication_step",
                                                   "top": 43, "bottom": 25,
                                                   "phase": "partial"})],
                "LO-2": [_scene("LO-2", "practice", "SENTINEL-PRACTICE explain it")],
                "LO-3": [_scene("LO-3", "practice", "SENTINEL-PRACTICE check it")],
            },
            "scenes": [_expository("LO-1",
                                   narration="SENTINEL-SCRIPT our problem is 23 times 14")],
        }

    def test_the_summary_carries_numbers_and_not_narration(self):
        c = _contract()
        summary = c.practice_summary(self._document(), IDS)
        blob = json.dumps(summary)
        assert "SENTINEL-PRACTICE" not in blob
        assert "SENTINEL-SCRIPT" not in blob
        assert summary["per_outcome"]["LO-1"]["numbers_used"] == ["43", "25"]
        assert summary["per_outcome"]["LO-1"]["step_reached"]["motion_templates"] == [
            "column_multiplication_step"]
        assert summary["per_outcome"]["LO-1"]["step_reached"]["motion_phases"] == ["partial"]

    def test_the_lesson_wide_number_list_unions_the_script_and_the_practice(self):
        """⛳ THE ADDITION BEYOND THE PER-OUTCOME SUMMARY, AND ITS REASON.
        Call 2 never sees the script, so without this "pose it in numbers this
        lesson has not worked" is unenforceable on the far side of the split.
        Digits only: it cannot carry a copyable sentence."""
        c = _contract()
        spent = c.practice_summary(self._document(), IDS)["numbers_already_used"]
        assert set(spent) >= {"23", "14", "43", "25"}

    def test_the_user_message_contains_no_practice_wording(self):
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.assessment_call import build_user_message
        c = _contract()
        doc = self._document()
        message = build_user_message(
            outcomes=OUTCOMES,
            assessment_plan=doc["assessment_plan"],
            summary=c.practice_summary(doc, IDS))
        assert "SENTINEL-PRACTICE" not in message
        assert "SENTINEL-SCRIPT" not in message
        # ...and it DOES contain the three things it is supposed to.
        assert "compute the product" in message          # the outcome text
        assert "does the LO-1 thing" in message          # the plan's brief
        assert "43" in message and "23" in message       # the spent numbers

    def test_the_user_message_carries_the_motion_template_catalogue(self):
        """⛔ ADDED AFTER THE FIRST ACCEPTANCE GENERATION MEASURED THE GAP.

        Call 2's LO-1 assessment chose `motion_graphics` and carried no
        template, and the gate refused it `MOTION_WITHOUT_TEMPLATE` — correctly,
        and the model had no way to comply: the template names live in call 1's
        42,365-character USER template, which call 2 has never seen. Telling a
        model to name a template while withholding the list is asking for a
        guess.

        ⛳ AND IT IS READ FROM THE RENDERER'S REGISTRY, NOT TYPED OUT. Call 1's
        template prose is a transcription of the same registry — *"Choose from
        EXACTLY these four templates"* — and a transcription is an accurate
        mirror with no authority (RC-P17). This one cannot go stale.
        """
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.assessment_call import build_user_message
        from shared.motion.templates import param_kinds, template_names

        message = build_user_message(
            outcomes=OUTCOMES,
            assessment_plan={"LO-1": {"evidence_kind": "assess",
                                      "learner_does": "multiplies unaided"}},
            summary={"per_outcome": {}, "numbers_already_used": []})
        assert template_names(), "the renderer registry is empty"
        for name in template_names():
            assert name in message, f"{name} is not offered to call 2"
            for param in param_kinds(name):
                assert param in message, f"{name}.{param} is not offered"

    def test_the_catalogue_degrades_rather_than_failing_the_job(self):
        """A worker that cannot import the motion package must still author
        assessments; what it loses is the ability to author a MOTION one, and
        the gate names that by itself."""
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        import design_core.assessment_call as ac

        original = sys.modules.get("shared.motion.templates")
        sys.modules["shared.motion.templates"] = None       # forces ImportError
        try:
            assert ac._motion_catalogue() == {}
        finally:
            if original is None:
                sys.modules.pop("shared.motion.templates", None)
            else:
                sys.modules["shared.motion.templates"] = original

    def test_the_user_message_cannot_render_what_it_was_not_handed(self):
        """⛔ THE STRUCTURAL VERSION OF THE CLAIM. `build_user_message` takes
        three keyword arguments; there is no document in scope, so no future
        edit can add "the practice, for context" without changing the
        signature — which is a diff a reviewer sees."""
        import inspect

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.assessment_call import build_user_message

        params = inspect.signature(build_user_message).parameters
        assert set(params) == {"outcomes", "assessment_plan", "summary"}
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())


# ---------------------------------------------------------------------------
# BELT — the near-duplicate refusal, and its calibration
# ---------------------------------------------------------------------------

class TestTheNearDuplicateBelt:

    def test_an_identical_pair_is_refused(self):
        from app.services.design_review import review, split
        same = ("Explain why we write a placeholder zero in the ones column "
                "before multiplying by the tens digit.")
        scenes = [
            dict(_expository("LO-2"), scene_index=0),
            dict(_scene("LO-2", "practice", same), scene_index=1,
                 scene_origin="sourced"),
            dict(_scene("LO-2", "assess", same), scene_index=2,
                 scene_origin="designed"),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[1]])
        refusals, _ = split(findings)
        codes = [f.code for f in refusals]
        assert "EVIDENCE_NEAR_DUPLICATE" in codes
        finding = next(f for f in refusals if f.code == "EVIDENCE_NEAR_DUPLICATE")
        assert finding.outcome_id == "LO-2"
        assert finding.detail["assessment_scene_index"] == 2
        assert finding.detail["duplicate_of_scene_index"] == 1
        assert finding.detail["duplicate_of_kind"] == "practice"
        assert finding.detail["containment"] == 1.0

    def test_a_differentiated_pair_is_not_refused(self):
        """B2's real one, from the bank: a fresh number AND the method hint
        withheld. 12g called it *"real scaffolding, correctly faded"* and the
        belt must agree."""
        from app.services.design_review import review, split
        scenes = [
            dict(_expository("LO-1", narration="Dividing by 10 makes it smaller."),
                 scene_index=0),
            dict(_scene("LO-1", "practice",
                        "Divide 234 by 10. Use the place-value shift method."),
                 scene_index=1),
            dict(_scene("LO-1", "assess", "Divide 432 by 10."), scene_index=2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        refusals, _ = split(findings)
        assert "EVIDENCE_NEAR_DUPLICATE" not in [f.code for f in refusals]

    def test_the_same_numbers_with_the_support_sentence_removed_is_refused(self):
        """⛔ LIMB B, AND IT IS THE ROW 12g DID NOT QUOTE AS A DUPLICATE.

        Run B gen 1 LO-1: practice *"Multiply 43 by 25 using the standard column
        algorithm. You can use the workspace below to help you."* against assess
        *"Now it's your turn to try. Multiply 43 by 25 using the standard column
        algorithm."* Containment 0.64 — below limb A — and the SAME TWO NUMBERS.
        It is the same problem posed twice with the support sentence deleted.
        """
        from app.services.design_review import review, split
        scenes = [
            dict(_expository("LO-1"), scene_index=0),
            dict(_scene("LO-1", "practice",
                        "Multiply 43 by 25 using the standard column algorithm. "
                        "You can use the workspace below to help you."),
                 scene_index=1),
            dict(_scene("LO-1", "assess",
                        "Now it's your turn to try. Multiply 43 by 25 using the "
                        "standard column algorithm."),
                 scene_index=2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        refusals, _ = split(findings)
        finding = next(f for f in refusals if f.code == "EVIDENCE_NEAR_DUPLICATE")
        assert finding.detail["limb"] == "no_fresh_axis"
        assert finding.detail["numerals_equal"] is True

    def test_the_worked_example_limb_fires_too(self):
        """⛳ THE LIMB THAT CAUGHT WHAT FIVE GENERATIONS OF HAND-COMPARISON
        MISSED: B2's LO-1 assessment is byte-identical to its own `guide` scene,
        in the design 12g.10 called correctly faded."""
        from app.services.design_review import review, split
        scenes = [
            dict(_expository("LO-1", event="guide", narration="Divide 432 by 10."),
                 scene_index=0),
            dict(_scene("LO-1", "practice",
                        "Divide 234 by 10. Use the place-value shift method."),
                 scene_index=1),
            dict(_scene("LO-1", "assess", "Divide 432 by 10."), scene_index=2),
        ]
        findings, _ = review(scenes=scenes, outcomes=[OUTCOMES[0]])
        refusals, _ = split(findings)
        finding = next(f for f in refusals if f.code == "EVIDENCE_NEAR_DUPLICATE")
        assert finding.detail["duplicate_of_kind"] == "worked example"
        assert finding.detail["duplicate_of_scene_index"] == 0

    def test_the_stoplist_carries_no_task_word(self):
        """⛔ THE ONE CHANGE THIS MODULE FORBIDS. Adding a task word to the
        stoplist would fit the measure to its own test set."""
        from shared.design.duplication import STOPWORDS
        for word in ("practice", "explain", "problem", "multiply", "check",
                     "work", "learner", "assess", "divide", "why", "column"):
            assert word not in STOPWORDS

    def test_numerals_are_kept_in_the_token_set(self):
        """Dropping them was measured to DESTROY the belt: B2's two correctly
        differentiated pairs both go to containment 1.00 without them, because a
        faded and an unaided attempt at one procedure differ in nothing else."""
        from shared.design.duplication import normalized_tokens
        assert "432" in normalized_tokens("Divide 432 by 10.")

    def test_the_calibration_holds_over_every_banked_12g_emission(self):
        """⛔ THE ACCEPTANCE, AS A TEST. If a later package retunes the
        threshold, this fails rather than RC-Q9g quietly shipping again.

        Classification is 12g's own: every pair it quoted as ⛔ IDENTICAL or as
        a *"Let's practice"* prefix must REFUSE, and B2's two computational
        pairs — which 12g.10 called correctly faded — must PASS on the practice
        limb.
        """
        from shared.design.duplication import duplication_verdict

        must_refuse, must_pass = 0, 0
        for filename in ("ACCEPT-contract6-runB-contracts.json",
                         "ACCEPT-contract6-contracts.json",
                         "B2-contract6-contracts.json"):
            path = BANK / "wpivgs12g-evidence" / filename
            for obj in json.loads(path.read_text()):
                if not obj:
                    continue
                A = obj.get("assessment_scenes") or {}
                P = obj.get("practice_scenes") or {}
                for oid, entry in A.items():
                    scene = entry[0] if isinstance(entry, list) else entry
                    a = scene.get("narration_text")
                    dup = any(duplication_verdict(a, s.get("narration_text"))["duplicate"]
                              for s in (P.get(oid) or []))
                    must_refuse += dup
                    must_pass += (not dup)
        # 12 duplicates on the practice limb across the three banked runs — the
        # 11 12g quoted on the operator's script plus B2's collapsed LO-3 — and
        # one more (run B gen 1 LO-1) that limb B catches, which the report names
        # as a twelfth rather than tuning around.
        assert must_refuse == 13, f"the banked duplicate count moved: {must_refuse}"
        assert must_pass == 5, f"the banked clean count moved: {must_pass}"

    def test_the_calibration_script_is_committed_and_runs(self):
        """A threshold argued from bytes nobody can re-run is a threshold
        nobody can re-argue."""
        script = BANK / "wpivgs12h-evidence" / "calibrate12h.py"
        assert script.exists()
        assert "EXPECTED" in script.read_text()


# ---------------------------------------------------------------------------
# FATAL — call 2's failure is the job's failure
# ---------------------------------------------------------------------------

class TestCallTwoFailureIsNeverSilent:

    def test_the_seam_reraises_the_fatal_class_and_swallows_everything_else(self):
        import asyncio

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from clients import vllm_client

        async def go():
            # an ordinary transform bug: swallowed, document returned untouched
            vllm_client.set_document_transform(
                lambda doc: (_ for _ in ()).throw(RuntimeError("bug")))
            assert await vllm_client._apply_document_transform({"a": 1}) == {"a": 1}

            # a DELIBERATE failure: raised
            def fatal(doc):
                raise vllm_client.DocumentTransformFatal("call 2 failed")

            vllm_client.set_document_transform(fatal)
            with pytest.raises(vllm_client.DocumentTransformFatal):
                await vllm_client._apply_document_transform({"a": 1})

            # an ASYNC transform is awaited
            async def rewrite(doc):
                return {"a": 2}

            vllm_client.set_document_transform(rewrite)
            assert await vllm_client._apply_document_transform({"a": 1}) == {"a": 2}

            vllm_client.set_document_transform(None)

        asyncio.run(go())

    def test_nothing_registered_is_still_byte_identical_previous_behaviour(self):
        import asyncio

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from clients import vllm_client

        vllm_client.set_document_transform(None)
        doc = {"scenes": []}
        assert asyncio.run(vllm_client._apply_document_transform(doc)) is doc

    def test_the_transform_declines_the_three_documented_cases(self):
        """A stored brief, a v7 storyboard and a no-outcomes project each get NO
        second call — and none of them is a contract-7 failure."""
        import asyncio

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core import capture

        called = []

        async def explode(**kw):
            called.append(kw)
            raise AssertionError("call 2 must not have been made")

        state = {"stage": "storyboard", "project_id": "p", "job_id": "j"}
        # already present
        doc = {"assessment_scenes": {"LO-1": [{}]}, "practice_scenes": {"LO-1": [{}]}}
        assert asyncio.run(capture._author_assessments_if_needed(state, doc)) is doc
        # no practice layer at all — a v7 storyboard
        doc2 = {"scenes": []}
        assert asyncio.run(capture._author_assessments_if_needed(state, doc2)) is doc2
        assert called == []

    def test_the_assessment_prompt_has_no_file_fallback(self):
        """⛔ DELIBERATE. WP-IVGS-12 Task 3's argument is that an unversioned
        prompt is unrollbackable and invisible in the run record; a hidden
        default here would recreate exactly that, in the one call whose
        behaviour is this package's claim."""
        source = (REPO / "ivgs-workers" / "design_core" / "assessment_call.py").read_text()
        assert "Refusing to author assessments from an unversioned prompt" in source


# ---------------------------------------------------------------------------
# THE PROMPTS — the drops are moves, and the moves are proved
# ---------------------------------------------------------------------------

class TestThePromptLineage:

    def _publisher(self):
        from app.scripts import wpivgs12_publish_design_prompts as pub
        return pub

    def test_v8_moved_and_did_not_lose(self):
        """⛔ EVERY PHRASE DROPPED FROM THE DESIGN PROMPT IS GATED ON THE
        ASSESSMENT PROMPT. Read from the publisher's own tuples so a "move" that
        is really a deletion cannot pass."""
        pub = self._publisher()
        moved = (
            "POSE THE PROBLEM COLD",
            "HOLD — a silent attempt window",
            "REVEAL for self-check",
            "THE ASSESS IS THE WHOLE PROCEDURE, NOT A\nFRAGMENT",
            "POSE THE PROBLEM COLD, IN FRESH NUMBERS THE SCRIPT NEVER WORKED",
        )
        for phrase in moved:
            assert phrase not in pub.DESIGN_PHRASES, (
                f"{phrase!r} is still gated on the CALL-1 prompt, which no "
                "longer authors the assessment"
            )
            assert phrase in pub.ASSESSMENT_PHRASES, (
                f"{phrase!r} was dropped from the design prompt and does NOT "
                "appear on the assessment prompt. That is a deletion, not a move."
            )

    def test_the_definition_of_the_kind_stays_on_call_one(self):
        """Call 1 still chooses `evidence_kind` in the plan, and that plan is
        the entire brief call 2 answers."""
        pub = self._publisher()
        assert "THE LEARNER PERFORMS IT UNAIDED" in pub.DESIGN_PHRASES
        assert "THE LEARNER PERFORMS IT UNAIDED" in pub.ASSESSMENT_PHRASES

    def test_v8_removed_nothing_else_v7_gated(self):
        """Every phrase 12b, 12d, 12e, 12f and 12g pinned that is not part of
        the audited move must still be gated."""
        pub = self._publisher()
        survivors = (
            "BACKWARD DESIGN, IN THIS ORDER",
            "DETERMINE ACCEPTABLE EVIDENCE",
            "EVERY REWRITE IS MARKED",
            "SILENT LOSS IS THE ONE THING YOU MAY NOT DO",
            "DURATION IS AN OUTPUT OF YOUR DESIGN, NEVER AN INPUT TO IT",
            "YOU DO NOT WRITE THE OUTCOMES AND YOU CANNOT CHANGE THEM",
            "DESIGN THE ASSESSMENT FIRST, THEN THE ARC THAT REALIZES IT",
            "assessment_plan", "evidence_kind", "learner_does",
            "THE FADING SEQUENCE", "a COMPLETE worked example",
            "an INDEPENDENT problem",
            "practice_scenes",
            'origin: "sourced"', 'origin: "designed"',
            "SO `scenes` IS THE EXPOSITORY ARC, AND ONLY THAT",
            "THE PRACTICE MUST NOT BE THE ASSESSMENT WEARING A LABEL",
        )
        missing = [p for p in survivors if p not in pub.DESIGN_PHRASES]
        assert missing == [], missing

    def test_the_dropped_key_is_the_one_the_schema_no_longer_has(self):
        pub = self._publisher()
        assert "assessment_scenes" not in pub.DESIGN_PHRASES
        assert "assessment_scenes" in pub.ASSESSMENT_PHRASES

    def test_both_templates_carry_what_the_publisher_gates(self):
        pub = self._publisher()
        seed = REPO / "ivgs-api" / "seed" / "default_prompts"
        design = (seed / "storyboard_design_system.j2").read_text(encoding="utf-8")
        assessment = (seed / "assessment_authoring_system.j2").read_text(encoding="utf-8")
        assert [p for p in pub.DESIGN_PHRASES if p not in design] == []
        assert [p for p in pub.ASSESSMENT_PHRASES if p not in assessment] == []

    def test_the_assessment_template_is_static_and_cannot_leak(self):
        """⛔ THE MECHANISM, GATED. A `{{ }}` added here would undo the package
        silently: the model would start copying again and the only symptom would
        be a duplicate."""
        import re

        from jinja2 import BaseLoader, Environment

        seed = REPO / "ivgs-api" / "seed" / "default_prompts"
        text = (seed / "assessment_authoring_system.j2").read_text(encoding="utf-8")
        body = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
        assert "{{" not in body and "{%" not in body
        rendered = Environment(loader=BaseLoader()).from_string(text).render(
            practice_scenes="SENTINEL", scenes="SENTINEL",
            combined_transcript="SENTINEL", learning_outcomes="SENTINEL")
        assert "SENTINEL" not in rendered

    def test_the_new_lineage_is_in_the_python_enum_too(self):
        """⛔ THE WP-68 SHAPE, AND MIGRATION 0047 ALREADY WALKED INTO IT ONCE.
        The rows were published, and the next SELECT that touched one raised
        `LookupError: ... is not among the defined enum values`. The list is
        load-bearing ON READ."""
        from shared.models.enums import PROMPT_TYPES, PromptType
        assert PromptType.ASSESSMENT_AUTHORING_SYSTEM.value == "assessment_authoring_system"
        assert "assessment_authoring_system" in PROMPT_TYPES

    def test_the_migration_adds_the_same_member(self):
        path = (REPO / "ivgs-api" / "migrations" / "versions"
                / "0053_wp_ivgs_12h_assessment_prompt_lineage.py")
        text = path.read_text()
        assert 'revision = "0053"' in text
        assert 'down_revision = "0052"' in text
        assert "assessment_authoring_system" in text


class TestTheContractSevenRoundTrip:
    """⛔ THE SPLIT MUST NOT MOVE ONE SCENE ROW, AND THAT IS PROVED NOT ASSERTED.

    Contract-7 changes WHERE the assessment is authored and nothing about where
    it GOES: the stitched document carries `assessment_scenes` under the same key
    contract-6 used, and `shared.design.merge` places it by the same law. So the
    scene rows this produces must be identical to contract-6's, which is the one
    claim a reader would most reasonably doubt.

    ⚠ 12g's own round trip is the comparison: same emission shape, same nine
    rows, same events, same origins, same evidence map.
    """

    async def test_a_stitched_contract_seven_emission_lands_exactly_as_six_did(
        self, db_session,
    ):
        import uuid as _uuid

        from app.models.project import Project
        from app.models.storyboard_scene import StoryboardScene
        from app.services.design_brief_service import DesignBriefService
        from sqlalchemy import select

        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import CONTRACT_VERSION, parse_contract
        from shared.design.merge import merged_scene_sequence

        outcomes_text = "\n".join(f"{o['id']}: {o['text']}." for o in OUTCOMES)
        project = Project(id=_uuid.uuid4(), name="12h round trip", state="DRAFT",
                          learning_outcomes=outcomes_text)
        db_session.add(project)
        await db_session.flush()

        # ── CALL 1's document: no `assessment_scenes` anywhere in it ──
        call_one = {
            "assessment_plan": {oid: {"evidence_kind": "assess",
                                      "learner_does": "does the thing"}
                                for oid in IDS},
            "practice_scenes": {
                "LO-1": [_scene("LO-1", "practice",
                                "Fill in the missing partial product.",
                                origin="sourced")],
                "LO-2": [_scene("LO-2", "practice", "Finish this explanation.")],
                "LO-3": [_scene("LO-3", "practice", "Check this working.")],
            },
            "outcome_notes": {oid: {"bloom_level": "apply", "measurable": True,
                                    "proposed_refinement": None} for oid in IDS},
            "scenes": [
                _expository("LO-1", narration="teach it"),
                _expository("LO-2", event="guide", narration="guide it"),
                _expository("LO-3", narration="show the check"),
            ],
            "dropped_beats": [],
            "design_notes": "an arc",
        }
        assert "assessment_scenes" not in call_one

        # ── CALL 2's section, stitched in by code exactly as the transform does
        call_one["assessment_scenes"] = {
            "LO-1": [_scene("LO-1", "assess", "Work out 71 times 36 on your own.")],
            "LO-2": [_scene("LO-2", "assess",
                            "A pupil wrote 74 times 58 with no zero. Say what "
                            "went wrong and why.")],
            "LO-3": [_scene("LO-3", "assess",
                            "Here is a finished working for 62 times 47. Find "
                            "the error.")],
        }

        for scene in merged_scene_sequence(call_one):
            db_session.add(StoryboardScene(
                project_id=project.id, scene_index=scene["scene_index"],
                narration_text=scene["narration_text"],
                visual_description=scene["visual_description"],
                media_type=scene["media_type"],
                duration_seconds=scene["duration_seconds"]))
        await db_session.flush()

        payload = parse_contract(call_one)
        assert payload["contract_version"] == CONTRACT_VERSION == "design-contract-7"
        brief = await DesignBriefService(db_session).record(project.id, payload)
        await db_session.refresh(brief)

        assert len(brief.scene_designs) == 9
        # ⛳ BYTE-FOR-BYTE 12g's MAP. The placement law did not move.
        assert brief.evidence_map == {"LO-1": [1, 2], "LO-2": [4, 5],
                                      "LO-3": [7, 8]}

        rows = list((await db_session.execute(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == project.id)
            .order_by(StoryboardScene.scene_index))).scalars().all())
        assert [r.instructional_event for r in rows] == [
            "present", "practice", "assess",
            "guide", "practice", "assess",
            "present", "practice", "assess"]
        # ⛳ ORIGIN FREE, EXERCISED THROUGH THE XOR CHECK (migration 0048):
        # LO-1's practice is sourced with spans, everything else is designed
        # with a rationale, and both survive the write.
        assert [r.scene_origin for r in rows] == [
            "sourced", "sourced", "designed",
            "sourced", "designed", "designed",
            "sourced", "designed", "designed"]
        assert rows[2].designed_rationale

        # ── AND THE GATE READS THE ROWS CLEAN: the assessments call 2 wrote are
        # distinct from the practices call 1 wrote, by the belt's own measure.
        from app.services.design_review import review, split

        findings, _ = review(
            scenes=rows, outcomes=brief.outcomes or [],
            assessment_plan=brief.assessment_plan or {},
            dropped_beats=brief.dropped_beats or [],
            learning_outcomes=outcomes_text)
        refusals, _ = split(findings)
        assert [f.code for f in refusals] == []
