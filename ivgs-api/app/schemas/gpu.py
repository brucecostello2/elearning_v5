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
    power_tdp_w: Optional[int] = Field(default=None, ge=0, description="GPU thermal design power in watts (spec C.4)")
    compute_capability: Optional[str] = Field(
        default=None, max_length=32, description="CUDA compute capability string"
    )


class GpuNodeUpdate(BaseModel):
    """Schema for updating a GPU node."""

    gpu_model: Optional[str] = Field(default=None, max_length=255)
    total_vram_mb: Optional[int] = Field(default=None, ge=0)
    power_tdp_w: Optional[int] = Field(default=None, ge=0, description="GPU thermal design power in watts (spec C.4)")
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
    # WP-60 Task 2(b). Reservation accounting, not a device reading. Kept under
    # its wire name; `reserved_vram_mb` is the same number correctly named and
    # is what a surface must label.
    used_vram_mb: int = 0
    reserved_vram_mb: int = 0
    available_vram_mb: int = 0
    # WP-60 Task 2(a). THESE THREE DEFAULTED TO 0.0 AND WERE NEVER SET.
    #
    # `scheduler_fleet.to_node_view` populates none of temperature or power, so
    # the pydantic defaults supplied them, and the GPU Fleet card printed
    # "0 C" and "0 W" for every node in the fleet -- the exact shape WP-24
    # removed from `/api/v1/nodes` (see that module's docstring) reappearing on
    # the route beside it. `gpu_utilization_pct` came through as
    # `float(... or 0.0)`, which turns an absent reading into a measured idle.
    #
    # None now means "not measured". The frontend renders that in words.
    gpu_utilization_pct: Optional[float] = None
    temperature_c: Optional[float] = None
    power_draw_w: Optional[float] = None
    power_tdp_w: Optional[int] = None  # Spec C.4; added per Spec v1.1 amendment 4
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
    reserved_vram_mb: int = 0
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


# ----------------------------------------------------------------------------
# History endpoint schemas - added per GPU Fleet Monitoring Spec v1.1
# ----------------------------------------------------------------------------


class GpuUtilizationPoint(BaseModel):
    """Single time-series GPU utilization measurement per spec 4.2 Table 19.

    Mirrors gpu_metrics_history storage layer field naming. Additionally
    carries node_hostname (JOINed from gpu_nodes) so chart consumers can
    correlate history points to display names without a second round-trip.

    Field naming mirrors gpu_metrics_history rather than GpuNodeResponse
    (the snapshot endpoint), per GPU Fleet Monitoring Spec v1.1 sec 3.4.
    """

    gpu_node_id: UUID
    node_hostname: str
    recorded_at: datetime
    gpu_util_pct: Optional[float] = None
    mem_util_pct: Optional[float] = None
    temperature_c: Optional[float] = None
    power_draw_w: Optional[float] = None
    active_job_count: Optional[int] = None
    queue_depth: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class GpuUtilizationHistoryResponse(BaseModel):
    """Response envelope for GET /api/v1/gpu/utilization/history.

    Returns time-series points within the requested range, ordered by
    (gpu_node_id, recorded_at). Empty when no nodes are registered or
    no workers have written heartbeat metrics in the requested window.

    Hard-capped at 5000 points per Spec v1.1 sec 3.3. Over-cap responses
    return HTTP 413 rather than truncating silently.
    """

    history: List[GpuUtilizationPoint] = Field(default_factory=list)
    range: str
    point_count: int = 0

    model_config = ConfigDict(from_attributes=True)
