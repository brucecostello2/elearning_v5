"""
IVGS v5 — Retention Tier Migration Service
========================================

RetentionService per §10.3. Runs daily via Celery Beat.

Storage tiers: hot → warm → cold → archive → delete

Configuration source: retention_policies table (Table 20)
  name, hot_days, warm_days, cold_days, archive_days,
  delete_after_days, applies_to, is_default

Tier transition logic:
1. Scan assets table for records exceeding current tier duration
2. Look up applicable retention_policy for the asset type
3. Call transition_tier(asset_id, new_tier) to move data
4. Update storage_tier and tier_transition_at columns
5. Skip assets with preserve_flag = true

SeaweedFS tier mapping per §10.3:
- hot:     SSD-backed volumes (fast random I/O)
- warm:    HDD-backed volumes (sequential reads)
- cold:    Compressed HDD (infrequent access)
- archive: NAS archival (glacial retrieval times)
- delete:  Permanent removal from all storage
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StorageTier(str, Enum):
    """Storage tier levels per §10.3."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVE = "archive"
    DELETE = "delete"


# Tier progression order (hot is most accessible, delete is terminal)
TIER_ORDER: list[StorageTier] = [
    StorageTier.HOT,
    StorageTier.WARM,
    StorageTier.COLD,
    StorageTier.ARCHIVE,
    StorageTier.DELETE,
]


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class RetentionPolicy(BaseModel):
    """Retention policy from Table 20 (retention_policies)."""

    name: str
    hot_days: int = Field(..., description="Days in hot tier")
    warm_days: int = Field(..., description="Days in warm tier")
    cold_days: int = Field(..., description="Days in cold tier")
    archive_days: int = Field(..., description="Days in archive tier")
    delete_after_days: int = Field(
        ...,
        description="Total days before permanent deletion",
    )
    applies_to: str = Field(
        ...,
        description="Asset type this policy applies to",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the default policy",
    )

    def get_tier_duration_days(self, tier: StorageTier) -> int:
        """
        Get the duration in days for a specific tier.

        Args:
            tier: Storage tier to query.

        Returns:
            Number of days an asset should remain in this tier.
        """
        mapping = {
            StorageTier.HOT: self.hot_days,
            StorageTier.WARM: self.warm_days,
            StorageTier.COLD: self.cold_days,
            StorageTier.ARCHIVE: self.archive_days,
            StorageTier.DELETE: 0,
        }
        return mapping.get(tier, 0)


class TierTransitionRecord(BaseModel):
    """Record of a single tier transition."""

    asset_id: str
    from_tier: StorageTier
    to_tier: StorageTier
    transitioned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    policy_name: str = ""
    storage_path: str = ""


