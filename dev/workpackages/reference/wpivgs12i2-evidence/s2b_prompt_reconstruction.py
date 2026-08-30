"""RC-S2(b) — reconstruct call 1's prompt exactly as the regen built it. READ ONLY."""
import sys, json, urllib.request
sys.path[:0] = ["/app", "/app/ivgs-workers"]
import asyncio
from sqlalchemy import select
from shared.database import get_db_context
from app.models.transcript import Transcript
from app.models.project import Project
from uuid import UUID
from jinja2 import BaseLoader, Environment

PID = UUID("680d9e4c-608b-488a-9270-9b4317a7f693")
SEED = "/app/seed/default_prompts"

async def main():
    async with get_db_context() as db:
        trs = list((await db.scalars(select(Transcript)
                    .where(Transcript.project_id == PID)
                    .order_by(Transcript.sequence_order))).all())
        proj = await db.scalar(select(Project).where(Project.id == PID))
    combined = "\n\n".join(f"[Segment {t.sequence_order}]\n{t.refined_text}" for t in trs)
    print("combined_transcript chars:", len(combined))
    print("script present in it:", "How to Multiply Double-Digit Numbers" in combined,
          "| Step 4 present:", "Step 4" in combined)
    import os
    for name in sorted(os.listdir(SEED)):
        print("  seed prompt:", name)
    env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
    sysp = open(f"{SEED}/storyboard_design_system.j2").read()
    userp = open(f"{SEED}/storyboard_design_user.j2").read() if os.path.exists(
        f"{SEED}/storyboard_design_user.j2") else None
    print("system prompt chars:", len(sysp))
    print("user template found:", userp is not None)
asyncio.run(main())
