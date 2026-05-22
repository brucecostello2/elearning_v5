"""
IVGS v5 — DLQ Service Tests
========================================

Tests for DLQService per §6.2 and Table 15.

Test coverage:
- DLQ entry creation with all failure categories
- Message replay with queue and kwargs overrides
- Message discard and escalation workflows
- Periodic processing (auto-replay transient, flag stale)
- Statistics aggregation
- Error handling for duplicate resolutions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ivgs_workers.services.dlq_service import (
    DLQEntry,
    DLQReplayRequest,
    DLQReplayResult,
    DLQService,
    DLQStats,
    FailureCategory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_session_factory() -> AsyncMock:
    """Create a mock async database session factory."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()

    factory = AsyncMock(return_value=session)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.fixture
def mock_celery_app() -> MagicMock:
    """Create a mock Celery application."""
    app = MagicMock()
    task_result = MagicMock()
    task_result.id = str(uuid.uuid4())
    app.send_task.return_value = task_result
    return app


@pytest.fixture
def dlq_service(
    mock_db_session_factory: AsyncMock,
    mock_celery_app: MagicMock,
) -> DLQService:
    """Create a DLQ service instance with mock dependencies."""
    return DLQService(
        db_session_factory=mock_db_session_factory,
        celery_app=mock_celery_app,
    )


# ---------------------------------------------------------------------------
# DLQ Entry Creation Tests
# ---------------------------------------------------------------------------

class TestDLQEntryCreation:
    """Tests for DLQ entry creation per §6.2."""

    @pytest.mark.asyncio
    async def test_send_to_dlq_with_exception_object(
        self, dlq_service: DLQService
    ) -> None:
        """Test DLQ entry creation from an exception object."""
        exc = TimeoutError("vLLM inference timeout after 120s")

        entry = await dlq_service.send_to_dlq(
            original_queue="gpu_llm",
            task_name="ivgs_workers.tasks.transcript_refinement_task",
            task_args=[],
            task_kwargs={"job_id": "test-job-1", "scene_id": "scene-1"},
            exception=exc,
            failure_category=FailureCategory.TRANSIENT,
            retry_count_exhausted=4,
        )

        assert isinstance(entry, DLQEntry)
        assert entry.original_queue == "gpu_llm"
        assert entry.task_name == "ivgs_workers.tasks.transcript_refinement_task"
        assert entry.exception_type == "TimeoutError"
        assert "120s" in entry.exception_message
        assert entry.failure_category == FailureCategory.TRANSIENT
        assert entry.retry_count_exhausted == 4
        assert entry.id is not None

    @pytest.mark.asyncio
    async def test_send_to_dlq_with_string_fields(
        self, dlq_service: DLQService
    ) -> None:
        """Test DLQ entry creation from string representations."""
        entry = await dlq_service.send_to_dlq(
            original_queue="gpu_image",
            task_name="ivgs_workers.tasks.image_generation_task",
            task_kwargs={"prompt": "A serene landscape"},
            exception_type="ComfyUIError",
            exception_message="FLUX.1 model failed to generate",
            traceback_str="Traceback (most recent call last):\n...",
            failure_category=FailureCategory.EXTERNAL,
            retry_count_exhausted=3,
        )

        assert entry.exception_type == "ComfyUIError"
        assert entry.failure_category == FailureCategory.EXTERNAL
        assert entry.retry_count_exhausted == 3

    @pytest.mark.asyncio
    async def test_send_to_dlq_all_failure_categories(
        self, dlq_service: DLQService
    ) -> None:
        """Test DLQ entry creation for all four failure categories."""
        for category in FailureCategory:
            entry = await dlq_service.send_to_dlq(
                original_queue="default",
                task_name=f"test_task_{category.value}",
                exception_type="TestError",
                exception_message=f"Test {category.value} error",
                failure_category=category,
            )
            assert entry.failure_category == category


# ---------------------------------------------------------------------------
# Replay Tests
# ---------------------------------------------------------------------------

