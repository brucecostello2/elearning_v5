"""
GPU Pydantic schemas per §5.2.1 and Appendix C.4.

Includes: GpuNodeCreate, GpuNodeUpdate, GpuNodeResponse,
GpuReservationResponse, GpuUtilizationResponse, GpuFleetSummary.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GpuNodeCreate(BaseModel):
    """Schema for registering a new GPU node."""

    node_hostname: str = Field(max_length=128, description="Node hostname")
    gpu_index: int = Field(ge=0, description="GPU device index")
    gpu_model: Optional[str] = Field(default=None, max_length=255, description="GPU model name")
    total_vram_mb: Optional[int] = Field(default=None, ge=0, description="Total VRAM in megabytes")
    compute_capability: Optional[str] = Field(
        default=None, max_length=32, description="CUDA compute capability string"
    )


class GpuNodeUpdate(BaseModel):
    """Schema for updating a GPU node."""

    gpu_model: Optional[str] = Field(default=None, max_length=255)
    total_vram_mb: Optional[int] = Field(default=None, ge=0)
    compute_capability: Optional[str] = Field(default=None, max_length=32)
    status: Optional[str] = Field(
        default=None,
        pattern="^(online|offline|draining)$",
        description="Node status",
    )


class ActiveJobSummary(BaseModel):
    """Active job summary embedded in GPU node response (C.4)."""

    job_id: UUID
    project_name: Optional[str] = None
    stage: Optional[str] = None
    started_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GpuReservationResponse(BaseModel):
    """GPU VRAM reservation response."""

    id: UUID
    gpu_node_id: UUID
    job_id: Optional[UUID] = None
    reserved_vram_mb: int
    model_name: Optional[str] = None
    status: str
    reserved_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GpuNodeResponse(BaseModel):
    """
    GPU node response per Appendix C.4.

    Includes computed fields: used_vram_mb, available_vram_mb,
    gpu_utilization_pct, active_jobs.
    """

    id: UUID
    node_hostname: str
    gpu_index: int
    gpu_model: Optional[str] = None
    total_vram_mb: Optional[int] = None
    used_vram_mb: int = 0
    available_vram_mb: int = 0
    gpu_utilization_pct: float = 0.0
    temperature_c: float = 0.0
    power_draw_w: float = 0.0
    compute_capability: Optional[str] = None
    status: str
    registered_at: datetime
    last_heartbeat_at: Optional[datetime] = None
    active_jobs: List[ActiveJobSummary] = []
    reservations: List[GpuReservationResponse] = []

    model_config = ConfigDict(from_attributes=True)


class GpuNodeSummary(BaseModel):
    """Compact GPU node summary for fleet utilization."""

    id: UUID
    node_hostname: str
    gpu_index: int
    gpu_model: Optional[str] = None
    total_vram_mb: int = 0
    used_vram_mb: int = 0
    available_vram_mb: int = 0
    status: str
    active_reservation_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class GpuFleetSummary(BaseModel):
    """Fleet-wide GPU utilization summary."""

    total_nodes: int = 0
    online_nodes: int = 0
    offline_nodes: int = 0
    draining_nodes: int = 0
    total_vram_mb: int = 0
    used_vram_mb: int = 0
    available_vram_mb: int = 0
    fleet_utilization_pct: float = 0.0
    active_reservations: int = 0
    nodes: List[GpuNodeSummary] = []
