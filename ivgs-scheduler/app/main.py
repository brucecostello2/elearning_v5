"""GPU Scheduler FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routes import router

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: setup on start, cleanup on shutdown."""
    logger.info("GPU Scheduler starting on port %s", settings.port)
    Base.metadata.create_all(bind=engine)  # Ensure tables exist (read-only DDL)
    yield
    logger.info("GPU Scheduler shutting down")


app = FastAPI(
    title="IVGS GPU Scheduler",
    description="VRAM-aware GPU task scheduling service for IVGS Phase 1",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health_check() -> dict:
    """Liveness probe endpoint."""
    return {"status": "ok", "service": "ivgs-scheduler"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port,
                reload=False, log_level=settings.log_level)
