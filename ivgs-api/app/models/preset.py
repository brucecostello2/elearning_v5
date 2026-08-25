"""
ORM model for the ``presets`` table (AD-09.5) — a named, VERSIONED bundle of
choices applied at project creation.

Migration: 0032_wp56_presets
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    String, Text, Integer, Boolean, DateTime, ForeignKey,
    UniqueConstraint, CheckConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class Preset(Base):
    """One VERSION of a preset. Identity is ``(name, version)``, not ``id``.

    Editing a preset INSERTS a new row and flips ``is_active``. Nothing
    UPDATEs ``payload`` — an in-place edit would silently rewrite the
    provenance of every project already created from it.
    """
    __tablename__ = "presets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"),
    )
    # Opaque by design — see migration 0032's docstring on why there is no
    # CHECK constraint here. The API validates it; the database stores it.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    owner_scope: Mapped[str] = mapped_column(
        PG_ENUM("global", "user", name="library_owner_scope", create_type=False),
        nullable=False, server_default="user",
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_presets_name_version"),
        CheckConstraint("version >= 1", name="ck_presets_version_positive"),
    )

    def __repr__(self) -> str:
        return f"<Preset id={self.id} name={self.name!r} v{self.version} active={self.is_active}>"
