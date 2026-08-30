"""RC-S2 — the fidelity loophole, calibrated; and this regen's inputs. READ ONLY."""
import asyncio, sys, json
from collections import Counter
from uuid import UUID
sys.path.insert(0, "/app")
from sqlalchemy import select
from shared.database import get_db_context
from app.models.design_brief import StoryboardDesignBrief
from app.models.transcript import Transcript
from app.services.design_review import HARD_GAP_CHARS, MIN_GAP_CHARS

PID = UUID("680d9e4c-608b-488a-9270-9b4317a7f693")

def gaps(scene_designs, dropped, source_text):
    spans = []
    for s in scene_designs:
        for ref in (s.get("source_refs") or []):
            if isinstance(ref, dict):
                spans.append((int(ref.get("start") or 0), int(ref.get("end") or 0)))
    drop_spans = []
    for b in dropped:
        sp = b.get("span") if isinstance(b, dict) else None
        if isinstance(sp, dict):
            drop_spans.append((int(sp.get("start") or 0), int(sp.get("end") or 0)))
    merged = []
    for a, b in sorted((max(0, x), min(len(source_text), y))
                       for x, y in spans + drop_spans if y > x):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out, cursor = [], 0
    for a, b in merged + [[len(source_text), len(source_text)]]:
        if a - cursor >= MIN_GAP_CHARS:
            out.append((cursor, a, a - cursor))
        cursor = max(cursor, b)
    covered = sum(b - a for a, b in merged)
    return out, covered, len(spans), len(drop_spans)

async def main():
    async with get_db_context() as db:
        trs = list((await db.scalars(select(Transcript)
                    .where(Transcript.project_id == PID)
                    .order_by(Transcript.sequence_order))).all())
        src = "\n\n".join(t.source_text or "" for t in trs).strip()
        print(f"uploaded script: {len(src)} chars\n")
        briefs = list((await db.scalars(select(StoryboardDesignBrief)
                        .where(StoryboardDesignBrief.project_id == PID)
                        .order_by(StoryboardDesignBrief.created_at))).all())
        for label, b in zip(("WATCH-1 design (19 scenes)", "WATCH-2 regen (17 scenes)"), briefs):
            sd = b.scene_designs or []
            dropped = b.dropped_beats or []
            g, covered, nrefs, ndrops = gaps(sd, dropped, src)
            print(f"=== {label}  brief {str(b.id)[:8]} active={b.is_active} ===")
            print(f"  source_refs on scenes: {nrefs} | declared drops: {ndrops}")
            print(f"  covered {covered}/{len(src)} chars "
                  f"({100.0*covered/max(1,len(src)):.1f}%)")
            for a, bb, n in g:
                over = "OVER-THRESHOLD" if n >= HARD_GAP_CHARS else "under"
                print(f"    gap {a}..{bb} = {n} chars [{over}]  "
                      f"{src[a:bb].strip()[:70]!r}")
            big = [x for x in g if x[2] >= HARD_GAP_CHARS]
            old_hard = [x for x in big if not dropped]
            print(f"  OLD RULE (gap>=400 AND dropped_beats empty): "
                  f"{len(old_hard)} refusal(s)")
            print(f"  NEW RULE (every uncovered span>=400 refuses): "
                  f"{len(big)} refusal(s)")
            print(f"  origins: {dict(Counter(s.get('scene_origin') for s in sd))}")
            print(f"  events : {dict(Counter(s.get('instructional_event') for s in sd))}")
            print(f"  model={b.model_used} fingerprint={b.prompt_fingerprint}")
            rc = b.raw_contract or {}
            print(f"  raw_contract top-level keys: {sorted(rc.keys())[:12]}")
            for k in ("usage", "prompt_tokens", "_usage", "tokens"):
                if k in rc: print(f"    {k}: {rc[k]}")
            print()
asyncio.run(main())
