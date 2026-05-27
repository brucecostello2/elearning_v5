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
