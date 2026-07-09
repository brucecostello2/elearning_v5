"""AD-01.6 selection planner + Model Store service helpers (ARCH-1 T1).

Selection algorithm (AD-01.6, verbatim intent):

  1. Candidate set = models WHERE stage matches AND tier in {requested, both}
     AND state = APPROVED AND enabled AND available on >=1 node
     (model_node_availability.status = available). For non-loadable engines
     (vllm), the availability row must also have served = true.
  2. Score each candidate by matching its capability tags against the job
     capability profile (per-tag weight, default 1.0 when unset).
  3. Tie-break by node VRAM headroom (gpu_nodes on the candidate's available
     nodes), then is_default, then name (deterministic).
  4. Persist the top candidate to project_model_selections
     (selected_by='auto') with a human-readable rationale.
  5. Empty candidate set -> the (stage, tier) is_default model; if none,
     raise PlanningError (surfaced as HTTP 422 by the route).

Service-level enforcement of the PG partial-unique invariants (so SQLite
test runs behave identically):
  * set_default() clears any other is_default in the (stage, tier) scope
    in the same transaction;
  * plan/override replace the prior row for their exact scope.
"""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gpu_node import GpuNode
from shared.models.model_store import (
    CapabilityDimension,
    Model,
    ModelNodeAvailability,
    ModelStage,
    ModelState,
    ModelTier,
    NodeAvailabilityStatus,
    ProjectModelSelection,
    SelectionSource,
)


class PlanningError(Exception):
    """AD-01.6 step 5: no candidate and no default for a (stage, tier)."""

    def __init__(self, stage: ModelStage, tier: ModelTier) -> None:
        self.stage = stage
        self.tier = tier
        super().__init__(
            f"no eligible model and no is_default fallback for "
            f"stage={stage.value!r} tier={tier.value!r}"
        )


# --------------------------------------------------------------------------
# candidate gathering
# --------------------------------------------------------------------------

async def _available_nodes(
    session: AsyncSession, model: Model
) -> list[ModelNodeAvailability]:
    rows = [
        a for a in model.node_availability
        if a.status == NodeAvailabilityStatus.AVAILABLE
    ]
    if not model.dynamically_loadable:
        # AD-01.9 engine constraint: vLLM-class models must be *served*.
        rows = [a for a in rows if a.served]
    return rows


async def _candidates(
    session: AsyncSession, stage: ModelStage, tier: ModelTier
) -> list[tuple[Model, list[ModelNodeAvailability]]]:
    stmt = select(Model).where(
        Model.stage == stage,
        Model.tier.in_([tier, ModelTier.BOTH]),
        Model.state == ModelState.APPROVED,
        Model.enabled.is_(True),
    )
    models = (await session.execute(stmt)).scalars().unique().all()
    out: list[tuple[Model, list[ModelNodeAvailability]]] = []
    for m in models:
        nodes = await _available_nodes(session, m)
        if nodes:
            out.append((m, nodes))
    return out


# --------------------------------------------------------------------------
# scoring + tie-breaks
# --------------------------------------------------------------------------

def _capability_score(
    model: Model, profile: dict[CapabilityDimension, str]
) -> tuple[float, list[str]]:
    """Sum of matched-tag weights; returns (score, matched descriptions)."""
    score = 0.0
    matched: list[str] = []
    for tag in model.capability_tags:
        want = profile.get(tag.dimension)
        if want is not None and tag.value == want:
            w = float(tag.weight) if tag.weight is not None else 1.0
            score += w
            matched.append(f"{tag.dimension.value}={tag.value}")
    return score, matched


