"""The check the grammar cannot make: is the assessment the practice, again?

WP-IVGS-12h, TASK 2. ⛔ THIS EXISTS BECAUSE RC-Q9g IS NOT A GRAMMAR PROBLEM AND
NEVER COULD BE.

Under design-contract-6 both scenes are legally declared, both serve the outcome,
one is `practice` and one is `assess`, and `OUTCOME_ASSESSED_TWICE` correctly does
not fire because there is exactly one assessment. The defect is that the two
scenes say THE SAME THING:

    LO-2 practice : "Explain why we write a placeholder zero in the ones column
                     before multiplying by the tens digit."
    LO-2 assess   : "Explain why we write a placeholder zero in the ones column
                     before multiplying by the tens digit."

Verbatim identical, in 9 of 15 outcome-pairs across five completed generations,
with 2 more differing only by a *"Let's practice"* prefix. A JSON Schema cannot
see it: two different strings are two different strings.

⛳ SO IT IS MEASURED, IN CODE, DETERMINISTICALLY, AND THE THRESHOLD IS ARGUED
FROM BANKED BYTES RATHER THAN CHOSEN. See `THE CALIBRATION SET` below.

WHAT IS COMPARED, AND WHY IT IS ANCHORED ON THE ASSESSMENT

For each outcome: its ONE assessment narration against

  * each of its 1..2 practice narrations — the RC-Q9g defect proper; and
  * each `present`/`guide` scene serving the same outcome — the WORKED EXAMPLES.
    ⛳ This limb is not decoration. It caught a defect five generations of
    hand-comparison missed: WP-IVGS-12g called script B2's LO-1 *"real
    scaffolding, correctly faded"* on the strength of practice *"Divide 234 by
    10. Use the place-value shift method."* against assess *"Divide 432 by 10."*
    — and the same design's scene 17 is a `guide` reading *"Divide 432 by 10."*,
    byte-identical to the assessment. The lesson worked the problem on screen and
    then set it as the unaided attempt.

⚠ The PRACTICE is not itself compared against the worked examples. The order
scopes this belt to the assessment, and 12g's run A gen 2 quoted a practice that
IS the script's own worked example (*"Solve the problem: 23 times 14."*) — that
case is named in the report as a residue, not silently swept in here.

THE MEASURE

`containment(A, X) = |tokens(A) ∩ tokens(X)| / |tokens(A)|` — how much of the
ASSESSMENT is already present in the other scene. Containment and not Jaccard,
because the degenerate assessment is typically the SHORTER string: gen 3's
practice *"Let's practice checking our work by verifying the column alignment…"*
wholly contains its assessment *"Check your work by verifying the column
alignment…"*, and a symmetric measure dilutes exactly the case that matters.

Tokens are lower-cased alphanumeric runs with a small GENERIC English stoplist
removed. ⛔ THE STOPLIST IS ARTICLES, PRONOUNS, COPULAS AND PREPOSITIONS AND
NOTHING ELSE — no task words, no words drawn from the measured corpus. Tuning a
stoplist against the calibration set would be fitting the belt to the very data
that is supposed to test it. Measured, both ways: with the stoplist the two
classes separate 0.667 | 0.900; without it, 0.750 | 0.857. The stoplist more
than doubles the margin and it is kept for that reason.

⛔ NUMERALS ARE **KEPT** IN THE TOKEN SET. Dropping them was measured and it
DESTROYS the belt: B2's two correctly-differentiated computational pairs both go
to containment 1.00 the moment the numbers are removed, because a faded and an
unaided attempt at the same procedure differ in nothing else. The number IS the
axis — which is 12g's own finding, stated there in words and confirmed here on
the bytes.

TWO LIMBS, AND THE SECOND IS 12g's FINDING MADE MECHANICAL

  limb A  containment >= NEAR_DUPLICATE_CONTAINMENT
          The assessment restates the other scene, whatever the numbers.

  limb B  the numeral multisets are EQUAL and containment >= NO_FRESH_AXIS
          There is no fresh number to distinguish the two attempts, and most of
          the assessment is the other scene's words. 12g measured the mechanism
          exactly: *"where a FRESH NUMBER exists as an axis, the model
          differentiates; where the outcome is 'explain why' or 'check your
          work', it has no axis and writes the same sentence twice."*

⚠ LIMB B IS NOT "NUMERALS ALONE", AND THE DIFFERENCE IS THE WHOLE DESIGN. On the
bank, numeral equality alone is a PERFECT classifier — 13 of 13 equal-numeral
pairs are duplicates and 5 of 5 fresh-numeral pairs are sound. Shipping that
would refuse every "explain why" outcome forever, because neither narration has a
number in it and their numeral sets are trivially equal. The containment floor is
what keeps a genuinely re-worded explain-why assessment legal.

THE CALIBRATION SET, AND IT IS BANKED

`dev/workpackages/reference/wpivgs12g-evidence/*-contracts.json` — 18 outcome
pairs over two scripts, five generations of the operator's ABCD outcomes plus one
of script B2. Re-measured by
`dev/workpackages/reference/wpivgs12h-evidence/calibrate12h.py`, which is part of
the WP-IVGS-12h acceptance and fails if any row moves class.

    MUST REFUSE, practice limb (12)   containment 0.900 .. 1.000
        9 verbatim-identical pairs, 2 "Let's practice"-prefixed pairs, and B2's
        collapsed non-computational LO-3.
    MUST PASS, practice limb (6)      containment 0.100 .. 0.667
        B2's two computational pairs and the operator's four LO-1 pairs.

⛔ MARGIN 0.667 -> 0.900, AND THE THRESHOLD IS PUT IN THE MIDDLE OF IT AT 0.80.
Not at either edge: a threshold sitting on an observed value is a threshold that
reclassifies the first time a synonym moves one token.

⚠ AND ONE ROW THAT 12g DID NOT QUOTE AS A DUPLICATE IS ONE ANYWAY, by limb B.
Run B gen 1's LO-1 practice *"Multiply 43 by 25 using the standard column
algorithm. You can use the workspace below to help you."* against its assessment
*"Now it's your turn to try. Multiply 43 by 25 using the standard column
algorithm."* — containment 0.64, and THE SAME TWO NUMBERS. It is the same problem
posed twice with the support sentence removed, which is the defect wearing its
politest form. It is reported as a twelfth duplicate rather than tuned around.

⛳ IT LIVES IN `shared` FOR `evidence.py` AND `merge.py`'s REASON. The API's gate,
the worker and the acceptance harness all ask this question and they must not
answer it three ways.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

#: ⛔ GENERIC ENGLISH FUNCTION WORDS ONLY. Articles, pronouns, copulas,
#: prepositions, conjunctions. No verb a lesson would use, no noun a subject
#: would use, and nothing chosen by looking at what the model wrote. Adding a
#: task word here — "practice", "explain", "problem" — would be fitting the
#: measure to its own test set and is the one change this module forbids.
STOPWORDS: frozenset = frozenset("""
a an the and or but if then so of to in on at by for with from into onto over
under is are was were be been being do does did doing have has had having
it its this that these those you your yours we our us they them their
he she his her i me my as not no
""".split())

#: limb A. Measured margin on the banked calibration set: the refuse class floors
#: at 0.900 and the pass class ceilings at 0.667. 0.80 is the midpoint.
NEAR_DUPLICATE_CONTAINMENT = 0.80

#: limb B, applied ONLY when the two narrations use the same numbers. Every
#: equal-numeral pair in the bank is a duplicate (13 of 13) and the lowest sits
#: at 0.64, so this floor is below every measured duplicate and there is no
#: measured counter-example above it. ⚠ Stated as the WIDER claim of the two:
#: limb A is calibrated between two observed classes, limb B is calibrated
#: against one class and the absence of the other.
NO_FRESH_AXIS_CONTAINMENT = 0.60

_WORD = re.compile(r"[a-z0-9]+")
_NUMERAL = re.compile(r"\d+(?:\.\d+)?")


def normalized_tokens(text: Any) -> Set[str]:
    """Lower-cased alphanumeric tokens, generic function words removed."""
    return {w for w in _WORD.findall(str(text or "").lower()) if w not in STOPWORDS}


def numerals(text: Any) -> List[str]:
    """Every number in the narration, sorted — the multiset, as a list.

    Sorted rather than set-ed: *"Multiply 43 by 43"* and *"Multiply 43 by 27"*
    must not compare equal through the accident of a repeated digit run.
    """
    return sorted(_NUMERAL.findall(str(text or "")))


def containment(assessment: Any, other: Any) -> float:
    """How much of ``assessment`` is already present in ``other``. 0.0 .. 1.0.

    An empty assessment returns 1.0 — it contains nothing the other scene does
    not, which is the honest answer and also unreachable, since the contract
    pins ``minLength: 1`` on every narration.
    """
    a = normalized_tokens(assessment)
    if not a:
        return 1.0
    return len(a & normalized_tokens(other)) / len(a)


def duplication_verdict(assessment: Any, other: Any) -> Dict[str, Any]:
    """The whole measurement for ONE pair, with the reason it came out that way.

    Returns the numbers as well as the verdict so a refusal can show its work at
    the gate and a test can assert the value rather than the outcome — a belt
    whose threshold cannot be seen is a belt nobody can re-argue.
    """
    score = containment(assessment, other)
    same_numbers = numerals(assessment) == numerals(other)
    if score >= NEAR_DUPLICATE_CONTAINMENT:
        limb = "restates"
    elif same_numbers and score >= NO_FRESH_AXIS_CONTAINMENT:
        limb = "no_fresh_axis"
    else:
        limb = None
    return {
        "containment": round(score, 4),
        "numerals_equal": same_numbers,
        "assessment_numerals": numerals(assessment),
        "other_numerals": numerals(other),
        "limb": limb,
        "duplicate": limb is not None,
    }


def is_near_duplicate(assessment: Any, other: Any) -> bool:
    return bool(duplication_verdict(assessment, other)["duplicate"])


def explain(limb: Optional[str]) -> str:
    """One sentence a reviewer can act on, keyed by which limb fired."""
    if limb == "restates":
        return (
            "the assessment restates that scene almost word for word, so the "
            "learner is asked the same question twice under two labels"
        )
    if limb == "no_fresh_axis":
        return (
            "the assessment uses the SAME NUMBERS as that scene and most of its "
            "wording, so nothing distinguishes the unaided attempt from the "
            "supported one it was meant to fade from"
        )
    return "not a duplicate"
