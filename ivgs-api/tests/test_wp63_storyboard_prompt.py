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

WP-64 EXTENDS THIS CHECKER TO THE MEDIUM (Task 2(c)). v4 gained RULE 2's
deliberate per-scene media_type choice and RULE 7's requirement that the
description be AUTHORED for the medium chosen. Both are checkable
deterministically and both are checked here, because the failure they close is
silent: a description authored for a still and then labelled "video_clip" is
accepted by every layer below it and reaches CogVideoX as the whole of its
motion instruction (`ivgs-workers/tasks/video_generation_task.py:245`). Nothing
downstream rewrites it, so if the motion is not in this string it does not
exist anywhere.

The medium vocabulary is deliberately about SHAPE, not about a particular
lesson: "what moves", "what the camera does", "in what order" for a clip; "what
builds" and "who is performing it" for an animation. The person requirement on
animation is not stylistic - `animation_generation_task.py:481` REFUSES a scene
whose reference image carries no person, by name.
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


# ---------------------------------------------------------------------------
# WP-64 Task 2(c) — the medium vocabularies
# ---------------------------------------------------------------------------

#: Something in the frame MOVES. A clip whose description names no movement is
#: a photograph caption with a duration attached.
MOTION_VOCABULARY = (
    re.compile(r"\b(moves?|moving)\b", re.I),
    re.compile(r"\b(sweeps?|sweeping)\b", re.I),
    re.compile(r"\b(slides?|sliding)\b", re.I),
    re.compile(r"\b(glides?|gliding)\b", re.I),
    re.compile(r"\b(traces?|tracing)\b", re.I),
    re.compile(r"\b(lifts?|lifting)\b", re.I),
    re.compile(r"\b(turns?|turning|rotat\w+)\b", re.I),
    re.compile(r"\b(pours?|pouring|flows?|flowing)\b", re.I),
    re.compile(r"\b(walks?|walking|steps? (?:in|back|forward))\b", re.I),
    re.compile(r"\b(descends?|descending|rises?|rising)\b", re.I),
    re.compile(r"\b(drags?|dragging|pushes|pulling|pulls)\b", re.I),
    re.compile(r"\b(gestur\w+|reach(?:es|ing))\b", re.I),
)

#: The camera is an instrument with behaviour, and "locked off" IS a behaviour.
#: What is forbidden is silence about it.
CAMERA_VOCABULARY = (
    re.compile(r"\b(pan|pans|panning)\b", re.I),
    re.compile(r"\b(tilt|tilts|tilting)\b", re.I),
    re.compile(r"\b(dolly|dollies|dollying)\b", re.I),
    re.compile(r"\btracking shot\b", re.I),
    re.compile(r"\b(zoom\w*)\b", re.I),
    re.compile(r"\bpush(?:es|ing)? in\b", re.I),
    re.compile(r"\bpull(?:s|ing)? back\b", re.I),
    re.compile(r"\b(handheld|crane|orbit\w*)\b", re.I),
    re.compile(r"\block\w*[- ]off\b", re.I),
    re.compile(r"\bstatic camera\b", re.I),
    re.compile(r"\bcamera (?:holds?|drifts?|follows?|stays?|remains?)\b", re.I),
)

#: A clip has a start and an end, and the description must say which is which.
TEMPORAL_VOCABULARY = (
    re.compile(r"\bbegins?\b", re.I),
    re.compile(r"\bstarts? (?:with|on)\b", re.I),
    re.compile(r"\bthen\b", re.I),
    re.compile(r"\bcontinu\w+\b", re.I),
    re.compile(r"\bthroughout\b", re.I),
    re.compile(r"\buntil\b", re.I),
    re.compile(r"\bfinally\b", re.I),
    re.compile(r"\bends? (?:with|on|holding)\b", re.I),
    re.compile(r"\bwhile\b", re.I),
    re.compile(r"\bas the\b", re.I),
)

#: An animation is a BUILD or a TRANSFORM, per RULE 2's second question.
BUILD_VOCABULARY = (
    re.compile(r"\b(builds?|building)\b", re.I),
    re.compile(r"\b(assembl\w+)\b", re.I),
    re.compile(r"\b(accumulat\w+)\b", re.I),
    re.compile(r"\b(grows?|growing)\b", re.I),
    re.compile(r"\b(forms?|forming)\b", re.I),
    re.compile(r"\b(emerg\w+)\b", re.I),
    re.compile(r"\b(transform\w+|morph\w+)\b", re.I),
    re.compile(r"\b(unfold\w+)\b", re.I),
    re.compile(r"\bone (?:\w+ )?at a time\b", re.I),
    re.compile(r"\bstep by step\b", re.I),
    re.compile(r"\bpiece by piece\b", re.I),
    re.compile(r"\b(fills?|filling) (?:in|from)\b", re.I),
)

