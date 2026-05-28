"""
ORM models for ``gpu_nodes`` and ``gpu_reservations`` tables (§4.1 Tables 11–12).

Migration: 0003_gpu_registry
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, DateTime, ForeignKey, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base


class GpuNode(Base):
    __tablename__ = "gpu_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    node_hostname: Mapped[str] = mapped_column(String(64), nullable=False)
    gpu_index: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_model: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    total_vram_mb: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    power_tdp_w: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        doc="GPU thermal design power in watts. Per spec Appendix C.4. "
            "Added by migration 0016 per GPU Fleet Monitoring Spec v1.1.",
    )
    compute_capability: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM("online", "offline", "draining",
                name="gpu_node_status", create_type=False),
        nullable=False, server_default="online",
        doc="PostgreSQL ENUM gpu_node_status",
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ──
    reservations = relationship(
        "GpuReservation",
        back_populates="gpu_node",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "node_hostname", "gpu_index", name="uq_gpu_nodes_host_index",
        ),
    )


    @property
    def used_vram_mb(self) -> int:
        """Calculate used VRAM from active reservations."""
        if not self.reservations:
            return 0
        return sum(
            r.reserved_vram_mb
            for r in self.reservations
            if r.status in ("reserved", "active")
        )

    @property
    def available_vram_mb(self) -> int:
        """Calculate available VRAM."""
        total = self.total_vram_mb or 0
        return total - self.used_vram_mb

    def __repr__(self) -> str:
        return (
            f"<GpuNode id={self.id} host={self.node_hostname} "
            f"gpu={self.gpu_index} status={self.status}>"
        )


class GpuReservation(Base):
    __tablename__ = "gpu_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    gpu_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gpu_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    reserved_vram_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        PG_ENUM("reserved", "active", "released", "expired",
                name="reservation_status", create_type=False),
        nullable=False, server_default="reserved",
        doc="PostgreSQL ENUM reservation_status",
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ──
    gpu_node = relationship("GpuNode", back_populates="reservations")

    def __repr__(self) -> str:
        return (
            f"<GpuReservation id={self.id} node={self.gpu_node_id} "
            f"vram={self.reserved_vram_mb}MB status={self.status}>"
        )
