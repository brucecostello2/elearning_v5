"""
Storyboard scene endpoint tests: CRUD, reorder, regenerate.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSceneCRUD:
    """Test storyboard scene operations."""

    async def test_list_scenes(self, client: AsyncClient, operator_token: str, project_with_scenes: dict):
        """Test listing scenes ordered by scene_index."""
        project_id = project_with_scenes["project_id"]
        response = await client.get(
            f"/api/v1/projects/{project_id}/scenes",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        # Verify ordering
        for i in range(1, len(data)):
            assert data[i]["scene_index"] >= data[i - 1]["scene_index"]

    async def test_update_scene(self, client: AsyncClient, operator_token: str, scene_fixture: dict):
        """Test updating scene fields."""
        project_id = scene_fixture["project_id"]
        scene_id = scene_fixture["id"]
        response = await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={
                "narration_text": "Updated narration for the scene",
                "visual_description": "A modern classroom with interactive displays",
                "media_type": "image",
                "duration_seconds": 15.0,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["narration_text"] == "Updated narration for the scene"
        assert data["media_type"] == "image"
        assert data["duration_seconds"] == 15.0

    async def test_update_scene_invalid_media_type(self, client: AsyncClient, operator_token: str, scene_fixture: dict):
        """Test that invalid media_type is rejected."""
        project_id = scene_fixture["project_id"]
        scene_id = scene_fixture["id"]
        response = await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={"media_type": "invalid_type"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestSceneReorder:
    """Test scene reordering."""

    async def test_reorder_scenes(self, client: AsyncClient, operator_token: str, project_with_scenes: dict):
        """Test bulk reordering scenes."""
        project_id = project_with_scenes["project_id"]
        scenes = project_with_scenes["scenes"]

        items = [
            {"id": str(scenes[-1]["id"]), "scene_index": 1},
            {"id": str(scenes[0]["id"]), "scene_index": 2},
        ]
        if len(scenes) > 2:
            for i, s in enumerate(scenes[1:-1], start=3):
                items.append({"id": str(s["id"]), "scene_index": i})

        response = await client.post(
            f"/api/v1/projects/{project_id}/scenes/reorder",
            json={"items": items},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200

    async def test_reorder_duplicate_index_rejected(
        self, client: AsyncClient, operator_token: str, project_with_scenes: dict
    ):
        """Test that duplicate scene_index values are rejected."""
        project_id = project_with_scenes["project_id"]
        scenes = project_with_scenes["scenes"]
        items = [
            {"id": str(scenes[0]["id"]), "scene_index": 1},
            {"id": str(scenes[1]["id"]), "scene_index": 1},  # Duplicate!
        ]
        response = await client.post(
            f"/api/v1/projects/{project_id}/scenes/reorder",
            json={"items": items},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestSceneRegenerate:
    """Test scene regeneration."""

    async def test_regenerate_scene(self, client: AsyncClient, operator_token: str, scene_fixture: dict):
        """Test queuing scene regeneration creates a render job."""
        project_id = scene_fixture["project_id"]
        scene_id = scene_fixture["id"]
        response = await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["job_type"] == "storyboard_generation"
        assert data["status"] == "pending"
