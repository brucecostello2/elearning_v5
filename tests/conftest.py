"""
Shared test fixtures for IVGS v5.

Provides:
- Async database session using SQLite for fast isolated tests
- Redis mock via fakeredis
- Test settings override
"""
import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Override settings before importing application modules
os.environ.update({
    "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
    "REDIS_URL": "redis://localhost:6379/15",
    "SEAWEEDFS_MASTER_URL": "http://localhost:9333",
    "SEAWEEDFS_FILER_URL": "http://localhost:8888",
    "JWT_SECRET_KEY": "test_secret_key_for_testing_only_64_characters_minimum_padding!!",
    "LOG_LEVEL": "DEBUG",
    "LOG_FORMAT": "console",
    "NODE_HOSTNAME": "test-node",
})

from shared.database import Base  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean database session for each test function.

    Creates all tables before the test and drops them after.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test.db",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Provide a mock Redis client for tests that don't need real Redis."""
    mock = AsyncMock()
    mock.ping.return_value = True
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = True
    mock.exists.return_value = False
    return mock


@pytest.fixture
def mock_seaweedfs() -> AsyncMock:
    """Provide a mock SeaweedFS client for tests."""
    mock = AsyncMock()
    mock.check_health.return_value = True
    mock.upload_file.return_value = "3,01a2b3c4"
    mock.download_file.return_value = b"fake file content"
    mock.delete_file.return_value = True
    return mock
