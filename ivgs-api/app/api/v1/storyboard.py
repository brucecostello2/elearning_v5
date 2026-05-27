"""
Storyboard scene API endpoints per §5.1.4.

Endpoints:
- GET    /api/v1/projects/{id}/scenes               — List scenes
- PATCH  /api/v1/projects/{id}/scenes/{sid}          — Update scene
- POST   /api/v1/projects/{id}/scenes/reorder        — Bulk reorder
- POST   /api/v1/projects/{id}/scenes/{sid}/regenerate — Queue scene regeneration
"""
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.storyboard import SceneResponse, SceneUpdate, SceneReorderRequest
from app.schemas.render_job import JobResponse
from app.services.storyboard_service import StoryboardService
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["Storyboard"])


@router.get("", response_model=List[SceneResponse], summary="List all scenes")
async def list_scenes(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all scenes ordered by scene_index."""
    project_service = ProjectService(db)
    project = await project_service.get_project(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )

    service = StoryboardService(db)
    scenes = await service.list_scenes(project_id)
    return [SceneResponse.model_validate(s) for s in scenes]


@router.patch("/{scene_id}", response_model=SceneResponse, summary="Update scene")
async def update_scene(
    project_id: UUID,
    scene_id: UUID,
    data: SceneUpdate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update narration_text, visual_description, media_type, or duration_seconds."""
    service = StoryboardService(db)
    scene = await service.update_scene(
        project_id=project_id,
        scene_id=scene_id,
        narration_text=data.narration_text,
        visual_description=data.visual_description,
        media_type=data.media_type,
        duration_seconds=data.duration_seconds,
    )
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Scene {scene_id} not found"}},
        )
    return SceneResponse.model_validate(scene)


@router.post("/reorder", response_model=List[SceneResponse], summary="Bulk reorder scenes")
async def reorder_scenes(
    project_id: UUID,
    data: SceneReorderRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Bulk reorder. Body: [{id, scene_index}]."""
    service = StoryboardService(db)
    try:
        scenes = await service.reorder_scenes(project_id, data.items)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    return [SceneResponse.model_validate(s) for s in scenes]


@router.post(
    "/{scene_id}/regenerate",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue scene regeneration",
)
async def regenerate_scene(
    project_id: UUID,
    scene_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Queue LLM regeneration of a specific scene."""
    service = StoryboardService(db)
    job = await service.regenerate_scene(project_id, scene_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Scene {scene_id} not found"}},
        )
    return JobResponse.model_validate(job)
