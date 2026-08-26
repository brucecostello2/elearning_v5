"""WP-66 Tasks 3/4 — what a project is bound to, and where each binding came from.

THE FINDING THIS SERVES. The selection mechanism is complete at both ends and
had no middle: ``ProjectModelSelection`` carries a nullable ``scene_id``
(``shared/models/model_store.py:365``) so per-scene binding was designed in from
the start; dispatch honours it, scene first then project
(``shared/providers/factory.py:147-151``); three endpoints exist. And
``grep -rn "selections" ivgs-frontend/src`` returned nothing but a preset type
and a storyboard "clear all selections" handler. No picker, at any scope.

WHY PROVENANCE IS A FIRST-CLASS FIELD HERE. A resolved binding has four
different origins that look identical once resolved:

  * an explicit project selection the operator made
  * a selection a PRESET wrote (real -- ``preset_service.py:246`` -- and until
    WP-66 recorded as ``manual``, indistinguishable from the above)
  * a row the AUTO-PLANNER wrote (``POST /selections/plan`` persists; it is not
    a dry run, whatever its name suggests)
  * no row at all, falling back to the stage's ``is_default`` model

WP-60 Task 5 established that a surface presenting mixed provenance as one fact
is this codebase's recurring defect. So the panel never says "the model" without
also saying which of the four it is.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.model_store import (
    ProjectSelectionsOut,
    SelectionCandidateOut,
    SelectionOut,
    StageBindingOut,
)
from app.services.model_selection import SelectionRefused, _availability_refusal
from app.services.weight_placement import compute_status
from shared.models.model_store import (
    Model,
    ModelStage,
    ModelState,
    ModelTier,
    ProjectModelSelection,
    SelectionSource,
)

logger = logging.getLogger(__name__)

#: ``selected_by`` -> (provenance slug, the words shown beside the model).
_PROVENANCE: dict[SelectionSource, tuple[str, str]] = {
    SelectionSource.MANUAL: ("selection", "chosen for this project"),
    SelectionSource.PRESET: ("preset", "written by a preset"),
    SelectionSource.AUTO: ("auto", "chosen by the planner"),
}

_DEFAULT_PROVENANCE = ("default", "the system default for this stage")
_NONE_PROVENANCE = ("none", "no model is bound and no default exists")
_SCENE_PROVENANCE = ("scene", "overridden for this scene")

#: Lifecycle states a selection may legitimately keep pointing at. DEPRECATED
#: is servable (AD-01.5.1) but is worth a warning: it will stop being.
_SERVABLE = (ModelState.APPROVED, ModelState.DEPRECATED)


@dataclass
class _Resolved:
    provenance: str
    label: str
    selection: ProjectModelSelection | None
    model: Model | None
    warning: str | None = None

    def model_name_or_none(self) -> str:
        """The bound model's name, or words saying there is none.

        Never an empty string: a message reading "this scene now uses ()" is
        how an absence gets rendered as a value.
        """
        return self.model.name if self.model is not None else "no model"


def _stage_list() -> list[ModelStage]:
    """Every stage a project can bind, taken from the enum.

    Read from ``ModelStage`` rather than retyped, deliberately: the brief that
    commissioned this listed nine stages by hand and the enum is the authority.
    """
    return list(ModelStage)


async def _candidates_for(
    db: AsyncSession, stage: ModelStage, tier: ModelTier
) -> list[SelectionCandidateOut]:
    """Every model that could serve ``(stage, tier)``, usable or not.

    Unavailable models are included and labelled rather than filtered out. A
    user who cannot see the model they expected has no way to learn why, which
    is how "the picker is broken" gets reported instead of "the weights are not
    fetched".
    """
    stmt = (
        select(Model)
        .where(
            Model.stage == stage,
            Model.tier.in_([tier, ModelTier.BOTH]),
        )
        .order_by(Model.is_default.desc(), Model.name)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()

    out: list[SelectionCandidateOut] = []
    for model in rows:
        status = compute_status(model)
        candidate = SelectionCandidateOut(
            id=model.id,
            name=model.name,
            display_name=model.display_name,
            stage=model.stage,
            engine=model.engine,
            tier=model.tier,
            state=model.state,
            is_default=model.is_default,
            vram_gb=float(model.vram_gb) if model.vram_gb is not None else None,
            weight_state=status.state,
            weight_label=status.label,
        )

        # Ask the SAME function PUT /selections asks, so the picker cannot
        # offer something the write would refuse, or grey out something it
        # would accept. One definition of selectable, two readers.
        if model.state not in _SERVABLE:
            candidate.selectable = False
            candidate.refusal_reason = "not_approved"
            candidate.refusal_message = (
                f"{model.name} is {model.state.value}, not approved. An admin "
                f"approves a candidate in Admin -> Models after reviewing its "
                f"attestation."
            )
        elif not model.enabled:
            candidate.selectable = False
            candidate.refusal_reason = "disabled"
            candidate.refusal_message = f"{model.name} is disabled in the Model Store."
        else:
            refusal = _availability_refusal(model)
            if refusal is not None:
                candidate.selectable = False
                candidate.refusal_reason = refusal.reason
                candidate.refusal_message = str(refusal)

        out.append(candidate)
    return out


async def _selection_row(
    db: AsyncSession,
    project_id: UUID,
    stage: ModelStage,
    tier: ModelTier,
    scene_id: UUID | None,
) -> ProjectModelSelection | None:
    """The selection for one exact scope, newest first.

    Mirrors ``factory._get_binding_in_session``'s query exactly — same scope
    predicate, same ``created_at desc`` ordering, same ``limit(1)``. If these
    two ever disagree the panel shows one model and the render uses another,
    which is the failure mode this whole package exists to prevent.
    """
    stmt = (
        select(ProjectModelSelection)
        .where(
            ProjectModelSelection.project_id == project_id,
            ProjectModelSelection.stage == stage,
            ProjectModelSelection.tier == tier,
            ProjectModelSelection.scene_id == scene_id
            if scene_id is not None
            else ProjectModelSelection.scene_id.is_(None),
        )
        .order_by(ProjectModelSelection.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def resolve_binding(
    db: AsyncSession,
    *,
    project_id: UUID,
    stage: ModelStage,
    tier: ModelTier,
    scene_id: UUID | None = None,
) -> _Resolved:
    """What WILL run for this scope, and where the choice came from.

    Resolution order is dispatch's order, not a convenient one: scene-scoped
    selection, then project-scoped, then the stage's ``is_default`` model.
    """
    selection = None
    provenance = None

    if scene_id is not None:
        selection = await _selection_row(db, project_id, stage, tier, scene_id)
        if selection is not None:
            provenance = _SCENE_PROVENANCE

    if selection is None:
        selection = await _selection_row(db, project_id, stage, tier, None)
        if selection is not None:
            provenance = _PROVENANCE.get(
                selection.selected_by, ("selection", "chosen for this project")
            )

    if selection is not None:
        model = await db.get(Model, selection.model_id)
        warning = None
        if model is None:
            # The FK is ondelete=RESTRICT, so this should be unreachable. Said
            # out loud rather than rendered as a blank cell.
            warning = (
                f"this selection points at model {selection.model_id}, which no "
                f"longer exists"
            )
        elif model.state not in _SERVABLE:
            warning = (
                f"{model.name} is {model.state.value} and can no longer run. "
                f"The selection is kept, not rewritten — choose another model "
                f"before the next render."
            )
        elif not model.enabled:
            warning = f"{model.name} is disabled in the Model Store."
        else:
            refusal = _availability_refusal(model)
            if refusal is not None:
                warning = str(refusal)
            else:
                status = compute_status(model)
                if status.state != "available":
                    # NOT a refusal. WP-65 §7.4: IVGS having no record of a
                    # fetch is a fact about IVGS's records, not about the node.
                    warning = (
                        f"{status.label}. If the next render fails to load this "
                        f"model, an admin can fetch and verify its weights from "
                        f"Admin -> Models."
                    )
        assert provenance is not None
        return _Resolved(provenance[0], provenance[1], selection, model, warning)

    # No row at any scope -> the stage default, which is a real binding.
    default = (
        await db.execute(
            select(Model).where(
                Model.stage == stage,
                Model.tier.in_([tier, ModelTier.BOTH]),
                Model.is_default.is_(True),
            )
        )
    ).scalars().first()
    if default is None:
        return _Resolved(*_NONE_PROVENANCE, None, None)
    return _Resolved(*_DEFAULT_PROVENANCE, None, default)


async def project_panel(
    db: AsyncSession, *, project_id: UUID, tier: ModelTier
) -> ProjectSelectionsOut:
    """Task 3's whole payload: every stage, its binding, its provenance, its options."""
    bindings: list[StageBindingOut] = []
    for stage in _stage_list():
        resolved = await resolve_binding(
            db, project_id=project_id, stage=stage, tier=tier
        )
        bindings.append(
            StageBindingOut(
                stage=stage,
                tier=tier,
                provenance=resolved.provenance,
                provenance_label=resolved.label,
                selection=(
                    SelectionOut.from_row(resolved.selection)
                    if resolved.selection is not None
                    else None
                ),
                model_id=resolved.model.id if resolved.model else None,
                model_name=resolved.model.name if resolved.model else None,
                model_display_name=(
                    resolved.model.display_name if resolved.model else None
                ),
                warning=resolved.warning,
                candidates=await _candidates_for(db, stage, tier),
            )
        )
    return ProjectSelectionsOut(project_id=project_id, tier=tier, bindings=bindings)