async def _node_headroom_mb(
    session: AsyncSession, nodes: Sequence[ModelNodeAvailability]
) -> int:
    """Max total VRAM across the candidate's available nodes (gpu_nodes,
    matched on hostname). 0 when unmatched — headroom then simply does not
    differentiate."""
    hostnames = [a.node_id for a in nodes]
    if not hostnames:
        return 0
    stmt = (
        select(func.coalesce(func.max(GpuNode.total_vram_mb), 0))
        .where(GpuNode.node_hostname.in_(hostnames))
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------

async def _replace_selection(
    session: AsyncSession,
    *,
    project_id: UUID,
    scene_id: UUID | None,
    stage: ModelStage,
    tier: ModelTier,
    model_id: UUID,
    selected_by: SelectionSource,
    rationale: str,
) -> ProjectModelSelection:
    """Replace-then-insert for the exact selection scope (one row per scope)."""
    scope = [
        ProjectModelSelection.project_id == project_id,
        ProjectModelSelection.stage == stage,
        ProjectModelSelection.tier == tier,
        (
            ProjectModelSelection.scene_id == scene_id
            if scene_id is not None
            else ProjectModelSelection.scene_id.is_(None)
        ),
    ]
    await session.execute(delete(ProjectModelSelection).where(*scope))
    row = ProjectModelSelection(
        project_id=project_id,
        scene_id=scene_id,
        stage=stage,
        tier=tier,
        model_id=model_id,
        selected_by=selected_by,
        rationale=rationale,
    )
    session.add(row)
    await session.flush()
    return row


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

async def plan_stage(
    session: AsyncSession,
    *,
    project_id: UUID,
    stage: ModelStage,
    tier: ModelTier,
    capability_profile: dict[CapabilityDimension, str],
) -> ProjectModelSelection:
    """AD-01.6 steps 1-5 for a single stage; persists and returns the row."""
    candidates = await _candidates(session, stage, tier)

    if candidates:
        ranked: list[tuple[float, int, bool, str, Model, list[str]]] = []
        for model, nodes in candidates:
            score, matched = _capability_score(model, capability_profile)
            headroom = await _node_headroom_mb(session, nodes)
            ranked.append(
                (score, headroom, model.is_default, model.name, model, matched)
            )
        # score desc, headroom desc, is_default first, name asc
        ranked.sort(key=lambda r: (-r[0], -r[1], not r[2], r[3]))
        score, headroom, _, _, best, matched = ranked[0]

        parts = [f"selected {best.name}"]
        parts.append(
            "capability match: " + "; ".join(matched) if matched
            else "no capability-profile match (base eligibility)"
        )
        parts.append(f"tier {tier.value}")
        nodes = await _available_nodes(session, best)
        parts.append(
            "available on " + ", ".join(sorted(a.node_id for a in nodes))
        )
        if len(ranked) > 1 and headroom:
            parts.append(f"tie-break VRAM headroom {headroom} MB")
        rationale = "; ".join(parts)

        return await _replace_selection(
            session,
            project_id=project_id,
            scene_id=None,
            stage=stage,
            tier=tier,
            model_id=best.id,
            selected_by=SelectionSource.AUTO,
            rationale=rationale,
        )

    # step 5 — is_default fallback
    default_stmt = select(Model).where(
        Model.stage == stage,
        Model.tier.in_([tier, ModelTier.BOTH]),
        Model.is_default.is_(True),
        Model.state == ModelState.APPROVED,
        Model.enabled.is_(True),
    ).limit(1)
    default = (await session.execute(default_stmt)).scalar_one_or_none()
    if default is None:
        raise PlanningError(stage, tier)
    return await _replace_selection(
        session,
        project_id=project_id,
        scene_id=None,
        stage=stage,
        tier=tier,
        model_id=default.id,
        selected_by=SelectionSource.AUTO,
        rationale=(
            f"selected {default.name}: is_default fallback — no candidate "
            f"with node availability for ({stage.value}, {tier.value})"
        ),
    )


async def plan_selections(
    session: AsyncSession,
    *,
    project_id: UUID,
    stages: Sequence[ModelStage],
    tier: ModelTier,
    capability_profile: dict[CapabilityDimension, str],
) -> list[ProjectModelSelection]:
    """Plan every requested stage; atomic — any PlanningError aborts all."""
    rows: list[ProjectModelSelection] = []
    for stage in stages:
        rows.append(
            await plan_stage(
                session,
                project_id=project_id,
                stage=stage,
                tier=tier,
                capability_profile=capability_profile,
            )
        )
    return rows


async def manual_override(
    session: AsyncSession,
    *,
    project_id: UUID,
    scene_id: UUID | None,
    stage: ModelStage,
    tier: ModelTier,
    model_id: UUID,
    rationale: str,
) -> ProjectModelSelection:
    """AD-01.8.4 — operator/admin override (selected_by='manual')."""
    model = await session.get(Model, model_id)
    if model is None:
        raise ValueError(f"model {model_id} does not exist")
    if model.state not in (ModelState.APPROVED, ModelState.DEPRECATED):
        raise ValueError(
            f"model {model.name!r} is {model.state.value} — not servable"
        )
    if model.stage != stage:
        raise ValueError(
            f"model {model.name!r} serves stage {model.stage.value!r}, "
            f"not {stage.value!r}"
        )
    return await _replace_selection(
        session,
        project_id=project_id,
        scene_id=scene_id,
        stage=stage,
        tier=tier,
        model_id=model_id,
        selected_by=SelectionSource.MANUAL,
        rationale=rationale,
    )


async def set_default(
    session: AsyncSession, *, model: Model, is_default: bool
) -> None:
    """Transactional default swap — enforces one default per (stage, tier)."""
    if is_default:
        others = (
            await session.execute(
                select(Model).where(
                    Model.stage == model.stage,
                    Model.tier == model.tier,
                    Model.id != model.id,
                    Model.is_default.is_(True),
                )
            )
        ).scalars().all()
        for other in others:
            other.is_default = False
        # Flush the clears first: the PG partial unique index
        # (uq_models_default_per_stage_tier) is non-deferrable, so a
        # single-flush swap would transiently hold two defaults.
        await session.flush()
    model.is_default = is_default
    await session.flush()
