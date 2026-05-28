"""
ORM model for the ``storage_quotas`` table (§10.1).

Migration: 0012_storage_quotas
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, BigInteger, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class StorageQuota(Base):
    """
    Storage quota per entity (project or user) across the 4-tier storage system (§10.1).

    Tiers: hot → warm → cold → archived → deleted
    Alert at configurable threshold (default 80%).
    """
    __tablename__ = "storage_quotas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    max_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0"),
    )
    tier: Mapped[Optional[str]] = mapped_column(
        PG_ENUM("hot", "warm", "cold", "archived", "deleted",
                name="storage_tier", create_type=False),
        nullable=True,
        doc="storage_tier ENUM: hot | warm | cold | archived | deleted",
    )
    alert_threshold_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("80"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
