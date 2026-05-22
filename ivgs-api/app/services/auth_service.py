"""
Authentication service: login, logout, refresh, session management.

Per §5.3 and §16.1:
- Login validates credentials, returns access + refresh tokens
- Logout blacklists both tokens in Redis
- Refresh exchanges a valid refresh token for new token pair
- Password change invalidates all existing sessions
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.auth import blacklist_token
from app.services.user_service import get_user_by_username
from shared.config import settings
from shared.redis_client import redis_client

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when login credentials are invalid."""



class TokenError(Exception):
    """Raised when refresh token is invalid or expired."""



async def login(
    db: AsyncSession,
    username: str,
    password: str,
) -> dict:
    """
    Authenticate user and return token pair.

    Returns:
        {
            "access_token": "...",
            "refresh_token": "...",
            "token_type": "bearer",
            "expires_in": 3600
        }

    Raises:
        AuthenticationError: If credentials are invalid or account is inactive.
    """
    user = await get_user_by_username(db, username)

    if user is None:
        logger.warning(f"Login failed: user not found — username={username}")
        raise AuthenticationError("Invalid username or password")

    if not user.is_active:
        logger.warning(f"Login failed: account inactive — username={username}")
        raise AuthenticationError("Account is deactivated")

    if not verify_password(password, user.password_hash):
        logger.warning(f"Login failed: invalid password — username={username}")
        raise AuthenticationError("Invalid username or password")

    # Generate token pair
    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
    )
    refresh_token = create_refresh_token(
        user_id=str(user.id),
        role=user.role,
    )

    # Store refresh token JTI in Redis for invalidation support
    refresh_payload = decode_token(refresh_token)
    if refresh_payload and "jti" in refresh_payload:
        refresh_key = f"refresh_token:{refresh_payload['jti']}"
        ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await redis_client.set(refresh_key, str(user.id), ex=ttl)

    # Update last_login_at
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"Login successful: username={username} user_id={user.id}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def logout(access_token: str, refresh_token: Optional[str] = None) -> None:
    """
    Logout by blacklisting the access token JTI (and optionally refresh token).

    The blacklist TTL matches the token's remaining validity.
    """
    # Blacklist access token
    access_payload = decode_token(access_token)
    if access_payload and "jti" in access_payload:
        await blacklist_token(
            jti=access_payload["jti"],
            expire_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # Blacklist refresh token if provided
    if refresh_token:
        refresh_payload = decode_token(refresh_token)
        if refresh_payload and "jti" in refresh_payload:
            await blacklist_token(
                jti=refresh_payload["jti"],
                expire_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            )
            # Remove from valid refresh tokens
            refresh_key = f"refresh_token:{refresh_payload['jti']}"
            await redis_client.delete(refresh_key)

    logger.info("Logout completed — tokens blacklisted")


async def refresh_tokens(refresh_token_str: str) -> dict:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token is blacklisted after successful exchange.

    Returns:
        Same format as login() response.

    Raises:
        TokenError: If refresh token is invalid, expired, or blacklisted.
    """
    payload = decode_token(refresh_token_str)

    if payload is None:
        raise TokenError("Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise TokenError("Token is not a refresh token")

    jti = payload.get("jti", "")
    user_id = payload.get("sub")
    role = payload.get("role")

    if not user_id or not role:
        raise TokenError("Invalid refresh token payload")

    # Check if token is blacklisted
    blacklist_key = f"token:blacklist:{jti}"
    if await redis_client.exists(blacklist_key):
        raise TokenError("Refresh token has been revoked")

    # Verify token is in the valid set
    refresh_key = f"refresh_token:{jti}"
    stored_user_id = await redis_client.get(refresh_key)
    if stored_user_id is None:
        raise TokenError("Refresh token not found — may have been invalidated")

    if stored_user_id != user_id:
        raise TokenError("Refresh token user mismatch")

    # Blacklist old refresh token
    await blacklist_token(jti=jti, expire_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    await redis_client.delete(refresh_key)

    # Issue new token pair
    new_access_token = create_access_token(user_id=user_id, role=role)
    new_refresh_token = create_refresh_token(user_id=user_id, role=role)

    # Store new refresh token
    new_refresh_payload = decode_token(new_refresh_token)
    if new_refresh_payload and "jti" in new_refresh_payload:
        new_refresh_key = f"refresh_token:{new_refresh_payload['jti']}"
        ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await redis_client.set(new_refresh_key, user_id, ex=ttl)

    logger.info(f"Token refresh successful: user_id={user_id}")

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
