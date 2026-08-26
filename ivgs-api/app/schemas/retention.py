"""
Retention policy Pydantic schemas per §5.2.6.

Includes: RetentionPolicyCreate, RetentionPolicyUpdate,
RetentionPolicyResponse, RetentionReportResponse.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetentionPolicyCreate(BaseModel):
    """Schema for creating a new retention policy."""

    name: str = Field(min_length=1, max_length=128, description="Policy name (unique)")
    description: Optional[str] = Field(default=None, max_length=500)
    hot_days: int = Field(ge=1, le=365, description="Days in hot tier (SSD)")
    warm_days: int = Field(ge=1, le=730, description="Days in warm tier (HDD)")
    cold_days: int = Field(ge=1, le=1825, description="Days in cold tier (NAS)")
    archive_days: Optional[int] = Field(
        default=None, ge=1, le=3650, description="Days in archive tier"
    )
    delete_after_days: Optional[int] = Field(
        default=None, ge=1, le=7300, description="Days before permanent deletion"
    )
    applies_to: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Asset type or scope (null = all)",
    )
    is_default: bool = Field(default=False, description="Whether this is the default policy")

    @field_validator("warm_days")
    @classmethod
    def warm_after_hot(cls, v: int, info) -> int:
        hot_days = info.data.get("hot_days")
        if hot_days is not None and v < hot_days:
            raise ValueError("warm_days must be >= hot_days")
        return v

    @field_validator("cold_days")
    @classmethod
    def cold_after_warm(cls, v: int, info) -> int:
        warm_days = info.data.get("warm_days")
        if warm_days is not None and v < warm_days:
            raise ValueError("cold_days must be >= warm_days")
        return v


class RetentionPolicyUpdate(BaseModel):
    """Schema for updating a retention policy."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    hot_days: Optional[int] = Field(default=None, ge=1, le=365)
    warm_days: Optional[int] = Field(default=None, ge=1, le=730)
    cold_days: Optional[int] = Field(default=None, ge=1, le=1825)
    archive_days: Optional[int] = Field(default=None, ge=1, le=3650)
    delete_after_days: Optional[int] = Field(default=None, ge=1, le=7300)
    applies_to: Optional[str] = Field(default=None, max_length=128)
    is_default: Optional[bool] = None


class RetentionPolicyResponse(BaseModel):
    """Retention policy response."""

    id: UUID
    name: str
    description: Optional[str] = None
    hot_days: int
    warm_days: int
    cold_days: int
    archive_days: Optional[int] = None
    delete_after_days: Optional[int] = None
    applies_to: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TierDistribution(BaseModel):
    """Asset count and size distribution for a storage tier."""

    tier: str
    asset_count: int = 0
    total_size_bytes: int = 0


class UpcomingMigration(BaseModel):
    """Assets approaching tier migration threshold."""

    asset_id: UUID
    current_tier: str
    next_tier: str
    days_until_migration: int
    file_size_bytes: int = 0


class DedupSavings(BaseModel):
    """WP-57 Task 2 — deduplication savings, DERIVED (was ledger P2.4).

    P2.4 recorded that the figure was derivable and nothing derived it, so the
    panel honestly said "not computed". WP-45 restored ``assets.content_hash``
    and both columns this needs are populated on every row (measured: 159 of 159
    assets carry a hash), so the honest answer is no longer "unknown" — it is a
    number, and reporting it is the fix.

    ``bytes_saved`` is what deduplication ACTUALLY avoided storing, not an
    estimate of what compression might achieve. ``AssetService.upload_asset``
    increments ``reference_count`` instead of writing the bytes a second time,
    so every reference beyond the first is one copy not stored:

        bytes_saved = SUM(file_size_bytes * (reference_count - 1))

    ``duplicate_count`` is the number of avoided copies, not the number of rows
    involved — an asset referenced three times avoided two copies.

    A zero here now means "dedup ran and found nothing to save", which is a
    measurement. That is only true because the fields are populated; if they ever
    stop being, this must go back to saying it does not know.
    """

    bytes_saved: int = 0
    duplicate_count: int = 0
    percent: float = Field(
        default=0.0,
        description="bytes_saved as a percentage of what would have been stored without dedup",
    )


class RetentionReportResponse(BaseModel):
    """Retention report: asset distribution across tiers and upcoming migrations."""

    total_assets: int = 0
    total_size_bytes: int = 0
    tier_distribution: List[TierDistribution] = []
    upcoming_migrations: List[UpcomingMigration] = []
    policy_name: str = ""
    # None means "not derivable", which is a different answer from zero savings.
    dedup_savings: Optional[DedupSavings] = None
