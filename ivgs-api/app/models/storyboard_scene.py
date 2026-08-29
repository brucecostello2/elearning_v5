"""
ORM model for the ``storyboard_scenes`` table (§4.1 Table 3).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from shared.models.enums import MEDIA_TYPES
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, text, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class StoryboardScene(Base):
    __tablename__ = "storyboard_scenes"

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
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    narration_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visual_description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    media_type: Mapped[Optional[str]] = mapped_column(
        # WP-68: `motion_graphics` (migration 0041). THIS LIST IS LOAD-BEARING
        # ON READ, not only on write. Adding the label to the PostgreSQL type
        # alone let an INSERT succeed and made every subsequent SELECT raise
        # `LookupError: 'motion_graphics' is not among the defined enum
        # values` -- the row was written and could not be read back. Caught by
        # the acceptance run, not by a test, which is why the values are now
        # taken from ONE list rather than typed here.
        PG_ENUM(*MEDIA_TYPES, name="media_type", create_type=False),
        nullable=True,
        doc=f"PostgreSQL ENUM media_type: {', '.join(MEDIA_TYPES)}",
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    # ── WP-43 D-2, ruled EXTEND; migration 0028 ──
    # The Edit Scene modal has always sent these five keys. SceneUpdate declared
    # four, so Pydantic dropped the rest without an error and the dialog looked
    # exactly as though it had saved them. camera_angle and transition_type are
    # read by the generation and composition prompts, so removing the controls
    # would have discarded intent the operator was already expressing.
    camera_angle: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    transition_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    effects: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
    )
    timing_offset_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    generation_params: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    # ── WP-IVGS-10, v7's per-scene content contract; migration 0045 ──
    # `media_rationale` is RULE 9: one line on why THIS medium for THIS scene.
    # `text_carried_by` is RULE 1-EXTENDED's declaration: when the narration's
    # content is written or numeric and the scene keeps a diffusion medium, the
    # storyboard must SAY that the words carry the text and the picture carries
    # the situation. A declaration a machine has to infer from prose is not a
    # declaration -- this repository has measured that mistake three times -- so
    # it is a column with one legal value, checked in the database.
    media_rationale: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    text_carried_by: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )
    # ── WP-IVGS-12, THE DESIGN CONTRACT; migration 0048 ──
    # Instructional Design Foundation §6. Each of these is a DECLARATION the
    # designer makes and the gate checks; none is inferred from prose, for the
    # reason 0045 already records — a declaration a machine must recover with a
    # regular expression is not a declaration.
    #
    # ⚠ Foundation §6 also lists `modality_rationale`. IT IS NOT ADDED HERE: it
    # is `media_rationale` above, created by 0045 for v7's RULE 9, which asks
    # the identical question. One fact, one column. Flagged in the WP-IVGS-12
    # report rather than resolved silently.
    #
    # Outcome ids this scene serves, ≥1 once a design brief exists. Serving is
    # not evidence — `evidence_map` on the brief answers the other half.
    # ⛔ `none_as_null=True` ON EVERY DESIGN JSONB COLUMN, AND IT IS LOAD-BEARING.
    # SQLAlchemy's JSON/JSONB default is `none_as_null=False`: a Python `None`
    # is written as the JSON value `null`, NOT as SQL NULL. Measured 2026-08-29
    # when WP-IVGS-12b started writing the declaration WHOLE (explicit None for
    # absent fields) instead of omitting keys —
    #     new row ... violates check constraint
    #     "ck_storyboard_scenes_source_xor_designed"
    # on a row whose source_refs printed as `null` in the DETAIL and looked
    # perfectly legal. `source_refs IS NULL` is FALSE for jsonb 'null', so the
    # `designed` branch could never match. Two spellings of "nothing", one of
    # which the constraint cannot see.
    #
    # Migration 0050 hardens the CHECK as well, because rows may already carry
    # jsonb 'null' and a constraint that distinguishes two spellings of absence
    # is a trap whatever the writer does. This is the writer half.
    #
    # ⚠ SCOPED TO THE DESIGN COLUMNS. `effects` and `generation_params` predate
    # this package and their existing behaviour is not changed on a hunch.
    serves_outcomes: Mapped[Optional[list]] = mapped_column(
        JSONB(none_as_null=True), nullable=True,
    )
    # One of INSTRUCTIONAL_EVENTS (Gagné, Foundation §3). Complementary to
    # `scene_kind`, not a duplicate of it: AD-09's `intro`/`outro` are template
    # shapes, this is the instructional job the scene performs.
    instructional_event: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )
    # One of BLOOM_LEVELS (Foundation §2). Set by the served outcome's verb.
    bloom_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # [{transcript_id, start, end}] — character spans of `transcripts.source_text`,
    # NOT of `refined_text`. See the note on that column.
    source_refs: Mapped[Optional[list]] = mapped_column(
        JSONB(none_as_null=True), nullable=True,
    )
    # `sourced` | `designed` — SCENE_ORIGINS. The XOR against `source_refs` is a
    # CHECK constraint (ck_storyboard_scenes_source_xor_designed), so it is the
    # database that refuses a scene claiming both or claiming neither, rather
    # than whichever caller remembers to look.
    scene_origin: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # {transcript_id, start, end, original} when the narration was REWORDED
    # under R1a. Marking is mandatory and the original travels with the mark:
    # the ruling is that silent loss is the defect class, so an unmarked rewrite
    # is worse than a bad one.
    rewrite_of: Mapped[Optional[dict]] = mapped_column(
        JSONB(none_as_null=True), nullable=True,
    )
    # Optional. Mayer signalling (Foundation §4): what to highlight and when,
    # e.g. the carry digit at the word "carry". This is what the motion
    # template's `phase` mechanism exists to execute.
    signal_spec: Mapped[Optional[dict]] = mapped_column(
        JSONB(none_as_null=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # ── Relationships ──
    project = relationship("Project", back_populates="scenes")

    __table_args__ = (
        Index(
            "ix_storyboard_scenes_project_index",
            "project_id", "scene_index",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<StoryboardScene id={self.id} project={self.project_id} "
            f"idx={self.scene_index}>"
        )
