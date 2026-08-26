"""WP-65 Task 6 -- storyboard prompt v5, and a checker that catches near-repeats.

WHAT THE BRIEF ASKED FOR, AND WHAT WAS ALREADY THERE
-----------------------------------------------------
WP-65 Task 6 asked for two checker extensions. BOTH ALREADY EXISTED, and one of
them was stronger than the requested version:

  * "the deterministic checker gains an assertion that no two scenes share a
    description" -- ``check_visuals`` has had exactly that since WP-63
    (RULE 6, first half), and ``test_no_two_are_alike`` asserts it.
  * "extend the checker to fail a description containing multi-digit numerals"
    -- ``DIGITS`` is ``re.compile(r"\\d")``, which fails on a SINGLE digit.
    Implementing the request literally would have been a RELAXATION, and the
    package rules forbid one ("better discrimination, never looser gates"). It
    is left alone.

MEASURED, to be sure rather than to assume: the existing checker was run
against the operator's real v4 storyboard (project 92e30c7e, 13 scenes,
2026-08-26, read-only) and returned 22 findings, including precisely the three
duplicate pairs and the five digit-naming scenes the brief names.

SO THE GAP WAS NOT DETECTION, IT WAS TWO OTHER THINGS
------------------------------------------------------
1. The identity check only catches BYTE-identical repeats. Run with content-word
   similarity, the same storyboard has SIX repeated pictures, not three: scene 8
   is 100% content-identical to scene 2, scene 7 is 94% of scene 1, scene 5 is
   90% of scene 3. A viewer sees those as the same frame and content-hash dedup
   collapses them into shared bytes, so they never show in the asset count.
2. Nothing runs the checker against a real storyboard. Its own docstring says
   why: the only place it could run is Stage 2's task body, which AD-05 §8
   freezes. That is ledgered, not worked around.

v5 therefore PREVENTS rather than detects, and this file pins what it says.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_wp63_storyboard_prompt import (
    NEAR_DUPLICATE_THRESHOLD,
    check_visuals,
    similarity,
)

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "seed"
    / "default_prompts"
    / "storyboard_generation.j2"
)


def _scene(index: int, visual: str, media_type: str = "image") -> dict:
    return {
        "scene_index": index,
        "media_type": media_type,
        "visual_description": visual,
    }


# ---------------------------------------------------------------------------
# the strengthened duplicate check
# ---------------------------------------------------------------------------

class TestNearDuplicatesAreCaught:
    _BASE = (
        "over-the-shoulder view of a hand resting a pencil tip at the foot of a "
        "two-row column addition on lined paper; both partial-product rows are "
        "already written above a ruled horizontal line and the answer row "
        "beneath it is still empty"
    )

    def test_a_byte_identical_repeat_is_still_caught(self):
        """Everything the old check rejected, this one still rejects."""
        findings = check_visuals([_scene(0, self._BASE), _scene(1, self._BASE)])
        assert any("identical to scene 0" in f for f in findings)

    def test_a_repeat_with_one_word_changed_is_caught_too(self):
        """The case the old check missed, and the reason this is a change and
        not a re-assertion."""
        tweaked = self._BASE.replace("resting", "placing")
        findings = check_visuals([_scene(0, self._BASE), _scene(1, tweaked)])
        assert any("the same as scene 0" in f for f in findings), findings

    def test_two_scenes_sharing_only_style_are_not_flagged(self):
        """RULE 6 explicitly WANTS a shared style: 'consistency belongs to the
        STYLE, not to the content'. A check that fired on that would push the
        model away from the thing the prompt asks for."""
        a = (
            "a hand marking a single carry mark above the second column from "
            "the right on lined paper, warm desk lamp from the left, "
            "illustration style"
        )
        b = (
            "a hand drawing a ruled horizontal line beneath two "
            "partial-product rows on lined paper, warm desk lamp from the "
            "left, illustration style"
        )
        assert similarity(a, b) < NEAR_DUPLICATE_THRESHOLD
        findings = check_visuals([_scene(0, a), _scene(1, b)])
        assert not any("same as" in f or "identical" in f for f in findings)

    def test_the_threshold_separates_the_measured_cases_cleanly(self):
        """On the real v4 storyboard the six repeats scored 90-100% and the
        highest non-repeat scored 60%. The threshold sits in that gap, so it is
        a measured value rather than a guessed one."""
        assert 0.60 < NEAR_DUPLICATE_THRESHOLD < 0.90

    def test_similarity_is_symmetric_and_bounded(self):
        a, b = self._BASE, self._BASE.replace("empty", "blank")
        assert similarity(a, b) == similarity(b, a)
        assert 0.0 <= similarity(a, b) <= 1.0
        assert similarity(a, a) == 1.0


# ---------------------------------------------------------------------------
# v5's two amendments, as contract phrases
# ---------------------------------------------------------------------------

class TestV5AmendsRule1ForProseDigits:
    """The measured defect: five of thirteen v4 descriptions named the
    operands ("23 on top and 14 underneath") while three correctly described
    structure only. v4's RULE 1 examples are all about text written ON a
    surface, so naming a number in prose read as permitted."""

    @pytest.fixture(scope="class")
    def text(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def test_the_prose_digit_failure_is_named(self, text):
        assert "NAMING A NUMBER IN PROSE IS STILL ASKING FOR IT TO BE DRAWN" in text

    def test_the_measured_wrong_example_is_quoted(self, text):
        assert '"23 on top and 14 underneath' in text

    def test_a_deletion_test_is_given_not_just_a_prohibition(self, text):
        """A rule the model can APPLY beats a rule it can only agree with."""
        assert "if you\ndelete every digit from your description" in text.replace(
            "\r\n", "\n"
        )

    def test_the_vocabulary_that_replaces_digits_is_supplied(self, text):
        assert "POSITION, COUNT, WIDTH, ORDER and EMPTINESS" in text

    def test_rule_1_is_not_weakened_anywhere(self, text):
        """v5 tightens RULE 1; it must not have traded any of it away."""
        assert "NO TEXT IN THE VISUAL" in text
        assert "must NEVER request on-screen text" in text
        assert "2? x 23.14" in text


class TestV5AmendsRule6ForRecaps:
    """The measured defect: scenes 9/5, 10/6 and 11/0 were byte-identical --
    the tail of a 13-scene storyboard repeating its head. v4 forbade repeats
    but gave no way to picture a recap, so the model copied."""

    @pytest.fixture(scope="class")
    def text(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def test_the_recap_case_is_addressed_rather_than_only_forbidden(self, text):
        assert "A SCENE THAT REVISITS AN EARLIER STEP IS STILL A DIFFERENT SCENE" in text

    def test_the_measured_repeat_pattern_is_quoted(self, text):
        assert "scene 11 carried scene 0's description byte for byte" in text.replace(
            "\n", " "
        ).replace("  ", " ") or "scene 11\ncarried scene 0's description byte for byte" in text

    def test_a_closing_self_check_is_required_before_output(self, text):
        assert "BEFORE YOU OUTPUT, RE-READ YOUR OWN DESCRIPTIONS AS A SET" in text

    def test_the_self_check_names_the_accumulation_invariant(self, text):
        """The one property that makes a repeat mechanically detectable by the
        model itself: the page only ever gains."""
        assert "THE WORKING SURFACE ONLY EVER GAINS" in text

    def test_near_identical_is_stated_to_be_identical(self, text):
        assert "Near-identical is identical" in text

    def test_rule_6_is_not_weakened(self, text):
        assert "NO TWO SCENES MAY SHARE A VISUAL" in text
        assert "stock-photo framing" in text


class TestV5PreservesEveryEarlierContract:
    """v5 is an EXTENSION of v4. Every phrase the publisher gates on, and every
    rule WP-63 and WP-64 paid for, must survive it."""

    @pytest.fixture(scope="class")
    def text(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    @pytest.mark.parametrize("phrase", [
        "EVERY VISUAL MUST DEPICT ITS OWN SCENE'S STEP",
        "NO TWO SCENES MAY SHARE A VISUAL",
        "stock-photo framing",
        "CHOOSE media_type DELIBERATELY, SCENE BY SCENE",
        "WRITE THE DESCRIPTION FOR THE MEDIUM YOU JUST CHOSE",
        "WHAT MOVES, as a verb",
        "WHAT HAPPENS IN WHAT ORDER",
        "RULE 0 —",
        "=== LEARNING OUTCOMES (authored by the course owner) ===",
        "=== END LEARNING OUTCOMES ===",
        "DO NOT invent outcomes",
        "NO TEXT IN THE VISUAL",
        "must NEVER request on-screen text",
    ])
    def test_the_publisher_gate_phrases_all_survive(self, text, phrase):
        assert phrase in text

    def test_v5_is_strictly_longer_than_v4(self, text):
        """v4 was 12915 stored characters (md5
        c2b514642ccc3c140d4236b662361fc5, the live active row on 2026-08-26).
        v5 adds; it does not trade."""
        assert len(text.strip()) > 12915
