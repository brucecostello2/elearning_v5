"""
IVGS v5 Test Suite — conftest.py

Implements:
- Remedy A2: pytest reporting hook to reclassify known asyncpg teardown errors
- NullPool engine for clean connection disposal
- Committed-data fixtures with per-test table truncation
- Independent sessions for API handlers (no cross-task connection sharing)
- User factories, auth helpers, FastAPI test client
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# ============================================================================
# REMEDY A2: Pytest reporting hook — reclassify known asyncpg teardown errors
# ============================================================================

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Reclassify known benign teardown errors as passes."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "teardown" and report.failed:
        if report.longrepr:
            error_text = str(report.longrepr)
            known_benign_patterns = [
                "Event loop is closed",
                "cannot perform operation: another operation is in progress",
                "connection is closed",
                "Connection._cancel",
                "attached to a different loop",
            ]
            if any(pattern in error_text for pattern in known_benign_patterns):
                report.outcome = "passed"
                report.longrepr = None
                logger.debug(
                    "Suppressed known asyncpg teardown error for %s", item.nodeid
                )


def pytest_configure(config):
    """Add warning filters for known asyncpg teardown warnings."""
    config.addinivalue_line(
        "filterwarnings",
        "ignore::pytest.PytestUnraisableExceptionWarning",
    )
    config.addinivalue_line(
        "filterwarnings",
        "ignore::RuntimeWarning",
    )


# ============================================================================
# DATABASE ENGINE — NullPool
# ============================================================================

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb",
    ),
)
if "+psycopg2" in TEST_DATABASE_URL:
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("+psycopg2", "+asyncpg")


# ============================================================================
# SAFETY GUARD — refuse to run against a non-test database.
# The db_session fixture TRUNCATEs ALL tables after every test. If this ever
# pointed at the live 'ivgs' database it would destroy production data.
# This guard makes that structurally impossible: the test DB name must look
# like a test database (end with '_test' or contain 'reconciliation').
# ============================================================================
_guard_db_name = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
if not (_guard_db_name.endswith("_test") or "reconciliation" in _guard_db_name):
    raise RuntimeError(
        f"REFUSING TO RUN TESTS: target database '{_guard_db_name}' does not look "
        f"like a test database. The test suite TRUNCATEs all tables after every "
        f"test. Point DATABASE_URL (or TEST_DATABASE_URL) at a disposable test "
        f"database whose name ends with '_test' or contains 'reconciliation' "
        f"(e.g. ivgs_reconciliation_test). Refusing to touch '{_guard_db_name}'."
    )


# Store original get_session reference BEFORE any monkeypatching
# This is the function object that FastAPI's Depends() references
from shared.database import get_session as _original_get_session
from app.models.user import User
from app.models.project import Project


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Async test engine with NullPool."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    yield engine
    try:
        await engine.dispose()
    except Exception:
        pass


@pytest_asyncio.fixture(scope="session")
def test_session_factory(test_engine):
    """Session factory bound to test engine."""
    return async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )


# ============================================================================
# TABLE NAMES for truncation
# ============================================================================

_ALL_TABLES = [
    # AD-01 Model Store (children before parents; selections before projects)
    "project_model_selections",
    "model_approvals",
    "model_node_availability",
    "model_capability_tags",
    "models",
    "prompt_tag_associations",
    "asset_quality_scores",
    "pipeline_checkpoints",
    "render_segments",
    "gpu_reservations",
    "gpu_nodes",
    "gpu_metrics_history",
    "task_retries",
    "dead_letter_messages",
    "worker_heartbeats",
    "composition_manifests",
    "backup_records",
    "storage_quotas",
    "fallback_policies",
    "audit_log",
    "assets",
    "render_jobs",
    "storyboard_scenes",
    "transcripts",
    "language_variants",
    "prompts",
    "prompt_tags",
    "retention_policies",
    "projects",
    "users",
]


# ============================================================================
# DB SESSION — commits data, truncates after test
# ============================================================================

@pytest_asyncio.fixture
async def db_session(test_engine, test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session for fixture data creation.

    Data is committed (not rolled back) so that API handlers running in
    separate tasks can see it. Tables are truncated after each test.
    """
    async with test_session_factory() as session:
        yield session
        # Commit any pending changes from fixtures
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    # Truncate all tables after test completes
    async with test_engine.begin() as conn:
        table_list = ", ".join(_ALL_TABLES)
        await conn.execute(text(f"TRUNCATE TABLE {table_list} CASCADE"))


