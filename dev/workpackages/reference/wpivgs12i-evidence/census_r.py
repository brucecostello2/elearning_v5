"""Measure the live project's completeness refusals, by kind. READ ONLY."""
import asyncio, os, sys, json
from uuid import UUID
sys.path.insert(0, "/app")
from sqlalchemy import select
from shared.database import get_db_context
from app.models.storyboard_scene import StoryboardScene
from app.services.storyboard_completeness import assess_storyboard

PID = UUID(sys.argv[1])

async def main():
    async with get_db_context() as db:
        rows = list((await db.scalars(
            select(StoryboardScene).where(StoryboardScene.project_id == PID)
            .order_by(StoryboardScene.scene_index)
        )).all())
        for authoring in (True, False):
            out = assess_storyboard(rows, authoring_will_run=authoring)
            ref = [a for a in out if a.severity == "refuse"]
            flg = [a for a in out if a.severity == "flag"]
            print(f"=== authoring_will_run={authoring}: {len(rows)} scenes, "
                  f"{len(ref)} refuse, {len(flg)} flag ===")
            for a in out:
                if a.severity == "refuse":
                    print(f"  R scene {a.scene_index} [{a.media_type}] {a.reason[:150]}")
            print()
asyncio.run(main())
