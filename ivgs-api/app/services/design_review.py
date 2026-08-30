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

⛔ WP-IVGS-12d: THREE CHECKS WERE DELETED, AND THE DELETION IS THE FIX

12c promoted ``EVIDENCE_MAP_DISAGREES`` from flag to hard refusal: the model
named scenes as evidence, and this module caught it when its own scenes said
otherwise. It fired on every outcome of every generation. **The check was
right and the question was wrong.** Asking a model to assemble a list of scene
indices it has already declared through ``serves_outcomes`` and
``instructional_event`` is asking it to transcribe — the RC-Q9 defect one layer
up — and a transcription can always disagree with its source.

So ``evidence_map`` left the model's schema (contract-4) and CODE derives it
from the scenes (``shared.design.evidence.derive_evidence_map``, imported by
both this module and the worker's parse so they cannot drift). A derived map
cannot disagree with the scenes, which makes three checks meaningless at once:

    EVIDENCE_MAP_DISAGREES        gone — nothing left to disagree
    EVIDENCE_MAP_PHANTOM_SCENE    gone — a derived index came from a scene
    EVIDENCE_MAP_NAMES_NOTHING    gone — it WAS ``OUTCOME_UNASSESSED``, twice

``OUTCOME_UNASSESSED`` is the one true check and is now computed from the
derived map. ⛳ **A package that removes three refusals and adds one is not
loosening the gate** — it is removing the ones that were measuring the model's
bookkeeping instead of its design.

⛔ AND ONE CHECK WAS ADDED, WHICH IS WHERE THE PRESSURE MOVED

The model now writes an ``assessment_plan`` BEFORE any scene exists — declaration
order binds generation order on the pinned engine, measured in both directions
against an explicit prompt instruction to do otherwise. So it commits to what
the learner will DO to prove each outcome while it has no lesson to rationalise
from. ``PLAN_ENTRY_UNREALIZED`` then checks the design against that promise:
every plan entry must be realized by at least one scene serving that outcome and
declaring that exact ``evidence_kind``.

⛳ **THIS IS OBJECTIVE IN THE WP-IVGS-10 SENSE AND THAT IS WHY IT REFUSES.** The
plan's ``evidence_kind`` is a closed two-value enum the model chose; the scene's
``instructional_event`` is a closed nine-value enum the model chose. Two
declarations by one author, compared. Nothing here judges whether the practice
item is any good.

⛔ WP-IVGS-12f: TWO OF THESE REFUSALS ARE NOW STRUCTURALLY UNREACHABLE, AND
NEITHER IS DELETED

Contract-5 makes `designed_assessments` a REQUIRED per-outcome object whose
values are scenes the grammar pins to `origin: "designed"`,
`instructional_event: "assess"` and `serves_outcomes: [that outcome]`. Code
merges them into the sequence. So for any emission the decoder accepted:

    OUTCOME_UNASSESSED             every outcome has an `assess` scene serving
                                   it, so the derived map is never empty
    PLAN_ENTRY_UNREALIZED(assess)  a plan entry promising `assess` is realized
                                   by that outcome's designed assessment, always

⛔ WP-IVGS-12g: THE OTHER HALF, AND ONE NEW CHECK THAT IS BORN UNREACHABLE

Contract-5 forced `assess` and left `practice` to the model's own
follow-through, and RC-Q9f measured what happened in the gap — SIX generations
of six refused `PLAN_ENTRY_UNREALIZED` on LO-2, whose plan said `practice` in
every one. That is RC-Q9d's non-causal plan surviving intact in the one kind the
grammar did not force, and it is the fourth package to measure the same law:
**on this stack the model's plan predicts nothing; only the grammar is causal.**

Contract-6 applies it once, to the whole evidence layer. `practice_scenes`
(1..2 per outcome) and `assessment_scenes` (exactly 1) are both REQUIRED
per-outcome sections, and `scenes[]` loses `practice` and `assess` from its
`instructional_event` enum entirely. So:

    PLAN_ENTRY_UNREALIZED          unreachable for BOTH kinds now, not one.
                                   Whichever kind the plan promises, a scene
                                   serving that outcome and declaring that kind
                                   exists before the plan is even read
    OUTCOME_ASSESSED_TWICE         new, and it has never been able to fire.
                                   RC-Q9f limb 2 is the reason it exists: with
                                   `assess` forced elsewhere, contract-5's model
                                   began writing EXTRA assess scenes into
                                   `scenes[]` — four generations of six — and
                                   the merge placed the mandated one beside its
                                   near-identical twin, posing one problem twice
                                   back to back. `scenes[]` cannot declare
                                   `assess` any more and the section holds
                                   exactly one, so the count is always one

⛳ ALL OF THEM STAY, AS THE LOUD REGRESSION BELT, AND THAT INCLUDES THE ONE BORN
UNREACHABLE. A structural guarantee is a claim about a schema, a merge and a
decoder, and all three are code that can be edited by someone who does not know
why they are shaped this way. This whole lineage is a record of guarantees that
turned out narrower than believed — `guided_json` returning 200 and doing
nothing is the purest example, and contract-5's own `assess`-only forcing is the
most recent. A check that can never fire costs one comparison per outcome and is
the only thing that will say so out loud when the guarantee stops holding.
`test_wpivgs12g_evidence_layer` asserts every one of these unreachable directly,
including against the hostile cases, so the guarantee is MEASURED and not
assumed.

⛳ AND THEY BOTH STAY, AS THE LOUD REGRESSION BELT. A structural guarantee is a
claim about a schema, a merge and a decoder, and all three are code that can be
edited by someone who does not know why they are shaped this way. The whole
lineage this gate lives in is a record of guarantees that turned out to be
narrower than believed — `guided_json` returning 200 and doing nothing is the
purest example. A check that can never fire costs one comparison per outcome and
is the only thing that will say so out loud when the guarantee stops holding.
`test_wpivgs12f_designed_assessments` asserts the unreachability directly, so
the guarantee is measured rather than assumed, and the check is what catches the
day the measurement stops being true in production.

⚠ AND ONE REFUSAL GOT QUIETLY WEAKER, WHICH IS 12f'S OWN COST AND IS NOT HIDDEN.
`OUTCOME_UNSERVED` asks whether ANY scene declares the outcome. A designed
assessment declares it, so an outcome the lesson never TEACHES — no present, no
guide, nothing — is no longer unserved: it is served by its own assessment.
`PRACTICE_NOT_PREPARED` is what remains, and it names exactly that shape ("asks
the learner to perform before any earlier scene presents or guides the same
outcome"). It is a FLAG. Promoting it is an operator ruling and this package did
not take it — 12c's promotion of `EVIDENCE_MAP_DISAGREES` was ordered, not
chosen, and the precedent is the point.

⛔ WP-IVGS-12g DOES NOT RESTORE IT AND MAKES THE COST TOTAL, WHICH IS SAID HERE
RATHER THAN DISCOVERED. Under contract-6 every outcome carries at least two
authored evidence scenes that declare it, so `OUTCOME_UNSERVED` is now
unreachable as well — and unlike the other two it is unreachable for a reason
nobody should be comforted by. It has stopped measuring anything. The question
it was asked to answer, *"does this lesson TEACH the outcome it assesses?"*,
now lives ONLY in `PRACTICE_NOT_PREPARED`, still a flag, firing on the merged
sequence when nothing presents or guides the outcome before its attempt. ⚠ The
belt-and-braces reading — three unreachable refusals plus one flag — is that
this gate's hard limb increasingly measures the grammar rather than the design,
and that the flag limb is where a reviewer's attention now has to go. Promoting
`PRACTICE_NOT_PREPARED` remains an operator ruling and 12g does not take it
either.

⛳ WP-IVGS-12h ADDS THE REFUSAL THAT ANSWERS 12g's OWN CLOSING SENTENCE

12g wrote of RC-Q9g: *"Two narrations being equal is a string comparison, and
near-equality is a judgment. WP-IVGS-10's line holds: this is reviewer
territory, not a hard refusal."* ⛔ **That sentence is superseded by this
package, and by measurement rather than by preference.** Near-equality stopped
being a judgment the moment it was calibrated: `EVIDENCE_NEAR_DUPLICATE` scores
the assessment against its own practice and against the lesson's worked
examples with a fixed formula and a fixed generic stoplist, and on 18 banked
outcome-pairs from two scripts the duplicate class and the sound class separate
0.667 | 0.900 with the threshold in the gap. A reviewer can act on *"LO-2's
assessment repeats its practice word for word"* — which is WP-IVGS-10's test,
and the reason the line is held rather than moved.

⛳ AND IT IS THE FIRST HARD REFUSAL IN THREE PACKAGES THAT MEASURES THE DESIGN
RATHER THAN THE GRAMMAR. The paragraph above says this gate's hard limb had
become a check on the schema — three refusals unreachable by construction and
the teaching question left to one flag. This one cannot be made unreachable by
any grammar: two strings the same author wrote are two strings, and no decoder
can be told to make them different. `shared.design.duplication` carries the
measure, the thresholds and the argument for both.

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

from shared.design.duplication import (
    NEAR_DUPLICATE_CONTAINMENT,
    NO_FRESH_AXIS_CONTAINMENT,
    duplication_verdict,
    explain as explain_duplication,
)
from shared.design.equations import lint_scenes as lint_equations
from shared.design.evidence import (
    derive_evidence_map,
    realizes,
    scene_index_of,
)
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

#: ⛔ WP-IVGS-12i2, RC-S2(a). THE LOOPHOLE THIS CONSTANT USED TO HAVE, AND WHY
#: IT IS GONE.
#:
#: The 12b rule above was `gap >= HARD_GAP_CHARS and not dropped_beats`, and the
#: second clause is GLOBAL where the first is PER-SPAN. So **one throwaway
#: declared drop anywhere in the design defeated the check for every hole in the
#: script.** Measured on the operator's live project, 2026-08-30: the
#: regenerated design declared ONE drop, cited source spans covering **110 of
#: 3,138 characters — 3.5%** — and left a single undeclared 2,968-character
#: stretch. Old rule: zero refusals. The first watch's design covered 51.7% and
#: left a 1,473-character tail (the script's whole "Step 4: Add the Two Answers"
#: section) with two drops declared. Old rule: zero refusals.
#:
#: ⛳ THE NEW RULE IS PER-SPAN, AND NOTE THAT IT NEEDS NO NEW BOOKKEEPING: a
#: declared drop's span is ALREADY merged into the coverage below, so a stretch
#: that survives as a gap is by construction one that **no drop declared**.
#: Dropping the global clause is therefore exactly the operator's rule —
#: *"every unused span >= 400 chars must be individually covered by a declared
#: drop whose span matches it; an undeclared span over threshold refuses
#: regardless of other drops"* — and not an approximation of it.
#:
#: ⚠ THE SPAN-ARITHMETIC DOUBT THAT KEEPS ATTRIBUTION SOFT DOES NOT REACH HERE,
#: and that is why this can be hard. An off-by-twenty on one offset does not
#: manufacture a 400-character hole; 400 characters is a BEAT.


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
    assessment_plan: Optional[Dict[str, Any]] = None,
    dropped_beats: Optional[Sequence[Dict[str, Any]]] = None,
    source_text: str = "",
    learning_outcomes: str = "",
) -> Tuple[List[Finding], List["OutcomeRow"]]:
    """Assess one design. Writes nothing, reads nothing but its arguments.

    ⛔ THERE IS NO `evidence_map` PARAMETER ANY MORE (WP-IVGS-12d). It is
    DERIVED here, from the scenes, by the same shared function the worker uses
    at capture. Accepting one would reintroduce exactly the thing contract-4
    removed: a second, authored account of what the scenes already say.
    """
    assessment_plan = assessment_plan if isinstance(assessment_plan, dict) else {}
    dropped_beats = list(dropped_beats or [])
    findings: List[Finding] = []
    findings.extend(_outcomes_are_the_operators(learning_outcomes, outcomes))

    indices = {int(_scene_field(s, "scene_index", i) or 0)
               for i, s in enumerate(scenes)}
    declared_ids = {str(o.get("id")) for o in outcomes if o.get("id")}

    # ⛔ THE EVIDENCE MAP, DERIVED — the design's own answer to "what assesses
    # this outcome", read off the scenes rather than accepted from an author.
    # One function, shared with the worker's parse, so a stored brief's map and
    # this computation are the same map by construction.
    evidence_map = derive_evidence_map(
        scenes, [str(o.get("id")) for o in outcomes if o.get("id")],
    )

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
        # ⛔ ONE DEFINITION (WP-IVGS-12d). This used to be a second in-place
        # computation of the same thing `derive_evidence_map` computes, sitting
        # a few lines from a THIRD account of it that the model had written.
        # Three answers to one question is how they came to disagree.
        assessed_by = list(evidence_map.get(oid, []))
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

        # ⛔ WP-IVGS-12g, RC-Q9f limb 2, BORN UNREACHABLE — see the module
        # docstring. The `assess` scenes serving this outcome, counted off the
        # merged sequence the same way `derive_evidence_map` reads it.
        independent = sorted(
            scene_index_of(s, i) for i, s in enumerate(scenes)
            if _scene_field(s, "instructional_event") == "assess"
            and oid in [str(x) for x in (_scene_field(s, "serves_outcomes") or [])]
        )
        if len(independent) > 1:
            findings.append(Finding(
                REFUSE, "OUTCOME_ASSESSED_TWICE",
                f"is assessed by {len(independent)} independent-attempt scenes "
                f"{independent}. One outcome gets ONE unaided attempt: a second "
                "poses the same problem again, and under contract-5 the two "
                "landed adjacent and near-identical (RC-Q9f limb 2). "
                "design-contract-6 emits exactly one per outcome and `scenes[]` "
                "cannot declare `assess` at all, so this firing means the "
                "structural guarantee has stopped holding — not that the "
                "designer made a judgment call.",
                outcome_id=oid,
                detail={"assess_scene_indices": independent},
            ))

        # ⛔ WP-IVGS-12h, RC-Q9g. THE CHECK THE GRAMMAR CANNOT MAKE.
        # Contract-6 guaranteed both kinds EXIST and measured, five generations
        # running, that the model filled both slots with the same sentence:
        # 9 of 15 outcome-pairs verbatim identical, 2 more differing by a
        # "Let's practice" prefix. Every schema-level check was correct and
        # silent — both scenes are legally declared, both serve the outcome, one
        # is `practice` and one is `assess`, and there is exactly one
        # assessment, so `OUTCOME_ASSESSED_TWICE` rightly does not fire.
        #
        # ⛳ IT REFUSES RATHER THAN FLAGS, AND THAT IS WP-IVGS-10's LINE HELD,
        # NOT CROSSED. 12g wrote that near-equality "is a judgment" and left it
        # to the reviewer. It is not a judgment once it is MEASURED: the
        # comparison is two strings the same author wrote, normalised by a fixed
        # generic stoplist, scored by a fixed formula, against a threshold
        # calibrated on 18 banked outcome-pairs where the two classes separate
        # 0.667 | 0.900. A reviewer can act on "LO-2's assessment repeats its
        # practice word for word"; that is the WP-IVGS-10 test and it passes it.
        # What stays a judgment — and stays a FLAG — is whether a DIFFERENT
        # assessment is a GOOD one.
        findings.extend(_evidence_is_distinct(oid, scenes))

        # ── RC-S3. THE SAME MEASURE, OVER THE PAIRS THE HARD LIMB CANNOT SEE ──
        # Assessment-anchored above; any other same-outcome pair here, at flag
        # level. The live regen's scenes 10/11 are the driving evidence.
        findings.extend(_same_outcome_duplicates(oid, scenes))

        # ── the promise, checked against the design that had to keep it ──
        findings.extend(_plan_is_realized(assessment_plan, oid, scenes))
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

    # ── RC-S4. IS THE MATHS TRUE? Last, and unconditioned on everything above:
    # a scene teaching a false calculation is wrong whether or not it is
    # declared, sourced, assessed or depictable.
    findings.extend(_arithmetic_is_true(scenes))

    return findings, rows


def _arithmetic_is_true(scenes: Sequence[Any]) -> List[Finding]:
    """RC-S4. Does what a scene SAYS about arithmetic actually hold?

    ⛳ THE OPERATOR'S CATCH, and the first check in this pipeline that asks
    whether generated content is CORRECT rather than whether it is DECLARED,
    DEPICTABLE or CONSISTENT WITH ITS TEMPLATE. Every other check here would
    pass a scene that teaches 23 × 14 = 212 without a murmur.

    ⛔ HARD, BECAUSE A COMPLETE CLAIM IS DECIDABLE BY ARITHMETIC. There is no
    taste in `4 times 3 equals 13`, no span-offset doubt and no pedagogical
    judgement — the sentence is wrong and a nine-year-old would learn it.

    ⚠ AND IT CATCHES ONLY WHAT IT CAN DECIDE. `shared.design.equations` parses
    statements naming both operands, the operation and the result; anything
    short of that falls out rather than being guessed at. **Scene 4 of the
    operator's own regenerated design — "we need to multiply the tens and the
    units separately" — is NOT caught by this and cannot be**, and RC-S4's
    ledger row says so rather than letting the presence of a maths check imply
    the maths was checked.
    """
    findings: List[Finding] = []
    for bad in lint_equations(scenes):
        findings.append(Finding(
            REFUSE, "NARRATION_ARITHMETIC_FALSE",
            f"states arithmetic that is not true — {bad['message']}. A scene "
            f"may not teach a false calculation. Fix the narration, or the "
            f"numbers it quotes."
            + (f" (This scene's template draws {bad['template_operands']}.)"
               if bad["template_operands"] else ""),
            scene_index=bad["scene_index"],
            detail=bad,
        ))
    return findings


def _evidence_is_distinct(
    oid: str, scenes: Sequence[Any],
) -> List[Finding]:
    """RC-Q9g. Is this outcome's assessment a different scene from its practice?

    WP-IVGS-12h TASK 2. The measure, the two limbs and the calibration are all in
    `shared.design.duplication`, imported here rather than restated — the API's
    gate, the worker and the acceptance harness must not answer this three ways.

    Anchored on the ASSESSMENT and compared against two sets:

      * the outcome's `practice` scenes — the defect RC-Q9g names; and
      * the `present`/`guide` scenes serving the same outcome, which are the
        lesson's worked examples. ⛳ That limb earned its place before it
        shipped: it catches script B2's LO-1, whose assessment *"Divide 432 by
        10."* is byte-identical to its own `guide` scene, in a design 12g read
        by hand and called correctly faded.

    ⚠ The practice is NOT compared against the worked examples here. The scope
    is the order's and it is the assessment; 12g's run A gen 2 quoted a practice
    that IS the script's own worked example, and that case is a named residue in
    the report rather than a check smuggled in under this one.
    """
    def _narration(scene: Any) -> str:
        return str(_scene_field(scene, "narration_text") or "")

    def _serving(scene: Any) -> bool:
        return oid in [str(x) for x in (_scene_field(scene, "serves_outcomes") or [])]

    indexed = [
        (int(_scene_field(s, "scene_index", i) or 0), s)
        for i, s in enumerate(scenes)
    ]
    assessments = [
        (idx, s) for idx, s in indexed
        if _scene_field(s, "instructional_event") == "assess" and _serving(s)
    ]
    others = [
        (idx, s, "practice" if _scene_field(s, "instructional_event") == "practice"
         else "worked example")
        for idx, s in indexed
        if _serving(s)
        and _scene_field(s, "instructional_event") in ("practice", "present", "guide")
    ]

    findings: List[Finding] = []
    for a_idx, assessment in assessments:
        a_text = _narration(assessment)
        if not a_text:
            continue
        for o_idx, other, kind in others:
            o_text = _narration(other)
            if not o_text:
                continue
            verdict = duplication_verdict(a_text, o_text)
            if not verdict["duplicate"]:
                continue
            findings.append(Finding(
                REFUSE, "EVIDENCE_NEAR_DUPLICATE",
                f"scene {a_idx} is this outcome's independent attempt and "
                f"scene {o_idx} is its {kind}, and "
                f"{explain_duplication(verdict['limb'])} "
                f"(containment {verdict['containment']:.2f} against a threshold "
                f"of {NEAR_DUPLICATE_CONTAINMENT}"
                + (f", and both use the numbers {verdict['assessment_numerals']}"
                   if verdict["limb"] == "no_fresh_axis" else "")
                + "). Foundation §2: the assessment is the END of the fading "
                "sequence, not the middle of it repeated. Pose it cold, in "
                "numbers this lesson has not worked.",
                scene_index=a_idx,
                outcome_id=oid,
                detail={
                    "assessment_scene_index": a_idx,
                    "duplicate_of_scene_index": o_idx,
                    "duplicate_of_kind": kind,
                    "assessment_narration": a_text,
                    "other_narration": o_text,
                    "threshold": (
                        NO_FRESH_AXIS_CONTAINMENT
                        if verdict["limb"] == "no_fresh_axis"
                        else NEAR_DUPLICATE_CONTAINMENT
                    ),
                    **verdict,
                },
            ))
    return findings


def _same_outcome_duplicates(
    oid: str, scenes: Sequence[Any],
) -> List[Finding]:
    """RC-S3. ANY two scenes serving one outcome that say the same thing.

    ⛳ THE WIDENING THE 12h BELT'S OWN DOCSTRING NAMED AS ITS RESIDUE:
    *"The practice is NOT compared against the worked examples here."* That
    scope was the order's and it was anchored on the ASSESSMENT, so a design can
    repeat itself anywhere else in an outcome's sequence and nothing sees it.

    ⛔ MEASURED ON THE OPERATOR'S REGENERATED LIVE DESIGN, 2026-08-30. LO-2's
    `guide` scene 10 and its `practice` scene 11 carry **byte-identical**
    narration — *"Can you identify the units and tens in the number 45?"* — and
    so do LO-1's scenes 6/7/8 and LO-3's 13/14. Neither member of any of those
    pairs is an `assess`, so the assessment-anchored belt could not and did not
    fire. Three duplicated pairs, and the gate said nothing.

    ⛳ WHY THIS LIMB IS A FLAG AND THE ASSESSMENT LIMB STAYS HARD, per the
    operator's ruling: *"hard only where 12h's ruling already made it hard;
    flag-level elsewhere."* The hard case has a pedagogical absolute behind it —
    an independent attempt that repeats the practice is not evidence, full stop.
    Two `guide` scenes that restate one question are usually a defect and
    sometimes deliberate repetition for a nine-year-old who is anxious about
    multiplication, and this module does not get to decide which. The reviewer
    does, with the pair in front of them.

    ⚠ IT USES THE SAME MEASURE, NOT A SECOND ONE. `duplication_verdict` is
    imported and called exactly as the hard limb calls it, so a threshold change
    moves both together and the calibration bank governs both.
    """
    def _narration(scene: Any) -> str:
        return str(_scene_field(scene, "narration_text") or "")

    serving = [
        (int(_scene_field(s, "scene_index", i) or 0), s)
        for i, s in enumerate(scenes)
        if oid in [str(x) for x in (_scene_field(s, "serves_outcomes") or [])]
    ]

    findings: List[Finding] = []
    for position, (a_idx, a) in enumerate(serving):
        a_text = _narration(a)
        if not a_text:
            continue
        for b_idx, b in serving[position + 1:]:
            b_text = _narration(b)
            if not b_text:
                continue
            a_event = str(_scene_field(a, "instructional_event") or "")
            b_event = str(_scene_field(b, "instructional_event") or "")
            # ⛔ The hard limb owns every pair with an `assess` in it. Emitting a
            # flag beside a refusal about the same two scenes would tell a
            # reviewer two things about one sentence and leave them to work out
            # which to fix — the duplication `assess_scene` avoids by design.
            if "assess" in (a_event, b_event):
                continue
            verdict = duplication_verdict(a_text, b_text)
            if not verdict["duplicate"]:
                continue
            # ⛔ NOT `explain_duplication` HERE, AND THE REASON IS THAT ITS
            # SENTENCES SAY "the assessment". They are correct for the
            # assessment-anchored limb above and false here, where neither
            # scene need be an assessment — measured on the 12i2 acceptance
            # run, where this limb reported "the assessment restates that
            # scene" about a `guide`/`practice` pair. A shared helper whose
            # wording only fits one caller is worse than two sentences.
            same_numbers = verdict["limb"] == "no_fresh_axis"
            findings.append(Finding(
                FLAG, "SAME_OUTCOME_NEAR_DUPLICATE",
                f"scenes {a_idx} ({a_event or 'unlabelled'}) and {b_idx} "
                f"({b_event or 'unlabelled'}) both serve this outcome and "
                + (
                    "say the same thing in the same numbers, so the second "
                    "asks nothing the first did not"
                    if same_numbers else
                    "restate each other almost word for word, so the learner "
                    "meets the same question twice under two labels"
                )
                + f" (containment {verdict['containment']:.2f}). Two scenes in "
                f"one outcome's sequence asking the same question do not fade "
                f"it. Blocks nothing — deliberate repetition is a real choice, "
                f"and it is yours.",
                scene_index=a_idx,
                outcome_id=oid,
                detail={
                    "scene_indices": [a_idx, b_idx],
                    "events": [a_event, b_event],
                    "narrations": [a_text, b_text],
                    **verdict,
                },
            ))
    return findings


def _plan_is_realized(
    assessment_plan: Dict[str, Any], oid: str, scenes: Sequence[Any],
) -> List[Finding]:
    """Did a scene deliver what the plan promised for THIS outcome?

    WP-IVGS-12d, the one check this package adds. The model wrote
    ``assessment_plan`` before any scene existed (declaration order binds
    generation order — measured), so this compares a commitment against the
    design that had to keep it, rather than comparing a claim against itself.

    ⛔ THE `evidence_kind` IS MATCHED EXACTLY, not merely as a member of
    ``ASSESSING_EVENTS``. A plan promising the learner performs it UNAIDED
    (`assess`) is not kept by a guided `practice` item. The model picked the
    kind from a two-value enum; holding it to the one it picked is what makes
    the promise mean anything, and a design that changed its mind can say so by
    writing the other kind.

    ⚠ A plan entry for an outcome the operator never wrote is IGNORED here — the
    scenes cannot serve an id that does not exist, so refusing on it would
    report the same defect twice. `SCENE_CITES_UNKNOWN_OUTCOME` owns that.

    ⛔ WP-IVGS-12f MADE THIS UNREACHABLE FOR `assess`; WP-IVGS-12g MAKES IT
    UNREACHABLE FOR BOTH KINDS. The code is unchanged in both packages, on
    purpose — see the module docstring.

    ⚠ AND THE ROUTE HERE IS WORTH KEEPING IN VIEW, because it is the argument
    against the fix that was NOT taken. RC-Q9f offered three routes and two were
    refused: loosening this comparison to accept any assessing event would have
    greened the number and left LO-2's learner with no supported attempt at all
    (12d declined exactly that with the number on the record, and 12e made it a
    standing rule — evidence kinds are never collapsed to green a check); adding
    prompt emphasis after seeing the number is iterating against the metric, and
    the instruction was already there and already correct. The third route was
    to force the other kind too, and it is what contract-6 does. **The check is
    not weakened by one character.**
    """
    entry = assessment_plan.get(oid)
    if not isinstance(entry, dict):
        if assessment_plan:
            # The schema requires one entry per id, so this is the degraded
            # path — no stated outcomes, or a pre-contract-4 brief. A FLAG and
            # not a refusal: `OUTCOME_UNASSESSED` already refuses the case that
            # actually harms the learner, and refusing twice for one defect
            # makes a gate people learn to skim.
            return [Finding(
                FLAG, "ASSESSMENT_PLAN_MISSING_OUTCOME",
                "has no entry in the assessment plan, so nothing was promised "
                "for it before the scenes were designed.",
                outcome_id=oid,
            )]
        return []
    kind = entry.get("evidence_kind")
    if kind not in ASSESSING_EVENTS:
        return [Finding(
            FLAG, "ASSESSMENT_PLAN_BAD_KIND",
            f"names evidence_kind {kind!r}, which is not one of "
            f"{sorted(ASSESSING_EVENTS)}.",
            outcome_id=oid, detail={"entry": entry},
        )]
    if any(realizes(scene, oid, kind) for scene in scenes):
        return []
    return [Finding(
        REFUSE, "PLAN_ENTRY_UNREALIZED",
        f"the assessment plan promised a {kind!r} scene for this outcome — "
        f"\"{str(entry.get('learner_does') or '')[:160]}\" — and no scene "
        f"serving it declares instructional_event {kind!r}. The plan was "
        "written before the scenes; the scenes did not keep it.",
        outcome_id=oid,
        detail={"evidence_kind": kind,
                "learner_does": entry.get("learner_does"),
                "scenes_serving": sorted(
                    scene_index_of(s, i) for i, s in enumerate(scenes)
                    if oid in [str(x) for x in (_scene_field(s, "serves_outcomes") or [])]
                )},
    )]


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
            # RC-S2(a). PER-SPAN, not global. A drop's span is already merged
            # into the coverage above, so reaching this line means NO declared
            # drop covers this stretch — whatever was declared elsewhere.
            hard = gap >= HARD_GAP_CHARS
            findings.append(Finding(
                REFUSE if hard else FLAG,
                "UNDECLARED_SPAN_OVER_THRESHOLD" if hard else "UNDECLARED_SCRIPT_GAP",
                (
                    f"{gap} characters of the uploaded script are used by no "
                    f"scene and covered by no declared drop — over the "
                    f"{HARD_GAP_CHARS}-character threshold, which makes this a "
                    f"BEAT rather than connective tissue. "
                    + (
                        f"{len(dropped_beats)} beat(s) are declared dropped "
                        f"elsewhere in this design, and none of them covers "
                        f"this stretch: a drop declared somewhere else is not a "
                        f"declaration about here. "
                        if dropped_beats else
                        "`dropped_beats` is EMPTY, which claims nothing was "
                        "dropped at all. "
                    )
                    + "Use it, or declare it dropped with its span and a reason."
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
