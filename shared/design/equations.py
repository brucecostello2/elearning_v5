"""Is the arithmetic a scene SAYS actually true? — WP-IVGS-12i2, RC-S4.

⛳ THE OPERATOR'S CATCH, 2026-08-30, on the regenerated live design. Scene 4's
narration reads:

    "To multiply two double-digit numbers, we need to multiply the tens and the
     units separately."

That is the classic double-digit multiplication misconception, taught as method.
A learner who follows it computes 23 × 14 as 20 × 10 + 3 × 4 = 212. ⛔ **Nothing
anywhere in this pipeline checks whether what a scene says about mathematics is
true.** Every check that exists asks whether the scene is DECLARED
(`instructional_event`, `serves_outcomes`, provenance), whether the visual can
DEPICT it (`storyboard_completeness`), or whether the template contradicts the
words (`motion_authoring.verify_spec_against_narration`). Not one asks whether
the words are RIGHT.

WHAT THIS MODULE DOES, AND THE HALF IT DELIBERATELY REFUSES TO ATTEMPT

It lints **complete arithmetic claims** — a statement naming both operands, the
operation and the result, in prose or in symbols:

    "4 times 3 equals 12"       "23 x 14 = 322"      "9 plus 3 is 12"
    "12 minus 5 equals 7"       "144 divided by 12 = 12"

A complete claim is decidable by arithmetic with no taste involved, so a false
one is a **hard refusal**, named with the scene and the claim.

⛔ **SCENE 4'S OWN SHAPE IS NOT LINTABLE HERE AND THIS MODULE MUST NOT PRETEND
OTHERWISE.** *"Multiply the tens and the units separately"* contains no numerals
and states no equation. It is a METHOD claim, it is wrong, and deciding that
requires knowing what the method computes — which is a semantic judgement about
generated prose, not arithmetic. That half stays at the human gate until the L7
checker (M3.3), and RC-S4's ledger row says so with this scene as the driving
evidence. **A lint that quietly scored method prose would be worse than none:
it would let a reviewer believe the maths had been checked.**

⚠ AND THE PRIMARY GUARD FOR AN UPLOADED SCRIPT IS NOT THIS MODULE. It is
RC-S2's fidelity rule: **a design anchored to a correct script cannot state a
wrong method**, because its narration comes from the script. Scene 4 exists
because the regenerated design used 110 characters of a 3,138-character script
and invented the rest. This lint catches the arithmetic; fidelity is what stops
the invention.

WHAT IS AND IS NOT A CLAIM

⛔ **A PARTIAL STATEMENT IS NOT A CLAIM AND IS NEVER REFUSED.** *"Now multiply 4
times 3"* asserts nothing; *"write the 2 underneath and carry the 1"* asserts
nothing arithmetic at all. Only a statement carrying **both operands and the
result** is decidable, and the parser is built so that anything short of that
falls out rather than being guessed at. The cost of that choice is false
negatives, which are the right failures for a check that hard-refuses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

#: The operations a claim may use, as the verb/symbol vocabulary a narration
#: actually uses, mapped to the function that decides them.
_OPS = {
    "times": ("×", lambda a, b: a * b),
    "multiplied by": ("×", lambda a, b: a * b),
    "x": ("×", lambda a, b: a * b),
    "*": ("×", lambda a, b: a * b),
    "×": ("×", lambda a, b: a * b),
    "plus": ("+", lambda a, b: a + b),
    "+": ("+", lambda a, b: a + b),
    "minus": ("−", lambda a, b: a - b),
    "-": ("−", lambda a, b: a - b),
    "−": ("−", lambda a, b: a - b),
    "divided by": ("÷", lambda a, b: None if b == 0 else (a / b)),
    "/": ("÷", lambda a, b: None if b == 0 else (a / b)),
    "÷": ("÷", lambda a, b: None if b == 0 else (a / b)),
}

#: Word forms, longest first so "multiplied by" wins over a bare "by".
_WORD_OPS = ("multiplied by", "divided by", "times", "plus", "minus")
_SYMBOL_OPS = ("×", "÷", "−", "x", "*", "+", "-", "/")

#: What separates the operands from the result. ⛔ "is" and "makes" are here and
#: "gives"/"leaves" are not, because the second pair also introduces remainders
#: and partial states ("that leaves 1 to carry"), and a check that hard-refuses
#: may not guess at a sentence's aboutness.
_EQUALS = r"(?:=|equals|equal to|is equal to|is|are|makes|gives us)"

_NUM = r"(-?\d+(?:\.\d+)?)"

#: Word-form claims: "4 times 3 equals 12", "9 plus 3 is 12".
_WORD_CLAIM = re.compile(
    rf"{_NUM}\s*\b(" + "|".join(re.escape(w) for w in _WORD_OPS) + rf")\b\s*{_NUM}"
    rf"\s*\b{_EQUALS}\b\s*{_NUM}",
    re.I,
)

#: Symbol-form claims: "23 x 14 = 322". ⛔ The separator here is "=" ONLY.
#: "23 x 14 is the problem" is not a claim, and a symbol expression followed by
#: an English copula is far more often a description of the task than an
#: assertion of its answer.
_SYMBOL_CLAIM = re.compile(
    rf"{_NUM}\s*(" + "|".join(re.escape(s) for s in _SYMBOL_OPS) + rf")\s*{_NUM}\s*=\s*{_NUM}"
)


@dataclass(frozen=True)
class Claim:
    """One complete arithmetic statement, and whether it is true."""

    left: float
    op: str
    right: float
    stated: float
    computed: Optional[float]
    text: str

    @property
    def is_true(self) -> bool:
        if self.computed is None:          # division by zero: not decidable
            return True
        return abs(self.computed - self.stated) < 1e-9

    def as_dict(self) -> Dict[str, Any]:
        def _n(v: Optional[float]) -> Any:
            if v is None:
                return None
            return int(v) if float(v).is_integer() else v
        return {
            "text": self.text,
            "left": _n(self.left),
            "op": self.op,
            "right": _n(self.right),
            "stated": _n(self.stated),
            "computed": _n(self.computed),
            "is_true": self.is_true,
        }

    def __str__(self) -> str:
        def _n(v: Optional[float]) -> str:
            if v is None:
                return "undefined"
            return str(int(v)) if float(v).is_integer() else str(v)
        return (
            f"{self.text.strip()!r} — {_n(self.left)} {self.op} {_n(self.right)} "
            f"is {_n(self.computed)}, not {_n(self.stated)}"
        )


def _claim_from(match: "re.Match[str]") -> Optional[Claim]:
    left, op_token, right, stated = match.groups()
    entry = _OPS.get(op_token.strip().lower())
    if entry is None:
        return None
    symbol, fn = entry
    a, b, k = float(left), float(right), float(stated)
    try:
        computed = fn(a, b)
    except ZeroDivisionError:            # pragma: no cover - fn guards it
        computed = None
    return Claim(a, symbol, b, k, computed, match.group(0))


def parse_claims(text: Any) -> List[Claim]:
    """Every complete arithmetic claim in one piece of text, in order.

    ⚠ Overlaps are not deduplicated across the two forms because they cannot
    overlap: one requires an English operator word, the other requires a literal
    ``=``.
    """
    body = str(text or "")
    found: List[Claim] = []
    for pattern in (_WORD_CLAIM, _SYMBOL_CLAIM):
        for match in pattern.finditer(body):
            claim = _claim_from(match)
            if claim is not None:
                found.append(claim)
    return sorted(found, key=lambda c: body.find(c.text))


def false_claims(text: Any) -> List[Claim]:
    """The claims in this text that are arithmetically WRONG."""
    return [c for c in parse_claims(text) if not c.is_true]


#: Template parameters that are OPERANDS rather than positions or phases. The
#: lint reads a template's own declared numbers through this so that a claim
#: stated in the parameters is decided by the same code that decides one stated
#: in prose.
_OPERAND_KEYS = ("top", "bottom", "number", "multiplicand", "multiplier")


def template_operands(generation_params: Any) -> List[int]:
    """The integers an authored template declares, in a stable order.

    ⛳ WHAT THIS IS FOR, AND WHAT IT IS NOT FOR. It reports the numbers the
    renderer will DRAW so a refusal can quote them beside the words. It does not
    re-derive what the template PRODUCES: `motion_authoring.producible_numbers`
    already does that, phase by phase and carry by carry, and a second
    implementation here is exactly the "two builders for one payload" mistake
    WP-IVGS-09f records. A claim whose result the template cannot draw is that
    guard's refusal, not this one's.
    """
    if not isinstance(generation_params, dict):
        return []
    out: List[int] = []
    for key in _OPERAND_KEYS:
        value = generation_params.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            out.append(value)
        elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            out.append(int(value.strip()))
    return out


def lint_scene(
    narration: Any, generation_params: Any = None,
) -> List[Claim]:
    """Every FALSE arithmetic claim this scene makes, narration and template.

    The narration is the learner-facing text and is the whole of the hard limb.
    ``generation_params`` is read so a refusal can name the numbers the renderer
    would have drawn underneath the false sentence — evidence for the reviewer,
    not a second rule.
    """
    return false_claims(narration)


def lint_scenes(scenes: Sequence[Any]) -> List[Dict[str, Any]]:
    """Every false claim across a storyboard, keyed by scene index.

    Accepts ORM rows or dicts, like every other check at this gate.
    """
    def field(scene: Any, name: str, default: Any = None) -> Any:
        if isinstance(scene, dict):
            return scene.get(name, default)
        return getattr(scene, name, default)

    out: List[Dict[str, Any]] = []
    for position, scene in enumerate(scenes):
        index = field(scene, "scene_index", position)
        params = field(scene, "generation_params")
        for claim in lint_scene(field(scene, "narration_text"), params):
            out.append({
                "scene_index": int(index if isinstance(index, int) else position),
                "claim": claim.as_dict(),
                "message": str(claim),
                "template_operands": template_operands(params),
            })
    return out
