"""
Authentication dependencies for FastAPI route protection.

Provides:
- get_current_user: Extracts and validates JWT from Bearer header
- get_current_active_user: Ensures the user account is active
- blacklist_token: Adds a token to the Redis blacklist (logout)
"""
import hmac
import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from shared.redis_client import redis_client
from app.models.user import User
from app.core.security import decode_token
from shared.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    """
    FastAPI dependency: extract user from Bearer JWT.

    Checks:
    1. Token decodes successfully
    2. Token type is "access"
    3. Token is not blacklisted in Redis
    4. User exists in database
    5. User account is active (is_active)
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "code": "AUTHENTICATION_REQUIRED",
                "message": "Invalid authentication credentials",
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": "Invalid token type — expected access token",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: Optional[str] = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    # Check Redis blacklist
    blacklist_key = f"token:blacklist:{payload.get('jti', token)}"
    if await redis_client.exists(blacklist_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": "Token has been revoked",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "User account is deactivated",
                }
            },
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency alias that ensures the user is active (already checked)."""
    return current_user


async def blacklist_token(jti: str, expire_seconds: int = 3600) -> None:
    """
    Add a token JTI to the Redis blacklist for logout.

    Args:
        jti: JWT token ID (jti claim)
        expire_seconds: TTL for blacklist entry (default: 1 hour)
    """
    blacklist_key = f"token:blacklist:{jti}"
    await redis_client.set(blacklist_key, "1", ex=expire_seconds)
    logger.info("Token blacklisted: jti=%s for %ss", jti, expire_seconds)


async def blacklist_all_user_tokens(user_id: str) -> None:
    """
    Blacklist all tokens for a user by setting a user-level invalidation marker.

    Used when password changes to invalidate all sessions.
    """
    invalidation_key = f"user:invalidated_before:{user_id}"
    now_ts = str(int(__import__("time").time()))
    await redis_client.set(invalidation_key, now_ts, ex=86400 * 8)
    logger.info("All tokens invalidated for user_id=%s", user_id)


async def get_service_or_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Dual-mode auth for internal worker -> API endpoints.

    If the Bearer token matches the configured internal service token, resolve it to the seeded
    svc-pipeline service account (app/scripts/seed_service_account.py). Otherwise fall back to the
    normal user-JWT path (get_current_user), unchanged. Apply only to endpoints the worker fleet
    calls; user-facing endpoints keep get_current_user.
    """
    token = credentials.credentials
    if hmac.compare_digest(token, settings.IVGS_SERVICE_TOKEN):
        result = await db.execute(select(User).where(User.username == "svc-pipeline"))
        service_user = result.scalar_one_or_none()
        if service_user is None:
            logger.error(
                "service token accepted but svc-pipeline account is missing; run: "
                "docker compose exec api python -m app.scripts.seed_service_account"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "SERVICE_ACCOUNT_MISSING", "message": "Service account not provisioned"}},
            )
        if not service_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "SERVICE_ACCOUNT_DISABLED", "message": "Service account is disabled"}},
            )
        return service_user
    return await get_current_user(credentials=credentials, db=db)
