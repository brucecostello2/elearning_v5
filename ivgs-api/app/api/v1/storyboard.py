"""
Storyboard scene API endpoints per §5.1.4.

Endpoints:
- GET    /api/v1/projects/{id}/scenes               — List scenes
- PATCH  /api/v1/projects/{id}/scenes/{sid}          — Update scene
- POST   /api/v1/projects/{id}/scenes/reorder        — Bulk reorder
- POST   /api/v1/projects/{id}/scenes/{sid}/regenerate — Queue scene regeneration
- POST   /api/v1/projects/{id}/scenes/{sid}/adapt-description — Propose a
         medium-appropriate rewrite of this scene's visual description (WP-64
         Task 3). Returns a proposal; writes no scene row.
- POST   /api/v1/projects/{id}/scenes/auto-repair — WP-IVGS-12i RC-R4. Repair
         every MECHANICAL refusal before the gate opens, declare each on the
         design brief, re-validate once. The orchestrator calls it.
- POST   /api/v1/projects/{id}/scenes/{sid}/author-motion — WP-IVGS-12i RC-R2.
         The MANUAL half of the same primitive: one scene, on the reviewer's
         press, for the judgment cases code deliberately does not touch.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user, get_service_or_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.storyboard import (
    SceneAdaptDescriptionRequest,
    SceneAdaptDescriptionResponse,
    SceneBatchRegenerateRequest,
    SceneCreate,
    SceneReorderRequest,
    SceneResponse,
    SceneUpdate,
)
from app.schemas.render_job import JobResponse
from app.services.design_brief_service import SCENE_DESIGN_FIELDS
from app.services.storyboard_service import StoryboardService
from app.services.regeneration import RegenerationError
from app.api.v1._dispatch_guards import already_running, gate_blocked
from app.services.gate_service import GateBlocked
from app.services.project_service import PipelineAlreadyRunningError
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
        # WP-45 Task 6(d): Stage 2 can now persist these on creation rather than
        # having them added by hand afterwards.
        camera_angle=data.camera_angle,
        transition_type=data.transition_type,
        effects=data.effects,
        timing_offset_ms=data.timing_offset_ms,
        generation_params=data.generation_params,
        # WP-IVGS-10. v7 emits these; the route accepts them so that a
        # storyboard authored under v7 arrives complete rather than being
        # reconstructed afterwards.
        media_rationale=data.media_rationale,
        text_carried_by=data.text_carried_by,
        # ── WP-IVGS-12 ──
        # ⛔ BUILT FROM A SHARED TUPLE, NOT TYPED OUT. Every explicit keyword
        # list above this line is the shape that produced RC-P1: v7 asked the
        # model for three new fields, the two lists in the frozen stage body
        # named five and eight, and not one of the three could reach the
        # database for three days. A hand-maintained whitelist drops the field
        # that was added last, which is always the field somebody is waiting on.
        # `test_wpivgs12_design_contract.py` asserts that every SceneCreate
        # field reaches a column, so a v9 field that nobody wires here FAILS A
        # TEST instead of vanishing.
        design={
            name: getattr(data, name, None)
            for name in SCENE_DESIGN_FIELDS
            if getattr(data, name, None) is not None
        },
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
    """Update any of the nine scene fields the Edit Scene modal sends.

    WP-45 Task 6(d) / WP-43 D-2: camera_angle, transition_type, effects,
    timing_offset_ms and generation_params are persisted for the first time.
    They were sent, accepted with a 200, and dropped by Pydantic because
    SceneUpdate did not declare them.

    ``exclude_unset`` is what makes clearing a field possible: only keys the
    client actually sent are written, so ``{"camera_angle": null}`` clears it
    while omitting the key leaves it alone. Under the old fixed signature both
    arrived as ``None`` and neither could be told from the other.
    """
    service = StoryboardService(db)
    fields = data.model_dump(exclude_unset=True)
    try:
        scene = await service.update_scene(
            project_id=project_id,
            scene_id=scene_id,
            **fields,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Scene {scene_id} not found"}},
        )
    return SceneResponse.model_validate(scene)


@router.post(
    "/{scene_id}/adapt-description",
    response_model=SceneAdaptDescriptionResponse,
    summary="Adapt this scene's visual description to a medium",
)
async def adapt_scene_description(
    project_id: UUID,
    scene_id: UUID,
    data: SceneAdaptDescriptionRequest,
    request: Request,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Propose a rewrite of this scene's visual description for a medium.

    WP-64 Task 3. **This endpoint never writes the scene.** It returns the
    rewrite for the operator to read, edit and save; saving is the existing
    ``PATCH /projects/{id}/scenes/{sid}``. A feature that silently replaced an
    operator's own words the moment they changed a dropdown would destroy
    authored intent with no diff and no undo.

    WHY IT EXISTS. A scene's description is authored once by Stage 2 for the
    media_type Stage 2 chose. ``update_scene`` above persists a media_type
    change with no rewrite, and neither media task adds the motion afterwards
    (``video_generation_task.py:245``, ``animation_generation_task.py:389``
    interpolate the description as-is). So a scene switched to video used to
    reach CogVideoX carrying a still's words. This is the explicit repair.

    409 PIPELINE_ALREADY_RUNNING, though it dispatches no stage: it consumes
    capacity on the same LLM a running Stage 1 or Stage 2 is using, and it
    reads scene rows that run may be about to overwrite (Task 3(c)).
    """
    from app.services.adaptation_service import AdaptationError, AdaptationService

    client_ip = request.client.host if request.client else None
    try:
        result = await AdaptationService(db).adapt_description(
            project_id=project_id,
            scene_id=scene_id,
            target_media_type=data.target_media_type,
            actor=current_user,
            client_ip=client_ip,
        )
    except PipelineAlreadyRunningError as e:
        raise already_running(e)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    except AdaptationError as e:
        # 502, not 500: the API worked, the model or its endpoint did not, and
        # the operator needs to be able to tell those apart before deciding
        # whether to retry (WP-61's rebuilt distinction, applied here).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "ADAPTATION_FAILED", "message": str(e)}},
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Scene {scene_id} not found in project {project_id}",
                }
            },
        )
    return SceneAdaptDescriptionResponse(**result)


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
    """Re-run this scene's media generation from its current fields (WP-45 Task 3).

    A 202 from this route now means a broker message was produced. It used to
    mean a row was inserted.
    """
    service = StoryboardService(db)
    try:
        job = await service.regenerate_scene(project_id, scene_id)
    except PipelineAlreadyRunningError as e:
        # WP-62 Task 6 (WP-61 D-1, RULED: extend). THIS IS THE ROUTE THE
        # MEASURED INCIDENT USED. WP-60's six dispatches on project 52d52867
        # were `video_generation` and `animation_generation` job types, which
        # `trigger_pipeline` does not produce - they came through here, and
        # WP-61's guard did not reach it.
        raise already_running(e)
    except GateBlocked as e:
        # WP-62 Task 2(c). A regeneration dispatches media generation, so it is
        # behind the storyboard gate like every other path that does.
        raise gate_blocked(e)
    except RegenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "REGENERATION_UNAVAILABLE", "message": str(e)}},
        )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Scene {scene_id} not found"}},
        )
    return JobResponse.model_validate(job)


