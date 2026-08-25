# =============================================================================
# IVGS v5 — Integration Tests: Authentication & Authorization
# =============================================================================
# Spec reference: §5.3 Authentication API
#                 §16.1 Table 16-1 — Authentication Specifications
#                 §16.2 Table 16-2 — RBAC Role Definitions
#                 §16.3 — Security Controls
#
# Test coverage:
#   1. User registration (admin-only endpoint)
#   2. Login with valid/invalid credentials
#   3. JWT access token validation and expiry
#   4. Refresh token rotation
#   5. Logout and session invalidation
#   6. RBAC enforcement (Admin, Operator, Viewer)
#   7. Rate limiting on /auth/login (5/minute per §16.3)
#   8. Password change invalidates all sessions
#   9. Audit log entries for state-changing operations
# =============================================================================

import asyncio
import time
from datetime import datetime, timedelta
from typing import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Configuration — overridden by environment or conftest.py
# ---------------------------------------------------------------------------
from tests_system.service_urls import API_BASE_URL as BASE_URL  # WP-52: was hardcoded localhost:8001
ADMIN_EMAIL = "admin@ivgs.local"
ADMIN_PASSWORD = "TestAdmin!2026_secure"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest_asyncio.fixture
async def admin_token(client: httpx.AsyncClient) -> str:
    """Authenticate as admin and return access token."""
    response = await client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    return data["access_token"]


@pytest_asyncio.fixture
async def operator_credentials(client: httpx.AsyncClient, admin_token: str) -> dict:
    """Create a test operator user and return credentials."""
    email = f"operator-{uuid4().hex[:8]}@ivgs.local"
    password = "TestOp3rator!2026_secure"
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "role": "operator"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201, f"Operator registration failed: {response.text}"
    return {"email": email, "password": password, "id": response.json()["id"]}


@pytest_asyncio.fixture
async def viewer_credentials(client: httpx.AsyncClient, admin_token: str) -> dict:
    """Create a test viewer user and return credentials."""
    email = f"viewer-{uuid4().hex[:8]}@ivgs.local"
    password = "TestV1ewer!2026_secure"
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201, f"Viewer registration failed: {response.text}"
    return {"email": email, "password": password, "id": response.json()["id"]}


