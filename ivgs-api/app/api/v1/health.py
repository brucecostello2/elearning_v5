"""
Health check endpoint per §5.1.1.

GET /api/v1/health — No authentication required.
Returns database, Redis, and SeaweedFS connectivity status.
"""
import logging
import time

from fastapi import APIRouter, status
from starlette.responses import JSONResponse

from shared.database import check_db_connection
from shared.redis_client import redis_client
from shared.seaweedfs_client import seaweedfs_client
from app.schemas.base import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)

router = APIRouter()


async def _check_service(check_fn, service_name: str) -> ServiceStatus:
    """Run a health check function and return status with latency."""
    start = time.monotonic()
    try:
        healthy = await check_fn()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return ServiceStatus(
            status="connected" if healthy else "disconnected",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        logger.error("Health check failed for %s: %s", service_name, e)
        return ServiceStatus(status="disconnected", latency_ms=latency_ms)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    description="Returns connectivity status for database, Redis, and SeaweedFS. No auth required.",
)
async def health_check():
    """
    GET /api/v1/health — service health check.

    Returns 200 with service status even if some services are degraded.
    The overall status reflects the worst-case component status.
    """
    db_status = await _check_service(check_db_connection, "database")
    redis_status = await _check_service(redis_client.ping, "redis")
    seaweedfs_status = await _check_service(seaweedfs_client.check_health, "seaweedfs")

    # Determine overall status
    statuses = [db_status.status, redis_status.status, seaweedfs_status.status]
    if all(s == "connected" for s in statuses):
        overall = "healthy"
    elif db_status.status == "disconnected" or redis_status.status == "disconnected":
        overall = "unhealthy"
    else:
        overall = "degraded"

    response = HealthResponse(
        status=overall,
        version="5.0.0",
        database=db_status,
        redis=redis_status,
        seaweedfs=seaweedfs_status,
    )

    http_status = (
        status.HTTP_200_OK
        if overall in ("healthy", "degraded")
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(content=response.model_dump(), status_code=http_status)
