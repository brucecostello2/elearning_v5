"""WP-IVGS-10 — the visual description must depict the narration.

⛔ EVERY NARRATION AND EVERY VISUAL QUOTED IN THIS FILE IS VERBATIM from a
storyboard that actually shipped, read out of the live database on 2026-08-28.
A paraphrase would test a sentence I wrote rather than the one the pipeline
produced, and the whole point of this package is what the pipeline produces.

Sources:
  * project ``9c29b1d1-1322-40a4-9a65-00a95e934129`` — "two by two
    multiplication", 14 scenes, the operator's own in-flight project.
  * project ``c12fa967-f989-4ed4-8e20-3ea62cb92e8f`` — the conformance baseline
    ``reference-run-2026-08-23``, 18 scenes.
"""
from __future__ import annotations

import pytest

from app.services.storyboard_completeness import (
    DELEGATES,
    DEPICTS,
    GENERIC,
    SEV_FLAG,
    SEV_OK,
    SEV_REFUSE,
    StoryboardIncomplete,
    assess_scene,
    assess_storyboard,
    demands_on_screen_text,
    depicted_structure,
    names_a_numeral,
    referents,
    refuse_if_incomplete,
)


class _Row:
    """The attributes the classifier reads. Not an ORM row on purpose: the
    module takes anything with these names, and pinning that keeps the gate's
    in-memory overlay (`storyboard_reconcile._SceneView`) usable without a
    second code path."""

    def __init__(self, **kw):
        self.scene_index = kw.get("scene_index", 0)
        self.media_type = kw.get("media_type", "image")
        self.narration_text = kw.get("narration_text", "")
        self.visual_description = kw.get("visual_description", "")
        self.generation_params = kw.get("generation_params")
        self.media_rationale = kw.get("media_rationale")
        self.text_carried_by = kw.get("text_carried_by")


# ---------------------------------------------------------------------------
# THE OPERATOR'S OWN EXAMPLE
# ---------------------------------------------------------------------------

#: 9c29b1d1 scene 1, verbatim. The ruling of 2026-08-28 quotes this exact pair.
OPERATOR_NARRATION = (
    "First, we set up the problem. Write the numbers on top and underneath, "
    "making sure the ones digits line up and the tens digits line up. Draw a "
    "line underneath."
)
OPERATOR_VISUAL = (
    "A hand holding a pencil, poised over a blank sheet of lined paper with a "
    "ruler and a soft pink pencil case nearby, warm and gentle lighting"
)


def test_the_operators_own_example_is_caught():
    """The scene the ruling names, classified the way the ruling classifies it."""
    a = assess_scene(
        scene_index=1,
        media_type="image",
        narration_text=OPERATOR_NARRATION,
        visual_description=OPERATOR_VISUAL,
    )
    assert a.verdict == DELEGATES
    assert a.severity == SEV_REFUSE
    # And the reason must quote what the narration actually asked for, so a
    # reviewer is not asked to accept a verdict on their own words unsighted.
    assert "write" in a.reason.lower()


def test_the_operators_example_depicts_nothing_of_the_working_surface():
    """The measurement behind the ruling, isolated from the verdict.

    "a hand, a pencil, a ruler, a pink pencil case, warm lighting" names not one
    part of the working: no row, no column, no ruled line, no answer row. This
    is the assertion that would fail first if the structure lexicon were ever
    loosened until everything scored as content.
    """
    assert depicted_structure(OPERATOR_VISUAL) == ()
    refs = referents(OPERATOR_NARRATION)
    assert "write" in refs.written
    assert "draw a line" in refs.written
    assert refs.is_written_or_numeric


def test_a_visual_that_does_depict_the_step_passes():
    """9c29b1d1 scene 6's visual, verbatim — the one description in that
    storyboard that answers RULE 5's three questions."""
    visual = (
        "Over-the-shoulder view of a hand resting a pencil tip at the foot of a "
        "two-row column addition on lined paper; both partial-product rows are "
        "already written above a ruled horizontal line and the answer row "
        "beneath it is still empty; warm desk lamp from the left, upper right "
        "third of the sheet kept clear for the overlay"
    )
    depicted = depicted_structure(visual)
    assert "partial-product" in depicted
    assert "answer row" in depicted
    assert "already written" in depicted
    assert "still empty" in depicted


# ---------------------------------------------------------------------------
# THE OBJECTIVE LIMB — the only thing allowed to refuse
# ---------------------------------------------------------------------------

