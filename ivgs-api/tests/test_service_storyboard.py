"""
Phase 4 — Storyboard Service Unit Tests.

Tests business logic in app/services/storyboard_service.py:
  - create_scene: with optional fields
  - list_scenes: ordered by scene_index
  - update_scene: partial update
  - delete_scene
  - reorder_scenes: validation (missing/extra IDs)
"""

import pytest
from uuid import uuid4

from app.services.storyboard_service import StoryboardService

pytestmark = pytest.mark.asyncio


class TestCreateScene:
    async def test_create_scene_minimal(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        scene = await svc.create_scene(project_id, scene_index=0)
        assert scene is not None
        assert scene.scene_index == 0
        assert str(scene.project_id) == project_id

    async def test_create_scene_with_all_fields(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        scene = await svc.create_scene(
            project_id,
            scene_index=1,
            narration_text="Hello world",
            visual_description="A beautiful sunset",
            media_type="image",
            duration_seconds=5.0,
        )
        assert scene.narration_text == "Hello world"
        assert scene.visual_description == "A beautiful sunset"
        assert scene.duration_seconds == 5.0


class TestListScenes:
    async def test_list_scenes_empty(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        scenes = await svc.list_scenes(project_id)
        assert isinstance(scenes, list)

    async def test_list_scenes_ordered_by_index(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        await svc.create_scene(project_id, scene_index=2)
        await svc.create_scene(project_id, scene_index=0)
        await svc.create_scene(project_id, scene_index=1)
        scenes = await svc.list_scenes(project_id)
        indices = [s.scene_index for s in scenes]
        assert indices == sorted(indices)


class TestUpdateScene:
    async def test_update_narration(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        scene = await svc.create_scene(project_id, scene_index=0, narration_text="old")
        updated = await svc.update_scene(project_id, scene.id, narration_text="new")
        assert updated is not None
        assert updated.narration_text == "new"

    async def test_update_nonexistent_scene(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        result = await svc.update_scene(project_id, uuid4(), narration_text="test")
        assert result is None


class TestDeleteScene:
    async def test_delete_scene_success(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        scene = await svc.create_scene(project_id, scene_index=0)
        result = await svc.delete_scene(project_id, scene.id)
        assert result is True

    async def test_delete_nonexistent_scene(self, db_session, project_id: str):
        svc = StoryboardService(db_session)
        result = await svc.delete_scene(project_id, uuid4())
        assert result is False


class TestReorderScenes:
    async def test_reorder_valid(self, db_session, project_id: str):
        from app.schemas.storyboard import SceneReorderItem
        svc = StoryboardService(db_session)
        s0 = await svc.create_scene(project_id, scene_index=1)
        s1 = await svc.create_scene(project_id, scene_index=2)
        s2 = await svc.create_scene(project_id, scene_index=3)
        
        # Reverse order
        reorder_items = [
            SceneReorderItem(id=s2.id, scene_index=1),
            SceneReorderItem(id=s1.id, scene_index=2),
            SceneReorderItem(id=s0.id, scene_index=3),
        ]
        result = await svc.reorder_scenes(project_id, reorder_items)
        assert len(result) == 3

    async def test_reorder_with_missing_scene_raises(self, db_session, project_id: str):
        from app.schemas.storyboard import SceneReorderItem
        svc = StoryboardService(db_session)
        await svc.create_scene(project_id, scene_index=1)
        
        with pytest.raises((ValueError, Exception)):
            await svc.reorder_scenes(project_id, [
                SceneReorderItem(id=uuid4(), scene_index=1),
            ])
