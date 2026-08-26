"""Publish the amended translation prompt as version 2. WP-61 Task 3(c).

RUN INSIDE `ivgs-fastapi`:

    sudo docker exec -i ivgs-fastapi python -m app.scripts.wp61_publish_prompt

WHY THIS IS A SCRIPT AND NOT A `psql` BLOCK. The template contains `{{ }}`,
angle brackets and newlines, and dev/CLAUDE.md §5 forbids pasting those through
PuTTY. Reading it out of the image is also the only way to be sure the text
published is the text this package tested: the file is baked into the image at
build time and its sha256 is printed below.

WHAT IT REFUSES TO DO, and why each refusal matters:

  * It refuses if the template does not contain the `IVGS-TRANSLATION-FLAG:`
    marker. Publishing a prompt without the fail-and-flag contract would leave
    `TranslationService` correctly refusing every run (409), and the operator
    hunting a routing problem that is not there.
  * It refuses if there is not exactly ONE active global translation prompt to
    supersede. Zero means something has already changed underneath this; more
    than one means the prompt table has a shape this script was not written for
    and guessing which to deactivate is how the wrong one gets retired.
  * It refuses if an identical version is already published, so a second run is
    a no-op rather than a v3 that differs from v2 by nothing.

WHAT IT DOES NOT DO. It does not UPDATE or DELETE version 1. That row produced
silent in-language corrections in all four target languages on 2026-08-25 and
it stays readable, deactivated. Superseding through the table's own versioning
is the whole reason the table has a `version` column.
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select

from app.models.prompt import Prompt
from shared.database import async_session_factory

MARKER = "IVGS-TRANSLATION-FLAG:"
TEMPLATE = Path(__file__).resolve().parents[2] / "seed" / "default_prompts" / "translation.j2"

CHANGE_NOTE = (
    "WP-61 Task 3(c), RULED FAIL-AND-FLAG. Translate faithfully; never correct "
    "the source; if the translator believes the source contains a factual "
    "error, append exactly one machine-readable "
    f"'{MARKER} <reason>' line AFTER the translation. The consuming path strips "
    "the marker from the deliverable and sets the variant to 'flagged' rather "
    "than 'completed'. Supersedes v1, under which Qwen appended a correction "
    "in ALL FOUR target languages on 2026-08-25 because the reference "
    "project's scene 5 narration genuinely teaches 10x3=30, 10x2=20 => '320' "
    "written as 230 - a divergence that would exist only in languages the team "
    "cannot read."
)


def _fail(message: str) -> None:
    print(f"REFUSED: {message}")
    print("Nothing was written.")
    sys.exit(1)


async def main() -> None:
    if not TEMPLATE.exists():
        _fail(f"template not found in the image at {TEMPLATE}")

    text = TEMPLATE.read_text(encoding="utf-8").strip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"template : {TEMPLATE}")
    print(f"sha256   : {digest}")
    print(f"bytes    : {len(text)}")

    if MARKER not in text:
        _fail(
            f"the template does not contain {MARKER!r}. Publishing it would "
            "leave TranslationService refusing every run, which is correct "
            "behaviour for the wrong reason."
        )
    if "NEVER correct the source" not in text:
        _fail(
            "the template does not forbid correcting the source. The marker "
            "alone is not the contract."
        )
    print(f"contract : OK ({MARKER} present, correction forbidden)")
    print()

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Prompt)
                .where(
                    Prompt.prompt_type == "translation",
                    Prompt.project_id.is_(None),
                    Prompt.scene_id.is_(None),
                )
                .order_by(Prompt.version)
            )
        ).scalars().all()

        print("BEFORE:")
        for r in rows:
            print(f"  {r.id}  v{r.version}  active={r.is_active}  {r.created_at}")
        print()

        active = [r for r in rows if r.is_active]
        if len(active) != 1:
            _fail(
                f"expected exactly 1 active global translation prompt, found "
                f"{len(active)}. Deciding which to retire is not this script's "
                "call."
            )

        current = active[0]
        if current.prompt_text.strip() == text:
            print(
                "The active prompt is ALREADY this exact text. Nothing to do; "
                "a second run must not create a version that differs by nothing."
            )
            return

        next_version = max((r.version for r in rows), default=0) + 1

        current.is_active = False
        published = Prompt(
            prompt_type="translation",
            prompt_text=text,
            version=next_version,
            is_active=True,
            project_id=None,
            scene_id=None,
            created_by="system",
            change_note=CHANGE_NOTE,
        )
        db.add(published)
        await db.commit()
        await db.refresh(published)

        print(f"v{current.version} -> is_active false  ({current.id})")
        print(f"v{next_version} inserted             ({published.id})")
        print()

        rows = (
            await db.execute(
                select(Prompt)
                .where(
                    Prompt.prompt_type == "translation",
                    Prompt.project_id.is_(None),
                    Prompt.scene_id.is_(None),
                )
                .order_by(Prompt.version)
            )
        ).scalars().all()
        print("AFTER:")
        for r in rows:
            print(f"  {r.id}  v{r.version}  active={r.is_active}  {r.created_at}")


if __name__ == "__main__":
    asyncio.run(main())
