"""
ORM model for the ``prompts`` table (§4.1 Table 5).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Boolean, Text, DateTime,
    ForeignKey, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    scene_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storyboard_scenes.id", ondelete="CASCADE"),
        nullable=True,
    )
    prompt_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        doc="PostgreSQL ENUM prompt_type — 10 values",
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    is_library_template: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    change_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # §9.5 Prompt Library — many-to-many relationship with tags
    tags = relationship(
        "PromptTag",
        secondary="prompt_tag_associations",
        back_populates="prompts",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Prompt id={self.id} type={self.prompt_type} "
            f"v{self.version} active={self.is_active}>"
        )
