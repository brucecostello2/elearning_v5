"""
Asset API endpoints per §5.1.5.

Endpoints:
- GET    /api/v1/projects/{id}/assets            — List assets (filterable)
- POST   /api/v1/projects/{id}/assets/upload     — Upload asset to SeaweedFS
- GET    /api/v1/assets/{id}                     — Get asset metadata
- GET    /api/v1/assets/{id}/download            — Proxy download from SeaweedFS
- POST   /api/v1/assets/{id}/regenerate          — Queue asset regeneration
- DELETE /api/v1/assets/{id}                     — Delete asset
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.asset import AssetUploadResponse, AssetResponse
from app.schemas.render_job import JobResponse
from app.services.asset_service import AssetService
from app.models.render_job import RenderJob

logger = logging.getLogger(__name__)

project_router = APIRouter(prefix="/projects/{project_id}/assets", tags=["Assets"])
asset_router = APIRouter(prefix="/assets", tags=["Assets"])


@project_router.get(
    "",
    response_model=PaginatedResponse[AssetResponse],
    summary="List project assets",
)
async def list_assets(
    project_id: UUID,
    scene_id: Optional[UUID] = Query(default=None),
    asset_type: Optional[str] = Query(default=None),
    language_code: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all assets. Supports ?scene_id=&asset_type=&language_code= filters."""
    service = AssetService(db)
    assets, total = await service.list_assets(
        project_id=project_id,
        scene_id=scene_id,
        asset_type=asset_type,
        language_code=language_code,
        page=page,
        per_page=per_page,
    )
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=[AssetResponse.model_validate(a) for a in assets],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@project_router.post(
    "/upload",
    response_model=AssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload asset to SeaweedFS",
)
async def upload_asset(
    project_id: UUID,
    file: UploadFile = File(...),
    asset_type: str = Form(...),
    scene_id: Optional[str] = Form(default=None),
    language_code: Optional[str] = Form(default=None),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Upload asset file to SeaweedFS. Returns {id, seaweedfs_fid, seaweedfs_path}."""
    content = await file.read()

    scene_uuid = UUID(scene_id) if scene_id else None

    service = AssetService(db)
    try:
        asset = await service.upload_asset(
            project_id=project_id,
            file_content=content,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            asset_type=asset_type,
            scene_id=scene_uuid,
            language_code=language_code,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    return AssetUploadResponse.model_validate(asset)


@asset_router.get("/{asset_id}", response_model=AssetResponse, summary="Get asset metadata")
async def get_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get asset metadata including quality scores."""
    service = AssetService(db)
    asset = await service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Asset {asset_id} not found"}},
        )
    return AssetResponse.model_validate(asset)


@asset_router.get("/{asset_id}/download", summary="Proxy download from SeaweedFS")
async def download_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Proxy download from SeaweedFS."""
    service = AssetService(db)
    result = await service.download_asset(asset_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Asset {asset_id} not found or unavailable"}},
        )

    content, mime_type, filename = result
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


@asset_router.post(
    "/{asset_id}/regenerate",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue asset regeneration",
)
async def regenerate_asset(
    asset_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Queue asset regeneration using stored generation_prompt_id."""
    service = AssetService(db)
    asset = await service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Asset {asset_id} not found"}},
        )

    # Determine job type from asset type
    type_to_job = {
        "image": "image_generation",
        "video": "video_generation",
        "audio": "tts_audio",
    }
    job_type = type_to_job.get(asset.asset_type, "image_generation")

    job = RenderJob(
        project_id=asset.project_id,
        job_type=job_type,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    logger.info(f"Asset regeneration queued: asset={asset_id} job={job.id}")
    return JobResponse.model_validate(job)


@asset_router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete asset",
)
async def delete_asset(
    asset_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Delete asset from SeaweedFS and database."""
    service = AssetService(db)
    deleted = await service.delete_asset(asset_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Asset {asset_id} not found"}},
        )
