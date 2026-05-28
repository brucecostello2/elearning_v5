"""
ORM model for the ``assets`` table (§4.1 Table 4).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, BigInteger, Float, Integer, Boolean,
    DateTime, ForeignKey, text,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class Asset(Base):
    __tablename__ = "assets"

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
    scene_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storyboard_scenes.id", ondelete="SET NULL"),
        nullable=True,
    )
    asset_type: Mapped[str] = mapped_column(
        PG_ENUM("image", "video", "audio", "document", "talking_head",
                "final_render", name="asset_type", create_type=False),
        nullable=False,
        doc="PostgreSQL ENUM asset_type",
    )
    seaweedfs_fid: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    seaweedfs_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True,
    )
    mime_type: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    language_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
    )
    generation_prompt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # v4 tier columns
    storage_tier: Mapped[str] = mapped_column(
        PG_ENUM("hot", "warm", "cold", "archived", "deleted",
                name="storage_tier", create_type=False),
        nullable=False, server_default="hot",
        doc="PostgreSQL ENUM storage_tier",
    )
    tier_transition_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    preserve_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    reference_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"),
    )
    generation_params_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<Asset id={self.id} type={self.asset_type} "
            f"project={self.project_id}>"
        )
