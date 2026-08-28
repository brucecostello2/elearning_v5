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
from app.services.weight_placement import (
    CLIENT_AVAILABLE,
    compute_client_status,
    compute_status,
)
# Importing this module POPULATES the registry: `client_registry.py:635` calls
# `register_builtin_clients()` at module scope. `engines_for_families` is empty
# without that, and `engines_for_media_type` RAISES on an empty result rather
# than widening -- so if that call is ever removed, this fails loudly here
# instead of quietly offering every engine on the stage again.
from shared.providers.client_registry import engines_for_families
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
#: WP-IVGS-09b. A medium that shares a stage can have no `is_default` of its own
#: -- the flag is one-per-stage and `animation_generation`'s belongs to Wan. When
#: such a medium has exactly ONE servable model, that model is what will run, and
#: saying so is more useful than "none". It is deliberately NOT called "default":
#: nobody chose it, it is simply the only candidate, and if a second is approved
#: this provenance disappears and the operator is asked to choose.
_ONLY_CANDIDATE_PROVENANCE = (
    "only_candidate", "the only model this medium can use"
)

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
    db: AsyncSession,
    stage: ModelStage,
    tier: ModelTier,
    engines: frozenset[str] | None = None,
) -> list[SelectionCandidateOut]:
    """Every model that could serve ``(stage, tier)``, usable or not.

    Unavailable models are included and labelled rather than filtered out. A
    user who cannot see the model they expected has no way to learn why, which
    is how "the picker is broken" gets reported instead of "the weights are not
    fetched".

    ``engines`` narrows that to the engines a MEDIUM can actually use, and is
    the one exception to the sentence above -- WP-IVGS-09b. It is not an
    availability filter: a Wan2.2-Animate row is not "unavailable" to a
    motion-graphics scene, it is *not a candidate for it at all*, and listing it
    greyed-out would invite the operator to wonder why. ``None`` means the
    caller's stage serves one medium and no narrowing applies; the project-scope
    caller passes ``None`` because it asks about a STAGE and has no medium.
    """
    stmt = (
        select(Model)
        .where(
            Model.stage == stage,
            Model.tier.in_([tier, ModelTier.BOTH]),
        )
        .order_by(Model.is_default.desc(), Model.name)
    )
    if engines is not None:
        stmt = stmt.where(Model.engine.in_(sorted(engines)))
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
            else:
                # WP-67 Task 5. A model with no client is a THIRD kind of
                # unusable, and it is the most absolute of the three: no admin
                # action and no operator action can make it runnable, because
                # what is missing is code. It bars a selection for the same
                # reason `no_host` does -- a render bound to it has nowhere to
                # go -- but it says something different, because it needs a
                # different person.
                client = compute_client_status(model)
                if client.state != CLIENT_AVAILABLE:
                    candidate.selectable = False
                    candidate.refusal_reason = client.state
                    candidate.refusal_message = client.detail or client.label

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
    engines: frozenset[str] | None = None,
) -> _Resolved:
    """What WILL run for this scope, and where the choice came from.

    Resolution order is dispatch's order, not a convenient one: scene-scoped
    selection, then project-scoped, then the stage's ``is_default`` model.

    ``engines`` narrows the LAST of those three to the engines a medium can use
    -- WP-IVGS-09b, and the fix is only half done without it. With the candidate
    list corrected but the default left stage-wide, a ``motion_graphics`` scene
    with no selection of its own resolved to ``wan2.2-animate``: the panel
    offered exactly one model, ``maths-motion``, and announced underneath it that
    the scene was currently bound to a model that cannot render it. Measured in
    exactly that state before this change.

    It does NOT narrow the two selection lookups. A row an operator wrote is
    theirs, and if it points somewhere the medium cannot use, the right
    behaviour is the warning machinery below -- surfaced, never silently
    rewritten -- not a filter that makes their choice disappear.
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
    #
    # WP-IVGS-09b: within the medium's engines, where the medium narrows them.
    # `animation_generation` has one `is_default` row (`wan2.2-animate`) and it
    # is the default for the ANIMATION medium, not for every medium the stage
    # serves.
    default_stmt = select(Model).where(
        Model.stage == stage,
        Model.tier.in_([tier, ModelTier.BOTH]),
        Model.is_default.is_(True),
    )
    if engines is not None:
        default_stmt = default_stmt.where(Model.engine.in_(sorted(engines)))
    default = (await db.execute(default_stmt)).scalars().first()

    if default is None and engines is not None:
        # No `is_default` inside this medium. Rather than fall back to the
        # stage's default -- which is another medium's model, and the whole
        # defect -- take the one servable candidate if there is exactly ONE.
        # Exactly one is not a preference; it is the only unambiguous answer,
        # and it is the state a newly-approved single-model medium is in.
        sole = (
            await db.execute(
                select(Model).where(
                    Model.stage == stage,
                    Model.tier.in_([tier, ModelTier.BOTH]),
                    Model.engine.in_(sorted(engines)),
                    Model.state.in_(list(_SERVABLE)),
                    Model.enabled.is_(True),
                ).order_by(Model.name)
            )
        ).scalars().unique().all()
        if len(sole) == 1:
            return _Resolved(*_ONLY_CANDIDATE_PROVENANCE, None, sole[0])
        # Two or more, or none: there is no honest answer, and inventing one is
        # what this whole change exists to stop. `_NONE_PROVENANCE` says so and
        # the picker asks the operator to choose.
        return _Resolved(*_NONE_PROVENANCE, None, None)

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
#:
#: ⛔ WP-IVGS-09b. `motion_graphics` WAS MISSING and the lookup below fell back
#: to IMAGE_GENERATION, silently. Measured live 2026-08-28 through the GUI path:
#: a scene switched to `motion_graphics` came back `stage="image_generation"`
#: with the two FLUX rows as its candidates, so `maths-motion` -- approved,
#: enabled, and the only thing that can render the scene -- could never be
#: offered. The medium had a renderer, a task, a queue and a Model Store row,
#: and the one table that decides what the picker asks about did not know it
#: existed.
MEDIA_TYPE_STAGE: dict[str, ModelStage] = {
    "image": ModelStage.IMAGE_GENERATION,
    "video_clip": ModelStage.VIDEO_GENERATION,
    "animation": ModelStage.ANIMATION_GENERATION,
    # MBCP's taxonomy, not a second opinion: WP-67 registers `maths_motion` on
    # `animation_generation` (`client_registry.py:439`) and the Model Store row
    # is `stage=animation_generation`. Motion graphics ARE animation to AD-01;
    # they are a different FAMILY of it. See MEDIA_TYPE_FAMILIES.
    "motion_graphics": ModelStage.ANIMATION_GENERATION,
}


#: ⛔ A STAGE IS NOT A MEDIUM, and on `animation_generation` two media types
#: share one stage.
#:
#: Without this, adding `motion_graphics` above would hand a motion-graphics
#: scene the Wan2.2-Animate rows -- a model that needs a person in a reference
#: still and refuses a personless one by name -- and would leave an `animation`
#: scene being offered `maths-motion`, a template renderer that cannot animate a
#: person. Measured before the fix: the `animation` picker already listed
#: `maths-motion` as SELECTABLE. That half was live before this package and is
#: closed by the same edit.
#:
#: ONLY the media types that share a stage appear here. `talking_head`,
#: `video_generation` and `voiceover_tts` also serve several families, but each
#: serves exactly ONE medium, so narrowing them would change a list nobody
#: reported and is not this fix's business. A medium absent from this map gets
#: every model on its stage, which is what it got before.
MEDIA_TYPE_FAMILIES: dict[str, frozenset[str]] = {
    "animation": frozenset({"wan_animate", "animatediff"}),
    "motion_graphics": frozenset({"maths_motion"}),
}


def stage_for_media_type(media_type: str) -> ModelStage:
    """The stage a medium dispatches to. Refuses an unknown one BY NAME.

    ⛔ THE OLD FORM WAS `MEDIA_TYPE_STAGE.get(media_type, IMAGE_GENERATION)`,
    and the default is what made this defect silent for the life of the feature:
    a medium nobody had mapped did not fail, it quietly became an image, and the
    picker confidently offered FLUX for a scene that draws arithmetic. A wrong
    answer delivered with no warning is worse than no answer -- the operator has
    nothing to notice.

    `MediaType` is a closed enum and `SceneUpdate` validates against it, so a
    value reaching here that this map does not know is a MAPPING GAP, not user
    input. It says so.
    """
    try:
        return MEDIA_TYPE_STAGE[media_type or "image"]
    except KeyError:
        raise ValueError(
            f"media_type {media_type!r} has no stage mapping. Known: "
            f"{', '.join(sorted(MEDIA_TYPE_STAGE))}. A media type that reaches "
            f"this point without a mapping is a gap in MEDIA_TYPE_STAGE, not a "
            f"bad request -- it was accepted by MediaType and by SceneUpdate."
        ) from None


def engines_for_media_type(media_type: str, stage: ModelStage) -> frozenset[str] | None:
    """Which engines may be offered for this medium, or ``None`` for "all".

    ``None`` and an empty set are DIFFERENT answers and neither is guessed:
    ``None`` means this medium does not share its stage and needs no narrowing;
    an empty set would mean the registry knows no engine for its families, which
    is a registry gap and is raised rather than silently widened to everything.
    """
    families = MEDIA_TYPE_FAMILIES.get(media_type or "image")
    if families is None:
        return None
    engines = engines_for_families(stage.value, families)
    if not engines:
        raise ValueError(
            f"media_type {media_type!r} declares families {sorted(families)} on "
            f"stage {stage.value!r} and the client registry has no engine for "
            f"any of them. Refusing to fall back to every engine on the stage: "
            f"that is how a scene gets offered a model that cannot render it."
        )
    return engines


async def scene_panel(
    db: AsyncSession,
    *,
    project_id: UUID,
    scene_id: UUID,
    media_type: str,
    tier: ModelTier,
) -> StageBindingOut:
    """Task 4's payload for one scene: its stage, its override, its inheritance."""
    stage = stage_for_media_type(media_type)
    engines = engines_for_media_type(media_type, stage)
    resolved = await resolve_binding(
        db, project_id=project_id, stage=stage, tier=tier, scene_id=scene_id,
        engines=engines,
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
        candidates=await _candidates_for(db, stage, tier, engines=engines),
    )
