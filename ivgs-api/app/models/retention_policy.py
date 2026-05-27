"""
ORM model for the ``retention_policies`` table (§4.1 Table 20).

Migration: 0011_retention_policies
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    hot_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30"),
    )
    warm_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("90"),
    )
    cold_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("365"),
    )
    archive_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    delete_after_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    applies_to: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
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

    def __repr__(self) -> str:
        return (
            f"<RetentionPolicy id={self.id} name={self.name!r} "
            f"default={self.is_default}>"
        )