def test_numerals_plus_diffusion_plus_no_declaration_refuses():
    a = assess_scene(
        scene_index=9,
        media_type="image",
        # 9c29b1d1 scene 9, verbatim.
        narration_text=(
            "Multiply 1 times 2, which equals 2, and 1 times 3, which equals 3. "
            "Our first answer is 32."
        ),
        visual_description=(
            "Over-the-shoulder view of a hand resting a pencil tip at the foot "
            "of a two-row column layout on lined paper; the upper row is empty "
            "and the lower row has a multiplication sign to the left, a ruled "
            "horizontal line beneath, and the answer row still empty"
        ),
    )
    # ⛔ A GOOD DESCRIPTION DOES NOT RESCUE THE WRONG MEDIUM. This visual passes
    # RULE 5 comfortably -- it names the rows, the sign, the ruled line and the
    # empty answer row -- and it is STILL refused, because the narration's
    # content is four spoken numbers and an announced result, and an image model
    # cannot put any of them on the page. That is RULE 1-EXTENDED: the defect is
    # the delegation, not the prose.
    assert a.verdict == DELEGATES
    assert a.severity == SEV_REFUSE
    # ...and the description itself is NOT the complaint: it depicts the working
    # perfectly well. The reason names the delegation, not the prose.
    assert "diffusion medium" in a.reason


def test_the_declaration_lifts_the_refusal():
    a = assess_scene(
        scene_index=9,
        media_type="image",
        narration_text="Our first answer is 32.",
        visual_description=(
            "a two-row column layout on lined paper, the answer row still empty"
        ),
        text_carried_by="narration",
        media_rationale="image: the numbers are spoken; the page is what must be seen.",
    )
    assert a.verdict == DEPICTS
    assert a.severity == SEV_OK


def test_the_declaration_never_licenses_a_digit():
    """⛔ THE ESCAPE IS A DECLARATION, NOT A LOOPHOLE.

    RULE 1 is the older rule and it is checked BEFORE the declaration, so a
    declared scene whose description names a numeral is refused exactly as an
    undeclared one is. If this ordering is ever reversed, `text_carried_by`
    becomes a way to ask an image model for digits with the gate's blessing.
    """
    a = assess_scene(
        scene_index=1,
        media_type="image",
        narration_text="Write 23 on top and 14 underneath.",
        # c12fa967 scene 1's original visual, verbatim.
        visual_description=(
            "A close-up of a hand writing the multiplication problem 23 x 14 on "
            "a piece of paper, with the numbers lined up correctly and a line "
            "drawn underneath. The style is realistic, with a focus on the "
            "handwriting and the numbers."
        ),
        text_carried_by="narration",
    )
    assert a.verdict == DELEGATES
    assert a.severity == SEV_REFUSE
    assert "23" in a.reason


def test_a_description_can_demand_text_without_naming_a_digit():
    """RULE 1's other half, and the half no check has ever covered.

    Measured: 9c29b1d1 scene 12 asked for "a few key steps written in the
    margins" and scene 13 for "her paper with a few calculations on it"; the
    reference run's scene 15 asked for an infographic "with a focus on the steps
    and the calculations". None contains a numeral. All three are asking a
    diffusion model for legible writing.
    """
    assert names_a_numeral(
        "A summary page with a pencil and a soft pink background, warm and "
        "inviting lighting, with a few key steps written in the margins"
    ) == ()
    # ⛔ AND IT MUST BE THE TEXT OBJECT THAT TRIGGERS, NEVER THE BARE VERB.
    # v5's RULE 1 holds up "the first partial-product row already WRITTEN above
    # a ruled horizontal line" as the RIGHT answer; a check that matched the
    # word "written" would refuse the prompt's own gold standard, and an early
    # cut of this module did exactly that.
    assert "steps written" in demands_on_screen_text(
        "A summary page with a few key steps written in the margins"
    )
    assert demands_on_screen_text(
        "a partial-product row already written above a ruled horizontal line, "
        "the answer row still empty"
    ) == ()
    assert "calculations" in demands_on_screen_text(
        "A young girl smiling and holding up her paper with a few calculations on it"
    )


def test_a_motion_scene_with_no_template_refuses():
    """The GUI flip leaves ``{}``, and ``{}`` is an object that says nothing.

    WP-IVGS-09c measured six scenes in exactly this state. Written out because
    a bare truth test would be right by accident and wrong on ``{"seed": 1}``.
    """
    for params in (None, {}, {"seed": 1}):
        a = assess_scene(
            scene_index=2,
            media_type="motion_graphics",
            narration_text="Multiply 4 times 3, which equals 12.",
            visual_description="the carry travelling to the tens column",
            generation_params=params,
        )
        assert a.verdict == DELEGATES, params
        assert a.severity == SEV_REFUSE, params


