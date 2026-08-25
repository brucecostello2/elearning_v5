"""
ORM model for the ``actors`` table (AD-09.4.3) — presenter identity as a
first-class entity.

Migration: 0031_wp56_actors
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    String, Text, Boolean, DateTime, ForeignKey, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base

PRESENTER_ORIENTATIONS = ("landscape", "portrait")


class Actor(Base):
    """A reusable presenter identity: reference media + voice + engine params.

    The AD-09.4.3 constraint this class exists to make expressible: an actor's
    identity is only reproducible on the ENGINE it was established against.
    ``certified_model_id`` is that pin and ``engine_bindings`` is keyed by
    engine for the same reason. Changing the bound engine is an identity
    change, and the UI must say so rather than silently producing a
    different-sounding presenter.
    """
    __tablename__ = "actors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # "Whichever the bound engine requires" — both nullable, because which one
    # is needed is a property of an engine that may not be chosen yet.
    reference_clip_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("library_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    reference_image_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("library_assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Engine-scoped: TTS voice id / speaker embedding ref / seed / joint-engine
    # voice params. Separate from engine_bindings because AD-09.6.1 rules audio
    # and video are always persisted as separate assets whichever engine made them.
    voice_profile: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ⚠ AD-09.14 OPEN QUESTION 1 — AWAITING THE OPERATOR.
    # The concrete MagiHuman parameter set for working generation and for
    # actor/voice consistency is operator knowledge that is recorded NOWHERE in
    # this repository. WP-56 designed this column to hold it and deliberately
    # did not invent its contents. Shape: {"<engine_name>": {...}, ...}.
    # Nothing reads it. Do not add a validator that guesses the keys.
    engine_bindings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    default_orientation: Mapped[str] = mapped_column(
        PG_ENUM(*PRESENTER_ORIENTATIONS, name="presenter_orientation", create_type=False),
        nullable=False, server_default="landscape",
        doc="PostgreSQL ENUM presenter_orientation",
    )
    certified_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"),
        nullable=True,
        doc="The AD-01 model this identity was established against",
    )
    owner_scope: Mapped[str] = mapped_column(
        PG_ENUM("global", "user", name="library_owner_scope", create_type=False),
        nullable=False, server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
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

    def __repr__(self) -> str:
        return f"<Actor id={self.id} name={self.name!r} scope={self.owner_scope}>"
