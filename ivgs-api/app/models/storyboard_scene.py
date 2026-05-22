"""
ORM model for the ``storyboard_scenes`` table (§4.1 Table 3).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, text, Index
from sqlalchemy.dialects.postgresql import UUID
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
        String(16), nullable=True,
        doc="PostgreSQL ENUM media_type: image, video_clip, animation",
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
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
