"""
ORM model for the ``fallback_policies`` table (§6.3 Table 6-6, Appendix D.4).

Migration: 0014_fallback_policies
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class FallbackPolicy(Base):
    """
    4-level fallback policy per scene type (§6.3 Table 6-6).

    Scene types: action | talking_head | broll | title_card
    Each level defines a degradation strategy:
      L1 (best): ai_video
      L2: animated_still
      L3: zoom_pan
      L4 (worst): static_image
    """
    __tablename__ = "fallback_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    scene_type: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
    )
    level_1_strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    level_2_strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    level_3_strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    level_4_strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
