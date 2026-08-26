"""AD-01.6 planner tests — candidate gating, scoring, tie-breaks, persistence."""
from __future__ import annotations

import uuid

import pytest
from app.models.gpu_node import GpuNode
from app.services.model_selection import (
    PlanningError,
    manual_override,
    plan_selections,
    plan_stage,
    set_default,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.model_store import (
    CapabilityDimension,
    ModelStage,
    ModelState,
    ModelTier,
    NodeAvailabilityStatus,
    ProjectModelSelection,
    SelectionSource,
)
from tests.conftest import make_model

pytestmark = pytest.mark.asyncio

CD = CapabilityDimension
NA = NodeAvailabilityStatus


async def _selections(db: AsyncSession, project_id) -> list[ProjectModelSelection]:
    stmt = select(ProjectModelSelection).where(
        ProjectModelSelection.project_id == project_id
    )
    return list((await db.execute(stmt)).scalars().all())


async def test_capability_score_picks_best_match(
    db_session, model_store_project, talking_head_store
):
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={CD.VISUAL_STYLE: "stylized"},
    )
    await db_session.commit()
    assert row.model_id == talking_head_store["sadtalker"].id
    assert row.selected_by == SelectionSource.AUTO
    assert "visual_style=stylized" in row.rationale


async def test_tag_weights_decide_between_matches(db_session, model_store_project):
    weak = make_model(
        name="weak-match",
        tags=[(CD.VISUAL_STYLE, "photorealistic", 0.3)],
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    strong = make_model(
        name="strong-match",
        tags=[(CD.VISUAL_STYLE, "photorealistic", 0.9)],
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    db_session.add_all([weak, strong])
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={CD.VISUAL_STYLE: "photorealistic"},
    )
    await db_session.commit()
    assert row.model_id == strong.id


async def test_unset_weight_defaults_to_one(db_session, model_store_project):
    unweighted = make_model(
        name="unweighted",
        tags=[(CD.VISUAL_STYLE, "photorealistic", None)],
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    weighted = make_model(
        name="weighted-lower",
        tags=[(CD.VISUAL_STYLE, "photorealistic", 0.4)],
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    db_session.add_all([unweighted, weighted])
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={CD.VISUAL_STYLE: "photorealistic"},
    )
    await db_session.commit()
    assert row.model_id == unweighted.id


async def test_vram_headroom_breaks_score_ties(db_session, model_store_project):
    small_node = make_model(
        name="on-small-node",
        nodes=[("node-05", NA.AVAILABLE, False)],
    )
    big_node = make_model(
        name="on-big-node",
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    db_session.add_all([
        small_node,
        big_node,
        GpuNode(id=uuid.uuid4(), node_hostname="node-05", gpu_index=0,
                total_vram_mb=24576),
        GpuNode(id=uuid.uuid4(), node_hostname="node-04", gpu_index=0,
                total_vram_mb=98304),
    ])
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert row.model_id == big_node.id
    assert "VRAM headroom" in row.rationale


async def test_is_default_then_name_break_remaining_ties(db_session, model_store_project):
    b_default = make_model(
        name="bbb-default", is_default=True,
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    a_plain = make_model(
        name="aaa-plain",
        nodes=[("node-04", NA.AVAILABLE, False)],
    )
    db_session.add_all([b_default, a_plain])
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert row.model_id == b_default.id  # is_default wins before name

    b_default.is_default = False
    await db_session.commit()
    row2 = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert row2.model_id == a_plain.id  # name asc when nothing else differs


async def test_candidate_gating_state_enabled_tier_availability(
    db_session, model_store_project
):
    eligible = make_model(
        name="eligible", nodes=[("node-04", NA.AVAILABLE, False)],
    )
    db_session.add_all([
        eligible,
        make_model(name="still-candidate", state=ModelState.CANDIDATE,
                   nodes=[("node-04", NA.AVAILABLE, False)]),
        make_model(name="switched-off", enabled=False,
                   nodes=[("node-04", NA.AVAILABLE, False)]),
        make_model(name="wrong-tier", tier=ModelTier.PRODUCTION,
                   nodes=[("node-04", NA.AVAILABLE, False)]),
        make_model(name="no-node", nodes=[]),
        make_model(name="node-loading",
                   nodes=[("node-04", NA.LOADING, False)]),
    ])
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert row.model_id == eligible.id


async def test_non_loadable_requires_served(db_session, model_store_project):
    not_served = make_model(
        name="vllm-not-served",
        stage=ModelStage.TRANSCRIPT_REFINEMENT,
        dynamically_loadable=False,
        nodes=[("node-02", NA.AVAILABLE, False)],
    )
    served = make_model(
        name="vllm-served",
        stage=ModelStage.TRANSCRIPT_REFINEMENT,
        dynamically_loadable=False,
        nodes=[("node-02", NA.AVAILABLE, True)],
    )
    db_session.add_all([not_served, served])
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TRANSCRIPT_REFINEMENT,
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert row.model_id == served.id


async def test_empty_candidates_fall_back_to_default(db_session, model_store_project):
    default_no_node = make_model(name="default-no-node", is_default=True, nodes=[])
    db_session.add(default_no_node)
    await db_session.commit()
    row = await plan_stage(
        db_session,
        project_id=model_store_project.id,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert row.model_id == default_no_node.id
    assert "is_default fallback" in row.rationale


async def test_planning_error_when_nothing_eligible(db_session, model_store_project):
    with pytest.raises(PlanningError):
        await plan_stage(
            db_session,
            project_id=model_store_project.id,
            stage=ModelStage.TALKING_HEAD,
            tier=ModelTier.PROTOTYPE,
            capability_profile={},
        )


async def test_replan_replaces_single_scope_row(
    db_session, model_store_project, talking_head_store
):
    for _ in range(2):
        await plan_stage(
            db_session,
            project_id=model_store_project.id,
            stage=ModelStage.TALKING_HEAD,
            tier=ModelTier.PROTOTYPE,
            capability_profile={},
        )
        await db_session.commit()
    rows = await _selections(db_session, model_store_project.id)
    assert len(rows) == 1


async def test_plan_selections_multi_stage(db_session, model_store_project, talking_head_store):
    tts = make_model(
        name="kokoro-v1",
        stage=ModelStage.VOICEOVER_TTS,
        nodes=[("node-05", NA.AVAILABLE, False)],
    )
    db_session.add(tts)
    await db_session.commit()
    rows = await plan_selections(
        db_session,
        project_id=model_store_project.id,
        stages=[ModelStage.TALKING_HEAD, ModelStage.VOICEOVER_TTS],
        tier=ModelTier.PROTOTYPE,
        capability_profile={},
    )
    await db_session.commit()
    assert {r.stage for r in rows} == {
        ModelStage.TALKING_HEAD, ModelStage.VOICEOVER_TTS,
    }


async def test_manual_override_validations(
    db_session, model_store_project, talking_head_store
):
    ok = await manual_override(
        db_session,
        project_id=model_store_project.id,
        scene_id=None,
        stage=ModelStage.TALKING_HEAD,
        tier=ModelTier.PROTOTYPE,
        model_id=talking_head_store["sadtalker"].id,
        rationale="operator prefers stylized output",
    )
    await db_session.commit()
    assert ok.selected_by == SelectionSource.MANUAL

    with pytest.raises(ValueError, match="does not exist"):
        await manual_override(
            db_session,
            project_id=model_store_project.id,
            scene_id=None,
            stage=ModelStage.TALKING_HEAD,
            tier=ModelTier.PROTOTYPE,
            model_id=uuid.uuid4(),
            rationale="x",
        )

    talking_head_store["sadtalker"].state = ModelState.RETIRED
    await db_session.commit()
    # WP-66 STRENGTHENED THIS, and did not relax it. The refusal is unchanged;
    # what changed is that it now carries a machine slug the surface switches on
    # (`SelectionRefused.reason`) and names the remedy. The old assertion could
    # only see the prose. Both are checked below: the wording AND the slug, so a
    # future reword cannot silently break the frontend's branch.
    with pytest.raises(ValueError, match="not servable") as _retired:
        await manual_override(
            db_session,
            project_id=model_store_project.id,
            scene_id=None,
            stage=ModelStage.TALKING_HEAD,
            tier=ModelTier.PROTOTYPE,
            model_id=talking_head_store["sadtalker"].id,
            rationale="x",
        )
    assert _retired.value.reason == "not_approved"
    assert "retired" in str(_retired.value)

    with pytest.raises(ValueError, match="serves stage"):
        await manual_override(
            db_session,
            project_id=model_store_project.id,
            scene_id=None,
            stage=ModelStage.VOICEOVER_TTS,
            tier=ModelTier.PROTOTYPE,
            model_id=talking_head_store["latentsync"].id,
            rationale="x",
        )


async def test_set_default_swaps_within_stage_tier(
    db_session, model_store_project, talking_head_store
):
    latentsync = talking_head_store["latentsync"]
    sadtalker = talking_head_store["sadtalker"]
    assert latentsync.is_default is True
    await set_default(db_session, model=sadtalker, is_default=True)
    await db_session.commit()
    await db_session.refresh(latentsync)
    await db_session.refresh(sadtalker)
    assert sadtalker.is_default is True
    assert latentsync.is_default is False
