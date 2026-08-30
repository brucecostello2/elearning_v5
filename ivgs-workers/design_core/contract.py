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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.design.evidence import derive_evidence_map
from shared.design.merge import merged_scene_sequence
from shared.models.enums import (
    ASSESSING_EVENTS,
    BLOOM_LEVELS,
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
CONTRACT_VERSION = "design-contract-5"

#: The one supported mechanism, measured. See the module docstring.
MECHANISM_JSON_SCHEMA = "json_schema"
#: Measured equivalent on the same engine; kept so a future engine that drops
#: `response_format` support has a named path rather than an improvised one.
MECHANISM_STRUCTURED_OUTPUTS = "structured_outputs"

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

#: WP-IVGS-12f. The same bound, for the one sentence a designed assessment gives
#: on what the script lacked. ⚠ The `rationale` on the `scenes` oneOf's
#: `designed` branch is deliberately NOT bounded by this package: that branch is
#: untouched contract-4 surface, and widening a package's blast radius to tidy a
#: string is how a contract change acquires a second variable. Named as a
#: residue rather than fixed quietly.
MAX_DESIGNED_RATIONALE_CHARS = 300

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


def _designed_assessments_schema(
    outcome_ids: Sequence[str], *, media_types: Tuple[str, ...],
) -> Dict[str, Any]:
    """One INVENTED unaided scene per outcome, and the model cannot decline.

    ⛔ WHY AN INVITATION WAS NEVER GOING TO BE ENOUGH, MEASURED TWICE

    The prompt has invited invention since v8 — *"material the outcomes require
    that the script lacks is legitimate: you invent it, mark the scene
    `origin: designed`"* — and across six generations and 83 scenes the model
    accepted it ZERO times (RC-Q9e). Every scene of every generation was
    `sourced`, anchored to a span of the uploaded script.

    ⛳ AND WP-IVGS-12f MEASURED WHY, WHICH IS NOT WHAT RC-Q9e ASSUMED. Handed a
    SPARSE script that teaches a procedure and contains no practice material at
    all, the same model on the same stack invented FIVE scenes and emitted the
    first `assess` event this project has ever recorded. It is not that the
    model cannot design. It is that in one `scenes[]` array, sourced and
    designed material compete for the same slots, and anything the script can
    supply wins. Handed an explicit unaided problem (*"Now you try. Work out 63
    minus 48"*), it anchored three scenes to that span and labelled them
    `practice` — the invention refused even where the pedagogy was written down.

    So this object removes the competition rather than arguing with it. Three
    keys are pinned by the grammar and are not decisions the model makes:

        origin              "designed"   — it cannot cite a span
        instructional_event "assess"     — it cannot downgrade to `practice`
        serves_outcomes     [that id]    — it cannot re-aim at another outcome

    Every pin is a single-value `enum`, which RC-Q12 measured ENFORCED on the
    pinned engine, re-measured for this package under a prompt ordering each one
    broken. `const` was measured too and is implemented and enforced — scalar
    and whole-array alike — and is NOT used: it buys nothing the proven
    construct does not already give, and RC-Q12's whitespace corridor applies
    identically to both shapes. The order's tie-break stands.

    ⛔ AND THERE IS NO `scene_index`. Placement is not the model's to make —
    `shared.design.merge` inserts each of these after the last scene serving its
    outcome. 12b's principle: never ask the model for what code can compute.
    """
    def one(oid: str) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                # First, because generation order follows declaration order
                # (12d): the model states what the script lacked BEFORE it
                # writes the scene that supplies it.
                "provenance": {
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string", "enum": ["designed"]},
                        "rationale": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_DESIGNED_RATIONALE_CHARS,
                            "description": (
                                "One sentence: what this outcome needs that the "
                                "script does not contain. It does not contain an "
                                "unaided attempt — that is why you are writing "
                                "one."
                            ),
                        },
                    },
                    "required": ["origin", "rationale"],
                    "additionalProperties": False,
                },
                "instructional_event": {"type": "string", "enum": ["assess"]},
                "serves_outcomes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {"type": "string", "enum": [oid]},
                    "description": f"This scene assesses {oid} and nothing else.",
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
                    ),
                },
                "visual_description": {"type": "string", "minLength": 1},
                "media_type": {"type": "string", "enum": list(media_types)},
                "media_rationale": {
                    "type": "string",
                    "description": (
                        "Which row of the modality table this scene sits in. A "
                        "computational attempt is `motion_graphics` and MUST "
                        "carry a template in `generation_params`; an explain-it "
                        "or check-your-own-work attempt is `image` or "
                        "`talking_head`, because the renderer has no template "
                        "for it and a motion scene without one is refused."
                    ),
                },
                "duration_seconds": {
                    "type": "number", "minimum": 3, "maximum": 120,
                    "description": (
                        "Long enough to pose, hold and reveal in ONE scene. The "
                        "hold is the part that makes it unaided; a three-second "
                        "assess has no hold in it."
                    ),
                },
                "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
                "text_carried_by": {
                    "type": _nullable("string"), "enum": ["narration", None],
                },
                "generation_params": {
                    "type": _nullable("object"),
                    "description": (
                        "REQUIRED when media_type is motion_graphics: the "
                        "template name and its parameters FLAT alongside it. "
                        "The numbers here are the FRESH ones you posed, not the "
                        "script's."
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

    return {
        "type": "object",
        "properties": {oid: one(oid) for oid in outcome_ids},
        "required": list(outcome_ids),
        "additionalProperties": False,
        "description": (
            "ONE SCENE PER OUTCOME THAT YOU INVENT. The script is source "
            "material for present/guide/recall; the assessments are YOURS TO "
            "AUTHOR and there is no entry here you can leave out. Pose the "
            "problem cold in fresh numbers, hold while the learner attempts it, "
            "then reveal. You do NOT place these — they are inserted after the "
            "last scene serving each outcome, so design each one as the end of "
            "that outcome's fading sequence."
        ),
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
            "instructional_event": {
                "type": "string",
                "enum": list(INSTRUCTIONAL_EVENTS),
                "description": "Gagné, Foundation §3. The job this scene performs.",
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
        # ⛔ WP-IVGS-12f PUTS `designed_assessments` SECOND, AND THE POSITION IS
        # THE ARGUMENT. Declaration order binds generation order, so the model
        # writes the unaided assessment while the scene list is STILL EMPTY —
        # it has no worked example of its own to copy the numbers out of, which
        # is the exact degeneracy the acceptance has to check for by hand. This
        # is Foundation §1 in full for the first time: outcomes, then the
        # evidence, then the assessment that IS the evidence, and only then the
        # arc that leads to it.
        properties = {
            "assessment_plan": _assessment_plan_schema(ids),
            "designed_assessments": _designed_assessments_schema(
                ids, media_types=tuple(media_types or MEDIA_TYPES),
            ),
            **properties,
        }
        required.insert(0, "designed_assessments")
        required.insert(0, "assessment_plan")
    # With no ids there is no plan to require: the operator stated no outcomes,
    # so there is nothing to promise evidence FOR — and nothing to force an
    # assessment OF, so `designed_assessments` is absent on this path too
    # (WP-IVGS-12f). An empty required-key object would be a grammar demanding
    # a key set that does not exist. `design_review` says the outcomes were
    # never stated and carries the whole weight on that path.

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
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

    # ⛔ WP-IVGS-12f. FROM HERE ON, `scenes` MEANS THE MERGED SEQUENCE.
    # `designed_assessments` are full scenes the model authored and did NOT
    # place; `shared.design.merge` inserts each after the last scene serving its
    # outcome and re-indexes the whole design. Everything downstream — the
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
