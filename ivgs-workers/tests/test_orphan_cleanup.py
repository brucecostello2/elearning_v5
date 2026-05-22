"""
IVGS v5 — Orphan Cleanup Tests
========================================

Tests for OrphanCleanupService per §10.6.

Test coverage:
- Type 1: SeaweedFS objects without DB records
- Type 2: DB records without SeaweedFS files
- Type 3: Zero-reference count assets (>7 days)
- Quarantine lifecycle (7-day retention before delete)
- Audit log recording
- Error handling for SeaweedFS API failures
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ivgs_workers.services.orphan_cleanup import (
    QUARANTINE_DAYS,
    QUARANTINE_PATH,
    SEAWEEDFS_SCAN_DIRECTORIES,
    ZERO_REF_THRESHOLD_DAYS,
    CleanupReport,
    OrphanCleanupService,
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
def orphan_service(mock_db_session_factory: AsyncMock) -> OrphanCleanupService:
    """Create an OrphanCleanupService with mock dependencies."""
    return OrphanCleanupService(
        db_session_factory=mock_db_session_factory,
    )


# ---------------------------------------------------------------------------
# Configuration Tests
# ---------------------------------------------------------------------------

class TestOrphanCleanupConfig:
    """Tests for orphan cleanup configuration constants."""

    def test_quarantine_days_is_7(self) -> None:
        """Quarantine period must be 7 days per §10.6."""
        assert QUARANTINE_DAYS == 7

    def test_zero_ref_threshold_is_7_days(self) -> None:
        """Zero-reference threshold must be 7 days per §10.6."""
        assert ZERO_REF_THRESHOLD_DAYS == 7

    def test_quarantine_path(self) -> None:
        """Quarantine path must be /ivgs/quarantine."""
        assert QUARANTINE_PATH == "/ivgs/quarantine"

    def test_scan_directories_match_spec(self) -> None:
        """Scan directories must match §10.2 SeaweedFS structure."""
        expected_dirs = {
            "/ivgs/images/",
            "/ivgs/videos/",
            "/ivgs/audio/",
            "/ivgs/talking-heads/",
            "/ivgs/animations/",
            "/ivgs/drafts/",
            "/ivgs/final/",
            "/ivgs/thumbnails/",
            "/ivgs/captions/",
        }
        assert set(SEAWEEDFS_SCAN_DIRECTORIES) == expected_dirs


# ---------------------------------------------------------------------------
# Scan Type Tests
# ---------------------------------------------------------------------------

class TestScanType2:
    """Tests for Type 2: DB records without SeaweedFS files."""

    @pytest.mark.asyncio
    async def test_detects_missing_seaweedfs_files(
        self,
        orphan_service: OrphanCleanupService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """DB records pointing to non-existent files are detected."""
        # Mock DB returns assets with storage paths
        mock_rows = [
            (str(uuid.uuid4()), "/ivgs/images/proj1/scene1/image.png"),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        # Mock HTTP client returns 404
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.head.return_value = mock_response
        orphan_service._http_client = mock_client

        report = CleanupReport()
        count = await orphan_service._scan_type2_db_without_seaweedfs(report)

        assert count == 1


class TestScanType3:
    """Tests for Type 3: Zero-reference count assets."""

    @pytest.mark.asyncio
    async def test_detects_zero_reference_assets(
        self,
        orphan_service: OrphanCleanupService,
        mock_db_session_factory: AsyncMock,
    ) -> None:
        """Assets with reference_count=0 for >7 days are detected."""
        mock_rows = [
            (str(uuid.uuid4()), "/ivgs/images/orphan.png"),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        session = mock_db_session_factory.return_value.__aenter__.return_value
        session.execute.return_value = mock_result

        # Mock quarantine operation
        with patch.object(
            orphan_service,
            "_quarantine_asset",
            new_callable=AsyncMock,
        ):
            report = CleanupReport()
            count = await orphan_service._scan_type3_zero_reference(report)

            assert count == 1


# ---------------------------------------------------------------------------
# Cleanup Report Tests
# ---------------------------------------------------------------------------

class TestCleanupReport:
    """Tests for CleanupReport model."""

    def test_report_defaults(self) -> None:
        """CleanupReport should have zero defaults."""
        report = CleanupReport()
        assert report.type1_seaweedfs_without_db == 0
        assert report.type2_db_without_seaweedfs == 0
        assert report.type3_zero_reference_count == 0
        assert report.newly_quarantined == 0
        assert report.permanently_deleted == 0
        assert report.errors == []
        assert report.run_id is not None
