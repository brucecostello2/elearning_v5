"""WP-IVGS-12 — the Design Core, worker side.

⛔ THE MOST IMPORTANT TEST IN THIS FILE IS `test_guided_json_is_refused_by_name`.
The recovery plan prescribes `guided_json`; the pinned engine accepts it with
HTTP 200 and discards it. That text will outlive this session, so the refusal
has to live where its reader reaches — and a test has to keep it there.
"""
from __future__ import annotations

import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# The mechanism of record
# ---------------------------------------------------------------------------

class TestTheConstrainedDecodingMechanism:
    def test_guided_json_is_refused_by_name(self):
        from design_core.contract import (
            UnsupportedMechanism, design_contract_schema, response_format_for,
        )
        schema = design_contract_schema()
        for dead in ("guided_json", "guided_choice", "guided_decoding_backend"):
            with pytest.raises(UnsupportedMechanism) as exc:
                response_format_for(schema, mechanism=dead)
            # The MEASUREMENT must be in the message. A refusal that does not
            # say why gets worked around by the next reader of the plan.
            assert "SILENTLY IGNORED" in str(exc.value)
            assert "3dbe092e" in str(exc.value)

    def test_the_mechanism_of_record_is_json_schema_strict(self):
        from design_core.contract import design_contract_schema, response_format_for
        rf = response_format_for(design_contract_schema())
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is True
        assert rf["json_schema"]["schema"]["type"] == "object"

    def test_guided_json_is_never_USED_in_the_worker_tree(self):
        """A field this engine drops without comment reports success forever.

        ⚠ MENTIONS ARE ALLOWED AND WARNINGS ARE WANTED — `vllm_client` carries
        a "DO NOT PUT `guided_json` HERE" note beside the override it would be
        tempting to put it in, and that note is the point. What is forbidden is
        USE: the name appearing in code rather than in a comment or a string.
        """
        offenders = []
        for path in (REPO / "ivgs-workers").rglob("*.py"):
            if "test" in path.name or "design_core" in str(path):
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                code = line.split("#", 1)[0]
                if "guided_json" in code or "guided_choice" in code:
                    offenders.append(f"{path.relative_to(REPO)}:{lineno}")
        assert offenders == [], offenders


# ---------------------------------------------------------------------------
# The schema closes its enums from the CODE, not from the Foundation's prose
# ---------------------------------------------------------------------------

class TestTheSchema:
    def test_media_enum_comes_from_media_types_and_excludes_talking_head(self):
        """RC-Q4. Foundation §4 gives `talking_head` a modality row; the
        storyboard stage RAISES on a fifth media type and one such scene fails
        the entire storyboard (RC-P4)."""
        from design_core.contract import design_contract_schema
        from shared.models.enums import MEDIA_TYPES
        schema = design_contract_schema()
        media = schema["properties"]["scenes"]["items"]["properties"]["media_type"]["enum"]
        assert media == list(MEDIA_TYPES)
        assert "talking_head" not in media

    def test_serves_outcomes_is_required_with_at_least_one(self):
        from design_core.contract import design_contract_schema
        scene = design_contract_schema()["properties"]["scenes"]["items"]
        assert "serves_outcomes" in scene["required"]
        assert scene["properties"]["serves_outcomes"]["minItems"] == 1
        assert scene["additionalProperties"] is False

    def test_provenance_is_a_two_branch_oneof(self):
        from design_core.contract import design_contract_schema
        scene = design_contract_schema()["properties"]["scenes"]["items"]
        branches = scene["properties"]["provenance"]["oneOf"]
        assert len(branches) == 2
        origins = sorted(b["properties"]["origin"]["enum"][0] for b in branches)
        assert origins == ["designed", "sourced"]
        sourced = next(b for b in branches
                       if b["properties"]["origin"]["enum"] == ["sourced"])
        assert sourced["properties"]["source_refs"]["minItems"] == 1
        assert "rewrite_of" in sourced["required"]

    def test_measurable_and_a_refinement_cannot_both_be_asserted(self):
        """MEASURED: with these as independent members the model returned
        `measurable: true` AND a non-null refinement for both outcomes. The
        `oneOf` makes the contradiction ungrammatical."""
        from design_core.contract import design_contract_schema
        branches = design_contract_schema()["properties"]["outcomes"]["items"]["oneOf"]
        assert len(branches) == 2
        true_branch = next(b for b in branches
                           if b["properties"]["measurable"]["enum"] == [True])
        false_branch = next(b for b in branches
                            if b["properties"]["measurable"]["enum"] == [False])
        assert true_branch["properties"]["proposed_refinement"]["type"] == "null"
        assert false_branch["properties"]["proposed_refinement"]["type"] == "string"


