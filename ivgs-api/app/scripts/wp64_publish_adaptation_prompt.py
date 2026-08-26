"""Publish the tracked scene-media-adaptation template. WP-64 Task 3(a).

The same versioning path `wp61_publish_prompt.py` and
`wp63_publish_storyboard_prompt.py` use -- current version preserved inactive,
next version inserted active, change note recorded on the row, rollback is one
UPDATE of `is_active` -- pointed at the new `scene_media_adaptation` type.

It is a SEPARATE script for the same reason the storyboard one is: the gates
differ. The translation publisher gates on the fail-and-flag contract, the
storyboard publisher on RULES 0/1/2/5/6/7, and this one on the three rules that
make an ADAPTATION an adaptation rather than a fresh invention. A shared
publisher would either lose every set of gates or grow an `if prompt_type ==`
ladder, and the gates are the point.

RUN INSIDE `ivgs-fastapi`, AFTER migration 0038:

    sudo docker exec -i ivgs-fastapi \\
      python -m app.scripts.wp64_publish_adaptation_prompt

Migration 0038 adds the `scene_media_adaptation` label to the `prompt_type`
enum. Without it this script fails on the INSERT with an invalid input value
for the enum -- loudly, before anything is written, which is the correct
outcome and is stated here so it is not mistaken for a defect.

WHAT IT REFUSES TO DO:

  * It refuses if the template has lost RULE 1's no-text-in-the-visual rule.
    An adaptation prompt without it produces rewrites full of drawn digits,
    which this pipeline has measured twice ("2? x 23.14", "12 + 44 = 67 + 5").
  * It refuses if the template has lost RULE 2 (keep the subject). Without it
    the model writes a NEW scene rather than the same scene in a new medium,
    and the operator cannot tell from reading the output that it has happened.
  * It refuses if the template has lost RULE 3's per-medium instructions, which
    are the entire function of the prompt.
  * It refuses if the template does not carry the person constraint on
    animation. `animation_generation_task.py:481` REFUSES a scene whose
    reference image has no person; a rewrite that drops the person produces a
    scene the pipeline will then reject.
  * It refuses if there is not exactly ONE active global prompt of this type,
    OR none at all -- a first publish is legal and is the expected case.
  * It refuses if an identical version is already published, so a second run is
    a no-op rather than a version differing from its predecessor by nothing.

WHAT IT DOES NOT DO. It does not UPDATE or DELETE any existing version.

THE MODEL DOES NOT MOVE. This prompt is rendered against the AD-01 binding for
`storyboard_generation` -- Llama, resolved through the same `get_binding` the
worker calls (`app/services/adaptation_service.py:_resolve_binding`). Publishing
a prompt row cannot change which model runs it.
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import select

from app.models.prompt import Prompt
from shared.database import async_session_factory

PROMPT_TYPE = "scene_media_adaptation"
TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "seed"
    / "default_prompts"
    / "scene_media_adaptation.j2"
)

CHANGE_NOTE = (
    "WP-64 Task 3. First version. MEASURED IN THE TREE 2026-08-26: a scene's "
    "visual_description is authored once by Stage 2 for whatever media_type "
    "Stage 2 chose, and no layer below rewrites it when the medium changes. "
    "update_scene (ivgs-api/app/api/v1/storyboard.py:143) persists a "
    "media_type change with no rewrite; video_generation_task.py:245 "
    "interpolates the same still-authored description into the "
    "cinematographer prompt; animation_generation_task.py:389 hands it to "
    "Wan2.2-Animate verbatim. So switching a scene to video or animation "
    "dispatched the right engine into a frozen idea. This prompt is the "
    "operator's explicit repair: narration + current description + target "
    "medium in, one rewritten description out, RETURNED TO THE OPERATOR TO "
    "READ AND EDIT - the endpoint never writes the scene row. It keeps the "
    "subject (same step, same working surface, same style), writes for the "
    "target medium (motion/camera/order for video_clip; the build, its order "
    "and the performer for animation; one composed instant for image), and "
    "RULE 1 outranks all of it: no digits, no captions, no drawn text."
)

#: The three rules that make this an adaptation rather than an invention, and
#: the person constraint the animation branch enforces in code. A prompt
#: missing any of these publishes cleanly, runs cleanly, and returns something
#: the operator cannot tell from a good answer by reading it.
CONTRACT_PHRASES = (
    "NO TEXT IN THE VISUAL",
    "KEEP THE SUBJECT",
    "WRITE IT FOR THE TARGET MEDIUM",
    "pose reenactment",
)

#: Rendering is StrictUndefined (adaptation_service.render_prompt), so a
#: template that names a variable the service does not pass raises at request
#: time, in front of an operator, instead of here. Gated at publish instead.
REQUIRED_VARIABLES = (
    "project_title",
    "scene_label",
    "target_media_type",
    "current_media_type",
    "narration_text",
    "current_description",
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

    # Two digests, each named for what it covers -- WP-62 Task 8(e)'s
    # correction, which this script inherits rather than repeats. The file
    # digest is what `sha256sum` prints; the stored digest is of the stripped
    # text that becomes `prompts.prompt_text`. They differ by a trailing
    # newline, and labelling both `sha256` is what cost WP-62 an afternoon.
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

    missing = [p for p in CONTRACT_PHRASES if p not in text]
    if missing:
        _fail(
            "the template does not carry the WP-64 Task 3 adaptation "
            f"contract: missing {missing!r}. Without the no-text rule the "
            "rewrite asks an image model to draw digits; without "
            "keep-the-subject it writes a different scene; without the "
            "per-medium rules it is not an adaptation at all."
        )

    missing = [v for v in REQUIRED_VARIABLES if ("{{ " + v + " }}") not in text]
    if missing:
        _fail(
            f"the template never renders {missing!r}. The service passes "
            "exactly these six and renders with StrictUndefined, so a template "
            "that ignores one is a prompt missing the scene it is meant to be "
            "rewriting -- which is IVGS-0.4's defect, where a template rendered "
            "with unset variables asked the model to translate nothing into "
            "nothing."
        )
    print(f"contract : OK ({len(CONTRACT_PHRASES)} rules, "
          f"{len(REQUIRED_VARIABLES)} variables)")
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
        if not rows:
            print("  (none - this is the first version of this prompt type)")
        for r in rows:
            print(f"  {r.id}  v{r.version}  active={r.is_active}  {r.created_at}")
        print()

        active = [r for r in rows if r.is_active]
        if len(active) > 1:
            _fail(
                f"found {len(active)} active global {PROMPT_TYPE} prompts. "
                "Deciding which to retire is not this script's call."
            )

        current = active[0] if active else None
        if current is not None and current.prompt_text.strip() == text:
            print(
                "The active prompt is ALREADY this exact text. Nothing to do; "
                "a second run must not create a version that differs by nothing."
            )
            return

        next_version = max((r.version for r in rows), default=0) + 1

        if current is not None:
            current.is_active = False
        published = Prompt(
            prompt_type=PROMPT_TYPE,
            prompt_text=text,
            version=next_version,
            is_active=True,
            project_id=None,
            scene_id=None,
            created_by="wp-64-media",
            change_note=CHANGE_NOTE,
        )
        db.add(published)
        await db.commit()
        await db.refresh(published)

        if current is not None:
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
        if current is None:
            print(
                "ROLLBACK: there is no earlier version to fall back to. "
                "Setting is_active=false on v1 disables the Adapt action, "
                "which then refuses by name rather than improvising a prompt."
            )
        else:
            print(
                "ROLLBACK, if the rewrites read worse: one UPDATE flips "
                f"is_active back to v{current.version}. Nothing was deleted."
            )


if __name__ == "__main__":
    asyncio.run(main())
