"""Author a motion_graphics scene's template + parameters, one scene at a time.

WP-IVGS-09c. RUN-2 BLOCKER, AND THE MEASUREMENT THAT DEFINED IT.

Three paths can put a scene into ``media_type=motion_graphics``, and before this
module **only one of them could produce a scene that renders**:

* **v6 authoring it itself (stage 2).** RULE 8 of the live storyboard prompt
  tells the model that *"a motion_graphics scene is STRUCTURED DATA, not a
  description"* and asks it to emit ``generation_params`` with a template name
  and that template's parameters, choosing from exactly four. This works, and it
  only ever happens while the whole storyboard is being written.
* **The GUI flip.** Changes ``media_type`` and nothing else. Measured on project
  ``9c29b1d1``: six scenes at ``generation_params = {}`` with their *image*
  prose still in ``visual_description`` (*"Close-up of a hand moving a pencil
  across the paper"*). Nothing anywhere authored a template.
* **Per-scene Regen.** ⛔ **Never reaches a prompt at all.** ``regenerate_scene``
  goes to ``dispatch_scene_media_regeneration``, which re-renders media from the
  scene's *current* fields — it is a re-render path, by design, and WP-45's
  docstring says so in as many words: *"pressing Regen on a scene card does not
  re-run the storyboard LLM, it re-renders that scene's media."*

So a flipped scene had no way to become renderable, and the failure surfaced
deep in the run: all six refused at dispatch with the correct named error, the
stage failed, partial-advance carried the job into ``talking_head_render``, and
that is where the LatentSync OOM was met.

WHY NOT ``adapt-description``, WHICH IS THE OTHER MEDIUM-AWARE PROMPT.
It is prose-only and **deliberately excludes this medium**:
``adaptation_service.MEDIA_TYPES`` is ``("image", "video_clip", "animation")``
with a comment saying offering ``motion_graphics`` *"would ask the model to
write a description for a renderer that never reads one"*, and
``test_wp68_prompt_v6.py`` asserts the exclusion **so a future tidy-up does not
'fix' it into agreement**. Routing Regen through it would be exactly that
tidy-up. This module is the separate thing that was missing, not a widening of
the one that was right.

WHAT THIS ASKS FOR, AND WHAT IT REFUSES

One JSON object, for ONE scene. The catalogue it offers the model is built from
``shared.motion.templates`` — the same module the renderer draws from — so the
prompt cannot describe a template the renderer does not have, and a template
added there appears here without an edit.

⛔ **Nothing is invented on the model's behalf.** A reply naming a template that
does not exist, omitting a parameter the template declares, or inventing one it
does not, is REFUSED BY NAME. There is no "closest match", no default template
and no partial spec: a motion graphic that draws the wrong sum is worse than a
scene that says it could not be authored, because the arithmetic is the content
and no gate downstream reads it (WP62-L7 — human eyes until M3.3).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Budget for one scene's spec. A template call is a handful of tokens; this is
#: generous enough that a model which reasons briefly is not clipped, and small
#: enough that a runaway completion fails visibly rather than costing minutes.
MAX_TOKENS = 300

#: Low, and lower than adaptation's. This is not composition — the right answer
#: is largely determined by the lesson's own numbers, and creativity here means
#: teaching arithmetic the transcript never mentioned.
TEMPERATURE = 0.1


class MotionAuthoringError(RuntimeError):
    """A motion spec could not be authored. Always names why."""


def template_catalogue() -> Dict[str, Dict[str, Any]]:
    """The four templates, from the renderer's own module.

    Read from ``shared.motion.templates`` rather than restated here. A second
    list of what the templates are would be a second definition, and the
    renderer would keep drawing from the first one.
    """
    from shared.motion.templates import (
        param_kinds,
        template_names,
        template_spec,
    )

    return {
        name: {
            "params": dict(template_spec(name)["params"]),
            "kinds": param_kinds(name),
            "describes": template_spec(name)["describes"],
        }
        for name in template_names()
    }


def build_prompt(
    *,
    narration: str,
    visual_description: str,
    project_name: str,
    project_description: str,
    scene_index: int | None = None,
    context_scenes: "list[tuple[int, str]] | None" = None,
) -> str:
    """RULE 8's ask, narrowed to one scene — and ANCHORED TO THAT SCENE'S WORDS.

    The catalogue is rendered from the templates module, so the prompt and the
    renderer cannot disagree about what exists or what a parameter is called.

    WP-IVGS-09f. WHAT THIS PROMPT USED TO RECEIVE, AND WHY EVERY SCENE CAME BACK
    THE SAME. It got the narration, the image-era ``visual_description``, and the
    project name/description — **no scene index and no neighbours**. It then
    handed the model a fully worked answer in prose:

        So that scene is {"top": 23, "bottom": 14, "step": 0}

    At ``TEMPERATURE = 0.1`` a model shown a complete answer returns that answer.
    Measured on project ``9c29b1d1``: scenes 3, 4, 5, 7 and 10 all came back
    ``{"top": 23, "bottom": 14, "step": 1}`` — identical, and four of them wrong,
    while their narrations walk five different steps of two different sums.

    TWO CHANGES, AND THE SECOND IS THE ONE THAT MATTERS.

    1. **The worked example no longer uses this lesson's numbers.** It is stated
       on 47 x 36 so that copying it is visibly wrong rather than accidentally
       plausible, and the step-selection rule is spelled out per step kind
       instead of left to one word ("step") in a parameter gloss.

    2. **The scene is placed in its lesson.** A lesson works more than one sum:
       ``9c29b1d1`` does 23 x 14 in scenes 0-7 and 32 x 21 in scenes 8-11.
       Scene 10's own words are *"move to the tens digit, 2 ... 2 times 2 ... 2
       times 3 ... second answer is 640"* — **its multiplier 21 is never spoken
       in that scene at all**; it is spoken in scene 8. A prompt given only the
       scene's own narration therefore CANNOT resolve the operands, and asking
       it to would be asking it to guess. So neighbours are supplied, LABELLED
       BY INDEX and explicitly marked as context-for-operands-only: the scene's
       own words remain the sole authority on WHICH STEP this is.
    """
    from shared.motion.templates import PHASES

    #: A parameter is shown to the model with the SHAPE it actually takes.
    #: ⛔ Every parameter used to be rendered `<int>`, `label` included, and the
    #: live consequence is on project c12fa967 scene 1: `{"label": 0}`, a
    #: caption written as the integer zero because the prompt said it was one.
    #: The kinds come from the templates' own signatures (`param_kinds`), so a
    #: parameter cannot be advertised as one type and implemented as another.
    placeholder = {
        "int": "<int>",
        "text": "<short word>",
        "choice": " | ".join(f'"{v}"' for v in PHASES),
    }

    cat = template_catalogue()
    lines = []
    for name, spec in sorted(cat.items()):
        kinds = spec.get("kinds", {})
        params = ", ".join(
            f'"{p}": {placeholder.get(kinds.get(p, "int"), "<int>")}'
            for p in sorted(spec["params"])
        )
        lines.append(f'  {{"template": "{name}", {params}}}')
        lines.append(f"      {spec['describes']}")
        for pname, meaning in sorted(spec["params"].items()):
            lines.append(f"      {pname}: {meaning}")
    catalogue = "\n".join(lines)

    here = "this scene" if scene_index is None else f"scene {scene_index}"
    if context_scenes:
        ctx = "\n".join(
            f"  scene {i}: {(t or '').strip()}" for i, t in context_scenes
        )
    else:
        ctx = "  (no neighbouring scenes supplied)"

    return f"""You are authoring ONE motion-graphics scene for a maths lesson.

