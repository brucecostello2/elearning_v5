"""
ORM model for the ``task_retries`` table (§6.3).

Migration: 0004_retry_tracking
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class TaskRetry(Base):
    """Tracks per-task retry attempts for observability and retry policy (§6.3)."""
    __tablename__ = "task_retries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_type: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        doc="failure_category ENUM: transient | config | external | resource",
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_after_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
