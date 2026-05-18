"""REST endpoints for GPU node management."""
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.gpu import GpuNode, GpuReservation
from app.schemas.gpu import (
    DrainRequest,
    GpuNodeResponse,
    GpuReservationResponse,
    GpuUtilizationSummary,
)

router = APIRouter(prefix="/gpu", tags=["gpu"])


@router.get("/nodes", response_model=List[GpuNodeResponse])
def list_gpu_nodes(db: Session = Depends(get_db)) -> List[GpuNodeResponse]:
    """List all registered GPU nodes with current status."""
    nodes = db.query(GpuNode).order_by(
        GpuNode.node_hostname, GpuNode.gpu_index
    ).all()
    return [GpuNodeResponse.from_orm(n) for n in nodes]


@router.get("/nodes/{node_id}/reservations",
            response_model=List[GpuReservationResponse])
def list_node_reservations(
    node_id: int,
    db: Session = Depends(get_db),
) -> List[GpuReservationResponse]:
    """List active (reserved/active) reservations on a GPU node."""
    node = db.query(GpuNode).filter_by(id=node_id).first()
    if node is None:
        raise HTTPException(status_code=404, detail="GPU node not found")

    reservations = (
        db.query(GpuReservation)
        .filter(
            GpuReservation.gpu_node_id == node_id,
            GpuReservation.status.in_(["reserved", "active"]),
        )
        .all()
    )
    return [GpuReservationResponse.from_orm(r) for r in reservations]


@router.post("/nodes/{node_id}/drain", response_model=GpuNodeResponse)
def drain_node(
    node_id: int,
    req: DrainRequest,
    db: Session = Depends(get_db),
) -> GpuNodeResponse:
    """Mark a GPU node as draining — no new tasks will be scheduled to it."""
    node = db.query(GpuNode).filter_by(id=node_id).first()
    if node is None:
        raise HTTPException(status_code=404, detail="GPU node not found")

    node.status = "draining" if req.drain else "online"
    db.commit()
    db.refresh(node)
    return GpuNodeResponse.from_orm(node)


@router.get("/utilization", response_model=GpuUtilizationSummary)
def get_fleet_utilization(db: Session = Depends(get_db)) -> GpuUtilizationSummary:
    """Get a fleet-wide GPU utilization summary."""
    nodes = db.query(GpuNode).all()
    total_vram = sum(n.total_vram_mb for n in nodes)
    used_vram = sum(n.total_vram_mb - n.available_vram_mb for n in nodes)

    return GpuUtilizationSummary(
        total_nodes=len(nodes),
        online_nodes=sum(1 for n in nodes if n.status == "online"),
        draining_nodes=sum(1 for n in nodes if n.status == "draining"),
        offline_nodes=sum(1 for n in nodes if n.status == "offline"),
        total_vram_mb=total_vram,
        used_vram_mb=used_vram,
        utilization_pct=round(used_vram / total_vram * 100, 1) if total_vram else 0.0,
    )
