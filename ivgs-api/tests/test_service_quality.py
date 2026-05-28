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

    async def test_get_job_quality_with_mixed_scores(
        self, db_session, project_id, asset_id, running_job
    ):
        """Three scores in mixed states: counts, averages, response shape."""
        job_id = running_job["id"]
        await _seed_quality_score(
            db_session, project_id, asset_id, job_id,
            decision="approved", quality=0.95, safety=0.99,
        )
        await _seed_quality_score(
            db_session, project_id, asset_id, job_id,
            decision="flagged", quality=0.60, safety=0.85,
        )
        await _seed_quality_score(
            db_session, project_id, asset_id, job_id,
            decision="rejected", quality=0.30, safety=0.50,
        )
        await db_session.commit()

        svc = QualityService(db_session)
        result = await svc.get_job_quality(job_id)
        assert result is not None
        assert result.total_assets == 3
        assert result.approved_count == 1
        assert result.flagged_count == 1
        assert result.rejected_count == 1
        # Averages: (0.95 + 0.60 + 0.30) / 3 = 0.6167; (0.99 + 0.85 + 0.50) / 3 = 0.78
        assert result.average_quality_score is not None
        assert abs(result.average_quality_score - 0.6167) < 0.001
        assert result.average_safety_score is not None
        assert abs(result.average_safety_score - 0.78) < 0.001
        assert len(result.scores) == 3

    async def test_get_job_quality_handles_null_score_values(
        self, db_session, project_id, asset_id, running_job
    ):
        """Score rows with NULL quality/safety should be excluded from average."""
        job_id = running_job["id"]
        # One score with values, one with NULLs
        await _seed_quality_score(
            db_session, project_id, asset_id, job_id,
            decision="approved", quality=0.80, safety=0.90,
        )
        # Insert a null-valued score via raw SQL (helper requires non-null)
        from sqlalchemy import text
        await db_session.execute(
            text(
                "INSERT INTO asset_quality_scores "
                "(id, asset_id, job_id, quality_score, safety_score, decision, created_at) "
                "VALUES (:id, :aid, :jid, NULL, NULL, 'flagged', :created_at)"
            ),
            {
                "id": str(uuid4()),
                "aid": asset_id,
                "jid": job_id,
                "created_at": datetime.now(timezone.utc),
            },
        )
        await db_session.commit()

        svc = QualityService(db_session)
        result = await svc.get_job_quality(job_id)
        assert result is not None
        assert result.total_assets == 2
        # Only the non-null score contributes to the average
        assert result.average_quality_score == 0.80
        assert result.average_safety_score == 0.90


class TestListFlagged:
    async def test_list_flagged_empty(self, db_session):
        svc = QualityService(db_session)
        flagged, total = await svc.list_flagged(page=1, per_page=50)
        assert isinstance(flagged, list)
        assert isinstance(total, int)

    async def test_list_flagged_returns_assets_with_project_context(
        self, db_session, project_id, asset_id, running_job
    ):
        """Flagged scores include asset_type, project_id, project_name."""
        await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"],
            decision="flagged", quality=0.55, safety=0.80,
        )
        # Add an approved score that should NOT appear in flagged list
        await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"],
            decision="approved", quality=0.95, safety=0.95,
        )
        await db_session.commit()

        svc = QualityService(db_session)
        flagged, total = await svc.list_flagged(page=1, per_page=50)
        assert total == 1
        assert len(flagged) == 1
        item = flagged[0]
        assert item.decision == "flagged"
        assert item.quality_score == 0.55
        assert str(item.project_id) == str(project_id)
        assert item.project_name is not None
        assert item.asset_type is not None

    async def test_list_flagged_pagination(
        self, db_session, project_id, asset_id, running_job
    ):
        """Pagination returns correct subset and accurate total."""
        # Seed 3 flagged scores
        for i in range(3):
            await _seed_quality_score(
                db_session, project_id, asset_id, running_job["id"],
                decision="flagged", quality=0.5 + i * 0.1, safety=0.7,
            )
        await db_session.commit()

        svc = QualityService(db_session)
        page1, total = await svc.list_flagged(page=1, per_page=2)
        assert total == 3
        assert len(page1) == 2

        page2, total2 = await svc.list_flagged(page=2, per_page=2)
        assert total2 == 3
        assert len(page2) == 1


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

    async def test_approve_score_wrong_state_raises(
        self, db_session, project_id, asset_id, running_job
    ):
        """Approving an already-approved (or rejected) score raises ValueError."""
        # Seed an already-approved score
        score_id = await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"], decision="approved"
        )
        await db_session.commit()

        svc = QualityService(db_session)
        with pytest.raises(ValueError, match="Cannot approve score with decision"):
            await svc.approve_score(score_id, "admin_user")


class TestRejectScore:
    async def test_reject_nonexistent_score(self, db_session):
        svc = QualityService(db_session)
        result = await svc.reject_score(uuid4(), "admin_user")
        assert result is None

    async def test_reject_flagged_score_with_regenerate(
        self, db_session, project_id, asset_id, running_job
    ):
        """Reject a flagged score with regenerate=True (default)."""
        score_id = await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"], decision="flagged"
        )
        await db_session.commit()

        svc = QualityService(db_session)
        result = await svc.reject_score(
            score_id, "admin_user", notes="Quality too low", regenerate=True
        )
        assert result is not None
        assert result.decision == "rejected"
        assert result.reviewed_by == "admin_user"
        assert result.review_notes == "Quality too low"
        assert result.reviewed_at is not None

    async def test_reject_flagged_score_without_regenerate(
        self, db_session, project_id, asset_id, running_job
    ):
        """Reject a flagged score with regenerate=False (no regen queued)."""
        score_id = await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"], decision="flagged"
        )
        await db_session.commit()

        svc = QualityService(db_session)
        result = await svc.reject_score(
            score_id, "admin_user", regenerate=False
        )
        assert result is not None
        assert result.decision == "rejected"
        assert result.reviewed_by == "admin_user"

    async def test_reject_score_wrong_state_raises(
        self, db_session, project_id, asset_id, running_job
    ):
        """Rejecting an already-rejected (or approved) score raises ValueError."""
        score_id = await _seed_quality_score(
            db_session, project_id, asset_id, running_job["id"], decision="approved"
        )
        await db_session.commit()

        svc = QualityService(db_session)
        with pytest.raises(ValueError, match="Cannot reject score with decision"):
            await svc.reject_score(score_id, "admin_user")
