"""
ORM model for the ``dead_letter_messages`` table (§4.1 Table 15).

Migration: 0006_dead_letter_queue

WP-56 Task 1 (ledger P2.60). MOVED here from ``ivgs-api/app/models/dead_letter_queue.py``.

The worker image ships ``shared/`` (``ivgs-workers/Dockerfile:30``) and does
NOT ship ``ivgs-api/``. Five worker call sites deferred-imported
``ivgs_api.app.models`` -- a package that resolves in no image -- so every one
of them raised ``ModuleNotFoundError`` at the moment it was reached. DLQ replay
was the visible casualty: ``process_dlq`` got as far as ``_dlq_table()`` and
died there.

Ruled a MOVE rather than an HTTP rewrite (WP-56 Task 1): the DLQ is the
mechanism reached for when things are already failing, and putting a network
hop inside a recovery path adds a way for the recovery itself to fail.

``shared.database.Base`` was already the declarative base for this model, so
the move is a relocation, not a re-parenting. ``app.models`` re-exports the
class, which keeps Alembic autogenerate, ``Base.metadata.create_all()`` and
every existing ``from app.models import ...`` working unchanged.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Integer, Text, DateTime, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
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
        PG_ENUM("transient", "config", "external", "resource",
                name="failure_category", create_type=False),
        nullable=True,
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
        PG_ENUM("replayed", "discarded", "escalated",
                name="dlq_resolution", create_type=False),
        nullable=True,
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
