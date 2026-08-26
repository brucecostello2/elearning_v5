"""
Retention policy service: policy CRUD and tier migration report.

Per §5.2.6 — manages retention policy lifecycle and provides reports
on asset distribution across storage tiers.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, update, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retention_policy import RetentionPolicy
from app.models.asset import Asset
from app.schemas.retention import (
    RetentionPolicyCreate,
    RetentionPolicyUpdate,
    RetentionPolicyResponse,
    DedupSavings,
    RetentionReportResponse,
    TierDistribution,
    UpcomingMigration,
)

logger = logging.getLogger(__name__)


class RetentionService:
    """Business logic for retention policy management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_policies(self) -> List[RetentionPolicyResponse]:
        """List all retention policies."""
        result = await self.db.execute(
            select(RetentionPolicy).order_by(RetentionPolicy.name)
        )
        policies = result.scalars().all()
        return [RetentionPolicyResponse.model_validate(p) for p in policies]

    async def get_policy(self, policy_id: UUID) -> Optional[RetentionPolicyResponse]:
        """Get a single retention policy by ID."""
        result = await self.db.execute(
            select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            return None
        return RetentionPolicyResponse.model_validate(policy)

    async def create_policy(
        self, data: RetentionPolicyCreate
    ) -> RetentionPolicyResponse:
        """
        Create a new retention policy.

        If is_default=True, clears is_default on all existing policies first.
        """
        # Check for name uniqueness
        existing = await self.db.execute(
            select(RetentionPolicy).where(RetentionPolicy.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Retention policy with name '{data.name}' already exists")

        # Clear existing default if setting this as default
        if data.is_default:
            await self.db.execute(
                update(RetentionPolicy)
                .where(RetentionPolicy.is_default.is_(True))
                .values(is_default=False)
            )

        policy = RetentionPolicy(
            name=data.name,
            description=data.description,
            hot_days=data.hot_days,
            warm_days=data.warm_days,
            cold_days=data.cold_days,
            archive_days=data.archive_days,
            delete_after_days=data.delete_after_days,
            applies_to=data.applies_to,
            is_default=data.is_default,
        )
        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)

        logger.info("Retention policy created: id=%s name=%s", policy.id, repr(policy.name))
        return RetentionPolicyResponse.model_validate(policy)

    async def update_policy(
        self, policy_id: UUID, data: RetentionPolicyUpdate
    ) -> Optional[RetentionPolicyResponse]:
        """
        Update a retention policy's tiers and thresholds.

        If is_default=True, clears is_default on all other policies.
        """
        result = await self.db.execute(
            select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Check name uniqueness if changing name
        if "name" in update_data and update_data["name"] != policy.name:
            name_check = await self.db.execute(
                select(RetentionPolicy).where(
                    RetentionPolicy.name == update_data["name"],
                    RetentionPolicy.id != policy_id,
                )
            )
            if name_check.scalar_one_or_none():
                raise ValueError(
                    f"Retention policy with name '{update_data['name']}' already exists"
                )

        # Clear existing default if setting this as default
        if update_data.get("is_default"):
            await self.db.execute(
                update(RetentionPolicy)
                .where(
                    RetentionPolicy.is_default.is_(True),
                    RetentionPolicy.id != policy_id,
                )
                .values(is_default=False)
            )

        for field, value in update_data.items():
            setattr(policy, field, value)

        policy.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(policy)

        logger.info(
            f"Retention policy updated: id={policy_id} "
            f"fields={list(update_data.keys())}"
        )
        return RetentionPolicyResponse.model_validate(policy)

    async def get_report(self) -> RetentionReportResponse:
        """
        Asset distribution across tiers and upcoming migrations.

        Queries the assets table for tier distribution counts and sizes,
        and identifies assets approaching tier transition thresholds.
        """
        # Total assets
        total_result = await self.db.execute(
            select(func.count(), func.coalesce(func.sum(Asset.file_size_bytes), 0))
            .select_from(Asset)
            .where(Asset.storage_tier.cast(String) != "deleted")
        )
        total_row = total_result.first()
        total_assets = total_row[0] if total_row else 0
        total_size = total_row[1] if total_row else 0

        # Tier distribution
        tier_result = await self.db.execute(
            select(
                Asset.storage_tier,
                func.count().label("cnt"),
                func.coalesce(func.sum(Asset.file_size_bytes), 0).label("total_size"),
            )
            .where(Asset.storage_tier.cast(String) != "deleted")
            .group_by(Asset.storage_tier)
            .order_by(Asset.storage_tier)
        )
        tier_distribution = [
            TierDistribution(tier=row[0], asset_count=row[1], total_size_bytes=row[2])
            for row in tier_result.all()
        ]

        # Get default retention policy for migration calculations
        default_policy_result = await self.db.execute(
            select(RetentionPolicy).where(RetentionPolicy.is_default.is_(True)).limit(1)
        )
        default_policy = default_policy_result.scalar_one_or_none()
        policy_name = default_policy.name if default_policy else "none"

        # Upcoming migrations: assets in hot tier approaching warm transition
        upcoming_migrations: List[UpcomingMigration] = []
        if default_policy:
            now = datetime.now(timezone.utc)
            hot_assets_result = await self.db.execute(
                select(Asset)
                .where(
                    Asset.storage_tier.cast(String) == "hot",
                    Asset.preserve_flag.is_(False),
                    Asset.created_at.isnot(None),
                )
                .order_by(Asset.created_at)
                .limit(50)
            )
            hot_assets = hot_assets_result.scalars().all()

            for asset in hot_assets:
                age_days = (now - asset.created_at).days
                days_until = max(0, default_policy.hot_days - age_days)
                if days_until <= 7:
                    upcoming_migrations.append(
                        UpcomingMigration(
                            asset_id=asset.id,
                            current_tier="hot",
                            next_tier="warm",
                            days_until_migration=days_until,
                            file_size_bytes=asset.file_size_bytes or 0,
                        )
                    )

        # WP-57 Task 2 — deduplication savings, derived rather than declared
        # unknown. Ledger P2.4 said the figure was derivable and nothing derived
        # it; both columns are populated on every row, so it is now computed.
        #
        # Only rows that were actually re-referenced contribute. `reference_count`
        # defaults to 1, so `reference_count - 1` is the number of copies dedup
        # avoided writing for that asset, and multiplying by its size is the
        # bytes not stored. Guarded on `> 1` so the sum is over avoided copies
        # rather than over every asset.
        dedup_row = (
            await self.db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            Asset.file_size_bytes * (Asset.reference_count - 1)
                        ),
                        0,
                    ),
                    func.coalesce(func.sum(Asset.reference_count - 1), 0),
                )
                .where(
                    Asset.storage_tier != "deleted",
                    Asset.reference_count > 1,
                    Asset.file_size_bytes.isnot(None),
                )
            )
        ).one()
        bytes_saved = int(dedup_row[0] or 0)
        duplicate_count = int(dedup_row[1] or 0)
        # Denominator is what storage WOULD have been without dedup.
        # int() is load-bearing: SUM() over a BigInteger column comes back as
        # decimal.Decimal, and `100.0 * int / Decimal` raises TypeError rather
        # than coercing. `total_size` is the same shape, so both are normalised
        # here instead of at the point of division.
        would_have_stored = int(total_size or 0) + bytes_saved
        dedup_savings = DedupSavings(
            bytes_saved=bytes_saved,
            duplicate_count=duplicate_count,
            percent=round(100.0 * bytes_saved / would_have_stored, 2)
            if would_have_stored
            else 0.0,
        )

        return RetentionReportResponse(
            total_assets=total_assets,
            total_size_bytes=total_size,
            tier_distribution=tier_distribution,
            upcoming_migrations=upcoming_migrations,
            policy_name=policy_name,
            dedup_savings=dedup_savings,
        )
