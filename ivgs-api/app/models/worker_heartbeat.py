"""
ORM model for the ``worker_heartbeats`` table (§12.2).

Migration: 0005_worker_heartbeats
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class WorkerHeartbeat(Base):
    """Tracks Celery worker heartbeats for dead-worker detection (§12.2)."""
    __tablename__ = "worker_heartbeats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_hostname: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    gpu_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("render_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    heartbeat_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM("alive", "suspected_dead", "confirmed_dead",
                name="heartbeat_status", create_type=False),
        nullable=False, server_default="alive",
        doc="heartbeat_status ENUM: alive | suspected_dead | confirmed_dead",
    )
