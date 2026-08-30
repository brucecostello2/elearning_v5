"""
ORM model for the ``transcripts`` table (§4.1 Table 2).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

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
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    original_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    refined_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ── WP-IVGS-12, migration 0046 ──
    # ⛔ `refined_text` IS NOT THE UPLOAD. The upload path writes the extracted
    # file text here (`transcript_service.py:157`) and Stage 1 then PATCHes its
    # paraphrase over the top of it (`stage1_transcript.py:241`), so on any
    # project that has run once, the operator's script is gone. Measured on one
    # 3,172-byte upload: 1,866 / 1,851 / 1,615 chars across three projects.
    #
    # `source_text` is the extraction as uploaded.
    # ⛔ AMENDED BY RC-Q18 RULING (2), 2026-08-30: it was "written ONCE, by the
    # upload path only", and it is now ALSO written when an operator edits an
    # uploaded transcript's `refined_text` at the gate. The two move together,
    # because on an uploaded row the operator is editing THE SCRIPT — and if
    # they did not, the design would read one string while the spans indexed
    # into another, which is RC-Q15 with a person's hand on it. It is what the Design Contract's `source_refs`
    # character spans index into — a span offset is meaningless against a string
    # that is rewritten between the write and the read — and it is what the gate
    # shows beside a rewrite under ruling R1a.
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # `uploaded` | `generated` | `unknown` — TRANSCRIPT_SOURCE_KINDS, checked in
    # the database. Task 2's mode switch reads this and nothing else.
    source_kind: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )
    language_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
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
    project = relationship("Project", back_populates="transcripts")

    __table_args__ = (
        Index("ix_transcripts_project_sequence", "project_id", "sequence_order"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transcript id={self.id} project={self.project_id} "
            f"seq={self.sequence_order}>"
        )
