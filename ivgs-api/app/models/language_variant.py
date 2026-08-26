"""
ORM model for the ``language_variants`` table (§4.1 Table 8).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class LanguageVariant(Base):
    __tablename__ = "language_variants"

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
    language_code: Mapped[str] = mapped_column(
        String(10), nullable=False,
    )
    state: Mapped[str] = mapped_column(
        # WP-61 Task 3(c), migration 0034: `flagged` is the FAIL-AND-FLAG
        # terminal state. It is a usable deliverable the model doubted, which
        # is neither `complete` nor `failed` -- collapsing it into either one
        # hides a real deliverable behind an error badge or a real doubt behind
        # a green one.
        PG_ENUM("pending", "processing", "complete", "failed", "flagged",
                name="language_variant_state", create_type=False),
        nullable=False, server_default="pending",
        doc="PostgreSQL ENUM language_variant_state",
    )
    # WP-61. The deliverable, per scene, plus the provenance of the run. The
    # text here has ALREADY had any IVGS-TRANSLATION-FLAG marker stripped from
    # it; the marker lives in `translation_flags`. NULL = never translated,
    # which is what all 16 rows on this fleet are (measured 2026-08-26).
    translation: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    # WP-61. Markers the translator emitted, verbatim, with their scene. A
    # separate column, not a key inside `translation`, so "which variants did
    # the model doubt?" is one predicate rather than a dig through a blob.
    translation_flags: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
    )
    final_render_1080p_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    final_render_4k_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # ── Relationships ──
    project = relationship("Project", back_populates="language_variants")

    def __repr__(self) -> str:
        return (
            f"<LanguageVariant id={self.id} lang={self.language_code} "
            f"state={self.state}>"
        )
