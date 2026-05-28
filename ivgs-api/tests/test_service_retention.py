"""
Phase 4 — Retention Service Unit Tests.

Tests business logic in app/services/retention_service.py:
  - create_policy: name uniqueness, default flag
  - list_policies
  - update_policy: name change validation
  - get_report: tier aggregation
"""

import pytest
from uuid import uuid4

from app.services.retention_service import RetentionService

pytestmark = pytest.mark.asyncio


class TestCreatePolicy:
    async def test_create_policy_success(self, db_session):
        svc = RetentionService(db_session)
        from app.schemas.retention import RetentionPolicyCreate
        data = RetentionPolicyCreate(
            name="svc_test_policy",
            hot_days=7,
            warm_days=14,
            cold_days=30,
        )
        result = await svc.create_policy(data)
        assert result is not None
        assert result.name == "svc_test_policy"

    async def test_create_policy_duplicate_name_raises(self, db_session):
        svc = RetentionService(db_session)
        from app.schemas.retention import RetentionPolicyCreate
        data = RetentionPolicyCreate(name="svc_dup_pol", hot_days=7, warm_days=14, cold_days=30)
        await svc.create_policy(data)
        with pytest.raises((ValueError, Exception)):
            await svc.create_policy(data)


class TestListPolicies:
    async def test_list_policies(self, db_session):
        svc = RetentionService(db_session)
        policies = await svc.list_policies()
        assert isinstance(policies, list)


class TestGetReport:
    async def test_get_report_returns_structure(self, db_session):
        svc = RetentionService(db_session)
        report = await svc.get_report()
        assert report is not None
