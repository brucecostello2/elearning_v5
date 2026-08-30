"""The evidence scenes, PLACED — never positioned by the model.

WP-IVGS-12f, extended by WP-IVGS-12g. The 12b principle a third and fourth time:
never ask the model to supply what code can compute. 12b took the outcome TEXT
away from it; 12d took the `evidence_map` away from it; 12f took the POSITION of
the assessment away from it; 12g takes the position of the practice too, and
with it the ORDER the two sit in.

⛔ WHY THE EVIDENCE LIVES OUTSIDE `scenes[]` AT ALL

Contract-4 invited invention and was declined 83 times out of 83 (RC-Q9e): the
prompt has said "material the outcomes require that the script lacks is
legitimate: you invent it, mark the scene `origin: designed`" since v8, and the
model segmented the script instead, every time.

⛳ AND THE 12f MEASUREMENT SHOWED WHY, WHICH CHANGED THE FIX. A sparse script
with no practice material in it (B2) produced FIVE designed scenes and the first
`assess` event this project has ever recorded. The model is not incapable of
invention — it is out-competed by it. Given anything it can anchor to, it
anchors. `scenes[]` was one array where sourced and designed material compete
for the same slots, and sourced always won.

⛔ AND 12f's HALF-MEASURE MEASURED ITS OWN BOUNDARY, TWICE

Contract-5 removed the competition for `assess` only, and RC-Q9f is what the
remaining half did:

  * **limb 1** — the plan promised `practice` for LO-2 in all six generations
    and no practice scene was ever built. Six `PLAN_ENTRY_UNREALIZED` refusals
    out of six, the same outcome every time. RC-Q9d's non-causal plan, surviving
    intact in the one evidence kind the grammar had left unforced.
  * **limb 2** — with `assess` forced elsewhere, the model started writing EXTRA
    `assess` scenes into `scenes[]` (four of six generations, the first
    `designed` scenes ever emitted into that array on the operator's script),
    and this module dutifully placed the mandated one immediately after its
    near-identical twin. *"Now it's your turn to try. Multiply 43 by 27 using
    the standard column algorithm."* twice, adjacent.

So contract-6 stops asking for both kinds. `practice_scenes` and
`assessment_scenes` are REQUIRED per-outcome sections, and `scenes[]`'s
`instructional_event` enum no longer contains `practice` or `assess` at all.
There is no slot for a sourced scene to out-compete an authored one, no unforced
kind for an unkept promise to hide in, and nowhere for a duplicate to be written.
⛳ **Origin stays free in both sections** — B1 showed the model finding a real
"now you try" span and anchoring to it, which is legitimate evidence; the
grammar guarantees the scene EXISTS and the model still says where it came from.

⛔ AND THE MODEL IS NEVER ASKED WHERE THEY GO

No evidence scene carries a `scene_index`; the key is absent from its schema.
This module derives the position, and the rule is Foundation §2's fading order
rather than 12f's simpler one:

    practice     after the LAST scene that PRESENTS or GUIDES its outcome —
                 the end of the teaching, which is where the supported attempt
                 belongs. Falling back to the last scene serving the outcome at
                 all when the design never presents or guides it.
    assessment   after that outcome's practice, always. Same insertion point,
                 emitted second, so the block reads
                 present/guide … → practice → assess.

An outcome no scene serves has no anchor and its evidence goes at the end, where
`PRACTICE_NOT_PREPARED` will flag it for exactly what it is: an attempt at
something the lesson never taught.

⚠ CONTRACT-5 EMISSIONS KEEP CONTRACT-5's RULE, and that is deliberate. A brief
stored under `designed_assessments` had no practice to sit after, so its
assessment still anchors to the last scene serving its outcome. Re-deriving old
briefs under the new rule would silently move scenes in records the gate has
already been reviewed against.

⛳ IT LIVES IN `shared` FOR `evidence.py`'s REASON, WHICH IS THE 12d LESSON.
Two trees compute this sequence and they must not disagree: the worker's
`parse_contract` builds the payload the API stores, and the worker's response
transform hands the SAME sequence to the frozen stage body so the scene rows in
the table are the merged ones. One function, imported twice, deterministic and
pure — so a brief's `scene_designs` and the `storyboard_scenes` rows cannot
drift apart.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

#: Every key the contracts pin for an authored evidence scene. Named here so the
#: contract, the merge and the tests all read one list.
PINNED_EVENT = "assess"
PINNED_ORIGIN = "designed"

#: ⛔ WP-IVGS-12g. THE EVENTS THAT PREPARE AN ATTEMPT. Foundation §4: every
#: practice scene is preceded by a `present` or `guide` on the same outcome —
#: the worked → faded → independent sequence — and `PRACTICE_NOT_PREPARED`
#: names a design that does otherwise. Anchoring the practice to the LAST of
#: these is what makes the flag structurally quiet for a sound design instead of
#: firing on placement this module chose.
#:
#: ⚠ NOT `feedback` and not `hook`/`objective`/`recall_prior`. Feedback follows
#: an attempt rather than preparing one, and anchoring a practice after it would
#: put the supported attempt after its own correction.
PREPARING_EVENTS: Tuple[str, ...] = ("present", "guide")

#: The contract-6 sections, in the order they are inserted at a shared anchor.
#: ⛔ THE ORDER OF THIS TUPLE IS THE FADING SEQUENCE AND IS NOT STYLE. Practice
#: before assessment, so the supported attempt precedes the independent one.
#: Reversing it would put the unaided attempt before its own rehearsal, which is
#: the one ordering error Foundation §2 names.
EVIDENCE_SECTIONS: Tuple[str, ...] = ("practice_scenes", "assessment_scenes")

#: Contract-5's single section, still merged so stored briefs keep meaning.
LEGACY_SECTION = "designed_assessments"


def _serves(scene: Any) -> List[str]:
    if not isinstance(scene, dict):
        return []
    return [str(x) for x in (scene.get("serves_outcomes") or [])]


def anchor_positions(
    scenes: Sequence[Any],
    outcome_ids: Sequence[str],
    *,
    prefer_events: Sequence[str] = (),
) -> Dict[str, int]:
    """``{outcome_id: position}`` — where each outcome's evidence is inserted.

    Without ``prefer_events`` this is contract-5's rule and is unchanged: the
    LAST scene in the emitted order that serves each outcome.

    With ``prefer_events`` (contract-6 passes ``PREPARING_EVENTS``) it is the
    last scene serving the outcome whose ``instructional_event`` is one of them
    — the end of that outcome's TEACHING — and it falls back to the last scene
    serving the outcome at all when the design never presents or guides it.

    ``-1`` for an outcome no scene serves: there is no fading sequence to sit at
    the end of, so the evidence goes to the end of the design instead. That is a
    real defect in the lesson and it is not this function's job to hide it —
    ``PRACTICE_NOT_PREPARED`` names it at the gate.
    """
    preferred = {str(e) for e in prefer_events}
    best: Dict[str, int] = {str(oid): -1 for oid in outcome_ids}
    fallback: Dict[str, int] = {str(oid): -1 for oid in outcome_ids}
    for i, scene in enumerate(scenes):
        event = scene.get("instructional_event") if isinstance(scene, dict) else None
        for oid in _serves(scene):
            if oid not in fallback:
                continue
            fallback[oid] = i
            if preferred and event in preferred:
                best[oid] = i
    if not preferred:
        return fallback
    return {oid: (best[oid] if best[oid] >= 0 else fallback[oid]) for oid in best}


def _sections_of(raw_contract: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """The evidence sections present in this emission, in insertion order.

    Contract-6 first; contract-5's `designed_assessments` only when neither
    contract-6 section is present, so an emission carrying both — which nothing
    produces, but a hand-written fixture might — is read as the newer shape
    rather than merged twice.
    """
    found = [
        (name, raw_contract[name])
        for name in EVIDENCE_SECTIONS
        if isinstance(raw_contract.get(name), dict) and raw_contract[name]
    ]
    if found:
        return found
    legacy = raw_contract.get(LEGACY_SECTION)
    if isinstance(legacy, dict) and legacy:
        return [(LEGACY_SECTION, legacy)]
    return []


def _scenes_in(entry: Any) -> List[Dict[str, Any]]:
    """One evidence entry's scenes.

    Contract-6 holds an ARRAY per outcome (bounded 1..2 for practice, exactly 1
    for assessment). Contract-5 held a single scene OBJECT. Both are accepted so
    a stored brief and a fresh emission travel the same path.
    """
    if isinstance(entry, dict):
        return [entry]
    if isinstance(entry, list):
        return [s for s in entry if isinstance(s, dict)]
    return []


def merged_scene_sequence(raw_contract: Any) -> List[Dict[str, Any]]:
    """The sequence stage 3+ and the derived evidence map consume.

    The model's own ``scenes`` array is NOT edited: every emitted scene keeps its
    content and its relative order. Each evidence scene is inserted at its
    outcome's anchor — practice first, then the assessment — and the whole
    sequence is then indexed 0..n-1 so ``scene_index`` means position in the
    merged design, which is what every consumer downstream already assumes it
    means.

    ⚠ RE-INDEXING IS NOT OPTIONAL AND IT IS WHY THIS RETURNS COPIES. An inserted
    scene shifts every later scene's position by one; leaving the model's
    original indices in place would make `evidence_map` name scenes that are no
    longer where it says. The dicts are copied rather than mutated so the
    caller's `raw_contract` stays the verbatim evidence limb it is stored as.

    A contract with no evidence section — anything pre-contract-5 — comes back as
    its own ``scenes`` list, re-indexed: the identity case, so a caller can use
    this unconditionally.
    """
    if not isinstance(raw_contract, dict):
        return []
    scenes = [s for s in (raw_contract.get("scenes") or []) if isinstance(s, dict)]
    sections = _sections_of(raw_contract)
    if not sections:
        merged = [dict(s) for s in scenes]
        for index, scene in enumerate(merged):
            scene["scene_index"] = index
        return merged

    # ⛔ THE KEY ORDER IS THE OUTCOME ORDER AND IT IS THE TIE-BREAK. Two outcomes
    # whose anchor is the same scene both insert after it, and they must do so in
    # an order that does not depend on dict iteration luck. The schema builds
    # each section from the operator's id list in order, and JSON preserves it,
    # so this is the operator's own ordering.
    ids: List[str] = []
    for _name, section in sections:
        for key in section.keys():
            if str(key) not in ids:
                ids.append(str(key))

    # Contract-6 anchors to the end of the TEACHING; contract-5 to the last scene
    # serving the outcome. See the module docstring on why old briefs keep the
    # old rule.
    is_legacy = sections[0][0] == LEGACY_SECTION
    anchors = anchor_positions(
        scenes, ids, prefer_events=() if is_legacy else PREPARING_EVENTS,
    )

    after: Dict[int, List[Dict[str, Any]]] = {}
    tail: List[Dict[str, Any]] = []
    # ⛔ OUTCOME-MAJOR, THEN SECTION ORDER. Every scene for one outcome is
    # contiguous — its practice then its assessment — rather than every
    # practice in the lesson then every assessment. The alternative would
    # scatter one outcome's fading sequence around another outcome's.
    for oid in ids:
        position = anchors.get(oid, -1)
        bucket = tail if position < 0 else after.setdefault(position, [])
        for _name, section in sections:
            for scene in _scenes_in(section.get(oid)):
                bucket.append(dict(scene))

    merged: List[Dict[str, Any]] = []
    for i, scene in enumerate(scenes):
        merged.append(dict(scene))
        merged.extend(after.get(i, []))
    merged.extend(tail)

    for index, scene in enumerate(merged):
        scene["scene_index"] = index
    return merged
