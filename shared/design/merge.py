"""The designed assessments, PLACED — never positioned by the model.

WP-IVGS-12f. The 12b principle a third time: never ask the model to supply what
code can compute. 12b took the outcome TEXT away from it; 12d took the
`evidence_map` away from it; this takes the POSITION away from it.

⛔ WHY A SEPARATE TOP-LEVEL OBJECT AND NOT A SCENE IN `scenes`

Contract-4 invited invention and was declined 83 times out of 83 (RC-Q9e): the
prompt has said "material the outcomes require that the script lacks is
legitimate: you invent it, mark the scene `origin: designed`" since v8, and the
model segmented the script instead, every time.

⛳ AND THE 12f MEASUREMENT SHOWED WHY, WHICH CHANGED THE FIX. A sparse script
with no practice material in it (B2) produced FIVE designed scenes and the first
`assess` event this project has ever recorded. The model is not incapable of
invention — it is out-competed by it. Given anything it can anchor to, it
anchors. Contract-4 offered `scenes[]` as one array where sourced and designed
material compete for the same slots, and sourced always won.

So contract-5 stops asking. `designed_assessments` is a REQUIRED per-outcome
object whose values are scenes the grammar has already pinned to
`origin: designed`, `instructional_event: assess` and `serves_outcomes: [that
outcome]`. There is no slot for a sourced scene to win, because there is no
competition: an emission without one invented unaided scene per outcome is not
parseable. The excerpter cannot decline.

⛔ AND THE MODEL IS NEVER ASKED WHERE THEY GO

A designed assessment carries no `scene_index`; the key is absent from its
schema. This module derives the position: **each designed assessment is inserted
immediately after the LAST scene serving its outcome** — the end of that
outcome's fading sequence, which is where Foundation §2 puts the independent
attempt. An outcome no scene serves has no anchor and its assessment goes at the
end, where `PRACTICE_NOT_PREPARED` will flag it for exactly what it is: an
unaided attempt at something the lesson never taught.

⛳ IT LIVES IN `shared` FOR `evidence.py`'s REASON, WHICH IS THE 12d LESSON.
Two trees compute this sequence and they must not disagree: the worker's
`parse_contract` builds the payload the API stores, and the worker's response
transform hands the SAME sequence to the frozen stage body so the scene rows in
the table are the merged ones. One function, imported twice, deterministic and
pure — so a brief's `scene_designs` and the `storyboard_scenes` rows cannot
drift apart.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

#: Every key contract-5 pins for a designed assessment. Named here so the
#: contract, the merge and the tests all read one list.
PINNED_EVENT = "assess"
PINNED_ORIGIN = "designed"


def _serves(scene: Any) -> List[str]:
    if not isinstance(scene, dict):
        return []
    return [str(x) for x in (scene.get("serves_outcomes") or [])]


def anchor_positions(
    scenes: Sequence[Any], outcome_ids: Sequence[str],
) -> Dict[str, int]:
    """``{outcome_id: position}`` — the LAST scene in the emitted order that
    serves each outcome, as an index into ``scenes``.

    ``-1`` for an outcome no scene serves: there is no fading sequence to sit at
    the end of, so the assessment goes to the end of the design instead. That is
    a real defect in the lesson and it is not this function's job to hide it —
    ``PRACTICE_NOT_PREPARED`` names it at the gate.
    """
    positions: Dict[str, int] = {str(oid): -1 for oid in outcome_ids}
    for i, scene in enumerate(scenes):
        for oid in _serves(scene):
            if oid in positions:
                positions[oid] = i
    return positions


def merged_scene_sequence(raw_contract: Any) -> List[Dict[str, Any]]:
    """The sequence stage 3+ and the derived evidence map consume.

    The model's own ``scenes`` array is NOT edited: every emitted scene keeps its
    content and its relative order. Each designed assessment is inserted after
    the last scene serving its outcome, and the whole sequence is then indexed
    0..n-1 so ``scene_index`` means position in the merged design — which is what
    every consumer downstream already assumes it means.

    ⚠ RE-INDEXING IS NOT OPTIONAL AND IT IS WHY THIS RETURNS COPIES. An inserted
    scene shifts every later scene's position by one; leaving the model's
    original indices in place would make `evidence_map` name scenes that are no
    longer where it says. The dicts are copied rather than mutated so the
    caller's `raw_contract` stays the verbatim evidence limb it is stored as.

    A contract with no ``designed_assessments`` (anything pre-contract-5) comes
    back as its own ``scenes`` list, re-indexed — the identity case, so a caller
    can use this unconditionally.
    """
    if not isinstance(raw_contract, dict):
        return []
    scenes = [s for s in (raw_contract.get("scenes") or []) if isinstance(s, dict)]
    designed = raw_contract.get("designed_assessments")
    designed = designed if isinstance(designed, dict) else {}

    # ⛔ THE KEY ORDER IS THE OUTCOME ORDER AND IT IS THE TIE-BREAK. Two outcomes
    # whose last serving scene is the same scene both insert after it, and they
    # must do so in an order that does not depend on dict iteration luck. The
    # schema builds `designed_assessments` from the operator's id list in order,
    # and JSON preserves it, so this is the operator's own ordering.
    ids = [str(k) for k in designed.keys()]
    anchors = anchor_positions(scenes, ids)

    after: Dict[int, List[Dict[str, Any]]] = {}
    tail: List[Dict[str, Any]] = []
    for oid in ids:
        scene = designed.get(oid)
        if not isinstance(scene, dict):
            continue
        placed = dict(scene)
        position = anchors.get(oid, -1)
        if position < 0:
            tail.append(placed)
        else:
            after.setdefault(position, []).append(placed)

    merged: List[Dict[str, Any]] = []
    for i, scene in enumerate(scenes):
        merged.append(dict(scene))
        merged.extend(after.get(i, []))
    merged.extend(tail)

    for index, scene in enumerate(merged):
        scene["scene_index"] = index
    return merged