A motion_graphics scene is STRUCTURED DATA, not a description. The renderer does
not read prose; it takes a TEMPLATE NAME and that template's PARAMETERS and
draws the result itself in a real font. That is the point: a renderer that puts
"23" on screen cannot misspell it.

THE LESSON
  Title: {project_name}
  About: {project_description}

THE SCENE YOU ARE AUTHORING IS {here.upper()}, AND ITS OWN NARRATION IS THE ONLY
AUTHORITY ON WHICH STEP IT SHOWS:

  {narration or "(none recorded)"}

  (It also carries this description, written for a still image, which the
  renderer will never read and which you should ignore for arithmetic:
  {visual_description or "(none recorded)"})

THE SURROUNDING SCENES, FOR CONTEXT ONLY. A lesson often works MORE THAN ONE
SUM. Use these ONLY to discover which sum {here} belongs to and what its two
whole operands are — for example when {here} says "move to the tens digit" but
never repeats the numbers. DO NOT take the STEP from these; the step comes from
{here}'s own words above.

{ctx}

THE ONLY TEMPLATES THAT EXIST. Use a template name and parameter names EXACTLY
as written. Do not invent a template, a parameter, or a parameter spelling.

{catalogue}

CHOOSE THE TEMPLATE FROM WHAT THE WORDS DESCRIBE:

  the words multiply one digit of the multiplier through the top number,
  write a digit, carry, or announce that row's partial answer
      -> column_multiplication_step
  the words start a new row with a placeholder zero, or announce which
  multiplier digit is now being worked
      -> column_multiplication_step, with "step" naming THAT digit
  the words ADD the two partial answers together to reach the final total
      -> column_addition_carry, with top and bottom being THE TWO PARTIAL
         ANSWERS being added, not the original operands
  the words are about a number separating into its tens and its units
      -> place_value_split
  the words merely point at part of an existing sum
      -> highlight_and_hold