def test_a_motion_scene_is_judged_by_its_template_not_its_prose():
    """⛔ THE ARITHMETIC CASE IS WP-IVGS-09f'S GUARD, CALLED NOT REIMPLEMENTED.

    A motion scene's content is its template; the description is a caption the
    renderer never reads. So the depiction test for this medium IS
    `verify_spec_against_narration`, and a scene with a good template and a
    thin caption passes while a scene with a fine caption and a contradicting
    template does not.
    """
    good = assess_scene(
        scene_index=5,
        media_type="motion_graphics",
        # 9c29b1d1 scene 5, verbatim.
        narration_text=(
            "Multiply 1 times 3, which equals 3, and 1 times 2, which equals 2. "
            "Our second answer is 230."
        ),
        visual_description="the tens row filling in",
        generation_params={
            "template": "column_multiplication_step",
            "top": 23, "bottom": 14, "step": 1, "phase": "complete",
        },
        context_text="solve a problem like 23 times 14",
    )
    assert good.verdict == DEPICTS

    # Scene 7's ORIGINAL spec, which WP-IVGS-09f measured and refused: it can
    # draw at most 230 under narration announcing 322.
    bad = assess_scene(
        scene_index=7,
        media_type="motion_graphics",
        narration_text="Then, 1 plus 2 equals 3. Our final answer is 322.",
        visual_description="the final answer being written",
        generation_params={
            "template": "column_multiplication_step",
            "top": 23, "bottom": 14, "step": 1, "phase": "full",
        },
        context_text="solve a problem like 23 times 14",
    )
    assert bad.verdict == DELEGATES
    assert bad.severity == SEV_REFUSE


# ---------------------------------------------------------------------------
# THE SOFT LIMB — and that it stays soft
# ---------------------------------------------------------------------------

def test_generic_is_a_flag_and_never_a_refusal():
    """⛔ THE HUMAN GATE STAYS THE JUDGE OF EVERYTHING SUBJECTIVE.

    9c29b1d1 scene 12, verbatim. Its narration names no numeral, so the
    objective limb has nothing to say; its visual names no part of the working,
    so it is GENERIC. That combination must FLAG and must never stop a release.
    """
    a = assess_scene(
        scene_index=12,
        media_type="image",
        narration_text=(
            "To multiply two-digit numbers, remember these four steps: multiply "
            "by the ones digit, start the next line with a zero, multiply by "
            "the tens digit, and add the two answers together."
        ),
        visual_description="A summary page with a pencil and a soft pink background",
    )
    assert a.verdict == GENERIC
    assert a.severity == SEV_FLAG
    assert not a.refuses


def test_a_missing_rationale_flags_but_never_refuses():
    a = assess_scene(
        scene_index=3,
        media_type="image",
        narration_text="The carry travels to the next column.",
        visual_description="a carry mark above the second column, the answer row still empty",
        text_carried_by=None,
    )
    assert a.severity == SEV_FLAG
    assert a.verdict == DEPICTS      # the picture is fine; the reason is unrecorded
    assert not a.refuses


def test_two_scenes_sharing_a_visual_are_generic_not_refused():
    """RULE 6, as a flag. Measured on a real v4 run: six of thirteen pictures
    were repeats, and content-hash de-duplication then collapsed them into
    shared bytes so the repetition never showed in the asset count."""
    shared = "A teacher standing in front of a clean, empty whiteboard, gesturing"
    rows = [
        _Row(scene_index=0, narration_text="Let us begin the lesson.", visual_description=shared),
        _Row(scene_index=11, narration_text="Let us review the lesson.", visual_description=shared),
    ]
    out = assess_storyboard(rows)
    assert out[0].severity != SEV_REFUSE
    assert out[1].verdict == GENERIC
    assert out[1].severity == SEV_FLAG
    assert "scene 0" in out[1].reason


def test_a_scene_with_no_content_bearing_narration_is_clean():
    a = assess_scene(
        scene_index=0,
        media_type="image",
        narration_text="Great job! You have finished the lesson.",
        visual_description="A young girl smiling at a desk, soft pink background",
    )
    assert a.severity == SEV_OK
    assert a.verdict == DEPICTS


# ---------------------------------------------------------------------------
# THE ENFORCEMENT POINT
# ---------------------------------------------------------------------------

def test_refuse_if_incomplete_names_every_failing_scene_at_once():
    """One exception for the whole storyboard, not one per press.

    A reviewer who fixes scene 1, approves, and is then told about scene 6 has
    been told the truth twice and helped neither time.
    """
    rows = [
        _Row(scene_index=1, media_type="image",
             narration_text=OPERATOR_NARRATION, visual_description=OPERATOR_VISUAL),
        _Row(scene_index=6, media_type="image",
             narration_text="Add 2 plus 0, which equals 2, and 9 plus 3, which equals 12.",
             visual_description="a hand moving a pencil across the paper"),
        _Row(scene_index=13, media_type="image",
             narration_text="Great job!", visual_description="a girl smiling"),
    ]
    with pytest.raises(StoryboardIncomplete) as exc:
        refuse_if_incomplete(rows)
    message = str(exc.value)
    assert "scene 1" in message
    assert "scene 6" in message
    assert len(exc.value.assessments) == 2      # scene 13 bears no content
    assert "scene 13" not in message


