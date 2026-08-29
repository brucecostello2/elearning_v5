"""The evidence map, DERIVED — never asked of the model.

WP-IVGS-12d, on the operator's ruling closing RC-Q9c.

⛔ WHY THIS FUNCTION EXISTS AT ALL, AND WHY IT IS IN `shared`

12b's principle, applied one layer up: **never ask the model to assemble what
code can compute.** RC-Q9 was cured by refusing to ask the model to transcribe
outcome text. RC-Q9c is the same defect wearing the next hat — the model was
asked to assemble `evidence_map`, a list of scene indices it had *already
declared* through `serves_outcomes` and `instructional_event`, and it assembled
it wrongly in every generation of three:

  * gens 1 and 3 wrote five real `practice` scenes for LO-1 and then named
    `present` scenes as the evidence — the right answer was in its own output;
  * gen 2 named scenes as evidence while containing no `practice` or `assess`
    scene at all.

A map the model writes can disagree with the scenes. A map CODE derives from
the scenes cannot — the disagreement is not detected, it is made unrepresentable.
That is the whole move, and it deletes a hard refusal rather than adding one.

⛳ IT LIVES IN `shared` BECAUSE TWO TREES DERIVE IT AND THEY MUST NOT DISAGREE.
The worker derives it at capture from the model's raw scenes
(`design_core.contract.parse_contract`); the API derives it at the gate from the
stored scene ROWS (`app.services.design_review`). One function, imported twice,
so a brief's stored map and the gate's live computation cannot drift — which is
exactly the failure mode `PROMPT_TYPES` and `MEDIA_TYPES` were consolidated to
remove (RC-Q11: a warning is not a mechanism).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from shared.models.enums import ASSESSING_EVENTS


def _field(scene: Any, name: str, default: Any = None) -> Any:
    """Read a field off a dict OR an ORM row, because both callers exist."""
    if isinstance(scene, dict):
        return scene.get(name, default)
    return getattr(scene, name, default)


def scene_index_of(scene: Any, fallback: int = 0) -> int:
    raw = _field(scene, "scene_index", fallback)
    try:
        return int(raw if raw is not None else fallback)
    except (TypeError, ValueError):
        return fallback


def serves(scene: Any) -> List[str]:
    return [str(x) for x in (_field(scene, "serves_outcomes") or [])]


def derive_evidence_map(
    scenes: Sequence[Any],
    outcome_ids: Optional[Iterable[str]] = None,
) -> Dict[str, List[int]]:
    """``{outcome_id: [scene_index, ...]}`` — the ASSESSING scenes, from the
    scenes' own declarations and from nothing else.

    A scene is evidence for an outcome when it declares that outcome in
    ``serves_outcomes`` AND its ``instructional_event`` is one of
    ``ASSESSING_EVENTS``. Both are closed enums the designer wrote itself, so
    this is a read of the design, not an opinion about it.

    ``outcome_ids`` fixes the key set: every id gets an entry, and an outcome no
    scene assesses gets ``[]`` — **which is the honest answer and is exactly
    what the gate refuses on.** An empty list here is not a gap in the data; it
    is the finding. Without the id list the keys are whatever the scenes
    mention, which is right for a caller that has no outcome list to hand.

    Indices are sorted and de-duplicated: two scene rows at the same index (the
    RC-Q10 surplus-row shape) must not make one outcome look twice-assessed.
    """
    ids = [str(o) for o in outcome_ids] if outcome_ids is not None else None
    found: Dict[str, set] = {oid: set() for oid in (ids or [])}
    for position, scene in enumerate(scenes):
        if _field(scene, "instructional_event") not in ASSESSING_EVENTS:
            continue
        index = scene_index_of(scene, position)
        for oid in serves(scene):
            if ids is not None and oid not in found:
                # A scene citing an id the operator never wrote. The gate
                # refuses that by name (SCENE_CITES_UNKNOWN_OUTCOME); it must
                # not silently become a key here and imply the outcome exists.
                continue
            found.setdefault(oid, set()).add(index)
    return {oid: sorted(v) for oid, v in found.items()}


def realizes(scene: Any, outcome_id: str, evidence_kind: str) -> bool:
    """Does this ONE scene deliver what the plan promised for this outcome?

    The plan's ``evidence_kind`` is matched EXACTLY, not merely as a member of
    ``ASSESSING_EVENTS``: a plan that promised the learner would be assessed
    unaided is not realized by a guided practice item. The model chose the kind
    from a two-value enum; holding it to the one it chose is not strictness for
    its own sake, it is the only thing that makes the promise mean anything.
    """
    return (
        outcome_id in serves(scene)
        and _field(scene, "instructional_event") == evidence_kind
    )