@router.post(
    "/batch-regenerate",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue regeneration of several scenes in one dispatch",
)
async def batch_regenerate_scenes(
    project_id: UUID,
    data: SceneBatchRegenerateRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Re-run these scenes' media generation, from their current fields.

    WP-63 Task 7. THE ROUTE THE "REGENERATE SELECTED" BUTTON HAS BEEN POSTING
    TO SINCE WP-38, AND IT DID NOT EXIST. `useStoryboard.regenerateScenes`
    (ivgs-frontend/src/hooks/useStoryboard.ts) has always called
    `POST /api/v1/projects/{id}/scenes/batch-regenerate`; every press answered
    404 and the surface showed nothing, because the hook's `mutate` rolls the
    optimistic state back on error and no caller catches.

    ONE job row, ONE broker message, ONE armed media join, however many scenes.
    Behind exactly the same two refusals as the single-scene route, because it
    is the same choke point.
    """
    service = StoryboardService(db)
    try:
        job = await service.regenerate_scenes(project_id, data.scene_ids)
    except PipelineAlreadyRunningError as e:
        raise already_running(e)
    except GateBlocked as e:
        raise gate_blocked(e)
    except RegenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "REGENERATION_UNAVAILABLE", "message": str(e)}},
        )
    return JobResponse.model_validate(job)


@router.post(
    "/approve",
    summary="Approve storyboard -> start media generation (P1.5 item 2)",
)
async def approve_storyboard(
    project_id: UUID,
    request: Request,
    tier: str = Query(
        default="prototype",
        description=(
            "AD-01 model-selection tier for the media-generation run: "
            "prototype or production. Defaults to prototype."
        ),
    ),
    note: Optional[str] = Query(
        default=None,
        max_length=4000,
        description="Recorded with the gate decision and in audit_log.",
    ),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Approve the storyboard and resume the pipeline into media generation.

    WP-62 Task 2(a). THE SURFACE IS UNCHANGED AND THE BEHAVIOUR IS NOT.

    This is the endpoint the "Approve storyboard" button has posted to since
    P1.5. Measured 2026-08-26, all it did was set `projects.state` and dispatch
    `dispatch_media_generation`: no record of the decision, no reader, and
    therefore nothing anywhere that could refuse for want of an approval.

    It now RECORDS the decision first, against the exact storyboard version on
    screen, and releases second. The enforcement was built behind the existing
    surface rather than beside it, deliberately: a second Approve button would
    have left this one as a working bypass of the gate it was supposed to be.

    `POST /projects/{id}/gates/storyboard` is the contract-shaped equivalent
    (WP-62 Task 2(b)) and runs the identical service call.
    """
    from app.api.v1.projects import GateDecisionRequest, _gate_decision
    from app.models.project_gate import DECISION_APPROVE, GATE_STORYBOARD

    return await _gate_decision(
        project_id,
        GATE_STORYBOARD,
        GateDecisionRequest(decision=DECISION_APPROVE, note=note),
        request,
        current_user,
        db,
    )


# ---------------------------------------------------------------------------
# WP-IVGS-12i — the repair pass, and its manual twin
# ---------------------------------------------------------------------------

@router.post(
    "/auto-repair",
    summary="Repair every mechanical refusal, declared (WP-IVGS-12i RC-R4)",
)
async def auto_repair_scenes(
    project_id: UUID,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """One pass. Mechanical refusals repaired and declared; judgment untouched.

    ⛳ `get_service_or_user` BECAUSE THE ORCHESTRATOR IS THE CALLER. It runs
    between stage 2 finishing and the gate opening, which is the only moment at
    which "before the gate" means anything. It is also reachable by an operator,
    because a storyboard edited at the gate can acquire a mechanical refusal that
    was not there when the design was generated.

    ⛔ NOT IDEMPOTENT IN THE TRIVIAL SENSE AND IT DOES NOT PRETEND TO BE: a
    second call re-assesses and repairs whatever is mechanical NOW, and
    overwrites the declaration with the new pass. That is correct — the
    declaration describes the storyboard as it stands, not a history — and it is
    still ONE authoring call per refused scene per pass. There is no loop.
    """
    project_service = ProjectService(db)
    project = await project_service.get_project(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"Project {project_id} not found"}},
        )

    from app.services.storyboard_repair import repair_and_declare

    result = await repair_and_declare(db, project_id, project)
    return result.as_dict()


