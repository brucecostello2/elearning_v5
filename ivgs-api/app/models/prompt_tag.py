"""
ORM model for the ``prompt_tags`` and ``prompt_tag_associations`` tables (§9.5).

Migration: 0015_prompt_tags (or existing unnamed migration that creates these tables)

§9.5 Prompt Library:
  Admins can designate prompts as library templates with tags.
  Tags enable categorization and discovery of reusable prompt templates.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, DateTime, ForeignKey, Table, Column, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


# Many-to-many association table: prompt ↔ tag
prompt_tag_associations = Table(
    "prompt_tag_associations",
    Base.metadata,
    Column(
        "prompt_id",
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("prompt_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class PromptTag(Base):
    """
    A tag that can be applied to library prompt templates (§9.5).

    Tags enable admins to categorize prompts for discovery:
    e.g., "medical", "engineering", "conversational", "formal".
    """
    __tablename__ = "prompt_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True,
        doc="Human-readable tag name (e.g., 'medical', 'formal')",
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True,
        doc="Optional description of what this tag represents",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # Relationships
    prompts = relationship(
        "Prompt",
        secondary=prompt_tag_associations,
        back_populates="tags",
        lazy="selectin",
    )
