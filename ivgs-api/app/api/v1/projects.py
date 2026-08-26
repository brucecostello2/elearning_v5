"""
Project API endpoints per §5.1.2.

Endpoints:
- GET    /api/v1/projects                     — List projects (paginated, filterable)
- POST   /api/v1/projects                     — Create new project
- GET    /api/v1/projects/{id}                — Get project detail
- PATCH  /api/v1/projects/{id}                — Update project metadata
- DELETE /api/v1/projects/{id}?confirm_name=  — Delete project permanently (admin only)
- GET    /api/v1/projects/{id}/deletion-preview — What a deletion would destroy (admin)
- POST   /api/v1/projects/{id}/trigger        — Trigger pipeline execution
- PATCH  /api/v1/projects/{id}/state          — Advance lifecycle state (internal)
- POST   /api/v1/projects/{id}/upload-talking-head — Upload talking head clip
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import (
    require_admin,
    require_operator_or_admin,
    require_service_or_privileged_user,
)
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.project_service import (
    DEFAULT_RENDER_TIER,
    PipelineAlreadyRunningError,
    ProjectService,
)
from app.services.asset_service import AssetService
from app.services.project_deletion import (
    AlreadyDeletedError,
    ConfirmationMismatchError,
    NonTerminalJobsError,
    ProjectDeletionError,
    ProjectDeletionService,
)
from app.schemas.project_deletion import (
    DeletionCategory,
    DeletionPreviewResponse,
    DeletionResultResponse,
)
from shared.models.enums import ProjectState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Projects"])


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


@router.get(
    "/{project_id}/deletion-preview",
    response_model=DeletionPreviewResponse,
    summary="Enumerate everything a deletion of this project would destroy",
)
async def project_deletion_preview(
    project_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """WP-59 Task 1. The category list and the real count of each, for THIS project.

    This route exists so the dialog cannot invent its own list. The categories
    it returns ARE the categories the deletion destroys — both come from
    ``PROJECT_CATEGORIES``, which was built by reading the live foreign keys
    rather than the spec's table list. A category missing here is a category
    silently left behind, so there is exactly one place it can go missing.

    Admin-gated like the DELETE itself: this payload is a complete inventory of
    a project's contents and its blocking jobs, which is not viewer material.
    """
    service = ProjectDeletionService(db)
    try:
        preview = await service.preview(project_id)
    finally:
        await service.close()
    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )
    return DeletionPreviewResponse(
        project_id=preview.project_id,
        project_name=preview.project_name,
        project_state=preview.project_state,
        categories=[
            DeletionCategory(
                key=c.key,
                label=c.label,
                detail=c.detail,
                cascade=c.cascade,
                count=c.count,
                breakdown=c.breakdown,
            )
            for c in preview.categories
        ],
        blocking_jobs=preview.blocking_jobs,
        gpu_reservations_held=preview.gpu_reservations_held,
        total_rows=preview.total_rows,
        total_bytes=preview.total_bytes,
        deletable=preview.deletable,
        scheduler_registry_error=preview.scheduler_registry_error,
        redis_registry_error=preview.redis_registry_error,
    )


@router.delete(
    "/{project_id}",
    response_model=DeletionResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete project permanently (admin only)",
)
async def delete_project(
    project_id: UUID,
    request: Request,
    confirm_name: str = Query(
        ...,
        description=(
            "The project's EXACT name. Required, so an id alone cannot delete "
            "anything."
        ),
    ),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Permanently delete a project. WP-59 Tasks 2, 3, 4 and 6.

    THE API IS NOT A SECOND, WEAKER DOOR (Task 6). Everything the GUI enforces
    is enforced here, because the GUI is one caller of this route and not its
    gatekeeper:

    * ``require_admin`` — the same RBAC dependency the previous DELETE carried.
    * ``confirm_name`` is REQUIRED and must equal the project's name exactly.
      A bare ``curl -X DELETE .../projects/<uuid>`` gets a 422 for the missing
      parameter, and a wrong name gets a 409. Deleting by id alone is not
      reachable from any client.
    * Non-terminal jobs are a 409 listing them (Task 3), and a GPU reservation
      the SCHEDULER still holds is a 409 too — read from the scheduler's own
      registry, not inferred from the job row.
    * It is rate-limited in the ``job_trigger`` bucket alongside the pipeline
      triggers (``app/middleware/rate_limit.py``), not the 60/min content
      bucket.

    THE RESPONSE IS THE DESTRUCTION, NOT A STATUS CODE. WP-45 Task 3 found
    eight surfaces returning 202 while doing nothing, and its acceptance
    criterion was deliberately not "returns 202" for exactly that reason. This
    route runs the deletion synchronously and returns 200 with the per-table
    row counts actually removed, the number of stored objects deleted, the
    number PRESERVED and why. A 202 would assert only that the request was
    accepted, which is the claim that was worthless the last eight times.
    """
    service = ProjectDeletionService(db)
    try:
        result = await service.delete(
            project_id,
            confirmation_name=confirm_name,
            actor_id=current_user.id,
            actor_name=current_user.username,
            client_ip=request.client.host if request.client else None,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )
    except AlreadyDeletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ALREADY_DELETED",
                    "message": str(exc),
                    "audit_id": exc.audit_id,
                }
            },
        )
    except ConfirmationMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "CONFIRMATION_MISMATCH", "message": str(exc)}},
        )
    except NonTerminalJobsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JOBS_NOT_TERMINAL",
                    "message": str(exc),
                    "jobs": exc.jobs,
                }
            },
        )
    except ProjectDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DELETION_REFUSED", "message": str(exc)}},
        )
    finally:
        await service.close()

    return DeletionResultResponse(
        project_id=result.project_id,
        project_name=result.project_name,
        audit_id=result.audit_id,
        rows_deleted=result.rows_deleted,
        total_rows_deleted=sum(result.rows_deleted.values()),
        files_deleted=result.files_deleted,
        files_preserved=result.files_preserved,
        preserved_reasons=result.preserved_reasons,
        files_failed=result.files_failed,
        redis_keys_deleted=result.redis_keys_deleted,
        resumed=result.resumed,
    )


