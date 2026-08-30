"""RC-S4 — calibrate the equation lint on the operator's script and both designs."""
import asyncio, sys
from uuid import UUID
sys.path.insert(0, "/app")
from sqlalchemy import select
from shared.database import get_db_context
from app.models.storyboard_scene import StoryboardScene
from app.models.transcript import Transcript
from app.models.design_brief import StoryboardDesignBrief
from shared.design.equations import parse_claims, false_claims, lint_scenes

PID = UUID("680d9e4c-608b-488a-9270-9b4317a7f693")

async def main():
    async with get_db_context() as db:
        t = await db.scalar(select(Transcript).where(Transcript.project_id == PID))
        src = t.source_text or ""
        claims = parse_claims(src)
        false_ = false_claims(src)
        print(f"UPLOADED SCRIPT ({len(src)} chars): {len(claims)} complete claims, "
              f"{len(false_)} FALSE")
        for c in claims:
            print(f"   {'OK ' if c.is_true else 'BAD'} {c.text.strip()!r}")
        print()
        rows = list((await db.scalars(select(StoryboardScene)
                     .where(StoryboardScene.project_id == PID)
                     .order_by(StoryboardScene.scene_index))).all())
        bad = lint_scenes(rows)
        print(f"LIVE ROWS (19 scenes, the regen + 2 stale): {len(bad)} FALSE claim(s)")
        for b in bad:
            print("  ", b["scene_index"], b["message"])
        total = sum(len(parse_claims(r.narration_text)) for r in rows)
        print(f"   ({total} complete claims parsed across all 19 narrations)")
        print()
        briefs = list((await db.scalars(select(StoryboardDesignBrief)
                        .where(StoryboardDesignBrief.project_id == PID)
                        .order_by(StoryboardDesignBrief.created_at))).all())
        for label, b in zip(("WATCH-1 design", "WATCH-2 regen"), briefs):
            sd = b.scene_designs or []
            bad = lint_scenes(sd)
            n = sum(len(parse_claims(s.get("narration_text"))) for s in sd)
            print(f"{label}: {n} complete claims, {len(bad)} FALSE")
            for x in bad:
                print("   ", x["scene_index"], x["message"])
asyncio.run(main())
