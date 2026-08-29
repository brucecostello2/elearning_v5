"""Schemas for the design brief (WP-IVGS-12, Foundation §6-§7).

⚠ THE INGEST SCHEMA IS DELIBERATELY PERMISSIVE ABOUT SHAPE AND STRICT ABOUT
NOTHING. It receives a model emission that has already been constrained by the
engine's grammar, and its job is to STORE it, not to re-judge it. A 422 here
would throw away the only copy of a design the operator is waiting to review,
and would do it for a field the gate could simply have shown as missing. The
judging happens at the gate, where a human can see it and the assessment can
say which scene and why.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DesignBriefIngest(BaseModel):
    """What ``design_core.capture`` POSTs. Every member optional by design."""

    job_id: Optional[str] = None
    contract_version: Optional[str] = None
    model_used: Optional[str] = None
    prompt_fingerprint: Optional[str] = None
    outcomes: Optional[List[Dict[str, Any]]] = None
    dropped_beats: Optional[List[Dict[str, Any]]] = None
    evidence_map: Optional[Dict[str, List[int]]] = None
    design_notes: Optional[str] = None
    #: Parsed per-scene declarations. Absent on a stage-1 intent post.
    scenes: Optional[List[Dict[str, Any]]] = None
    #: The stage-1 extraction artifact. Posted on its own, ahead of any design.
    intent: Optional[Dict[str, Any]] = None
    #: The model's emission, verbatim. The evidence limb.
    raw_contract: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class DesignBriefResponse(BaseModel):
    id: UUID
    project_id: UUID
    job_id: Optional[UUID] = None
    is_active: bool
    outcomes: List[Dict[str, Any]] = Field(default_factory=list)
    dropped_beats: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_map: Dict[str, Any] = Field(default_factory=dict)
    scene_designs: List[Dict[str, Any]] = Field(default_factory=list)
    intent: Optional[Dict[str, Any]] = None
    contract_version: Optional[str] = None
    prompt_fingerprint: Optional[str] = None
    model_used: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OutcomeCoverage(BaseModel):
    """One row of the outcomes × scenes matrix the gate renders."""

    outcome_id: str
    text: str
    measurable: bool = True
    proposed_refinement: Optional[str] = None
    bloom_level: Optional[str] = None
    #: Scenes that SERVE it.
    served_by: List[int] = Field(default_factory=list)
    #: Scenes that ASSESS it — a different question, asked separately.
    assessed_by: List[int] = Field(default_factory=list)
    served: bool = False
    assessed: bool = False


class DesignReviewResponse(BaseModel):
    """The whole design review, as one payload the gate can render.

    Foundation §7: the reviewer sees the outcomes with any refinement to
    approve, the event arc, the outcomes × scenes × evidence matrix, every
    rewrite diffed against its span, every drop with its reason, and the
    modality rationale per scene — before a single pixel is rendered.
    """

    has_brief: bool
    brief: Optional[DesignBriefResponse] = None
    #: Ordered [{scene_index, instructional_event, media_type, bloom_level,
    #:           serves_outcomes, media_rationale, narration_text}]
    event_arc: List[Dict[str, Any]] = Field(default_factory=list)
    coverage: List[OutcomeCoverage] = Field(default_factory=list)
    #: [{scene_index, original, rewritten, reason, span}]
    rewrites: List[Dict[str, Any]] = Field(default_factory=list)
    dropped_beats: List[Dict[str, Any]] = Field(default_factory=list)
    #: Deterministic findings — `refuse` (objectively checkable) and `flag`
    #: (judgment). Same two-limb discipline WP-IVGS-10 established at this gate.
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    refusals: int = 0
    flags: int = 0
