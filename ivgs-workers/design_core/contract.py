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
from typing import Any, Dict, List, Optional, Tuple

from shared.models.enums import (
    BLOOM_LEVELS,
    INSTRUCTIONAL_EVENTS,
    MEDIA_TYPES,
)

#: Bumped when the SHAPE changes, not when the prompt does. Stored on the brief
#: so a reader knows which parse produced the row they are looking at.
CONTRACT_VERSION = "design-contract-1"

#: The one supported mechanism, measured. See the module docstring.
MECHANISM_JSON_SCHEMA = "json_schema"
#: Measured equivalent on the same engine; kept so a future engine that drops
#: `response_format` support has a named path rather than an improvised one.
MECHANISM_STRUCTURED_OUTPUTS = "structured_outputs"


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


def _outcome_schema() -> Dict[str, Any]:
    """One learning outcome, ABCD-checked. Foundation §2.

    ⛔ ``text`` IS THE OPERATOR'S OWN WORDS AND IS COPIED, NEVER EDITED. If the
    outcome is not measurable, the refinement goes in ``proposed_refinement``
    for approval AT THE GATE. The Foundation is explicit: never silently
    substitute, and never design against fog.

    ⛳ THE ``oneOf`` IS THERE BECAUSE THE FIRST PROBE EARNED IT. With
    ``measurable`` and ``proposed_refinement`` as independent members, the model
    returned ``measurable: true`` AND a non-null refinement for both outcomes —
    a self-contradiction the gate would then have shown the operator as a
    refinement to approve for an outcome that needed none. Splitting them into
    two mutually exclusive branches makes the contradiction ungrammatical
    instead of merely discouraged, using the construct probe 0(c) measured
    working. Evidence: `design-contract-probe-2026-08-29.txt`.
    """
    common = {
        "id": {
            "type": "string",
            "description": "Stable handle, e.g. LO-1. Scenes cite this.",
        },
        "text": {
            "type": "string",
            "description": "The operator's outcome, VERBATIM. Never reworded here.",
        },
        "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
        "abcd": {
            "type": "object",
            "properties": {
                "audience": {"type": _nullable("string")},
                "behavior": {"type": _nullable("string")},
                "condition": {"type": _nullable("string")},
                "degree": {"type": _nullable("string")},
            },
            "required": ["audience", "behavior", "condition", "degree"],
            "additionalProperties": False,
        },
    }
    return {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    **common,
                    "measurable": {"type": "boolean", "enum": [True]},
                    "proposed_refinement": {
                        "type": "null",
                        "description": (
                            "The operator's own text already states an "
                            "observable behaviour. There is nothing to propose "
                            "and proposing anyway wastes the reviewer's "
                            "attention on a decision that is not theirs to make."
                        ),
                    },
                },
                "required": ["id", "text", "measurable", "bloom_level", "abcd",
                             "proposed_refinement"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    **common,
                    "measurable": {"type": "boolean", "enum": [False]},
                    "proposed_refinement": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "An ABCD rewrite PROPOSED for the operator to "
                            "approve — Audience, Behavior, Condition, Degree. "
                            "It is NOT applied. The design proceeds against the "
                            "operator's text until the gate says otherwise."
                        ),
                    },
                },
                "required": ["id", "text", "measurable", "bloom_level", "abcd",
                             "proposed_refinement"],
                "additionalProperties": False,
            },
        ]
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


def _scene_schema(*, media_types: Tuple[str, ...]) -> Dict[str, Any]:
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
                "items": {"type": "string"},
                "description": (
                    "Outcome ids. A scene that serves nothing is decoration and "
                    "is cut — Foundation §1's alignment triad."
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
    media_types: Optional[Tuple[str, ...]] = None,
    min_scenes: int = 2,
) -> Dict[str, Any]:
    """The whole contract: project-level members plus the scene array."""
    return {
        "type": "object",
        "properties": {
            "outcomes": {
                "type": "array",
                "minItems": 1,
                "items": _outcome_schema(),
            },
            "scenes": {
                "type": "array",
                "minItems": min_scenes,
                "items": _scene_schema(
                    media_types=tuple(media_types or MEDIA_TYPES),
                ),
            },
            "dropped_beats": {
                "type": "array",
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
                    "Every beat of the script that no scene uses. Dropping is a "
                    "design decision; SILENT loss is the defect class this "
                    "contract exists to remove. An empty array is a claim that "
                    "nothing was dropped, and the validator checks it."
                ),
            },
            "evidence_map": {
                "type": "object",
                "description": (
                    "outcome id -> the scene_index values that ASSESS it. "
                    "Serving is not evidence: Foundation §1 stage 2 is a "
                    "separate question and the gate asks it separately."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                },
            },
            "design_notes": {
                "type": "string",
                "description": "One short paragraph: the arc, and why it is this arc.",
            },
        },
        "required": ["outcomes", "scenes", "dropped_beats", "evidence_map",
                     "design_notes"],
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
    # has outcomes, or scenes that declare what they serve. Anything else is a
    # storyboard from an older prompt and is left alone.
    has_outcomes = isinstance(raw.get("outcomes"), list) and raw["outcomes"]
    declares = any(
        isinstance(s, dict) and s.get("serves_outcomes")
        for s in scenes
    )
    if not (has_outcomes or declares):
        return None

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

    return {
        "contract_version": CONTRACT_VERSION,
        "outcomes": raw.get("outcomes") or [],
        "dropped_beats": raw.get("dropped_beats") or [],
        "evidence_map": raw.get("evidence_map") or {},
        "design_notes": raw.get("design_notes") or "",
        "scenes": scene_rows,
        "raw_contract": raw,
    }
