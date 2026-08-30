"""The live project's DESIGN review findings, by code. READ ONLY."""
import asyncio, sys
from collections import Counter
from uuid import UUID
sys.path.insert(0, "/app")
from sqlalchemy import select
from shared.database import get_db_context
from app.models.storyboard_scene import StoryboardScene
from app.models.transcript import Transcript
from app.models.project import Project
from app.services.design_brief_service import DesignBriefService
from app.services.design_review import review, split

PID = UUID(sys.argv[1])

async def main():
    async with get_db_context() as db:
        brief = await DesignBriefService(db).get_active(PID)
        print("has_brief:", brief is not None,
              "contract:", getattr(brief, "contract_version", None))
        scenes = list((await db.scalars(
            select(StoryboardScene).where(StoryboardScene.project_id == PID)
            .order_by(StoryboardScene.scene_index))).all())
        trs = list((await db.scalars(
            select(Transcript).where(Transcript.project_id == PID)
            .order_by(Transcript.sequence_order))).all())
        src = "\n\n".join(t.source_text or "" for t in trs).strip()
        proj = await db.scalar(select(Project).where(Project.id == PID))
        if brief is None:
            return
        findings, rows = review(
            scenes=scenes, outcomes=brief.outcomes or [],
            assessment_plan=brief.assessment_plan or {},
            dropped_beats=brief.dropped_beats or [],
            source_text=src,
            learning_outcomes=getattr(proj, "learning_outcomes", "") or "",
        )
        ref, flg = split(findings)
        print(f"design review: {len(ref)} refusals, {len(flg)} flags")
        print("REFUSE:", dict(Counter(f.code for f in ref)))
        print("FLAG  :", dict(Counter(f.code for f in flg)))
        print("max_runtime:", getattr(proj, "max_duration_seconds", None) or getattr(proj, "max_runtime", None))
        print("scene duration total:", sum((s.duration_seconds or 0) for s in scenes))
asyncio.run(main())
