"""
ORM model for the ``asset_quality_scores`` table (§4.1 Table 17).

Migration: 0008_quality_scores
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Float, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class AssetQualityScore(Base):
    __tablename__ = "asset_quality_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    quality_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    safety_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    scoring_details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    decision: Mapped[str] = mapped_column(
        String(16), nullable=False,
        doc="PostgreSQL ENUM quality_decision",
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<AssetQualityScore id={self.id} asset={self.asset_id} "
            f"decision={self.decision}>"
        )
