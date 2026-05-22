"""
ORM model for the ``projects`` table (§4.1 Table 1).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
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
        String(32),
        nullable=False,
        server_default="DRAFT",
        doc="PostgreSQL ENUM project_state — 13 values",
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
    target_audience: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
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

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} state={self.state}>"
