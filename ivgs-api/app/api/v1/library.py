"""
Production content library endpoints — AD-09.4 (assets, actors) and AD-09.5
(presets).

    GET    /api/v1/library/assets                  — browse
    POST   /api/v1/library/assets                  — upload
    GET    /api/v1/library/assets/{id}             — one
    PATCH  /api/v1/library/assets/{id}             — metadata only
    GET    /api/v1/library/assets/{id}/download    — proxy from SeaweedFS
    POST   /api/v1/library/assets/{id}/supersede   — retire in favour of another
    POST   /api/v1/library/assets/{id}/promote     — user -> global (admin)

    GET    /api/v1/actors                          — browse
    POST   /api/v1/actors                          — create
    GET    /api/v1/actors/{id}                     — one
    PATCH  /api/v1/actors/{id}                     — edit / retire

    GET    /api/v1/presets                         — browse (active by default)
    POST   /api/v1/presets                         — create v1
    GET    /api/v1/presets/{id}                    — one
    GET    /api/v1/presets/by-name/{name}/versions — provenance view
    POST   /api/v1/presets/{name}/revise           — create v(n+1)

    POST   /api/v1/projects/{id}/library-reference — reference-don't-copy
    POST   /api/v1/projects/{id}/apply-preset      — apply a preset

AD-09.15 CRITERION 7 — ALL OPERATIONS AVAILABLE IN THE GUI, NO CLI STEP. Every
route here has a frontend surface. There is deliberately no seeding script and
no management command: the operator has zero tolerance for CLI-only admin
functionality, and a route that only a script calls becomes one within a week.

NO PIPELINE CODE PATH READS ANY OF THIS. That is WP-56's boundary condition
against the Temporal cutover, and it is checkable: none of these routes is
reachable from `ivgs-workers`, and `library_assets`, `actors` and `presets`
appear nowhere in that tree.
"""
import json
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.rbac import require_admin, require_operator_or_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.asset import AssetResponse
from app.schemas.library import (
    ActorCreate,
    ActorResponse,
    ActorUpdate,
    LibraryAssetReferenceRequest,
    LibraryAssetResponse,
    LibraryAssetUpdate,
    LibraryAssetUploadResponse,
    PresetApplyRequest,
    PresetApplyResult,
    PresetCreate,
    PresetResponse,
    PresetRevise,
)
from app.services.library_service import ActorService, LibraryError, LibraryService
from app.services.preset_service import PresetService
from shared.database import get_session
from shared.seaweedfs_client import seaweedfs_client

logger = logging.getLogger(__name__)

library_router = APIRouter(prefix="/library/assets", tags=["Library"])
actors_router = APIRouter(prefix="/actors", tags=["Actors"])
presets_router = APIRouter(prefix="/presets", tags=["Presets"])
project_library_router = APIRouter(prefix="/projects/{project_id}", tags=["Library"])


def _bad_request(e: LibraryError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
    )


def _not_found(what: str, ident) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "NOT_FOUND", "message": f"{what} {ident} not found"}},
    )


def _paginate(rows, total, page, per_page, model):
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=[model.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


# ---------------------------------------------------------------------------
# Library assets
# ---------------------------------------------------------------------------

@library_router.get(
    "", response_model=PaginatedResponse[LibraryAssetResponse],
    summary="Browse the asset library",
)
async def list_library_assets(
    kind: Optional[str] = Query(default=None),
    owner_scope: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    include_superseded: bool = Query(
        default=False,
        description="Superseded assets are retired branding. Off by default so "
                    "the picker never offers one as a live choice.",
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    rows, total = await LibraryService(db).list_assets(
        kind=kind, owner_scope=owner_scope, search=search,
        include_superseded=include_superseded, page=page, per_page=per_page,
    )
    return _paginate(rows, total, page, per_page, LibraryAssetResponse)


@library_router.post(
    "", response_model=LibraryAssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an asset into the library",
)
async def upload_library_asset(
    file: UploadFile = File(...),
    kind: str = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(
        default=None, description="JSON array of free-form retrieval tags",
    ),
    owner_scope: str = Form(
        default="user",
        description="`global` requires admin and is rejected here for anyone else",
    ),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    parsed_tags: Optional[List[str]] = None
    if tags:
        try:
            parsed_tags = json.loads(tags)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "VALIDATION_ERROR",
                                  "message": f"tags is not valid JSON: {e}"}},
            )
        if not isinstance(parsed_tags, list) or any(
            not isinstance(t, str) for t in parsed_tags
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "VALIDATION_ERROR",
                                  "message": "tags must be a JSON array of strings"}},
            )

    # `global` is admin-mutable only (AD-09.4.2). Checked here rather than by a
    # route-level dependency because the SAME route serves both scopes and an
    # operator uploading to their own scope must not need admin.
    if owner_scope == "global" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "PERMISSION_DENIED",
                              "message": "Only an admin may write to the global library. "
                                         "Upload to your own scope and ask an admin to promote it."}},
        )

    content = await file.read()
    try:
        asset, was_deduplicated = await LibraryService(db).upload_asset(
            kind=kind,
            name=name,
            file_content=content,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            description=description,
            tags=parsed_tags,
            owner_scope=owner_scope,
            created_by=current_user.id,
        )
    except LibraryError as e:
        raise _bad_request(e)
    response = LibraryAssetUploadResponse.model_validate(asset)
    response.was_deduplicated = was_deduplicated
    return response


