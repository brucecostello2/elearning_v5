"""
Storyboard scene API endpoints per §5.1.4.

Endpoints:
- GET    /api/v1/projects/{id}/scenes               — List scenes
- PATCH  /api/v1/projects/{id}/scenes/{sid}          — Update scene
- POST   /api/v1/projects/{id}/scenes/reorder        — Bulk reorder
- POST   /api/v1/projects/{id}/scenes/{sid}/regenerate — Queue scene regeneration
"""
import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user, get_service_or_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.storyboard import SceneResponse, SceneUpdate, SceneReorderRequest, SceneCreate
from app.schemas.render_job import JobResponse
from app.services.storyboard_service import StoryboardService
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

from app.schemas.project import ProjectResponse

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["Storyboard"])


@router.get("", response_model=List[SceneResponse], summary="List all scenes")
async def list_scenes(
    project_id: UUID,
    current_user: User = Depends(get_service_or_user),
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


@router.post("", response_model=SceneResponse, status_code=status.HTTP_201_CREATED, summary="Create scene (internal: pipeline)")
async def create_scene(
    project_id: UUID,
    data: SceneCreate,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """Create a storyboard scene. Called by the worker fleet (service token) during Stage 2."""
    service = StoryboardService(db)
    scene = await service.create_scene(
        project_id=project_id,
        scene_index=data.scene_index,
        narration_text=data.narration_text,
        visual_description=data.visual_description,
        media_type=data.media_type,
        duration_seconds=data.duration_seconds,
    )
    # WP-38 / ORCH-5. Nothing advanced projects.state when a stage completed:
    # the only writers were trigger_pipeline (DRAFT -> TRANSCRIPT_REFINEMENT) and
    # approve_storyboard (-> MEDIA_GENERATION), and transition_state had no
    # callers at all. So after stages 1 and 2 both succeeded, project c12fa967
    # still read TRANSCRIPT_REFINEMENT - the review gate had no state to show.
    #
    # A persisted scene IS the storyboard existing, so this is the honest moment
    # to advance. Idempotent by construction: it only fires on the single
    # TRANSCRIPT_REFINEMENT -> STORYBOARD_GENERATION edge, so the other 17 scenes
    # of a run are no-ops, and a re-run from a later state is untouched.
    #
    # Deliberately narrow. It does not touch any other transition, and it is not
    # a general stage->state mechanism - that is ORCH-5's job and needs the
    # orchestrator, not this route.
    await _advance_to_storyboard_state(project_id, db)
    return SceneResponse.model_validate(scene)


async def _advance_to_storyboard_state(project_id: UUID, db: AsyncSession) -> None:
    """TRANSCRIPT_REFINEMENT -> STORYBOARD_GENERATION, once, when scenes land.

    Spec Table 4-3 sanctions STORYBOARD_GENERATION -> MEDIA_GENERATION, which is
    the edge `approve_storyboard` takes; this puts the project on the near side
    of it so the GUI can show the review gate and the continuation call is legal
    without hand-written SQL.

    Failure here must not fail the scene write: the scene is the durable fact and
    is already committed. A state that did not advance is recoverable; a scene
    that was rejected because a bookkeeping update failed is not.
    """
    from app.models.project import Project
    from shared.models.enums import ProjectState

    try:
        project = await db.scalar(select(Project).where(Project.id == project_id))
        if project is None:
            return
        if project.state != ProjectState.TRANSCRIPT_REFINEMENT.value:
            return
        project.state = ProjectState.STORYBOARD_GENERATION.value
        project.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "project_state_advanced project_id=%s %s -> %s reason=storyboard_scene_persisted",
            project_id,
            ProjectState.TRANSCRIPT_REFINEMENT.value,
            ProjectState.STORYBOARD_GENERATION.value,
        )
    except Exception as exc:
        logger.warning(
            "project_state_advance_failed project_id=%s error=%s", project_id, exc,
        )


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


@router.post(
    "/approve",
    response_model=ProjectResponse,
    summary="Approve storyboard -> start media generation (P1.5 item 2)",
)
async def approve_storyboard(
    project_id: UUID,
    tier: str = Query(
        default="prototype",
        description=(
            "AD-01 model-selection tier for the media-generation run: "
            "prototype or production. Defaults to prototype."
        ),
    ),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Approve the storyboard and resume the pipeline into media generation."""
    from app.services.project_service import ProjectService

    service = ProjectService(db)
    try:
        result = await service.approve_storyboard(
            project_id, current_user, tier=tier,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "INVALID_STATE_TRANSITION", "message": str(e)}},
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )
    return result
