"""
Phase 4 Gap Closure: Extended Retention Service Tests.

Targets uncovered branches in retention_service.py:
  - get_policy (found + not-found)
  - create_policy with is_default=True
  - update_policy (full coverage: found, not-found, name conflict, is_default)
  - get_report with assets and default policy (upcoming migrations)
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from app.services.retention_service import RetentionService
from app.schemas.retention import RetentionPolicyCreate, RetentionPolicyUpdate

pytestmark = pytest.mark.asyncio


# ── Helpers ──────────────────────────────────────────────────────────

async def _create_policy(svc, name, is_default=False, hot_days=7, warm_days=14, cold_days=30):
    data = RetentionPolicyCreate(
        name=name, hot_days=hot_days, warm_days=warm_days, cold_days=cold_days,
        is_default=is_default,
    )
    return await svc.create_policy(data)


# ── get_policy ───────────────────────────────────────────────────────

class TestGetPolicy:
    async def test_get_existing_policy(self, db_session):
        svc = RetentionService(db_session)
        created = await _create_policy(svc, f"get_exist_{uuid4().hex[:6]}")
        result = await svc.get_policy(created.id)
        assert result is not None
        assert result.id == created.id
        assert result.name == created.name

    async def test_get_nonexistent_policy_returns_none(self, db_session):
        svc = RetentionService(db_session)
        result = await svc.get_policy(uuid4())
        assert result is None


# ── create_policy with is_default ────────────────────────────────────

class TestCreatePolicyDefault:
    async def test_create_default_policy_clears_previous_default(self, db_session):
        svc = RetentionService(db_session)
        p1 = await _create_policy(svc, f"def1_{uuid4().hex[:6]}", is_default=True)
        assert p1.is_default is True

        p2 = await _create_policy(svc, f"def2_{uuid4().hex[:6]}", is_default=True)
        assert p2.is_default is True

        # p1 should no longer be default
        refreshed = await svc.get_policy(p1.id)
        assert refreshed.is_default is False


# ── update_policy ────────────────────────────────────────────────────

class TestUpdatePolicy:
    async def test_update_policy_success(self, db_session):
        svc = RetentionService(db_session)
        created = await _create_policy(svc, f"upd_{uuid4().hex[:6]}")
        updated = await svc.update_policy(
            created.id,
            RetentionPolicyUpdate(hot_days=10, description="updated"),
        )
        assert updated is not None
        assert updated.hot_days == 10
        assert updated.description == "updated"

    async def test_update_nonexistent_returns_none(self, db_session):
        svc = RetentionService(db_session)
        result = await svc.update_policy(uuid4(), RetentionPolicyUpdate(hot_days=5))
        assert result is None

    async def test_update_rename_success(self, db_session):
        svc = RetentionService(db_session)
        p = await _create_policy(svc, f"rename_src_{uuid4().hex[:6]}")
        new_name = f"rename_dst_{uuid4().hex[:6]}"
        result = await svc.update_policy(p.id, RetentionPolicyUpdate(name=new_name))
        assert result.name == new_name

    async def test_update_rename_duplicate_raises(self, db_session):
        svc = RetentionService(db_session)
        tag = uuid4().hex[:6]
        p1 = await _create_policy(svc, f"dup_a_{tag}")
        p2 = await _create_policy(svc, f"dup_b_{tag}")
        with pytest.raises(ValueError, match="already exists"):
            await svc.update_policy(p2.id, RetentionPolicyUpdate(name=p1.name))

    async def test_update_set_default_clears_others(self, db_session):
        svc = RetentionService(db_session)
        tag = uuid4().hex[:6]
        p1 = await _create_policy(svc, f"defa_{tag}", is_default=True)
        p2 = await _create_policy(svc, f"defb_{tag}")

        updated = await svc.update_policy(p2.id, RetentionPolicyUpdate(is_default=True))
        assert updated.is_default is True

        refreshed_p1 = await svc.get_policy(p1.id)
        assert refreshed_p1.is_default is False


# ── get_report with data ─────────────────────────────────────────────

class TestGetReportWithData:
    async def _seed_assets(self, db_session, project_id, count=3, tier="hot", age_days=5):
        """Seed assets in the given tier with the given age."""
        for _ in range(count):
            aid = uuid4()
            created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
            await db_session.execute(text("""
                INSERT INTO assets (id, project_id, asset_type, storage_tier,
                    file_size_bytes, content_hash, preserve_flag, created_at)
                VALUES (:id, :pid, 'image', :tier, 1048576, :hash, false, :cat)
            """), {
                "id": str(aid), "pid": str(project_id), "tier": tier,
                "hash": uuid4().hex, "cat": created_at,
            })
        await db_session.commit()

    async def _seed_project(self, db_session):
        pid = uuid4()
        uid = uuid4()
        await db_session.execute(text("""
            INSERT INTO users (id, username, password_hash, role, created_at, is_active)
            VALUES (:id, :un, 'x', 'admin', now(), true)
        """), {"id": str(uid), "un": f"ret_user_{uuid4().hex[:6]}"})
        await db_session.execute(text("""
            INSERT INTO projects (id, name, state, created_by, created_at, updated_at)
            VALUES (:id, :n, 'DRAFT', :uid, now(), now())
        """), {"id": str(pid), "n": f"ret_proj_{uuid4().hex[:6]}", "uid": str(uid)})
        await db_session.commit()
        return pid

    async def test_report_with_tier_distribution(self, db_session):
        """Report shows tier distribution when assets exist."""
        svc = RetentionService(db_session)
        pid = await self._seed_project(db_session)
        await self._seed_assets(db_session, pid, count=2, tier="hot")
        await self._seed_assets(db_session, pid, count=1, tier="warm")

        report = await svc.get_report()
        assert report.total_assets >= 3
        assert report.total_size_bytes > 0
        assert len(report.tier_distribution) >= 2
        tier_names = [t.tier for t in report.tier_distribution]
        assert "hot" in tier_names

    async def test_report_with_default_policy_and_upcoming_migrations(self, db_session):
        """Report calculates upcoming migrations when default policy exists."""
        svc = RetentionService(db_session)
        pid = await self._seed_project(db_session)

        # Create default policy with hot_days=7
        await _create_policy(svc, f"default_ret_{uuid4().hex[:6]}", is_default=True, hot_days=7)

        # Seed assets aged 5 days (days_until = 7-5 = 2, which is ≤7)
        await self._seed_assets(db_session, pid, count=2, tier="hot", age_days=5)

        report = await svc.get_report()
        assert report.policy_name != "none"
        assert len(report.upcoming_migrations) >= 2
        for m in report.upcoming_migrations:
            assert m.current_tier == "hot"
            assert m.next_tier == "warm"
            assert m.days_until_migration <= 7

    async def test_report_no_migrations_when_assets_too_new(self, db_session):
        """No upcoming migrations if assets are younger than threshold - 7."""
        svc = RetentionService(db_session)
        pid = await self._seed_project(db_session)

        # Create default policy with hot_days=30
        await _create_policy(svc, f"new_ret_{uuid4().hex[:6]}", is_default=True,
                             hot_days=30, warm_days=60, cold_days=90)

        # Seed assets aged 1 day (days_until = 30-1 = 29, which is > 7)
        await self._seed_assets(db_session, pid, count=2, tier="hot", age_days=1)

        report = await svc.get_report()
        # These assets should NOT be in upcoming_migrations
        new_migs = [m for m in report.upcoming_migrations if m.days_until_migration > 7]
        assert len(new_migs) == 0

    async def test_report_preserved_assets_excluded(self, db_session):
        """Assets with preserve_flag=true should not appear in upcoming migrations."""
        svc = RetentionService(db_session)
        pid = await self._seed_project(db_session)

        await _create_policy(svc, f"pres_ret_{uuid4().hex[:6]}", is_default=True, hot_days=7)

        # Seed preserved asset
        aid = uuid4()
        await db_session.execute(text("""
            INSERT INTO assets (id, project_id, asset_type, storage_tier,
                file_size_bytes, content_hash, preserve_flag, created_at)
            VALUES (:id, :pid, 'image', 'hot', 1024, :hash, true, :cat)
        """), {
            "id": str(aid), "pid": str(pid),
            "hash": uuid4().hex,
            "cat": datetime.now(timezone.utc) - timedelta(days=10),
        })
        await db_session.commit()

        report = await svc.get_report()
        migrating_ids = [m.asset_id for m in report.upcoming_migrations]
        assert aid not in migrating_ids


# ── Error handling ───────────────────────────────────────────────────

class TestRetentionErrorPaths:
    async def test_create_policy_validation_warm_less_than_hot(self):
        """Schema validation: warm_days must be >= hot_days."""
        with pytest.raises(Exception):
            RetentionPolicyCreate(
                name="bad_policy", hot_days=30, warm_days=10, cold_days=60,
            )

    async def test_create_policy_validation_cold_less_than_warm(self):
        """Schema validation: cold_days must be >= warm_days."""
        with pytest.raises(Exception):
            RetentionPolicyCreate(
                name="bad_cold", hot_days=7, warm_days=30, cold_days=10,
            )

    async def test_update_same_name_no_conflict(self, db_session):
        """Updating a policy with its own name should not raise."""
        svc = RetentionService(db_session)
        p = await _create_policy(svc, f"samename_{uuid4().hex[:6]}")
        result = await svc.update_policy(p.id, RetentionPolicyUpdate(name=p.name))
        assert result.name == p.name
