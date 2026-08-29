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