# ---------------------------------------------------------------------------
# The parse, and the capture seam
# ---------------------------------------------------------------------------

class TestTheParse:
    def test_a_v7_storyboard_is_not_a_design_contract(self):
        """Must return None, not a partial dict: "no contract here" and "a
        contract with problems" are different answers."""
        from design_core.contract import parse_contract
        assert parse_contract({"scenes": [{"narration_text": "x"}]}) is None
        assert parse_contract("not json") is None
        assert parse_contract(["a", "list"]) is None

    def test_sourced_with_no_refs_is_downgraded_rather_than_lost(self):
        """Migration 0048's CHECK would refuse it. Downgrading the ONE scene to
        undeclared keeps the other eleven and lets the validator name it."""
        from design_core.contract import parse_contract
        parsed = parse_contract({
            "outcomes": [{"id": "LO-1"}],
            "scenes": [{"scene_index": 0, "serves_outcomes": ["LO-1"],
                        "provenance": {"origin": "sourced", "source_refs": []}}],
        })
        assert parsed["scenes"][0]["scene_origin"] is None


class TestTheCaptureSeam:
    def test_it_is_silent_when_not_armed(self):
        from design_core import capture
        capture._armed.set(None)
        capture.observe('{"outcomes":[{"id":"x"}],"scenes":[]}')   # must not raise

    def test_a_plain_text_refinement_costs_no_exception(self):
        from design_core import capture
        capture.arm(task_name=capture.TRANSCRIPT_TASK,
                    task_input={"job_context": {"job_id": "j", "project_id": "p"}})
        posted = []
        original, capture._post = capture._post, lambda pid, pl: posted.append(pl)
        try:
            capture.observe("Let's learn how to multiply two-digit numbers.")
            assert posted == []
        finally:
            capture._post = original

    def test_stage1_intent_rides_out_while_the_script_stays_verbatim(self):
        """The frozen body takes `refined_text` and discards every sibling key
        (`stage1_transcript.py:359-364`), so the script is what it stores."""
        from design_core import capture
        capture.arm(task_name=capture.TRANSCRIPT_TASK,
                    task_input={"job_context": {"job_id": "j", "project_id": "p"}})
        posted = []
        original, capture._post = capture._post, lambda pid, pl: posted.append(pl)
        try:
            capture.observe(json.dumps({
                "refined_text": "THE SCRIPT VERBATIM",
                "intent": {"beats": [{"start": 0, "end": 9}]},
            }))
        finally:
            capture._post = original
        assert posted and posted[0]["intent"]["beats"] == [{"start": 0, "end": 9}]

    def test_an_unarmable_payload_does_not_arm(self):
        from design_core import capture
        capture.arm(task_name=capture.STORYBOARD_TASK, task_input={"job_context": {}})
        assert capture._armed.get() is None


# ---------------------------------------------------------------------------
# The client seams default to the previous behaviour, exactly
# ---------------------------------------------------------------------------

class TestTheClientSeams:
    def test_an_observer_that_raises_never_reaches_the_stage(self):
        import clients.vllm_client as v
        def boom(content, model=""):
            raise RuntimeError("observer exploded")
        v.RESPONSE_OBSERVERS.append(boom)
        try:
            v._notify_observers("x", "m")      # must not raise
        finally:
            v.RESPONSE_OBSERVERS.remove(boom)

    def test_the_response_format_defaults_to_json_object(self):
        """Unarmed, `chat_json` must send exactly what it always sent."""
        import inspect
        import clients.vllm_client as v
        v.set_response_format_override(None)
        assert v._RESPONSE_FORMAT_OVERRIDE == {}
        source = inspect.getsource(v.VLLMClient.chat_json)
        assert 'or {"type": "json_object"}' in source


# ---------------------------------------------------------------------------
# Task 6 — and the degradation that must be byte-identical
# ---------------------------------------------------------------------------

