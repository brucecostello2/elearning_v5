"""API routes for the GPU Scheduler microservice."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AdmissionResult,
    FleetStatus,
    HeartbeatUpdate,
    NodeRegistration,
    ScheduleRequest,
    ScheduleResponse,
)
from app.registry import GpuRegistry
from app.scheduler import GpuScheduler, NoCapacityError
from app.admission import AdmissionController

router = APIRouter()


def _scheduler(db: Session = Depends(get_db)) -> GpuScheduler:
    return GpuScheduler(db)


def _registry(db: Session = Depends(get_db)) -> GpuRegistry:
    return GpuRegistry(db)


def _admission(db: Session = Depends(get_db)) -> AdmissionController:
    return AdmissionController(db)


@router.post("/schedule", response_model=ScheduleResponse)
def schedule_job(
    req: ScheduleRequest,
    sched: GpuScheduler = Depends(_scheduler),
    adm: AdmissionController = Depends(_admission),
) -> ScheduleResponse:
    """Find an available GPU for the requested job and reserve it.

    Returns the assigned node_id and gpu_index, or raises 503 if no
    GPU with sufficient VRAM is available.
    """
    # Admission control first
    admission = adm.check_admission(req.task_type, req.vram_requirement_mb)
    if not admission.admitted:
        raise HTTPException(
            status_code=503,
            detail=f"Admission rejected: {admission.reason}",
        )

    try:
        node_id, gpu_index, reservation_id = sched.schedule_job(
            job_id=req.job_id,
            model_name=req.model_name,
            vram_requirement_mb=req.vram_requirement_mb,
            estimated_duration_seconds=req.estimated_duration_seconds,
        )
    except NoCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return ScheduleResponse(
        node_id=node_id,
        gpu_index=gpu_index,
        reservation_id=reservation_id,
        message="GPU reserved successfully",
    )


@router.delete("/reservations/{reservation_id}", status_code=204)
def release_reservation(
    reservation_id: int,
    sched: GpuScheduler = Depends(_scheduler),
) -> None:
    """Release a GPU reservation after task completion or failure."""
    sched.release_reservation(reservation_id)


@router.post("/register")
def register_node(
    reg: NodeRegistration,
    reg_svc: GpuRegistry = Depends(_registry),
) -> dict:
    """Register a GPU node with the scheduler on worker startup."""
    node_id = reg_svc.register_node(
        hostname=reg.hostname,
        gpu_index=reg.gpu_index,
        gpu_model=reg.gpu_model,
        total_vram_mb=reg.total_vram_mb,
        compute_capability=reg.compute_capability,
    )
    return {"node_id": node_id, "status": "registered"}


@router.put("/heartbeat")
def update_heartbeat(
    hb: HeartbeatUpdate,
    reg_svc: GpuRegistry = Depends(_registry),
) -> dict:
    """Update GPU node heartbeat metrics (called every 10s by workers)."""
    reg_svc.update_heartbeat(
        hostname=hb.hostname,
        gpu_index=hb.gpu_index,
        metrics=hb.metrics,
    )
    return {"status": "ok"}


@router.post("/drain/{node_id}")
def drain_node(
    node_id: int,
    reg_svc: GpuRegistry = Depends(_registry),
) -> dict:
    """Mark a GPU node as draining — no new tasks scheduled to it."""
    reg_svc.drain_node(node_id)
    return {"node_id": node_id, "status": "draining"}


@router.get("/fleet", response_model=FleetStatus)
def get_fleet_status(
    sched: GpuScheduler = Depends(_scheduler),
) -> FleetStatus:
    """Get fleet-wide GPU availability and utilization summary."""
    return sched.get_fleet_status()
