"""
ORM model for the ``audit_log`` table (§4.1 Table 9).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, DateTime, ForeignKey, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    before_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    after_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    client_ip: Mapped[Optional[str]] = mapped_column(
        INET, nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
        Index("ix_audit_log_timestamp", text("timestamp DESC")),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action_type} "
            f"resource={self.resource_type}/{self.resource_id}>"
        )
