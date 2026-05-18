(excerpt)from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

StorageTier = Literal["hot", "warm", "cold", "archive"]

class RetentionPolicyCreate(BaseModel):
    name: str
    project_type: Optional[str] = None
    hot_days: int = Field(7, ge=1)
    warm_days: int = Field(30, ge=1)
    cold_days: int = Field(180, ge=1)
    delete_after_days: Optional[int] = None
    preserve_on_download: bool = True

class RetentionPolicyOut(RetentionPolicyCreate):
    id: int
    created_at: datetime

class TierOverrideRequest(BaseModel):
    output_ids: list[int]
    target_tier: StorageTier

class TierOverrideResponse(BaseModel):
    success: int
    errors: int

class QuotaSetRequest(BaseModel):
    project_id: int
    quota_tier: Literal["free", "standard", "enterprise", "custom"]
    custom_bytes: Optional[int] = None

class StorageCapacityResponse(BaseModel):
    timestamp: str
    tiers: dict
    dedup_ratio: dict

class BackupTriggerRequest(BaseModel):
    backup_type: Literal["incremental", "full"] = "incremental"

class BackupSnapshotOut(BaseModel):
    id: int
    snapshot_name: str
    backup_type: str
    status: str
    bytes_transferred: Optional[int]
    completed_at: Optional[datetime]

class ArchiveRestoreRequest(BaseModel):
    output_id: int
