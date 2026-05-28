"""
ORM model for the ``pipeline_checkpoints`` table (§4.1 Table 10).

Migration: 0002_pipeline_checkpoints
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class PipelineCheckpoint(Base):
    __tablename__ = "pipeline_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_index: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    checkpoint_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    output_refs: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    version_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM("pending", "complete", "failed", "skipped",
                name="checkpoint_status", create_type=False),
        nullable=False, server_default="pending",
        doc="PostgreSQL ENUM checkpoint_status",
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # ── Relationships ──
    job = relationship("RenderJob", back_populates="checkpoints")

    __table_args__ = (
        Index("ix_pipeline_checkpoints_job_stage", "job_id", "stage_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<PipelineCheckpoint id={self.id} job={self.job_id} "
            f"stage={self.stage_name} status={self.status}>"
        )
