"""ARCH-1 selection-aware provider factory (§19.1 / AD-01.9).

Resolution precedence (AD-01.9, AD-01.12 back-compat guarantee):

    scene-level selection row
      -> project-level selection row
        -> the ``is_default`` model for (stage, tier)
          -> SelectionError

Servability gate:
  * selection rows serve APPROVED and DEPRECATED models (AD-01.5.1:
    deprecated = "still loadable for existing jobs but not chosen for new
    ones") provided ``enabled`` is true;
  * the default fallback serves APPROVED + enabled only — a default must
    never silently resolve to a deprecated model.

``build_provider`` maps a ModelBinding to a concrete provider through the
engine-builder registry; worker packages register builders at import time
(``ivgs_workers.providers.ensure_registered``). Task code touches nothing
but this surface — no model identity is hard-coded (ARCH-1).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.providers.binding import ModelBinding, resolve_endpoint
from shared.providers.errors import (
    EngineNotRegisteredError,
    SelectionError,
    SelectionIntegrityError,
)

# A builder takes (binding, **kwargs) and returns a provider instance.
ProviderBuilder = Callable[..., Any]

_BUILDERS: dict[str, ProviderBuilder] = {}

# Lifecycle states servable through an explicit selection row (AD-01.5.1).
_SERVABLE_VIA_SELECTION = ("approved", "deprecated")


def register_engine_builder(engine: str, builder: ProviderBuilder) -> None:
    """Register (or re-register) the provider builder for ``engine``."""
    _BUILDERS[engine] = builder


def registered_engines() -> tuple[str, ...]:
    """Engines with a registered builder (test/diagnostic surface)."""
    return tuple(sorted(_BUILDERS))


async def _pick_node(session: AsyncSession, model_id: UUID) -> str | None:
    """Best available node for ``model_id`` (poller data), else None."""
    from shared.models.model_store import (
        ModelNodeAvailability,
        NodeAvailabilityStatus,
    )

    rows = (
        await session.execute(
            select(ModelNodeAvailability.node_id)
            .where(
                ModelNodeAvailability.model_id == model_id,
                ModelNodeAvailability.status == NodeAvailabilityStatus.AVAILABLE,
            )
            .order_by(ModelNodeAvailability.node_id)
        )
    ).scalars().all()
    return rows[0] if rows else None


def _binding_from_model(
    model_row: Any,
    *,
    node_id: str | None,
    tier: str,
    selection_id: UUID | None,
    selected_by: str | None,
    rationale: str,
) -> ModelBinding:
    vram_mb: int | None = None
    if model_row.vram_gb is not None:
        vram_mb = int(float(model_row.vram_gb) * 1024)
    return ModelBinding(
        model_id=model_row.id,
        name=model_row.name,
        display_name=model_row.display_name,
        stage=model_row.stage.value,
        engine=model_row.engine.value,
        tier=tier,
        endpoint=resolve_endpoint(model_row.engine.value, node_id),
        node_id=node_id,
        vram_requirement_mb=vram_mb,
        dynamically_loadable=model_row.dynamically_loadable,
        default_params=dict(model_row.default_params or {}),
        selection_id=selection_id,
        selected_by=selected_by,
        rationale=rationale,
    )


async def _get_binding_in_session(
    session: AsyncSession,
    stage: str,
    project_id: UUID,
    tier: str,
    scene_id: UUID | None,
) -> ModelBinding:
    from shared.models.model_store import (
        Model,
        ModelStage,
        ModelState,
        ModelTier,
        ProjectModelSelection,
    )

    stage_e = ModelStage(stage)
    tier_e = ModelTier(tier)

    async def _selection_row(scene: UUID | None):
        stmt = (
            select(ProjectModelSelection)
            .where(
                ProjectModelSelection.project_id == project_id,
                ProjectModelSelection.stage == stage_e,
                ProjectModelSelection.tier == tier_e,
                ProjectModelSelection.scene_id == scene
                if scene is not None
                else ProjectModelSelection.scene_id.is_(None),
            )
            .order_by(ProjectModelSelection.created_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    selection = None
    if scene_id is not None:
        selection = await _selection_row(scene_id)
    if selection is None:
        selection = await _selection_row(None)

    if selection is not None:
        model_row = await session.get(Model, selection.model_id)
        if model_row is None:
            raise SelectionIntegrityError(
                f"selection {selection.id} references a missing model"
            )
        if (
            model_row.state.value not in _SERVABLE_VIA_SELECTION
            or not model_row.enabled
        ):
            raise SelectionIntegrityError(
                f"selection {selection.id} -> model {model_row.name!r} is not "
                f"servable (state={model_row.state.value}, "
                f"enabled={model_row.enabled})"
            )
        node = await _pick_node(session, model_row.id)
        return _binding_from_model(
            model_row,
            node_id=node,
            tier=tier,
            selection_id=selection.id,
            selected_by=selection.selected_by.value,
            rationale=selection.rationale,
        )

    # AD-01.12 back-compat: no selection row -> the (stage, tier) default.
    default_stmt = (
        select(Model)
        .where(
            Model.stage == stage_e,
            Model.tier.in_([tier_e, ModelTier.BOTH]),
            Model.is_default.is_(True),
            Model.state == ModelState.APPROVED,
            Model.enabled.is_(True),
        )
        .limit(1)
    )
    default_row = (await session.execute(default_stmt)).scalar_one_or_none()
    if default_row is None:
        raise SelectionError(
            f"no selection and no enabled APPROVED default model for "
            f"stage={stage!r} tier={tier!r} (project {project_id})"
        )
    node = await _pick_node(session, default_row.id)
    return _binding_from_model(
        default_row,
        node_id=node,
        tier=tier,
        selection_id=None,
        selected_by="default",
        rationale=f"is_default fallback for ({stage}, {tier}) — no selection row",
    )


async def get_binding(
    stage: str,
    *,
    project_id: UUID,
    tier: str = "prototype",
    scene_id: UUID | None = None,
    session: AsyncSession | None = None,
) -> ModelBinding:
    """Resolve the effective ModelBinding for (stage, project[, scene], tier).

    ``session=None`` (the common Celery-task path) opens a short-lived
    resolve-only session from the shared factory.
    """
    if session is not None:
        return await _get_binding_in_session(
            session, stage, project_id, tier, scene_id
        )
    from shared.database import async_session_factory

    async with async_session_factory() as own:
        return await _get_binding_in_session(own, stage, project_id, tier, scene_id)


def build_provider(binding: ModelBinding, **kwargs: Any) -> Any:
    """Instantiate the registered provider for ``binding.engine``."""
    builder = _BUILDERS.get(binding.engine)
    if builder is None:
        raise EngineNotRegisteredError(
            f"no provider builder registered for engine {binding.engine!r} "
            f"(registered: {', '.join(registered_engines()) or 'none'})"
        )
    return builder(binding, **kwargs)


async def get_provider(
    stage: str,
    *,
    project_id: UUID,
    tier: str = "prototype",
    scene_id: UUID | None = None,
    session: AsyncSession | None = None,
    **builder_kwargs: Any,
) -> Any:
    """AD-01.9: resolve the selection and return a bound provider."""
    binding = await get_binding(
        stage, project_id=project_id, tier=tier, scene_id=scene_id, session=session
    )
    return build_provider(binding, **builder_kwargs)
