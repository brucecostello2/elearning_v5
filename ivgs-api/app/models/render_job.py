"""
ORM model for the ``render_jobs`` table (§4.1 Table 7).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, text,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    job_type: Mapped[str] = mapped_column(
        PG_ENUM("transcript_refinement", "storyboard_generation",
                "image_generation", "video_generation", "animation_generation",
                "tts_audio", "talking_head_render", "prototype_draft",
                "final_render", "localisation",
                name="job_type", create_type=False),
        nullable=False,
        doc="PostgreSQL ENUM job_type — 10 values",
    )
    node_id: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM("pending", "running", "success", "failed",
                name="job_status", create_type=False),
        nullable=False, server_default="pending",
        doc="PostgreSQL ENUM job_status",
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    max_retries: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    failure_category: Mapped[Optional[str]] = mapped_column(
        PG_ENUM("transient", "config", "external", "resource",
                name="failure_category", create_type=False),
        nullable=True,
        doc="PostgreSQL ENUM failure_category",
    )
    # WP-45 Task 6(c) / migration 0028. Which language variant this job renders.
    # NULL means the project's source language. Attribution only - the per-language
    # progress figure is DERIVED from this job's pipeline_checkpoints every time
    # it is asked for, never stored (WP-43 D-1, ruled).
    language_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
    )
    resume_from_stage: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="Stage name this resume job picked up from (BUG-CHECKPOINT-STAGE). "
            "NULL for non-resume jobs. Free text, not an enum.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # ── Relationships ──
    project = relationship("Project", back_populates="render_jobs")
    checkpoints = relationship(
        "PipelineCheckpoint",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<RenderJob id={self.id} type={self.job_type} "
            f"status={self.status}>"
        )