def test_refuse_if_incomplete_returns_the_soft_flags_when_nothing_refuses():
    rows = [
        _Row(scene_index=0, media_type="image",
             narration_text="Let us multiply two numbers together.",
             visual_description="a desk with a lamp"),
    ]
    out = refuse_if_incomplete(rows)
    assert [a.verdict for a in out] == [GENERIC]
    assert all(not a.refuses for a in out)


def test_a_clean_v7_storyboard_passes_the_gate():
    """The shape v7 is asking for, end to end, over one worked sum."""
    rows = [
        # ⛔ SCENE 0 NAMES THE OPERANDS, and it has to: WP-IVGS-09f's operand
        # grounding requires every literal parameter to be SPOKEN somewhere in
        # the lesson, because a lesson names each worked example's numbers once
        # and never again (measured: scene 10 of 9c29b1d1 never says 32 or 21).
        # A fixture whose opening scene does not introduce its sum is not a
        # storyboard this pipeline could produce.
        _Row(scene_index=0, media_type="image", text_carried_by="narration",
             narration_text=(
                 "Today we will multiply two-digit numbers together, like 23 "
                 "times 14."
             ),
             visual_description=(
                 "a child at a desk turning a page towards the camera; the "
                 "working surface is empty beneath a single ruled horizontal "
                 "line, warm lamp from the left"
             ),
             media_rationale="image with text_carried_by narration: the sum is spoken."),
        _Row(scene_index=1, media_type="image", text_carried_by="narration",
             narration_text="Write the numbers on top and underneath and draw a line beneath.",
             visual_description=(
                 "two rows one above the other on lined paper, right edges flush, "
                 "a ruled horizontal line beneath both and the answer row still empty"
             ),
             media_rationale="image with text_carried_by narration: the numbers are spoken."),
        _Row(scene_index=2, media_type="motion_graphics",
             narration_text=(
                 "We start by multiplying by the ones digit, which is 4 in 14. "
                 "Multiply 4 times 3, which equals 12. Write the 2 underneath "
                 "the ones column and carry the 1 above the tens column."
             ),
             visual_description="the carry travelling to the next column",
             generation_params={
                 "template": "column_multiplication_step",
                 "top": 23, "bottom": 14, "step": 0, "phase": "start",
             },
             media_rationale="motion_graphics: a digit is written and a carry travels."),
    ]
    out = refuse_if_incomplete(rows)
    assert [a.verdict for a in out] == [DEPICTS, DEPICTS, DEPICTS]
    assert not any(a.refuses for a in out)


# ---------------------------------------------------------------------------
# the two paths tell the reviewer two different, both-true things
# ---------------------------------------------------------------------------

def test_a_templateless_motion_scene_flags_on_review_and_refuses_on_release():
    """⛔ THE GATE PANEL MUST NOT SAY APPROVING WILL FAIL WHEN IT WILL NOT.

    `approve_storyboard` runs `_author_missing_motion_specs` BEFORE the
    enforcement check, so a motion scene with no template is going to be
    authored from its own narration, not rejected. And it is the state MOST
    motion scenes are in, because the frozen Stage-2 validator drops
    `generation_params` before the row is written (RC-P1) — measured on the
    acceptance run, where six of six motion scenes arrived template-less.

    On the ENFORCEMENT path the authoring has already run, so a template still
    missing is a genuine stop.
    """
    kwargs = dict(
        scene_index=2,
        media_type="motion_graphics",
        narration_text="Multiply 4 times 3, which equals 12, and carry the 1.",
        visual_description="the carry travelling to the tens column",
        generation_params=None,
    )
    review = assess_scene(**kwargs, authoring_will_run=True)
    assert review.severity == SEV_FLAG
    assert not review.refuses
    assert "author one" in review.reason

    release = assess_scene(**kwargs)
    assert release.severity == SEV_REFUSE
    assert release.verdict == DELEGATES


def test_a_motion_scene_that_HAS_a_contradicting_template_refuses_on_both_paths():
    """The leniency is scoped to ABSENCE. A template that provably contradicts
    its narration is a stop wherever it is assessed — authoring will not rescue
    it, it will re-author it, and if that fails the release refuses by name."""
    kwargs = dict(
        scene_index=7,
        media_type="motion_graphics",
        narration_text="Then, 1 plus 2 equals 3. Our final answer is 322.",
        visual_description="the final answer",
        generation_params={
            "template": "column_multiplication_step",
            "top": 23, "bottom": 14, "step": 1, "phase": "full",
        },
        context_text="solve a problem like 23 times 14",
    )
    assert assess_scene(**kwargs, authoring_will_run=True).refuses
    assert assess_scene(**kwargs).refuses
