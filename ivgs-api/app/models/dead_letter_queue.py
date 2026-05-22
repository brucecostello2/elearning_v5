"""
ORM model for the ``dead_letter_messages`` table (§4.1 Table 15).

Migration: 0006_dead_letter_queue
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Integer, Text, DateTime, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class DeadLetterMessage(Base):
    __tablename__ = "dead_letter_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    original_queue: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    task_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    task_args: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    task_kwargs: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    exception_type: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    exception_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_category: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
        doc="PostgreSQL ENUM failure_category",
    )
    retry_count_exhausted: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    resolution: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
        doc="PostgreSQL ENUM dlq_resolution",
    )

    __table_args__ = (
        Index(
            "ix_dlq_category_created",
            "failure_category",
            text("created_at DESC"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DeadLetterMessage id={self.id} task={self.task_name} "
            f"category={self.failure_category}>"
        )