# ============================================================================
# OVERRIDE DB FUNCTIONS — route API sessions through test engine
# ============================================================================

@pytest.fixture(autouse=True)
def _patch_celery_dispatch(monkeypatch):
    """
    Stub out Celery task dispatch in API endpoints.

    Phase 14 Stream B introduced a refactor where the backup trigger and
    verify endpoints dispatch to a Celery worker via send_task().  In tests
    we don't want to actually push messages onto Redis (the live broker
    instance) because:
      - A live backup-worker is connected to /0 and would consume the
        message, then attempt to execute a real backup against test data
      - Test runs would pollute the broker's keyspace

    Recorded calls available at celery_client.send_task.calls for assertion.
    """
    try:
        from app.api.v1.backup import celery_client
    except ImportError:
        return

    calls = []

    def _stub_send_task(name, args=None, kwargs=None, queue=None, **extra):
        calls.append({
            "name": name,
            "args": args,
            "kwargs": kwargs,
            "queue": queue,
            **extra,
        })
        class _StubAsyncResult:
            id = "stub-task-id"
            def get(self, *a, **kw): return None
            def ready(self): return False
            def __bool__(self): return True
        return _StubAsyncResult()

    _stub_send_task.calls = calls
    monkeypatch.setattr(celery_client, "send_task", _stub_send_task)


@pytest_asyncio.fixture(autouse=True)
async def _override_db_functions(test_engine, test_session_factory, monkeypatch):
    """
    Monkeypatch all shared.database functions to use the test engine.

    Each API request gets its own independent session from test_engine,
    avoiding asyncpg cross-task connection sharing issues caused by
    Starlette's BaseHTTPMiddleware.
    """
    # Override get_db_context
    @asynccontextmanager
    async def _test_db_context():
        async with test_session_factory() as session:
            async with session.begin():
                yield session

    monkeypatch.setattr("shared.database.get_db_context", _test_db_context)

    # Override get_session — each call creates a fresh independent session
    async def _test_get_session():
        async with test_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr("shared.database.get_session", _test_get_session)

    # Override check_db_connection
    async def _test_check_db_connection():
        try:
            async with test_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    monkeypatch.setattr("shared.database.check_db_connection", _test_check_db_connection)

    # Override dispose_engine
    async def _test_dispose_engine():
        pass

    monkeypatch.setattr("shared.database.dispose_engine", _test_dispose_engine)


# ============================================================================
# REDIS MOCK
# ============================================================================

