"""Publish the tracked storyboard template as the next prompt version.

WP-63 Task 9, RULED: prompt work now, THE MODEL DOES NOT MOVE off Llama.

WP-64 Task 2 EXTENDS THE CONTRACT THIS SCRIPT GATES, and the script keeps its
name because it is the same one publish. **v4 was committed by WP-63 and never
published** - WP-63 D-2 held it behind an acceptance sequence that was voided
when project 14f71729 was deleted. It therefore has no history to preserve, and
WP-64 extended it IN PLACE with RULE 2 (a deliberate per-scene media_type
choice) and RULE 7 (a description authored FOR that medium) before its first
publish. What this script inserts is v4: one version, carrying both packages.

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
  * It refuses if the template does not ask for the media_type to be CHOSEN and
    the description to be written FOR it (WP-64). Without RULE 7 the storyboard
    still authors every description for a still, and switching a scene to
    video_clip or animation dispatches the right engine into a frozen idea -
    there is no later stage that adds the motion back.
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
    "gets '2? x 23.14'. "
    "WP-64 Task 2, in the SAME v4 (v4 was committed by WP-63 and never "
    "published, so this extends it in place rather than rewriting history). "
    "MEASURED in the tree 2026-08-26: a scene's visual_description is authored "
    "once for whatever media_type Stage 2 chose - overwhelmingly image, "
    "because nothing in v3 asked for the choice to be made - and NO layer "
    "below ever rewrites it for a different medium. update_scene "
    "(ivgs-api/app/api/v1/storyboard.py:143) persists a media_type change with "
    "no rewrite; video_generation_task.py:245 interpolates the same still "
    "description into the cinematographer prompt; "
    "animation_generation_task.py:389 hands it to Wan2.2-Animate verbatim. So "
    "v4 adds RULE 2 (media_type is a deliberate per-scene decision with stated "
    "criteria: motion inherent to the step earns video_clip; a "
    "transformation or build-up carried by a person in the frame earns "
    "animation; image otherwise - and the person requirement is not stylistic, "
    "animation_generation_task.py:481 refuses a personless reference by name) "
    "and RULE 7 (the description must be authored FOR the chosen medium: "
    "motion, camera and order for video_clip; the build, its order and the "
    "performer for animation; one composed instant for image). RULE 1 IS "
    "UNCHANGED BY THAT TOO - motion, camera and time are all describable "
    "without a digit. "
    "WP-64 Task 6, also in this v4. The storyboard model could not reason from "
    "the course's learning outcomes because the project never carried them: "
    "migration 0037 adds projects.learning_outcomes (nullable TEXT, "
    "operator-authored, not retroactive) and v4 gains RULE 0, which conditions "
    "the RULE 2 media_type criteria and the RULE 5/6/7 visual authoring on the "
    "stated outcomes when present and degrades silently when absent. The "
    "outcomes reach Stage 2 inside project_description between two explicit "
    "delimiter lines, composed by pipeline_orchestrator_v2 for the storyboard "
    "branch only - NOT because that is the right shape but because "
    "stage2_storyboard._render_user_prompt (:127-137) fixes the template's "
    "variable list inside a body AD-05 section 8 freezes; the real fix is "
    "ledgered P2.66. "
    "WP-65 Task 6 publishes this as v5, extending the same template with the "
    "two defects the FIRST REAL v4 RUN exposed (project 92e30c7e, 13 scenes, "
    "2026-08-26 - a clear improvement on v3: descriptions depicted the actual "
    "step and three scenes were deliberately chosen as video_clip). "
    "(a) DUPLICATES. Scenes 0/11, 5/9 and 6/10 carried byte-identical "
    "visual_description text, and run through content-word similarity the "
    "storyboard has SIX repeated pictures, not three: scene 8 is 100% "
    "content-identical to scene 2, scene 7 is 94% of scene 1, scene 5 is 90% "
    "of scene 3. The tail of the storyboard was repeating its head. v4 already "
    "FORBADE repeats but gave no sanctioned way to picture a RECAP, so the "
    "model copied; v5 says how to write a revisiting scene (the completed "
    "working, never the working mid-step) and adds a closing self-check whose "
    "operative invariant is that the working surface only ever GAINS. "
    "(b) RULE 1 APPLIED INCONSISTENTLY. Scenes 3, 5 and 9 described structure "
    "only - correct - while scenes 1, 2, 4, 7 and 8 named the operands (\"23 "
    "on top and 14 underneath\"), which asks the image model for those exact "
    "numerals just as surely as writing them on a board does. v4's RULE 1 "
    "examples are all about text written ON a surface, so naming a number in "
    "prose read as permitted. v5 names that failure, supplies the deletion "
    "test (delete every digit - does the description still say what the scene "
    "teaches?) and gives the vocabulary that replaces digits: position, count, "
    "width, order and emptiness. "
    "RULE 1 IS TIGHTENED, NOT TRADED, and every WP-63/WP-64 gate phrase "
    "survives - pinned by tests/test_wp65_storyboard_v5.py. "
    "THE OPERATOR'S IN-FLIGHT PROJECT IS UNAFFECTED: its scenes are stored "
    "rows generated under v4 and were not regenerated, read-modified or "
    "approved. Publishing changes only what the NEXT storyboard run produces. "
    "v4 stays readable, inactive."
)

#: The binding contract, as phrases that must be present. A prompt missing
#: these publishes cleanly and reproduces the defect; that is why they are
#: gated rather than trusted.
BINDING_PHRASES = (
    "EVERY VISUAL MUST DEPICT ITS OWN SCENE'S STEP",
    "NO TWO SCENES MAY SHARE A VISUAL",
    "stock-photo framing",
)

#: WP-64 Task 2. The medium contract, gated for the same reason: a template
#: that has lost these publishes cleanly, runs cleanly, and authors every
#: description for a still while the operator switches scenes to video.
MEDIUM_PHRASES = (
    "CHOOSE media_type DELIBERATELY, SCENE BY SCENE",
    "WRITE THE DESCRIPTION FOR THE MEDIUM YOU JUST CHOSE",
    "WHAT MOVES, as a verb",
    "WHAT HAPPENS IN WHAT ORDER",
)

#: WP-64 Task 6(d). RULE 0, and the DELIMITER IT READS. The delimiter is not
#: decoration: the orchestrator writes the outcomes into the storyboard stage's
#: `project_description` between exactly these two lines
#: (`ivgs-workers/tasks/pipeline_orchestrator_v2.py:1122`), because the frozen
#: stage body cannot be given a template variable of its own. If the two copies
#: drift, the model is handed a block it was never told to look for, and the
#: outcomes are silently ignored while everything still runs green.
OUTCOMES_PHRASES = (
    "RULE 0 —",
    "=== LEARNING OUTCOMES (authored by the course owner) ===",
    "=== END LEARNING OUTCOMES ===",
    "DO NOT invent outcomes",
)

#: WP-65 Task 6. The two v5 amendments, gated for the reason every phrase here
#: is gated: a template that has lost them publishes cleanly, runs cleanly, and
#: reproduces the exact defects the first v4 run produced.
V5_PHRASES = (
    "NAMING A NUMBER IN PROSE IS STILL ASKING FOR IT TO BE DRAWN",
    "POSITION, COUNT, WIDTH, ORDER and EMPTINESS",
    "A SCENE THAT REVISITS AN EARLIER STEP IS STILL A DIFFERENT SCENE",
    "BEFORE YOU OUTPUT, RE-READ YOUR OWN DESCRIPTIONS AS A SET",
    "THE WORKING SURFACE ONLY EVER GAINS",
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
    missing = [p for p in MEDIUM_PHRASES if p not in text]
    if missing:
        _fail(
            "the template does not state the WP-64 Task 2 medium contract: "
            f"missing {missing!r}. Without it Stage 2 authors every "
            "visual_description for a still, and nothing below rewrites one "
            "when the medium changes - the description IS the motion "
            "instruction that reaches CogVideoX and Wan2.2-Animate."
        )
    missing = [p for p in OUTCOMES_PHRASES if p not in text]
    if missing:
        _fail(
            "the template does not state the WP-64 Task 6 learning-outcomes "
            f"contract: missing {missing!r}. The delimiter lines in particular "
            "must match the orchestrator's byte for byte "
            "(pipeline_orchestrator_v2.OUTCOMES_OPEN / OUTCOMES_CLOSE); a "
            "template that does not name them is handed the block and never "
            "looks for it, and the outcomes are ignored with everything green."
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
    missing = [p for p in V5_PHRASES if p not in text]
    if missing:
        _fail(
            "the template has lost the WP-65 Task 6 amendments: missing "
            f"{missing!r}. Both close a defect the FIRST REAL v4 run produced "
            "(project 92e30c7e, 13 scenes, 2026-08-26): six of thirteen "
            "pictures were repeats of an earlier scene's, and five of thirteen "
            "named the operands in prose, which asks the image model for those "
            "numerals as surely as writing them on a board does."
        )
    print(
        "contract : OK (RULE 0, RULE 2, RULE 5, RULE 6 and RULE 7 present, "
        "RULE 1 intact, WP-65 v5 amendments present)"
    )
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
            created_by="wp-63-validator+wp-64-media",
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
