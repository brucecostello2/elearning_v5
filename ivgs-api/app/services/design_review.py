"""The storyboard gate becomes a design review.

WP-IVGS-12 Task 5. Instructional Design Foundation §6-§7, recovery plan §1
RC-A step 3.

⛔ THE TWO LIMBS, AND WHY THE LINE IS WHERE IT IS

WP-IVGS-10 established the discipline at this gate and it is kept exactly:
**hard-refuse only what is objectively checkable; soft-flag every judgment.**
One assessment feeds both surfaces, there are no prompt loops, and a refusal
names the scene.

An outcome that NO scene declares is objectively unserved — the declaration is
a list of ids and the list is empty. That is a refusal. Whether the scene that
declares it serves it WELL is a judgment, and this module does not have an
opinion about it. The distinction is the whole reason the gate stayed usable
through WP-IVGS-10's five hard refusals: a reviewer can act on "scene 7 declares
no outcome" and can only argue with "scene 7 feels thin".

⚠ WHAT IS DELIBERATELY A FLAG THOUGH IT LOOKS CHECKABLE

Beat coverage. Every character of the uploaded script should be inside some
scene's ``source_refs`` or inside a declared ``dropped_beats`` span, and the
arithmetic of that is objective. But a BEAT boundary is a judgment, and the
spans are counted by the model: an off-by-twenty on one offset would hard-refuse
a design that is completely sound. So an uncovered stretch is FLAGGED, with the
uncovered text quoted so the reviewer can see in one glance whether a worked
example just went missing. That is the check the recovery plan §3 item 4 says
nobody ever performed — "no check anywhere compares output narration to input
script" — and it performs it, at the strength the evidence supports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from shared.models.enums import (
    APPLICATION_EVENTS,
    ASSESSING_EVENTS,
    DEMONSTRATION_EVENTS,
    INSTRUCTIONAL_EVENTS,
)

REFUSE = "refuse"
FLAG = "flag"

#: Foundation §4, segmenting: "narration for a `present`/`guide` scene ≤ ~2
#: sentences per visual change". A ceiling, not a target, and a FLAG because
#: sentence counting is a proxy for pace and a good scene can break it.
MAX_SENTENCES_PRESENT_GUIDE = 2

#: How much uncovered script counts as a gap worth showing. Below this it is
#: whitespace and connective tissue between spans, not a lost beat.
MIN_GAP_CHARS = 120


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    scene_index: Optional[int] = None
    outcome_id: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "scene_index": self.scene_index,
            "outcome_id": self.outcome_id,
            "detail": self.detail,
        }


def _sentences(text: str) -> int:
    if not text:
        return 0
    return len([s for s in text.replace("!", ".").replace("?", ".").split(".")
                if s.strip()])


def _scene_field(scene: Any, name: str, default: Any = None) -> Any:
    if isinstance(scene, dict):
        return scene.get(name, default)
    return getattr(scene, name, default)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def review(
    *,
    scenes: Sequence[Any],
    outcomes: Sequence[Dict[str, Any]],
    evidence_map: Optional[Dict[str, Any]] = None,
    dropped_beats: Optional[Sequence[Dict[str, Any]]] = None,
    source_text: str = "",
) -> Tuple[List[Finding], List["OutcomeRow"]]:
    """Assess one design. Writes nothing, reads nothing but its arguments."""
    evidence_map = evidence_map or {}
    dropped_beats = list(dropped_beats or [])
    findings: List[Finding] = []

    indices = {int(_scene_field(s, "scene_index", i) or 0)
               for i, s in enumerate(scenes)}
    declared_ids = {str(o.get("id")) for o in outcomes if o.get("id")}

    # ── per-scene declarations ───────────────────────────────────────────
    events_present: List[str] = []
    for i, scene in enumerate(scenes):
        idx = int(_scene_field(scene, "scene_index", i) or 0)
        serves = _scene_field(scene, "serves_outcomes") or []
        event = _scene_field(scene, "instructional_event")
        origin = _scene_field(scene, "scene_origin")
        refs = _scene_field(scene, "source_refs") or []
        media = _scene_field(scene, "media_type")
        params = _scene_field(scene, "generation_params") or {}
        narration = _scene_field(scene, "narration_text") or ""
        if event:
            events_present.append(event)

        if not serves:
            findings.append(Finding(
                REFUSE, "SCENE_SERVES_NOTHING",
                "declares no learning outcome. Foundation §1: a scene that "
                "serves nothing is decoration and is cut.",
                scene_index=idx,
            ))
        else:
            unknown = [o for o in serves if str(o) not in declared_ids]
            if unknown and declared_ids:
                findings.append(Finding(
                    REFUSE, "SCENE_CITES_UNKNOWN_OUTCOME",
                    f"cites outcome(s) that the brief does not declare: {unknown}",
                    scene_index=idx, detail={"cited": unknown,
                                             "declared": sorted(declared_ids)},
                ))

        if not event:
            findings.append(Finding(
                REFUSE, "SCENE_NO_EVENT",
                "declares no instructional_event. Without it the arc cannot be "
                "read and the Merrill check cannot run.",
                scene_index=idx,
            ))
        elif event not in INSTRUCTIONAL_EVENTS:
            findings.append(Finding(
                REFUSE, "SCENE_BAD_EVENT",
                f"instructional_event {event!r} is not one of Gagné's nine.",
                scene_index=idx,
            ))

        if origin is None:
            findings.append(Finding(
                REFUSE, "SCENE_PROVENANCE_UNDECLARED",
                "declares neither source_refs nor origin 'designed'. Silent "
                "invention is the defect class ruling R1a exists to remove — "
                "designed material is welcome, undeclared material is not.",
                scene_index=idx,
            ))
        elif origin == "sourced" and not refs:
            findings.append(Finding(
                REFUSE, "SCENE_SOURCED_WITHOUT_REFS",
                "claims to work from the script but names no span.",
                scene_index=idx,
            ))

        # RULE 8 / Foundation §4: the symbolic-procedure row of the modality
        # table. UNCHANGED from v7 — a motion scene without a template and
        # params cannot be drawn, and the renderer is the only thing on this
        # pipeline that gets digits right.
        if media == "motion_graphics":
            template = params.get("template") if isinstance(params, dict) else None
            if not template:
                findings.append(Finding(
                    REFUSE, "MOTION_WITHOUT_TEMPLATE",
                    "is motion_graphics but carries no generation_params."
                    "template. RULE 8: the renderer draws the digits; diffusion "
                    "invents them.",
                    scene_index=idx,
                ))
            else:
                # ⛔ THE PARAMETERS ARE FLAT ALONGSIDE `template`, NOT NESTED
                # UNDER A `params` KEY. This check's first draft assumed the
                # nested shape and refused SEVEN sound motion scenes on the
                # first acceptance run — the real rows read
                # {"top": 23, "bottom": 14, "phase": "start",
                #  "template": "column_multiplication_step"}.
                #
                # And it is checked against the RENDERER'S OWN SPEC rather than
                # against any shape this module believes in, so a template that
                # gains a parameter (as two did when WP-IVGS-10 added `phase`)
                # cannot leave this check quietly passing a spec that will fail
                # at authoring time.
                missing = _missing_motion_params(template, params)
                if missing is None:
                    findings.append(Finding(
                        REFUSE, "MOTION_UNKNOWN_TEMPLATE",
                        f"is motion_graphics with template {template!r}, which "
                        "the renderer does not serve.",
                        scene_index=idx,
                    ))
                elif missing:
                    findings.append(Finding(
                        REFUSE, "MOTION_WITHOUT_PARAMS",
                        f"is motion_graphics with template {template!r} and is "
                        f"missing the parameter(s) it needs: {missing}.",
                        scene_index=idx, detail={"missing": missing},
                    ))

        if not _scene_field(scene, "media_rationale"):
            findings.append(Finding(
                FLAG, "NO_MODALITY_RATIONALE",
                "gives no one-line reason for its medium (v7 RULE 9 / "
                "Foundation §4). A wrong choice and a right one look identical "
                "on the row without it.",
                scene_index=idx,
            ))

        if event in ("present", "guide") and _sentences(narration) > MAX_SENTENCES_PRESENT_GUIDE:
            findings.append(Finding(
                FLAG, "SEGMENTING",
                f"is a {event} scene carrying {_sentences(narration)} sentences; "
                f"Foundation §4 segmenting suggests ≤ {MAX_SENTENCES_PRESENT_GUIDE} "
                "per visual change at novice pace.",
                scene_index=idx,
            ))

        rewrite = _scene_field(scene, "rewrite_of")
        if isinstance(rewrite, dict) and not rewrite.get("original"):
            findings.append(Finding(
                FLAG, "REWRITE_WITHOUT_ORIGINAL",
                "marks a rewrite but carries no original to diff it against. "
                "R1a requires the original beside it at the gate.",
                scene_index=idx,
            ))

    # ── the alignment triad, per outcome ─────────────────────────────────
    rows: List[OutcomeRow] = []
    for outcome in outcomes:
        oid = str(outcome.get("id") or "")
        served_by = sorted(
            int(_scene_field(s, "scene_index", i) or 0)
            for i, s in enumerate(scenes)
            if oid in [str(x) for x in (_scene_field(s, "serves_outcomes") or [])]
        )
        # Assessed = a scene that serves it AND performs an assessing event.
        # The evidence_map is the designer's CLAIM; this is the check of it.
        assessed_by = sorted(
            int(_scene_field(s, "scene_index", i) or 0)
            for i, s in enumerate(scenes)
            if oid in [str(x) for x in (_scene_field(s, "serves_outcomes") or [])]
            and _scene_field(s, "instructional_event") in ASSESSING_EVENTS
        )
        rows.append(OutcomeRow(
            outcome_id=oid,
            text=str(outcome.get("text") or ""),
            measurable=bool(outcome.get("measurable", True)),
            proposed_refinement=outcome.get("proposed_refinement"),
            bloom_level=outcome.get("bloom_level"),
            served_by=served_by,
            assessed_by=assessed_by,
        ))
        if not served_by:
            findings.append(Finding(
                REFUSE, "OUTCOME_UNSERVED",
                "is served by no scene. Foundation §1: an outcome served by "
                "nothing fails the design at the gate.",
                outcome_id=oid,
            ))
        if not assessed_by:
            findings.append(Finding(
                REFUSE, "OUTCOME_UNASSESSED",
                "is served but never assessed — no scene serving it performs "
                f"{sorted(ASSESSING_EVENTS)}. Serving is not evidence; "
                "Foundation §1 stage 2 decides what would PROVE it.",
                outcome_id=oid,
            ))
        claimed = evidence_map.get(oid)
        if isinstance(claimed, list):
            phantom = [c for c in claimed if int(c) not in indices]
            if phantom:
                findings.append(Finding(
                    REFUSE, "EVIDENCE_MAP_PHANTOM_SCENE",
                    f"evidence_map names scene(s) {phantom} that do not exist.",
                    outcome_id=oid, detail={"claimed": claimed},
                ))
            disagree = sorted(set(int(c) for c in claimed if int(c) in indices)
                              - set(assessed_by))
            if disagree:
                findings.append(Finding(
                    FLAG, "EVIDENCE_MAP_DISAGREES",
                    f"evidence_map claims scene(s) {disagree} assess this "
                    "outcome, but they do not declare an assessing event.",
                    outcome_id=oid,
                ))
        if not outcome.get("measurable", True):
            findings.append(Finding(
                FLAG, "OUTCOME_NOT_MEASURABLE",
                "is not stated measurably. An ABCD refinement is PROPOSED for "
                "your approval and has NOT been applied — the design was made "
                "against your words as written.",
                outcome_id=oid,
                detail={"proposed_refinement": outcome.get("proposed_refinement")},
            ))

    # ── Merrill: does the design ever leave demonstration? ───────────────
    if events_present and not (set(events_present) & APPLICATION_EVENTS):
        findings.append(Finding(
            FLAG, "MERRILL_NO_APPLICATION",
            "no scene performs practice, feedback or assess — every scene sits "
            f"in events 1-5 ({sorted(DEMONSTRATION_EVENTS)}). Foundation §3: a "
            "storyboard missing application is a lecture, not a lesson.",
            detail={"events": events_present},
        ))

    # ── the fading sequence: practice must be prepared ───────────────────
    ordered = sorted(
        ((int(_scene_field(s, "scene_index", i) or 0), s)
         for i, s in enumerate(scenes)),
        key=lambda pair: pair[0],
    )
    for idx, scene in ordered:
        if _scene_field(scene, "instructional_event") not in ("practice", "assess"):
            continue
        serves = {str(x) for x in (_scene_field(scene, "serves_outcomes") or [])}
        prepared = any(
            _scene_field(prev, "instructional_event") in ("present", "guide")
            and serves & {str(x) for x in (_scene_field(prev, "serves_outcomes") or [])}
            for pidx, prev in ordered if pidx < idx
        )
        if not prepared:
            findings.append(Finding(
                FLAG, "PRACTICE_NOT_PREPARED",
                "asks the learner to perform before any earlier scene presents "
                "or guides the same outcome. Foundation §4: every practice "
                "scene is preceded by a present/guide on the same outcome — the "
                "worked → faded → independent sequence.",
                scene_index=idx,
            ))

    # ── beat coverage: what the script said and the design did not use ───
    findings.extend(_coverage_gaps(scenes, dropped_beats, source_text))

    return findings, rows


def _coverage_gaps(
    scenes: Sequence[Any],
    dropped_beats: Sequence[Dict[str, Any]],
    source_text: str,
) -> List[Finding]:
    """Stretches of the uploaded script that no scene uses and no drop declares.

    See the module docstring for why this flags rather than refuses.
    """
    if not source_text:
        return []
    spans: List[Tuple[int, int]] = []
    for scene in scenes:
        for ref in (_scene_field(scene, "source_refs") or []):
            if isinstance(ref, dict):
                spans.append((int(ref.get("start") or 0), int(ref.get("end") or 0)))
    for beat in dropped_beats:
        span = beat.get("span") if isinstance(beat, dict) else None
        if isinstance(span, dict):
            spans.append((int(span.get("start") or 0), int(span.get("end") or 0)))
    if not spans:
        return [Finding(
            FLAG, "NO_SOURCE_COVERAGE",
            "not one scene names a span of the uploaded script and not one "
            "beat is declared dropped. Either the design ignored the script "
            "entirely or it did not say what it used.",
            detail={"script_chars": len(source_text)},
        )]

    merged: List[List[int]] = []
    for start, end in sorted((max(0, a), min(len(source_text), b))
                             for a, b in spans if b > a):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    findings: List[Finding] = []
    cursor = 0
    for start, end in merged + [[len(source_text), len(source_text)]]:
        if start - cursor >= MIN_GAP_CHARS:
            text = source_text[cursor:start].strip()
            findings.append(Finding(
                FLAG, "UNDECLARED_SCRIPT_GAP",
                f"{start - cursor} characters of the uploaded script are used "
                "by no scene and declared in no dropped_beat.",
                detail={"start": cursor, "end": start,
                        "text": text[:400] + ("…" if len(text) > 400 else "")},
            ))
        cursor = max(cursor, end)
    return findings



def _missing_motion_params(template: str, params: Dict[str, Any]) -> Optional[List[str]]:
    """Parameters the renderer declares and this scene has not supplied.

    Returns ``None`` when the template is not one the renderer serves, and a
    (possibly empty) list otherwise. Read from ``shared.motion.templates`` so
    this module holds no second copy of the contract.
    """
    try:
        from shared.motion.templates import template_spec
        spec = template_spec(template)
    except Exception:                                            # noqa: BLE001
        return None
    if not spec:
        return None
    declared = list((spec.get("params") or {}).keys())
    return [name for name in declared if params.get(name) is None]


@dataclass
class OutcomeRow:
    outcome_id: str
    text: str
    measurable: bool = True
    proposed_refinement: Optional[str] = None
    bloom_level: Optional[str] = None
    served_by: List[int] = field(default_factory=list)
    assessed_by: List[int] = field(default_factory=list)

    @property
    def served(self) -> bool:
        return bool(self.served_by)

    @property
    def assessed(self) -> bool:
        return bool(self.assessed_by)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "text": self.text,
            "measurable": self.measurable,
            "proposed_refinement": self.proposed_refinement,
            "bloom_level": self.bloom_level,
            "served_by": self.served_by,
            "assessed_by": self.assessed_by,
            "served": self.served,
            "assessed": self.assessed,
        }


def split(findings: Iterable[Finding]) -> Tuple[List[Finding], List[Finding]]:
    findings = list(findings)
    return ([f for f in findings if f.severity == REFUSE],
            [f for f in findings if f.severity == FLAG])
