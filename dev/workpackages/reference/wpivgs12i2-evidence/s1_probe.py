"""RC-S1 — where did the second LO-3 assessment come from? READ ONLY."""
import asyncio, sys, json
from uuid import UUID
sys.path.insert(0, "/app")
from sqlalchemy import select
from shared.database import get_db_context
from app.models.storyboard_scene import StoryboardScene
from app.models.design_brief import StoryboardDesignBrief

PID = UUID("680d9e4c-608b-488a-9270-9b4317a7f693")

async def main():
    async with get_db_context() as db:
        briefs = list((await db.scalars(
            select(StoryboardDesignBrief)
            .where(StoryboardDesignBrief.project_id == PID)
            .order_by(StoryboardDesignBrief.created_at))).all())
        for b in briefs:
            sd = b.scene_designs or []
            idx = sorted(d.get("scene_index") for d in sd if d.get("scene_index") is not None)
            print(f"brief {str(b.id)[:8]} active={b.is_active} created={b.created_at} "
                  f"designs={len(sd)} indices={idx}")
            assess = {}
            for d in sd:
                if d.get("instructional_event") == "assess":
                    for lo in (d.get("serves_outcomes") or []):
                        assess.setdefault(lo, []).append(d.get("scene_index"))
            print("   assess-by-LO in THIS CONTRACT:", assess)
        rows = list((await db.scalars(
            select(StoryboardScene).where(StoryboardScene.project_id == PID)
            .order_by(StoryboardScene.scene_index))).all())
        print(f"\nscene ROWS in the database: {len(rows)}  indices "
              f"{[r.scene_index for r in rows]}")
        active = briefs[-1]
        designed = {d.get("scene_index") for d in (active.scene_designs or [])}
        orphans = [r.scene_index for r in rows if r.scene_index not in designed]
        print("indices in the ACTIVE contract:", sorted(designed))
        print("ROWS WITH NO ENTRY IN THE ACTIVE CONTRACT:", orphans)
        prev = briefs[0]
        prev_by_idx = {d.get("scene_index"): d for d in (prev.scene_designs or [])}
        for i in orphans:
            row = next(r for r in rows if r.scene_index == i)
            p = prev_by_idx.get(i, {})
            print(f"\n  orphan scene {i}: updated_at={row.updated_at}")
            print(f"    row narration : {(row.narration_text or '')[:90]!r}")
            print(f"    PREVIOUS contract's scene {i} narration: "
                  f"{(p.get('narration_text') or '')[:90]!r}")
            print(f"    row event={row.instructional_event} serves={row.serves_outcomes} "
                  f"origin={row.scene_origin}")
        print("\nrow updated_at by index:")
        for r in rows:
            print(f"  {r.scene_index:>2} {r.updated_at}  ev={r.instructional_event}")
asyncio.run(main())
