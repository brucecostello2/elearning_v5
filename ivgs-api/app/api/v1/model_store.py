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
    ManualSelectionIn,
    ModelOut,
    ModelRegisterIn,
    ModelUpdateIn,
    PlanRequest,
    PlanResponse,
    SelectionOut,
)
from app.services import model_selection as planner
from app.services.model_selection import PlanningError
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

@models_router.get("", response_model=list[ModelOut])
async def list_models(
    stage: ModelStage | None = None,
    state: ModelState | None = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> list[Model]:
    stmt = select(Model).order_by(Model.stage, Model.name)
    if stage is not None:
        stmt = stmt.where(Model.stage == stage)
    if state is not None:
        stmt = stmt.where(Model.state == state)
    return list((await db.execute(stmt)).scalars().unique().all())


@models_router.get("/{model_id}", response_model=ModelOut)
async def get_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> Model:
    return await _get_model_or_404(db, model_id)


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
# planner + selections
# --------------------------------------------------------------------------

@selections_router.get("", response_model=list[SelectionOut])
async def list_selections(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_operator_or_admin),
) -> list[ProjectModelSelection]:
    stmt = (
        select(ProjectModelSelection)
        .where(ProjectModelSelection.project_id == project_id)
        .order_by(
            ProjectModelSelection.stage,
            ProjectModelSelection.tier,
            ProjectModelSelection.scene_id,
        )
    )
    return list((await db.execute(stmt)).scalars().unique().all())


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
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
        ) from exc
    await db.commit()
    await db.refresh(row)
    return row
