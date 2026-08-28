"""AD-01 Model Store + selection-planner routes (ARCH-1 Tarball 1).

Mutations are admin-only (AD-01.10); the planner and manual override accept
operator-or-admin (AD-01.8.4). Lifecycle rules enforced here:
  * CANDIDATE -> APPROVED requires a complete attestation (AD-01.7.2);
  * APPROVED -> DEPRECATED -> RETIRED are one-way admin actions;
  * is_default is a transactional swap (one per stage/tier).
"""
from __future__ import annotations

from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_admin, require_operator_or_admin
from app.models.user import User
from app.schemas.model_store import (
    ApproveIn,
    AvailabilityIn,
    AvailabilityOut,
    ClearSelectionIn,
    ClearSelectionOut,
    ClientStatusOut,
    FetchWeightsOut,
    ManualSelectionIn,
    ModelOut,
    ModelRegisterIn,
    ModelUpdateIn,
    PlanRequest,
    PlanResponse,
    ProjectSelectionsOut,
    SelectionOut,
    StageBindingOut,
    WeightStatusOut,
)
from app.services import model_selection as planner
from app.services import selection_panel
from app.services import weight_placement as weights
from app.services.model_selection import PlanningError, SelectionRefused
from shared.database import get_session
from shared.models.model_store import (
    Model,
    ModelApproval,
    ModelCapabilityTag,
    ModelNodeAvailability,
    ModelStage,
    ModelState,
    ModelTier,
    ProjectModelSelection,
)
from app.models.audit_log import AuditLog
from shared.weights.service import fetch_model_weights

models_router = APIRouter(prefix="/models", tags=["Model Store"])
selections_router = APIRouter(
    prefix="/projects/{project_id}/model-selections",
    tags=["Model Selections"],
)


async def _get_model_or_404(db: AsyncSession, model_id: UUID) -> Model:
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "model not found")
    return model


# --------------------------------------------------------------------------
# registry CRUD
# --------------------------------------------------------------------------

def _with_weight_status(model: Model) -> ModelOut:
    """Serialise a model and attach WP-65's computed weight state.

    ``weight_status`` is derived, not stored: it is the answer to "what should
    an admin do about this model's weights", and it is computed from the
    placement rows plus the offline part of the fetch plan. Attaching it here
    rather than letting the frontend infer it is deliberate -- the frontend
    inferring availability from a row count is precisely the defect WP-65 Task
    1 measured (``page.tsx:606``).
    """
    out = ModelOut.model_validate(model)
    out.weight_status = WeightStatusOut(**weights.compute_status(model).as_dict())
    # WP-67 Task 5. Computed here for the same reason weight_status is: the
    # frontend inferring runnability from what it can see is the defect, and
    # there is nothing on a Model row from which "IVGS has a client for this"
    # could be inferred at all.
    out.client_status = ClientStatusOut(
        **weights.compute_client_status(model).as_dict()
    )
    return out