"step" COUNTS FROM THE UNITS DIGIT OF THE MULTIPLIER: step 0 is the multiplier's
ones digit, step 1 is its tens digit. Narration that says "multiplying by the
ones digit" is step 0; "now the tens digit" is step 1.

"phase" IS READ FROM THE WORDS, NEVER CALCULATED. "step" says WHICH multiplier
digit; "phase" says HOW FAR THROUGH THAT DIGIT'S ROW {here} gets, and a lesson
usually takes two scenes over one row. Decide it from {here}'s own sentence:

  the words write a digit and CARRY, and announce no result for the row
      -> "start"    (its first column only; the row is left incomplete)
  the words continue a row already begun and ANNOUNCE its result
    - "our first answer is 92", "that gives us 230"
      -> "complete" (opens with that first column already drawn, finishes the
                     row)
  one sentence really does walk the whole row start to finish, or the scene is
  a recap of a completed row
      -> "full"

⛔ THIS WAS MEASURED. Before "phase" existed, scenes 2 and 3 of project
9c29b1d1 rendered the IDENTICAL animation, and so did scenes 4 and 5: four
scenes, two pictures. The child heard "write the 2 and carry the 1" over a
picture that had already written the answer, then heard the answer over that
same picture again. Choosing "full" for a scene that only carries reproduces
exactly that, and it is refused.

THE PARAMETERS ARE THE LESSON'S WHOLE NUMBERS, NOT THE DIGITS THIS STEP
MULTIPLIES. A narration reading "multiply 6 times 7" inside a lesson working
47 x 36 is describing ONE STEP of that sum: the whole sum is what the template
draws. That scene is {{"top": 47, "bottom": 36, "step": 0}} — NOT
{{"top": 7, "bottom": 6}}. (47 x 36 is an ILLUSTRATION. It is not this lesson's
sum. Do not copy 47 or 36 into your answer.)

THE NUMBERS MUST BE THE ONES {here.upper()} ACTUALLY WORKS. If {here} announces a
result — "our second answer is 640" — then the template and parameters you
choose MUST be ones that produce that very number. A spec whose arithmetic does
not reach the number the learner is about to hear is wrong, and it will be
refused. Do not choose round or convenient numbers the lesson does not teach.

