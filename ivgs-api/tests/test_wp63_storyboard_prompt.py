"""
WP-63 Task 9 — visual descriptions that do not depict the lesson.

MEASURED, project 14f71729 ("second multiplication project", 9 scenes,
2026-08-26), read from `storyboard_scenes` verbatim:

  scene_index 2  "...multiply 4 times 3, which equals 12. Write down 2 and
                  carry the 1..."
                 visual: "A hand moving a pencil across a blank sheet of paper,
                 with a subtle background of a classroom, illustration style,
                 leaving space for the composition overlay"

  scene_index 3  "...put a zero in the ones place as a placeholder. Multiply 1
                  times 3... Our second answer is 230."
                 visual: THE IDENTICAL STRING, word for word.

  scene_index 4  "Now, let's add the two answers together. We have 92 and 230
                  ... Our final answer is 322."
                 visual: "A hand holding a pencil, looking at a blank sheet of
                 paper on a wooden desk, with a subtle background of a
                 classroom, illustration style, leaving space for the
                 composition overlay"

Six of nine visuals would have fitted any lesson on any subject. The generated
images were correspondingly content-free.

THE RULE 1 / RULE 5 COLLISION, AND HOW IT IS RESOLVED HERE. The brief's example
is that scene 4's visual "should show 92 + 230 = 322 being worked". Taken
literally that asks an image model to draw digits, and RULE 1 of this very
prompt exists because that was measured twice on this pipeline: "a whiteboard
with 23 x 14 written on it" produced a board reading "2? x 23.14", and
calculations "appearing on screen" produced "12 + 44 = 67 + 5". So v4 binds the
visual to the scene's STEP and the STATE OF THE WORKING SURFACE — "two
partial-product rows already written above a ruled line, the answer row still
empty" — and leaves the digits to the composition overlay, which renders them
in a real font. That is specific, it is different for every scene, and there is
nothing in it for the model to misspell. It is recorded as a decision in the
WP-63 report rather than assumed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "seed"
    / "default_prompts"
    / "storyboard_generation.j2"
)


# ---------------------------------------------------------------------------
# The checker — a fixture narration in, a verdict out
# ---------------------------------------------------------------------------

#: Framing that would fit any lesson on any subject. Every one of these is
#: taken from a real storyboard this pipeline produced, not invented.
STOCK_FRAMING = (
    re.compile(r"\bblank sheet of paper\b", re.I),
    re.compile(r"\bclean,?\s+empty whiteboard\b", re.I),
    re.compile(r"\bpencil,?\s+poised over\b", re.I),
    re.compile(r"\bhand moving a pencil across\b", re.I),
    re.compile(r"\bsmiling\b.*\bthumbs up\b", re.I),
)

#: Words that name a STEP or a STATE of the working surface rather than a mood.
#: A description containing none of these is describing the room.
STEP_VOCABULARY = (
    re.compile(r"\b(row|rows)\b", re.I),
    re.compile(r"\bcolumn\b", re.I),
    re.compile(r"\bcarry\b", re.I),
    re.compile(r"\bplaceholder\b", re.I),
    re.compile(r"\bpartial[- ]product\b", re.I),
    re.compile(r"\bruled line\b", re.I),
    re.compile(r"\banswer row\b", re.I),
    re.compile(r"\balready written\b", re.I),
    re.compile(r"\bstill empty\b", re.I),
    re.compile(r"\bunderlin\w+\b", re.I),
    re.compile(r"\btens (place|column|digit)\b", re.I),
    re.compile(r"\bones (place|column|digit)\b", re.I),
)

#: RULE 1: the description must not ask for digits to be drawn.
DIGITS = re.compile(r"\d")


def check_visuals(scenes: list[dict]) -> list[str]:
    """Findings about a storyboard's visual descriptions. Empty means clean.

    Deterministic and model-free on purpose: it is a check on the SHAPE the
    prompt asks for, so it can gate a fixture in CI without an LLM in the loop
    and without a flaky assertion about what Llama happened to say today.

    NOT WIRED INTO THE PIPELINE. Stage 2's task body is frozen (AD-05 §8), so
    this cannot become a stage-side gate without the exception this package
    declined to take. The place it could go without touching a frozen body is
    the scene-create route, as a FLAG rather than a refusal; that is a
    behaviour change beyond this task and is ledgered in the report.
    """
    findings: list[str] = []
    seen: dict[str, int] = {}

    for scene in scenes:
        index = scene.get("scene_index")
        visual = (scene.get("visual_description") or "").strip()

        if not visual:
            findings.append(f"scene {index}: no visual_description at all")
            continue

        # RULE 6, first half: no two scenes may share a visual.
        key = re.sub(r"\s+", " ", visual.lower())
        if key in seen:
            findings.append(
                f"scene {index}: visual is identical to scene {seen[key]}'s. "
                "Two scenes teaching different steps cannot look the same."
            )
        else:
            seen[key] = index

        # RULE 6, second half: no stock-photo framing.
        for pattern in STOCK_FRAMING:
            if pattern.search(visual):
                findings.append(
                    f"scene {index}: stock framing {pattern.pattern!r}. It "
                    "would fit any lesson on any subject."
                )

        # RULE 5: the description must name the step or the state of the work.
        if not any(pattern.search(visual) for pattern in STEP_VOCABULARY):
            findings.append(
                f"scene {index}: names no step and no state of the working "
                "surface, so it does not depict what this scene teaches."
            )

        # RULE 1: and it must still not ask for digits to be drawn.
        if DIGITS.search(visual):
            findings.append(
                f"scene {index}: contains digits. The overlay renders the "
                "numbers; an image model asked for them produces "
                "text-shaped marks."
            )

    return findings


# ---------------------------------------------------------------------------
# The measured storyboard, and a compliant rewrite of the same four scenes
# ---------------------------------------------------------------------------

MEASURED = [
    {
        "scene_index": 1,
        "narration_text": (
            "First, let's set up the problem. We have 23 times 14. Write 23 on "
            "top and 14 underneath, making sure the numbers line up correctly."
        ),
        "visual_description": (
            "A close-up of a hand holding a pencil, poised over a blank sheet "
            "of paper on a wooden desk, with a subtle background of a "
            "classroom, illustration style"
        ),
    },
    {
        "scene_index": 2,
        "narration_text": (
            "Now, let's start multiplying. We'll begin with the ones digit, "
            "which is 4. Multiply 4 times 3, which equals 12. Write down 2 and "
            "carry the 1."
        ),
        "visual_description": (
            "A hand moving a pencil across a blank sheet of paper, with a "
            "subtle background of a classroom, illustration style, leaving "
            "space for the composition overlay"
        ),
    },
    {
        "scene_index": 3,
        "narration_text": (
            "Next, we'll multiply by the tens digit, which is 1. So, put a "
            "zero in the ones place as a placeholder. Our second answer is 230."
        ),
        "visual_description": (
            "A hand moving a pencil across a blank sheet of paper, with a "
            "subtle background of a classroom, illustration style, leaving "
            "space for the composition overlay"
        ),
    },
    {
        "scene_index": 4,
        "narration_text": (
            "Now, let's add the two answers together. We have 92 and 230. Add "
            "them up. Our final answer is 322. So, 23 times 14 equals 322."
        ),
        "visual_description": (
            "A hand holding a pencil, looking at a blank sheet of paper on a "
            "wooden desk, with a subtle background of a classroom, "
            "illustration style, leaving space for the composition overlay"
        ),
    },
]

COMPLIANT = [
    {
        "scene_index": 1,
        "narration_text": MEASURED[0]["narration_text"],
        "visual_description": (
            "Over-the-shoulder view of a hand ruling a short horizontal line "
            "beneath two freshly written stacked rows on lined paper, the "
            "ones column aligned under the ones column; warm desk lamp from "
            "the left, upper right third of the sheet kept clear for the "
            "overlay, muted blue-grey illustration style"
        ),
    },
    {
        "scene_index": 2,
        "narration_text": MEASURED[1]["narration_text"],
        "visual_description": (
            "The same desk and lamp; a pencil tip touching the ones column of "
            "the top row while a small carry mark sits above the tens column, "
            "the first partial-product row half written beneath the ruled "
            "line, muted blue-grey illustration style"
        ),
    },
    {
        "scene_index": 3,
        "narration_text": MEASURED[2]["narration_text"],
        "visual_description": (
            "The same desk and lamp; the first partial-product row complete, "
            "the pencil placing a placeholder in the ones place of a new "
            "second row, the tens column marked by a light guide stroke, "
            "muted blue-grey illustration style"
        ),
    },
    {
        "scene_index": 4,
        "narration_text": MEASURED[3]["narration_text"],
        "visual_description": (
            "The same desk and lamp; two partial-product rows already written "
            "above a second ruled line, the answer row beneath it still empty, "
            "the pencil resting at the foot of the ones column ready to "
            "descend, muted blue-grey illustration style"
        ),
    },
]


class TestTheMeasuredStoryboardFails:
    def test_the_measured_run_is_caught(self):
        findings = check_visuals(MEASURED)
        assert findings, "the checker must catch the storyboard that shipped"

    def test_the_two_identical_scenes_are_named(self):
        findings = check_visuals(MEASURED)
        assert any(
            "identical to scene 2" in f for f in findings
        ), findings

    def test_the_addition_scene_is_flagged_for_saying_nothing(self):
        """`scene_index` 4 — the one the brief quotes as "scene 5"."""
        findings = check_visuals([MEASURED[3]])
        assert any("names no step" in f for f in findings), findings
        assert any("stock framing" in f for f in findings), findings

    def test_every_one_of_the_four_is_flagged(self):
        for scene in MEASURED:
            assert check_visuals([scene]), scene["scene_index"]


class TestACompliantStoryboardPasses:
    def test_the_rewrite_is_clean(self):
        assert check_visuals(COMPLIANT) == []

    def test_each_scene_names_its_own_step(self):
        """Not just "different" — each one names ITS step.

        Scene 2 carries; scene 3 places the placeholder; scene 4 has both
        partial products written and an empty answer row. A reader who saw only
        the visuals could put them back in order.
        """
        for scene in COMPLIANT:
            assert any(
                p.search(scene["visual_description"]) for p in STEP_VOCABULARY
            ), scene["scene_index"]

    def test_no_two_are_alike(self):
        texts = {s["visual_description"] for s in COMPLIANT}
        assert len(texts) == len(COMPLIANT)

    def test_and_none_of_them_asks_for_a_digit(self):
        """RULE 1 still wins. This is the constraint the binding runs inside."""
        for scene in COMPLIANT:
            assert not DIGITS.search(scene["visual_description"]), (
                scene["scene_index"]
            )


class TestTheTemplateCarriesTheContract:
    """The tracked template and the publisher must not drift apart.

    `app/scripts/wp63_publish_storyboard_prompt.py` REFUSES to publish a
    template missing any of these. If the template were edited to drop one, the
    publisher would refuse at the operator's console and nothing would say why
    until then; this fails in CI instead.
    """

    @pytest.fixture(scope="class")
    def text(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def test_rule_5_binding_is_stated(self, text):
        assert "EVERY VISUAL MUST DEPICT ITS OWN SCENE'S STEP" in text

    def test_rule_6_forbids_repeats_and_stock_framing(self, text):
        assert "NO TWO SCENES MAY SHARE A VISUAL" in text
        assert "stock-photo framing" in text

    def test_rule_1_survives(self, text):
        """The older rule, and the one measured twice. It wins on the digits."""
        assert "NO TEXT IN THE VISUAL" in text
        assert "must NEVER request on-screen text" in text

    def test_the_publisher_gates_on_exactly_these_phrases(self, text):
        from app.scripts.wp63_publish_storyboard_prompt import (
            BINDING_PHRASES,
            NO_TEXT_PHRASES,
        )

        for phrase in BINDING_PHRASES + NO_TEXT_PHRASES:
            assert phrase in text, phrase

    def test_the_measured_defect_is_named_in_the_prompt(self, text):
        """A rule stated abstractly did not stop this one.

        WP-62 learned the same thing about the translation prompt: v3 names
        scene 9's exact shape because the abstract rule had not held. This
        names the identical-visual and blank-sheet failures that shipped.
        """
        assert "blank sheet" in text.lower()
        assert "14f71729" in text
