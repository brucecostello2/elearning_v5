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
    "WP-68 Task 4 publishes this as v6. MEASURED 2026-08-26: the operator's "
    "project asked in its own description for 'fun animations' and one of its "
    "stated learning outcomes is 'understand the difference between 10's and "
    "unit numbers' - a concept that is inherently animated - and the system "
    "produced ZERO animations across thirteen scenes and could not have "
    "produced any. animation_generation is bound to Wan2.2-Animate, which is "
    "pose reenactment: it needs a person in the still and a driving clip, so "
    "WP-64's D-2 criterion is correct for the engine and STRUCTURALLY EXCLUDES "
    "THE MATHEMATICS. "
    "AND THE CHEAP PATH DOES NOT EXIST. `drawtext` appears NOWHERE in this "
    "repository: the compositor overlays PRE-RENDERED layers at a fixed x:y "
    "(ffmpeg_client.py:480-517) and burns bottom-aligned SRT captions "
    "(:524-531). It cannot place a digit at a position, let alone move one "
    "between columns. So RULE 1's standing promise - that 'every equation, "
    "number, label and caption is rendered by the COMPOSITION OVERLAY in a "
    "later stage, with a real font' - has had one half missing since v3. "
    "v6 adds a FOURTH media type, `motion_graphics` (migration 0041), with a "
    "criterion naming exactly what earns it: a numeric or structural "
    "transformation the viewer must SEE HAPPEN. WP-64's D-2 person-in-frame "
    "criterion STAYS for `animation`, because Wan is still Wan, and v6 states "
    "in as many words that the two are not interchangeable - a person "
    "demonstrating earns `animation`, numbers changing earn "
    "`motion_graphics`, and a scene with no person can never be the former "
    "however much it moves. "
    "RULE 8 is the new rule and the unusual one: a motion_graphics scene is "
    "NOT described in prose. It emits `generation_params` carrying a template "
    "name and that template's parameters - {\"template\": "
    "\"place_value_split\", \"number\": 23} - into a JSONB column that has "
    "existed since the table was created, so this needs no schema fight. Four "
    "templates are offered and all four are served by "
    "shared/motion/templates.py; this publisher REFUSES a template naming one "
    "that is not. RULE 1 is SCOPED rather than contradicted: the parameters "
    "are digits and they are DRAWN, not generated, which is the path that "
    "makes RULE 1 unnecessary rather than merely enforced - a renderer that "
    "puts '23' on screen in a real font cannot produce '2? x 23.14'. The "
    "scene's visual_description is still written, still short, and still "
    "digit-free, because it is a caption and a record, not an instruction. "
    "WHAT THIS DOES NOT DO, and the prompt does not pretend otherwise: no "
    "renderer is deployed for the motion_graphics engine, so a scene chosen "
    "this way is HELD BY NAME by the orchestrator rather than dispatched or "
    "silently rendered as an image, and the Media Type dropdown deliberately "
    "does not offer this value - WP-64 removed one advertising a pathway that "
    "did not exist and adding it back early would be the same defect. "
    "WP-IVGS-10 Task 2 publishes this as v7, on the operator's ruling of "
    "2026-08-28: THE STORYBOARD'S VISUAL LAYER IS AUTHORED AS AESTHETIC "
    "STAGING, NOT CONTENT. Measured the same day over both stored "
    "storyboards with the classifier that now runs at the gate "
    "(app/services/storyboard_completeness.py): the reference run c12fa967 is "
    "17 of 18 scenes DELEGATES-TO-WRONG-MEDIUM, and 9c29b1d1 is 8 of 14 - and "
    "in 9c29b1d1 every one of the six scenes that DEPICTS is a motion scene "
    "WP-IVGS-09f authored, so EVERY visual the storyboard model itself wrote "
    "is a delegation or a generic. The operator's own example: scene 1's "
    "narration says 'write the numbers on top and underneath, making sure the "
    "ones digits line up ... draw a line underneath' and its visual is 'a hand "
    "holding a pencil, poised over a blank sheet of lined paper with a ruler "
    "and a soft pink pencil case nearby, warm and gentle lighting'. "
    "v7 adds RULE 1-EXTENDED, which is the general rule the motion-params saga "
    "(WP-IVGS-09b..09f) was one measurable instance of. RULE 1 has always "
    "governed the DESCRIPTION and never the MEDIA-TYPE CHOICE, so a scene "
    "whose content IS written or numeric could still be handed to diffusion, "
    "and RULE 1 then forbade its description from naming the thing the scene "
    "teaches - leaving nothing to depict, which is what 'a hand, a pencil, "
    "warm lighting' is. v7 classifies the content FIRST and derives the medium "
    "from it: content-bearing scenes are either motion_graphics with a "
    "template (RULE 8) or diffusion WITH an explicit "
    "text_carried_by='narration' declaration, and there is no third answer. "
    "The declaration is a COLUMN (migration 0045), not a phrase in the prose, "
    "because every previous attempt to state something about a visual inside "
    "the visual's own text has had to be recovered by a regular expression "
    "afterwards. Declaring never licenses a digit: RULE 1 still refuses a "
    "declared scene whose description names a numeral or asks for 'the "
    "calculations'. "
    "v7 also amends RULE 5 - STAGING MAY REMAIN, CONTENT IS MANDATORY, with a "
    "second deletion test (delete the staging; does the lesson step survive?) "
    "and the WHAT IS SHOWN / IN WHAT STATE / CHANGING HOW ordering - and adds "
    "RULE 9, one line per scene recording the classification that decided its "
    "medium (migration 0045's media_rationale). A wrong media choice and a "
    "right one have looked identical on the row since WP-64 made the choice "
    "deliberate. "
    "AND RULE 8 GAINS 'phase' (WP-IVGS-10 Task 4, executing RC-O10). Measured "
    "on 9c29b1d1: scenes 2 and 3 rendered the IDENTICAL animation and so did 4 "
    "and 5, because the template took only (top, bottom, step) and step names "
    "WHICH MULTIPLIER DIGIT, never HOW FAR THROUGH THAT DIGIT'S ROW. 'start' "
    "writes the row's first column and leaves it incomplete, 'complete' opens "
    "with that column already drawn and finishes the row, 'full' is the whole "
    "row and is BYTE-IDENTICAL to what the templates produced before phases "
    "existed. The narration states the phase in words - announces a result -> "
    "complete, carries with no result -> start - so it is read, not "
    "calculated, and the WP-IVGS-09f guard refuses both wrong ways round. "
    "THE FIELD LIST AT THE TOP IS ALSO CORRECTED: it said media_type was 'One "
    "of image, video_clip, or animation' while RULE 2 and RULE 8 three rules "
    "below offered motion_graphics, so the first thing the model read about "
    "its own output contract said the fourth value does not exist. "
    "EVERY WP-63/WP-64/WP-65/WP-68 GATE PHRASE SURVIVES and RULE 1 IS "
    "TIGHTENED, NOT TRADED. v6 stays readable, inactive."
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
#: ⚠ AMENDED BY WP-IVGS-12, AND TWO PHRASES ARE DELIBERATELY DROPPED.
#: The two delimiter lines were gated because the orchestrator pasted the
#: outcomes into `project_description` between exactly them, and a drift
#: between the writer and the reader meant the model was handed a block it was
#: never told to look for while everything still ran green.
#:
#: ⛳ THERE IS NO BLOCK ANY MORE. Migration 0047 gives the SYSTEM prompt its own
#: version lineage, and the orchestrator renders it with `learning_outcomes` as
#: a first-class Jinja variable — which is what ledger P2.66 asked for and what
#: `_description_with_outcomes` was an explicitly-marked fallback for. Gating a
#: delimiter that nothing writes any more would refuse every correct v8.
#:
#: The two phrases that are still TRUE are kept, and two v8 phrases replace the
#: dropped pair: the model must still be told the outcomes govern every rule,
#: and must still be forbidden from inventing them.
OUTCOMES_PHRASES = (
    "RULE 0 —",
    "THE LEARNING OUTCOMES ARE IN YOUR SYSTEM INSTRUCTIONS",
    "There is\nno delimited block to look for any more.",
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

#: WP-68 Task 4. RULE 8 and the fourth media type. Gated for the same reason:
#: a template that has lost them publishes cleanly, runs cleanly, and quietly
#: goes back to having no motion-graphics pathway while the renderer, the
#: templates and the checker all still exist.
V6_PHRASES = (
    "NUMERIC OR STRUCTURAL TRANSFORMATION THE VIEWER MUST SEE",
    'RULE 8 — A "motion_graphics" SCENE IS STRUCTURED DATA',
    '"animation" AND "motion_graphics" ARE NOT INTERCHANGEABLE',
    "MUST be the numbers this lesson actually uses",
)

#: WP-IVGS-10 Task 2. v7's three amendments, gated for the reason every phrase
#: here is gated: a template that has lost them publishes cleanly, runs cleanly,
#: and goes straight back to authoring the visual layer as staging.
#:
#: RULE 1-EXTENDED is the load-bearing one. Without it RULE 1 governs only the
#: DESCRIPTION, a scene whose content is written or numeric can still be handed
#: to diffusion, and RULE 1 then forbids its description from naming the thing
#: the scene teaches -- which is exactly how "a hand, a pencil, warm lighting"
#: became the house style over thirty-two measured scenes.
V7_PHRASES = (
    "RULE 1-EXTENDED — WRITTEN OR NUMERIC CONTENT IS NEVER DELEGATED TO DIFFUSION",
    "THERE IS NO THIRD ANSWER",
    '"text_carried_by": "narration"',
    "STAGING MAY REMAIN. CONTENT IS MANDATORY.",
    "WHAT IS SHOWN",
    "IN WHAT STATE",
    "CHANGING HOW",
    "RULE 9 — RECORD WHY YOU CHOSE THAT MEDIUM, IN ONE LINE",
    "MEDIA TYPE IS DERIVED, NOT PREFERRED",
    '"phase" — WHICH PART OF THE ROW THIS SCENE WRITES',
)

#: WP-IVGS-12b. v9 removes outcome TEXT from what the model produces and makes
#: the empty-drops claim checkable. Gated for the usual reason: a template that
#: loses them publishes cleanly, runs cleanly, and goes straight back to a
#: design whose spine is a paraphrase (RC-Q9).
V9_PHRASES = (
    '"outcome_notes": one entry per outcome id',
    "You do not write outcome TEXT",
    "YOU CANNOT INVENT AN ID",
    "REFUSES THE DESIGN OUTRIGHT when a",
)

#: WP-IVGS-12 Task 3. v8's Design Contract rules, gated for the reason every
#: phrase here is gated: a template that has lost them publishes cleanly, runs
#: cleanly, and goes straight back to sequencing a paraphrase.
#:
#: RULE 12 is the load-bearing one and it is the audit's headline finding.
#: v7 said "Total Runtime Target" at the top of the prompt and Stage 1's system
#: prompt said "align with max_runtime_seconds", and between them a four-minute
#: script became a 1:45 condensation with a worked example missing. Duration is
#: an OUTPUT of a design. A prompt that reinstates a target reinstates the
#: defect this entire package exists to remove.
V8_PHRASES = (
    "RULE 10 — EVERY SCENE DECLARES WHAT IT TEACHES AND WHAT JOB IT DOES",
    "SERVING IS NOT EVIDENCE",
    "RULE 11 — EVERY SCENE SAYS WHERE ITS MATERIAL CAME FROM",
    "IF YOU REWORD THE SCRIPT, SAY SO",
    'EVERY BEAT YOU DO NOT USE GOES IN "dropped_beats", WITH ITS REASON',
    "RULE 12 — DURATION DERIVES FROM THE DESIGN",
    "THE RUNTIME FIGURE ABOVE IS ADVISORY AND IT IS NOT A BUDGET TO HIT",
    "THE ARC MUST REACH APPLICATION",
    'DO NOT WRITE "talking_head" AS A media_type',
)


#: WP-IVGS-10. The four media types, in the OUTPUT CONTRACT at the top of the
#: template rather than only in RULE 2. v6 introduced `motion_graphics` in
#: RULE 2 and RULE 8 and left the field list three rules above them saying
#: "image, video_clip, or animation" -- so the first thing the model read about
#: its own output said the fourth value does not exist.
FIELD_LIST_PHRASES = (
    'One of "image", "video_clip", "animation" or "motion_graphics"',
    '"media_rationale"',
    '"text_carried_by"',
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
    missing = [p for p in V6_PHRASES if p not in text]
    if missing:
        _fail(
            "the template has lost the WP-68 Task 4 amendments: missing "
            f"{missing!r}. RULE 8 is the only place the prompt is told that a "
            "motion_graphics scene is emitted as a template name and its "
            "parameters rather than as prose; without it the fourth media type "
            "is a value the model can choose and never populate."
        )

    missing = [p for p in V7_PHRASES if p not in text]
    if missing:
        _fail(
            "the template has lost the WP-IVGS-10 Task 2 amendments: missing "
            f"{missing!r}. These are v7 and they are the operator's ruling of "
            "2026-08-28 -- that the visual layer is authored as aesthetic "
            "staging rather than content. MEASURED over both stored "
            "storyboards on 2026-08-28: of 18 scenes in the reference run "
            "17 delegated written or numeric content to a diffusion medium, "
            "and of 14 scenes in 9c29b1d1 eight did, while EVERY scene the "
            "model itself authored as a visual was a delegation or generic. "
            "RULE 1-EXTENDED is the one that must not be dropped: without it "
            "RULE 1 governs the description and nothing governs the CHOICE, "
            "so a scene whose content is written or numeric still reaches an "
            "image model and its description is then forbidden from naming "
            "what the scene teaches."
        )
    # ⛔ IT MUST RENDER, IN EVERY BRANCH. ADDED BY WP-IVGS-12 BECAUSE THIS
    # PUBLISHER HAD NO SUCH CHECK AND I BROKE THE TEMPLATE WITH IT MISSING.
    # Editing RULE 0 swallowed the `{% endif %}` that closed
    # `{% if project_description %}`, and every phrase gate above still passed:
    # a substring check cannot see an unbalanced block. It was caught by a test
    # two layers away, and without that test it would have published cleanly and
    # raised `TemplateSyntaxError` inside a FROZEN stage body at run time —
    # `_render_user_prompt` converts it to `ValueError("Jinja2 syntax error in
    # storyboard prompt")` and Stage 2 dies for every project at once.
    from jinja2 import BaseLoader as _BaseLoader, Environment as _Env

    _env = _Env(loader=_BaseLoader(), keep_trailing_newline=True)
    for _label, _desc in (("with a brief", "A short lesson."), ("with none", "")):
        try:
            _rendered = _env.from_string(text).render(
                project_title="p",
                project_description=_desc,
                target_audience="general",
                max_duration_seconds=300,
                total_runtime_seconds=300,
                combined_transcript="t",
                transcript_count=1,
                target_scene_count=None,
                language_code="en-US",
            )
        except Exception as _exc:                                # noqa: BLE001
            _fail(
                f"the template does not RENDER {_label}: {type(_exc).__name__}: "
                f"{_exc}. Stage 2 renders this inside a frozen body; a template "
                "that raises there fails every project until it is rolled back."
            )
        if len(_rendered) < 10_000:
            _fail(
                f"the template renders only {len(_rendered)} characters "
                f"{_label} — a guard has swallowed most of the prompt."
            )

    missing = [p for p in V9_PHRASES if p not in text]
    if missing:
        _fail(
            "the template has lost the WP-IVGS-12b amendments: missing "
            f"{missing!r}. v9 is RC-Q9's structural cure: the model does not "
            "emit outcome TEXT at all, because asked to transcribe three ABCD "
            "outcomes it returned two, reworded, three times running, and no "
            "prompt wording fixed it. If this template starts asking for "
            "outcome text again, the design's spine is a paraphrase and the "
            "gate's whole matrix is drawn against it."
        )

    missing = [p for p in V8_PHRASES if p not in text]
    if missing:
        _fail(
            "the template has lost the WP-IVGS-12 Design Core amendments: "
            f"missing {missing!r}. These are v8 and they are Phase 1 of the "
            "recovery plan -- the storyboard becomes an instructional DESIGN "
            "rather than a sequenced script. RULE 12 is the one that must not "
            "be dropped: v7 headed this prompt with a 'Total Runtime Target' "
            "and Stage 1's system prompt said 'align with "
            "max_runtime_seconds', and between them a four-minute script "
            "became a 1:45 condensation with a worked example missing. "
            "Duration is an OUTPUT of a design. RULE 10 and RULE 11 are the "
            "declarations the gate checks mechanically -- every outcome served "
            "AND assessed, every beat sourced or dropped-with-reason -- and a "
            "prompt that stops asking for them produces a design brief with "
            "nothing in it while the run still reports success."
        )

    missing = [p for p in FIELD_LIST_PHRASES if p not in text]
    if missing:
        _fail(
            "the template's OUTPUT CONTRACT does not offer what its rules ask "
            f"for: missing {missing!r}. A field list that omits a media type "
            "RULE 2 tells the model to choose, or a field the gate refuses "
            "without, is a contract that contradicts its own rules -- and the "
            "model reads the contract first."
        )

    # A prompt that offers a template the renderer does not serve produces a
    # scene that cannot be rendered at all -- checked against the module rather
    # than against a list in this script, so the two cannot drift.
    import re as _re

    from shared.motion.templates import template_names as _template_names

    offered = set(_re.findall(r'"template": "([a-z_]+)"', text))
    unknown = offered - set(_template_names())
    if unknown:
        _fail(
            f"the template offers motion templates that do not exist: "
            f"{sorted(unknown)}. Known: {', '.join(_template_names())}."
        )
    if not offered:
        _fail(
            "the template names no motion templates at all, so RULE 8 asks for "
            "structured data the model has no vocabulary for."
        )

    # WP-IVGS-10. EVERY PARAMETER THE RENDERER DECLARES MUST BE NAMED IN THE
    # PROMPT. Checked against the module for the same reason the template names
    # are: `phase` was added to two templates by Task 4, and a prompt that never
    # mentions it produces specs without it -- which `parse_and_validate`
    # refuses at authoring time, one stage too late and with a message about a
    # missing parameter rather than about a prompt that never asked for one.
    from shared.motion.templates import template_spec as _spec

    unnamed = sorted(
        {
            param
            for name in _template_names()
            for param in _spec(name)["params"]
            if f'"{param}"' not in text
        }
    )
    if unnamed:
        _fail(
            f"the templates declare parameter(s) {unnamed} that this prompt "
            f"never names, so the model cannot supply them and every spec it "
            f"returns will be refused for omitting one. Name them in RULE 8."
        )

    print(
        "contract : OK (RULE 0, RULE 1-EXTENDED, RULE 2, RULE 5, RULE 6, "
        "RULE 7, RULE 8 and RULE 9 present, RULE 1 intact, WP-65 v5, WP-68 v6 "
        "and WP-IVGS-10 v7 amendments present, output contract offers all four "
        f"media types, {len(offered)} motion templates all served)"
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
