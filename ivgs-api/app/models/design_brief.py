"""ORM model for ``storyboard_design_briefs`` (WP-IVGS-12, migration 0048).

THE DESIGN BRIEF IS THE THING THE REVIEWER APPROVES.

A storyboard gate has always been *supposed* to be a course-design review;
until this package it showed thumbnails and narration. Foundation §7 says what
it must show instead, and three of those six things belong to the design as a
whole rather than to any scene: the outcomes (with any ABCD refinement awaiting
approval), the beats consciously dropped with reasons, and the evidence map.
This row is those three, plus the evidence limb that lets a reader check them.

WHY A ROW PER GENERATION AND NOT COLUMNS ON ``projects``

A project can regenerate its storyboard. Each regeneration is a NEW design, and
overwriting the previous one is precisely the behaviour recovery-plan RC-E
records as a defect: the gate's Regenerate button sits beside Approve with no
confirmation and no record of what it discards, and it wiped a storyboard the
operator had edited. One row per design, ``is_active`` marking the current one
and a partial unique index enforcing that there is only one, means the
superseded design is still there to diff against. It is the same lineage shape
``prompts`` uses, for the same reason.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class StoryboardDesignBrief(Base):
    __tablename__ = "storyboard_design_briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Nullable, and deliberately NOT a foreign key: a brief is evidence of what
    #: was designed and must outlive the job row that retention prunes.
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )

    #: [{id, text, bloom_level, abcd:{audience,behavior,condition,degree},
    #:   measurable: bool, proposed_refinement: str|null}]
    #:
    #: ⛔ ``text`` IS THE OPERATOR'S OWN WORDS AND IS NEVER REWRITTEN IN PLACE.
    #: Foundation §2: an unmeasurable outcome gets an ABCD refinement PROPOSED
    #: at the gate for approval; it is never silently substituted, and the
    #: designer never designs against fog without saying so.
    outcomes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    #: [{span:{transcript_id,start,end}, summary, reason}] — dropping is a
    #: design decision. Silent loss is the defect class this package exists to
    #: remove, so a beat that is not used is a beat that is DECLARED dropped.
    dropped_beats: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    #: {outcome_id: [scene_index, ...]} — the ASSESSING scenes only.
    #: Foundation §1 stage 2 is "determine acceptable evidence", and it is a
    #: different question from "which scenes serve this outcome". The gate asks
    #: both and can fail on either.
    evidence_map: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
    )
    #: The stage-1 extraction artifact the design consumed: beats with spans,
    #: the description-derived audience/purpose/tone/constraints, the parsed
    #: outcomes. Kept so the gate can show a rewrite beside the beat it came
    #: from, and a drop in its context, without re-deriving anything.
    intent: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    #: The model's emission, verbatim and unparsed. THE EVIDENCE LIMB: every
    #: field above is derived from it, and a reader who doubts the derivation
    #: can check. RC-P1 was undetectable for three days because nobody could.
    raw_contract: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    #: The parsed per-scene declarations. Derived from `raw_contract` by the
    #: WORKER's single parse (`design_core.contract.parse_contract`) and stored
    #: so the API never grows a second copy of it — the contract is captured
    #: before the scene rows exist, so `create_scene` must look its scene up.
    scene_designs: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    #: 64, not 16. Migration 0049: `design-contract-1` is seventeen characters
    #: and 0048's VARCHAR(16) rejected every ingest with HTTP 500. A version
    #: string is a label, not a key.
    contract_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    #: Which prompt actually produced this — the DB row's id and version, or
    #: the ``.j2`` file's SHA-256 when the file fallback ran. The system prompt
    #: has a version lineage as of 0047; this is how a reader knows WHICH
    #: version, including in the case where no row existed.
    prompt_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    model_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    project = relationship("Project", back_populates="design_briefs")

    __table_args__ = (
        Index(
            "ux_storyboard_design_briefs_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index(
            "ix_storyboard_design_briefs_project_created",
            "project_id", "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<StoryboardDesignBrief id={self.id} project={self.project_id} "
            f"active={self.is_active} outcomes={len(self.outcomes or [])}>"
        )
