"""
Storyboard service: business logic for scene CRUD, reordering, and regeneration.

Per §5.1.4 — scenes are ordered by scene_index within a project.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storyboard_scene import StoryboardScene
from app.services.design_brief_service import SCENE_DESIGN_FIELDS
from app.models.render_job import RenderJob
from app.services.regeneration import (
    RegenerationError,
    dispatch_scene_media_regeneration,
    dispatch_scene_media_regenerations,
)

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
        camera_angle: Optional[str] = None,
        transition_type: Optional[str] = None,
        effects: Optional[List[str]] = None,
        timing_offset_ms: Optional[int] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        media_rationale: Optional[str] = None,
        text_carried_by: Optional[str] = None,
        design: Optional[Dict[str, Any]] = None,
    ) -> StoryboardScene:
        """Create or REPLACE the scene at this index (WP-43 D-2 fields included).

        WP-63 Task 8. THIS INSERTED UNCONDITIONALLY, AND THAT MADE A STORYBOARD
        RE-RUN IMPOSSIBLE. Stage 2 POSTs one of these per scene and its own code
        says what it expected: *"Try POST to create; if scenes already exist,
        try PATCH"*, with a branch on 409 (`stage2_storyboard.py:452`). No 409
        was ever returned, so a second Stage-2 run over a 9-scene project left
        18 rows -- two scenes at every index, the storyboard fingerprint
        meaningless, and the media dispatch fanning out over both copies.

        Nothing had noticed because nothing had ever re-run Stage 2 on a project
        that already had scenes. WP-63 Task 8 makes the gate's `regenerate`
        decision do exactly that, so it had to be true before that could ship.

        THE ROW IS UPDATED IN PLACE, NOT DELETED AND RECREATED, and the id is
        what matters: `assets.scene_id`, `asset_quality_scores` through them and
        every language variant hang off it. Recreating would orphan the six good
        images this package's recovery depends on. Updating also moves
        `updated_at`, which moves the storyboard fingerprint, which re-opens the
        review gate on the new artifact -- which is the behaviour Task 8 wants
        and it comes for free from WP-62's mechanism.

        A LIMITATION, STATED RATHER THAN HIDDEN: a re-run that produces FEWER
        scenes than the project already has leaves the surplus rows behind. This
        method sees one scene at a time and cannot know the new total. It is
        logged (`scene_upsert`) so the count is visible in the run's log, and
        the gate re-opens either way, so the operator reviews what is actually
        there. Trimming needs the whole-storyboard write that Stage 2 does not
        make; ledgered for the Temporal cutover.
        """
        existing = await self.db.scalar(
            select(StoryboardScene).where(
                StoryboardScene.project_id == project_id,
                StoryboardScene.scene_index == scene_index,
            )
        )
        fields = {
            "narration_text": narration_text,
            "visual_description": visual_description,
            "media_type": media_type,
            "duration_seconds": duration_seconds,
            "camera_angle": camera_angle,
            "transition_type": transition_type,
            "effects": effects,
            "timing_offset_ms": timing_offset_ms,
            "generation_params": generation_params,
            # WP-IVGS-10 (migration 0045). v7's per-scene content contract.
            "media_rationale": media_rationale,
            "text_carried_by": text_carried_by,
        }

        # ── WP-IVGS-12: the scene carries its design declarations FROM BIRTH ──
        #
        # The Design Contract reaches the API BEFORE any scene row exists —
        # `design_core.capture` flushes it the moment the model's response is
        # parsed, because `_save_storyboard_scenes` swallows a non-2xx and a
        # brief written first survives scenes that never land. So the
        # declarations for THIS scene are looked up off the active brief by
        # scene_index as the scene arrives, rather than back-filled afterwards.
        #
        # ⛳ NOT AN OPTIMISATION — A CORRECTNESS POINT. The frozen stage body
        # dispatches `handle_stage_completion` immediately after the last scene
        # POSTs, and that opens the review gate. A back-fill racing that
        # dispatch would show the operator a gate with no design on it, some of
        # the time, which is worse than never having one.
        #
        # Silent and free when there is no brief: pre-v8 storyboards get {}.
        from app.services.design_brief_service import DesignBriefService

        pending = await DesignBriefService(self.db).pending_design_for(
            project_id, scene_index,
        )
        fields.update(pending)
        # An explicit `design=` from the caller WINS over the brief: the gate's
        # editor and any future whole-storyboard write are correcting what the
        # brief said, and a lookup that overrode them would silently undo the
        # reviewer.
        for name, value in (design or {}).items():
            if name in SCENE_DESIGN_FIELDS and value is not None:
                fields[name] = value

        if existing is not None:
            for name, value in fields.items():
                setattr(existing, name, value)
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            logger.info(
                "scene_upsert: REPLACED id=%s project=%s index=%s "
                "(a storyboard re-run; the scene id is preserved so its assets "
                "stay attached)",
                existing.id, project_id, scene_index,
            )
            return existing

        scene = StoryboardScene(
            project_id=project_id,
            scene_index=scene_index,
            **fields,
        )
        self.db.add(scene)
        await self.db.commit()
        await self.db.refresh(scene)
        logger.info("Scene created: id=%s project=%s index=%s", scene.id, project_id, scene_index)
        return scene

    # WP-45 Task 6(d) / WP-43 D-2. The five fields the Edit Scene modal has
    # always sent and this service never had columns for. Listed once so the
    # loop below and the route cannot drift out of step with each other.
    OPTIONAL_SCENE_FIELDS = (
        "narration_text",
        "visual_description",
        "media_type",
        "duration_seconds",
        "camera_angle",
        "transition_type",
        "effects",
        "timing_offset_ms",
        "generation_params",
        # WP-IVGS-10. v7's declarations are editable at the gate for the same
        # reason every other scene field is: the reviewer is the judge, and a
        # reviewer who can see a flag but not answer it has been shown a
        # problem and denied the fix.
        "media_rationale",
        "text_carried_by",
        # WP-IVGS-12. The Design Contract's declarations are editable at the
        # gate for exactly the reason the v7 pair are: the reviewer is the
        # judge. A reviewer who can see "scene 7 serves no outcome" and cannot
        # answer it has been shown a problem and denied the fix.
        "serves_outcomes",
        "instructional_event",
        "bloom_level",
        "source_refs",
        "scene_origin",
        "rewrite_of",
        "signal_spec",
    )

    async def update_scene(
        self,
        project_id: UUID,
        scene_id: UUID,
        **fields: Any,
    ) -> Optional[StoryboardScene]:
        """Update scene fields. Only keys present in ``fields`` are written.

        WP-45 Task 6(d). Takes the caller's **set** fields rather than a fixed
        signature of Optionals, so that clearing a field is expressible. Under
        the old shape ``None`` meant "not supplied", which made
        ``camera_angle: null`` - the way a modal says "I removed this" -
        indistinguishable from not mentioning it at all.
        """
        scene = await self.get_scene(project_id, scene_id)
        if scene is None:
            return None

        unknown = set(fields) - set(self.OPTIONAL_SCENE_FIELDS)
        if unknown:
            # Loudly, because this whole package exists because a schema
            # dropping fields in silence looked exactly like saving them.
            raise ValueError(
                f"Unknown scene field(s): {', '.join(sorted(unknown))}. "
                f"Updatable: {', '.join(self.OPTIONAL_SCENE_FIELDS)}"
            )

        for field, value in fields.items():
            setattr(scene, field, value)

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

    async def regenerate_scenes(
        self,
        project_id: UUID,
        scene_ids: Sequence[UUID],
    ) -> RenderJob:
        """Re-run several scenes' media generation in ONE dispatch.

        WP-63 Task 7. The bulk surface ("Regenerate Selected") has posted to a
        route that did not exist since WP-38; this is its service half.

        It is not a loop over ``regenerate_scene``, and that is not tidiness.
        The first single-scene dispatch leaves a `running` job on the project,
        so the second call would hit WP-62's in-flight guard and 409 -- and the
        media join is armed once per job, so N jobs against one project is the
        stranding shape WP-06 exists to prevent. One job, N scenes, one join.

        Raises ``RegenerationError`` naming every id that is not a scene of
        this project. A partial batch is refused rather than silently trimmed:
        an operator who selected six scenes and got four regenerated has no way
        to find out which two were dropped.
        """
        found = list(
            (
                await self.db.scalars(
                    select(StoryboardScene).where(
                        StoryboardScene.project_id == project_id,
                        StoryboardScene.id.in_(list(scene_ids)),
                    )
                )
            ).all()
        )
        missing = sorted(
            {str(sid) for sid in scene_ids} - {str(s.id) for s in found}
        )
        if missing:
            raise RegenerationError(
                f"{len(missing)} of the {len(set(scene_ids))} requested scenes "
                f"do not belong to project {project_id}: {', '.join(missing)}. "
                "Nothing was dispatched."
            )

        found.sort(key=lambda s: s.scene_index)
        return await dispatch_scene_media_regenerations(
            self.db,
            found,
            reason=(
                "scene_batch_regenerate:"
                + ",".join(str(s.scene_index) for s in found)
            ),
        )
