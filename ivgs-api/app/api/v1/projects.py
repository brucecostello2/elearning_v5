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
from app.models.project_gate import (
    DECISION_REGENERATE,
    DECISIONS,
    GATE_DRAFT,
    GATE_STORYBOARD,
)
from app.services.regeneration import (
    RegenerationError,
    dispatch_gate_regeneration,
)
from app.api.v1._dispatch_guards import gate_blocked
from app.services.gate_service import GateBlocked, GateError, GateService
from app.services.storyboard_completeness import StoryboardIncomplete
from app.services.project_progress import ProjectProgressService
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


# NOTE ON ROUTE ORDER, and it is load-bearing rather than tidiness.
# FastAPI matches in REGISTRATION order, and this module registers
# `GET /{project_id}` below. A literal path that starts with a segment which
# could be a project id must therefore be declared BEFORE it, or
# `/projects/deletions/audit` is matched as `project_id="deletions"` and
# answers 422 on a UUID parse. Declared here, first.
@router.get(
    "/deletions/audit",
    summary="Every recorded project deletion, classified (admin only)",
)
async def deletion_audit(
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """WP-62 Task 5. THE READ PATH FOR THE DELETION LEDGER.

    The closure the ledger asked for already existed: `_record_completion`
    UPDATEs the ORIGINATING audit row, setting `after_payload.purge_state` and
    flipping `action_type` to PROJECT_DELETE_COMPLETED. Measured 2026-08-26,
    all fourteen recorded deletions are COMPLETED with purge_state 'complete'.

    What did not exist was a way to READ it. `before_payload.purge_state` says
    "pending" on every row forever -- it is deliberately a record of the moment
    before destruction and is never rewritten -- so an operator querying the
    obvious field got "pending" on fourteen finished deletions. This route
    classifies each row once: completed / completed_partial / died_mid_purge /
    in_flight, and says which are resumable.

    The ten 2026-08-26 deletions are historical test data and are NOT modified
    by this package. They appear here as `completed`, which is what they are.
    """
    service = ProjectDeletionService(db)
    try:
        return {"deletions": await service.deletion_audit_status(limit=limit)}
    finally:
        await service.close()


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
    except GateBlocked as e:
        # WP-62 Task 2(c). "Trigger pipeline" CANNOT BYPASS THE DRAFT GATE.
        # From USER_REVIEW this button IS the final render, and §6.1 puts a
        # blocking human gate in front of it. 409 with its own code, because
        # "the draft is not approved" is a different fact with a different
        # remedy from "you cannot trigger from this state".
        raise gate_blocked(e)
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


# ---------------------------------------------------------------------------
# The two human review gates (WP-62 Task 2)
# ---------------------------------------------------------------------------


class GateDecisionRequest(BaseModel):
    """Body for both gate endpoints. ONE contract, deliberately.

    Spec v5.1 §6.4 gives both gates the same three signals, so they get the
    same body and the same response. Two endpoints with two shapes would be two
    things to keep in step at M3.3 cutover, when each becomes a Temporal signal
    send against `gate_storyboard` / `gate_draft`.
    """

    decision: str = Field(
        description=(
            "approved, rejected or regenerate. §6.4: 'Gates additionally "
            "accept reject / regenerate signals.'"
        ),
    )
    note: Optional[str] = Field(
        default=None,
        max_length=4000,
        description=(
            "Free text recorded with the decision and in audit_log. A "
            "rejection without a reason is a decision nobody can act on."
        ),
    )


async def _gate_decision(
    project_id: UUID,
    gate: str,
    payload: GateDecisionRequest,
    request: Request,
    current_user: User,
    db: AsyncSession,
) -> dict:
    """Both gate endpoints, once.

    RBAC is `require_operator_or_admin`, matching every other pipeline-moving
    control. A viewer must not be offered a decision they would be refused.
    """
    if payload.decision not in DECISIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": (
                        f"Unknown decision '{payload.decision}'. The gate "
                        f"accepts {list(DECISIONS)}."
                    ),
                }
            },
        )

    project_service = ProjectService(db)
    if await project_service.get_project(project_id, current_user) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Project {project_id} not found",
                }
            },
        )

    service = GateService(db)
    try:
        row = await service.decide(
            project_id,
            gate,
            payload.decision,
            actor=current_user,
            note=payload.note,
            client_ip=request.client.host if request.client else None,
        )
    except GateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "GATE_ARTIFACT_ABSENT", "message": str(exc)}},
        )

    released: Optional[dict] = None
    if payload.decision == "approved" and gate == GATE_STORYBOARD:
        # Approval RELEASES the pipeline. This is the same dispatch the
        # existing "Approve storyboard" button has always made; what is new is
        # that the decision is recorded FIRST, so the dispatch happens because
        # of an approval that exists rather than beside one that does not.
        try:
            result = await project_service.approve_storyboard(
                project_id, current_user,
            )
            released = {
                "dispatched": result is not None,
                "state": result.state if result is not None else None,
            }
        except PipelineAlreadyRunningError as exc:
            # The decision STANDS - a human approved this storyboard and that
            # is recorded. Only the release is refused, and the operator is
            # told which run is holding it up. Rolling the approval back
            # because a dispatch could not happen would lose the human's
            # decision to a scheduling condition.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "PIPELINE_ALREADY_RUNNING",
                        "message": (
                            f"{exc} The approval WAS recorded "
                            f"(decision {row.id}); only the dispatch was "
                            "refused. Nothing needs re-approving."
                        ),
                        "active_job": {
                            "id": str(exc.job_id),
                            "job_type": exc.job_type,
                            "status": exc.status,
                        },
                    }
                },
            )
        except RegenerationError as exc:
            # ⛔ WP-IVGS-12i RC-R1. MEASURED 2026-08-30: THIS ANSWERED HTTP 500.
            #
            # `approve_storyboard` runs `_author_missing_motion_specs` before the
            # completeness check, and that helper RAISES `RegenerationError` for
            # a motion scene whose template cannot be authored from its own
            # narration — by design, since WP-IVGS-09f: "one scene that cannot be
            # drawn is a reason not to start". Nothing here caught it, so the
            # operator's press answered `INTERNAL_ERROR / An unexpected error
            # occurred` with a request id and nothing else, while the decision
            # row was already written and the log held a full traceback naming
            # the scene, the template and the contradiction.
            #
            # Measured on the 12i acceptance project, scene 7: *"the narration
            # announces 4 … but column_addition_carry{top:230,bottom:92} never
            # produces 4"*. That sentence is the whole answer and the surface
            # threw it away. A 500 also tells a reviewer the SYSTEM broke, when
            # what actually happened is that the system refused — the two are
            # opposite instructions about what to do next.
            #
            # The approval STANDS, on the same rule the two refusals beside this
            # one follow: a human approved this storyboard and that is recorded;
            # only the dispatch is refused.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "MOTION_AUTHORING_REFUSED",
                        "message": (
                            f"{exc}\n\nThe approval WAS recorded (decision "
                            f"{row.id}); only the dispatch was refused. Nothing "
                            f"was rendered and no job row was created."
                        ),
                    }
                },
            )
        except StoryboardIncomplete as exc:
            # WP-IVGS-10 Task 3. ITS OWN CODE, not INVALID_STATE_TRANSITION.
            # A reviewer told "invalid state transition" goes to look at the
            # project's state, and the project's state is fine: what is wrong is
            # named scenes in the storyboard on their screen, and the surface
            # branches on this code to say so beside them.
            #
            # The approval STANDS, on the same rule every other release refusal
            # here follows: a human approved this storyboard and that is
            # recorded. Only the dispatch is refused. Re-approving after fixing
            # the scenes is required anyway, because editing a scene moves the
            # artifact fingerprint and re-opens the gate on its own.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "STORYBOARD_INCOMPLETE",
                        # WP-IVGS-12i RC-R1. THE COUNT, AS A FIELD. The message
                        # has always carried it in prose; a surface that wants
                        # to say "N refusals block approval" beside a disabled
                        # button should not have to parse an English sentence to
                        # find N, and one that does will disagree with this one
                        # the first time the sentence is reworded.
                        "refusals": len(exc.assessments),
                        "message": (
                            f"{exc}\n\nThe approval WAS recorded (decision "
                            f"{row.id}); only the dispatch was refused. Fix the "
                            f"scenes named above -- each needs either a "
                            f"motion_graphics template or an explicit "
                            f"text_carried_by declaration -- and approve again."
                        ),
                        "scenes": [a.as_dict() for a in exc.assessments],
                    }
                },
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "INVALID_STATE_TRANSITION",
                        "message": (
                            f"{exc} The approval WAS recorded (decision "
                            f"{row.id}); only the dispatch was refused."
                        ),
                    }
                },
            )

    # WP-63 Task 8. THE `regenerate` DECISION NOW RELEASES SOMETHING.
    #
    # Measured before this change, project 14f71729 on 2026-08-26: two
    # `regenerate` decisions four seconds apart (15:17:25.362Z and
    # 15:17:29.616Z -- the operator pressed it again because nothing had
    # happened), two audit rows, and zero broker messages.
    #
    # The decision row it already wrote is now the audit OF this dispatch,
    # which is why the dispatch happens after `decide` rather than instead of
    # it. `dispatch_gate_regeneration` carries the ruled semantics and the
    # reason the trigger layer can serve them standalone.
    if payload.decision == DECISION_REGENERATE:
        try:
            job = await dispatch_gate_regeneration(
                db,
                project_id,
                gate,
                reason=f"gate_regenerate:{gate}:{row.id}",
            )
            released = {
                "dispatched": True,
                "job_id": str(job.id),
                "job_type": job.job_type,
                "stage": job.resume_from_stage,
            }
        except PipelineAlreadyRunningError as exc:
            # Same rule as an approval whose release is refused: THE DECISION
            # STANDS. A reviewer asked for a regeneration and that is recorded;
            # only the dispatch was refused, and the operator is told which run
            # is holding it up.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "PIPELINE_ALREADY_RUNNING",
                        "message": (
                            f"{exc} The regenerate decision WAS recorded "
                            f"(decision {row.id}); only the dispatch was "
                            "refused. Nothing needs re-deciding."
                        ),
                        "active_job": {
                            "id": str(exc.job_id),
                            "job_type": exc.job_type,
                            "status": exc.status,
                        },
                    }
                },
            )
        except RegenerationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "REGENERATION_UNAVAILABLE",
                        "message": (
                            f"{exc} The regenerate decision WAS recorded "
                            f"(decision {row.id})."
                        ),
                    }
                },
            )

    statuses = await service.all_statuses(project_id)
    return {
        "decision_id": str(row.id),
        "gate": gate,
        "decision": row.decision,
        "artifact_version": row.artifact_version,
        # The M3.3 signal this decision corresponds to, on the response, so a
        # caller written today against this API is already written against the
        # Temporal contract.
        "signal": {"name": f"gate_{gate}", "payload": row.signal_payload()},
        "released": released,
        "gates": {name: st.as_dict() for name, st in statuses.items()},
    }


