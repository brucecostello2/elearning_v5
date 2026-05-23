"""
ORM model for the ``users`` table (§4.1 Table 6).

Migration: 0001_initial_core
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False,
        doc="One of: admin, operator, viewer (PostgreSQL ENUM user_role)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
        doc="Soft-disable flag — False blocks login (§4.1 Table 6, added 0015)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