#: WP-66 Task 4. media_type -> the stage that renders it. The scene picker
#: offers models for the stage its OWN media type dispatches to, so changing
#: Media Type changes the candidate list -- which is the behaviour the brief
#: asks for, expressed as data rather than as a conditional in the component.
MEDIA_TYPE_STAGE: dict[str, ModelStage] = {
    "image": ModelStage.IMAGE_GENERATION,
    "video_clip": ModelStage.VIDEO_GENERATION,
    "animation": ModelStage.ANIMATION_GENERATION,
}


async def scene_panel(
    db: AsyncSession,
    *,
    project_id: UUID,
    scene_id: UUID,
    media_type: str,
    tier: ModelTier,
) -> StageBindingOut:
    """Task 4's payload for one scene: its stage, its override, its inheritance."""
    stage = MEDIA_TYPE_STAGE.get(media_type or "image", ModelStage.IMAGE_GENERATION)
    resolved = await resolve_binding(
        db, project_id=project_id, stage=stage, tier=tier, scene_id=scene_id
    )
    return StageBindingOut(
        stage=stage,
        tier=tier,
        provenance=resolved.provenance,
        provenance_label=resolved.label,
        selection=(
            SelectionOut.from_row(resolved.selection)
            if resolved.selection is not None
            else None
        ),
        model_id=resolved.model.id if resolved.model else None,
        model_name=resolved.model.name if resolved.model else None,
        model_display_name=resolved.model.display_name if resolved.model else None,
        warning=resolved.warning,
        candidates=await _candidates_for(db, stage, tier),
    )
