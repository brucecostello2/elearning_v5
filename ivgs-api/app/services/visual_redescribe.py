"""Exit (b) — redescribe a visual so it stops asking for on-screen text.

WP-IVGS-12i3, RC-T1(b), **as narrowed by the operator's amendment of
2026-08-30**:

    CONTENT MUST NOT BE LOST — dilution to pass validation is a worse defect
    than a refusal. Redescription is legal ONLY where the on-screen text is
    incidental to the scene's declared purpose.

⛳ THAT NARROWING IS THE MOST IMPORTANT THING IN THIS MODULE, so it is enforced
by `redescription_is_legal` BEFORE any model is called, decided from the design
contract's own declarations rather than from taste. A scene whose
`instructional_event` is `present`/`guide`/`practice`/`assess` over narration
that names written or numeric content is a scene where **the learner must SEE
the digits**: Foundation §4's redundancy rule says on-screen text is *"for
labels, symbols, and the worked math itself — which narration cannot carry"*.
Rewriting that description to remove the digits does not repair the scene; it
deletes the lesson and leaves a picture that validates. Those scenes belong to
exit (a) or exit (c), and if neither takes them the stage fails.

WHAT THE CALL IS, AND THE THREE THINGS THAT BOUND IT

  * **ONE call per scene, no retry.** The same no-loop ruling the authoring call
    obeys. A second attempt at a refused redescription is a prompt loop with a
    different name.
  * **`json_schema` with `strict: true`, emitting ONE key.** RC-Q1: on this
    fleet `guided_json` is accepted with HTTP 200 and silently ignored, and so
    is every unknown body member. `response_format` with `json_schema` is the
    mechanism of record, measured enforcing.
  * ⛔ **A DETERMINISTIC POST-CHECK THAT THE MODEL CANNOT TALK ITS WAY PAST.**
    The result is fed back through **the very extractor that produced the
    refusal** — `names_a_numeral` and `demands_on_screen_text` — and if it finds
    a single demand the redescription is DISCARDED and the original refusal
    stands. The model is never trusted to have complied; compliance is measured.
    This is why the call can be bounded at one: the check, not the retry, is
    what makes the result safe.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storyboard_completeness import (
    demands_on_screen_text,
    names_a_numeral,
)

logger = logging.getLogger(__name__)


class RedescribeRefused(RuntimeError):
    """The redescription was not usable, and the sentence says why."""


#: ⛔ THE EVENTS AT WHICH THE LEARNER IS DOING THE WORK. Foundation §3: present
#: (4), guide (5), practice (6), assess (8). At these moments the written
#: content IS the content, and Foundation §4's redundancy rule reserves
#: on-screen text for exactly that: "labels, symbols, and the worked math
#: itself — which narration cannot carry".
CONTENT_EVENTS = frozenset({"present", "guide", "practice", "assess"})

#: Phrases in a scene's own `media_rationale` by which the DESIGNER said the
#: learner must see the written content. Read as evidence from the contract,
#: never inferred: if the designer wrote it down, it is not incidental.
_RATIONALE_SIGHT = (
    "see the", "seeing the", "on screen", "on-screen", "shown on screen",
    "read the", "reads the", "visible", "displayed", "watch the",
)

#: The one key the model may emit. `additionalProperties: false` plus a
#: single-entry `required` is the whole schema: the smaller the grammar, the
#: less there is for a constrained decode to run away into (RC-Q12).
REDESCRIBE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "visual_description": {"type": "string", "minLength": 20, "maxLength": 600},
    },
    "required": ["visual_description"],
    "additionalProperties": False,
}

MAX_TOKENS = 400
TEMPERATURE = 0.2


def redescription_is_legal(
    *,
    instructional_event: Optional[str],
    narration_text: Optional[str],
    media_rationale: Optional[str],
) -> "tuple[bool, str]":
    """May this scene's description be rewritten? Decided from the contract.

    Returns ``(legal, reason)``; the reason is quoted at the gate either way, so
    a reviewer can see WHY code declined to touch a scene as readily as why it
    touched one.
    """
    event = (instructional_event or "").strip().lower()
    rationale = (media_rationale or "").lower()

    for phrase in _RATIONALE_SIGHT:
        if phrase in rationale:
            return False, (
                f"this scene's own media_rationale says the learner must see "
                f"the content ({phrase!r}), so removing it from the description "
                f"would be dilution rather than repair"
            )

    from app.services.storyboard_completeness import referents

    if event in CONTENT_EVENTS and referents(narration_text or "").is_written_or_numeric:
        return False, (
            f"this is a {event!r} scene over narration that states written or "
            f"numeric content, so the written content IS the content "
            f"(Foundation §4: on-screen text is for the worked math itself). "
            f"Rewriting the description to remove it would delete the lesson "
            f"and leave a picture that validates — the dilution the 2026-08-30 "
            f"amendment forbids. This scene belongs to exit (a) or exit (c)"
        )
    return True, (
        f"the text demand is incidental to a {event or 'unlabelled'} scene "
        f"whose narration states no written or numeric content of its own"
    )


def build_prompt(*, narration: str, visual_description: str) -> str:
    """The instruction, which is RULE 1's deletion test and nothing else."""
    return (
        "You are correcting ONE storyboard scene's visual description.\n\n"
        "The scene is rendered by an image model. Image models cannot spell or "
        "do arithmetic: every attempt this pipeline has measured produced "
        "garbage like '2? x 23.14' and '12 + 44 = 67 + 5'. So the description "
        "must not ask for ANY on-screen text — no numerals, no equations, no "
        "captions, no labels, no 'the calculations', no writing of any kind.\n\n"
        "RULE 1's DELETION TEST: delete every request for text, and replace it "
        "with the STRUCTURE that would carry it — rows, columns, a ruled line, "
        "an answer row, a placeholder, a carry mark, and their states (already "
        "written, still empty, one digit wider). Describe the working SURFACE, "
        "never the marks on it.\n\n"
        "⛔ DO NOT change what the scene is about. Keep the setting, the people, "
        "the mood and the framing. You are removing a request for text, not "
        "redesigning the shot.\n\n"
        f"The narration the learner hears:\n{narration.strip()}\n\n"
        f"The current description:\n{visual_description.strip()}\n\n"
        "Emit ONLY the corrected description."
    )


