"""
ORM model for the ``projects`` table (§4.1 Table 1).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_runtime_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    state: Mapped[str] = mapped_column(
        PG_ENUM("DRAFT", "TRANSCRIPT_REFINEMENT", "STORYBOARD_GENERATION",
                "MEDIA_GENERATION", "MANIFEST_GENERATION", "AUDIO_GENERATION",
                "TALKING_HEAD_RENDER", "PROTOTYPE_DRAFT", "USER_REVIEW",
                "FINAL_RENDER", "COMPLETE", "LOCALISATION", "ERROR",
                "DELETING",
                name="project_state", create_type=False),
        nullable=False,
        server_default="DRAFT",
        doc="PostgreSQL ENUM project_state — 14 values (DELETING: WP-59, 0033)",
    )
    hero_image_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    talking_head_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_audience: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    # ── WP-64 Task 6, migration 0037 ──
    # What the viewer should be able to DO after watching. Operator-authored
    # free text, one statement or several. It is an INPUT to storyboard
    # generation (RULE 0 of the storyboard prompt), not a display field: the
    # scene mix and each scene's visual are judged against it.
    #
    # NOT RETROACTIVE. Editing it after a storyboard has been generated does
    # not rewrite scenes that already exist; it feeds the NEXT run. The GUI
    # says so where the field is edited.
    learning_outcomes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    # ── AD-09.5 preset provenance; WP-56 Task 4, migration 0032 ──
    # PROVENANCE ONLY. Applying a preset writes concrete values into the
    # project's own columns; nothing re-reads the preset at render time, so
    # editing a preset later cannot change what this project renders.
    preset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presets.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Denormalised on purpose: the FK is SET NULL, and when it fires this is
    # the only surviving record of which VERSION produced the project.
    # Provenance a delete can erase is not provenance.
    preset_version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
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

    # ── Relationships ──────────────────────────────────────────────────
    scenes = relationship(
        "StoryboardScene",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    transcripts = relationship(
        "Transcript",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    render_jobs = relationship(
        "RenderJob",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    language_variants = relationship(
        "LanguageVariant",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # WP-IVGS-12. `lazy="select"` and NOT `selectin` like its siblings: a brief
    # carries the whole raw model emission in `raw_contract`, and every project
    # list endpoint would otherwise drag several kilobytes of JSONB per project
    # into memory to render a name and a state.
    design_briefs = relationship(
        "StoryboardDesignBrief",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="StoryboardDesignBrief.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} state={self.state}>"