Reply with ONE JSON object and nothing else. No prose, no code fence, no
explanation.
"""


def parse_and_validate(raw: str) -> Dict[str, Any]:
    """The model's reply -> a spec the renderer will accept, or a named refusal.

    Every branch here refuses rather than repairs. The alternative — filling in
    a missing parameter, or matching a near-miss template name — produces a
    scene that renders confidently and teaches the wrong thing, which is the
    one failure this whole medium exists to prevent.
    """
    from shared.motion.templates import template_names, template_spec

    text = (raw or "").strip()
    # A code fence is the common, harmless deviation; strip it and keep going.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    # A model that prefaces the object is also common; take the first object.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise MotionAuthoringError(
                f"the model returned no JSON object. It said: {text[:200]!r}"
            )
        text = text[start : end + 1]

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MotionAuthoringError(
            f"the model's reply is not valid JSON ({exc}). It said: {text[:200]!r}"
        ) from exc

    if not isinstance(obj, dict):
        raise MotionAuthoringError(
            f"expected one JSON object, got {type(obj).__name__}: {text[:200]!r}"
        )

    name = obj.get("template")
    known = template_names()
    if name not in known:
        raise MotionAuthoringError(
            f"the model chose template {name!r}, which does not exist. The "
            f"renderer has exactly: {', '.join(known)}. Refused rather than "
            f"matched to the nearest one."
        )

    declared = set(template_spec(str(name))["params"])
    supplied = {k for k in obj if k != "template"}
    missing = sorted(declared - supplied)
    extra = sorted(supplied - declared)
    if missing or extra:
        faults = []
        if missing:
            faults.append(f"omitted {missing}")
        if extra:
            faults.append(f"invented {extra}")
        raise MotionAuthoringError(
            f"template {name!r} takes exactly {sorted(declared)}; the model "
            f"{' and '.join(faults)}. Refused rather than defaulted: a missing "
            f"parameter drawn from a default teaches arithmetic nobody asked for."
        )

    spec: Dict[str, Any] = {"template": str(name)}
    for key in sorted(declared):
        value = obj[key]
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise MotionAuthoringError(
                f"template {name!r} parameter {key!r} must be a number or a "
                f"short string; got {type(value).__name__} {value!r}"
            )
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        spec[key] = value

    # The renderer is the final authority: if it will not draw this, say so now
    # rather than at dispatch. Cheap — the templates module is pure data.
    from shared.motion.templates import render as render_template

    try:
        render_template(spec["template"], **{k: v for k, v in spec.items() if k != "template"})
    except Exception as exc:  # noqa: BLE001 — every rejection is one fact
        raise MotionAuthoringError(
            f"the templates module refused {spec!r}: {type(exc).__name__}: {exc}"
        ) from exc

    return spec


# ---------------------------------------------------------------------------
# THE NARRATION GUARD (WP-IVGS-09f)
#
# ⛔ THIS IS A GUARD, NOT THE L7 CHECKER, AND THE DIFFERENCE IS THE WHOLE POINT.
#
# WP62-L7 records that nothing downstream reads a motion scene's arithmetic —
# every quality gate measures output-against-input, so a template that draws a
# confident, beautifully rendered WRONG SUM passes all of them. The real checker
# for "does this teach the right thing" is human eyes until M3.3 lands one.
#
# This is not that. This is the much narrower, purely mechanical question:
#
#     does the spec CONTRADICT ITS OWN NARRATION?
#
# It cannot tell you a spec is correct. It can only tell you that a spec is
# provably inconsistent with the words the learner will hear over it — and it
# refuses those by name so they never reach a renderer. Everything it checks is
# derived from the templates module's own arithmetic, so it cannot drift from
# what the renderer will actually draw.
#
# It would have caught, mechanically and without a model:
#   * scene 7  — authored column_multiplication_step(23,14,1), which can draw at
#                most 230, over narration that says "our final answer is 322"
#   * scene 10 — authored (23,14,1) -> 230, over narration that says "our second
#                answer is 640", a different sum entirely
# It would NOT have caught scene 2's original {"top": 14, "bottom": 3}: 14 and 3
# both appear in that scene's words. That one is the prompt's job (the
# whole-numbers rule), and saying so is more useful than pretending otherwise.

#: Words that mean "this scene adds two partial answers together".
_ADD_WORDS = ("add", "plus", "together", "sum")
#: Words that mean "a digit carried into the next column".
_CARRY_WORDS = ("carry", "carried", "carrying")
#: Words that mean "this scene announces a result".
_ANSWER_WORDS = ("answer", "total", "altogether")
#: Words that mean "a number is being split into tens and units".
_PLACE_WORDS = ("place value", "tens place", "ones place", "means 10", "split")
#: Words that mean "a multiplication step is being worked".
_MULT_WORDS = ("multiply", "multiplying", "times", "digit", "placeholder", "zero")

#: Which keyword class each template REQUIRES the narration to be in. A template
#: absent from this map is unconstrained (``highlight_and_hold`` only points at
#: an existing sum, so any narration can legitimately want it).
_TEMPLATE_REQUIRES: Dict[str, tuple] = {
    "column_addition_carry": _ADD_WORDS,
    "column_multiplication_step": _MULT_WORDS,
    "place_value_split": _PLACE_WORDS,
}


def narration_numbers(narration: str) -> "set[int]":
    """Every standalone integer the narration says, as ints.

    Word boundaries matter: "322" must not also yield 32 or 22, or the
    producibility check below would accept a spec that reaches a substring of
    the number the learner hears.
    """
    return {int(m) for m in re.findall(r"\b\d+\b", narration or "")}


def producible_numbers(spec: Dict[str, Any]) -> "set[int]":
    """Every number this exact spec can legitimately put in front of a learner.

    Computed the way the TEMPLATE computes it — same digit order, same carries,
    same placeholder shift — so this set cannot drift from what is drawn.
    """
    name = spec.get("template")
    out: "set[int]" = set()

    def digits(n: int) -> "list[int]":
        return [int(c) for c in str(abs(int(n)))][::-1]  # units first, as the renderer

    # WP-IVGS-10. `phase` NARROWS WHAT A TEMPLATE PRODUCES, AND THAT IS THE
    # POINT OF IT. `column_multiplication_step(23, 14, step=0)` reaches 92 at
    # `phase="full"` and reaches only 2-carry-1 at `phase="start"`, because the
    # row is deliberately left half written. A producibility set computed
    # without the phase would let a `start` scene sit under narration announcing
    # the row's answer -- exactly the class of contradiction assertion 2b
    # exists to refuse. Absent or "full" reproduces the pre-phase set exactly.
    phase = str(spec.get("phase", "full") or "full").strip().lower()

    if name == "column_multiplication_step":
        a, b, step = int(spec["top"]), int(spec["bottom"]), int(spec["step"])
        db = digits(b)
        step = max(0, min(step, len(db) - 1))
        multiplier = db[step]
        da = digits(a)
        # `start` writes the first column only, so the row's total is never on
        # screen; `complete` and `full` both finish the row.
        first_only = phase == "start" and len(da) > 1
        if not first_only:
            out |= {a, b, multiplier, a * multiplier, a * multiplier * (10 ** step)}
        else:
            out |= {a, b, multiplier}
        carry = 0
        for i, d in enumerate(da):
            if first_only and i > 0:
                break
            total = d * multiplier + carry
            out |= {d, d * multiplier, total, total % 10}
            carry = total // 10
            if carry:
                out.add(carry)
    elif name == "column_addition_carry":
        a, b = int(spec["top"]), int(spec["bottom"])
        da, db = digits(a), digits(b)
        first_only = phase == "start" and max(len(da), len(db)) > 1
        out |= {a, b} if first_only else {a, b, a + b}
        carry = 0
        for i in range(max(len(da), len(db))):
            if first_only and i > 0:
                break
            total = (da[i] if i < len(da) else 0) + (db[i] if i < len(db) else 0) + carry
            out |= {total, total % 10}
            carry = total // 10
            if carry:
                out.add(carry)
        out |= set(da) | set(db)
    elif name == "place_value_split":
        n = int(spec["number"])
        out |= {n, (abs(n) // 10) * 10, abs(n) % 10}
    elif name == "highlight_and_hold":
        a, b = int(spec["top"]), int(spec["bottom"])
        out |= {a, b, int(spec.get("column", 0))} | set(digits(a)) | set(digits(b))

    return out


def verify_spec_against_narration(
    spec: Dict[str, Any],
    narration: str,
    *,
    context_text: str = "",
    scene_index: Any = None,
) -> None:
    """Refuse a spec that contradicts the words it will play under.

    Three assertions, cheapest first, each refusing BY NAME. Raises
    ``MotionAuthoringError``; returns ``None`` when the spec is merely not
    provably wrong — which is not the same as right (see the block above).
    """
    where = "this scene" if scene_index is None else f"scene {scene_index}"
    words = (narration or "").lower()
    name = str(spec.get("template"))
    said = narration_numbers(narration)
    can_draw = producible_numbers(spec)
    params = {k: v for k, v in spec.items() if k != "template"}

    # 1. STEP KIND. The template must be one the words could plausibly want.
    required = _TEMPLATE_REQUIRES.get(name)
    if required and not any(w in words for w in required):
        raise MotionAuthoringError(
            f"{where}: template {name!r} needs narration about "
            f"{'/'.join(required[:3])}, and this scene's words contain none of "
            f"them: {narration.strip()[:160]!r}. Refused rather than rendered — "
            f"a template that animates a step the words never mention teaches "
            f"over the top of them."
        )

    # 2. PRODUCIBILITY — the assertion that catches a spec pointed at the wrong
    #    sum. If the learner is about to HEAR a number, the animation must be
    #    able to REACH it. Only numbers larger than anything the template can
    #    produce are treated as proof of contradiction; small shared digits are
    #    not evidence either way, and pretending they are would refuse correct
    #    specs.
    ceiling = max(can_draw) if can_draw else 0
    unreachable = sorted(n for n in said if n > ceiling)
    if unreachable:
        raise MotionAuthoringError(
            f"{where}: the narration says {unreachable[0]}, which "
            f"{name}{params} can never draw — the largest number it produces is "
            f"{ceiling}. The spec is pointed at a different sum from the words. "
            f"Refused rather than rendered."
        )

    # 2b. THE ANNOUNCED RESULT. Stronger than the ceiling above, and narrower:
    #     when a sentence ANNOUNCES a result — "our first answer is 92" — that
    #     exact number must be one the template actually produces, not merely
    #     one it does not exceed. This is what separates step 0 from step 1 of
    #     the same sum: (23,14,step=1) draws 230 and never 92, so it cannot sit
    #     under narration announcing 92, even though 92 < 230 and the ceiling
    #     test alone lets it through. Measured: that is exactly what scene 3
    #     carried. Restricted to the announcing SENTENCE on purpose — scene 7
    #     also says "23 times 14 equals 322" while adding 92 and 230, and those
    #     operands belong to the lesson, not to this template's arithmetic.
    for sentence in re.split(r"(?<=[.!?])\s+", narration or ""):
        if not any(w in sentence.lower() for w in _ANSWER_WORDS):
            continue
        for n in sorted(narration_numbers(sentence)):
            if n not in can_draw:
                raise MotionAuthoringError(
                    f"{where}: the narration announces {n} — "
                    f"{sentence.strip()[:90]!r} — but {name}{params} never "
                    f"produces {n}; it draws {sorted(can_draw)[-6:]}. The words "
                    f"and the animation would disagree in front of the learner. "
                    f"Refused rather than rendered."
                )

    # 4. THE MULTIPLIER THE WORDS NAME. Narration in this lesson's own idiom
    #    states the step and the multiplier together — "the ones digit, which is
    #    4 in 14" — and that sentence pins TWO things mechanically: the
    #    multiplier is 14, and the digit being worked is 4, so `step` must be
    #    the position of 4 within 14.
    #
    #    This is the assertion that catches an inverted spec, which neither the
    #    ceiling nor the announced-result test can see. Measured: scene 2
    #    carried {"top": 14, "bottom": 3} over exactly that sentence — 14 read as
    #    the multiplicand when the words call it the multiplier. Every number in
    #    that spec appears in the narration and nothing it draws exceeds what the
    #    words say, so tests 1-3 all pass it. This one does not.
    #
    #    Only fires when the narration actually uses the construction; silence is
    #    not evidence of anything and is not treated as such.
    if name == "column_multiplication_step":
        m = re.search(
            r"(ones|tens)\s+digit,?\s+which\s+is\s+(\d+)\s+in\s+(\d+)",
            words,
        )
        if m:
            spoken_digit, spoken_multiplier = int(m.group(2)), int(m.group(3))
            bottom = int(spec["bottom"])
            if bottom != spoken_multiplier:
                raise MotionAuthoringError(
                    f"{where}: the narration calls {spoken_multiplier} the number "
                    f"being multiplied BY — {m.group(0)!r} — but the spec makes "
                    f"the multiplier {bottom} (bottom={bottom}, top={spec['top']}). "
                    f"The two operands are the wrong way round. Refused rather "
                    f"than rendered."
                )
            db_digits = [int(c) for c in str(abs(bottom))][::-1]
            step_i = max(0, min(int(spec["step"]), len(db_digits) - 1))
            if db_digits[step_i] != spoken_digit:
                raise MotionAuthoringError(
                    f"{where}: the narration works the digit {spoken_digit} of "
                    f"{spoken_multiplier} — {m.group(0)!r} — but step="
                    f"{spec['step']} selects {db_digits[step_i]}. The animation "
                    f"would work a different digit from the one the learner "
                    f"hears named. Refused rather than rendered."
                )

    # 5. THE PHASE THE WORDS DESCRIBE (WP-IVGS-10, RC-O10).
    #
    # ⛔ ASSERTIONS 1-4 ARE UNCHANGED BY THIS PACKAGE, byte for byte. This is an
    # addition, and it exists because `phase` is a new parameter: a guard that
    # cannot see a parameter cannot refuse a spec that gets it wrong, and RC-O10
    # was opened precisely because two consecutive scenes rendered the same
    # picture. Adding the parameter without adding its assertion would move the
    # defect from "the template cannot tell these apart" to "the template can
    # and nothing checks whether it did".
    #
    # Two mechanical facts, and it fires only when the words state one of them:
    #
    #   * A scene that ANNOUNCES the row's answer -- "our first answer is 92" --
    #     has finished the row. It cannot be `phase="start"`, which by
    #     construction leaves the row incomplete. (Assertion 2b already catches
    #     this now that producibility is phase-aware; this states it in words a
    #     reader can act on rather than as an unreachable number.)
    #   * A scene that CARRIES with nothing else after it -- "write the 2 and
    #     carry the 1" and no announced total -- is the beginning of a row, not
    #     the whole of it. `phase="full"` there draws the answer before the
    #     narration reaches it, which is the RC-O10 defect seen from the other
    #     side.
    #
    # Silence is not evidence. A narration that states neither is left alone.
    if name in ("column_multiplication_step", "column_addition_carry"):
        phase = str(spec.get("phase", "full") or "full").strip().lower()
        announces = any(
            any(w in sentence.lower() for w in _ANSWER_WORDS)
            and narration_numbers(sentence)
            for sentence in re.split(r"(?<=[.!?])\s+", narration or "")
        )
        if announces and phase == "start":
            raise MotionAuthoringError(
                f"{where}: the narration announces this row's result, so the "
                f"scene finishes the row — but phase='start' writes only its "
                f"first column and deliberately leaves it incomplete. The "
                f"learner would hear the answer over a picture that does not "
                f"contain it. Use phase='complete' (the first column already "
                f"written by the previous scene) or 'full'. Refused rather "
                f"than rendered."
            )
        carries = any(w in words for w in _CARRY_WORDS)
        if carries and not announces and phase == "full":
            raise MotionAuthoringError(
                f"{where}: the narration writes a digit and carries, and "
                f"announces no result — that is the BEGINNING of a row — but "
                f"phase='full' draws the whole row, so the answer appears "
                f"before the words reach it and the next scene has nothing "
                f"left to show. That is RC-O10, the defect this parameter "
                f"exists to close. Use phase='start'. Refused rather than "
                f"rendered."
            )

    # 3. OPERAND GROUNDING. Every literal number in the params must be spoken
    #    somewhere real — this scene, or the surrounding scenes that establish
    #    which sum is being worked. A lesson's second worked example names its
    #    operands once, in its opening scene, and never again (measured: scene
    #    10 of 9c29b1d1 never says 32 or 21), so the scene's own words alone are
    #    NOT a sufficient source and requiring them would refuse correct specs.
    grounded = said | narration_numbers(context_text)
    for key, value in sorted(params.items()):
        if not isinstance(value, int) or isinstance(value, bool):
            continue          # `label` and friends are prose, not arithmetic
        if key == "step" or 0 <= value <= 9:
            continue          # a step index / single digit is structural, not a quantity
        if value not in grounded:
            raise MotionAuthoringError(
                f"{where}: parameter {key}={value} appears nowhere in this "
                f"scene's narration or its neighbours', so it was invented. "
                f"Spoken numbers are {sorted(grounded)}. Refused rather than "
                f"rendered."
            )


def has_motion_spec(generation_params: Any) -> bool:
    """Whether a scene already carries a template. ``{}`` and ``None`` do not.

    The GUI flip leaves ``{}`` — an object that exists and says nothing — and
    ``{}`` is falsy, so a bare truth test would have been right by accident.
    Written out because the distinction is the whole defect.
    """
    return isinstance(generation_params, dict) and bool(generation_params.get("template"))


async def author_params_for_scene(
    db: AsyncSession,
    *,
    project_id: UUID,
    narration: str,
    visual_description: str,
    project_name: str,
    project_description: str,
    scene_index: Any = None,
    context_scenes: "list[tuple[int, str]] | None" = None,
) -> Dict[str, Any]:
    """Ask the storyboard model for this scene's template + parameters.

    Runs on the **storyboard-generation binding**, deliberately and for the same
    reason ``adapt-description`` does: RULE 8 is a storyboard rule, and the model
    that writes storyboards is the one that has been told what these templates
    are. It does not fall back to another model.

    WP-IVGS-09f: the reply is now also checked AGAINST THIS SCENE'S OWN WORDS by
    ``verify_spec_against_narration`` before it is returned. A spec that
    contradicts its narration is refused here, where the refusal names the scene
    and costs nothing, rather than rendered into a draft an operator has to
    watch to discover.
    """
    from app.services.adaptation_service import _call_model, _resolve_binding

    resolved = await _resolve_binding(db, project_id)
    prompt = build_prompt(
        narration=narration,
        visual_description=visual_description,
        project_name=project_name,
        project_description=project_description,
        scene_index=scene_index,
        context_scenes=context_scenes,
    )
    answer = await _call_model(
        prompt,
        endpoint=resolved["endpoint"],
        model=resolved["model"],
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    spec = parse_and_validate(answer.get("content", ""))
    verify_spec_against_narration(
        spec,
        narration,
        context_text=" ".join(t or "" for _, t in (context_scenes or [])),
        scene_index=scene_index,
    )
    logger.info(
        "motion_spec_authored project=%s scene_index=%s template=%s params=%s "
        "binding=%s narration_verified=True",
        project_id, scene_index, spec.get("template"),
        {k: v for k, v in spec.items() if k != "template"},
        resolved["binding"],
    )
    return spec