@router.post(
    "/{project_id}/trigger",
    response_model=ProjectResponse,
    summary="Trigger pipeline execution",
)
async def trigger_pipeline(
    project_id: UUID,
    tier: str = Query(
        default=DEFAULT_RENDER_TIER,
        description=(
            "AD-01 model-selection tier for this run: prototype or production. "
            "Defaults to prototype."
        ),
    ),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Trigger pipeline execution from current state."""
    service = ProjectService(db)
    try:
        result = await service.trigger_pipeline(project_id, current_user, tier=tier)
    except PipelineAlreadyRunningError as e:
        # WP-61 Task 5 (WP-60 D-3, RULED). 409, NAMING THE ACTIVE RUN.
        #
        # Caught before the generic ValueError branch below, and given its own
        # code, because "a run is already going" and "you cannot trigger from
        # this state" are different facts with different remedies. The active
        # job's id is in the payload so the GUI can link to it rather than
        # telling the operator to go and look.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "PIPELINE_ALREADY_RUNNING",
                    "message": str(e),
                    "active_job": {
                        "id": str(e.job_id),
                        "job_type": e.job_type,
                        "status": e.status,
                    },
                }
            },
        )
    except ValueError as e:
        # IVGS-0.3: an unknown tier is a bad request, not a state conflict.
        if "render tier" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
            )
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


class ProjectStateUpdate(BaseModel):
    """Body for PATCH /projects/{id}/state — the pipeline's own state callback."""

    state: str = Field(
        description="Target ProjectState, e.g. MANIFEST_GENERATION or USER_REVIEW."
    )
    reason: Optional[str] = Field(
        default=None,
        description="Free text recorded in the API log, e.g. the completed stage.",
    )


@router.patch(
    "/{project_id}/state",
    response_model=ProjectResponse,
    summary="Advance project lifecycle state (internal)",
)
async def transition_project_state(
    project_id: UUID,
    payload: ProjectStateUpdate,
    current_user: User = Depends(require_service_or_privileged_user),
    db: AsyncSession = Depends(get_session),
):
    """Advance a project through the §6.1 state machine.

    WP-45 Task 2(a) / ORCH-5, and WP-39 §4 Gap A. ``transition_state`` has been
    implemented and validated since Phase 3 and **had no route and no caller**.
    Only three writers ever touched ``projects.state``: ``trigger_pipeline``,
    ``approve_storyboard``, and WP-38's scene-write edge. Nothing advanced a
    project past MEDIA_GENERATION, so MANIFEST_GENERATION, AUDIO_GENERATION,
    TALKING_HEAD_RENDER, PROTOTYPE_DRAFT and USER_REVIEW were states the system
    declared and could never reach - and spec §6.1's "post-assembly: project
    state transitions to USER_REVIEW", which gate 2 depends on, never happened.
    ``stage7_prototype_draft.py``'s own docstring lists it as step 9; no code
    performed it.

    This is the caller. The orchestrator invokes it on each hop through the back
    half of the pipeline, which is the only place that knows a stage finished.

    Service-token authenticated like every other worker-to-API route, and
    operator/admin may call it too - an operator moving a stuck project through
    the machine by hand is doing what the state machine sanctions, which is
    strictly better than the UPDATE statement they use today.

    An illegal transition is a 409 with the legal set named. The validation lives
    in ProjectService.transition_state against PROJECT_STATE_TRANSITIONS; this
    route adds none of its own.
    """
    try:
        target = ProjectState(payload.state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": (
                        f"Unknown project state '{payload.state}'. Valid: "
                        f"{[s.value for s in ProjectState]}"
                    ),
                }
            },
        )

    service = ProjectService(db)

    # Idempotent by construction. This is a callback route and the worker fleet
    # retries it; asking for the state a project is already in is a no-op, not a
    # conflict. Doing it here rather than in transition_state keeps the state
    # machine's own validation exactly as strict as it was.
    existing = await service.get_project(project_id, current_user)
    if existing is not None and existing.state == target.value:
        logger.info(
            "Project state already %s: project=%s reason=%s (no-op)",
            target.value, project_id, payload.reason or "-",
        )
        return existing

    try:
        result = await service.transition_state(project_id, target, current_user)
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
    logger.info(
        "Project state advanced: project=%s -> %s reason=%s by=%s",
        project_id, target.value, payload.reason or "-", current_user.username,
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
    # WP-45: upload_asset returns (asset, was_deduplicated). Re-uploading the
    # same reference clip re-references the stored row instead of a second copy.
    asset, _deduplicated = await asset_service.upload_asset(
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
