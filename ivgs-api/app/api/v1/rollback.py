"""Rollback API endpoints for deploy-node.sh integration."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_db, require_admin
from app.services.rollback_service import RollbackService

router = APIRouter(prefix="/rollback", tags=["rollback"])
rollback_service = RollbackService()


class CreateRollbackRequest(BaseModel):
    version_tag: str


class RollbackToRequest(BaseModel):
    rollback_point_id: str


@router.post("/create")
async def create_rollback_point(
    request: CreateRollbackRequest,
    db=Depends(get_db),
):
    point = await rollback_service.create_rollback_point(request.version_tag, db)
    return {"id": point.id, "version_tag": point.version_tag, "created_at": point.created_at.isoformat()}


@router.post("/restore")
async def rollback_to(
    request: RollbackToRequest,
    db=Depends(get_db),
    _=Depends(require_admin),
):
    result = await rollback_service.rollback_to(request.rollback_point_id, db)
    return result


@router.get("/points")
async def list_rollback_points():
    return await rollback_service.list_rollback_points()
