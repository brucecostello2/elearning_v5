"""
Storyboard service: business logic for scene CRUD, reordering, and regeneration.

Per §5.1.4 — scenes are ordered by scene_index within a project.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storyboard_scene import StoryboardScene
from app.models.render_job import RenderJob
from app.services.regeneration import dispatch_scene_media_regeneration

logger = logging.getLogger(__name__)


class StoryboardService:
    """Business logic for storyboard scene management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_scenes(self, project_id: UUID) -> List[StoryboardScene]:
        """List all scenes for a project, ordered by scene_index."""
        result = await self.db.execute(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == project_id)
            .order_by(StoryboardScene.scene_index)
        )
        return list(result.scalars().all())

    async def get_scene(
        self, project_id: UUID, scene_id: UUID
    ) -> Optional[StoryboardScene]:
        """Get a single scene by ID within a project."""
        result = await self.db.execute(
            select(StoryboardScene).where(
                StoryboardScene.id == scene_id,
                StoryboardScene.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_scene(
        self,
        project_id: UUID,
        scene_index: int,
        narration_text: Optional[str] = None,
        visual_description: Optional[str] = None,
        media_type: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> StoryboardScene:
        """Create a new storyboard scene."""
        scene = StoryboardScene(
            project_id=project_id,
            scene_index=scene_index,
            narration_text=narration_text,
            visual_description=visual_description,
            media_type=media_type,
            duration_seconds=duration_seconds,
        )
        self.db.add(scene)
        await self.db.commit()
        await self.db.refresh(scene)
        logger.info("Scene created: id=%s project=%s index=%s", scene.id, project_id, scene_index)
        return scene

    async def update_scene(
        self,
        project_id: UUID,
        scene_id: UUID,
        narration_text: Optional[str] = None,
        visual_description: Optional[str] = None,
        media_type: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> Optional[StoryboardScene]:
        """Update scene fields."""
        scene = await self.get_scene(project_id, scene_id)
        if scene is None:
            return None

        if narration_text is not None:
            scene.narration_text = narration_text
        if visual_description is not None:
            scene.visual_description = visual_description
        if media_type is not None:
            scene.media_type = media_type
        if duration_seconds is not None:
            scene.duration_seconds = duration_seconds

        scene.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(scene)
        logger.info("Scene updated: id=%s", scene_id)
        return scene

    async def delete_scene(
        self, project_id: UUID, scene_id: UUID
    ) -> bool:
        """Delete a scene from the storyboard."""
        scene = await self.get_scene(project_id, scene_id)
        if scene is None:
            return False

        await self.db.delete(scene)
        await self.db.commit()
        logger.info("Scene deleted: id=%s from project=%s", scene_id, project_id)
        return True

    async def reorder_scenes(
        self,
        project_id: UUID,
        items: list,
    ) -> List[StoryboardScene]:
        """
        Bulk reorder scenes.

        Validates:
        - All IDs belong to the project
        - No duplicate scene_index values
        """
        existing = await self.list_scenes(project_id)
        existing_ids = {s.id for s in existing}
        request_ids = {item.id for item in items}

        if request_ids != existing_ids:
            missing = existing_ids - request_ids
            extra = request_ids - existing_ids
            errors = []
            if missing:
                errors.append(f"Missing scene IDs: {missing}")
            if extra:
                errors.append(f"Unknown scene IDs: {extra}")
            raise ValueError("; ".join(errors))

        order_map = {item.id: item.scene_index for item in items}
        for scene in existing:
            scene.scene_index = order_map[scene.id]
            scene.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        return await self.list_scenes(project_id)

    async def regenerate_scene(
        self,
        project_id: UUID,
        scene_id: UUID,
    ) -> Optional[RenderJob]:
        """Re-run this scene's media generation, from the scene's current fields.

        WP-45 Task 3, site 1 - the original WP-43 D-3 finding, and the one that
        named the whole family. This inserted a ``storyboard_generation`` job
        row, logged "Scene regeneration queued", returned 202 and dispatched
        nothing. Nine such rows are sitting ``pending`` with zero checkpoints on
        the reference project alone, two of them created 2026-08-25; nothing was
        ever going to consume them, and the progress strip read them as work in
        flight.

        Two things change besides the dispatch.

        The job_type was ``storyboard_generation``, which named the wrong work:
        pressing Regen on a scene card does not re-run the storyboard LLM, it
        re-renders that scene's media. The row now says image_generation /
        video_generation / animation_generation, matching the branch that will
        actually run, so the Jobs tab and the tracker stop mislabelling it.

        And the regeneration consumes the scene's **current** fields, as ruled.
        An operator pressing Regen has usually just edited the scene; replaying
        the arguments that produced the asset they are replacing would regenerate
        exactly what they were trying to change.
        """
        scene = await self.get_scene(project_id, scene_id)
        if scene is None:
            return None

        return await dispatch_scene_media_regeneration(
            self.db, scene, reason=f"scene_regenerate:{scene_id}",
        )
