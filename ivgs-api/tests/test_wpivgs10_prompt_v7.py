"""WP-IVGS-10 Task 2 — the v7 storyboard contract, and what the publisher gates.

⛔ THE RULING THESE TESTS SERVE, 2026-08-28: *"the storyboard's visual layer is
authored as aesthetic staging, not content."*

The publisher (`app/scripts/wp63_publish_storyboard_prompt.py`) is the only
thing standing between a template that has quietly lost a rule and a database
row that publishes cleanly, runs cleanly, and reproduces the defect. Every phrase
group it checks is a rule this pipeline has MEASURED breaking, so these tests
assert two things: that v7's phrases are present, and — the more important half —
that every earlier package's phrases are still there. RULE 1 has been tightened
five times and traded away zero times, and that record is the asset.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import app.scripts.wp63_publish_storyboard_prompt as publisher

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "seed" / "default_prompts" / "storyboard_generation.j2"
)
TEXT = TEMPLATE.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# nothing earlier was traded away
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "group",
    ["BINDING_PHRASES", "MEDIUM_PHRASES", "OUTCOMES_PHRASES", "NO_TEXT_PHRASES",
     "V5_PHRASES", "V6_PHRASES"],
)
def test_every_earlier_gate_phrase_survives_v7(group):
    """⛔ THE ONE THAT MATTERS MOST IN THIS FILE.

    v7 adds a rule ABOVE RULE 1 and it would be easy to write it in a way that
    softens the rule below. Each of these groups is a defect somebody measured
    on real output: v3's "2? x 23.14", v4's six repeated pictures, v5's five
    descriptions naming the operands, v6's absent motion pathway.
    """
    missing = [p for p in getattr(publisher, group) if p not in TEXT]
    assert missing == [], f"{group} lost: {missing}"


def test_rule_1_still_wins_on_the_digits():
    """RULE 1-EXTENDED is upstream of RULE 1, not instead of it."""
    assert "RULE 1 — NO TEXT IN THE VISUAL. Absolute." in TEXT
    assert "NAMING A NUMBER IN PROSE IS STILL ASKING FOR IT TO BE DRAWN" in TEXT
    # and v7 says in as many words that declaring does not buy a digit
    assert "AND (ii) IS A DECLARATION, NOT A LOOPHOLE." in TEXT


# ---------------------------------------------------------------------------
# v7's own three amendments
# ---------------------------------------------------------------------------

def test_v7_states_rule_1_extended():
    missing = [p for p in publisher.V7_PHRASES if p not in TEXT]
    assert missing == []


def test_the_content_classification_has_exactly_two_answers():
    """The rule is only enforceable because silence is not one of the answers.

    A content-bearing scene is motion_graphics with a template, or diffusion
    with a declaration. "THERE IS NO THIRD ANSWER" is the sentence the gate's
    hard refusal implements, and a template that softens it into a preference
    makes the refusal look arbitrary to whoever meets it.
    """
    assert "THERE IS NO THIRD ANSWER" in TEXT
    # The phrase wraps in the template; assert the part that cannot wrap.
    assert "is REFUSED BY NAME at the" in TEXT
    assert "storyboard gate" in TEXT


def test_the_output_contract_offers_all_four_media_types():
    """⛔ THE v6 CONTRADICTION, PINNED.

    v6 introduced motion_graphics in RULE 2 and RULE 8 and left the field list
    three rules above them saying "One of image, video_clip, or animation". The
    model reads its own output contract first.
    """
    missing = [p for p in publisher.FIELD_LIST_PHRASES if p not in TEXT]
    assert missing == []
    header = TEXT.split("PROJECT BRIEF", 1)[0]
    assert "motion_graphics" in header, (
        "the fourth media type is offered by the rules and absent from the "
        "field list -- which is exactly what v6 shipped"
    )


def test_rule_5_makes_content_mandatory_and_staging_optional():
    assert "STAGING MAY REMAIN. CONTENT IS MANDATORY." in TEXT
    for question in ("WHAT IS SHOWN", "IN WHAT STATE", "CHANGING HOW"):
        assert question in TEXT
    assert "THE DELETION TEST, IN ITS SECOND FORM." in TEXT


def test_the_operators_measured_example_is_quoted_as_the_wrong_answer():
    """A rule stated abstractly gets read as advice.

    Every rule in this template that has actually held carries the output that
    broke it, verbatim. v7's is the operator's own: project 9c29b1d1 scene 1.
    """
    assert "a soft pink pencil case nearby, warm and gentle lighting" in TEXT
    assert "9c29b1d1" in TEXT


def test_rule_9_asks_for_the_classification_not_the_subject():
    assert "RULE 9 — RECORD WHY YOU CHOSE THAT MEDIUM, IN ONE LINE" in TEXT
    assert "MEDIA TYPE IS DERIVED, NOT PREFERRED" in TEXT
    # the WRONG examples are what stop it becoming a restatement of the scene
    assert "This scene shows the multiplication." in TEXT


# ---------------------------------------------------------------------------
# RULE 8 and the renderer cannot drift apart
# ---------------------------------------------------------------------------

def test_rule_8_offers_only_templates_the_renderer_serves():
    import re

    from shared.motion.templates import template_names

    offered = set(re.findall(r'"template": "([a-z_]+)"', TEXT))
    assert offered, "RULE 8 names no templates at all"
    assert offered <= set(template_names())


def test_rule_8_names_every_parameter_the_templates_declare():
    """⛔ THE GATE TASK 4 NEEDED.

    `phase` was added to two templates, and `parse_and_validate` refuses a spec
    that omits any declared parameter. A prompt that never mentions `phase`
    therefore produces a spec that is refused at authoring time, one stage late,
    with a message about a missing parameter rather than about a prompt that
    never asked for one.
    """
    from shared.motion.templates import template_names, template_spec

    unnamed = sorted(
        {
            param
            for name in template_names()
            for param in template_spec(name)["params"]
            if f'"{param}"' not in TEXT
        }
    )
    assert unnamed == []


def test_rule_8_teaches_the_phase_from_the_narration():
    assert '"phase" — WHICH PART OF THE ROW THIS SCENE WRITES' in TEXT
    assert "READ THE NARRATION, NOT THE ARITHMETIC." in TEXT
    for phase in ("start", "complete", "full"):
        assert f'"{phase}"' in TEXT


# ---------------------------------------------------------------------------
# the publisher REFUSES a template that has lost a rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase",
    [
        "RULE 1-EXTENDED — WRITTEN OR NUMERIC CONTENT IS NEVER DELEGATED TO DIFFUSION",
        "STAGING MAY REMAIN. CONTENT IS MANDATORY.",
        "RULE 9 — RECORD WHY YOU CHOOSE",   # deliberately not a real phrase
    ],
)
def test_a_template_missing_a_v7_phrase_would_be_refused(phrase):
    """The gate is a check on THIS text, so removing a phrase must be detectable.

    The third parameter is a phrase that is NOT in V7_PHRASES, and it asserts
    the converse: the check is specific, not a substring match that any similar
    sentence would satisfy.
    """
    mutilated = TEXT.replace(phrase, "")
    missing = [p for p in publisher.V7_PHRASES if p not in mutilated]
    if phrase in publisher.V7_PHRASES:
        assert phrase in missing
    else:
        assert missing == [], "a phrase the gate does not check must not affect it"
