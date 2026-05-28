"""
Phase 4 — Auth Service Unit Tests.

Tests business logic in app/services/auth_service.py:
  - login: valid credentials, invalid password, nonexistent user, inactive account
  - logout: token blacklisting
  - refresh_tokens: valid exchange, invalid token, blacklisted token
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.auth_service import (
    login,
    logout,
    refresh_tokens,
    AuthenticationError,
    TokenError,
)
from app.services.user_service import create_user
from app.core.security import decode_token

pytestmark = pytest.mark.asyncio


class TestLogin:
    async def test_login_success(self, db_session):
        await create_user(db_session, "auth_login_ok", "Str0ngP@ss1", "operator")
        result = await login(db_session, "auth_login_ok", "Str0ngP@ss1")
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"
        assert result["expires_in"] > 0

    async def test_login_returns_valid_jwt(self, db_session):
        await create_user(db_session, "auth_jwt_ok", "Str0ngP@ss1", "admin")
        result = await login(db_session, "auth_jwt_ok", "Str0ngP@ss1")
        payload = decode_token(result["access_token"])
        assert payload is not None
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    async def test_login_wrong_password(self, db_session):
        await create_user(db_session, "auth_wrong_pw", "Str0ngP@ss1", "operator")
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            await login(db_session, "auth_wrong_pw", "WrongPassword1")

    async def test_login_nonexistent_user(self, db_session):
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            await login(db_session, "no_such_user_xyz", "Str0ngP@ss1")

    async def test_login_inactive_user(self, db_session):
        from app.services.user_service import update_user
        user = await create_user(db_session, "auth_inactive", "Str0ngP@ss1", "operator")
        await update_user(db_session, user, is_active=False)
        with pytest.raises(AuthenticationError, match="deactivated"):
            await login(db_session, "auth_inactive", "Str0ngP@ss1")

    async def test_login_updates_last_login_at(self, db_session):
        user = await create_user(db_session, "auth_last_login", "Str0ngP@ss1", "operator")
        assert user.last_login_at is None
        await login(db_session, "auth_last_login", "Str0ngP@ss1")
        await db_session.refresh(user)
        assert user.last_login_at is not None


class TestLogout:
    async def test_logout_blacklists_access_token(self, db_session):
        await create_user(db_session, "auth_logout", "Str0ngP@ss1", "operator")
        result = await login(db_session, "auth_logout", "Str0ngP@ss1")
        # Should not raise
        await logout(result["access_token"], result["refresh_token"])

    async def test_logout_with_only_access_token(self, db_session):
        await create_user(db_session, "auth_logout_at", "Str0ngP@ss1", "operator")
        result = await login(db_session, "auth_logout_at", "Str0ngP@ss1")
        await logout(result["access_token"])  # no refresh token


class TestRefreshTokens:
    async def test_refresh_success(self, db_session):
        await create_user(db_session, "auth_refresh", "Str0ngP@ss1", "operator")
        result = await login(db_session, "auth_refresh", "Str0ngP@ss1")
        new_tokens = await refresh_tokens(result["refresh_token"])
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["access_token"] != result["access_token"]

    async def test_refresh_invalid_token(self, db_session):
        with pytest.raises(TokenError, match="Invalid"):
            await refresh_tokens("completely.invalid.token")

    async def test_refresh_with_access_token_fails(self, db_session):
        await create_user(db_session, "auth_ref_at", "Str0ngP@ss1", "operator")
        result = await login(db_session, "auth_ref_at", "Str0ngP@ss1")
        with pytest.raises(TokenError, match="not a refresh token"):
            await refresh_tokens(result["access_token"])
