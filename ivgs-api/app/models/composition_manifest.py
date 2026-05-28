"""
ORM model for the ``composition_manifests`` table (§6.1 Stage 4).

Migration: 0007_composition_manifests
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class CompositionManifest(Base):
    """
    Composition manifest — single source of truth for rendering (§6.1 Stage 4).

    States: draft → locked → rendered | invalid
    Once locked, a manifest is immutable; modifications require a new manifest.
    """
    __tablename__ = "composition_manifests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    manifest_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolution_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolution_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    framerate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_sample_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timeline: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        PG_ENUM("draft", "locked", "rendered", "invalid",
                name="manifest_status", create_type=False),
        nullable=False, server_default="draft",
        doc="manifest_status ENUM: draft | locked | rendered | invalid",
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    rendered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
