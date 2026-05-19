"""
Shared test fixtures for Phase 2 tests.

Provides:
- Async test database session (SQLite in-memory for speed)
- FastAPI test client with dependency overrides
- User factory functions (admin, operator, viewer)
- Token generation helpers
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.database import Base, get_session
from shared.redis_client import redis_client
from app.core.security import hash_password, create_access_token, create_refresh_token


# ---------------------------------------------------------------------------
# Database fixtures (in-memory SQLite for isolation)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all session-scoped fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create the async engine for the test database."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional database session that rolls back after each test."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Redis mock
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """
    Replace the global redis_client with an in-memory dict-backed mock.
    Prevents tests from requiring a running Redis instance.
    """
    store = {}

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, ex=None):
        store[key] = value
        return True

    async def mock_delete(key):
        return store.pop(key, None) is not None

    async def mock_exists(key):
        return key in store

    async def mock_incr(key):
        val = int(store.get(key, 0)) + 1
        store[key] = str(val)
        return val

    async def mock_expire(key, seconds):
        return True

    async def mock_ping():
        return True

    async def mock_close():
        pass

    monkeypatch.setattr(redis_client, "get", mock_get)
    monkeypatch.setattr(redis_client, "set", mock_set)
    monkeypatch.setattr(redis_client, "delete", mock_delete)
    monkeypatch.setattr(redis_client, "exists", mock_exists)
    monkeypatch.setattr(redis_client, "incr", mock_incr)
    monkeypatch.setattr(redis_client, "expire", mock_expire)
    monkeypatch.setattr(redis_client, "ping", mock_ping)
    monkeypatch.setattr(redis_client, "close", mock_close)


# ---------------------------------------------------------------------------
# SeaweedFS mock
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_seaweedfs(monkeypatch):
    """Mock SeaweedFS client for tests."""
    from shared.seaweedfs_client import seaweedfs_client

    async def mock_health():
        return True

    async def mock_close():
        pass

    monkeypatch.setattr(seaweedfs_client, "check_health", mock_health)
    monkeypatch.setattr(seaweedfs_client, "close", mock_close)


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client wired to the FastAPI app with overridden dependencies.
    """
    from main import app

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------

async def create_test_user(
    db: AsyncSession,
    username: str = "testuser",
    password: str = "TestPass123",
    role: str = "operator",
    is_active: bool = True,
):
    """Create a test user and return (user, plain_password)."""
    from app.models.user import User

    user = User(
        id=uuid.uuid4(),
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user, password


def make_auth_header(user) -> dict:
    """Generate Authorization header with a valid access token for a test user."""
    token = create_access_token(user_id=str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_user(db_session):
    """Create and return an admin test user."""
    user, password = await create_test_user(
        db_session, username="admin_test", role="admin"
    )
    return user, password


@pytest_asyncio.fixture
async def operator_user(db_session):
    """Create and return an operator test user."""
    user, password = await create_test_user(
        db_session, username="operator_test", role="operator"
    )
    return user, password


@pytest_asyncio.fixture
async def viewer_user(db_session):
    """Create and return a viewer test user."""
    user, password = await create_test_user(
        db_session, username="viewer_test", role="viewer"
    )
    return user, password