@router.post(
    "/{project_id}/gates/storyboard",
    summary="Storyboard review gate: approve / reject / regenerate",
)
async def decide_storyboard_gate(
    project_id: UUID,
    payload: GateDecisionRequest,
    request: Request,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Record a decision at the storyboard gate, and release on approval.

    WP-62 Task 2(b). The API contract, stated once and shared with the draft
    gate below. `POST /projects/{id}/scenes/approve` remains and now runs
    through the same service, so the existing surface keeps working and the
    two cannot diverge.
    """
    return await _gate_decision(
        project_id, GATE_STORYBOARD, payload, request, current_user, db,
    )


@router.post(
    "/{project_id}/gates/draft",
    summary="Draft review gate: approve / reject / regenerate",
)
async def decide_draft_gate(
    project_id: UUID,
    payload: GateDecisionRequest,
    request: Request,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Record a decision at the draft gate.

    Approval does NOT dispatch. §6.1 puts the final render behind an explicit
    "Start final render" action after this gate, and collapsing the two would
    mean an approval silently consumed full-resolution GPU time. The render
    trigger refuses until this gate is approved (WP-62 Task 2(c)).
    """
    return await _gate_decision(
        project_id, GATE_DRAFT, payload, request, current_user, db,
    )


@router.get(
    "/{project_id}/gates",
    summary="State of both human review gates",
)
async def get_project_gates(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Both gates, recomputed against the artifacts as they stand now.

    Read by the stepper (stage 9 Review is the draft gate's home), by the
    Storyboard tab and by the Draft Preview tab. ONE computation; three
    surfaces cannot disagree about whether a gate is open.
    """
    service = GateService(db)
    if await ProjectService(db).get_project(project_id, current_user) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Project {project_id} not found",
                }
            },
        )
    statuses = await service.all_statuses(project_id)
    history = await service.history(project_id)
    return {
        "gates": {name: st.as_dict() for name, st in statuses.items()},
        "history": [
            {
                "id": str(h.id),
                "gate": h.gate,
                "decision": h.decision,
                "artifact_version": h.artifact_version,
                "note": h.note,
                "decided_by_name": h.decided_by_name,
                "decided_at": h.decided_at.isoformat() if h.decided_at else None,
            }
            for h in history
        ],
    }


@router.get(
    "/{project_id}/progress",
    summary="Where this project is: the 11-step stepper, the tabs and the gates",
)
async def get_project_progress(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """WP-62 Task 3, RULED. ONE computation, three consumers.

    The top stepper, the per-tab indicators and the Overview run panel's
    heading all read this. They used to derive their own answers from three
    different fields and could therefore disagree - and did: the stepper was
    frozen at DRAFT on a project whose Jobs tab listed a successful final
    render.

    Polled by the client. It is a read of three tables and a gate recompute;
    nothing here writes, and in particular NOTHING HERE REPAIRS
    `projects.state`. `stored_state` and `derived_state` are both on the
    payload, and `stored_state_matches` says whether they agree, because the
    gap is a fact about the project that an operator needs to see rather than
    something to silently paper over.
    """
    service = ProjectService(db)
    project = await service.get_project_model(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Project {project_id} not found",
                }
            },
        )
    return await ProjectProgressService(db).compute(project)