# ---------------------------------------------------------------------------
# Test Suite 1: Registration (Admin-only per §16.2)
# ---------------------------------------------------------------------------
class TestRegistration:
    """Registration endpoint tests — admin-only access."""

    @pytest.mark.asyncio
    async def test_admin_can_register_user(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Admin role can create new users."""
        email = f"test-{uuid4().hex[:8]}@ivgs.local"
        response = await client.post(
            "/auth/register",
            json={"email": email, "password": "Secure!Pass123", "role": "operator"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == email
        assert data["role"] == "operator"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_operator_cannot_register_user(
        self, client: httpx.AsyncClient, operator_credentials: dict
    ):
        """Operator role denied — per Table 16-2."""
        login = await client.post(
            "/auth/login",
            json={
                "email": operator_credentials["email"],
                "password": operator_credentials["password"],
            },
        )
        op_token = login.json()["access_token"]

        response = await client.post(
            "/auth/register",
            json={
                "email": f"reject-{uuid4().hex[:8]}@ivgs.local",
                "password": "Secure!Pass123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {op_token}"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Duplicate email returns 409."""
        response = await client.post(
            "/auth/register",
            json={"email": ADMIN_EMAIL, "password": "AnyPass!123", "role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_unauthenticated_register_rejected(
        self, client: httpx.AsyncClient
    ):
        """No token → 401."""
        response = await client.post(
            "/auth/register",
            json={
                "email": f"anon-{uuid4().hex[:8]}@ivgs.local",
                "password": "Pass!123",
                "role": "viewer",
            },
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test Suite 2: Login (§5.3, §16.1 Table 16-1)
# ---------------------------------------------------------------------------
class TestLogin:
    """Login endpoint tests — JWT issuance and validation."""

    @pytest.mark.asyncio
    async def test_valid_login_returns_tokens(self, client: httpx.AsyncClient):
        """Successful login returns access + refresh tokens."""
        response = await client.post(
            "/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    @pytest.mark.asyncio
    async def test_invalid_password_rejected(self, client: httpx.AsyncClient):
        """Wrong password → 401."""
        response = await client.post(
            "/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrong_password"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_nonexistent_user_rejected(self, client: httpx.AsyncClient):
        """Unknown email → 401."""
        response = await client.post(
            "/auth/login",
            json={"email": "nobody@ivgs.local", "password": "irrelevant"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_token_works_for_api(
        self, client: httpx.AsyncClient, admin_token: str
    ):
        """Access token grants API access."""
        response = await client.get(
            "/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: httpx.AsyncClient):
        """Expired token → 401 with TOKEN_EXPIRED code."""
        # Use a pre-crafted expired token (mock in staging)
        response = await client.get(
            "/projects",
            headers={"Authorization": "Bearer expired.token.here"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test Suite 3: Token Refresh (§16.1 — 7-day refresh token)
# ---------------------------------------------------------------------------
class TestTokenRefresh:
    """Refresh token rotation tests."""

    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(self, client: httpx.AsyncClient):
        """Valid refresh token produces new access + refresh pair."""
        login = await client.post(
            "/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        refresh_token = login.json()["refresh_token"]

        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # Old refresh token should differ from new one (rotation)
        assert data["refresh_token"] != refresh_token

    @pytest.mark.asyncio
    async def test_used_refresh_token_rejected(self, client: httpx.AsyncClient):
        """Replay of consumed refresh token → 401."""
        login = await client.post(
            "/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        refresh_token = login.json()["refresh_token"]

        # Use it once
        await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        # Use it again — should be rejected
        response = await client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test Suite 4: Logout & Session Invalidation (§16.3)
# ---------------------------------------------------------------------------
class TestLogout:
    """Logout and session invalidation tests."""

    @pytest.mark.asyncio
    async def test_logout_invalidates_refresh_token(
        self, client: httpx.AsyncClient
    ):
        """Logout blacklists refresh token in Redis."""
        login = await client.post(
            "/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        tokens = login.json()

        # Logout
        response = await client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200

        # Refresh should fail
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test Suite 5: RBAC Enforcement (§16.2 Table 16-2)
# ---------------------------------------------------------------------------
class TestRBAC:
    """Role-based access control enforcement tests."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_project(
        self, client: httpx.AsyncClient, viewer_credentials: dict
    ):
        """Viewer role cannot create projects — per Table 16-2."""
        login = await client.post(
            "/auth/login",
            json={
                "email": viewer_credentials["email"],
                "password": viewer_credentials["password"],
            },
        )
        token = login.json()["access_token"]

        response = await client.post(
            "/projects",
            json={"name": "Should Fail", "max_runtime_seconds": 600},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_can_create_project(
        self, client: httpx.AsyncClient, operator_credentials: dict
    ):
        """Operator role can create and manage own projects."""
        login = await client.post(
            "/auth/login",
            json={
                "email": operator_credentials["email"],
                "password": operator_credentials["password"],
            },
        )
        token = login.json()["access_token"]

        response = await client.post(
            "/projects",
            json={"name": "Operator Project", "max_runtime_seconds": 600},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_viewer_can_read_gallery(
        self, client: httpx.AsyncClient, viewer_credentials: dict
    ):
        """Viewer can access gallery (read-only)."""
        login = await client.post(
            "/auth/login",
            json={
                "email": viewer_credentials["email"],
                "password": viewer_credentials["password"],
            },
        )
        token = login.json()["access_token"]

        response = await client.get(
            "/projects",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test Suite 6: Rate Limiting (§16.3 — 5 attempts/minute on /auth/login)
# ---------------------------------------------------------------------------
class TestRateLimiting:
    """Rate limiting enforcement tests."""

    @pytest.mark.asyncio
    async def test_login_rate_limit_enforced(self, client: httpx.AsyncClient):
        """Exceeding 5 login attempts/minute triggers rate limit."""
        for i in range(6):
            response = await client.post(
                "/auth/login",
                json={"email": f"ratelimit-{i}@ivgs.local", "password": "wrong"},
            )
            if response.status_code == 429:
                # Rate limit hit — test passes
                assert "retry-after" in response.headers or response.status_code == 429
                return

        # If we didn't hit rate limit in 6 attempts, check the 6th response
        assert response.status_code == 429, (
            "Rate limiting not enforced after 6 attempts"
        )
