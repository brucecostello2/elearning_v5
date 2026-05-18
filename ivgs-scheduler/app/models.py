"""Pydantic models for the GPU Scheduler microservice API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScheduleRequest(BaseModel):
    job_id: Optional[int] = None
    model_name: str
    task_type: str
    vram_requirement_mb: int = Field(gt=0)
    estimated_duration_seconds: int = Field(default=300, ge=1)


class ScheduleResponse(BaseModel):
    node_id: int
    gpu_index: int
    reservation_id: int
    message: str


class NodeRegistration(BaseModel):
    hostname: str
    gpu_index: int = 0
    gpu_model: str
    total_vram_mb: int = Field(gt=0)
    compute_capability: Optional[str] = None


class HeartbeatUpdate(BaseModel):
    hostname: str
    gpu_index: int = 0
    metrics: Dict[str, Any] = Field(default_factory=dict)


class AdmissionResult(BaseModel):
    admitted: bool
    reason: Optional[str] = None


class NodeStatus(BaseModel):
    node_id: int
    hostname: str
    gpu_index: int
    gpu_model: str
    total_vram_mb: int
    available_vram_mb: int
    status: str
    active_reservations: int
    is_alive: bool


class FleetStatus(BaseModel):
    nodes: List[NodeStatus]
    total_vram_mb: int
    used_vram_mb: int
    utilization_pct: float
