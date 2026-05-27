"""
Project API endpoints per §5.1.2.

Endpoints:
- GET    /api/v1/projects                     — List projects (paginated, filterable)
- POST   /api/v1/projects                     — Create new project
- GET    /api/v1/projects/{id}                — Get project detail
- PATCH  /api/v1/projects/{id}                — Update project metadata
- DELETE /api/v1/projects/{id}                — Delete project (admin only)
- POST   /api/v1/projects/{id}/trigger        — Trigger pipeline execution
- POST   /api/v1/projects/{id}/upload-talking-head — Upload talking head clip
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_admin, require_operator_or_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.project_service import ProjectService
from app.services.asset_service import AssetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "",
    response_model=PaginatedResponse[ProjectResponse],
    summary="List all projects",
)
async def list_projects(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    state: Optional[str] = Query(default=None, description="Filter by project state"),
    search: Optional[str] = Query(default=None, description="Search in name/description"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all projects with pagination. Supports ?state=DRAFT&search=text filters."""
    service = ProjectService(db)
    projects, total = await service.list_projects(
        current_user=current_user,
        page=page,
        per_page=per_page,
        state_filter=state,
        search=search,
    )
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=projects,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new project",
)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create new project. Body: {name, description, max_runtime_seconds, target_languages[]}."""
    service = ProjectService(db)
    return await service.create_project(data, current_user)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project detail",
)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get project detail including scene count, job status, asset counts."""
    service = ProjectService(db)
    project = await service.get_project(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )
    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project metadata",
)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update project metadata (name, description, max_runtime_seconds)."""
    service = ProjectService(db)
    project = await service.update_project(project_id, data, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project (admin only)",
)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Delete project and all associated assets (admin only). Queues asset cleanup."""
    service = ProjectService(db)
    deleted = await service.delete_project(project_id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )


@router.post(
    "/{project_id}/trigger",
    response_model=ProjectResponse,
    summary="Trigger pipeline execution",
)
async def trigger_pipeline(
    project_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Trigger pipeline execution from current state."""
    service = ProjectService(db)
    try:
        result = await service.trigger_pipeline(project_id, current_user)
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


@router.post(
    "/{project_id}/upload-talking-head",
    summary="Upload talking head presenter clip",
)
async def upload_talking_head(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """
    Upload talking head presenter clip (MP4/MOV, max 500MB).

    Returns asset_id. Stores in SeaweedFS at /ivgs/uploads/{project_id}/talking_head.*
    """
    # Validate content type
    allowed_types = {"video/mp4", "video/quicktime"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"Invalid file type '{file.content_type}'. Allowed: MP4, MOV",
                }
            },
        )

    content = await file.read()

    # Validate file size (500 MB max)
    max_size = 500 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"File too large: {len(content)} bytes. Maximum: {max_size} bytes (500MB)",
                }
            },
        )

    # Upload asset
    asset_service = AssetService(db)
    asset = await asset_service.upload_asset(
        project_id=project_id,
        file_content=content,
        filename=file.filename or "talking_head.mp4",
        content_type=file.content_type,
        asset_type="talking_head",
    )

    # Update project talking_head_asset_id
    project_service = ProjectService(db)
    project = await project_service.get_project_model(project_id, current_user)
    if project:
        project.talking_head_asset_id = asset.id
        await db.commit()

    return {
        "asset_id": str(asset.id),
        "seaweedfs_fid": asset.seaweedfs_fid,
        "seaweedfs_path": asset.seaweedfs_path,
        "file_size_bytes": asset.file_size_bytes,
    }