@models_router.get("", response_model=list[ModelOut])
async def list_models(
    stage: ModelStage | None = None,
    state: ModelState | None = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> list[ModelOut]:
    stmt = select(Model).order_by(Model.stage, Model.name)
    if stage is not None:
        stmt = stmt.where(Model.stage == stage)
    if state is not None:
        stmt = stmt.where(Model.state == state)
    rows = list((await db.execute(stmt)).scalars().unique().all())
    return [_with_weight_status(m) for m in rows]


@models_router.get("/{model_id}", response_model=ModelOut)
async def get_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> ModelOut:
    return _with_weight_status(await _get_model_or_404(db, model_id))


@models_router.post(
    "", response_model=ModelOut, status_code=status.HTTP_201_CREATED,
)
async def register_model(
    body: ModelRegisterIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Model:
    """AD-01.5.1: registration lands in CANDIDATE — never selectable."""
    dup = (
        await db.execute(select(Model).where(Model.name == body.name))
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"model name {body.name!r} already exists"
        )
    model = Model(
        name=body.name,
        display_name=body.display_name,
        stage=body.stage,
        engine=body.engine,
        tier=body.tier,
        state=ModelState.CANDIDATE,
        description=body.description,
        strengths=body.strengths,
        weaknesses=body.weaknesses,
        source_url=body.source_url,
        weights_ref=body.weights_ref,
        weights_checksum=body.weights_checksum,
        license=body.license,
        vram_gb=body.vram_gb,
        dynamically_loadable=body.dynamically_loadable,
        default_params=body.default_params,
        created_by=current_user.username,
    )
    for tag in body.capability_tags:
        model.capability_tags.append(
            ModelCapabilityTag(
                dimension=tag.dimension, value=tag.value, weight=tag.weight,
            )
        )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@models_router.patch("/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: UUID,
    body: ModelUpdateIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Model:
    model = await _get_model_or_404(db, model_id)
    data = body.model_dump(exclude_unset=True)
    is_default = data.pop("is_default", None)
    for key, value in data.items():
        setattr(model, key, value)
    if is_default is not None:
        if is_default and model.state != ModelState.APPROVED:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "only an APPROVED model may be the (stage, tier) default",
            )
        await planner.set_default(db, model=model, is_default=is_default)
    await db.commit()
    await db.refresh(model)
    return model


@models_router.post("/{model_id}/approve", response_model=ModelOut)
async def approve_model(
    model_id: UUID,
    body: ApproveIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Model:
    """AD-01.7.2: CANDIDATE -> APPROVED, rejected without the attestation."""
    model = await _get_model_or_404(db, model_id)
    if model.state != ModelState.CANDIDATE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"only CANDIDATE models can be approved "
            f"(current: {model.state.value})",
        )
    if not body.checklist:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "attestation checklist must not be empty (AD-01.7.2)",
        )
    model.approvals.append(
        ModelApproval(
            attested_by=body.attested_by,
            vetting_reference=body.vetting_reference,
            checklist=body.checklist,
        )
    )
    model.state = ModelState.APPROVED
    await db.commit()
    await db.refresh(model)
    return model


@models_router.post("/{model_id}/deprecate", response_model=ModelOut)
async def deprecate_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Model:
    model = await _get_model_or_404(db, model_id)
    if model.state != ModelState.APPROVED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"only APPROVED models can be deprecated "
            f"(current: {model.state.value})",
        )
    model.state = ModelState.DEPRECATED
    model.is_default = False
    await db.commit()
    await db.refresh(model)
    return model


@models_router.post("/{model_id}/retire", response_model=ModelOut)
async def retire_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> Model:
    model = await _get_model_or_404(db, model_id)
    if model.state != ModelState.DEPRECATED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"only DEPRECATED models can be retired "
            f"(current: {model.state.value})",
        )
    model.state = ModelState.RETIRED
    model.enabled = False
    await db.commit()
    await db.refresh(model)
    return model


