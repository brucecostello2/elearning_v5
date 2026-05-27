"""
SQLAlchemy async engine, session factory, and connection pooling.

Uses SQLAlchemy 2.0 async API with asyncpg driver for PostgreSQL 17.
Connection pool: configurable via DATABASE_POOL_SIZE and DATABASE_MAX_OVERFLOW.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from .config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


# Async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_pre_ping=True,
    echo=False,
)

# Async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields an async database session.

    Usage:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session outside FastAPI request cycle.

    Usage:
        async with get_db_context() as db:
            result = await db.execute(select(User))
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables from metadata (development only; use Alembic in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully")


async def check_db_connection() -> bool:
    """
    Verify database connectivity.

    Returns:
        True if a SELECT 1 succeeds, False otherwise.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def dispose_engine() -> None:
    """Dispose of the engine and its connection pool (for graceful shutdown)."""
    await engine.dispose()
    logger.info("Database engine disposed")
