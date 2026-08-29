"""Parse the operator's learning outcomes IN CODE, and prove it reversible.

WP-IVGS-12b Task 1(a). ⛔ THIS EXISTS BECAUSE ASKING A MODEL TO TRANSCRIBE
SOMETHING THE DATABASE ALREADY HOLDS IS A DEFECT, NOT A PROMPT PROBLEM.

MEASURED, WP-IVGS-12 acceptance, three consecutive generations on three genuine
ABCD outcomes: **all three emitted TWO outcomes, not three, and reworded both
they kept.**

    operator: "Given two 2-digit numbers written in column form, the learner
               will compute their product using the standard column algorithm,
               producing both partial products with correct carries and a
               correct final sum."
    model   : "The learner can multiply two double-digit numbers."
              measurable: true    proposed_refinement: null

LO-3 vanished and was not declared dropped. No prompt wording fixed it, and no
JSON Schema can: **a paraphrase is a valid string.** So the model stops being
asked. Code parses `projects.learning_outcomes`, assigns stable ids, and the
outcome TEXT is injected server-side; the model may only REFERENCE the ids
(closed by a per-request enum, measured enforced) and PROPOSE a refinement
against one.

REVERSIBILITY IS THE CONTRACT. ``reconstruct(parse(text)) == text.strip()`` for
every input, and `test_wpivgs12b_outcomes.py` proves it over a corpus including
wrapped lines, blank lines, mixed markers and no markers at all. Without that
the "byte-compare belt" of Task 1(d) would be comparing against a normalisation
rather than against what the operator typed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

#: Line shapes that OPEN a new outcome. Anything else continues the previous
#: one, which is how a wrapped outcome survives intact.
#:
#: ⚠ Deliberately NOT greedy about prose. A line beginning "Given two 2-digit
#: numbers…" opens an outcome only because it is the FIRST line; a line
#: beginning "producing both partial products…" continues one. The markers are
#: the signal, and their absence means continuation.
_MARKER = re.compile(
    r"""^\s*(?:
          (?P<lo>LO[\s._-]*\d+)            # LO-1, LO 2, LO_3, lo1
        | (?P<num>\d+)                     # 1.  2)  3:
        | (?P<bullet>[-*•–])     # -  *  •  –
        )\s*[:.)\]]?\s+""",
    re.IGNORECASE | re.VERBOSE,
)


def parse_outcomes(raw: Any) -> List[Dict[str, Any]]:
    """``projects.learning_outcomes`` -> ``[{id, text, source, marker}]``.

    ``id``      stable, positional: LO-1 … LO-n. It is what the model cites and
                what the schema's enum is built from, so it must not depend on
                anything the operator wrote — an operator who numbers their
                outcomes 2, 5 and 9 still gets LO-1, LO-2, LO-3.
    ``text``    the outcome as the operator wrote it, marker stripped, wrapped
                lines rejoined with a single space.
    ``source``  the EXACT source lines, joined by newline. ``reconstruct`` uses
                this and nothing else.
    """
    if not raw or not str(raw).strip():
        return []
    lines = str(raw).strip().splitlines()

    # ⛔ THE CONTINUATION RULE NEEDS A GUARD, AND IT WAS EARNED BY A TEST CASE.
    # "a line with no marker continues the previous outcome" is right when the
    # operator marks their outcomes and wraps a long one. It is WRONG when they
    # mark nothing and put one outcome per line — three outcomes collapse into
    # one, which is the same silent-loss shape this module exists to remove.
    #
    # So: if NOTHING in the text carries a marker, every non-empty line is its
    # own outcome. If ANYTHING does, the marker/continuation rule applies and a
    # wrapped outcome survives intact.
    any_marker = any(_MARKER.match(line) for line in lines)

    blocks: List[List[str]] = []
    markers: List[str] = []
    for line in lines:
        match = _MARKER.match(line)
        opens = bool(match) or not blocks or (not any_marker and line.strip())
        if opens:
            blocks.append([line])
            markers.append(match.group(0) if match else "")
        else:
            blocks[-1].append(line)

    outcomes: List[Dict[str, Any]] = []
    for index, (lines, marker) in enumerate(zip(blocks, markers), start=1):
        source = "\n".join(lines)
        body = source[len(marker):] if marker else source
        text = " ".join(part.strip() for part in body.splitlines() if part.strip())
        if not text:
            # A block that is only a marker or only blank lines is not an
            # outcome. It stays in `source` so reconstruction is still exact,
            # attached to the previous block.
            if outcomes:
                outcomes[-1]["source"] += "\n" + source
                continue
        outcomes.append({
            "id": f"LO-{index}",
            "text": text,
            "source": source,
            "marker": marker,
        })
    # Re-number after any empty block was folded away, so ids stay contiguous.
    for position, outcome in enumerate(outcomes, start=1):
        outcome["id"] = f"LO-{position}"
    return outcomes


def reconstruct(outcomes: List[Dict[str, Any]]) -> str:
    """The inverse of :func:`parse_outcomes`, for the Task 1(d) byte-compare."""
    return "\n".join(o.get("source", "") for o in outcomes)


def outcome_ids(outcomes: List[Dict[str, Any]]) -> List[str]:
    return [str(o["id"]) for o in outcomes]


def is_faithful(raw: Any, outcomes: List[Dict[str, Any]]) -> bool:
    """Does this outcome list still say exactly what the operator typed?"""
    return reconstruct(outcomes) == (str(raw or "").strip())
