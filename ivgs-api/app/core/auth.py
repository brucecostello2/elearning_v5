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


#: The value shipped in shared/config.py. Named here so the check below is
#: explicit rather than a string literal buried in a comparison.
_INSECURE_DEFAULT_SERVICE_TOKEN = "dev-service-token"


#: The seeded principal a service token resolves to
#: (`app/scripts/seed_service_account.py`). ⛳ A CONSTANT because RC-Q15 made it
#: load-bearing beyond authentication: `TranscriptService.update_transcript` asks
#: "is the worker writing, or a person?" to decide whether a `refined_text` is a
#: model's echo to discard or an operator's edit to honour. A caller comparing
#: that username by hand is a second copy of a security-relevant identity.
SERVICE_ACCOUNT_USERNAME = "svc-pipeline"


def is_service_principal(user: object) -> bool:
    """Is this the worker fleet writing, rather than a person?

    ⛔ RC-Q15. THE TEST IS THE AUTHENTICATED PRINCIPAL AND NOT A FLAG IN THE
    REQUEST BODY, which is the whole reason it lives here: a worker must not be
    able to present itself as a person in order to keep its paraphrase, and a
    person must not be able to claim to be the worker.
    """
    return getattr(user, "username", None) == SERVICE_ACCOUNT_USERNAME


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

    # WP-57 Task 8. `IVGS_SERVICE_TOKEN` has been unset fleet-wide since WP-44
    # D-5 flagged it, resolving to the shipped default "dev-service-token" - a
    # value that is in the repository, guarding a route the quality gate depends
    # on. Three packages carried it forward.
    #
    # THE ROUTE MUST NOT ACCEPT BOTH. Once a real token is configured, the
    # shipped default has to stop working - otherwise setting a strong value
    # changes nothing, because the published one still opens the door. The
    # comparison below is a single constant-time compare, so that already holds;
    # this guard makes it EXPLICIT and testable rather than incidental, and
    # states the property in the place someone would go to weaken it.
    #
    # It deliberately does NOT fail closed while the default is still in place.
    # Refusing service auth outright would stop the live fleet the moment this
    # deploys, before the operator has run the block that sets the value. The
    # default is refused only once a real one exists; until then its use is
    # logged loudly at every acceptance so the gap is visible rather than quiet.
    if token == _INSECURE_DEFAULT_SERVICE_TOKEN:
        if settings.IVGS_SERVICE_TOKEN != _INSECURE_DEFAULT_SERVICE_TOKEN:
            logger.warning(
                "service_token_rejected_shipped_default: a caller presented the "
                "shipped default token while a real IVGS_SERVICE_TOKEN is "
                "configured. Refused. Update that caller's environment."
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_SERVICE_TOKEN",
                        "message": "The shipped default service token is not accepted.",
                    }
                },
            )
        logger.warning(
            "service_token_is_the_shipped_default: IVGS_SERVICE_TOKEN is unset, "
            "so internal service auth is guarded by a value published in the "
            "repository (WP-44 D-5 / WP-57 Task 8). Set it on every node."
        )

    if hmac.compare_digest(token, settings.IVGS_SERVICE_TOKEN):
        result = await db.execute(select(User).where(User.username == SERVICE_ACCOUNT_USERNAME))
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
