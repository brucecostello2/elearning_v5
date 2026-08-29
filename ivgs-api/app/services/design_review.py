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

⛔ WP-IVGS-12c: ONE CHECK WAS PROMOTED FROM FLAG TO REFUSAL, AND WHY IT QUALIFIES

``EVIDENCE_MAP_DISAGREES`` was a flag. It is now a hard refusal, because it is
the same KIND of thing as "scene 7 declares no outcome" and not the same kind of
thing as "scene 7 feels thin": the designer names scene 5 as the evidence for
LO-2, and the check reads scene 5's OWN two declarations — is LO-2 in its
``serves_outcomes``, and is its ``instructional_event`` ``practice`` or
``assess``? Both are closed enums the designer wrote itself. Nothing here is
judged; two declarations by one author are compared and they either agree or
they do not. That is the WP-IVGS-10 line, and this is on the objective side of
it.

It is promoted alongside a schema change: ``evidence_map`` now REQUIRES a key
per outcome holding at least one scene index (contract-3, measured enforced), so
"nothing assesses this outcome" is no longer an emittable sentence. Together the
two make *every outcome is served and assessed* **structurally or loudly** true —
the schema forces the claim to exist, this module refuses a false one.

⛔ AND HERE IS EXACTLY WHAT THAT STILL CANNOT DO, stated because it is the
residue and not a caveat to be discovered later. Neither the schema nor this
module can force the named scene to GENUINELY assess. A designer that labels a
recap ``assess`` and points ``evidence_map`` at it passes both checks. What
changes is the SHAPE of the failure: RC-Q9b arrived as a missing map, which
looks like a machine problem; it now arrives as a scene whose event label does
not match its own narration, which looks like what it is — a wrong brief, in
front of the reviewer, at the gate. **That judgment is the reviewer's, by
design.** Foundation §7 gives it to them and this module does not take it back.

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

#: WP-IVGS-12b Task 1(d). A single contiguous uncovered stretch this large is a
#: BEAT, not connective tissue — the acceptance run's was 2,658 characters,
#: three times running, with `dropped_beats` empty every time.
#:
#: ⛳ WHY THIS ONE HARD-REFUSES WHERE THE ATTRIBUTION FLAG DOES NOT. The worry
#: that keeps gap attribution soft is the model's span ARITHMETIC — an
#: off-by-twenty on one offset should not refuse a sound design. That worry does
#: not touch this check: `dropped_beats == []` is the model's own CLAIM that it
#: used everything, the uncovered length is measured BY CODE against the
#: uploaded text, and the two cannot both be true. Silence is the defect class,
#: and an empty array asserting completeness over a 400-character hole is the
#: purest form of it.
HARD_GAP_CHARS = 400


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