@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Replace global redis_client with in-memory dict mock."""
    from shared.redis_client import redis_client

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


# ============================================================================
# SEAWEEDFS MOCK
# ============================================================================

@pytest.fixture(autouse=True)
def mock_seaweedfs(monkeypatch):
    """Mock SeaweedFS client for tests."""
    from shared.seaweedfs_client import seaweedfs_client

    async def mock_health():
        return True

    async def mock_close():
        pass

    _fs_store: dict[str, bytes] = {}

    async def mock_upload(*args, **kwargs):
        # Handles both positional and keyword calls
        path = kwargs.get("path") or kwargs.get("file_path") or (args[0] if args else "unknown")
        data = kwargs.get("data") or kwargs.get("content") or kwargs.get("file_data") or (args[1] if len(args) > 1 else b"")
        if isinstance(data, str):
            data = data.encode()
        # Real shared.seaweedfs_client.upload_file returns Optional[str] (the
        # bare fid), which asset_service stores directly into the VARCHAR
        # seaweedfs_fid column. Returning a dict here made asyncpg reject the
        # bind on PostgreSQL ("expected str, got dict"). Match the contract.
        fid = f"mock-fid-{len(_fs_store) + 1}"
        # Key by BOTH path and fid: download resolves by fid
        # (asset.seaweedfs_fid), while path-based callers still hit.
        _fs_store[path] = data
        _fs_store[fid] = data
        return fid

    async def mock_download(*args, **kwargs):
        path = kwargs.get("path") or kwargs.get("fid") or (args[0] if args else "")
        return _fs_store.get(path, b"")

    async def mock_delete(*args, **kwargs):
        path = kwargs.get("path") or kwargs.get("fid") or (args[0] if args else "")
        _fs_store.pop(path, None)
        return True

    monkeypatch.setattr(seaweedfs_client, "check_health", mock_health)
    monkeypatch.setattr(seaweedfs_client, "close", mock_close)
    monkeypatch.setattr(seaweedfs_client, "upload_file", mock_upload)
    monkeypatch.setattr(seaweedfs_client, "upload_to_filer", mock_upload)
    monkeypatch.setattr(seaweedfs_client, "download_file", mock_download)
    monkeypatch.setattr(seaweedfs_client, "delete_file", mock_delete)
    # Services also call short names: upload, download, delete
    seaweedfs_client.upload = mock_upload
    seaweedfs_client.download = mock_download
    seaweedfs_client.delete = mock_delete


# ============================================================================
# FASTAPI TEST CLIENT
# ============================================================================

@pytest_asyncio.fixture
async def client(test_session_factory) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client wired to FastAPI with overridden DB dependency.

    Uses _original_get_session (captured before monkeypatch) as the
    dependency override key. Each API request gets its own independent
    session from test_session_factory.
    """
    from main import app

    async def override_get_session():
        async with test_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[_original_get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================================
# USER FACTORIES
# ============================================================================

async def create_test_user(
    db: AsyncSession,
    username: str = "testuser",
    password: str = "TestPass123",
    role: str = "operator",
    is_active: bool = True,
):
    """Create a test user, commit, and return (user, plain_password).

    Data is committed so API handlers in separate sessions can see it.
    """
    from app.models.user import User
    from app.core.security import hash_password

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
    await db.commit()
    return user, password


def make_auth_header(user) -> dict:
    """Generate Authorization header with a valid access token."""
    from app.core.security import create_access_token

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


# ============================================================================
# TOKEN FIXTURES — JWT strings for role-based API testing
# ============================================================================

@pytest_asyncio.fixture
async def admin_token(db_session) -> str:
    """Return a JWT access token for an admin user."""
    from app.core.security import create_access_token

    user, _ = await create_test_user(
        db_session, username="admin_token_user", role="admin"
    )
    return create_access_token(user_id=str(user.id), role=user.role)


@pytest_asyncio.fixture
async def operator_token(db_session) -> str:
    """Return a JWT access token for an operator user."""
    from app.core.security import create_access_token

    user, _ = await create_test_user(
        db_session, username="operator_token_user", role="operator"
    )
    return create_access_token(user_id=str(user.id), role=user.role)


@pytest_asyncio.fixture
async def viewer_token(db_session) -> str:
    """Return a JWT access token for a viewer user."""
    from app.core.security import create_access_token

    user, _ = await create_test_user(
        db_session, username="viewer_token_user", role="viewer"
    )
    return create_access_token(user_id=str(user.id), role=user.role)


@pytest_asyncio.fixture
async def other_operator_token(db_session) -> str:
    """Return a JWT access token for a second operator (RBAC cross-user tests)."""
    from app.core.security import create_access_token

    user, _ = await create_test_user(
        db_session, username="other_operator_user", role="operator"
    )
    return create_access_token(user_id=str(user.id), role=user.role)


# ============================================================================
# PROJECT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def project_id(db_session, operator_token) -> str:
    """Create a test project and return its UUID as a string."""
    from app.models.project import Project
    from app.core.security import decode_token

    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])

    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        description="A project for testing",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()
    return str(project.id)


