"""Would the server still refuse this storyboard? READ ONLY — nothing dispatched."""
import asyncio, sys
from uuid import UUID
sys.path.insert(0, "/app")
from sqlalchemy import select
from shared.database import get_db_context
from app.models.storyboard_scene import StoryboardScene
from app.services.storyboard_completeness import (
    StoryboardIncomplete, refuse_if_incomplete,
)
from app.services.motion_authoring import (
    MotionAuthoringError, has_motion_spec, verify_spec_against_narration,
)

PID = UUID(sys.argv[1])

async def main():
    async with get_db_context() as db:
        rows = list((await db.scalars(
            select(StoryboardScene).where(StoryboardScene.project_id == PID)
            .order_by(StoryboardScene.scene_index))).all())
        ctx = " ".join(r.narration_text or "" for r in rows)
        # the pre-gate authoring step, asked WITHOUT writing: would it raise?
        blockers = []
        for r in rows:
            if (r.media_type or "image") != "motion_graphics":
                continue
            if not has_motion_spec(r.generation_params):
                blockers.append((r.scene_index, "no template -> would be authored"))
                continue
            try:
                verify_spec_against_narration(
                    dict(r.generation_params), r.narration_text or "",
                    context_text=ctx, scene_index=r.scene_index)
            except MotionAuthoringError as e:
                blockers.append((r.scene_index, f"contradicts -> would be re-authored: {e}"))
        print("pre-gate authoring would touch:", blockers or "NOTHING")
        try:
            assessments = refuse_if_incomplete(rows)
        except StoryboardIncomplete as e:
            print("COMPLETENESS REFUSES:", len(e.assessments))
            return
        soft = [a for a in assessments if a.severity == "flag"]
        print(f"COMPLETENESS PASSES: {len(assessments)} scenes, 0 refusals, "
              f"{len(soft)} soft flags -> approve would dispatch")
asyncio.run(main())
