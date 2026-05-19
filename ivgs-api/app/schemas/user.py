"""
User Pydantic schemas for request validation and response serialization.

Per §5.1.9 (admin-only user management) and §16.2 (RBAC roles).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    """Schema for POST /api/v1/users — create new user."""

    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-\.]+$",
        description="Unique username (3–64 chars, alphanumeric + _-.)",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Password (8–128 chars)",
    )
    role: str = Field(description="User role: admin, operator, or viewer")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"admin", "operator", "viewer"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_upper and has_lower and has_digit):
            raise ValueError(
                "Password must contain uppercase, lowercase, and digit characters"
            )
        return v


class UserUpdate(BaseModel):
    """Schema for PATCH /api/v1/users/{id} — update user."""

    role: Optional[str] = Field(default=None, description="New role assignment")
    password: Optional[str] = Field(
        default=None, min_length=8, max_length=128, description="New password"
    )
    is_active: Optional[bool] = Field(
        default=None, description="Activate/deactivate user account"
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"admin", "operator", "viewer"}
            if v not in allowed:
                raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) >= 8:
            has_upper = any(c.isupper() for c in v)
            has_lower = any(c.islower() for c in v)
            has_digit = any(c.isdigit() for c in v)
            if not (has_upper and has_lower and has_digit):
                raise ValueError(
                    "Password must contain uppercase, lowercase, and digit characters"
                )
        return v


class UserResponse(BaseModel):
    """Schema for user in API responses — never exposes password_hash."""

    id: UUID
    username: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
