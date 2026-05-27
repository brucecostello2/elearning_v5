"""
ORM model for the ``backup_records`` table (§14).

Migration: 0013_backup_records
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, BigInteger, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class BackupRecord(Base):
    """
    Record of a backup operation (§14.1).

    Backup types: full_database | wal_archive | asset_backup | config_backup | vm_snapshot
    Status flow: running → completed → verified | failed
    """
    __tablename__ = "backup_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    backup_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        doc="backup_type ENUM: full_database | wal_archive | asset_backup | config_backup | vm_snapshot",
    )
    scope: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="running",
        doc="backup_status ENUM: running | completed | failed | verified",
    )
    backup_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    verification_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    retention_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
