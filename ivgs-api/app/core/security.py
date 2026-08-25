"""
Security utilities: password hashing (bcrypt cost 12) and JWT management.

Per §16.1:
- Access tokens: JWT HS256, 1-hour expiration
- Refresh tokens: JWT HS256, 7-day expiration
- Password storage: bcrypt cost factor 12

WP-52: passlib retired, `bcrypt` called directly.
`passlib==1.7.4` (last release 2020-10, unmaintained) reads
`bcrypt.__about__.__version__`, an attribute bcrypt 4.x removed, so every
process that imported this module logged a trapped traceback at startup.
It also `import crypt`s at module scope, and `crypt` is gone in Python 3.13 --
the next base-image bump would have broken authentication outright rather than
noisily. The wire format is unchanged: `$2b$`, cost 12, so every hash already
in `users.password_hash` keeps verifying.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

import bcrypt
from jose import JWTError, jwt

from shared.config import settings

logger = logging.getLogger(__name__)

# Cost factor 12 per §16.1. bcrypt's own algorithm ignores everything past the
# first 72 bytes of the password; passlib truncated identically, so behaviour
# for the 128-character passwords the schemas permit is unchanged.
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt with cost factor 12."""
    password_bytes = password.encode("utf-8")
    if b"\x00" in password_bytes:
        # passlib rejected NULL bytes; bcrypt does not. Keep rejecting them --
        # a C-string truncation here would silently shorten the password.
        raise ValueError("bcrypt does not allow NULL bytes in password")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against its bcrypt hash.

    Returns False -- never raises -- for a missing or malformed stored hash.
    passlib raised `UnknownHashError`/`ValueError` there, which surfaced at the
    one caller (`auth_service.authenticate_user`) as a 500 on a login attempt.
    A corrupt hash is a failed login, logged, not a stack trace to the client.
    """
    if not hashed_password or not plain_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError) as e:
        logger.warning("Password verification failed on a malformed stored hash: %s", e)
        return False


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    username: str | None = None,
) -> str:
    """
    Create a JWT access token.

    Payload: {sub: user_id, role: role, exp, iat, jti, type: "access"}
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": str(user_id),
        "role": role,
        "username": username,
        "exp": expire,
        "iat": now,
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, role: str,
    username: str | None = None,
) -> str:
    """
    Create a JWT refresh token with 7-day expiration.

    Payload: {sub: user_id, role: role, exp, iat, jti, type: "refresh"}
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "role": role,
        "username": username,
        "exp": expire,
        "iat": now,
        "jti": uuid.uuid4().hex,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT token.

    Returns decoded payload dict if valid, None on any error.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None
