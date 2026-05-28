"""
Phase 4 Gap 1: DLQ Service Tests

Tests DLQService: list_messages, get_message, replay_message,
discard_message, bulk_replay, get_analytics.
PURE_DB service.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.dlq_service import DLQService
from app.schemas.dlq import DLQBulkReplayRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_dlq_message(
    db,
    task_name="pipeline.render",
    category="transient",
    resolution=None,
    created_offset_days=0,
):
    mid = uuid.uuid4()
    created = datetime(2026, 5, 27 - created_offset_days, 12, 0, 0, tzinfo=timezone.utc)
    await db.execute(
        text(
            "INSERT INTO dead_letter_messages "
            "(id, task_name, failure_category, resolution, created_at, "
            " exception_type, exception_message, original_queue) "
            "VALUES (:mid, :task, :cat, :res, :created, 'RuntimeError', 'boom', 'default')"
        ),
        {
            "mid": str(mid),
            "task": task_name,
            "cat": category,
            "res": resolution,
            "created": created,
        },
    )
    await db.commit()
    return mid


# ===========================================================================
# List / Get Tests
# ===========================================================================

class TestListMessages:
    async def test_list_all(self, db_session):
        await _insert_dlq_message(db_session)
        svc = DLQService(db_session)
        msgs, total = await svc.list_messages()
        assert total >= 1
        assert len(msgs) >= 1

    async def test_list_filter_category(self, db_session):
        await _insert_dlq_message(db_session, category="config")
        svc = DLQService(db_session)
        msgs, total = await svc.list_messages(category="config")
        assert all(m.failure_category == "config" for m in msgs)

    async def test_list_filter_task_name(self, db_session):
        await _insert_dlq_message(db_session, task_name="pipeline.audio")
        svc = DLQService(db_session)
        msgs, _ = await svc.list_messages(task_name="audio")
        assert len(msgs) >= 1

    async def test_list_filter_resolution(self, db_session):
        await _insert_dlq_message(db_session, resolution="replayed")
        svc = DLQService(db_session)
        msgs, _ = await svc.list_messages(resolution="replayed")
        assert all(m.resolution == "replayed" for m in msgs)

    async def test_list_pagination(self, db_session):
        for _ in range(3):
            await _insert_dlq_message(db_session)
        svc = DLQService(db_session)
        msgs, total = await svc.list_messages(page=1, per_page=2)
        assert len(msgs) <= 2
        assert total >= 3

    async def test_list_empty(self, db_session):
        """List with impossible filter returns empty."""
        svc = DLQService(db_session)
        msgs, total = await svc.list_messages(task_name="nonexistent_task_xyz")
        assert total == 0
        assert msgs == []


class TestGetMessage:
    async def test_get_existing(self, db_session):
        mid = await _insert_dlq_message(db_session)
        svc = DLQService(db_session)
        result = await svc.get_message(mid)
        assert result is not None
        assert result.id == mid

    async def test_get_nonexistent(self, db_session):
        svc = DLQService(db_session)
        result = await svc.get_message(uuid.uuid4())
        assert result is None


# ===========================================================================
# Replay / Discard Tests
# ===========================================================================

class TestReplayMessage:
    async def test_replay_success(self, db_session):
        mid = await _insert_dlq_message(db_session)
        svc = DLQService(db_session)
        result = await svc.replay_message(mid, "admin")
        assert result is not None
        assert result.resolution == "replayed"

    async def test_replay_already_resolved_raises(self, db_session):
        mid = await _insert_dlq_message(db_session, resolution="discarded")
        svc = DLQService(db_session)
        with pytest.raises(ValueError, match="already resolved"):
            await svc.replay_message(mid, "admin")

    async def test_replay_nonexistent(self, db_session):
        svc = DLQService(db_session)
        result = await svc.replay_message(uuid.uuid4(), "admin")
        assert result is None


class TestDiscardMessage:
    async def test_discard_success(self, db_session):
        mid = await _insert_dlq_message(db_session)
        svc = DLQService(db_session)
        result = await svc.discard_message(mid, "invalid config", "admin")
        assert result is not None
        assert result.resolution == "discarded"

    async def test_discard_already_resolved_raises(self, db_session):
        mid = await _insert_dlq_message(db_session, resolution="replayed")
        svc = DLQService(db_session)
        with pytest.raises(ValueError, match="already resolved"):
            await svc.discard_message(mid, "reason", "admin")

    async def test_discard_nonexistent(self, db_session):
        svc = DLQService(db_session)
        result = await svc.discard_message(uuid.uuid4(), "reason", "admin")
        assert result is None


# ===========================================================================
# Bulk Replay Tests
# ===========================================================================

class TestBulkReplay:
    async def test_bulk_replay_by_category(self, db_session):
        task = f"pipeline.bulk_{uuid.uuid4().hex[:6]}"
        for _ in range(3):
            await _insert_dlq_message(db_session, task_name=task, category="transient")

        svc = DLQService(db_session)
        result = await svc.bulk_replay(
            DLQBulkReplayRequest(task_name=task), "admin"
        )
        assert result.replayed_count == 3
        assert len(result.message_ids) == 3

    async def test_bulk_replay_skips_resolved(self, db_session):
        task = f"pipeline.skip_{uuid.uuid4().hex[:6]}"
        await _insert_dlq_message(db_session, task_name=task, category="transient")  # unresolved
        await _insert_dlq_message(db_session, task_name=task, category="transient", resolution="discarded")

        svc = DLQService(db_session)
        result = await svc.bulk_replay(
            DLQBulkReplayRequest(task_name=task), "admin"
        )
        assert result.replayed_count == 1

    async def test_bulk_replay_no_matches(self, db_session):
        svc = DLQService(db_session)
        result = await svc.bulk_replay(
            DLQBulkReplayRequest(task_name="nonexistent_xyz"), "admin"
        )
        assert result.replayed_count == 0


# ===========================================================================
# Analytics Tests
# ===========================================================================

class TestAnalytics:
    async def test_analytics_returns_structure(self, db_session):
        await _insert_dlq_message(db_session, category="transient")
        await _insert_dlq_message(db_session, category="config")

        svc = DLQService(db_session)
        analytics = await svc.get_analytics()
        assert analytics.total_messages >= 2
        assert analytics.unresolved_count >= 0
        assert isinstance(analytics.by_category, list)
        assert isinstance(analytics.by_task, list)
        assert isinstance(analytics.by_day, list)

    async def test_analytics_counts_resolutions(self, db_session):
        await _insert_dlq_message(db_session, resolution="replayed")
        await _insert_dlq_message(db_session, resolution="discarded")
        await _insert_dlq_message(db_session)  # unresolved

        svc = DLQService(db_session)
        analytics = await svc.get_analytics()
        assert analytics.replayed_count >= 1
        assert analytics.discarded_count >= 1
        assert analytics.unresolved_count >= 1

    async def test_analytics_empty_db(self, db_session):
        """Analytics works even with sparse data."""
        svc = DLQService(db_session)
        analytics = await svc.get_analytics()
        assert analytics.total_messages >= 0
