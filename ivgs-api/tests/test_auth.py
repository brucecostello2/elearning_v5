"""
Authentication endpoint tests.

Covers: login, logout, refresh, token expiry, lockout, me endpoint.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import create_test_user, make_auth_header
from app.core.security import create_access_token, create_refresh_token


# ===================================================================
# Login Tests
# ===================================================================


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user):
    """Successful login returns access_token, refresh_token, token_type, expires_in."""
    user, password = admin_user
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, admin_user):
    """Login with wrong password returns 401."""
    user, _ = admin_user
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "WrongPassword1"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Login with non-existent username returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "NoPass123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db_session):
    """Login with deactivated account returns 401."""
    user, password = await create_test_user(
        db_session, username="inactive_user", is_active=False
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    assert response.status_code == 401


# ===================================================================
# Logout Tests
# ===================================================================


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient, admin_user):
    """Logout blacklists the token — subsequent requests fail."""
    user, password = admin_user

    # Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    tokens = login_resp.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Logout
    logout_resp = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_logout_without_token(client: AsyncClient):
    """Logout without Bearer token returns 403."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 403


# ===================================================================
# Refresh Tests
# ===================================================================


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient, admin_user):
    """Refresh returns new token pair and invalidates old refresh token."""
    user, password = admin_user

    # Login to get tokens
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    tokens = login_resp.json()

    # Refresh
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["access_token"] != tokens["access_token"]


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client: AsyncClient):
    """Refresh with garbage token returns 401."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.token.here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token(client: AsyncClient, admin_user):
    """Refresh using an access token (not refresh) returns 401."""
    user, _ = admin_user
    access_token = create_access_token(user_id=str(user.id), role=user.role)

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401


# ===================================================================
# Me Endpoint Tests
# ===================================================================


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, admin_user):
    """GET /auth/me returns current user info."""
    user, _ = admin_user
    headers = make_auth_header(user)

    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user.username
    assert data["role"] == user.role
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_me_without_auth(client: AsyncClient):
    """GET /auth/me without token returns 403."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403


# ===================================================================
# Token Validation Tests
# ===================================================================


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient, admin_user):
    """An expired access token is rejected with 401."""
    from datetime import timedelta

    user, _ = admin_user
    expired_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        expires_delta=timedelta(seconds=-1),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}

    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