def surviving_demands(visual_description: str) -> List[str]:
    """What the refusal's own extractor still finds. The post-check."""
    return list(names_a_numeral(visual_description)) + list(
        demands_on_screen_text(visual_description)
    )


async def redescribe_scene(
    db: AsyncSession,
    *,
    project_id: UUID,
    narration: str,
    visual_description: str,
    scene_index: Any = None,
) -> str:
    """One bounded call, then the deterministic check. Raises on either failure.

    ⛔ NO RETRY. If the model returns something that still demands text, that is
    the answer: the redescription is discarded and the caller's original refusal
    stands with both sentences named.
    """
    from app.services.adaptation_service import _call_model, _resolve_binding

    where = "this scene" if scene_index is None else f"scene {scene_index}"
    resolved = await _resolve_binding(db, project_id)
    answer = await _call_model(
        build_prompt(narration=narration, visual_description=visual_description),
        endpoint=resolved["endpoint"],
        model=resolved["model"],
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "ivgs_visual_redescription",
                "strict": True,
                "schema": REDESCRIBE_SCHEMA,
            },
        },
    )
    content = (answer.get("content") or "").strip()
    try:
        parsed = json.loads(content)
    except ValueError as exc:
        raise RedescribeRefused(
            f"{where}: the redescription call did not return JSON despite a "
            f"strict json_schema ({exc}). Discarded: {content[:160]!r}"
        ) from exc
    if not isinstance(parsed, dict) or not isinstance(
        parsed.get("visual_description"), str
    ):
        raise RedescribeRefused(
            f"{where}: the redescription call returned {parsed!r}, which is not "
            f"an object carrying visual_description. Discarded."
        )

    proposed = parsed["visual_description"].strip()
    still = surviving_demands(proposed)
    if still:
        raise RedescribeRefused(
            f"{where}: the redescription STILL asks for on-screen text — "
            f"{still} — measured by the same extractor that produced the "
            f"original refusal. Discarded; the original description and its "
            f"refusal stand. One call, no retry."
        )
    if not proposed:
        raise RedescribeRefused(f"{where}: the redescription was empty. Discarded.")

    logger.info(
        "visual_redescribed project=%s scene=%s binding=%s chars=%s->%s",
        project_id, scene_index, resolved["binding"],
        len(visual_description or ""), len(proposed),
    )
    return proposed
