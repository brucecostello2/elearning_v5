"""
IVGS v5 API — Main application entry point.

FastAPI application with authentication, RBAC, audit logging,
rate limiting, and standardized error handling.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import logging
import os

from shared.database import check_db_connection, dispose_engine
from shared.redis_client import redis_client
from shared.seaweedfs_client import seaweedfs_client
from shared.logging_config import setup_logging

from app.middleware.audit import AuditMiddleware
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.api.v1 import api_v1_router
from app.api.ad01_ingest import ad01_router

setup_logging(service_name="ivgs-api")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager — startup and shutdown logic."""
    logger.info("Starting IVGS v5 API...")

    if not await check_db_connection():
        logger.error("Database connection failed at startup")
        raise RuntimeError("Database not available")

    if not await redis_client.ping():
        logger.error("Redis connection failed at startup")
        raise RuntimeError("Redis not available")

    if not await seaweedfs_client.check_health():
        logger.warning("SeaweedFS not available at startup — non-fatal")

    logger.info("IVGS v5 API started successfully")
    yield

    logger.info("Shutting down IVGS v5 API...")
    await redis_client.close()
    await seaweedfs_client.close()
    await dispose_engine()
    logger.info("IVGS v5 API shutdown complete")


app = FastAPI(
    title="IVGS v5 API",
    description="Instructional Video Generation System — Version 5.0",
    version="5.1.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

# --- Middleware stack (order matters: outermost first) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        f"http://{os.environ.get('FRONTEND_HOST', 'localhost')}:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)

# --- Routers ---
app.include_router(api_v1_router, prefix="/api/v1")
# AD-04 seam 1: MBCP posts to {base}/ad01/v1/certified-models — root-mounted.
app.include_router(ad01_router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — API information."""
    return {
        "name": "IVGS v5 API",
        "version": "5.0.0",
        "status": "operational",
        "docs": "/api/v1/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("UVICORN_PORT", "8001")),
        reload=False,
        log_config=None,
    )
