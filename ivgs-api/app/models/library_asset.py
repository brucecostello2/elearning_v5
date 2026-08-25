"""
ORM model for the ``library_assets`` table (AD-09.4.2).

Migration: 0030_wp56_library_assets

This model lives in ``ivgs-api/app/models/`` and NOT in ``shared/models/``,
deliberately. ``shared/models/`` is the seam for models a WORKER needs
(WP-56 Task 1, ledger P2.60). No worker reads the library — that is the WP-56
boundary condition against the Temporal cutover — and putting the class where
the workers can reach it would be the first step toward one doing so.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    String, BigInteger, Float, Text, DateTime, ForeignKey, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base

LIBRARY_ASSET_KINDS = (
    "logo", "video_clip", "audio_clip", "music_bed",
    "reference_clip", "reference_image", "font", "document",
)
LIBRARY_OWNER_SCOPES = ("global", "user")


class LibraryAsset(Base):
    __tablename__ = "library_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    kind: Mapped[str] = mapped_column(
        PG_ENUM(*LIBRARY_ASSET_KINDS, name="library_asset_kind", create_type=False),
        nullable=False,
        doc="PostgreSQL ENUM library_asset_kind",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Mirrors `assets` exactly — same SeaweedFS storage path, different owner.
    seaweedfs_fid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seaweedfs_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    tags: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    owner_scope: Mapped[str] = mapped_column(
        PG_ENUM(*LIBRARY_OWNER_SCOPES, name="library_owner_scope", create_type=False),
        nullable=False, server_default="user",
        doc="PostgreSQL ENUM library_owner_scope; `global` is admin-mutable only",
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Library assets are never hard-deleted while referenced (AD-09.4.2).
    # Replacing one points the old row here and leaves history resolvable.
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("library_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_library_assets_kind_scope", "kind", "owner_scope"),
    )

    def __repr__(self) -> str:
        return (
            f"<LibraryAsset id={self.id} kind={self.kind} "
            f"scope={self.owner_scope} name={self.name!r}>"
        )
