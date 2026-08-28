"""
Health check endpoint per §5.1.1.

GET /api/v1/health — No authentication required.
Returns database, Redis, and SeaweedFS connectivity status.
"""
import logging
import time

import os

from fastapi import APIRouter, status
from starlette.responses import JSONResponse

from shared.database import check_db_connection
from shared.redis_client import redis_client
from shared.seaweedfs_client import seaweedfs_client
from app.schemas.base import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)

def build_ref() -> str:
    """The build this image was made from, or "unknown".

    Set by `ARG IVGS_BUILD_REF` -> `ENV` in the Dockerfile at build time. NOT
    `IVGS_API_TAG`: that is injected by the service-level `env_file` and
    dev/CLAUDE.md S6 documents it as a known liar -- measured reporting
    v5.1.14-stream-b on an image that was v5.27.0-motion.
    """
    return os.environ.get("IVGS_BUILD_REF", "unknown")


def build_sha() -> str:
    return os.environ.get("IVGS_BUILD_SHA", "unknown")


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
        # WP-IVGS-08 Task 3(a). Was the string literal "5.0.0", which had been
        # wrong since at least v5.1 and read as authoritative because it sits
        # in the health payload. It now reports the build the image was
        # actually made from -- or "unknown", which is honest, where the old
        # literal was confidently false.
        version=build_ref(),
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


@router.get("/version", summary="What build is this, really")
async def version() -> dict:
    """WP-IVGS-08 Task 3(a). The route WP-IVGS-03 S2.4 declined to add.

    It declined for a good reason: at the time nothing inside the image knew
    its own build, so the only candidate value was the stale env-injected
    `IVGS_API_TAG`, and an endpoint reading that would have shipped a
    confident falsehood. The Dockerfile now bakes the real tag and commit sha
    at build time, so the endpoint has something true to report.

    `"unknown"` is a real answer here, not a placeholder: it means the image
    was built without the build args, which is exactly the state an operator
    needs to be able to see.
    """
    return {
        "build_ref": build_ref(),
        "commit_sha": build_sha(),
        "service": "ivgs-api",
    }
