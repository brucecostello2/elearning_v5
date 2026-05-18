"""Pydantic schemas for GPU management API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class GpuNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_hostname: str
    gpu_index: int
    gpu_model: str
    total_vram_mb: int
    available_vram_mb: int
    compute_capability: Optional[str] = None
    status: str
    last_heartbeat_at: Optional[datetime] = None
    registered_at: datetime


class GpuReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gpu_node_id: int
    job_id: Optional[int] = None
    reserved_vram_mb: int
    model_name: Optional[str] = None
    status: str
    reserved_at: datetime
    expires_at: datetime


class GpuUtilizationSummary(BaseModel):
    total_nodes: int
    online_nodes: int
    draining_nodes: int
    offline_nodes: int
    total_vram_mb: int
    used_vram_mb: int
    utilization_pct: float


class DrainRequest(BaseModel):
    drain: bool = True
    reason: Optional[str] = None