#: Wan2.2-Animate is pose reenactment. No subject, no animation - and the
#: worker says so by name rather than inventing a body.
PERSON_VOCABULARY = (
    re.compile(
        r"\b(person|people|figure|presenter|teacher|instructor|tutor|"
        r"character|man|woman|student|speaker|host|narrator|subject|"
        r"demonstrator)\b",
        re.I,
    ),
)

#: What an "image" description must NOT contain: a still cannot pan, and it has
#: no elapsed time to spend. Words that only make sense over a duration are, in
#: an image scene, evidence that the medium and the description disagree.
#:
#: DELIBERATELY NARROW. A first draft of this tuple also matched ``seconds?``,
#: which flagged "a second ruled line" in four of the compliant fixtures - the
#: ORDINAL, not the unit. A checker that fires on the wrong word teaches
#: authors to write around it. Elapsed time in an image description is already
#: caught by RULE 1's digit rule ("over 3 seconds"), so nothing is lost.
STILL_INCOMPATIBLE = CAMERA_VOCABULARY + (
    re.compile(r"\bframe by frame\b", re.I),
    re.compile(r"\bover the course of\b", re.I),
    re.compile(r"\belapsed\b", re.I),
)

#: The three values `SceneUpdate.validate_media_type` accepts. A scene with no
#: media_type at all is an image, which is what the API's own default says.
MEDIA_TYPES = ("image", "video_clip", "animation")


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

    WP-64 Task 2(c): each finding is also checked AGAINST ITS OWN media_type.
    A scene with no ``media_type`` key is an image, which is what the API
    default says and what every scene of the measured run was.
    """
    findings: list[str] = []
    seen: dict[str, int] = {}

    for scene in scenes:
        index = scene.get("scene_index")
        visual = (scene.get("visual_description") or "").strip()
        media_type = (scene.get("media_type") or "image").strip() or "image"

        if not visual:
            findings.append(f"scene {index}: no visual_description at all")
            continue

        if media_type not in MEDIA_TYPES:
            findings.append(
                f"scene {index}: media_type {media_type!r} is not one of "
                f"{', '.join(MEDIA_TYPES)}. The API accepts nothing else and "
                "the orchestrator groups an unknown value into the image "
                "branch without saying so."
            )

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

        # RULE 7 (WP-64): the description must be written FOR its medium.
        findings.extend(_medium_findings(index, media_type, visual))

    return findings


def _matches(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _medium_findings(index, media_type: str, visual: str) -> list[str]:
    """RULE 7, per medium. Empty means the description matches its media_type.

    Why this is a check and not a preference: the description IS the motion
    instruction. `video_generation_task._generate_video_prompt` interpolates it
    into a cinematographer prompt (`video_generation_task.py:245`) and
    `_params_from_binding` hands it to Wan2.2-Animate as the render prompt
    (`animation_generation_task.py:389`). Neither invents motion that the
    description did not carry, so a still description under a moving media_type
    produces a moving render of a frozen idea - which is exactly what a scene
    switched from image to video in the editor used to get.
    """
    out: list[str] = []

    if media_type == "video_clip":
        if not _matches(MOTION_VOCABULARY, visual):
            out.append(
                f"scene {index}: media_type is video_clip but the description "
                "names nothing that moves. It would read equally well as a "
                "photograph caption, and the motion instruction reaching "
                "CogVideoX is this string and nothing else."
            )
        if not _matches(CAMERA_VOCABULARY, visual) and not _matches(
            TEMPORAL_VOCABULARY, visual
        ):
            out.append(
                f"scene {index}: media_type is video_clip but the description "
                "says neither what the camera does nor in what order things "
                "happen. A clip has a start and an end; RULE 7 requires the "
                "description to say which is which."
            )

    elif media_type == "animation":
        if not _matches(BUILD_VOCABULARY, visual):
            out.append(
                f"scene {index}: media_type is animation but the description "
                "names no build and no transformation. RULE 2 gives animation "
                "to a step that accumulates or changes state; a description "
                "without one has chosen the branch for no stated reason."
            )
        if not _matches(PERSON_VOCABULARY, visual):
            out.append(
                f"scene {index}: media_type is animation but the description "
                "names no person. Wan2.2-Animate is pose reenactment and the "
                "worker REFUSES this scene by name - 'reference image contains "
                "no person to animate' - rather than inventing a body."
            )

    else:  # image, and anything unknown, which is grouped as image downstream
        for pattern in STILL_INCOMPATIBLE:
            if pattern.search(visual):
                out.append(
                    f"scene {index}: media_type is image but the description "
                    f"asks for {pattern.pattern!r}, which only exists over a "
                    "duration. Either the medium is wrong or the description "
                    "is; RULE 7 makes them one decision."
                )

    return out


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


# ---------------------------------------------------------------------------
# WP-64 Task 6(e) — a stated outcome the scene plan has to answer
# ---------------------------------------------------------------------------

#: Verbs that describe an outcome the viewer performs or watches happen. A
#: still frame cannot serve one: "follow the carrying step AS IT HAPPENS" is a
#: claim about time. Bloom's lower band - recognise, name, recall, compare - is
#: deliberately absent, because those ARE served by a still and a checker that
#: demanded motion for them would push GPU time at nothing.
MOTION_IMPLYING_OUTCOME = (
    re.compile(r"\bfollow\b", re.I),
    re.compile(r"\bas it happens\b", re.I),
    re.compile(r"\bwatch\b", re.I),
    re.compile(r"\bperform\b", re.I),
    re.compile(r"\bcarry out\b", re.I),
    re.compile(r"\bdemonstrat\w+\b", re.I),
    re.compile(r"\bstep[- ]by[- ]step\b", re.I),
    re.compile(r"\bin real time\b", re.I),
    re.compile(r"\bunfold\w*\b", re.I),
)


def outcome_findings(learning_outcomes: str, scenes: list[dict]) -> list[str]:
    """RULE 0, as far as a model-free check honestly reaches.

    WP-64 Task 6(e). This does NOT try to judge whether the storyboard covers
    the outcomes - that needs a reader. It checks the one thing that is
    decidable from the text: an outcome that names an action the viewer must
    FOLLOW or PERFORM cannot be served by a storyboard in which every single
    scene is a still. That is the measured failure shape (project 14f71729:
    nine scenes, nine images), and it is the one RULE 0 exists to break.

    No outcomes, or no motion-implying outcome, means no finding. Silence is
    the correct answer for a course whose outcomes are all recognition.
    """
    outcomes = (learning_outcomes or "").strip()
    if not outcomes:
        return []
    if not any(p.search(outcomes) for p in MOTION_IMPLYING_OUTCOME):
        return []
    if not scenes:
        return ["the outcomes name an action to follow, and there are no scenes"]

    moving = [
        s for s in scenes
        if (s.get("media_type") or "image") in ("video_clip", "animation")
    ]
    if moving:
        return []
    return [
        "the stated learning outcomes name an action the viewer must follow "
        "or perform, and every scene in this plan is a still. RULE 0 makes "
        "the outcome the test of the media_type: a step that has to be "
        "watched happening is a video_clip (or an animation where RULE 2's "
        "person condition is met)."
    ]


# ---------------------------------------------------------------------------
# WP-64 Task 2(c) — the medium fixtures
# ---------------------------------------------------------------------------

#: THE DEFECT THIS PACKAGE CLOSES, as a fixture. Word for word the scene-2
#: description the measured run produced, with the media_type an operator would
#: set in the Edit Scene modal. Nothing else changes; the description is still
#: the one Stage 2 authored for a still. That is the whole finding: the medium
#: moved and the words did not.
STILL_WORDS_UNDER_A_MOVING_MEDIUM = [
    {
        "scene_index": 2,
        "media_type": "video_clip",
        "narration_text": MEASURED[1]["narration_text"],
        "visual_description": COMPLIANT[1]["visual_description"],
    },
    {
        "scene_index": 3,
        "media_type": "animation",
        "narration_text": MEASURED[2]["narration_text"],
        "visual_description": COMPLIANT[2]["visual_description"],
    },
]

#: The same two steps, authored for the media_type they carry. RULE 5's step
#: language survives, RULE 1 is untouched, and the medium is now in the words.
MEDIUM_APT = [
    {
        "scene_index": 1,
        "media_type": "image",
        "narration_text": MEASURED[0]["narration_text"],
        "visual_description": COMPLIANT[0]["visual_description"],
    },
    {
        "scene_index": 2,
        "media_type": "video_clip",
        "narration_text": MEASURED[1]["narration_text"],
        "visual_description": (
            "The same desk and lamp, camera holding steady over the sheet; the "
            "pencil begins at the ones column of the top row and traces "
            "downward, a small carry mark forming above the tens column, then "
            "the first partial-product row fills in beneath the ruled line, "
            "muted blue-grey illustration style"
        ),
    },
    {
        "scene_index": 3,
        "media_type": "animation",
        "narration_text": MEASURED[2]["narration_text"],
        "visual_description": (
            "The same desk and lamp; the presenter builds the second row one "
            "column at a time beneath the completed partial-product row, a "
            "placeholder taking shape in the ones place while their shoulders "
            "turn toward each new column, muted blue-grey illustration style"
        ),
    },
    {
        "scene_index": 4,
        "media_type": "image",
        "narration_text": MEASURED[3]["narration_text"],
        "visual_description": COMPLIANT[3]["visual_description"],
    },
]


class TestTheMediumMustBeInTheWords:
    """RULE 7. The description is the only motion instruction there is."""

    def test_a_still_description_under_video_clip_is_caught(self):
        findings = check_visuals([STILL_WORDS_UNDER_A_MOVING_MEDIUM[0]])
        assert any("names nothing that moves" in f for f in findings), findings

    def test_a_still_description_under_animation_is_caught(self):
        findings = check_visuals([STILL_WORDS_UNDER_A_MOVING_MEDIUM[1]])
        assert any("no build and no transformation" in f for f in findings), findings
        assert any("names no person" in f for f in findings), findings

    def test_the_same_text_passes_as_an_image(self):
        """The description is not bad. It is bad FOR THAT MEDIUM.

        Identical strings, media_type image: clean. This is what makes the
        finding a mismatch rather than a quality complaint.
        """
        as_images = [
            {**scene, "media_type": "image"}
            for scene in STILL_WORDS_UNDER_A_MOVING_MEDIUM
        ]
        assert check_visuals(as_images) == []

    def test_the_medium_apt_storyboard_is_clean(self):
        assert check_visuals(MEDIUM_APT) == []

    def test_the_mix_is_deliberate_not_uniform(self):
        """RULE 2. Every scene of the measured run was an image."""
        chosen = {s["media_type"] for s in MEDIUM_APT}
        assert len(chosen) > 1, chosen

    def test_a_clip_that_moves_but_never_says_when_is_caught(self):
        findings = check_visuals([{
            "scene_index": 9,
            "media_type": "video_clip",
            "visual_description": (
                "A hand sweeping across the ruled line of a column addition, "
                "muted blue-grey illustration style"
            ),
        }])
        assert any("in what order things happen" in f for f in findings), findings

    def test_an_image_asked_to_pan_is_caught(self):
        findings = check_visuals([{
            "scene_index": 9,
            "media_type": "image",
            "visual_description": (
                "The camera pans slowly across the ruled line of a column "
                "addition, the answer row still empty"
            ),
        }])
        assert any("only exists over a duration" in f for f in findings), findings

    def test_an_unknown_media_type_is_named_not_absorbed(self):
        findings = check_visuals([{
            "scene_index": 9,
            "media_type": "VIDEO",
            "visual_description": COMPLIANT[3]["visual_description"],
        }])
        assert any("is not one of" in f for f in findings), findings

    def test_rule_1_still_wins_over_every_medium(self):
        """Motion, camera and order, and not one digit among them."""
        for scene in MEDIUM_APT:
            assert not DIGITS.search(scene["visual_description"]), scene["scene_index"]


class TestAStatedOutcomeReachesTheSceneMix:
    """WP-64 Task 6(e). The outcome is the test of the mix, not a decoration."""

    OUTCOME = (
        "By the end, the viewer can follow the carrying step as it happens, "
        "and can name the place value of each column."
    )

    def test_all_stills_under_a_motion_outcome_is_caught(self):
        """The measured shape: nine scenes, nine images, one motion outcome."""
        plan = [{**s, "media_type": "image"} for s in MEDIUM_APT]
        findings = outcome_findings(self.OUTCOME, plan)
        assert findings, "an all-still plan cannot serve 'follow ... as it happens'"
        assert "every scene in this plan is a still" in findings[0]

    def test_the_deliberate_mix_answers_the_outcome(self):
        """MEDIUM_APT carries a video_clip and an animation. That is enough."""
        assert outcome_findings(self.OUTCOME, MEDIUM_APT) == []

    def test_one_non_image_scene_is_the_bar(self):
        plan = [{**s, "media_type": "image"} for s in MEDIUM_APT]
        plan[1]["media_type"] = "video_clip"
        assert outcome_findings(self.OUTCOME, plan) == []

    def test_a_recognition_only_outcome_demands_nothing(self):
        """"Name" and "recall" are served by a still. No finding, deliberately."""
        recognition = (
            "By the end, the viewer can name the place value of each column "
            "and recall the order of the steps."
        )
        plan = [{**s, "media_type": "image"} for s in MEDIUM_APT]
        assert outcome_findings(recognition, plan) == []

    def test_no_outcomes_means_no_finding(self):
        """Task 6(d): absence degrades silently. It is not a defect."""
        plan = [{**s, "media_type": "image"} for s in MEDIUM_APT]
        assert outcome_findings("", plan) == []
        assert outcome_findings("   ", plan) == []


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
            MEDIUM_PHRASES,
            NO_TEXT_PHRASES,
            OUTCOMES_PHRASES,
        )

        for phrase in (
            BINDING_PHRASES + MEDIUM_PHRASES + OUTCOMES_PHRASES + NO_TEXT_PHRASES
        ):
            assert phrase in text, phrase

    def test_the_measured_defect_is_named_in_the_prompt(self, text):
        """A rule stated abstractly did not stop this one.

        WP-62 learned the same thing about the translation prompt: v3 names
        scene 9's exact shape because the abstract rule had not held. This
        names the identical-visual and blank-sheet failures that shipped.
        """
        assert "blank sheet" in text.lower()
        assert "14f71729" in text

    def test_rule_2_asks_for_a_deliberate_choice(self, text):
        """WP-64 Task 2(a). The mix defaulted to image because nothing asked."""
        assert "CHOOSE media_type DELIBERATELY, SCENE BY SCENE" in text
        assert "IS THE MOTION INHERENT TO THE STEP?" in text

    def test_rule_2_keeps_the_person_constraint_on_animation(self, text):
        """It is not a style note. The worker refuses the scene by name."""
        assert "pose reenactment (Wan2.2-Animate)" in text
        assert "refuses the scene by name" in text
        assert "invents a human body" in text

    def test_rule_7_binds_the_description_to_the_medium(self, text):
        assert "WRITE THE DESCRIPTION FOR THE MEDIUM YOU JUST CHOSE" in text
        assert "WHAT MOVES, as a verb" in text
        assert "WHAT THE CAMERA DOES" in text
        assert "WHAT HAPPENS IN WHAT ORDER" in text

    def test_rule_7_does_not_trade_away_rule_1(self, text):
        """The two pull against each other and RULE 1 still wins."""
        assert "RULE 1 IS UNCHANGED BY THIS AND STILL WINS" in text

    def test_rule_0_conditions_the_mix_on_the_outcomes(self, text):
        """WP-64 Task 6(d)."""
        assert "RULE 0 —" in text
        assert "TO RULE 2, the media_type of each scene" in text
        assert "TO RULES 5, 6 AND 7, the content of each visual" in text

    def test_rule_0_degrades_silently_when_the_field_is_absent(self, text):
        """Task 6(d): no placeholder text for a missing field.

        Two halves. The Jinja guard means the whole block disappears when
        `project_description` is empty, and the prose forbids the model
        narrating the absence when the description exists without the delimited
        block.
        """
        assert "{% if project_description %}" in text
        assert "{% endif %}" in text
        assert "DO NOT invent outcomes" in text
        assert "mention their absence" in text

    def test_the_delimiter_matches_the_orchestrator_byte_for_byte(self, text):
        """The one way this feature fails silently.

        The orchestrator writes the outcomes between these two lines because
        the frozen stage body cannot be given a variable of its own (P2.66).
        If the writer and the reader drift, the model is handed a block it was
        never told to look for: no error, no log line, outcomes ignored.
        """
        open_line = "=== LEARNING OUTCOMES (authored by the course owner) ==="
        close_line = "=== END LEARNING OUTCOMES ==="
        assert open_line in text
        assert close_line in text

        source = (
            Path(__file__).resolve().parents[2]
            / "ivgs-workers"
            / "tasks"
            / "pipeline_orchestrator_v2.py"
        ).read_text(encoding="utf-8")
        assert f'OUTCOMES_OPEN = "{open_line}"' in source
        assert f'OUTCOMES_CLOSE = "{close_line}"' in source
