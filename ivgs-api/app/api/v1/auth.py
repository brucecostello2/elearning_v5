"""
Authentication endpoints per §5.1.1.

POST /api/v1/auth/login  — Issue Bearer token
POST /api/v1/auth/logout — Invalidate session token
POST /api/v1/auth/refresh — Issue new token before expiry
GET  /api/v1/auth/me     — Current user info
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    LogoutResponse,
    MeResponse,
)
from app.services.auth_service import (
    login,
    logout,
    refresh_tokens,
    AuthenticationError,
    TokenError,
)
from app.core.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain JWT tokens",
    responses={
        401: {"description": "Invalid credentials"},
        429: {"description": "Rate limited — too many login attempts"},
    },
)
async def auth_login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Issue Bearer token. Body: {username, password}.
    Returns: {access_token, refresh_token, token_type, expires_in}.
    """
    try:
        result = await login(db, body.username, body.password)
        await db.commit()
        return result
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTHENTICATION_REQUIRED",
                    "message": str(e),
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Invalidate current session tokens",
)
async def auth_logout(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Invalidate session token. Blacklists the Bearer token in Redis.
    """
    auth_header = request.headers.get("authorization", "")
    access_token = auth_header.replace("Bearer ", "") if auth_header else ""

    await logout(access_token=access_token)
    logger.info("User logged out: username=%s", current_user.username)
    return LogoutResponse()


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token using refresh token",
    responses={
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def auth_refresh(body: RefreshRequest):
    """
    Issue new token pair before expiry.
    Old refresh token is invalidated after exchange.
    """
    try:
        result = await refresh_tokens(body.refresh_token)
        return result
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": str(e),
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user info",
)
async def auth_me(current_user: User = Depends(get_current_user)):
    """Return current authenticated user's profile."""
    return MeResponse(
        id=str(current_user.id),
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
    )