def _indices(claimed: Any) -> List[int]:
    """Scene indices out of an ``evidence_map`` entry, tolerantly.

    A stored brief is JSONB and a model emission is a model emission, so ``"3"``
    is possible and so is ``null`` inside the list. A non-numeric entry is
    DROPPED rather than crashing the whole review: the gate exists to report on
    a bad brief, and a gate that 500s on one is no gate.
    """
    if not isinstance(claimed, list):
        return []
    out: List[int] = []
    for item in claimed:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


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
    learning_outcomes: str = "",
) -> Tuple[List[Finding], List["OutcomeRow"]]:
    """Assess one design. Writes nothing, reads nothing but its arguments."""
    evidence_map = evidence_map or {}
    dropped_beats = list(dropped_beats or [])
    findings: List[Finding] = []
    findings.extend(_outcomes_are_the_operators(learning_outcomes, outcomes))

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
        # ── the designer's evidence CLAIM, checked against its own scenes ──
        raw_claim = evidence_map.get(oid)
        claimed = _indices(raw_claim)
        if not claimed:
            # ⛳ CANNOT FIRE WHEN THE SCHEMA ARMED. contract-3 makes this key
            # required and its array 1..N, so the model has no way to emit it.
            # It fires on the paths where that guarantee does not reach: a
            # project whose outcomes were never stated (the enum degrades to an
            # open object), a brief written by an older contract, or a row that
            # arrived by some route other than the capture observer. On those,
            # THIS is the whole of the guarantee, and it says so out loud.
            findings.append(Finding(
                REFUSE, "EVIDENCE_MAP_NAMES_NOTHING",
                "evidence_map names no scene as the evidence for this outcome. "
                "Deciding what would PROVE an outcome is stage 2 of backward "
                "design; a design that never decided it is not finished.",
                outcome_id=oid, detail={"claimed": raw_claim},
            ))
        else:
            phantom = [c for c in claimed if c not in indices]
            if phantom:
                findings.append(Finding(
                    REFUSE, "EVIDENCE_MAP_PHANTOM_SCENE",
                    f"evidence_map names scene(s) {phantom} that do not exist.",
                    outcome_id=oid, detail={"claimed": claimed},
                ))
            # ⛔ WP-IVGS-12c: A HARD REFUSAL, PROMOTED FROM A FLAG. See the
            # module docstring. A scene named as evidence for this outcome must
            # itself declare BOTH: the outcome in `serves_outcomes`, and an
            # instructional_event in {practice, assess}. Two declarations by
            # one author, compared. The two failures are separated because they
            # have different fixes — one scene is pointed at the wrong outcome,
            # the other is labelled the wrong event.
            real = [c for c in claimed if c in indices]
            not_serving = sorted(set(real) - set(served_by))
            not_assessing = sorted((set(real) & set(served_by)) - set(assessed_by))
            if not_serving or not_assessing:
                parts = []
                if not_serving:
                    parts.append(
                        f"scene(s) {not_serving} do not list this outcome in "
                        "their own serves_outcomes"
                    )
                if not_assessing:
                    parts.append(
                        f"scene(s) {not_assessing} serve it but declare an "
                        f"instructional_event outside {sorted(ASSESSING_EVENTS)}"
                    )
                findings.append(Finding(
                    REFUSE, "EVIDENCE_MAP_DISAGREES",
                    "evidence_map claims this outcome is assessed by scenes "
                    "that say otherwise about themselves: " + "; and ".join(parts)
                    + ". The map is a claim about the scenes; the scenes are "
                    "the fact.",
                    outcome_id=oid,
                    detail={"claimed": claimed, "not_serving": not_serving,
                            "not_assessing": not_assessing,
                            "served_by": served_by, "assessed_by": assessed_by},
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


def _outcomes_are_the_operators(
    learning_outcomes: str, outcomes: Sequence[Dict[str, Any]],
) -> List[Finding]:
    """THE BELT. Do the brief's outcomes still say what the operator typed?

    WP-IVGS-12b Task 1(d). ⛳ **WITH THE STRUCTURAL FIX IN PLACE THIS CANNOT
    FAIL**, because `DesignBriefService._outcomes_from_the_project` builds the
    list from `projects.learning_outcomes` and the model never sees the text.
    It exists so that if anyone ever routes outcome text back through a model
    again — a v10 prompt, a migration, a well-meant refactor — **RC-Q9 comes
    back LOUD instead of silently redrawing the gate's matrix against a
    paraphrase.** A check that can only fire on a regression is the point of it.
    """
    if not learning_outcomes.strip():
        return []
    from shared.design.outcomes import is_faithful, parse_outcomes

    expected = parse_outcomes(learning_outcomes)
    if len(expected) != len(outcomes):
        return [Finding(
            REFUSE, "OUTCOMES_COUNT_DRIFTED",
            f"the operator wrote {len(expected)} learning outcome(s) and this "
            f"brief carries {len(outcomes)}. An outcome that vanishes between "
            "the form field and the design is the RC-Q9 defect returning.",
            detail={"operator": len(expected), "brief": len(outcomes)},
        )]
    drifted = [
        {"id": e["id"], "operator": e["text"], "brief": str(b.get("text") or "")}
        for e, b in zip(expected, outcomes)
        if str(b.get("text") or "") != e["text"]
    ]
    if drifted:
        return [Finding(
            REFUSE, "OUTCOMES_TEXT_DRIFTED",
            "the brief's outcome text is not what the operator typed. It is "
            "never rewritten in place — a refinement is PROPOSED beside it.",
            outcome_id=drifted[0]["id"], detail={"drifted": drifted},
        )]
    if not is_faithful(learning_outcomes, expected):          # pragma: no cover
        return [Finding(
            FLAG, "OUTCOMES_PARSE_NOT_REVERSIBLE",
            "the outcome parser could not reconstruct the operator's text "
            "byte for byte, so the comparison above is weaker than it looks.",
        )]
    return []


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
            REFUSE if not dropped_beats else FLAG, "NO_SOURCE_COVERAGE",
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
        gap = start - cursor
        if gap >= MIN_GAP_CHARS:
            text = source_text[cursor:start].strip()
            # Task 1(d). An empty `dropped_beats` is the model CLAIMING it used
            # everything. Code has just measured a hole. Both cannot be true,
            # and the emptiness is not subject to the span-arithmetic doubt that
            # keeps attribution soft — see HARD_GAP_CHARS.
            hard = gap >= HARD_GAP_CHARS and not dropped_beats
            findings.append(Finding(
                REFUSE if hard else FLAG,
                "UNDECLARED_GAP_WITH_NO_DROPS" if hard else "UNDECLARED_SCRIPT_GAP",
                (
                    f"{gap} characters of the uploaded script are used by no "
                    "scene, and dropped_beats is EMPTY — which claims nothing "
                    "was dropped. Declare what you left out and why."
                ) if hard else (
                    f"{gap} characters of the uploaded script are used by no "
                    "scene and declared in no dropped_beat."
                ),
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
