"""
Phase 4 — Job Service Unit Tests.

Tests business logic in app/services/job_service.py:
  - list_jobs: pagination, ordering
  - get_job: found/not found
  - cancel_job: state validation, status transition
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.job_service import JobService

pytestmark = pytest.mark.asyncio


async def _create_job(db_session, project_id: str, status: str = "pending") -> str:
    """Helper to insert a render job directly."""
    job_id = str(uuid4())
    await db_session.execute(
        text(
            "INSERT INTO render_jobs (id, project_id, job_type, status, created_at) "
            "VALUES (:id, :pid, 'final_render', :status, :created_at)"
        ),
        {"id": job_id, "pid": project_id, "status": status, "created_at": datetime.now(timezone.utc)},
    )
    await db_session.flush()
    return job_id


class TestListJobs:
    async def test_list_jobs_empty_project(self, db_session, project_id: str):
        svc = JobService(db_session)
        jobs, total = await svc.list_jobs(uuid4())
        assert jobs == []
        assert total == 0

    async def test_list_jobs_with_data(self, db_session, project_id: str):
        await _create_job(db_session, project_id, "running")
        await _create_job(db_session, project_id, "pending")
        svc = JobService(db_session)
        jobs, total = await svc.list_jobs(project_id)
        assert total >= 2
        assert len(jobs) >= 2

    async def test_list_jobs_pagination(self, db_session, project_id: str):
        for _ in range(3):
            await _create_job(db_session, project_id)
        svc = JobService(db_session)
        jobs_p1, total = await svc.list_jobs(project_id, page=1, per_page=2)
        assert len(jobs_p1) == 2
        assert total >= 3

    async def test_list_jobs_ordered_by_created_at_desc(self, db_session, project_id: str):
        await _create_job(db_session, project_id)
        await _create_job(db_session, project_id)
        svc = JobService(db_session)
        jobs, _ = await svc.list_jobs(project_id)
        if len(jobs) >= 2:
            assert jobs[0].created_at >= jobs[1].created_at


class TestGetJob:
    async def test_get_job_found(self, db_session, project_id: str):
        jid = await _create_job(db_session, project_id)
        svc = JobService(db_session)
        job = await svc.get_job(jid)
        assert job is not None
        assert str(job.id) == jid

    async def test_get_job_not_found(self, db_session):
        svc = JobService(db_session)
        job = await svc.get_job(uuid4())
        assert job is None


class TestCancelJob:
    async def test_cancel_pending_job(self, db_session, project_id: str):
        jid = await _create_job(db_session, project_id, "pending")
        svc = JobService(db_session)
        job = await svc.cancel_job(jid)
        assert job is not None
        assert job.status == "failed"
        assert job.error_message == "Cancelled by user"
        assert job.completed_at is not None

    async def test_cancel_running_job(self, db_session, project_id: str):
        jid = await _create_job(db_session, project_id, "running")
        svc = JobService(db_session)
        job = await svc.cancel_job(jid)
        assert job is not None
        assert job.status == "failed"

    async def test_cancel_completed_job_raises(self, db_session, project_id: str):
        jid = await _create_job(db_session, project_id, "success")
        svc = JobService(db_session)
        with pytest.raises(ValueError, match="Cannot cancel"):
            await svc.cancel_job(jid)

    async def test_cancel_failed_job_raises(self, db_session, project_id: str):
        jid = await _create_job(db_session, project_id, "failed")
        svc = JobService(db_session)
        with pytest.raises(ValueError, match="Cannot cancel"):
            await svc.cancel_job(jid)

    async def test_cancel_nonexistent_job(self, db_session):
        svc = JobService(db_session)
        result = await svc.cancel_job(uuid4())
        assert result is None
