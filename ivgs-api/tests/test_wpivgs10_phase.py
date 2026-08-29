"""WP-IVGS-10 Task 4 — the template distinguishes its phases (RC-O10).

⛔ WHAT RC-O10 RECORDED, and it was read by eye on real frames before it was
written down: *"Scenes 2 and 3 render the identical animation; so do 4 and 5.
One multiplier digit of one sum, and the template takes only (top, bottom,
step) -- it cannot separate 'write the 2, carry the 1' from '...so our first
answer is 92'."*

The narrations quoted below are verbatim from project
``9c29b1d1-1322-40a4-9a65-00a95e934129``, scenes 2 to 5, read from the live
database on 2026-08-28. Those four scenes are the reason this parameter exists.
"""
from __future__ import annotations

import hashlib

import pytest

from app.services.motion_authoring import (
    MotionAuthoringError,
    parse_and_validate,
    producible_numbers,
    verify_spec_against_narration,
)
from shared.motion.templates import PHASES, param_kinds, render, template_spec

# 9c29b1d1, verbatim.
N2 = (
    "We start by multiplying by the ones digit, which is 4 in 14. Multiply 4 "
    "times 3, which equals 12. Write the 2 underneath the ones column and "
    "carry the 1 above the tens column."
)
N3 = (
    "Next, multiply 4 times 2, which equals 8. Add the carried 1 to get 9. So, "
    "our first answer is 92."
)
N4 = (
    "Now, we multiply by the tens digit, which is 1 in 14. Remember, this 1 "
    "means 10 because it's in the tens place. Put a zero in the ones place as "
    "a placeholder."
)
N5 = (
    "Multiply 1 times 3, which equals 3, and 1 times 2, which equals 2. Our "
    "second answer is 230."
)
CTX = (
    "Let's learn how to multiply two-digit numbers. By the end, you'll be able "
    "to solve a problem like 23 times 14 on your own."
)


def _texts(frame):
    return [op.text for op in frame.ops if op.op.value == "text"]


