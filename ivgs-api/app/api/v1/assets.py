"""
Asset API endpoints per §5.1.5.

Endpoints:
- GET    /api/v1/projects/{id}/assets            — List assets (filterable)
- POST   /api/v1/projects/{id}/assets/upload     — Upload asset to SeaweedFS
- GET    /api/v1/assets                          — Find assets by hash (dedup probe)
- GET    /api/v1/assets/{id}                     — Get asset metadata
- GET    /api/v1/assets/{id}/download            — Proxy download from SeaweedFS
- GET    /api/v1/assets/{id}/thumbnail           — Downscaled image preview
- POST   /api/v1/assets/{id}/regenerate          — Queue asset regeneration
- DELETE /api/v1/assets/{id}                     — Delete asset
"""
import json
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user, get_service_or_user
from app.core.rbac import require_operator_or_admin, require_service_or_privileged_user
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.asset import AssetUploadResponse, AssetResponse
from app.schemas.render_job import JobResponse
from app.services.asset_service import AssetService
from app.services.regeneration import (
    RegenerationError,
    dispatch_scene_media_regeneration,
    scene_for_asset,
)

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
    current_user: User = Depends(get_service_or_user),
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
    content_hash: Optional[str] = Form(
        default=None,
        description=(
            "SHA-256 of the uploaded bytes, as computed by the caller. Verified "
            "against the bytes that arrive; a mismatch is a 400."
        ),
    ),
    generation_params_hash: Optional[str] = Form(
        default=None,
        description=(
            "Caller-owned idempotency key over the generation request "
            "(prompt, parameters, input asset digests). Stored as given."
        ),
    ),
    metadata: Optional[str] = Form(
        default=None,
        description="JSON object of per-asset generation provenance.",
    ),
    library_kind: Optional[str] = Form(
        default=None,
        description=(
            "AD-09.4.2 upload-on-use. When set, the media is ALSO written to the "
            "asset library (owner_scope=user) and this asset records its "
            "library origin. OPT-IN: the GUI sends it, workers do not, and "
            "defaulting it on would pour every generated frame into the library."
        ),
    ),
    library_name: Optional[str] = Form(
        default=None,
        description="Operator-facing name for the library entry; defaults to the filename.",
    ),
    current_user: User = Depends(require_service_or_privileged_user),
    db: AsyncSession = Depends(get_session),
):
    """Upload asset file to SeaweedFS. Returns {id, seaweedfs_fid, seaweedfs_path}.

    WP-45 Task 1. ``content_hash``, ``generation_params_hash`` and ``metadata``
    are declared here for the first time. Every media task in the fleet has been
    sending two of them since it was written; FastAPI discards form fields a
    signature does not declare, without an error on either side, so the dedup key
    and the whole provenance record went nowhere and the caller could not tell
    (WP-46 addendum A5.2, ledger L-7). The response now also says whether the
    bytes were stored or an existing row was re-referenced.
    """
    content = await file.read()

    try:
        scene_uuid = UUID(scene_id) if scene_id else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"scene_id is not a UUID: {scene_id!r}",
                }
            },
        )

    generation_metadata = None
    if metadata:
        try:
            generation_metadata = json.loads(metadata)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"metadata is not valid JSON: {e}",
                    }
                },
            )
        if not isinstance(generation_metadata, dict):
            # A list or a bare string would store, and then no reader could ask
            # it "which engine made this?". Refuse rather than accept a shape
            # that silently answers nothing.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": (
                            "metadata must be a JSON object; got "
                            f"{type(generation_metadata).__name__}"
                        ),
                    }
                },
            )

    service = AssetService(db)
    try:
        asset, was_deduplicated = await service.upload_asset(
            project_id=project_id,
            file_content=content,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            asset_type=asset_type,
            scene_id=scene_uuid,
            language_code=language_code,
            claimed_content_hash=content_hash,
            generation_params_hash=generation_params_hash,
            generation_metadata=generation_metadata,
            library_kind=library_kind,
            library_name=library_name,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    response = AssetUploadResponse.model_validate(asset)
    response.was_deduplicated = was_deduplicated
    return response


@asset_router.get(
    "",
    response_model=List[AssetResponse],
    summary="Find assets by hash (deduplication probe)",
)
async def find_assets_by_hash(
    sha256: Optional[str] = Query(
        default=None,
        description=(
            "Match either content_hash or generation_params_hash. This is the "
            "shape the worker fleet's check_duplicate_asset has always called."
        ),
    ),
    content_hash: Optional[str] = Query(
        default=None, description="Match assets.content_hash exactly."
    ),
    generation_params_hash: Optional[str] = Query(
        default=None, description="Match assets.generation_params_hash exactly."
    ),
    project_id: Optional[UUID] = Query(
        default=None, description="Restrict the search to one project."
    ),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """Find live assets by content hash or generation-parameters hash.

    **This route did not exist.** ``check_duplicate_asset``
    (``ivgs-workers/utils/media_converter.py``) has called ``GET /api/v1/assets
    ?sha256=`` from every media branch since it was written; ``asset_router``
    carried only ``/{asset_id}`` and its children, so FastAPI matched the bare
    path to nothing and answered 404. The helper caught the failure and returned
    ``None``, which is indistinguishable from "no duplicate" — so dedup was dead
    fleet-wide and reported itself as working (WP-46 addendum A5.2 / ledger L-8;
    WP-00 swallowed-failures register).

    Returns a bare list, oldest first. An empty list means no duplicate; it does
    not mean the check failed, because a failed check is now a non-200.
    """
    if not (sha256 or content_hash or generation_params_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": (
                        "One of sha256, content_hash or generation_params_hash "
                        "is required. An unfiltered asset list is served by "
                        "GET /api/v1/projects/{id}/assets."
                    ),
                }
            },
        )
    service = AssetService(db)
    assets = await service.find_by_hash(
        content_hash=content_hash,
        generation_params_hash=generation_params_hash,
        any_hash=sha256,
        project_id=project_id,
        limit=limit,
    )
    return [AssetResponse.model_validate(a) for a in assets]


