"""
ORM model for the ``render_segments`` table (§6.1 Stage 8).

Migration: 0009_render_segments
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class RenderSegment(Base):
    """Individual render segment within a final render job (§6.1 Stage 8)."""
    __tablename__ = "render_segments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    output_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    output_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending",
        doc="segment_status ENUM: pending | rendering | complete | failed",
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
