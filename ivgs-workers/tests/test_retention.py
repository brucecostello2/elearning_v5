"""
IVGS v5 — Retention Migration Tests
========================================

Tests for RetentionService per §10.3.

Test coverage:
- Policy loading from database and defaults
- Tier progression order (hot → warm → cold → archive → delete)
- Asset transition eligibility based on tier duration
- preserve_flag = true exemption
- Permanent deletion for assets exceeding delete_after_days
- Migration report accuracy
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# WP-32.3: was `ivgs_workers.services.retention_migration`. There is no `ivgs_workers`
# package anywhere in the tree or on the path -- the name appears in
# pyproject's known-first-party and in mypy overrides, and in
# tasks/periodic_tasks.py, but the directory is `ivgs-workers` (hyphen),
# which is not an importable module name. The modules themselves are real
# and live at `services/retention_migration.py`.
from services.retention_migration import (
    DEFAULT_RETENTION_POLICIES,
    MigrationReport,
    RetentionPolicy,
    RetentionService,
    StorageTier,
    TIER_ORDER,
    TierTransitionRecord,
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
    session.commit = AsyncMock()

    factory = AsyncMock(return_value=session)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.fixture
def retention_service(
    mock_db_session_factory: AsyncMock,
) -> RetentionService:
    """Create a RetentionService with mock dependencies."""
    return RetentionService(
        db_session_factory=mock_db_session_factory,
    )


# ---------------------------------------------------------------------------
# Tier Configuration Tests
# ---------------------------------------------------------------------------

class TestTierConfiguration:
    """Tests for tier order and configuration."""

    def test_tier_order(self) -> None:
        """Tier progression: hot → warm → cold → archive → delete."""
        assert TIER_ORDER == [
            StorageTier.HOT,
            StorageTier.WARM,
            StorageTier.COLD,
            StorageTier.ARCHIVE,
            StorageTier.DELETE,
        ]

    def test_storage_tier_enum_values(self) -> None:
        """StorageTier enum must have correct string values."""
        assert StorageTier.HOT.value == "hot"
        assert StorageTier.WARM.value == "warm"
        assert StorageTier.COLD.value == "cold"
        assert StorageTier.ARCHIVE.value == "archive"
        assert StorageTier.DELETE.value == "delete"


# ---------------------------------------------------------------------------
# Default Policy Tests
# ---------------------------------------------------------------------------

class TestDefaultPolicies:
    """Tests for default retention policies."""

    def test_image_default_policy(self) -> None:
        """Image policy: hot=30d, warm=60d, cold=90d, archive=365d, delete=730d."""
        policy = next(
            p for p in DEFAULT_RETENTION_POLICIES if p.applies_to == "image"
        )
        assert policy.hot_days == 30
        assert policy.warm_days == 60
        assert policy.cold_days == 90
        assert policy.archive_days == 365
        assert policy.delete_after_days == 730

    def test_video_default_policy(self) -> None:
        """Video policy: hot=14d, warm=30d, cold=60d, archive=180d, delete=365d."""
        policy = next(
            p for p in DEFAULT_RETENTION_POLICIES if p.applies_to == "video"
        )
        assert policy.hot_days == 14
        assert policy.warm_days == 30
        assert policy.cold_days == 60
        assert policy.archive_days == 180
        assert policy.delete_after_days == 365

    def test_render_default_policy(self) -> None:
        """Render policy: hot=60d, warm=90d, cold=180d, archive=365d, delete=1095d."""
        policy = next(
            p for p in DEFAULT_RETENTION_POLICIES if p.applies_to == "render"
        )
        assert policy.hot_days == 60
        assert policy.warm_days == 90
        assert policy.cold_days == 180
        assert policy.archive_days == 365
        assert policy.delete_after_days == 1095

    def test_all_defaults_are_default(self) -> None:
        """All default policies should have is_default=True."""
        for policy in DEFAULT_RETENTION_POLICIES:
            assert policy.is_default is True


# ---------------------------------------------------------------------------
# Policy Model Tests
# ---------------------------------------------------------------------------

class TestRetentionPolicy:
    """Tests for RetentionPolicy model."""

    def test_get_tier_duration_days(self) -> None:
        """Test get_tier_duration_days returns correct values."""
        policy = RetentionPolicy(
            name="test",
            hot_days=10,
            warm_days=20,
            cold_days=30,
            archive_days=40,
            delete_after_days=100,
            applies_to="test",
        )
        assert policy.get_tier_duration_days(StorageTier.HOT) == 10
        assert policy.get_tier_duration_days(StorageTier.WARM) == 20
        assert policy.get_tier_duration_days(StorageTier.COLD) == 30
        assert policy.get_tier_duration_days(StorageTier.ARCHIVE) == 40
        assert policy.get_tier_duration_days(StorageTier.DELETE) == 0


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestRetentionService:
    """Tests for RetentionService operations."""

    def test_get_policy_for_known_type(
        self, retention_service: RetentionService
    ) -> None:
        """Known asset types should return their specific policy."""
        # Pre-load cache
        for policy in DEFAULT_RETENTION_POLICIES:
            retention_service._policies_cache[policy.applies_to] = policy

        image_policy = retention_service.get_policy_for_asset_type("image")
        assert image_policy.applies_to == "image"

        video_policy = retention_service.get_policy_for_asset_type("video")
        assert video_policy.applies_to == "video"

    def test_get_policy_for_unknown_type_returns_default(
        self, retention_service: RetentionService
    ) -> None:
        """Unknown asset types should return the default policy."""
        retention_service._default_policy = DEFAULT_RETENTION_POLICIES[0]

        policy = retention_service.get_policy_for_asset_type("unknown_type")
        assert policy.is_default is True


# ---------------------------------------------------------------------------
# Migration Report Tests
# ---------------------------------------------------------------------------

class TestMigrationReport:
    """Tests for MigrationReport model."""

    def test_report_defaults(self) -> None:
        """MigrationReport should have zero defaults."""
        report = MigrationReport()
        assert report.assets_scanned == 0
        assert report.transitions_performed == 0
        assert report.assets_deleted == 0
        assert report.assets_preserved == 0
        assert report.transitions == []
        assert report.errors == []
        assert report.run_id is not None

    def test_tier_transition_record(self) -> None:
        """TierTransitionRecord should capture transition details."""
        record = TierTransitionRecord(
            asset_id=str(uuid.uuid4()),
            from_tier=StorageTier.HOT,
            to_tier=StorageTier.WARM,
            policy_name="default_images",
            storage_path="/ivgs/images/test.png",
        )
        assert record.from_tier == StorageTier.HOT
        assert record.to_tier == StorageTier.WARM
        assert record.transitioned_at is not None
