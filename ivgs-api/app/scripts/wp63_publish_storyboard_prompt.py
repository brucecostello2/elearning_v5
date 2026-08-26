"""Publish the tracked storyboard template as the next prompt version.

WP-63 Task 9, RULED: prompt work now, THE MODEL DOES NOT MOVE off Llama.

This is the same versioning path `wp61_publish_prompt.py` uses for the
translation prompt — current version preserved inactive, next version inserted
active, change note recorded on the row — pointed at
``storyboard_generation``. It is a SEPARATE script rather than a parameter on
that one because its refusals are different: the translation publisher gates on
the fail-and-flag contract, and this one gates on the binding contract below.
A shared publisher would either lose both sets of gates or grow a `if
prompt_type ==` ladder, and the gates are the point.

RUN INSIDE `ivgs-fastapi`:

    sudo docker exec -i ivgs-fastapi python -m app.scripts.wp63_publish_storyboard_prompt

WHY THIS IS DATA AND NOT A MODEL CHANGE. The conformance baseline
(`reference-run-2026-08-23`) replays banked artefacts, not the active prompt
row, so publishing here cannot move the AD-05 diff. Stage 2 stays on Llama, as
`docs/reference-run-2026-08-23-correctness-annotation.md` §2 requires until
M3.3. Versioned and reversible: v3 stays readable, deactivated, and a rollback
is one UPDATE of `is_active`.

WHAT IT REFUSES TO DO:

  * It refuses if the template does not state the RULE 5 binding contract. A
    storyboard prompt that asks for "detailed" visuals without binding each one
    to its own scene's step reproduces exactly the measured defect — and would
    publish cleanly, run cleanly, and look fine.
  * It refuses if the template has lost RULE 1's no-text-in-the-visual rule.
    RULE 5 and RULE 1 pull against each other and RULE 1 wins on the digits:
    a prompt that asks for the numbers to be DRAWN gets "2? x 23.14", measured
    twice on this pipeline. The binding is to the board STATE and the STEP.
  * It refuses if there is not exactly ONE active global storyboard prompt to
    supersede.
  * It refuses if an identical version is already published, so a second run is
    a no-op rather than a version that differs from its predecessor by nothing.

WHAT IT DOES NOT DO. It does not UPDATE or DELETE v1, v2 or v3.
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select

from app.models.prompt import Prompt
from shared.database import async_session_factory

PROMPT_TYPE = "storyboard_generation"
TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "seed"
    / "default_prompts"
    / "storyboard_generation.j2"
)

CHANGE_NOTE = (
    "WP-63 Task 9, RULED (prompt work now; the model stays on Llama). v4 binds "
    "every scene's visual_description to THAT scene's instructional content. "
    "MEASURED, project 14f71729 on 2026-08-26, 9 scenes: scenes 2 and 3 were "
    "given the identical visual word for word though one places the "
    "placeholder zero and the other multiplies by the tens digit; two more "
    "shared 'A teacher standing in front of a clean, empty whiteboard'; and "
    "the scene teaching 92 + 230 = 322 was given 'A hand holding a pencil, "
    "looking at a blank sheet of paper on a wooden desk'. Six of nine visuals "
    "would have fitted any lesson on any subject, and the generated images "
    "were correspondingly content-free. v4 adds RULE 5 (three questions every "
    "description must answer from its own narration: which operation, what the "
    "working surface looks like at this moment, where the attention is) and "
    "RULE 6 (no two scenes may share a visual; no stock-photo framing - if the "
    "description would still make sense for a lesson about photosynthesis it "
    "is not a description of this scene). RULE 1 IS UNCHANGED AND STILL WINS "
    "ON THE DIGITS: the binding is to board STATE and STEP in words, never to "
    "text for the model to draw, because a prompt that asks for the numbers "
    "gets '2? x 23.14'. v3 stays readable, inactive."
)

#: The binding contract, as phrases that must be present. A prompt missing
#: these publishes cleanly and reproduces the defect; that is why they are
#: gated rather than trusted.
BINDING_PHRASES = (
    "EVERY VISUAL MUST DEPICT ITS OWN SCENE'S STEP",
    "NO TWO SCENES MAY SHARE A VISUAL",
    "stock-photo framing",
)

#: RULE 1 must survive. It is the older rule and it is the one measured twice.
NO_TEXT_PHRASES = (
    "NO TEXT IN THE VISUAL",
    "must NEVER request on-screen text",
)


def _fail(message: str) -> None:
    print(f"REFUSED: {message}")
    print("Nothing was written.")
    sys.exit(1)


async def main() -> None:
    if not TEMPLATE.exists():
        _fail(f"template not found in the image at {TEMPLATE}")

    raw = TEMPLATE.read_text(encoding="utf-8")
    text = raw.strip()

    # Two digests, each named for what it covers — WP-62 Task 8(e)'s correction,
    # kept here so this script cannot repeat it. The file digest is what
    # `sha256sum` on the file prints; the stored digest is of the stripped text
    # that becomes `prompts.prompt_text`. They differ by the trailing newline.
    print(f"template      : {TEMPLATE}")
    print(
        f"file sha256   : {hashlib.sha256(raw.encode()).hexdigest()}"
        "   <- matches `sha256sum` on the file"
    )
    print(
        f"stored sha256 : {hashlib.sha256(text.encode()).hexdigest()}"
        "   <- of the stripped text that becomes prompts.prompt_text"
    )
    print(f"file bytes    : {len(raw)}   stored chars: {len(text)}")

    missing = [p for p in BINDING_PHRASES if p not in text]
    if missing:
        _fail(
            "the template does not state the WP-63 Task 9 binding contract: "
            f"missing {missing!r}. A storyboard prompt without it produces "
            "visuals unbound to their narration, which is the defect this "
            "version exists to close."
        )
    missing = [p for p in NO_TEXT_PHRASES if p not in text]
    if missing:
        _fail(
            "the template has lost RULE 1 (no text in the visual): missing "
            f"{missing!r}. Binding a visual to its scene's content must never "
            "become asking an image model to draw the digits - that was "
            "measured twice on this pipeline and produced '2? x 23.14' and "
            "'12 + 44 = 67 + 5'."
        )
    print("contract : OK (RULE 5 and RULE 6 present, RULE 1 intact)")
    print()

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Prompt)
                .where(
                    Prompt.prompt_type == PROMPT_TYPE,
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
                f"expected exactly 1 active global {PROMPT_TYPE} prompt, found "
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
            prompt_type=PROMPT_TYPE,
            prompt_text=text,
            version=next_version,
            is_active=True,
            project_id=None,
            scene_id=None,
            created_by="wp-63-validator",
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
                    Prompt.prompt_type == PROMPT_TYPE,
                    Prompt.project_id.is_(None),
                    Prompt.scene_id.is_(None),
                )
                .order_by(Prompt.version)
            )
        ).scalars().all()
        print("AFTER:")
        for r in rows:
            print(f"  {r.id}  v{r.version}  active={r.is_active}")
        print()
        print(
            "ROLLBACK, if the next storyboard reads worse: one UPDATE flips "
            f"is_active back to v{current.version}. Nothing was deleted."
        )


if __name__ == "__main__":
    asyncio.run(main())