class TestTheInstructionalHeader:
    def test_no_brief_leaves_the_prompt_byte_identical(self):
        from jinja2 import BaseLoader, Environment
        from design_core import headers
        env = Environment(loader=BaseLoader())
        headers.install(env, preprocess=True)
        headers.arm("p"); headers._cache.set(None)
        original, headers._fetch = headers._fetch, lambda pid: {"has_brief": False}
        try:
            out = env.from_string("You are a cinematographer.").render()
        finally:
            headers._fetch = original
        assert out == "You are a cinematographer."

    def test_the_block_carries_every_foundation_field(self):
        from design_core import headers
        rendered = headers._render({
            "has_brief": True,
            "event_arc": [
                {"scene_index": 0, "instructional_event": "present",
                 "bloom_level": "apply", "media_type": "motion_graphics",
                 "serves_outcomes": ["LO-1"], "media_rationale": "symbolic"},
                {"scene_index": 1, "instructional_event": "assess",
                 "bloom_level": "apply", "media_type": "motion_graphics",
                 "serves_outcomes": ["LO-1"], "media_rationale": "attempt",
                 "text_carried_by": "narration"},
            ],
            "coverage": [{"outcome_id": "LO-1", "assessed_by": [1]}],
        })
        for field in ("serves_outcomes", "bloom", "event", "arc position",
                      "learner_state", "evidence_link", "modality_rationale"):
            assert field in rendered, field
        assert "proven later in scene 1" in rendered
        assert "has seen scene 0 (present)" in rendered

    def test_the_two_file_templates_call_the_global_UNDER_A_GUARD(self):
        """⛔ THE `is defined` GUARD IS PART OF THE CONTRACT, NOT NOISE.

        The global is installed on each stage's Jinja environment at worker
        init. In any process where that has not run — the test suite, a one-off
        script, a worker whose registration failed and logged it — `{{ x() }}`
        on an undefined name RAISES UndefinedError, and these templates are
        rendered INSIDE FROZEN STAGE BODIES that turn it into a stage failure.
        Without the guard a Task 6 wiring problem takes stage 3 down for every
        project instead of degrading to the prompt that shipped before.
        """
        from jinja2 import BaseLoader, Environment

        for name in ("stage3_system.j2", "stage4_system.j2"):
            text = (REPO / "ivgs-workers" / "prompts" / name).read_text()
            assert "instructional_blocks" in text, name
            assert "is defined" in text, (
                f"{name} calls instructional_blocks() unguarded; with no global "
                "installed this raises inside a frozen stage body"
            )
            # And prove it, rather than trusting the substring.
            env = Environment(loader=BaseLoader())
            rendered = env.from_string(text).render(
                project_title="p", project_description="d",
                target_audience="a", visual_style="s")
            assert "INSTRUCTIONAL CONTEXT" not in rendered
            assert len(rendered) > 500


# ---------------------------------------------------------------------------
# THE FREEZE. This package took the wrapper; prove it took nothing else.
# ---------------------------------------------------------------------------

class TestTheFrozenBodiesAreUntouched:
    def test_freeze_exception_2_still_appears_exactly_twice(self):
        """WP-IVGS-10's own guard, re-asserted here: a third edit under that
        banner fails. This package requested no exception #3."""
        body = (REPO / "ivgs-workers" / "tasks" / "stage2_storyboard.py").read_text()
        assert body.count("FREEZE EXCEPTION #2") == 2

    def test_the_frozen_render_call_still_takes_nine_names(self):
        """If a tenth appears, someone edited a frozen body and the whole
        system-prompt route was unnecessary — which is a thing to notice."""
        body = (REPO / "ivgs-workers" / "tasks" / "stage2_storyboard.py").read_text()
        start = body.index("        return template.render(")
        call = body[start:body.index("        )", start)]
        assert call.count("=") == 9
        assert "learning_outcomes" not in call

    def test_no_wp_ivgs_12_marker_is_inside_a_frozen_stage_body(self):
        frozen = (
            "stage1_transcript.py", "stage2_storyboard.py", "stage3_images.py",
            "stage4_manifest.py", "stage5_voiceover.py", "stage7_prototype_draft.py",
            "stage8_final_render.py", "talking_head_task.py",
            "video_generation_task.py",
        )
        offenders = [
            name for name in frozen
            if "WP-IVGS-12" in (REPO / "ivgs-workers" / "tasks" / name).read_text()
        ]
        assert offenders == [], (
            f"{offenders} carry a WP-IVGS-12 marker — this package is supposed "
            "to have touched no frozen stage body at all"
        )