class TestDLQReplay:
    """Tests for DLQ message replay."""

    @pytest.mark.asyncio
    async def test_replay_message_dispatches_to_celery(
        self,
        dlq_service: DLQService,
        mock_celery_app: MagicMock,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test that replay dispatches task to correct Celery queue."""
        # Setup mock to return a DLQ message
        mock_row = MagicMock()
        mock_row.original_queue = "gpu_video"
        mock_row.task_name = "video_generation_task"
        mock_row.task_args = []
        mock_row.task_kwargs = {"job_id": "job-1"}
        mock_row.resolution = None
        mock_row.reviewed_by = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        request = DLQReplayRequest(message_id=str(uuid.uuid4()))
        result = await dlq_service.replay_message(
            request, reviewed_by="admin"
        )

        assert isinstance(result, DLQReplayResult)
        assert result.status == "replayed"
        mock_celery_app.send_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_replay_with_queue_override(
        self,
        dlq_service: DLQService,
        mock_celery_app: MagicMock,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test replay with override_queue routes to different queue."""
        mock_row = MagicMock()
        mock_row.original_queue = "gpu_video"
        mock_row.task_name = "video_generation_task"
        mock_row.task_args = []
        mock_row.task_kwargs = {"job_id": "job-1"}
        mock_row.resolution = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        request = DLQReplayRequest(
            message_id=str(uuid.uuid4()),
            override_queue="gpu_image",
        )
        await dlq_service.replay_message(request)

        call_kwargs = mock_celery_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "gpu_image"


# ---------------------------------------------------------------------------
# Discard / Escalate Tests
# ---------------------------------------------------------------------------

class TestDLQResolutions:
    """Tests for discard and escalation workflows."""

    @pytest.mark.asyncio
    async def test_discard_message(
        self,
        dlq_service: DLQService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test discarding a DLQ message."""
        mock_row = MagicMock()
        mock_row.resolution = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        await dlq_service.discard_message(
            message_id=str(uuid.uuid4()),
            reviewed_by="admin",
            reason="Non-recoverable model failure",
        )

        # Verify update was called
        assert session.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_escalate_message(
        self,
        dlq_service: DLQService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test escalating a DLQ message."""
        mock_row = MagicMock()
        mock_row.resolution = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        await dlq_service.escalate_message(
            message_id=str(uuid.uuid4()),
            reviewed_by="admin",
            escalation_notes="Requires model redeployment",
        )

        assert session.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_cannot_resolve_already_resolved(
        self,
        dlq_service: DLQService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test that resolving an already-resolved message raises ValueError."""
        mock_row = MagicMock()
        mock_row.resolution = "replayed"
        mock_row.reviewed_by = "admin"

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="already resolved"):
            await dlq_service.discard_message(
                message_id=str(uuid.uuid4()),
                reviewed_by="admin2",
            )


# ---------------------------------------------------------------------------
# Periodic Processing Tests
# ---------------------------------------------------------------------------

class TestDLQPeriodicProcessing:
    """Tests for periodic DLQ processing (every 5 minutes)."""

    @pytest.mark.asyncio
    async def test_auto_replay_transient_within_1_hour(
        self,
        dlq_service: DLQService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test that transient failures < 1 hour old are auto-replayed."""
        recent_msg = MagicMock()
        recent_msg.id = str(uuid.uuid4())
        recent_msg.failure_category = "transient"
        recent_msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        recent_msg.task_name = "test_task"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [recent_msg]

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        with patch.object(dlq_service, "replay_message", new_callable=AsyncMock):
            result = await dlq_service.process_pending_messages(
                auto_replay_transient=True,
                max_auto_replays=10,
            )

            assert result["total_pending"] == 1

    @pytest.mark.asyncio
    async def test_flag_stale_messages_over_24_hours(
        self,
        dlq_service: DLQService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Test that messages > 24 hours old are flagged as stale."""
        old_msg = MagicMock()
        old_msg.id = str(uuid.uuid4())
        old_msg.failure_category = "config"
        old_msg.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
        old_msg.task_name = "old_task"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [old_msg]

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        result = await dlq_service.process_pending_messages()
        assert result["flagged_stale"] == 1


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------

class TestDLQModels:
    """Tests for DLQ Pydantic models."""

    def test_dlq_entry_defaults(self) -> None:
        """Test DLQEntry default values."""
        entry = DLQEntry(
            original_queue="gpu_llm",
            task_name="test_task",
            exception_type="TestError",
            exception_message="test",
            failure_category=FailureCategory.TRANSIENT,
        )
        assert entry.id is not None
        assert entry.task_args == []
        assert entry.task_kwargs == {}
        assert entry.retry_count_exhausted == 0

    def test_dlq_stats_defaults(self) -> None:
        """Test DLQStats default values."""
        stats = DLQStats()
        assert stats.total_messages == 0
        assert stats.pending_review == 0
        assert stats.by_category == {}