def _digest(rendered) -> str:
    return hashlib.sha256(repr(rendered.frames).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# ⛔ `full` MUST NOT MOVE
# ---------------------------------------------------------------------------

#: Digests of the ops of every template, taken from this module BEFORE `phase`
#: existed (2026-08-28, commit 08521bd). Every banked frame in
#: `dev/workpackages/reference/` and every rendered asset on the fleet was
#: produced by that code, so `full` moving is not a refactor -- it is silently
#: invalidating evidence, and the frame COUNT does not catch it: an early cut of
#: this package put the placeholder zero into the opening hold and produced 83
#: frames at step=1 exactly as before, with different pixels.
PRE_PHASE_DIGESTS = {
    ("column_multiplication_step", (23, 14, 0)): "f614cd2acc14b8c2",
    ("column_multiplication_step", (23, 14, 1)): "71bc3b21f2b88f50",
    ("column_multiplication_step", (32, 21, 1)): "55e9a84cdfbf1464",
}
PRE_PHASE_ADD_DIGESTS = {
    (230, 92): "9e5df190d8b2ba7a",
    (27, 15): "e0d67515954c23a7",
}


@pytest.mark.parametrize("key,want", sorted(PRE_PHASE_DIGESTS.items()))
def test_multiplication_full_is_byte_identical_to_the_pre_phase_renderer(key, want):
    _, (top, bottom, step) = key
    assert _digest(render("column_multiplication_step", top=top, bottom=bottom, step=step)) == want
    # and passing the default explicitly is the same thing
    assert _digest(
        render("column_multiplication_step", top=top, bottom=bottom, step=step, phase="full")
    ) == want


@pytest.mark.parametrize("key,want", sorted(PRE_PHASE_ADD_DIGESTS.items()))
def test_addition_full_is_byte_identical_to_the_pre_phase_renderer(key, want):
    top, bottom = key
    assert _digest(render("column_addition_carry", top=top, bottom=bottom)) == want
    assert _digest(render("column_addition_carry", top=top, bottom=bottom, phase="full")) == want


def test_a_render_is_byte_stable_per_params_and_phase():
    """Determinism is the property the conformance baseline and Temporal need."""
    for phase in PHASES:
        a = render("column_multiplication_step", top=23, bottom=14, step=0, phase=phase)
        b = render("column_multiplication_step", top=23, bottom=14, step=0, phase=phase)
        assert _digest(a) == _digest(b)


# ---------------------------------------------------------------------------
# RC-O10 ITSELF: consecutive sub-steps are now different pictures
# ---------------------------------------------------------------------------

def test_scenes_2_and_3_no_longer_render_the_same_animation():
    """THE DEFECT, as one assertion.

    Before this parameter both scenes were `(23, 14, step=0)` and rendered
    identically. Now scene 2 is `start` -- it writes the 2, the carry travels,
    and the row is left incomplete -- and scene 3 is `complete`, opening on
    exactly that page and finishing at 92.
    """
    start = render("column_multiplication_step", top=23, bottom=14, step=0, phase="start")
    complete = render("column_multiplication_step", top=23, bottom=14, step=0, phase="complete")
    assert _digest(start) != _digest(complete)

    # `start` ends with the units digit written and the carry above the next
    # column -- and WITHOUT the 9 that scene 3's words have not reached yet.
    assert _texts(start.frames[-1])[-2:] == ["2", "1"]
    # `complete` OPENS on that page: the 2 and the carry are already drawn.
    assert _texts(complete.frames[0])[-2:] == ["2", "1"]
    # ...and ends with the row finished.
    assert _texts(complete.frames[-1])[-3:] == ["2", "9", "1"]


def test_scenes_4_and_5_no_longer_render_the_same_animation():
    start = render("column_multiplication_step", top=23, bottom=14, step=1, phase="start")
    complete = render("column_multiplication_step", top=23, bottom=14, step=1, phase="complete")
    assert _digest(start) != _digest(complete)
    # step 1 writes its placeholder zero first, then the first column.
    assert _texts(start.frames[-1])[-2:] == ["0", "3"]
    assert _texts(complete.frames[0])[-2:] == ["0", "3"]
    assert _texts(complete.frames[-1])[-3:] == ["0", "3", "2"]      # 230


def test_start_hands_the_page_to_complete_unchanged():
    """The property that makes two scenes read as one continuous page.

    `start`'s last frame and `complete`'s first frame must show the same marks.
    If they ever diverge the lesson jumps between scenes, which is worse than
    the repetition RC-O10 opened for.
    """
    for step in (0, 1):
        start = render("column_multiplication_step", top=23, bottom=14, step=step, phase="start")
        complete = render("column_multiplication_step", top=23, bottom=14, step=step, phase="complete")
        assert _texts(start.frames[-1]) == _texts(complete.frames[0])


def test_start_never_writes_the_leading_carry_digit():
    """A row `start` leaves incomplete must not have its final carry resolved.

    23 x 14 step 0: the row is 92, and its leading 9 comes from the carry. If
    `start` wrote it, the answer would be on screen under narration that has
    not reached it -- exactly the defect, moved one column left.
    """
    start = render("column_multiplication_step", top=23, bottom=14, step=0, phase="start")
    assert "9" not in _texts(start.frames[-1])


def test_addition_phases_are_distinct_and_continuous():
    start = render("column_addition_carry", top=230, bottom=92, phase="start")
    complete = render("column_addition_carry", top=230, bottom=92, phase="complete")
    assert _digest(start) != _digest(complete)
    assert _texts(start.frames[-1]) == _texts(complete.frames[0])
    assert _texts(complete.frames[-1])[-4:] == ["2", "2", "3", "1"]      # 322 + the carry


def test_an_unknown_phase_is_refused_by_name_not_defaulted():
    """Refused, never coerced. A phase silently read as "full" renders the whole
    row under narration describing half of it, and no gate downstream reads it."""
    with pytest.raises(ValueError) as exc:
        render("column_multiplication_step", top=23, bottom=14, step=0, phase="middle")
    assert "middle" in str(exc.value)
    for name in PHASES:
        assert name in str(exc.value)


# ---------------------------------------------------------------------------
# the parameter reaches the model, the guard and the renderer contract
# ---------------------------------------------------------------------------

def test_both_column_templates_declare_phase():
    for name in ("column_multiplication_step", "column_addition_carry"):
        assert "phase" in template_spec(name)["params"]
        assert param_kinds(name)["phase"] == "choice"


def test_phase_is_offered_to_the_model_as_words_not_as_an_integer():
    """⛔ THE DEFECT THIS PREVENTS IS ON THE RECORD.

    `build_prompt` rendered every parameter as `<int>`, `label` included, and
    project c12fa967 scene 1 carries `{"label": 0}` as a result -- a caption
    written as the integer zero because the prompt said it was one. `phase`
    would have inherited that on the day it was added.
    """
    from app.services.motion_authoring import build_prompt

    prompt = build_prompt(
        narration=N2, visual_description="", project_name="p",
        project_description="d", scene_index=2, context_scenes=[(0, CTX)],
    )
    assert '"phase": "full" | "start" | "complete"' in prompt
    assert '"label": <short word>' in prompt
    assert '"label": <int>' not in prompt


def test_producibility_narrows_with_the_phase_and_is_unchanged_without_it():
    spec = {"template": "column_multiplication_step", "top": 23, "bottom": 14, "step": 0}
    no_phase = producible_numbers(dict(spec))
    full = producible_numbers({**spec, "phase": "full"})
    start = producible_numbers({**spec, "phase": "start"})
    # A spec written before this package behaves exactly as it did.
    assert no_phase == full
    # `start` cannot reach the row's answer, and that is what refuses a `start`
    # scene sitting under "our first answer is 92".
    assert 92 in full and 92 not in start
    assert start < full


@pytest.mark.parametrize(
    "narration,step,phase",
    [(N2, 0, "start"), (N3, 0, "complete"), (N4, 1, "start"), (N5, 1, "complete")],
)
def test_the_four_measured_scenes_now_author_to_four_distinct_specs(narration, step, phase):
    spec = {
        "template": "column_multiplication_step",
        "top": 23, "bottom": 14, "step": step, "phase": phase,
    }
    verify_spec_against_narration(spec, narration, context_text=CTX, scene_index=2)


def test_the_guard_refuses_a_carrying_scene_rendered_full():
    """RC-O10 seen from the other side: `full` under narration that only carries
    shows the learner the answer before the words reach it."""
    with pytest.raises(MotionAuthoringError) as exc:
        verify_spec_against_narration(
            {"template": "column_multiplication_step", "top": 23, "bottom": 14,
             "step": 0, "phase": "full"},
            N2, context_text=CTX, scene_index=2,
        )
    assert "RC-O10" in str(exc.value)


def test_the_guard_refuses_an_announcing_scene_rendered_start():
    with pytest.raises(MotionAuthoringError) as exc:
        verify_spec_against_narration(
            {"template": "column_multiplication_step", "top": 23, "bottom": 14,
             "step": 0, "phase": "start"},
            N3, context_text=CTX, scene_index=3,
        )
    assert "92" in str(exc.value)


def test_a_spec_omitting_phase_is_refused_at_parse_rather_than_defaulted():
    """`parse_and_validate` requires every declared parameter, so a model that
    ignores RULE 8's new field is told, instead of having a phase chosen for it."""
    with pytest.raises(MotionAuthoringError) as exc:
        parse_and_validate('{"template": "column_multiplication_step", '
                           '"top": 23, "bottom": 14, "step": 0}')
    assert "phase" in str(exc.value)


def test_an_invalid_phase_from_the_model_is_refused_at_parse():
    with pytest.raises(MotionAuthoringError) as exc:
        parse_and_validate('{"template": "column_multiplication_step", "top": 23, '
                           '"bottom": 14, "step": 0, "phase": "middle"}')
    assert "refused" in str(exc.value).lower()


def test_the_capability_contract_and_the_renderer_agree_about_phase():
    """Two lists, one truth. `ivgs-motion-renderer` refuses by name against the
    WP-67 contract, so a parameter in one and not the other is a 400 on a spec
    the templates would have drawn."""
    from pathlib import Path

    from shared.providers.client_registry import (
        contract_for,
        register_builtin_clients,
    )

    register_builtin_clients()
    contract = contract_for("animation_generation", "motion_graphics", "maths_motion")
    assert contract is not None
    assert "phase" in contract.accepts_params

    path = Path(__file__).resolve().parents[2] / "ivgs-motion-renderer" / "main.py"
    text = path.read_text(encoding="utf-8")
    declared = text.split("_ACCEPTED_PARAMS = frozenset(")[1].split(")")[0]
    assert '"phase"' in declared
