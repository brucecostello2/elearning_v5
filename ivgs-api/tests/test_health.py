import os
"""
Health check endpoint tests.

Covers: healthy response, degraded response, service status fields.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_success(client: AsyncClient):
    """Health check returns 200 with all services connected."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    # WP-IVGS-08 Task 3(a). This asserted the string literal "5.0.0" that
    # `health.py` hardcoded -- so the test PINNED THE DEFECT: the running image
    # was v5.27.0-motion while this endpoint said 5.0.0, and this assertion
    # would have failed had anyone made it truthful.
    #
    # `/health` now reports the build baked in at image build time. In a test
    # process there is no build, so "unknown" is correct -- and "unknown" is a
    # real answer, not a placeholder: it means the image was built without the
    # build args, a state an operator must be able to see.
    assert data["version"] == os.environ.get("IVGS_BUILD_REF", "unknown")
    assert data["version"] != "5.0.0", "the hardcoded literal must not come back"
    assert "database" in data
    assert "redis" in data
    assert "seaweedfs" in data


@pytest.mark.asyncio
async def test_health_check_no_auth_required(client: AsyncClient):
    """Health check does not require authentication — no Bearer token needed."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_structure(client: AsyncClient):
    """Verify health response matches HealthResponse schema."""
    response = await client.get("/api/v1/health")
    data = response.json()

    # Top-level fields
    assert "status" in data
    assert "version" in data

    # Service status fields
    for service in ("database", "redis", "seaweedfs"):
        assert service in data
        svc = data[service]
        assert "status" in svc
        assert svc["status"] in ("connected", "disconnected", "degraded")


@pytest.mark.asyncio
async def test_health_database_latency(client: AsyncClient):
    """Health check includes latency_ms for database."""
    response = await client.get("/api/v1/health")
    data = response.json()
    if data["database"]["latency_ms"] is not None:
        assert data["database"]["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Root endpoint returns API info."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "IVGS v5 API"
    # WP-IVGS-08 Task 3(a). This asserted the string literal "5.0.0" that
    # `health.py` hardcoded -- so the test PINNED THE DEFECT: the running image
    # was v5.27.0-motion while this endpoint said 5.0.0, and this assertion
    # would have failed had anyone made it truthful.
    #
    # `/health` now reports the build baked in at image build time. In a test
    # process there is no build, so "unknown" is correct -- and "unknown" is a
    # real answer, not a placeholder: it means the image was built without the
    # build args, a state an operator must be able to see.
    assert data["version"] == os.environ.get("IVGS_BUILD_REF", "unknown")
    assert data["version"] != "5.0.0", "the hardcoded literal must not come back"
    assert data["status"] == "operational"