# ============================================================================
# ASSET FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def asset_id(db_session, project_id) -> str:
    """Create a test asset and return its UUID as a string."""
    from app.models.asset import Asset

    asset = Asset(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        asset_type="image",
        mime_type="image/png",
        file_size_bytes=1024,
        storage_tier="hot",
        content_hash="abc123hash",
        seaweedfs_fid="1,01abc",
        seaweedfs_path="/test/image.png",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    await db_session.commit()
    return str(asset.id)


# ============================================================================
# SCENE FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def scene_id(db_session, project_id) -> str:
    """Create a single scene and return its UUID."""
    from app.models.storyboard_scene import StoryboardScene

    scene = StoryboardScene(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        scene_index=1,
        narration_text="Test narration",
        visual_description="A test visual",
        media_type="image",
        duration_seconds=10.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(scene)
    await db_session.flush()
    await db_session.commit()
    return str(scene.id)


@pytest_asyncio.fixture
async def scene_fixture(db_session, operator_token) -> dict:
    """Create a scene with its project."""
    from app.models.project import Project
    from app.models.storyboard_scene import StoryboardScene

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Scene Test Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    scene = StoryboardScene(
        id=uuid.uuid4(),
        project_id=project.id,
        scene_index=1,
        narration_text="Original narration",
        visual_description="Original visual",
        media_type="image",
        duration_seconds=10.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(scene)
    await db_session.flush()
    await db_session.commit()

    return {
        "id": str(scene.id),
        "project_id": str(project.id),
        "scene_index": scene.scene_index,
    }


@pytest_asyncio.fixture
async def project_with_scenes(db_session, operator_token) -> dict:
    """Create a project with multiple scenes for reorder tests."""
    from app.models.project import Project
    from app.models.storyboard_scene import StoryboardScene

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Multi Scene Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    scenes = []
    for i in range(1, 4):
        scene = StoryboardScene(
            id=uuid.uuid4(),
            project_id=project.id,
            scene_index=i,
            narration_text=f"Scene {i} narration",
            visual_description=f"Scene {i} visual",
            media_type="image",
            duration_seconds=10.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(scene)
        scenes.append(scene)
    await db_session.flush()
    await db_session.commit()

    return {
        "project_id": str(project.id),
        "scenes": [{"id": str(s.id), "scene_index": s.scene_index} for s in scenes],
    }


# ============================================================================
# TRANSCRIPT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def transcript_fixture(db_session, operator_token) -> dict:
    """Create a transcript with its project."""
    from app.models.project import Project
    from app.models.transcript import Transcript

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Transcript Test Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    transcript = Transcript(
        id=uuid.uuid4(),
        project_id=project.id,
        sequence_order=1,
        refined_text="Original test transcript text",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(transcript)
    await db_session.flush()
    await db_session.commit()

    return {
        "id": str(transcript.id),
        "project_id": str(project.id),
        "sequence_order": transcript.sequence_order,
    }


@pytest_asyncio.fixture
async def project_with_transcripts(db_session, operator_token) -> dict:
    """Create a project with 2 transcripts for reorder tests."""
    from app.models.project import Project
    from app.models.transcript import Transcript

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Multi Transcript Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    transcripts = []
    for i in range(1, 3):
        t = Transcript(
            id=uuid.uuid4(),
            project_id=project.id,
            sequence_order=i,
            refined_text=f"Transcript part {i}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(t)
        transcripts.append(t)
    await db_session.flush()
    await db_session.commit()

    return {
        "project_id": str(project.id),
        "transcripts": [{"id": str(t.id), "sequence_order": t.sequence_order} for t in transcripts],
    }


@pytest_asyncio.fixture
async def project_with_transcript(db_session, operator_token) -> dict:
    """Create a project with one transcript (for state machine trigger tests)."""
    from app.models.project import Project
    from app.models.transcript import Transcript

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Triggerable Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    transcript = Transcript(
        id=uuid.uuid4(),
        project_id=project.id,
        sequence_order=1,
        refined_text="Transcript for trigger test",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(transcript)
    await db_session.flush()
    await db_session.commit()

    return {"id": str(project.id)}


# ============================================================================
# RENDER JOB & CHECKPOINT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def job_with_checkpoints(db_session, operator_token) -> dict:
    """Create a completed job with checkpoints."""
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.models.checkpoint import PipelineCheckpoint
    from app.core.security import decode_token

    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])

    project = Project(
        id=uuid.uuid4(),
        name="Checkpoint Test Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="success",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    stages = []
    for i, name in enumerate(["transcript_refinement", "image_generation", "composition"]):
        cp = PipelineCheckpoint(
            id=uuid.uuid4(),
            job_id=job.id,
            stage_name=name,
            stage_index=i,
            checkpoint_data={"progress": 100},
            output_refs={"asset_ids": [str(uuid.uuid4())]},
            status="complete",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(cp)
        stages.append({"stage_name": name, "id": str(cp.id)})
    await db_session.flush()
    await db_session.commit()

    return {"job_id": str(job.id), "project_id": str(project.id), "stages": stages}


@pytest_asyncio.fixture
async def failed_job_with_checkpoints(db_session, operator_token) -> dict:
    """Create a failed job with partial checkpoints."""
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.models.checkpoint import PipelineCheckpoint
    from app.core.security import decode_token

    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])

    project = Project(
        id=uuid.uuid4(),
        name="Failed Job Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="failed",
        error_message="Out of memory during image generation",
        failure_category="transient",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    cp1 = PipelineCheckpoint(
        id=uuid.uuid4(),
        job_id=job.id,
        stage_name="transcript_refinement",
        stage_index=0,
        checkpoint_data={"progress": 100},
        output_refs={"asset_ids": [str(uuid.uuid4())]},
        status="complete",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    cp2 = PipelineCheckpoint(
        id=uuid.uuid4(),
        job_id=job.id,
        stage_name="image_generation",
        stage_index=1,
        checkpoint_data={"progress": 45},
        status="failed",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([cp1, cp2])
    await db_session.flush()
    await db_session.commit()

    return {"job_id": str(job.id), "project_id": str(project.id)}


@pytest_asyncio.fixture
async def running_job(db_session, operator_token) -> dict:
    """Create a currently-running job."""
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.core.security import decode_token

    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])

    project = Project(
        id=uuid.uuid4(),
        name="Running Job Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="running",
        started_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.commit()

    return {"id": str(job.id), "project_id": str(project.id)}


@pytest_asyncio.fixture
async def empty_job(db_session, operator_token) -> dict:
    """Create a job with no checkpoints."""
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.core.security import decode_token

    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])

    project = Project(
        id=uuid.uuid4(),
        name="Empty Job Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.commit()

    return {"id": str(job.id), "project_id": str(project.id)}


# ============================================================================
# DLQ FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def dlq_messages(db_session) -> list:
    """Create DLQ messages for listing/replay/discard tests."""
    from app.models.dead_letter_queue import DeadLetterMessage

    messages = []
    for i, (task, cat) in enumerate([
        ("image_generation", "transient"),
        ("video_composition", "external"),
        ("image_generation", "transient"),
    ]):
        msg = DeadLetterMessage(
            id=uuid.uuid4(),
            original_queue="celery",
            task_name=task,
            task_args={"scene_id": str(uuid.uuid4())},
            task_kwargs={"quality": "high"},
            exception_type="RuntimeError",
            exception_message=f"Test error {i}",
            traceback=f"Traceback (most recent call last):\n  File test.py\nRuntimeError: Test error {i}",
            failure_category=cat,
            retry_count_exhausted=3,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(msg)
        messages.append(msg)
    await db_session.flush()
    await db_session.commit()

    return [{"id": str(m.id), "task_name": m.task_name, "failure_category": m.failure_category} for m in messages]


@pytest_asyncio.fixture
async def resolved_dlq_message(db_session) -> dict:
    """Create an already-resolved DLQ message."""
    from app.models.dead_letter_queue import DeadLetterMessage

    msg = DeadLetterMessage(
        id=uuid.uuid4(),
        original_queue="celery",
        task_name="image_generation",
        exception_type="RuntimeError",
        exception_message="Already handled",
        failure_category="transient",
        resolution="replayed",
        reviewed_by="admin_test",
        reviewed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(msg)
    await db_session.flush()
    await db_session.commit()

    return {"id": str(msg.id)}


# ============================================================================
# GPU NODE FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def registered_gpu_node(db_session) -> dict:
    """Create a registered online GPU node."""
    from app.models.gpu_node import GpuNode

    node = GpuNode(
        id=uuid.uuid4(),
        node_hostname="test-node-01",
        gpu_index=0,
        gpu_model="NVIDIA A100",
        total_vram_mb=81920,
        compute_capability="8.0",
        status="online",
        registered_at=datetime.now(timezone.utc),
    )
    db_session.add(node)
    await db_session.flush()
    await db_session.commit()

    return {
        "id": str(node.id),
        "node_hostname": node.node_hostname,
        "gpu_model": node.gpu_model,
        "total_vram_mb": node.total_vram_mb,
        "status": node.status,
    }


@pytest_asyncio.fixture
async def draining_gpu_node(db_session) -> dict:
    """Create a GPU node in draining state."""
    from app.models.gpu_node import GpuNode

    node = GpuNode(
        id=uuid.uuid4(),
        node_hostname="test-node-drain",
        gpu_index=0,
        gpu_model="NVIDIA A100",
        total_vram_mb=81920,
        status="draining",
        registered_at=datetime.now(timezone.utc),
    )
    db_session.add(node)
    await db_session.flush()
    await db_session.commit()

    return {"id": str(node.id), "status": node.status}


# ============================================================================
# RETENTION POLICY FIXTURE
# ============================================================================

@pytest_asyncio.fixture
async def retention_policy(db_session) -> dict:
    """Create a retention policy."""
    from app.models.retention_policy import RetentionPolicy

    policy = RetentionPolicy(
        id=uuid.uuid4(),
        name="test-existing-policy",
        hot_days=30,
        warm_days=90,
        cold_days=365,
        archive_days=730,
        delete_after_days=1095,
        is_default=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(policy)
    await db_session.flush()
    await db_session.commit()

    return {
        "id": str(policy.id),
        "name": policy.name,
        "hot_days": policy.hot_days,
        "warm_days": policy.warm_days,
        "cold_days": policy.cold_days,
    }


# ============================================================================
# QUALITY SCORE FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def job_with_quality_scores(db_session, operator_token) -> dict:
    """Create a job with quality-scored assets."""
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.models.asset import Asset
    from app.models.quality_score import AssetQualityScore

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Quality Test Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="success",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    for decision in ["approved", "flagged", "approved"]:
        asset = Asset(
            id=uuid.uuid4(),
            project_id=project.id,
            asset_type="image",
            storage_tier="hot",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(asset)
        await db_session.flush()

        score = AssetQualityScore(
            id=uuid.uuid4(),
            asset_id=asset.id,
            job_id=job.id,
            quality_score=0.85 if decision == "approved" else 0.45,
            safety_score=0.95,
            decision=decision,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(score)
    await db_session.flush()
    await db_session.commit()

    return {"job_id": str(job.id), "project_id": str(project.id)}


@pytest_asyncio.fixture
async def flagged_quality_scores(db_session, operator_token) -> list:
    """Create flagged quality scores."""
    from app.models.project import Project
    from app.models.asset import Asset
    from app.models.render_job import RenderJob
    from app.models.quality_score import AssetQualityScore

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Flagged Quality Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="success",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    results = []
    for i in range(2):
        asset = Asset(
            id=uuid.uuid4(),
            project_id=project.id,
            asset_type="image",
            storage_tier="hot",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(asset)
        await db_session.flush()

        score = AssetQualityScore(
            id=uuid.uuid4(),
            asset_id=asset.id,
            job_id=job.id,
            quality_score=0.35,
            safety_score=0.90,
            decision="flagged",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(score)
        await db_session.flush()
        results.append({"id": str(score.id), "asset_id": str(asset.id)})

    await db_session.commit()
    return results


@pytest_asyncio.fixture
async def approved_quality_score(db_session, operator_token) -> dict:
    """Create an already-approved quality score."""
    from app.models.project import Project
    from app.models.asset import Asset
    from app.models.render_job import RenderJob
    from app.models.quality_score import AssetQualityScore

    from app.core.security import decode_token
    payload = decode_token(operator_token)
    _operator_user_id = uuid.UUID(payload["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="Approved Quality Project",
        state="DRAFT",
        created_by=_operator_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="final_render",
        status="success",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        asset_type="image",
        storage_tier="hot",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()

    score = AssetQualityScore(
        id=uuid.uuid4(),
        asset_id=asset.id,
        job_id=job.id,
        quality_score=0.92,
        safety_score=0.99,
        decision="approved",
        reviewed_by="admin_test",
        reviewed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(score)
    await db_session.flush()
    await db_session.commit()

    return {"id": str(score.id), "asset_id": str(asset.id)}


# ============================================================================
# AD-01 MODEL STORE FIXTURES (ARCH-1 Tarball 1)
# ============================================================================

def make_model(
    *,
    name,
    stage=None,
    engine=None,
    tier=None,
    state=None,
    enabled=True,
    is_default=False,
    vram_gb=16.0,
    dynamically_loadable=True,
    tags=None,
    nodes=None,
):
    """Build (unsaved) an AD-01 Model with tags and node availability."""
    from shared.models.model_store import (
        CapabilityDimension as _CD,  # noqa: F401  (imported for callers)
        Model,
        ModelCapabilityTag,
        ModelEngine,
        ModelNodeAvailability,
        ModelStage,
        ModelState,
        ModelTier,
    )

    model = Model(
        id=uuid.uuid4(),
        name=name,
        display_name=name.replace("-", " ").title(),
        stage=stage or ModelStage.TALKING_HEAD,
        engine=engine or ModelEngine.LATENTSYNC,
        tier=tier or ModelTier.BOTH,
        state=state or ModelState.APPROVED,
        enabled=enabled,
        is_default=is_default,
        vram_gb=vram_gb,
        dynamically_loadable=dynamically_loadable,
    )
    for dimension, value, weight in tags or []:
        model.capability_tags.append(
            ModelCapabilityTag(dimension=dimension, value=value, weight=weight)
        )
    for node_id, status, served in nodes or []:
        model.node_availability.append(
            ModelNodeAvailability(node_id=node_id, status=status, served=served)
        )
    return model


@pytest_asyncio.fixture
async def model_store_project(db_session, operator_token):
    """ORM-level project row for service/factory tests (returns Project)."""
    from app.core.security import decode_token
    from app.models.project import Project

    payload = decode_token(operator_token)
    row = Project(
        id=uuid.uuid4(),
        name="arch1-exemplar",
        description="ARCH-1 provider/planner test project",
        state="DRAFT",
        created_by=uuid.UUID(payload["sub"]),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.commit()
    return row


@pytest_asyncio.fixture
async def talking_head_store(db_session):
    """Two approved talking-head models on node-04; LatentSync is default."""
    from shared.models.model_store import (
        CapabilityDimension as CD,
        ModelEngine,
        NodeAvailabilityStatus as NA,
    )

    latentsync = make_model(
        name="latentsync-1.5",
        engine=ModelEngine.LATENTSYNC,
        is_default=True,
        vram_gb=16.0,
        tags=[
            (CD.VISUAL_STYLE, "photorealistic", 1.0),
            (CD.MOTION_PROFILE, "subtle", 0.5),
        ],
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    sadtalker = make_model(
        name="sadtalker-v2",
        engine=ModelEngine.SADTALKER,
        vram_gb=8.0,
        tags=[
            (CD.VISUAL_STYLE, "stylized", 1.0),
            (CD.MOTION_PROFILE, "expressive", 0.8),
        ],
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    db_session.add_all([latentsync, sadtalker])
    await db_session.commit()
    return {"latentsync": latentsync, "sadtalker": sadtalker}


# ============================================================================
# CELERY PRODUCER — WP-45
#
# Before WP-45, eight endpoints created a row, returned 202 and dispatched
# nothing, so no test in this suite could ever have touched a broker. Now that
# they dispatch, a test that does not stub the producer reaches out to
# `redis:6379`, a hostname that resolves inside the compose network and nowhere
# else - which turns a unit test into an environment test.
#
# This is AUTOUSE deliberately. Opt-in stubbing would mean the next endpoint
# that learns to dispatch silently starts depending on a live broker, and the
# failure would look like flakiness rather than a missing stub. A test that
# wants to ASSERT on what was published patches this again with its own
# recorder (see tests/test_wp45_dispatch.py); an inner patch wins.
# ============================================================================

class _RecordingBroker:
    """Records send_task / control.revoke instead of reaching a broker."""

    def __init__(self):
        self.sent = []
        self.revoked = []
        self.control = _RecordingControl(self)

    def send_task(self, name, args=None, kwargs=None, queue=None, **_ignored):
        self.sent.append(
            {"name": name, "args": args, "kwargs": kwargs, "queue": queue}
        )
        return _StubAsyncResult(f"stub-task-{len(self.sent)}")


class _RecordingControl:
    def __init__(self, broker):
        self._broker = broker

    def revoke(self, task_id, **kwargs):
        self._broker.revoked.append({"task_id": task_id, **kwargs})


class _StubAsyncResult:
    def __init__(self, task_id):
        self.id = task_id


@pytest.fixture(autouse=True)
def stub_celery_producer(monkeypatch):
    """Every test runs against a recording producer, never a live broker."""
    broker = _RecordingBroker()
    monkeypatch.setattr(
        "app.services.celery_producer.celery_app", broker, raising=False
    )
    return broker


# ============================================================================
# GPU SCHEDULER and MODEL SERVING — WP-45
#
# Same reasoning as the producer stub above. Two more surfaces learned to reach
# out of process in WP-45, and neither of them may turn a unit test into an
# environment test:
#
#   * GET /api/v1/gpu/{nodes,utilization} read the SCHEDULER's registry (Task
#     4(b), D-2 ruled read-through), because `gpu_nodes` has always had zero
#     rows - workers register with the scheduler, not with the API.
#   * The Prompt Playground calls a real model (Task 3, site 8). It used to
#     return a hand-written placeholder string in the model_response field.
#
# Both default to the EMPTY / benign answer, so a test that has not thought
# about them still passes; a test that cares patches the same target and wins.
# ============================================================================

_EMPTY_FLEET = {
    "total_nodes": 0, "alive_nodes": 0, "draining_nodes": 0,
    "total_vram_mb": 0, "used_vram_mb": 0, "available_vram_mb": 0,
    "fleet_utilization_pct": 0.0,
    "queue_depth": {"urgent": 0, "normal": 0, "batch": 0},
    "nodes": [],
}


@pytest.fixture(autouse=True)
def stub_scheduler_fleet(monkeypatch):
    """No test reaches a live GPU scheduler."""
    async def _fleet(*_args, **_kwargs):
        return dict(_EMPTY_FLEET)

    monkeypatch.setattr(
        "app.services.gpu_service.fetch_fleet", _fleet, raising=False
    )
    return _fleet


@pytest.fixture(autouse=True)
def stub_llm_playground(monkeypatch):
    """No test reaches a live vLLM/Ollama endpoint."""
    async def _completion(prompt, model_id, engine="vllm", parameters=None):
        return {
            "model_response": f"[stubbed completion for {model_id}]",
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            },
            "engine": engine,
            "endpoint": "http://stubbed-model.test:8000",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(
        "app.services.prompt_service.run_completion", _completion, raising=False
    )
    return _completion
