"""
Authentication Pydantic schemas for login, token, and refresh operations.

Per §5.1.1 and §16.1.
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Schema for POST /api/v1/auth/login."""

    username: str = Field(min_length=1, max_length=64, description="Username")
    password: str = Field(min_length=1, max_length=128, description="Password")


class TokenResponse(BaseModel):
    """
    Token response per §5.1.1.

    Returns: {access_token, refresh_token, token_type, expires_in}
    """

    access_token: str = Field(description="JWT access token (1-hour expiry)")
    refresh_token: str = Field(description="JWT refresh token (7-day expiry)")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Access token TTL in seconds")


class RefreshRequest(BaseModel):
    """Schema for POST /api/v1/auth/refresh."""

    refresh_token: str = Field(description="Current refresh token to exchange")


class LogoutResponse(BaseModel):
    """Response for POST /api/v1/auth/logout."""

    message: str = Field(default="Logged out successfully")


class MeResponse(BaseModel):
    """Response for GET /api/v1/auth/me — current user info."""

    id: str
    username: str
    role: str
    is_active: bool