@asset_router.get("/{asset_id}", response_model=AssetResponse, summary="Get asset metadata")
async def get_asset(
    asset_id: UUID,
    current_user: User = Depends(get_service_or_user),
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
    current_user: User = Depends(get_service_or_user),
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


@asset_router.get(
    "/{asset_id}/thumbnail",
    summary="Downscaled image preview",
)
async def asset_thumbnail(
    asset_id: UUID,
    w: int = Query(
        default=320,
        ge=16,
        le=1024,
        description="Target width in pixels. Height follows the aspect ratio.",
    ),
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """Return a width-limited preview of an image asset.

    WP-45 Task 6(b) / WP-40 §9.3. The Media Assets grid drew every card from
    ``/assets/{id}/download``, so a 40-card page pulled roughly 10 MB of
    full-size PNGs to render thumbnails a few hundred pixels wide. Acceptable on
    a LAN and indefensible anywhere else.

    Images only. There is no ffmpeg in the API image, so a video thumbnail would
    have to be faked or fetched from somewhere that does not exist; the route
    says 415 and names the reason instead of returning a placeholder that looks
    like a decoded frame.

    The response carries a strong ETag derived from the asset's content hash and
    the requested width, so a browser re-rendering the grid gets 304s rather than
    re-fetching. That, not the resize, is where most of the saving is.
    """
    service = AssetService(db)
    asset = await service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Asset {asset_id} not found"}},
        )
    if asset.asset_type != "image":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": {
                    "code": "THUMBNAIL_UNSUPPORTED",
                    "message": (
                        f"Asset {asset_id} is of type '{asset.asset_type}'. "
                        "Thumbnails are generated for image assets only; the API "
                        "image has no video decoder."
                    ),
                }
            },
        )

    try:
        thumbnail, mime_type = await service.build_thumbnail(asset, width=w)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Asset {asset_id} has no retrievable content",
                }
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "THUMBNAIL_FAILED", "message": str(e)}},
        )

    etag = f'"{(asset.content_hash or str(asset.id))[:32]}-w{w}"'
    return Response(
        content=thumbnail,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": etag,
            "Content-Length": str(len(thumbnail)),
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
    """Re-run the media generation for the scene this asset belongs to.

    WP-45 Task 3, site 2. This used to insert a ``render_jobs`` row, log
    "Asset regeneration queued", return 202 — and dispatch nothing. The row sat
    at ``pending`` forever and the operator had no way to tell that from a job
    that was genuinely waiting for a worker.

    Ruled semantics: an asset regenerate is a re-run of its scene's media
    generation, consuming the scene's **current** fields. Pressing Regen after
    editing a scene must produce the edited scene, not a replay of the arguments
    that produced the asset being replaced.
    """
    service = AssetService(db)
    asset = await service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Asset {asset_id} not found"}},
        )

    try:
        scene = await scene_for_asset(db, asset.scene_id, asset_id)
        job = await dispatch_scene_media_regeneration(
            db, scene, reason=f"asset_regenerate:{asset_id}",
        )
    except RegenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "REGENERATION_UNAVAILABLE", "message": str(e)}},
        )

    logger.info(
        "Asset regeneration dispatched: asset=%s scene=%s job=%s celery_task=%s",
        asset_id, scene.id, job.id, job.celery_task_id,
    )
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
