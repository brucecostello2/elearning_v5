"""ARCH-1 factory tests (DB) — resolution precedence and servability.

Runs on the API PostgreSQL harness; PG enforces the selections FKs, so the
scene-override test creates a real storyboard_scenes row.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storyboard_scene import StoryboardScene
from shared.models.model_store import (
    ModelStage,
    ModelState,
    ModelTier,
    NodeAvailabilityStatus,
    ProjectModelSelection,
    SelectionSource,
)
from shared.providers import (
    SelectionError,
    SelectionIntegrityError,
    get_binding,
)
from tests.conftest import make_model

pytestmark = pytest.mark.asyncio


async def _add_selection(
    db: AsyncSession,
    *,
    project_id,
    model_id,
    scene_id=None,
    tier=ModelTier.PROTOTYPE,
    selected_by=SelectionSource.AUTO,
    rationale="test selection",
):
    row = ProjectModelSelection(
        project_id=project_id,
        scene_id=scene_id,
        stage=ModelStage.TALKING_HEAD,
        tier=tier,
        model_id=model_id,
        selected_by=selected_by,
        rationale=rationale,
    )
    db.add(row)
    await db.commit()
    return row


async def _add_scene(db: AsyncSession, project_id, index: int = 0):
    """Persist a real scene row — PG enforces the selections scene FK."""
    scene = StoryboardScene(
        id=uuid.uuid4(),
        project_id=project_id,
        scene_index=index,
    )
    db.add(scene)
    await db.commit()
    return scene.id


async def test_project_selection_resolves(
    db_session, model_store_project, talking_head_store
):
    sel = await _add_selection(
        db_session,
        project_id=model_store_project.id,
        model_id=talking_head_store["sadtalker"].id,
    )
    binding = await get_binding(
        "talking_head",
        project_id=model_store_project.id,
        tier="prototype",
        session=db_session,
    )
    assert binding.name == "sadtalker-v2"
    assert binding.engine == "sadtalker"
    assert binding.selection_id == sel.id
    assert binding.selected_by == "auto"
    assert binding.node_id == "node-04"
    assert binding.vram_requirement_mb == 8192


async def test_scene_overrides_project(
    db_session, model_store_project, talking_head_store
):
    scene_id = await _add_scene(db_session, model_store_project.id)
    await _add_selection(
        db_session,
        project_id=model_store_project.id,
        model_id=talking_head_store["latentsync"].id,
    )
    await _add_selection(
        db_session,
        project_id=model_store_project.id,
        model_id=talking_head_store["sadtalker"].id,
        scene_id=scene_id,
        selected_by=SelectionSource.MANUAL,
    )
    project_binding = await get_binding(
        "talking_head", project_id=model_store_project.id, tier="prototype",
        session=db_session,
    )
    scene_binding = await get_binding(
        "talking_head", project_id=model_store_project.id, tier="prototype",
        scene_id=scene_id, session=db_session,
    )
    assert project_binding.name == "latentsync-1.5"
    assert scene_binding.name == "sadtalker-v2"
    assert scene_binding.selected_by == "manual"


async def test_default_fallback_when_no_selection(
    db_session, model_store_project, talking_head_store
):
    binding = await get_binding(
        "talking_head", project_id=model_store_project.id, tier="prototype",
        session=db_session,
    )
    assert binding.name == "latentsync-1.5"  # is_default
    assert binding.selected_by == "default"
    assert binding.selection_id is None
    assert "is_default fallback" in binding.rationale


async def test_no_selection_no_default_raises(db_session, model_store_project):
    with pytest.raises(SelectionError):
        await get_binding(
            "talking_head", project_id=model_store_project.id, tier="prototype",
            session=db_session,
        )


async def test_deprecated_model_serves_via_selection(
    db_session, model_store_project, talking_head_store
):
    model = talking_head_store["sadtalker"]
    await _add_selection(
        db_session, project_id=model_store_project.id, model_id=model.id,
    )
    model.state = ModelState.DEPRECATED
    await db_session.commit()
    binding = await get_binding(
        "talking_head", project_id=model_store_project.id, tier="prototype",
        session=db_session,
    )
    assert binding.name == "sadtalker-v2"


async def test_disabled_model_fails_closed(
    db_session, model_store_project, talking_head_store
):
    model = talking_head_store["sadtalker"]
    await _add_selection(
        db_session, project_id=model_store_project.id, model_id=model.id,
    )
    model.enabled = False
    await db_session.commit()
    with pytest.raises(SelectionIntegrityError):
        await get_binding(
            "talking_head", project_id=model_store_project.id, tier="prototype",
            session=db_session,
        )


async def test_retired_selection_fails_closed(
    db_session, model_store_project, talking_head_store
):
    model = talking_head_store["sadtalker"]
    await _add_selection(
        db_session, project_id=model_store_project.id, model_id=model.id,
    )
    model.state = ModelState.RETIRED
    await db_session.commit()
    with pytest.raises(SelectionIntegrityError):
        await get_binding(
            "talking_head", project_id=model_store_project.id, tier="prototype",
            session=db_session,
        )


async def test_deprecated_default_not_used_for_fallback(
    db_session, model_store_project
):
    deprecated_default = make_model(
        name="old-default",
        state=ModelState.DEPRECATED,
        is_default=True,
        nodes=[("node-04", NodeAvailabilityStatus.AVAILABLE, False)],
    )
    db_session.add(deprecated_default)
    await db_session.commit()
    with pytest.raises(SelectionError):
        await get_binding(
            "talking_head", project_id=model_store_project.id, tier="prototype",
            session=db_session,
        )


async def test_binding_without_availability_has_no_node(
    db_session, model_store_project
):
    lonely = make_model(name="no-node-model", is_default=True, nodes=[])
    db_session.add(lonely)
    await db_session.commit()
    binding = await get_binding(
        "talking_head", project_id=model_store_project.id, tier="prototype",
        session=db_session,
    )
    assert binding.node_id is None
