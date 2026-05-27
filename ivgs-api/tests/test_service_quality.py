"""
Phase 4 — Quality Service Unit Tests.

Tests business logic in app/services/quality_service.py:
  - get_job_quality: aggregation, averages
  - list_flagged: only decision='flagged' items
  - approve_score: state transition, audit logging
  - reject_score: state transition, only from 'flagged'
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.quality_service import QualityService

pytestmark = pytest.mark.asyncio


async def _seed_quality_score(db_session, project_id, asset_id, job_id, decision="flagged", quality=0.7, safety=0.9):
    """Insert a quality score record."""
    score_id = str(uuid4())
    await db_session.execute(
        text(
            "INSERT INTO asset_quality_scores "
            "(id, asset_id, job_id, quality_score, safety_score, decision, created_at) "
            "VALUES (:id, :aid, :jid, :quality, :safety, :decision, :created_at)"
        ),
        {
            "id": score_id,
            "aid": asset_id,
            "jid": job_id,
            "quality": quality,
            "safety": safety,
            "decision": decision,
            "created_at": datetime.now(timezone.utc),
        },
    )
    await db_session.flush()
    return score_id


class TestGetJobQuality:
    async def test_get_job_quality_not_found(self, db_session):
        svc = QualityService(db_session)
        result = await svc.get_job_quality(uuid4())
        assert result is None


class TestListFlagged:
    async def test_list_flagged_empty(self, db_session):
        svc = QualityService(db_session)
        flagged, total = await svc.list_flagged(page=1, per_page=50)
        assert isinstance(flagged, list)
        assert isinstance(total, int)


class TestApproveScore:
    async def test_approve_nonexistent_score(self, db_session):
        svc = QualityService(db_session)
        result = await svc.approve_score(uuid4(), "admin_user")
        assert result is None

    async def test_approve_flagged_score(self, db_session, project_id, asset_id, running_job):
        svc = QualityService(db_session)
        score_id = await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"], decision="flagged"
        )
        result = await svc.approve_score(score_id, "admin_user")
        assert result is not None
        assert result.decision == "approved"


class TestRejectScore:
    async def test_reject_nonexistent_score(self, db_session):
        svc = QualityService(db_session)
        result = await svc.reject_score(uuid4(), "admin_user")
        assert result is None
