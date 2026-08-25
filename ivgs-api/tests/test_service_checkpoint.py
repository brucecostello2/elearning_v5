"""
Phase 4 Gap 1: Checkpoint Service Tests

Tests CheckpointService: list_checkpoints, get_stage_checkpoint,
resume_from_checkpoint, clear_checkpoints.

Critical Path #8 tests included:
  - test_checkpoint_create_at_stage
  - test_checkpoint_resume_from_latest
  - test_checkpoint_resume_skips_completed_stages
  - test_checkpoint_clear_removes_all
"""
import uuid

import pytest
from sqlalchemy import text

from app.services.checkpoint_service import CheckpointService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_user(db):
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, username, password_hash, role) VALUES (:uid, :u, 'x', 'admin')"),
        {"uid": str(uid), "u": f"cpuser-{uuid.uuid4().hex[:8]}"},
    )
    await db.commit()
    return uid


async def _create_project(db, user_id):
    pid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO projects (id, name, created_by) VALUES (:pid, :n, :uid)"),
        {"pid": str(pid), "n": f"CP-Project-{uuid.uuid4().hex[:6]}", "uid": str(user_id)},
    )
    await db.commit()
    return pid


async def _create_job(db, project_id, status="failed"):
    jid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO render_jobs (id, project_id, job_type, status) "
            "VALUES (:jid, :pid, 'video_generation', :status)"
        ),
        {"jid": str(jid), "pid": str(project_id), "status": status},
    )
    await db.commit()
    return jid


async def _create_checkpoint(db, job_id, stage_name, stage_index, status="complete"):
    cpid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO pipeline_checkpoints (id, job_id, stage_name, stage_index, status) "
            "VALUES (:cpid, :jid, :stage, :idx, :status)"
        ),
        {
            "cpid": str(cpid),
            "jid": str(job_id),
            "stage": stage_name,
            "idx": stage_index,
            "status": status,
        },
    )
    await db.commit()
    return cpid


# ===========================================================================
# Critical Path #8 Tests (exact v3 Section 10 names)
# ===========================================================================

class TestCriticalPath8:
    """v3 Section 10 — Pipeline checkpoint → resume from failure."""

    async def test_checkpoint_create_at_stage(self, db_session):
        """Checkpoint creation is verified by listing after insert."""
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)
        await _create_checkpoint(db_session, jid, "transcript_refinement", 0)

        svc = CheckpointService(db_session)
        result = await svc.list_checkpoints(jid)
        assert result is not None
        assert result.total_stages == 1
        assert result.checkpoints[0].stage_name == "transcript_refinement"

    async def test_checkpoint_resume_from_latest(self, db_session):
        """Resume picks up from last completed stage."""
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid, status="failed")
        await _create_checkpoint(db_session, jid, "transcript_refinement", 0, "complete")
        await _create_checkpoint(db_session, jid, "storyboard_generation", 1, "complete")
        await _create_checkpoint(db_session, jid, "media_generation", 2, "failed")

        svc = CheckpointService(db_session)
        result = await svc.resume_from_checkpoint(jid, "admin")
        assert result is not None
        # WP-45: the same POSITION, in the vocabulary the orchestrator can
        # actually dispatch. This value is handed to dispatch_pipeline as
        # `resume_from_stage` and looked up in STAGE_TASK_MAP, which is keyed by
        # PipelineStage values - and "media_generation" is not one of them.
        # Naming the spec stage here produced a resume that could not be
        # dispatched, which never showed because the endpoint dispatched nothing
        # (swallow-register entry 17).
        assert result.resume_from_stage == "image_generation"
        assert result.new_job_id is not None

    async def test_checkpoint_resume_skips_completed_stages(self, db_session):
        """Resume doesn't restart completed stages — skips to next after last complete."""
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid, status="failed")
        # Only first 2 stages complete, stage 2 (media_gen) failed
        await _create_checkpoint(db_session, jid, "transcript_refinement", 0, "complete")
        await _create_checkpoint(db_session, jid, "storyboard_generation", 1, "failed")

        svc = CheckpointService(db_session)
        result = await svc.resume_from_checkpoint(jid, "admin")
        assert result is not None
        # Last complete is transcript_refinement (idx=0), so resume from storyboard_generation (idx=1)
        assert result.resume_from_stage == "storyboard_generation"

    async def test_checkpoint_clear_removes_all(self, db_session):
        """Clearing checkpoints removes all entries for a job."""
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)
        await _create_checkpoint(db_session, jid, "stage_a", 0)
        await _create_checkpoint(db_session, jid, "stage_b", 1)

        svc = CheckpointService(db_session)
        deleted = await svc.clear_checkpoints(jid, "admin")
        assert deleted == 2

        # Verify empty
        result = await svc.list_checkpoints(jid)
        assert result.total_stages == 0


