"""
Seed default global prompts from template files.

Reads .j2 files from /ivgs/ivgs-api/seed/default_prompts/ and creates
global prompt records (project_id=NULL, scene_id=NULL) for all 10 types.

Usage:
    docker-compose exec api python -m app.scripts.seed_prompts
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.database import async_session_factory
from shared.logging_config import setup_logging

setup_logging(service_name="seed-prompts")
logger = logging.getLogger(__name__)

# Mapping of prompt type to template filename
PROMPT_TEMPLATES = {
    "master": "master.j2",
    "transcript_refinement": "transcript_refinement.j2",
    "storyboard_generation": "storyboard_generation.j2",
    "image_generation": "image_generation.j2",
    "video_generation": "video_generation.j2",
    "animation_generation": "animation_generation.j2",
    "tts_voice": "tts_voice.j2",
    "talking_head": "talking_head.j2",
    "composition": "composition.j2",
    "translation": "translation.j2",
}

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "default_prompts"


async def seed_prompts() -> None:
    """Seed default global prompts from template files."""
    from sqlalchemy import select
    from app.models.prompt import Prompt

    async with async_session_factory() as db:
        seeded = 0
        skipped = 0

        for prompt_type, filename in PROMPT_TEMPLATES.items():
            # Check if a global prompt already exists for this type
            existing = await db.execute(
                select(Prompt).where(
                    Prompt.prompt_type == prompt_type,
                    Prompt.project_id.is_(None),
                    Prompt.scene_id.is_(None),
                    Prompt.is_active.is_(True),
                )
            )
            if existing.scalar_one_or_none():
                logger.info(f"Skipping {prompt_type}: active global prompt already exists")
                skipped += 1
                continue

            # Read template file
            template_path = SEED_DIR / filename
            if not template_path.exists():
                logger.warning(f"Template file not found: {template_path}")
                continue

            prompt_text = template_path.read_text(encoding="utf-8").strip()

            # Create prompt record
            prompt = Prompt(
                project_id=None,
                scene_id=None,
                prompt_type=prompt_type,
                prompt_text=prompt_text,
                version=1,
                is_active=True,
                created_by="system",
                change_note="Default global prompt — seeded at installation",
            )
            db.add(prompt)
            seeded += 1
            logger.info(f"Seeded global prompt: {prompt_type} (v1)")

        await db.commit()
        logger.info(f"Prompt seeding complete: {seeded} created, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(seed_prompts())
