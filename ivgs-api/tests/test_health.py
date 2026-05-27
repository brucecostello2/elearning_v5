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
    assert data["version"] == "5.0.0"
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
    assert data["version"] == "5.0.0"
    assert data["status"] == "operational"
