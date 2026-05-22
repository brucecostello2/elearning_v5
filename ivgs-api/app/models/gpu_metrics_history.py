"""
ORM model for the ``gpu_metrics_history`` TimescaleDB hypertable (§12.3/§13.2).

Migration: 0010_gpu_metrics
Note: This is a TimescaleDB hypertable partitioned by recorded_at with 30-day retention.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Float, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class GpuMetricsHistory(Base):
    """
    Time-series GPU metrics stored in a TimescaleDB hypertable (§13.2).

    Recorded every 30 seconds by the collect_gpu_fleet_metrics periodic task.
    Auto-pruned after 30 days by TimescaleDB retention policy.
    """
    __tablename__ = "gpu_metrics_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=text("uuid_generate_v4()"),
        primary_key=True,
    )
    gpu_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gpu_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    gpu_util_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mem_util_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power_draw_w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    active_job_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    queue_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
