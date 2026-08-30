"""The Design Contract — its JSON Schema, and the parse of a model's emission.

Instructional Design Foundation §6. This is the document stage 2 must produce
once it is an instructional designer rather than an excerpter.

⛔ HOW IT IS CONSTRAINED, AND WHY NOT THE WAY THE RECOVERY PLAN SAYS

The plan (§1 RC-A step 4, §4 Phase 1) prescribes vLLM ``guided_json``.
**MEASURED 2026-08-29 against the pinned engine — `vllm/vllm-openai@sha256:3dbe092e…`,
vLLM 0.19.2rc1.dev134+gfe9c3d6c5 on node-02 — `guided_json` RETURNS HTTP 200 AND
IS DISCARDED.** Output byte-identical to an unconstrained call. It returns 200
when handed ``{"type":"not_a_json_type"}``; it returns 200 when handed the bare
integer ``12345``; so does ``guided_choice``; and so does a field name invented
for the test. The engine drops unknown top-level body members without comment,
so a Design Contract built on ``guided_json`` would have been a permanent no-op
reporting success — the RC-E failure class, at the correctness core.

**What DOES enforce, measured on a nested contract with closed enums, a
``oneOf`` and ``minItems``:**

    response_format = {"type": "json_schema",
                       "json_schema": {"name": ..., "strict": True, "schema": ...}}

``structured_outputs: {"json": ...}`` measured equivalent and is the fallback.
``guided_json`` is refused by name in ``response_format_for`` so that nobody
reintroduces it from the recovery plan's text.

SCHEMA STYLE, AND WHY EVERYTHING IS "REQUIRED"

Under ``strict``, an optional key is expressed as a nullable TYPE and not as an
absent entry in ``required``. Every property is listed in ``required`` and
``additionalProperties`` is false everywhere. Two reasons, and neither is taste:
a constrained decoder builds a grammar, and a grammar with optional members is
larger and slower than one without; and a model that may omit a field will omit
the field it finds hardest, which here is always the one that matters
(``serves_outcomes`` and the provenance).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.design.evidence import derive_evidence_map
from shared.design.merge import merged_scene_sequence
from shared.models.enums import (
    ASSESSING_EVENTS,
    BLOOM_LEVELS,
    EXPOSITORY_EVENTS,
    INSTRUCTIONAL_EVENTS,
    MEDIA_TYPES,
)

#: Bumped when the SHAPE changes, not when the prompt does. Stored on the brief
#: so a reader knows which parse produced the row they are looking at.
#:
#: **-2, WP-IVGS-12b:** the model no longer emits outcome TEXT at all. It cites
#: ids that CODE assigned from `projects.learning_outcomes`, closed by a
#: per-request enum, and may only PROPOSE a refinement against one. RC-Q9.
#:
#: **-3, WP-IVGS-12c:** `evidence_map` is no longer satisfiable by an empty
#: array. Every outcome id is a REQUIRED key (measured enforced) holding
#: 1..`MAX_EVIDENCE_SCENES` scene indices, so "this outcome is assessed by
#: nothing" stops being an emittable sentence. RC-Q9b.
#:
#: **-4, WP-IVGS-12d:** backward design becomes the EMISSION ORDER. A new
#: `assessment_plan` is declared FIRST and is therefore generated before any
#: scene exists (declaration order measured to BIND — see below); and
#: `evidence_map` is GONE from the model's schema, because code derives it from
#: the scenes' own declarations. RC-Q9c.
#:
#: **-5, WP-IVGS-12f:** the excerpter is FORCED to design. `designed_assessments`
#: is a new REQUIRED top-level object with one entry per outcome, and each entry
#: is a full scene whose grammar has already pinned `origin: "designed"`,
#: `instructional_event: "assess"` and `serves_outcomes: [that outcome]`. An
#: emission that lacks an invented unaided scene per outcome is NOT PARSEABLE.
#: RC-Q9e — see `_designed_assessments_schema` for why an invitation was never
#: going to be enough.
#:
#: **-6, WP-IVGS-12g:** the evidence layer becomes STRUCTURAL, completely.
#: `designed_assessments` is replaced by TWO required per-outcome sections —
#: `assessment_scenes` (exactly one per outcome) and `practice_scenes` (one or
#: two per outcome) — and `scenes[]` loses `practice` and `assess` from its
#: `instructional_event` enum. RC-Q9f, both limbs, by grammar:
#:
#:   limb 1  a plan entry promising `practice` and never built. Contract-5
#:           forced `assess` and left `practice` to the model's follow-through,
#:           and six generations of six refused `PLAN_ENTRY_UNREALIZED` on the
#:           one outcome whose plan said `practice`. Both kinds are now forced,
#:           so there is no unforced kind left for the defect to survive in.
#:   limb 2  the duplicate. With `assess` forced elsewhere the model began
#:           writing EXTRA `assess` scenes into `scenes[]` (4 of 6 generations),
#:           and the merge placed the mandated one beside its near-identical
#:           twin. `scenes[]` cannot declare either evidence event any more, so
#:           the 117/117 excerpting contest and the duplicate both stop being
#:           emittable rather than being detected.
#:
#: ⛳ AND ORIGIN IS FREE IN BOTH SECTIONS, which is the one thing contract-5 got
#: wrong and 12f's own TASK 0 had already measured. B1 handed the model a script
#: containing an explicit unaided problem — *"Now you try. Work out 63 minus
#: 48. Pause here."* — and it found that span and anchored to it, twice. That is
#: legitimate evidence and pinning `origin: "designed"` would have forced the
#: model to invent a worse substitute and call the script's own practice
#: material absent. The grammar guarantees EXISTENCE; provenance stays honest,
#: under the same `oneOf` XOR every other scene uses.
#: **-7, WP-IVGS-12h:** THE CONTRACT IS SPLIT ACROSS TWO CALLS, and the split is
#: the shape RC-Q9g's own diagnosis dictates. Contract-6 guaranteed both evidence
#: kinds EXIST and measured what filling both slots in one emission produces: the
#: practice and the assessment for the same outcome are the SAME SCENE, written
#: twice — 9 of 15 outcome-pairs verbatim identical across five generations, 2
#: more differing only by a *"Let's practice"* prefix.
#:
#: ⛔ THE MECHANISM IS 12g's OWN ORDERING DECISION, AND THE CURE IS TO REMOVE THE
#: CONTEXT RATHER THAN TO REORDER IT. `assessment_scenes` was declared BEFORE
#: `practice_scenes`, declaration order binds generation order (12d, measured
#: both ways), so the model wrote the assessment and was then asked for a
#: practice on the same outcome WITH THE ASSESSMENT ALREADY IN ITS CONTEXT — and
#: copied it. Swapping the order would trade backward design, which 12d measured
#: and which is load-bearing, for a duplicate that would very likely just reverse
#: direction. Adding prompt emphasis was measured to do nothing: v7 already says
#: *"THE PRACTICE MUST NOT BE THE ASSESSMENT WEARING A LABEL"*, in the model's
#: own reading order, and was in place before a single acceptance generation ran.
#:
#: ⛳ SO THE CALLS SEPARATE THE KINDS AND THE SECOND CALL NEVER SEES WHAT IT MUST
#: NOT COPY:
#:
#:   CALL 1  `design_contract_schema` — everything contract-6 emitted EXCEPT
#:           `assessment_scenes`. The plan still comes first, the practice sits
#:           adjacent to the script where support naturally lives, and `scenes`
#:           keeps its narrowed seven-event enum.
#:   CALL 2  `assessment_authoring_schema` — `assessment_scenes` alone, from an
#:           input that is the OUTCOMES, the PLAN and a CODE-BUILT SUMMARY of
#:           what each outcome's practice covered. Not the practice narrations.
#:           Not `scenes`. **The model cannot copy what it never sees.**
#:
#: Both under `response_format: json_schema` with `strict: True`, the one
#: mechanism measured to enforce on this engine. `shared.design.merge` stitches
#: call 2's section into call 1's document and the placement law is unchanged.
CONTRACT_VERSION = "design-contract-7"

#: The one supported mechanism, measured. See the module docstring.
MECHANISM_JSON_SCHEMA = "json_schema"
#: Measured equivalent on the same engine; kept so a future engine that drops
#: `response_format` support has a named path rather than an improvised one.
MECHANISM_STRUCTURED_OUTPUTS = "structured_outputs"

#: WP-IVGS-12h. Numerals, for `practice_summary` — the one axis 12g measured
#: the model to differentiate on when it exists, and to collapse without.
_NUMERAL_RE = re.compile(r"\d+(?:\.\d+)?")

# ⛔ EVERY ARRAY IN THIS SCHEMA CARRIES A `maxItems`, AND IT IS NOT TIDINESS.
#
# MEASURED 2026-08-29 against the pinned engine: an array with `minItems` and NO
# maximum gives grammar-constrained decoding an infinite LEGAL continuation, and
# the model takes it — `"serves_outcomes": ["LO-1", "LO-3", "LO-3", "LO-3", …]`
# until the token budget dies, `finish_reason=length`, nothing parseable. The
# enum was honoured perfectly the whole time; membership was never the problem.
# `maxItems` IS compiled into the grammar (measured, on string-enum arrays and
# object arrays alike) and it stops it dead.
#
# ⚠ `uniqueItems` IS NOT: the engine answers HTTP 400
# `Grammar error: Unimplemented keys: ["uniqueItems"]`. ⛳ Note the CONTRAST with
# `guided_json`, which it accepts with 200 and discards — an unimplemented
# GRAMMAR key is refused loudly, an unknown BODY member is dropped silently.
# Two failure modes, one engine, and only one of them tells you.
MAX_SCENES = 40
MAX_SOURCE_REFS_PER_SCENE = 8
MAX_DROPPED_BEATS = 40

# ⛔ WP-IVGS-12c. `evidence_map[LO-x]` is bounded 1..4 and the LOWER bound is the
# load-bearing one: RC-Q9b is the designer serving an outcome and assessing it
# with nothing, and `[]` was the legal way to say so. It is no longer legal.
#
# MEASURED 2026-08-29 on the pinned engine before this was written — the whole
# construct, under a prompt ORDERING every part of it broken, because a schema
# the model had no wish to break proves nothing:
#
#   per-request REQUIRED keys  ✅ ENFORCED. Ordered to emit 'LO-1' only and to
#                                 omit 'LO-2' and 'LO-3' entirely, it emitted
#                                 all three.
#   additionalProperties:false ✅ ENFORCED. Ordered to add 'LO-9', it did not.
#   minItems+maxItems together ⚠  ENFORCED, AND IT CAN HANG — see below.
#   `contains`                 ⛔ HTTP 400 `Grammar error: Unimplemented keys:
#                                 ["contains"]`, exactly like `uniqueItems`.
#
# ⚠ THE HANG, AND WHY THE BOUND SHIPS ANYWAY. Ordered in the prompt to emit
# `[]`, the decoder forbade the `]` and the model took the only other legal
# continuation — WHITESPACE, 5,243 characters of it, to the token limit,
# `finish_reason=length`. `maxItems` bounds the ELEMENTS; nothing bounds the
# whitespace between `[` and the first one. RC-Q12's runaway in a shape
# `maxItems` does not close.
#
# It ships because the corridor is only reachable when the model's next token
# would be `]`, and two further probes measured that it does not go there under
# honest pressure: told plainly that the lesson was demonstration-only and
# assessed nothing, it filled the map (`{"LO-1":[0,1,2,3],"LO-2":[2],"LO-3":[4]}`)
# rather than hang. And when it IS reached, WP-37's `finish_reason` check raises
# `VLLMTruncatedResponseError` BEFORE the parse, naming the token limit — a loud
# failure, not a silent one.
#
# ⛳ AND NOTE WHAT THE SAME PROBE PROVED ABOUT THE LIMIT OF ALL THIS: in that
# demonstration-only run the model's own `design_notes` said the lesson "does
# not include any practice or assessment items" WHILE its `evidence_map` named
# scenes. Structure can force the claim to exist. It cannot make the claim true
# — which is what `EVIDENCE_MAP_DISAGREES` is for, and past that, the reviewer.
MIN_EVIDENCE_SCENES = 1
MAX_EVIDENCE_SCENES = 4

#: How much room the model gets to say what the learner will DO to prove one
#: outcome. Bounded because every string in a grammar-constrained emission is a
#: place the decoder can run, and `maxLength` is the string-shaped `maxItems`.
MAX_LEARNER_DOES_CHARS = 300

#: WP-IVGS-12f. The same bound, for the one sentence a designed scene gives on
#: what the script lacked.
#:
#: ⛳ WP-IVGS-12g CLOSES 12f's NAMED RESIDUE HERE, and the reason it is in scope
#: now is the reason it was out of scope then. 12f left the `rationale` on the
#: `scenes` oneOf's `designed` branch UNBOUNDED because that branch was
#: untouched contract-4 surface and widening a package's blast radius to tidy a
#: string is how a contract acquires a second variable. Contract-6 routes EVERY
#: evidence scene's provenance through that same `oneOf` — origin is free in
#: both sections — so the branch is now load-bearing in the one place a runaway
#: would cost a whole generation, and an unbounded string in a
#: grammar-constrained emission is exactly RC-Q12's shape one type along.
MAX_DESIGNED_RATIONALE_CHARS = 300

#: ⛔ WP-IVGS-12g. THE EVIDENCE SECTIONS' BOUNDS. Asymmetric on purpose, and the
#: asymmetry is Foundation §2: exactly ONE independent attempt per outcome
#: (two is RC-Q9f limb 2, the duplicate), but ONE OR TWO supported attempts,
#: because a complete worked example followed by a faded one is the fading
#: sequence and a ceiling of 1 would forbid it.
ASSESSMENT_SCENES_PER_OUTCOME = 1
MIN_PRACTICE_SCENES_PER_OUTCOME = 1
MAX_PRACTICE_SCENES_PER_OUTCOME = 2

# ⛔ WP-IVGS-12d. SCHEMA DECLARATION ORDER BINDS GENERATION ORDER — MEASURED,
# IN BOTH DIRECTIONS, AGAINST AN EXPLICIT PROMPT INSTRUCTION TO DO OTHERWISE.
#
# This is the whole foundation of `assessment_plan`. Foundation §1 says decide
# the evidence BEFORE designing instruction; that is only true of the model if
# the decoder makes it true, because a plan the model may write last is a plan
# it rationalises from scenes it has already designed.
#
#   A  properties [plan, scenes], prompt DEMANDS scenes first -> emitted PLAN first
#   B  properties [scenes, plan], prompt DEMANDS plan   first -> emitted SCENES first
#   C  properties [scenes, plan] with required [plan, scenes] -> emitted SCENES first
#
# A and B disagree with the prompt in OPPOSITE directions, so the result is the
# grammar and not the model's own preference for writing scenes first — which is
# the confound 12c's observation could not exclude. C settles which list rules:
# **`properties` order controls; `required` order does not.** That retroactively
# explains 12c, where `outcome_notes` was first in `required` and emitted LAST.
#
# ⚠ SO THE ORDER OF THE `properties` DICT BELOW IS LOAD-BEARING AND IS NOT
# STYLE. Moving `assessment_plan` down this file silently converts a commitment
# into a rationalisation, and nothing in a test that only checks membership
# would notice. `test_wpivgs12d_assessment_plan` asserts the position.
PLAN_IS_DECLARED_FIRST = "assessment_plan"


def _nullable(*types: str) -> List[str]:
    return [*types, "null"]


def _span_schema() -> Dict[str, Any]:
    """A character span of ``transcripts.source_text``.

    ⛔ OF ``source_text``, NOT ``refined_text``. Stage 1 PATCHes its paraphrase
    over ``refined_text`` (``stage1_transcript.py:241``), so an offset measured
    against that column indexes into a string that changes between the write and
    the read. Migration 0046 exists for this.
    """
    return {
        "type": "object",
        "properties": {
            "transcript_id": {"type": _nullable("string")},
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 0},
            "quote": {
                "type": "string",
                "description": (
                    "The exact text at [start, end). Carried so a reader can "
                    "check the offsets without the transcript, and so a "
                    "mis-counted span is visible rather than silent."
                ),
            },
        },
        "required": ["transcript_id", "start", "end", "quote"],
        "additionalProperties": False,
    }


def _outcome_notes_schema(outcome_ids: Sequence[str]) -> Dict[str, Any]:
    """What the model may say ABOUT an outcome — never what the outcome IS.

    ⛔ THE OUTCOME TEXT IS NOT IN THIS SCHEMA AND THAT IS THE WHOLE POINT.
    RC-Q9: asked to transcribe three ABCD outcomes, the model returned two,
    reworded, three times running, and marked them measurable. No prompt fixed
    it and no schema could, because a paraphrase is a valid string. So the text
    is injected server-side from `projects.learning_outcomes` and the model gets
    the ids only.

    An OBJECT keyed by the real ids rather than an array of {id, …}: `required`
    then forces exactly one entry per outcome and `additionalProperties: false`
    forbids an invented one. An array would let the model emit two entries for
    LO-1 and none for LO-3 — which is the failure being removed, in a new hat.

    Foundation §2 survives intact (ruling 1c): an unmeasurable outcome still
    gets an ABCD refinement PROPOSED for approval. It is proposed AGAINST an id,
    beside text the model never touched, so the gate can show the operator's
    words and the proposal side by side and the operator decides.
    """
    per_outcome = {
        "type": "object",
        "properties": {
            "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
            "measurable": {
                "type": "boolean",
                "description": (
                    "Does the OPERATOR's own wording state an observable "
                    "behaviour? You are judging their text, not writing it."
                ),
            },
            "proposed_refinement": {
                "type": _nullable("string"),
                "description": (
                    "An ABCD rewrite PROPOSED for the operator to approve when "
                    "`measurable` is false — Audience, Behavior, Condition, "
                    "Degree. Null when it is already measurable. It is NEVER "
                    "applied; the design is made against the operator's words "
                    "as they stand."
                ),
            },
        },
        "required": ["bloom_level", "measurable", "proposed_refinement"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {oid: per_outcome for oid in outcome_ids},
        "required": list(outcome_ids),
        "additionalProperties": False,
    }


def _assessment_plan_schema(outcome_ids: Sequence[str]) -> Dict[str, Any]:
    """Foundation §1 stage 2, made into a thing the model must write FIRST.

    ⛔ THIS IS DECLARED BEFORE `scenes` AND THAT IS THE ENTIRE POINT. Declaration
    order binds generation order on the pinned engine (measured, both
    directions), so every token of this object is produced while the scene list
    is still empty. The model commits to what would PROVE each outcome before it
    has a lesson to rationalise from.

    RC-Q9c is why. Asked for the evidence AFTER the scenes, the model wrote
    plausible scene indices that its own scenes contradicted, three generations
    running. Asked BEFORE, it has nothing to point at and must say what the
    learner will DO — and `design_review` then checks the design against that
    promise instead of checking a claim against itself.

    Per-outcome REQUIRED keys with `additionalProperties: false` is the
    construct measured ENFORCED in 12c, reused rather than re-invented.
    """
    entry = {
        "type": "object",
        "properties": {
            "evidence_kind": {
                "type": "string",
                "enum": sorted(ASSESSING_EVENTS),
                "description": (
                    "`practice` — the learner attempts it with support; "
                    "`assess` — the learner performs it first, unaided. Pick "
                    "the one you will actually build a scene for: a scene "
                    "declaring THIS event and serving THIS outcome must exist, "
                    "and the gate refuses the design when it does not."
                ),
            },
            "learner_does": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_LEARNER_DOES_CHARS,
                "description": (
                    "One sentence, concrete: what the LEARNER does that would "
                    "prove this outcome. 'Multiplies 34 by 21 unaided and "
                    "checks the placeholder zero', not 'understands "
                    "multiplication'. You are writing the assessment before "
                    "the lesson, which is the order this works in."
                ),
            },
        },
        "required": ["evidence_kind", "learner_does"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {oid: dict(entry) for oid in outcome_ids},
        "required": list(outcome_ids),
        "additionalProperties": False,
        "description": (
            "BEFORE YOU DESIGN ANY SCENE: for each outcome, what will the "
            "learner DO to prove it? One entry per outcome id, no exceptions. "
            "Every entry must then be realized by a scene that serves that "
            "outcome and declares that exact instructional_event."
        ),
    }


def _evidence_scene_schema(
    oid: str, *, event: str, media_types: Tuple[str, ...],
) -> Dict[str, Any]:
    """ONE evidence scene for ONE outcome, of ONE kind — a full scene object.

    ⛔ WP-IVGS-12g. TWO fields are not decisions the model makes, and the third
    one contract-5 pinned is GIVEN BACK:

        instructional_event  enum [event]     the section IS the kind
        serves_outcomes      [enum [oid]]     one outcome, the one it proves
        provenance           the ordinary XOR — ORIGIN IS FREE

    ⛳ WHY ORIGIN IS FREE, WHICH IS 12g's ONE REVERSAL OF 12f. Contract-5 pinned
    `origin: "designed"` because the measured defect was total refusal to invent
    (0 designed scenes in 83). But 12f's own TASK 0 measured the other half and
    12f did not act on it: script B1 contained an EXPLICIT unaided problem —
    *"Now you try. … Work out 63 minus 48. Pause here. Do not read on yet."* —
    and the model found that span and anchored to it in both runs. That is a
    real practice item written by a real teacher, and a grammar pinning
    `designed` would force the model to invent a substitute for it AND to write
    a rationale asserting the script lacked what the script plainly contains.
    The invention defect was never about provenance; it was about COMPETITION
    inside one array, and the section removes the competition on its own.

    So: the grammar guarantees the scene EXISTS. The model still says honestly
    where it came from, under the same `oneOf` every other scene uses, and the
    same CHECK constraint (migration 0048) holds it at the database.

    ⛔ AND THERE IS NO `scene_index`, for the third package running. Placement is
    `shared.design.merge`'s — practice after the last `present`/`guide` serving
    the outcome, the assessment after that outcome's practice. 12b's principle:
    never ask the model for what code can compute.
    """
    assessing = event == "assess"
    return {
        "type": "object",
        "properties": {
            # First, because generation order follows declaration order (12d):
            # the model settles where this scene comes from BEFORE writing it.
            "provenance": {
                "oneOf": _provenance_branches(),
                "description": (
                    "Where this evidence scene comes from, and it is a real "
                    "choice. `sourced` with spans when the script genuinely "
                    "hands you the learner's own attempt — an explicit \"now "
                    "you try\", a problem left for the reader. `designed` with "
                    "a rationale otherwise, which is the usual case: most "
                    "scripts contain the teacher performing and never the "
                    "learner. Do not claim a span you did not use, and do not "
                    "invent a replacement for material the script already has."
                ),
            },
            "instructional_event": {"type": "string", "enum": [event]},
            "serves_outcomes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {"type": "string", "enum": [oid]},
                "description": (
                    f"This scene {'assesses' if assessing else 'practises'} "
                    f"{oid} and nothing else."
                ),
            },
            "narration_text": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "POSE the problem cold, in FRESH NUMBERS the script never "
                    "worked, then HOLD, then REVEAL for self-check. Do not "
                    "narrate the method, do not give the first step, and do "
                    "not restate the script's own worked answer. If the "
                    "learner could follow along without thinking, you have "
                    "written a `guide` and put an `assess` label on it."
                ) if assessing else (
                    "The learner attempts it WITH SUPPORT STILL ON SCREEN — a "
                    "faded worked example with one step left blank, a "
                    "prompt-then-confirm, a step they supply while the rest of "
                    "the working stays visible. This is the MIDDLE of the "
                    "fading sequence, not the end: if nothing is left on "
                    "screen to lean on you have written the assessment twice."
                ),
            },
            "visual_description": {"type": "string", "minLength": 1},
            "media_type": {"type": "string", "enum": list(media_types)},
            "media_rationale": {
                "type": "string",
                "description": (
                    "Which row of the modality table this scene sits in. A "
                    "computational attempt is `motion_graphics` and MUST carry "
                    "a template in `generation_params`; an explain-it or "
                    "check-your-own-work attempt is `image` or `talking_head`, "
                    "because the renderer has no template for it and a motion "
                    "scene without one is refused."
                ),
            },
            "duration_seconds": {
                "type": "number", "minimum": 3, "maximum": 120,
                "description": (
                    "Long enough to pose, hold and reveal in ONE scene. The "
                    "hold is the part that makes it unaided; a three-second "
                    "assess has no hold in it."
                ) if assessing else (
                    "Long enough to show the supported attempt and confirm it."
                ),
            },
            "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
            "text_carried_by": {
                "type": _nullable("string"), "enum": ["narration", None],
            },
            "generation_params": {
                "type": _nullable("object"),
                "description": (
                    "REQUIRED when media_type is motion_graphics: the template "
                    "name and its parameters FLAT alongside it. The numbers "
                    "here are the ones YOU posed, not the script's."
                ),
            },
            "signal_spec": {"type": _nullable("object")},
        },
        "required": [
            "provenance", "instructional_event", "serves_outcomes",
            "narration_text", "visual_description", "media_type",
            "media_rationale", "duration_seconds", "bloom_level",
            "text_carried_by", "generation_params", "signal_spec",
        ],
        "additionalProperties": False,
    }


def _evidence_section_schema(
    outcome_ids: Sequence[str],
    *,
    event: str,
    media_types: Tuple[str, ...],
    min_items: int,
    max_items: int,
    description: str,
) -> Dict[str, Any]:
    """One REQUIRED key per outcome, each holding a bounded array of scenes.

    ⛔ WP-IVGS-12g. THIS IS THE WHOLE PACKAGE. Contract-5 proved the shape works
    for `assess`: 0 designed scenes in 83 became 10 in 43, and
    `OUTCOME_UNASSESSED` stopped being able to fire. It also proved the shape's
    boundary — the ONE evidence kind left inside `scenes[]` kept failing exactly
    as it always had (RC-Q9f: six generations, six `PLAN_ENTRY_UNREALIZED`
    refusals on a promised `practice`). The measured law across four packages is
    that the model's plan predicts nothing and only the grammar is causal, so
    12g applies it ONCE, to the whole evidence layer, instead of chasing it kind
    by kind.

    ⚠ THE BOUNDS, AND THE ONE THAT IS NOT SYMMETRIC. `assessment_scenes` is
    exactly one per outcome: an outcome assessed twice is RC-Q9f limb 2, the
    duplicate-posing defect this package exists to make unemittable, and there
    is no design in which two independent attempts at one outcome is the right
    answer at this scale. `practice_scenes` is one or TWO, because Foundation §2
    fades in steps — a complete worked example and then a faded one are two
    supported attempts and a legitimate pair — and because a ceiling equal to
    its floor everywhere would forbid the fading sequence the same Foundation
    section prescribes.

    ⚠ AND THE CORRIDOR WAS MEASURED BEFORE THIS SHIPPED (RC-Q12). 12c measured a
    `minItems` array HANG: ordered to emit `[]`, the decoder forbade the `]` and
    the model emitted 5,243 characters of whitespace to the token limit. Both
    shapes here were probed on the pinned engine under a prompt ORDERING the
    array empty — `minItems=maxItems=1` and `minItems=1,maxItems=2`, over
    OBJECTS rather than 12f probe D's single-token strings — and neither hung:
    one element, `finish_reason=stop`, both times. Banked at
    `wpivgs12g-evidence/probe12g.json`.
    """
    per_outcome = {
        oid: {
            "type": "array",
            "minItems": min_items,
            "maxItems": max_items,
            "items": _evidence_scene_schema(
                oid, event=event, media_types=media_types,
            ),
        }
        for oid in outcome_ids
    }
    return {
        "type": "object",
        "properties": per_outcome,
        "required": list(outcome_ids),
        "additionalProperties": False,
        "description": description,
    }


def _provenance_branches() -> List[Dict[str, Any]]:
    """Foundation §6's ``source_refs[] XOR origin:"designed"``, as a ``oneOf``.

    A ``oneOf`` and not two optional keys: the exclusivity is the contract. The
    same exclusivity is a CHECK constraint in migration 0048, so it holds even
    for a scene that reaches the table by some path other than this one.
    """
    return [
        {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "enum": ["sourced"]},
                "source_refs": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_SOURCE_REFS_PER_SCENE,
                    "items": _span_schema(),
                    "description": "Spans of the uploaded script this scene works from.",
                },
                "rewrite_of": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "properties": {
                                "span": _span_schema(),
                                "original": {
                                    "type": "string",
                                    "description": "The script's own wording, carried so the gate can diff it.",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Why the design required this rewording.",
                                },
                            },
                            "required": ["span", "original", "reason"],
                            "additionalProperties": False,
                        },
                    ],
                    "description": (
                        "MANDATORY when the narration is not the script's own "
                        "words. Ruling R1a: rewriting is permitted, silence is "
                        "not. Null only when the narration is verbatim."
                    ),
                },
            },
            "required": ["origin", "source_refs", "rewrite_of"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "enum": ["designed"]},
                "rationale": {
                    "type": "string",
                    # ⛳ BOUNDED BY WP-IVGS-12g. See MAX_DESIGNED_RATIONALE_CHARS
                    # — contract-6 makes this branch the provenance of every
                    # evidence scene, so 12f's deliberate residue became
                    # load-bearing and is closed rather than re-declared.
                    "minLength": 1,
                    "maxLength": MAX_DESIGNED_RATIONALE_CHARS,
                    "description": (
                        "What the integrated intent required that the script "
                        "lacked. Designed material is legitimate and expected; "
                        "undeclared designed material is not."
                    ),
                },
            },
            "required": ["origin", "rationale"],
            "additionalProperties": False,
        },
    ]


def _scene_schema(
    *, media_types: Tuple[str, ...], outcome_ids: Sequence[str],
) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            # ── the five that already exist and keep their exact semantics ──
            "scene_index": {"type": "integer", "minimum": 0},
            "narration_text": {"type": "string", "minLength": 1},
            "visual_description": {"type": "string", "minLength": 1},
            "media_type": {"type": "string", "enum": list(media_types)},
            "duration_seconds": {"type": "number", "minimum": 3, "maximum": 120},
            # ── v7's per-scene content contract (0045), unchanged ──
            "media_rationale": {
                "type": "string",
                "description": (
                    "One line: why THIS medium for THIS scene, naming the row "
                    "of the modality decision table. This IS Foundation §6's "
                    "`modality_rationale`; v7 RULE 9 created it first and it "
                    "keeps its name so there is one column, not two."
                ),
            },
            "text_carried_by": {
                "type": _nullable("string"),
                "enum": ["narration", None],
                "description": (
                    "RULE 1-EXTENDED. 'narration' when written or numeric "
                    "content is spoken while the visual depicts the situation. "
                    "Null otherwise."
                ),
            },
            "generation_params": {
                "type": _nullable("object"),
                "description": (
                    "REQUIRED when media_type is motion_graphics. The template "
                    "name and its parameters FLAT alongside it, e.g. "
                    "{\"template\": \"column_multiplication_step\", \"top\": 23, "
                    "\"bottom\": 14, \"phase\": \"start\"} — NOT nested under a "
                    "\"params\" key. The renderer draws digits in a real font; "
                    "diffusion invents them."
                ),
            },
            # ── the Design Contract proper ──
            # ⛔ WP-IVGS-12g. NARROWED — SEVEN EVENTS, NOT NINE. `practice` and
            # `assess` are gone from this enum and live only in the evidence
            # sections. This array is the EXPOSITORY arc.
            #
            # It is the same per-request-enum construct 12b measured ENFORCED on
            # `serves_outcomes` and 12g re-measured on THIS field before
            # shipping it — a narrowed set is a claim about shrinking a
            # vocabulary, not about closing one, and the probe ordered the model
            # to emit `practice` and `assess` here and it could not
            # (`wpivgs12g-evidence/probe12g.json`, A1 and A2).
            #
            # Two defects die on this line. The 117/117 excerpting contest, in
            # which anything the script could supply out-competed an invented
            # scene for the same slot — there is no shared slot left. And RC-Q9f
            # limb 2, the duplicate: contract-5 taught the model the shape of an
            # authored assessment and it began writing a second one here, which
            # the merge then placed beside its twin.
            "instructional_event": {
                "type": "string",
                "enum": list(EXPOSITORY_EVENTS),
                "description": (
                    "Gagné, Foundation §3. The job this scene performs. These "
                    "seven are the TEACHING events. `practice` and `assess` are "
                    "not available here and are not missing: you author them in "
                    "`practice_scenes` and `assessment_scenes`, one entry per "
                    "outcome, and code places them into this arc for you."
                ),
            },
            "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
            "serves_outcomes": {
                "type": "array",
                "minItems": 1,
                "maxItems": max(1, len(outcome_ids)),
                "items": {"type": "string", "enum": list(outcome_ids)},
                "description": (
                    "Outcome ids, from the closed set above and no other. A "
                    "scene that serves nothing is decoration and is cut — "
                    "Foundation §1's alignment triad."
                ),
            },
            "provenance": {"oneOf": _provenance_branches()},
            "signal_spec": {
                "type": _nullable("object"),
                "description": (
                    "Optional. Mayer signalling: what to highlight and at which "
                    "narrated word. {highlight, at_word}."
                ),
            },
        },
        "required": [
            "scene_index", "narration_text", "visual_description", "media_type",
            "duration_seconds", "media_rationale", "text_carried_by",
            "generation_params", "instructional_event", "bloom_level",
            "serves_outcomes", "provenance", "signal_spec",
        ],
        "additionalProperties": False,
    }


def design_contract_schema(
    *,
    outcome_ids: Optional[Sequence[str]] = None,
    media_types: Optional[Tuple[str, ...]] = None,
    min_scenes: int = 2,
) -> Dict[str, Any]:
    """The whole contract, built PER REQUEST from this project's outcome ids.

    ``outcome_ids`` come from `shared.design.outcomes.parse_outcomes` over
    `projects.learning_outcomes` — never from the model. They close
    `serves_outcomes`, `evidence_map` and `outcome_notes`, so a scene cannot
    cite an outcome that does not exist and no outcome can be left unmentioned.

    ⚠ A per-request enum differs on every call and so cannot ride any cached
    grammar. **Measured enforced** on the pinned engine before this was built:
    given ids [LO-1] and told in the prompt to serve LO-1, LO-2 and LO-3, the
    model emitted LO-1 only.

    With no ids — a project whose operator wrote no outcomes — the enum would be
    empty and the grammar unsatisfiable, so the contract degrades to an open
    string and the gate says the outcomes were never stated.
    """
    ids = list(outcome_ids or [])
    scene = _scene_schema(
        media_types=tuple(media_types or MEDIA_TYPES), outcome_ids=ids,
    )
    if not ids:
        # No closed set to enforce. Keep the field, drop the enum, keep a bound.
        scene["properties"]["serves_outcomes"] = {
            "type": "array", "minItems": 1, "maxItems": 8,
            "items": {"type": "string"},
        }

    # ⛔ THE ORDER OF THIS DICT IS THE CONTRACT, NOT THE FORMATTING.
    # `properties` order binds generation order (measured, WP-IVGS-12d), so
    # `assessment_plan` sitting at the top is what makes it a COMMITMENT rather
    # than a rationalisation. Do not reorder for tidiness.
    properties: Dict[str, Any] = {
        "scenes": {
            "type": "array",
            "minItems": min_scenes,
            "maxItems": MAX_SCENES,
            "items": scene,
        },
        "dropped_beats": {
            "type": "array",
            "maxItems": MAX_DROPPED_BEATS,
            "items": {
                "type": "object",
                "properties": {
                    "span": _span_schema(),
                    "summary": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["span", "summary", "reason"],
                "additionalProperties": False,
            },
            "description": (
                "Every stretch of the script that no scene uses. Dropping is a "
                "design decision; SILENT loss is the defect class this contract "
                "exists to remove. An empty array is a CLAIM that you used "
                "everything, and the gate measures the script against your "
                "spans and HARD-REFUSES that claim when it is false."
            ),
        },
        "design_notes": {
            "type": "string",
            "description": "One short paragraph: the arc, and why it is this arc.",
        },
    }
    required = ["scenes", "dropped_beats", "design_notes"]

    if ids:
        properties["outcome_notes"] = _outcome_notes_schema(ids)
        required.insert(0, "outcome_notes")
        # ⛔ WP-IVGS-12d. REBUILT SO `assessment_plan` IS THE FIRST PROPERTY.
        # A dict preserves insertion order and `properties` order is what the
        # decoder follows, so this rebuild — not a mutation of the existing
        # dict — is what puts the plan ahead of `scenes` in the emission.
        #
        # ⛔ WP-IVGS-12g: THE ORDER IS BACKWARD DESIGN, COMPLETE — and it is
        # `assessment_scenes` BEFORE `practice_scenes` before `scenes`, which
        # reads backwards on the page and is exactly right.
        #
        # Declaration order binds generation order (12d, measured in both
        # directions against a prompt ordering otherwise), so this dict is the
        # sequence the model actually thinks in:
        #
        #   assessment_plan     what would PROVE each outcome        (12d)
        #   assessment_scenes   the independent attempt, written     (12f, whole)
        #   practice_scenes     the supported attempt that leads to it   (12g)
        #   scenes              only now, the exposition that prepares both
        #
        # The model writes the END of every outcome's fading sequence while the
        # scene list is STILL EMPTY, then the middle, then the beginning. It has
        # no worked example of its own to lift numbers out of when it poses the
        # assessment — which is the exact degeneracy the acceptance checks by
        # hand — and it writes the supported attempt knowing what it must fade
        # TOWARD. Foundation §1 in full: outcomes, evidence, then instruction.
        mt = tuple(media_types or MEDIA_TYPES)
        properties = {
            "assessment_plan": _assessment_plan_schema(ids),
            # ⛔ WP-IVGS-12h. `assessment_scenes` IS NOT HERE ANY MORE AND ITS
            # ABSENCE IS THE PACKAGE. It is authored by a SECOND call against
            # `assessment_authoring_schema`, from an input that carries the
            # outcomes, the plan and a code-built summary of the practice — and
            # not one word of the practice narrations themselves. See
            # CONTRACT_VERSION's -7 note for the measurement that forced it.
            #
            # ⛳ AND BACKWARD DESIGN SURVIVES THE SPLIT, WHICH IS THE THING THAT
            # HAD TO BE PROTECTED. The plan is still this schema's FIRST
            # property, so the model still commits to what would prove each
            # outcome before a scene exists (12d, measured in both directions).
            # What moved is only WHERE the independent attempt gets written, and
            # it is written from that same plan — call 2 receives the plan
            # verbatim, so the promise the model made at the top of call 1 is
            # the brief call 2 answers.
            "practice_scenes": _evidence_section_schema(
                ids, event="practice", media_types=mt,
                min_items=MIN_PRACTICE_SCENES_PER_OUTCOME,
                max_items=MAX_PRACTICE_SCENES_PER_OUTCOME,
                description=(
                    "THE SUPPORTED ATTEMPT, ONE OR TWO PER OUTCOME, AND THERE "
                    "IS NO KEY YOU CAN LEAVE OUT. The learner attempts it with "
                    "the scaffolding still on screen — a faded worked example "
                    "with one step left blank, a prompt-then-confirm. Two when "
                    "the fading needs a step between the complete worked "
                    "example and the independent one. You do NOT place these "
                    "either: each is inserted after the last scene that "
                    "presents or guides its outcome. You are NOT writing the "
                    "unaided attempt here and you are not asked to: it is "
                    "authored separately, from your plan, and it will be placed "
                    "immediately after this scene. Leave the support ON."
                ),
            ),
            **properties,
        }
        required.insert(0, "practice_scenes")
        required.insert(0, "assessment_plan")
    # With no ids there is no plan to require: the operator stated no outcomes,
    # so there is nothing to promise evidence FOR — and nothing to force
    # evidence OF, so BOTH evidence sections are absent on this path too
    # (WP-IVGS-12f, extended by 12g). An empty required-key object would be a
    # grammar demanding a key set that does not exist. `design_review` says the
    # outcomes were never stated and carries the whole weight on that path.
    #
    # ⚠ AND `scenes[]` KEEPS ITS NARROWED ENUM EVEN HERE. Without outcome ids
    # there is no evidence layer, so a design on this path cannot reach
    # `practice` or `assess` at all and `MERRILL_NO_APPLICATION` flags every one
    # of them. That is the honest report of a project whose owner wrote no
    # outcomes: it is a lecture, because nothing said what it should assess.
    # Widening the enum back for this path would let the model label an
    # assessment it was never asked to serve anything with.

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def assessment_authoring_schema(
    *,
    outcome_ids: Sequence[str],
    media_types: Optional[Tuple[str, ...]] = None,
) -> Dict[str, Any]:
    """CALL 2. The independent attempts, and NOTHING else. WP-IVGS-12h.

    ⛔ ONE TOP-LEVEL PROPERTY, AND THE NARROWNESS IS THE POINT. The whole reason
    this call exists is that the model, holding a practice scene in context, was
    measured to write it out again as the assessment. A second call that carried
    `scenes`, or the practice narrations, or a `design_notes` field inviting it
    to reflect on the lesson, would hand back the context the split removes. So
    the emission is `assessment_scenes` and there is nothing else to emit.

    ⛳ THE GRAMMAR IS CONTRACT-6's, UNCHANGED, DELIBERATELY. `_evidence_section_schema`
    with `event="assess"` and bounds 1..1 is the same construct probed ENFORCED
    in 12g (probes B1/B2/D) and shipped for a package; reusing it means this
    package's new surface is the CALL, not the shape, and a difference measured
    between contract-6 and contract-7 assessments is a difference in what the
    model could SEE and not in what it was allowed to write.

      instructional_event  enum ["assess"]   the section IS the kind
      serves_outcomes      [enum [oid]]      one outcome, the one it proves
      provenance           the ordinary XOR  — ORIGIN IS FREE (12g's reversal)
      no `scene_index`     placement is `shared.design.merge`'s, after the
                           outcome's practice, exactly as before

    ⚠ ORIGIN STAYS FREE EVEN THOUGH CALL 2 CANNOT SEE THE SCRIPT, and that is not
    an oversight. B1 measured the model finding a real *"Now you try… Work out 63
    minus 48"* span and anchoring to it, which is legitimate evidence; pinning
    `designed` would force an invented substitute. Call 2 will USUALLY answer
    `designed` because it has no spans in front of it — but a pin is a claim
    about what is TRUE, not about what is convenient, and `sourced` with a span
    it cannot support is caught by migration 0048's CHECK and by the gate's
    `UNDECLARED_ORIGIN` path rather than by a grammar that forbids honesty.
    ⛳ Whether it in fact stops answering `sourced` is a MEASUREMENT this package
    takes, not an assumption it makes: the acceptance reports the origin split.
    """
    ids = [str(o) for o in outcome_ids]
    if not ids:
        # No outcomes means no assessments to author and no enum to close. The
        # caller must not make this call at all; returning an unsatisfiable
        # grammar would be worse than saying so.
        raise ValueError(
            "assessment_authoring_schema requires at least one outcome id; a "
            "project whose operator stated no outcomes has no second call."
        )
    mt = tuple(media_types or MEDIA_TYPES)
    return {
        "type": "object",
        "properties": {
            "assessment_scenes": _evidence_section_schema(
                ids, event="assess", media_types=mt,
                min_items=ASSESSMENT_SCENES_PER_OUTCOME,
                max_items=ASSESSMENT_SCENES_PER_OUTCOME,
                description=(
                    "THE INDEPENDENT ATTEMPT, ONE PER OUTCOME, AND THERE IS NO "
                    "KEY YOU CAN LEAVE OUT. Exactly one scene each: the learner "
                    "performs the outcome UNAIDED. You have been given the "
                    "outcomes, the evidence plan you wrote, and a factual "
                    "summary of what each outcome's supported practice already "
                    "covered — the numbers it used and how far it took the "
                    "learner. You have NOT been given the practice wording and "
                    "you do not need it: your job is to write the attempt that "
                    "comes AFTER it. Pose the problem cold, in numbers this "
                    "lesson has not worked, hold while the learner attempts it, "
                    "then reveal so they can mark their own work. You do NOT "
                    "place these — each is inserted immediately after its "
                    "outcome's practice."
                ),
            ),
        },
        "required": ["assessment_scenes"],
        "additionalProperties": False,
    }


#: WP-IVGS-12h. How many numerals the practice summary carries per outcome.
#: Bounded for the same reason every array in this file is (RC-Q12), and small
#: because the summary is a fact sheet and not a transcript: its purpose is to
#: tell call 2 which numbers are SPENT, and a long tail of them would start to
#: reconstruct the narration this split exists to withhold.
MAX_SUMMARY_NUMERALS = 12


def practice_summary(
    raw_contract: Any, outcome_ids: Sequence[str],
) -> Dict[str, Any]:
    """CALL 2's input, BUILT BY CODE from call 1's document. WP-IVGS-12h.

    ⛔ THIS FUNCTION IS THE SPLIT. Everything call 2 knows about the lesson comes
    through here, so what it does NOT return matters more than what it does:

        NOT the practice narrations      the string that was copied, five
                                         generations running
        NOT the worked-example narrations the script's own numbers, restated
                                         with a practice label (12g run A gen 2)
        NOT `scenes`                     the expository arc, which is where the
                                         model found everything it anchored to

    What it DOES return is a fact sheet per outcome — what the practice covered,
    stated as data rather than as prose:

        numbers_used    every numeral the practice narration and its
                        `generation_params` contain. This is the AXIS. 12g
                        measured the mechanism exactly: *"where a FRESH NUMBER
                        exists as an axis, the model differentiates; where the
                        outcome is 'explain why' or 'check your work', it has no
                        axis and writes the same sentence twice."* Telling call 2
                        which numbers are spent is the smallest possible input
                        that lets it differentiate, and it cannot be copied as a
                        sentence because it is a list of digits.
        step_reached    how far the supported attempt took the learner: the
                        template and phase the motion renderer was given, the
                        Bloom level, how many practice scenes there were, and
                        their total on-screen seconds.
        media_type      so the assessment can choose its own modality knowingly.

    ⛳ AND ONE LESSON-WIDE FIELD, `numbers_already_used`, WHICH GOES BEYOND THE
    PER-OUTCOME SUMMARY THE ORDER SPECIFIES — stated plainly rather than folded
    in. Without it "pose it in numbers this lesson has not worked" is
    unenforceable at call 2, because call 2 never sees the script and so cannot
    know what the script worked. It is the union of every numeral in call 1's
    expository `scenes` and in every practice — code-built, digits only, and
    incapable of carrying a copyable sentence. It is what makes the freshness
    instruction mean something on the far side of the split.
    """
    ids = [str(o) for o in outcome_ids]
    document = raw_contract if isinstance(raw_contract, dict) else {}
    practices = document.get("practice_scenes")
    practices = practices if isinstance(practices, dict) else {}

    def _numerals(*parts: Any) -> List[str]:
        found: List[str] = []
        for part in parts:
            for token in _NUMERAL_RE.findall(json.dumps(part, default=str)):
                if token not in found:
                    found.append(token)
        return found

    lesson: List[str] = []
    for scene in (document.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        for token in _numerals(scene.get("narration_text"),
                               scene.get("generation_params")):
            if token not in lesson:
                lesson.append(token)

    per_outcome: Dict[str, Any] = {}
    for oid in ids:
        entries = practices.get(oid)
        entries = entries if isinstance(entries, list) else (
            [entries] if isinstance(entries, dict) else []
        )
        numbers: List[str] = []
        templates: List[str] = []
        phases: List[str] = []
        blooms: List[str] = []
        media: List[str] = []
        seconds = 0.0
        for scene in entries:
            if not isinstance(scene, dict):
                continue
            params = scene.get("generation_params")
            params = params if isinstance(params, dict) else {}
            for token in _numerals(scene.get("narration_text"), params):
                if token not in numbers:
                    numbers.append(token)
                if token not in lesson:
                    lesson.append(token)
            for key, bucket in (("template", templates), ("phase", phases)):
                value = params.get(key)
                if isinstance(value, str) and value and value not in bucket:
                    bucket.append(value)
            for key, bucket in (("bloom_level", blooms), ("media_type", media)):
                value = scene.get(key)
                if isinstance(value, str) and value and value not in bucket:
                    bucket.append(value)
            try:
                seconds += float(scene.get("duration_seconds") or 0)
            except (TypeError, ValueError):
                pass
        per_outcome[oid] = {
            "practice_scene_count": len(entries),
            "numbers_used": numbers[:MAX_SUMMARY_NUMERALS],
            "step_reached": {
                "motion_templates": templates,
                "motion_phases": phases,
                "bloom_levels": blooms,
                "total_seconds": round(seconds, 1),
            },
            "media_types": media,
        }

    return {
        "per_outcome": per_outcome,
        "numbers_already_used": lesson[:MAX_SUMMARY_NUMERALS * 4],
    }


class UnsupportedMechanism(ValueError):
    """Raised for a constrained-decoding mechanism measured NOT to work here."""


def response_format_for(
    schema: Dict[str, Any],
    *,
    mechanism: str = MECHANISM_JSON_SCHEMA,
    name: str = "ivgs_design_contract",
) -> Dict[str, Any]:
    """Build the request member that actually constrains the pinned engine.

    ⛔ ``guided_json`` IS REFUSED BY NAME. It is what the recovery plan asks
    for, it returns HTTP 200, and it does nothing. Refusing loudly here is the
    difference between a package that fails and a package that lies — and the
    plan's text will outlive this session, so the refusal has to live in the
    code the plan's reader reaches for.
    """
    if mechanism in ("guided_json", "guided_choice", "guided_decoding_backend"):
        raise UnsupportedMechanism(
            f"{mechanism!r} is accepted with HTTP 200 by "
            "vllm/vllm-openai@sha256:3dbe092e… and SILENTLY IGNORED — measured "
            "2026-08-29, output byte-identical to an unconstrained call, and "
            "still 200 when handed a non-schema. Use "
            f"{MECHANISM_JSON_SCHEMA!r}. See WP-IVGS-12 report §1.3."
        )
    if mechanism == MECHANISM_JSON_SCHEMA:
        return {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema},
        }
    if mechanism == MECHANISM_STRUCTURED_OUTPUTS:
        # Not a response_format member; the caller lifts it to the body root.
        return {"structured_outputs": {"json": schema}}
    raise UnsupportedMechanism(f"unknown mechanism {mechanism!r}")


# ---------------------------------------------------------------------------
# Parsing a model emission into the row shapes the API stores
# ---------------------------------------------------------------------------

def parse_contract(raw: Any) -> Optional[Dict[str, Any]]:
    """Normalise a model emission into the API's design-brief payload.

    Returns ``None`` — not a partial dict — when the object is not a design
    contract at all, so the capture path can tell "no contract here" from "a
    contract with problems". A malformed contract is reported, never repaired:
    repairing it would manufacture a design nobody authored, which is the whole
    complaint against the pipeline this package is fixing.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(raw, dict):
        return None
    scenes = raw.get("scenes")
    if not isinstance(scenes, list):
        return None
    # The discriminator: a v7 storyboard also has `scenes`. A DESIGN contract
    # carries per-outcome notes, or scenes that declare what they serve.
    # Anything else is a storyboard from an older prompt and is left alone.
    has_notes = isinstance(raw.get("outcome_notes"), dict) and raw["outcome_notes"]
    has_plan = isinstance(raw.get("assessment_plan"), dict) and raw["assessment_plan"]
    declares = any(
        isinstance(s, dict) and s.get("serves_outcomes")
        for s in scenes
    )
    if not (has_notes or has_plan or declares):
        return None

    # ⛔ WP-IVGS-12f, EXTENDED BY 12g. FROM HERE ON, `scenes` MEANS THE MERGED
    # SEQUENCE. The evidence sections (`practice_scenes`, `assessment_scenes`,
    # and contract-5's `designed_assessments` for stored briefs) are full scenes
    # the model authored and did NOT place; `shared.design.merge` inserts each
    # at its outcome's anchor — practice after the last present/guide serving
    # it, the assessment after that practice — and re-indexes the whole design.
    # Everything downstream — the
    # derived evidence map, the stored `scene_designs`, the gate's arc — reads
    # the merged sequence, because that is the design. The model's own array
    # survives untouched inside `raw_contract`, which is the evidence limb.
    #
    # ⚠ AND THE SAME FUNCTION PRODUCES THE SEQUENCE THE FROZEN STAGE BODY SEES
    # (`design_core.capture.transform_document`), so the brief's scenes and the
    # `storyboard_scenes` rows are one list computed once. That is 12d's lesson
    # about `derive_evidence_map`, applied before it could be learned twice.
    scenes = merged_scene_sequence(raw)

    scene_rows: List[Dict[str, Any]] = []
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        prov = scene.get("provenance") or {}
        origin = prov.get("origin") if isinstance(prov, dict) else None
        row: Dict[str, Any] = {
            "scene_index": scene.get("scene_index", i),
            "serves_outcomes": scene.get("serves_outcomes"),
            "instructional_event": scene.get("instructional_event"),
            "bloom_level": scene.get("bloom_level"),
            "signal_spec": scene.get("signal_spec"),
        }
        if origin == "designed":
            row["scene_origin"] = "designed"
            row["source_refs"] = None
            row["rewrite_of"] = None
            row["designed_rationale"] = prov.get("rationale")
        elif origin == "sourced":
            refs = prov.get("source_refs")
            row["scene_origin"] = "sourced"
            row["source_refs"] = refs if isinstance(refs, list) and refs else None
            row["rewrite_of"] = prov.get("rewrite_of")
            # The CHECK refuses 'sourced' with no refs. Rather than let the
            # write fail at the database and lose the whole brief, the parse
            # reports the scene as UNDECLARED and the validator says so by name.
            if row["source_refs"] is None:
                row["scene_origin"] = None
        scene_rows.append(row)

    # The evidence derivation reads `serves_outcomes` + `instructional_event`,
    # and `scene_rows` carries both — including for a scene whose provenance was
    # downgraded to UNDECLARED above, which is right: a badly-sourced scene that
    # genuinely assesses still assesses.
    scenes_for_evidence = scene_rows

    plan = raw.get("assessment_plan")
    plan = plan if isinstance(plan, dict) else {}

    return {
        "contract_version": CONTRACT_VERSION,
        # ⛔ NO `outcomes` KEY. The model does not emit outcome text any more
        # (RC-Q9); the API fills `outcomes` from `projects.learning_outcomes`
        # by code and merges these notes onto it by id.
        "outcome_notes": raw.get("outcome_notes") or {},
        "dropped_beats": raw.get("dropped_beats") or [],
        # ⛔ WP-IVGS-12d. NOT `raw.get("evidence_map")` — THE MODEL NO LONGER
        # EMITS ONE. It is DERIVED from the scenes the model declared, by the
        # one shared function the gate also uses, so the stored map and the
        # gate's live computation cannot drift. A derived map cannot disagree
        # with the scenes: RC-Q9c's whole failure mode is unrepresentable
        # rather than merely detected.
        #
        # ⚠ Derived from the RAW scenes and keyed by whatever they cite, because
        # the worker has no outcome-id list at this point; the API re-derives it
        # against the operator's real ids when it stores the brief.
        "evidence_map": derive_evidence_map(scenes_for_evidence),
        "assessment_plan": plan,
        "design_notes": raw.get("design_notes") or "",
        "scenes": scene_rows,
        "raw_contract": raw,
    }