# ===========================================================================
# Additional Tests
# ===========================================================================

class TestListCheckpoints:
    async def test_list_nonexistent_job(self, db_session):
        """Listing checkpoints for non-existent job returns None."""
        svc = CheckpointService(db_session)
        result = await svc.list_checkpoints(uuid.uuid4())
        assert result is None

    async def test_list_empty_checkpoints(self, db_session):
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)

        svc = CheckpointService(db_session)
        result = await svc.list_checkpoints(jid)
        assert result is not None
        assert result.total_stages == 0
        assert result.checkpoints == []

    async def test_list_counts_completed_and_failed(self, db_session):
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)
        await _create_checkpoint(db_session, jid, "s1", 0, "complete")
        await _create_checkpoint(db_session, jid, "s2", 1, "complete")
        await _create_checkpoint(db_session, jid, "s3", 2, "failed")

        svc = CheckpointService(db_session)
        result = await svc.list_checkpoints(jid)
        assert result.completed_stages == 2
        assert result.failed_stages == 1
        assert result.last_successful_stage == "s2"


class TestGetStageCheckpoint:
    async def test_get_existing_stage(self, db_session):
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)
        await _create_checkpoint(db_session, jid, "media_generation", 2)

        svc = CheckpointService(db_session)
        result = await svc.get_stage_checkpoint(jid, "media_generation")
        assert result is not None
        assert result.stage_name == "media_generation"

    async def test_get_nonexistent_stage(self, db_session):
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)

        svc = CheckpointService(db_session)
        result = await svc.get_stage_checkpoint(jid, "nonexistent")
        assert result is None


class TestResumeFromCheckpoint:
    async def test_resume_non_failed_job_raises(self, db_session):
        """Can only resume from failed jobs."""
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid, status="running")

        svc = CheckpointService(db_session)
        with pytest.raises(ValueError, match="Cannot resume"):
            await svc.resume_from_checkpoint(jid, "admin")

    async def test_resume_no_checkpoints_starts_from_beginning(self, db_session):
        """If no checkpoints exist, resume from first stage."""
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid, status="failed")

        svc = CheckpointService(db_session)
        result = await svc.resume_from_checkpoint(jid, "admin")
        assert result.resume_from_stage == "transcript_refinement"

    async def test_resume_nonexistent_job(self, db_session):
        svc = CheckpointService(db_session)
        result = await svc.resume_from_checkpoint(uuid.uuid4(), "admin")
        assert result is None


class TestClearCheckpoints:
    async def test_clear_nonexistent_job(self, db_session):
        svc = CheckpointService(db_session)
        result = await svc.clear_checkpoints(uuid.uuid4(), "admin")
        assert result is None

    async def test_clear_empty(self, db_session):
        uid = await _create_user(db_session)
        pid = await _create_project(db_session, uid)
        jid = await _create_job(db_session, pid)

        svc = CheckpointService(db_session)
        deleted = await svc.clear_checkpoints(jid, "admin")
        assert deleted == 0