@router.post(
    "/{scene_id}/author-motion",
    response_model=SceneResponse,
    summary="Author this scene as motion graphics (WP-IVGS-12i RC-R2)",
)
async def author_scene_as_motion(
    project_id: UUID,
    scene_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Flip ONE scene to `motion_graphics` and author its template from its words.

    ⛳ THE SAME PRIMITIVE THE AUTO-REPAIR PASS CALLS, ON A HUMAN'S PRESS. Two
    surfaces, one mechanism, for the reason WP-45 gives about dispatch and
    WP-IVGS-09f gives about payload builders: a second implementation of a rule
    is a second place for it to be wrong.

    This is the override path. Auto-repair deliberately touches only refusals
    with a deterministic default exit; a reviewer looking at a JUDGMENT finding —
    or at a scene that refuses nothing at all but that they judge belongs in a
    drawn medium — presses this.

    ⛔ IT REFUSES BY NAME AND WRITES NOTHING WHEN AUTHORING REFUSES. The scene is
    left exactly as it was, medium included.
    """
    from app.services.motion_authoring import (
        MotionAuthoringError,
        author_params_for_scene,
    )
    from app.models.storyboard_scene import StoryboardScene

    project_service = ProjectService(db)
    project = await project_service.get_project(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"Project {project_id} not found"}},
        )

    rows = list((await db.scalars(
        select(StoryboardScene)
        .where(StoryboardScene.project_id == project_id)
        .order_by(StoryboardScene.scene_index)
    )).all())
    scene = next((r for r in rows if r.id == scene_id), None)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"Scene {scene_id} not found"}},
        )

    try:
        spec = await author_params_for_scene(
            db,
            project_id=project_id,
            narration=scene.narration_text or "",
            # ⛳ PASSED, NEVER REWRITTEN. The description is the operator's and
            # it survives the flip; the renderer draws from the template.
            visual_description=scene.visual_description or "",
            project_name=getattr(project, "name", "") or "",
            project_description=getattr(project, "description", "") or "",
            scene_index=scene.scene_index,
            context_scenes=[(r.scene_index, r.narration_text or "") for r in rows],
        )
    except MotionAuthoringError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {
                "code": "MOTION_AUTHORING_REFUSED",
                "message": (
                    f"Scene {scene.scene_index} could not be authored as motion "
                    f"graphics: {exc} Nothing was changed — the scene is still "
                    f"{scene.media_type!r}."
                ),
            }},
        )

    scene.media_type = "motion_graphics"
    scene.generation_params = spec
    scene.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(scene)
    logger.info(
        "scene_authored_as_motion project=%s scene=%s index=%s template=%s",
        project_id, scene_id, scene.scene_index, spec.get("template"),
    )
    return SceneResponse.model_validate(scene)
