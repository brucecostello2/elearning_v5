"""Publish the tracked translation template as the next prompt version.

WP-61 Task 3(c) published v2 through this script. WP-62 Task 9(b) publishes v3
through THE SAME script, deliberately: the requirement is "publish v3 through
the same versioning path (v2 preserved inactive)", and a second publisher would
be a second set of refusals to keep in step. The module name is historical --
it is the translation prompt's versioning path, not WP-61's.

It was already version-agnostic (`next_version = max(...) + 1`); what WP-62
adds is a gate on the SCOPE half of the contract, below.

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
    "WP-62 Task 9(b), RULED SCOPE. v3 narrows the fail-and-flag contract to "
    "FACTUAL AND ARITHMETIC ERRORS ONLY. Pedagogical style is out of scope and "
    "must not flag: teaching method, notation, step order, placeholder zeros, "
    "digit-by-digit working and 'this could be clearer' are all correct "
    "arithmetic taught differently. Supersedes v2 (which stays readable, "
    "inactive, with its own note); v2 kept the fail-and-flag mechanism, which "
    "is unchanged and correct. WHY: the 2026-08-26 es-ES run of the reference "
    "project produced SEVEN flags, and operator verification against the "
    "source found TWO FALSE POSITIVES - scene 9 ('1 times 2 is 2, and 1 times "
    "3 is 3 ... our first answer is 32' is the standard algorithm applied to "
    "32 x 1, and correct) and scene 15 ('start the next line with a zero', a "
    "pedagogy opinion). Five flags are genuine: scenes 5, 6, 12 and 13 carry "
    "real arithmetic errors and scene 11 is genuinely garbled. A false flag on "
    "a correct lesson trains the reviewer to ignore the flags, which costs "
    "more than the flag saves."
)

# The two halves of the contract this script refuses to publish without. The
# marker gate has existed since v2; the SCOPE gate is WP-62 Task 9(b). A
# template that carries the marker but not the scope would publish cleanly, run
# cleanly, and reproduce the two false positives - which is exactly the shape
# of failure this series exists to stop: a green path over an unstated rule.
SCOPE_PHRASES = (
    "FACTUAL AND ARITHMETIC ERRORS ONLY",
    "OUT OF SCOPE",
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

    # WP-62 Task 8(e). TWO DIGESTS, EACH NAMED FOR WHAT IT COVERS.
    #
    # This printed ONE value labelled `sha256`, computed over the STRIPPED
    # text, five lines below an operator block that printed
    # `sha256sum ivgs-api/seed/default_prompts/translation.j2` - the FILE,
    # trailing newline included. Two digests of two different byte strings
    # under one word.
    #
    # They differ by exactly one byte and the divergence was reported as an
    # image/tree mismatch: container `205ddaba...` against tracked
    # `67be5991...`. Measured 2026-08-26, there is no mismatch - the baked
    # template in `ivgs-api:v5.20.0-qwen` is byte-identical to the tracked file
    # (both `67be5991ad4819...`), and `205ddaba...` is what THIS function
    # computes because of the `.strip()` above.
    #
    # The `.strip()` is kept: what goes into `prompts.prompt_text` should not
    # carry a trailing newline, and normalising it here is right. What was
    # wrong is printing its digest under a label that reads as the file's.
    file_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    row_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"template      : {TEMPLATE}")
    print(f"file sha256   : {file_digest}   <- matches `sha256sum` on the file")
    print(f"stored sha256 : {row_digest}   <- of the stripped text that becomes prompts.prompt_text")
    print(f"file bytes    : {len(raw)}   stored chars: {len(text)}")

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
    missing = [phrase for phrase in SCOPE_PHRASES if phrase not in text]
    if missing:
        _fail(
            "the template does not state the WP-62 Task 9(b) flag SCOPE: "
            f"missing {missing!r}. A prompt that asks for flags without "
            "bounding them to factual and arithmetic errors reproduces the two "
            "false positives measured on 2026-08-26 (scenes 9 and 15 of the "
            "reference project, both correct, both flagged on pedagogy)."
        )
    print(f"contract : OK ({MARKER} present, correction forbidden, scope stated)")
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
