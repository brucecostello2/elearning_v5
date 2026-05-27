"""
Phase 1: Basic rate limiting tests.

Tests the rate limiting middleware enforces limits correctly:
- 5 requests per minute for login endpoints (per IP)
- 60 requests per minute for default endpoints (per user)
- Sliding window via Redis incr/expire
"""

import pytest
from httpx import AsyncClient


# ===================================================================
# Login rate limit: 5 attempts/min per IP
# ===================================================================


@pytest.mark.asyncio
async def test_rate_limit_allows_under_threshold(
    client: AsyncClient, db_session, operator_token: str
):
    """4 login requests should all succeed (not rate-limited)."""
    for i in range(4):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": f"nobody_{i}", "password": "wrong"},
        )
        # May get 401 (bad credentials) but NOT 429
        assert response.status_code != 429, f"Request {i+1} was rate-limited prematurely"


@pytest.mark.asyncio
async def test_rate_limit_blocks_at_threshold(
    client: AsyncClient, db_session, operator_token: str
):
    """6th login request should be rate-limited (429)."""
    statuses = []
    for i in range(6):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": f"nobody_{i}", "password": "wrong"},
        )
        statuses.append(response.status_code)

    # First 5 should not be 429
    for idx, s in enumerate(statuses[:5]):
        assert s != 429, f"Request {idx+1}/5 was rate-limited prematurely"

    # 6th should be 429
    assert statuses[5] == 429, f"6th request should be 429, got {statuses[5]}"


@pytest.mark.asyncio
async def test_rate_limit_response_body(
    client: AsyncClient, db_session, operator_token: str
):
    """Rate-limited response should include error code and Retry-After header."""
    for i in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "wrong"},
        )

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    assert response.status_code == 429
    data = response.json()
    assert data["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in response.headers


@pytest.mark.asyncio
async def test_rate_limit_get_requests_exempt(
    client: AsyncClient, db_session, operator_token: str
):
    """GET requests should not be rate-limited (middleware skips them)."""
    for i in range(70):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # Should be 200 (or auth error) but never 429
        assert response.status_code != 429, f"GET request {i+1} was rate-limited"


@pytest.mark.asyncio
async def test_default_bucket_60_per_minute(
    client: AsyncClient, db_session, operator_token: str
):
    """Non-login POST endpoints allow 60 requests/minute per user."""
    # POST to a non-login, non-trigger endpoint
    # Use a dummy path that goes through rate limiter but doesn't need real logic
    statuses = []
    for i in range(61):
        response = await client.post(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": f"proj_{i}"},
        )
        statuses.append(response.status_code)

    # First 60 should not be 429
    rate_limited_before_60 = [s for s in statuses[:60] if s == 429]
    assert len(rate_limited_before_60) == 0, f"Some of first 60 requests were rate-limited: {rate_limited_before_60}"

    # 61st should be 429
    assert statuses[60] == 429, f"61st request should be 429, got {statuses[60]}"