@library_router.get(
    "/{asset_id}", response_model=LibraryAssetResponse, summary="Get a library asset",
)
async def get_library_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    asset = await LibraryService(db).get_asset(asset_id)
    if asset is None:
        raise _not_found("Library asset", asset_id)
    return LibraryAssetResponse.model_validate(asset)


@library_router.patch(
    "/{asset_id}", response_model=LibraryAssetResponse,
    summary="Edit library asset metadata",
)
async def update_library_asset(
    asset_id: UUID,
    body: LibraryAssetUpdate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Metadata only. The bytes are immutable — replacing a file is a supersede."""
    asset = await LibraryService(db).update_metadata(
        asset_id, name=body.name, description=body.description, tags=body.tags,
    )
    if asset is None:
        raise _not_found("Library asset", asset_id)
    return LibraryAssetResponse.model_validate(asset)


@library_router.get("/{asset_id}/download", summary="Download a library asset")
async def download_library_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    asset = await LibraryService(db).get_asset(asset_id)
    if asset is None:
        raise _not_found("Library asset", asset_id)
    if not asset.seaweedfs_fid:
        raise _not_found("Library asset content for", asset_id)
    content = await seaweedfs_client.download_file(asset.seaweedfs_fid)
    if content is None:
        raise _not_found("Library asset content for", asset_id)
    return Response(
        content=content,
        media_type=asset.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{asset.name}"'},
    )


@library_router.post(
    "/{asset_id}/supersede", response_model=LibraryAssetResponse,
    summary="Retire a library asset in favour of another",
)
async def supersede_library_asset(
    asset_id: UUID,
    replacement_id: UUID = Query(...),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """The only retirement path. There is NO delete route, deliberately:
    AD-09.4.2 rules library assets are never hard-deleted while referenced, and
    every project ever built from one references it."""
    try:
        asset = await LibraryService(db).supersede(asset_id, replacement_id)
    except LibraryError as e:
        raise _bad_request(e)
    if asset is None:
        raise _not_found("Library asset", asset_id)
    return LibraryAssetResponse.model_validate(asset)


@library_router.post(
    "/{asset_id}/promote", response_model=LibraryAssetResponse,
    summary="Promote a user asset to the global library (admin)",
    dependencies=[Depends(require_admin)],
)
async def promote_library_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_session),
):
    try:
        asset = await LibraryService(db).promote_to_global(asset_id)
    except LibraryError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONFLICT", "message": str(e)}},
        )
    if asset is None:
        raise _not_found("Library asset", asset_id)
    return LibraryAssetResponse.model_validate(asset)


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------

@actors_router.get(
    "", response_model=PaginatedResponse[ActorResponse], summary="Browse actors",
)
async def list_actors(
    owner_scope: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    rows, total = await ActorService(db).list_actors(
        owner_scope=owner_scope, include_inactive=include_inactive,
        page=page, per_page=per_page,
    )
    return _paginate(rows, total, page, per_page, ActorResponse)


@actors_router.post(
    "", response_model=ActorResponse, status_code=status.HTTP_201_CREATED,
    summary="Create an actor",
)
async def create_actor(
    body: ActorCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create a presenter identity.

    ``engine_bindings`` is stored VERBATIM and is not validated: AD-09.14 open
    question 1 (the MagiHuman parameter set) is unanswered, and a validator
    written against a guess would reject the operator's real values the day
    they are recorded.
    """
    try:
        actor = await ActorService(db).create_actor(
            body.model_dump(), created_by=current_user.id,
        )
    except LibraryError as e:
        raise _bad_request(e)
    return ActorResponse.model_validate(actor)


@actors_router.get("/{actor_id}", response_model=ActorResponse, summary="Get an actor")
async def get_actor(
    actor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    actor = await ActorService(db).get_actor(actor_id)
    if actor is None:
        raise _not_found("Actor", actor_id)
    return ActorResponse.model_validate(actor)


@actors_router.patch(
    "/{actor_id}", response_model=ActorResponse, summary="Edit or retire an actor",
)
async def update_actor(
    actor_id: UUID,
    body: ActorUpdate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Editing ``certified_model_id`` is an IDENTITY CHANGE (AD-09.4.3): an
    actor is only reproducible on the engine it was established against. The
    API records it; the GUI warns before sending it."""
    try:
        actor = await ActorService(db).update_actor(
            actor_id, body.model_dump(exclude_unset=True),
        )
    except LibraryError as e:
        raise _bad_request(e)
    if actor is None:
        raise _not_found("Actor", actor_id)
    return ActorResponse.model_validate(actor)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@presets_router.get(
    "", response_model=PaginatedResponse[PresetResponse], summary="Browse presets",
)
async def list_presets(
    owner_scope: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    rows, total = await PresetService(db).list_presets(
        owner_scope=owner_scope, active_only=active_only,
        page=page, per_page=per_page,
    )
    return _paginate(rows, total, page, per_page, PresetResponse)


@presets_router.post(
    "", response_model=PresetResponse, status_code=status.HTTP_201_CREATED,
    summary="Create a preset (version 1)",
)
async def create_preset(
    body: PresetCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    try:
        preset = await PresetService(db).create_preset(
            name=body.name,
            description=body.description,
            payload=body.payload.model_dump(mode="json", exclude_none=True),
            owner_scope=body.owner_scope,
            created_by=current_user.id,
        )
    except LibraryError as e:
        raise _bad_request(e)
    return PresetResponse.model_validate(preset)


@presets_router.get(
    "/by-name/{name}/versions", response_model=List[PresetResponse],
    summary="Every version of one preset",
)
async def list_preset_versions(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """The provenance view. A project pinned to version 2 must stay inspectable
    after version 5 becomes the active one."""
    rows = await PresetService(db).list_versions(name)
    if not rows:
        raise _not_found("Preset", name)
    return [PresetResponse.model_validate(r) for r in rows]


@presets_router.get("/{preset_id}", response_model=PresetResponse, summary="Get a preset")
async def get_preset(
    preset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    preset = await PresetService(db).get_preset(preset_id)
    if preset is None:
        raise _not_found("Preset", preset_id)
    return PresetResponse.model_validate(preset)


@presets_router.post(
    "/by-name/{name}/revise", response_model=PresetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the next version of a preset",
)
async def revise_preset(
    name: str,
    body: PresetRevise,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """There is no PATCH on a preset and there will not be one. Presets are
    versioned rather than mutated (AD-09.5); an in-place edit would rewrite the
    provenance of every project already created from it."""
    try:
        preset = await PresetService(db).revise(
            name=name,
            description=body.description,
            payload=body.payload.model_dump(mode="json", exclude_none=True),
            created_by=current_user.id,
        )
    except LibraryError as e:
        raise _bad_request(e)
    return PresetResponse.model_validate(preset)


# ---------------------------------------------------------------------------
# Project seam
# ---------------------------------------------------------------------------

@project_library_router.post(
    "/library-reference", response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reference a library asset into a project (no copy)",
)
async def reference_library_asset(
    project_id: UUID,
    body: LibraryAssetReferenceRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """AD-09.4.2 reference-don't-copy. Creates an ``assets`` row pointing at the
    SAME SeaweedFS object; no bytes move, so this is O(1) in file size."""
    try:
        asset = await LibraryService(db).reference_into_project(
            library_asset_id=body.library_asset_id,
            project_id=project_id,
            asset_type=body.asset_type,
            scene_id=body.scene_id,
            language_code=body.language_code,
        )
    except LibraryError as e:
        raise _bad_request(e)
    return AssetResponse.model_validate(asset)


@project_library_router.post(
    "/apply-preset", response_model=PresetApplyResult,
    summary="Apply a preset to a project",
)
async def apply_preset(
    project_id: UUID,
    body: PresetApplyRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Writes the preset's concrete values into the project and records
    ``preset_id`` + ``preset_version`` for provenance.

    The result is ITEMISED. ``recorded_not_applied`` names every bundle entry
    that was stored but has no consuming code path — branding, chiefly, because
    WP-56 Task 3 stopped on the presenter/logo render chain. Reporting a plain
    success while silently skipping half the bundle is the AD-09.3 stub family,
    and this package does not add to it.
    """
    try:
        result = await PresetService(db).apply_to_project(
            preset_id=body.preset_id, project_id=project_id,
        )
    except LibraryError as e:
        raise _bad_request(e)
    except ValueError as e:
        # model_selection.manual_override raises plain ValueError for a model
        # that is retired, missing, or serves a different stage. Those are all
        # operator-actionable and must not surface as a 500.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    return PresetApplyResult(**result)