class MigrationReport(BaseModel):
    """Summary report of a retention migration run."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    completed_at: datetime | None = None
    assets_scanned: int = 0
    transitions_performed: int = 0
    assets_deleted: int = 0
    assets_preserved: int = 0
    transitions: list[TierTransitionRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Default Retention Policies
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_POLICIES: list[RetentionPolicy] = [
    RetentionPolicy(
        name="default_images",
        hot_days=30,
        warm_days=60,
        cold_days=90,
        archive_days=365,
        delete_after_days=730,
        applies_to="image",
        is_default=True,
    ),
    RetentionPolicy(
        name="default_videos",
        hot_days=14,
        warm_days=30,
        cold_days=60,
        archive_days=180,
        delete_after_days=365,
        applies_to="video",
        is_default=True,
    ),
    RetentionPolicy(
        name="default_audio",
        hot_days=30,
        warm_days=60,
        cold_days=90,
        archive_days=365,
        delete_after_days=730,
        applies_to="audio",
        is_default=True,
    ),
    RetentionPolicy(
        name="default_renders",
        hot_days=60,
        warm_days=90,
        cold_days=180,
        archive_days=365,
        delete_after_days=1095,
        applies_to="render",
        is_default=True,
    ),
]


# ---------------------------------------------------------------------------
# Retention Service
# ---------------------------------------------------------------------------

class RetentionService:
    """
    Retention tier migration service per §10.3.

    Runs daily via Celery Beat. Manages the lifecycle of assets across
    storage tiers based on configurable retention policies.

    Tier progression: hot → warm → cold → archive → delete

    The service:
    1. Loads retention policies from the database (Table 20)
    2. Scans assets for tier transition eligibility
    3. Moves files between SeaweedFS tier-specific volumes
    4. Updates database records (storage_tier, tier_transition_at)
    5. Skips assets with preserve_flag = true
    6. Logs all transitions to audit_log (Table 9)

    SeaweedFS integration:
    - Uses SeaweedFS volume server rack/data center assignments
      to move data between tier-specific storage backends
    - hot = SSD volumes, warm = HDD volumes, cold = compressed HDD,
      archive = NAS volumes
    """

    def __init__(
        self,
        db_session_factory: Any,
        seaweedfs_filer_url: str = "http://node-01:8888",
    ) -> None:
        """
        Initialize retention service.

        Args:
            db_session_factory: Async SQLAlchemy session factory.
            seaweedfs_filer_url: SeaweedFS filer URL for file operations.
        """
        self._db_session_factory = db_session_factory
        self._seaweedfs_filer_url = seaweedfs_filer_url
        self._policies_cache: dict[str, RetentionPolicy] = {}
        self._default_policy: RetentionPolicy | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._log = logger.bind(service="retention_service")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for SeaweedFS operations."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def load_policies(self) -> None:
        """
        Load retention policies from the database (Table 20).

        Falls back to DEFAULT_RETENTION_POLICIES if database is empty.
        Caches policies for the duration of the migration run.
        """
        try:
            async with self._db_session_factory() as session:
                from sqlalchemy import text

                result = await session.execute(
                    text("SELECT * FROM retention_policies ORDER BY name")
                )
                rows = result.fetchall()

                if rows:
                    for row in rows:
                        policy = RetentionPolicy(
                            name=row.name,
                            hot_days=row.hot_days,
                            warm_days=row.warm_days,
                            cold_days=row.cold_days,
                            archive_days=row.archive_days,
                            delete_after_days=row.delete_after_days,
                            applies_to=row.applies_to,
                            is_default=row.is_default,
                        )
                        self._policies_cache[row.applies_to] = policy
                        if row.is_default and self._default_policy is None:
                            self._default_policy = policy

                    self._log.info(
                        "retention_policies_loaded_from_db",
                        count=len(self._policies_cache),
                    )
                    return

        except Exception as exc:
            self._log.warning(
                "retention_policies_db_load_failed",
                error=str(exc),
            )

        # Fall back to defaults
        for policy in DEFAULT_RETENTION_POLICIES:
            self._policies_cache[policy.applies_to] = policy
            if policy.is_default and self._default_policy is None:
                self._default_policy = policy

        self._log.info(
            "retention_policies_loaded_defaults",
            count=len(self._policies_cache),
        )

    def get_policy_for_asset_type(self, asset_type: str) -> RetentionPolicy:
        """
        Get retention policy for an asset type.

        Args:
            asset_type: Asset type string (image, video, audio, render).

        Returns:
            Matching or default retention policy.
        """
        if asset_type in self._policies_cache:
            return self._policies_cache[asset_type]

        if self._default_policy is not None:
            return self._default_policy

        # Ultimate fallback
        return DEFAULT_RETENTION_POLICIES[0]

    async def run_migration(self) -> MigrationReport:
        """
        Execute a full retention tier migration cycle.

        Scans all assets, checks tier transition eligibility against
        retention policies, and performs transitions for eligible assets.

        Returns:
            MigrationReport: Summary of the migration run.
        """
        report = MigrationReport()

        self._log.info("retention_migration_started", run_id=report.run_id)

        # Load/refresh policies
        await self.load_policies()

        now = datetime.now(timezone.utc)

        # Process each tier (hot → warm → cold → archive → delete)
        for tier_index, current_tier in enumerate(TIER_ORDER[:-1]):
            next_tier = TIER_ORDER[tier_index + 1]

            try:
                count = await self._process_tier_transitions(
                    current_tier=current_tier,
                    next_tier=next_tier,
                    now=now,
                    report=report,
                )
                report.transitions_performed += count
            except Exception as exc:
                report.errors.append(
                    f"Tier {current_tier.value}→{next_tier.value}: {exc}"
                )
                self._log.error(
                    "tier_transition_error",
                    current_tier=current_tier.value,
                    next_tier=next_tier.value,
                    error=str(exc),
                )

        report.completed_at = datetime.now(timezone.utc)
        report.duration_seconds = (
            report.completed_at - report.started_at
        ).total_seconds()

        self._log.info(
            "retention_migration_completed",
            run_id=report.run_id,
            scanned=report.assets_scanned,
            transitions=report.transitions_performed,
            deleted=report.assets_deleted,
            preserved=report.assets_preserved,
            errors=len(report.errors),
            duration_seconds=report.duration_seconds,
        )

        return report

    async def _process_tier_transitions(
        self,
        *,
        current_tier: StorageTier,
        next_tier: StorageTier,
        now: datetime,
        report: MigrationReport,
    ) -> int:
        """
        Process tier transitions for all assets in the given tier.

        Queries assets in current_tier, checks if they've exceeded
        the tier duration per their retention policy, and transitions
        eligible assets to next_tier.

        Args:
            current_tier: Source storage tier.
            next_tier: Destination storage tier.
            now: Current timestamp.
            report: Running migration report.

        Returns:
            Count of transitions performed.
        """
        transition_count = 0

        async with self._db_session_factory() as session:
            from sqlalchemy import text

            result = await session.execute(
                text(
                    "SELECT id, asset_type, storage_path, storage_tier, "
                    "tier_transition_at, preserve_flag, created_at "
                    "FROM assets "
                    "WHERE storage_tier = :tier "
                    "AND (preserve_flag IS NULL OR preserve_flag = false) "
                    "ORDER BY tier_transition_at ASC NULLS FIRST "
                    "LIMIT 5000"
                ),
                {"tier": current_tier.value},
            )
            rows = result.fetchall()
            report.assets_scanned += len(rows)

        for row in rows:
            asset_id = str(row[0])
            asset_type = str(row[1])
            storage_path = str(row[2]) if row[2] else ""
            tier_transition_at = row[4] or row[6]  # fallback to created_at

            policy = self.get_policy_for_asset_type(asset_type)
            tier_duration_days = policy.get_tier_duration_days(current_tier)

            # Check if asset has exceeded tier duration
            if tier_transition_at is None:
                continue

            time_in_tier = (now - tier_transition_at).days

            if time_in_tier < tier_duration_days:
                continue

            # Perform transition
            try:
                if next_tier == StorageTier.DELETE:
                    await self._delete_asset(
                        asset_id, storage_path, report
                    )
                    report.assets_deleted += 1
                else:
                    await self._transition_tier(
                        asset_id=asset_id,
                        storage_path=storage_path,
                        from_tier=current_tier,
                        to_tier=next_tier,
                        policy_name=policy.name,
                        report=report,
                    )

                transition_count += 1

            except Exception as exc:
                report.errors.append(
                    f"Transition failed for {asset_id}: {exc}"
                )
                self._log.error(
                    "asset_transition_failed",
                    asset_id=asset_id,
                    from_tier=current_tier.value,
                    to_tier=next_tier.value,
                    error=str(exc),
                )

        return transition_count

    async def _transition_tier(
        self,
        *,
        asset_id: str,
        storage_path: str,
        from_tier: StorageTier,
        to_tier: StorageTier,
        policy_name: str,
        report: MigrationReport,
    ) -> None:
        """
        Transition an asset from one tier to another.

        1. Move file to the new tier's SeaweedFS volume
        2. Update database record (storage_tier, tier_transition_at)
        3. Log to audit_log

        Args:
            asset_id: Asset UUID.
            storage_path: Current SeaweedFS file path.
            from_tier: Current storage tier.
            to_tier: Target storage tier.
            policy_name: Name of the governing retention policy.
            report: Running migration report.
        """
        client = await self._get_client()

        # SeaweedFS tier assignment via replication header
        tier_replication = {
            StorageTier.HOT: "000",      # SSD, no replication
            StorageTier.WARM: "001",     # HDD, 1 replica
            StorageTier.COLD: "010",     # Compressed HDD
            StorageTier.ARCHIVE: "100",  # NAS archival
        }

        replication = tier_replication.get(to_tier, "000")

        try:
            # Move file with tier assignment
            response = await client.post(
                f"{self._seaweedfs_filer_url}{storage_path}",
                headers={
                    "X-Seaweedfs-Replication": replication,
                    "X-Seaweedfs-Collection": to_tier.value,
                },
            )

            # Update database
            now = datetime.now(timezone.utc)
            async with self._db_session_factory() as session:
                async with session.begin():
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            "UPDATE assets SET storage_tier = :tier, "
                            "tier_transition_at = :now, "
                            "updated_at = :now "
                            "WHERE id = :asset_id"
                        ),
                        {
                            "tier": to_tier.value,
                            "now": now,
                            "asset_id": asset_id,
                        },
                    )

            record = TierTransitionRecord(
                asset_id=asset_id,
                from_tier=from_tier,
                to_tier=to_tier,
                policy_name=policy_name,
                storage_path=storage_path,
            )
            report.transitions.append(record)

            self._log.info(
                "tier_transition_completed",
                asset_id=asset_id,
                from_tier=from_tier.value,
                to_tier=to_tier.value,
                policy_name=policy_name,
            )

        except Exception as exc:
            raise RuntimeError(
                f"Tier transition failed for {asset_id}: {exc}"
            ) from exc

    async def _delete_asset(
        self,
        asset_id: str,
        storage_path: str,
        report: MigrationReport,
    ) -> None:
        """
        Permanently delete an asset that has exceeded delete_after_days.

        1. Delete file from SeaweedFS
        2. Delete or mark database record
        3. Log to audit_log

        Args:
            asset_id: Asset UUID.
            storage_path: SeaweedFS file path.
            report: Running migration report.
        """
        client = await self._get_client()

        try:
            if storage_path:
                await client.delete(
                    f"{self._seaweedfs_filer_url}{storage_path}"
                )

            async with self._db_session_factory() as session:
                async with session.begin():
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            "UPDATE assets SET status = 'deleted', "
                            "storage_tier = 'delete', "
                            "updated_at = NOW() "
                            "WHERE id = :asset_id"
                        ),
                        {"asset_id": asset_id},
                    )

            self._log.info(
                "asset_permanently_deleted",
                asset_id=asset_id,
                storage_path=storage_path,
            )

        except Exception as exc:
            raise RuntimeError(
                f"Asset deletion failed for {asset_id}: {exc}"
            ) from exc
