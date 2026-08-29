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
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.enums import PROMPT_TYPES

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
        # ⛔ THE VALUES COME FROM ONE LIST NOW, AND THEY DID NOT BEFORE.
        # This tuple was typed out by hand. Migration 0047 (WP-IVGS-12) added
        # `transcript_refinement_system` and `storyboard_generation_system` to
        # the PostgreSQL type and NOT here, and the very next SELECT that
        # touched one of those rows raised
        #     LookupError: 'storyboard_generation_system' is not among the
        #     defined enum values.
        # — which is precisely what the comment below has warned about since
        # WP-64, and it still happened, because a warning is not a mechanism.
        # `MediaType` was moved to a shared list for the same reason after the
        # same failure (see storyboard_scene.py). This is that fix, here.
        #
        # The label MUST be known to the ORM as well as to the database type:
        # SQLAlchemy validates the value it READS against this tuple, so a row
        # carrying a label the ORM does not know raises on every SELECT of the
        # table, not just on insert.
        PG_ENUM(*PROMPT_TYPES, name="prompt_type", create_type=False),
        nullable=False,
        doc=f"PostgreSQL ENUM prompt_type: {', '.join(PROMPT_TYPES)}",
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

    @property
    def scope(self) -> str:
        """
        Compute prompt scope from project_id and scene_id per §9.1.

        Returns:
            "SCENE" if scene_id is set
            "PROJECT" if project_id is set (and scene_id is None)
            "GLOBAL" if both are None
        """
        if self.scene_id is not None:
            return "SCENE"
        elif self.project_id is not None:
            return "PROJECT"
        return "GLOBAL"

    def __repr__(self) -> str:
        return (
            f"<Prompt id={self.id} type={self.prompt_type} "
            f"v{self.version} active={self.is_active} scope={self.scope}>"
        )