@models_router.put(
    "/{model_id}/availability/{node_id}", response_model=AvailabilityOut,
)
async def upsert_availability(
    model_id: UUID,
    node_id: str,
    body: AvailabilityIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> ModelNodeAvailability:
    """Poller/ops upsert (AD-01.6 availability poller writes through here)."""
    from datetime import datetime

    await _get_model_or_404(db, model_id)
    row = (
        await db.execute(
            select(ModelNodeAvailability).where(
                ModelNodeAvailability.model_id == model_id,
                ModelNodeAvailability.node_id == node_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = ModelNodeAvailability(model_id=model_id, node_id=node_id)
        db.add(row)
    row.status = body.status
    row.served = body.served
    row.last_health_check = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


# --------------------------------------------------------------------------
# weights (WP-65)
# --------------------------------------------------------------------------

@models_router.get("/{model_id}/weight-status", response_model=WeightStatusOut)
async def weight_status(
    model_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> WeightStatusOut:
    """The honest state of one model's weights. No side effects.

    Computable without credentials or network: every refusal short of the
    transfer itself is decidable offline, which is what lets the admin page
    label a model correctly before anyone clicks anything.
    """
    model = await _get_model_or_404(db, model_id)
    return WeightStatusOut(**weights.compute_status(model).as_dict())


@models_router.post(
    "/{model_id}/fetch-weights",
    response_model=FetchWeightsOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def fetch_weights(
    model_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
) -> FetchWeightsOut:
    """Fetch a certified model's weights to the node that will run it.

    ADMIN-ONLY AND GUI-ONLY -- the standing IVGS rule that admin functionality
    has no CLI. The refusals are first-class results, not errors: a model whose
    engine has no host, or whose certification is engine-only, gets a recorded
    placement row saying exactly that, so "nobody has tried" and "this can
    never work" stop looking the same.

    The response is 202 in every case. A refusal is an ANSWER -- it is the
    outcome of the action the admin asked for, and it is durable. The
    ``accepted`` flag and ``state`` say which happened; the page does not have
    to parse an error body to find out.
    """
    model = await _get_model_or_404(db, model_id)

    outcome = fetch_model_weights(model)
    row = await weights.record_outcome(
        db, model, outcome, actor=current_user.username,
    )
    await db.commit()
    await db.refresh(model)

    status_now = weights.compute_status(model)
    return FetchWeightsOut(
        accepted=outcome.ok,
        state=status_now.state,
        reason=None if outcome.ok else (outcome.error.reason if outcome.error else None),
        message=(
            f"weights already present and verified on {row.node_id}"
            if outcome.skipped_present
            else f"fetched and verified {row.file_count or 0} file(s) to {row.node_id}"
            if outcome.ok
            else str(outcome.error)
        ),
        placement=row,
        status=WeightStatusOut(**status_now.as_dict()),
    )


# --------------------------------------------------------------------------
# planner + selections
# --------------------------------------------------------------------------

@selections_router.get("", response_model=list[SelectionOut])
async def list_selections(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> list[SelectionOut]:
    """Every selection row for a project, project- and scene-scoped alike.

    Scene rows are distinguished by a non-null ``scene_id``; there is no filter
    parameter and none is added, because a picker needs both scopes to show
    which scenes override the project default.
    """
    stmt = (
        select(ProjectModelSelection)
        .where(ProjectModelSelection.project_id == project_id)
        .order_by(
            ProjectModelSelection.stage,
            ProjectModelSelection.tier,
            ProjectModelSelection.scene_id,
        )
    )
    rows = list((await db.execute(stmt)).scalars().unique().all())
    # WP-66: the model relationship is lazy="joined" and already travelled with
    # every one of these rows; the schema simply dropped it, leaving callers to
    # fetch the whole registry to render a name.
    return [SelectionOut.from_row(r) for r in rows]


@selections_router.post("/plan", response_model=PlanResponse)
async def plan(
    project_id: UUID,
    body: PlanRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> PlanResponse:
    """AD-01.6 planning step — binds a model per requested stage."""
    if body.tier == ModelTier.BOTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "plan for a concrete tier: prototype or production",
        )
    try:
        rows = await planner.plan_selections(
            db,
            project_id=project_id,
            stages=body.stages,
            tier=body.tier,
            capability_profile=body.capability_profile,
        )
    except PlanningError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
        ) from exc
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return PlanResponse(
        selections=[SelectionOut.model_validate(r) for r in rows]
    )


@selections_router.put("", response_model=SelectionOut)
async def override(
    project_id: UUID,
    body: ManualSelectionIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> ProjectModelSelection:
    """AD-01.8.4 manual override at project or scene level."""
    if body.tier == ModelTier.BOTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "override a concrete tier: prototype or production",
        )
    previous = await selection_panel.resolve_binding(
        db, project_id=project_id, stage=body.stage, tier=body.tier,
        scene_id=body.scene_id,
    )
    try:
        row = await planner.manual_override(
            db,
            project_id=project_id,
            scene_id=body.scene_id,
            stage=body.stage,
            tier=body.tier,
            model_id=body.model_id,
            rationale=(
                f"{body.rationale} (manual override by "
                f"{current_user.username})"
            ),
            actor_user_id=current_user.id,
        )
    except SelectionRefused as exc:
        # WP-66 Task 2. A 4xx with a message the user can act on, and a machine
        # slug beside it so the UI can offer the right next step -- "an admin
        # can fetch them from Admin -> Models" is a different remedy from
        # "an admin approves a candidate", and a generic validation error tells
        # the user neither.
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": exc.reason.upper(), "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
        ) from exc

    # WP-IVGS-08 Task 5. THE AUDIT MOVED DOWN, it did not disappear.
    # `manual_override` now writes it (`services/model_selection.py`), because
    # the preset path calls that function directly and bypassed this block
    # entirely -- WP-66's finding. Keeping a copy here would double-audit every
    # route write and leave two definitions of what a selection audit contains.
    await db.commit()
    await db.refresh(row)
    return SelectionOut.from_row(row)


# --------------------------------------------------------------------------
# WP-66 — the selection UI's read and clear paths
# --------------------------------------------------------------------------

@selections_router.get("/panel", response_model=ProjectSelectionsOut)
async def selection_panel_read(
    project_id: UUID,
    tier: ModelTier = ModelTier.PRODUCTION,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> ProjectSelectionsOut:
    """Every stage this project will run, its binding, and WHERE IT CAME FROM.

    One request rather than nine, and provenance computed server-side beside the
    model it describes -- a frontend that derives "is this a default?" from the
    absence of a row is exactly the inference WP-60 Task 5 found being made
    wrongly across this codebase.

    ``tier`` defaults to PRODUCTION because that is what a finished render uses;
    the panel presents it explicitly rather than hiding it, so a user choosing a
    production-tier model knows that is what they chose.
    """
    return await selection_panel.project_panel(db, project_id=project_id, tier=tier)


@selections_router.get("/scene/{scene_id}", response_model=StageBindingOut)
async def scene_selection_read(
    project_id: UUID,
    scene_id: UUID,
    media_type: str = "image",
    tier: ModelTier = ModelTier.PRODUCTION,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> StageBindingOut:
    """One scene's binding, for the stage ITS media type dispatches to.

    Changing Media Type changes the stage, which changes the candidate list --
    an animation scene offers animation models. The mapping is data
    (``selection_panel.MEDIA_TYPE_STAGE``), not a conditional in the component.

    WP-IVGS-09b: an unmapped ``media_type`` is a **422 that names it**, not a
    silent fall back to image generation. The fall back is what let
    ``motion_graphics`` sit unmapped while the picker confidently offered FLUX
    for a scene that draws arithmetic -- a wrong answer with nothing to notice.
    """
    try:
        return await selection_panel.scene_panel(
            db, project_id=project_id, scene_id=scene_id,
            media_type=media_type, tier=tier,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
        ) from exc


@selections_router.post("/clear", response_model=ClearSelectionOut)
async def clear_scene_selection(
    project_id: UUID,
    body: ClearSelectionIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> ClearSelectionOut:
    """"Use the project default" for one scene — DELETES the scene row.

    Not "write the project's model onto the scene". The difference only shows up
    later, and then it is silent: a duplicated row keeps pointing at the old
    model after the project default changes, while dispatch reads scene-scoped
    first (``factory.py:147-151``) and never looks at the project row again. The
    scene would stop following a default it appears to be following.
    """
    previous = await selection_panel.resolve_binding(
        db, project_id=project_id, stage=body.stage, tier=body.tier,
        scene_id=body.scene_id,
    )
    cleared = await planner.clear_selection(
        db, project_id=project_id, scene_id=body.scene_id,
        stage=body.stage, tier=body.tier,
    )
    if cleared:
        db.add(
            AuditLog(
                user_id=current_user.id,
                action_type="MODEL_SELECTION_CLEARED",
                resource_type="project",
                resource_id=project_id,
                before_payload={
                    "stage": body.stage.value,
                    "tier": body.tier.value,
                    "scene_id": str(body.scene_id),
                    "previous_model": previous.model.name if previous.model else None,
                },
                after_payload={"scope": "scene", "cleared": cleared},
            )
        )
    await db.commit()

    now = await selection_panel.resolve_binding(
        db, project_id=project_id, stage=body.stage, tier=body.tier,
        scene_id=body.scene_id,
    )
    return ClearSelectionOut(
        cleared=cleared,
        message=(
            f"scene override removed; this scene now uses "
            f"{now.model_name_or_none()} ({now.label})"
            if cleared
            else "this scene had no override; nothing was cleared"
        ),
    )
