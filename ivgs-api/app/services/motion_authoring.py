"""Author a motion_graphics scene's template + parameters, one scene at a time.

WP-IVGS-09c. RUN-2 BLOCKER, AND THE MEASUREMENT THAT DEFINED IT.

Three paths can put a scene into ``media_type=motion_graphics``, and before this
module **only one of them could produce a scene that renders**:

* **v6 authoring it itself (stage 2).** RULE 8 of the live storyboard prompt
  tells the model that *"a motion_graphics scene is STRUCTURED DATA, not a
  description"* and asks it to emit ``generation_params`` with a template name
  and that template's parameters, choosing from exactly four. This works, and it
  only ever happens while the whole storyboard is being written.
* **The GUI flip.** Changes ``media_type`` and nothing else. Measured on project
  ``9c29b1d1``: six scenes at ``generation_params = {}`` with their *image*
  prose still in ``visual_description`` (*"Close-up of a hand moving a pencil
  across the paper"*). Nothing anywhere authored a template.
* **Per-scene Regen.** ⛔ **Never reaches a prompt at all.** ``regenerate_scene``
  goes to ``dispatch_scene_media_regeneration``, which re-renders media from the
  scene's *current* fields — it is a re-render path, by design, and WP-45's
  docstring says so in as many words: *"pressing Regen on a scene card does not
  re-run the storyboard LLM, it re-renders that scene's media."*

So a flipped scene had no way to become renderable, and the failure surfaced
deep in the run: all six refused at dispatch with the correct named error, the
stage failed, partial-advance carried the job into ``talking_head_render``, and
that is where the LatentSync OOM was met.

WHY NOT ``adapt-description``, WHICH IS THE OTHER MEDIUM-AWARE PROMPT.
It is prose-only and **deliberately excludes this medium**:
``adaptation_service.MEDIA_TYPES`` is ``("image", "video_clip", "animation")``
with a comment saying offering ``motion_graphics`` *"would ask the model to
write a description for a renderer that never reads one"*, and
``test_wp68_prompt_v6.py`` asserts the exclusion **so a future tidy-up does not
'fix' it into agreement**. Routing Regen through it would be exactly that
tidy-up. This module is the separate thing that was missing, not a widening of
the one that was right.

WHAT THIS ASKS FOR, AND WHAT IT REFUSES

One JSON object, for ONE scene. The catalogue it offers the model is built from
``shared.motion.templates`` — the same module the renderer draws from — so the
prompt cannot describe a template the renderer does not have, and a template
added there appears here without an edit.

⛔ **Nothing is invented on the model's behalf.** A reply naming a template that
does not exist, omitting a parameter the template declares, or inventing one it
does not, is REFUSED BY NAME. There is no "closest match", no default template
and no partial spec: a motion graphic that draws the wrong sum is worse than a
scene that says it could not be authored, because the arithmetic is the content
and no gate downstream reads it (WP62-L7 — human eyes until M3.3).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Budget for one scene's spec. A template call is a handful of tokens; this is
#: generous enough that a model which reasons briefly is not clipped, and small
#: enough that a runaway completion fails visibly rather than costing minutes.
MAX_TOKENS = 300

#: Low, and lower than adaptation's. This is not composition — the right answer
#: is largely determined by the lesson's own numbers, and creativity here means
#: teaching arithmetic the transcript never mentioned.
TEMPERATURE = 0.1


class MotionAuthoringError(RuntimeError):
    """A motion spec could not be authored. Always names why."""


def template_catalogue() -> Dict[str, Dict[str, Any]]:
    """The four templates, from the renderer's own module.

    Read from ``shared.motion.templates`` rather than restated here. A second
    list of what the templates are would be a second definition, and the
    renderer would keep drawing from the first one.
    """
    from shared.motion.templates import template_names, template_spec

    return {
        name: {
            "params": dict(template_spec(name)["params"]),
            "describes": template_spec(name)["describes"],
        }
        for name in template_names()
    }


def build_prompt(
    *,
    narration: str,
    visual_description: str,
    project_name: str,
    project_description: str,
) -> str:
    """RULE 8's ask, narrowed to one scene.

    The catalogue is rendered from the templates module, so the prompt and the
    renderer cannot disagree about what exists or what a parameter is called.
    """
    cat = template_catalogue()
    lines = []
    for name, spec in sorted(cat.items()):
        params = ", ".join(f'"{p}": <int>' for p in sorted(spec["params"]))
        lines.append(f'  {{"template": "{name}", {params}}}')
        lines.append(f"      {spec['describes']}")
        for pname, meaning in sorted(spec["params"].items()):
            lines.append(f"      {pname}: {meaning}")
    catalogue = "\n".join(lines)

    return f"""You are authoring ONE motion-graphics scene for a maths lesson.

A motion_graphics scene is STRUCTURED DATA, not a description. The renderer does
not read prose; it takes a TEMPLATE NAME and that template's PARAMETERS and
draws the result itself in a real font. That is the point: a renderer that puts
"23" on screen cannot misspell it.

THE LESSON
  Title: {project_name}
  About: {project_description}

THIS SCENE
  Narration the learner will hear: {narration or "(none recorded)"}
  The description it currently carries, written for a still image and NOT
  something the renderer will read: {visual_description or "(none recorded)"}

THE ONLY TEMPLATES THAT EXIST. Use a template name and parameter names EXACTLY
as written. Do not invent a template, a parameter, or a parameter spelling.

{catalogue}

THE PARAMETERS ARE THE LESSON'S WHOLE NUMBERS, NOT THE DIGITS THIS STEP
MULTIPLIES. A narration that says "multiply 4 times 3" while the lesson is
23 x 14 is describing ONE STEP of that sum: the whole sum is what the template
draws, and "step" selects which multiplier digit the scene works. So that scene
is {{"top": 23, "bottom": 14, "step": 0}} — NOT {{"top": 14, "bottom": 3}}. Read the
narration for which step it is; read the lesson for the numbers.

THE NUMBERS MUST BE THE ONES THIS LESSON ACTUALLY USES. Take them from the
narration and the lesson together. If the narration names no numbers, take them from the lesson
title and description. Do not choose round or convenient numbers that the
lesson does not teach — the learner sees this arithmetic worked on screen, and
nothing downstream checks it.

Reply with ONE JSON object and nothing else. No prose, no code fence, no
explanation.
"""


def parse_and_validate(raw: str) -> Dict[str, Any]:
    """The model's reply -> a spec the renderer will accept, or a named refusal.

    Every branch here refuses rather than repairs. The alternative — filling in
    a missing parameter, or matching a near-miss template name — produces a
    scene that renders confidently and teaches the wrong thing, which is the
    one failure this whole medium exists to prevent.
    """
    from shared.motion.templates import template_names, template_spec

    text = (raw or "").strip()
    # A code fence is the common, harmless deviation; strip it and keep going.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    # A model that prefaces the object is also common; take the first object.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise MotionAuthoringError(
                f"the model returned no JSON object. It said: {text[:200]!r}"
            )
        text = text[start : end + 1]

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MotionAuthoringError(
            f"the model's reply is not valid JSON ({exc}). It said: {text[:200]!r}"
        ) from exc

    if not isinstance(obj, dict):
        raise MotionAuthoringError(
            f"expected one JSON object, got {type(obj).__name__}: {text[:200]!r}"
        )

    name = obj.get("template")
    known = template_names()
    if name not in known:
        raise MotionAuthoringError(
            f"the model chose template {name!r}, which does not exist. The "
            f"renderer has exactly: {', '.join(known)}. Refused rather than "
            f"matched to the nearest one."
        )

    declared = set(template_spec(str(name))["params"])
    supplied = {k for k in obj if k != "template"}
    missing = sorted(declared - supplied)
    extra = sorted(supplied - declared)
    if missing or extra:
        faults = []
        if missing:
            faults.append(f"omitted {missing}")
        if extra:
            faults.append(f"invented {extra}")
        raise MotionAuthoringError(
            f"template {name!r} takes exactly {sorted(declared)}; the model "
            f"{' and '.join(faults)}. Refused rather than defaulted: a missing "
            f"parameter drawn from a default teaches arithmetic nobody asked for."
        )

    spec: Dict[str, Any] = {"template": str(name)}
    for key in sorted(declared):
        value = obj[key]
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise MotionAuthoringError(
                f"template {name!r} parameter {key!r} must be a number or a "
                f"short string; got {type(value).__name__} {value!r}"
            )
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        spec[key] = value

    # The renderer is the final authority: if it will not draw this, say so now
    # rather than at dispatch. Cheap — the templates module is pure data.
    from shared.motion.templates import render as render_template

    try:
        render_template(spec["template"], **{k: v for k, v in spec.items() if k != "template"})
    except Exception as exc:  # noqa: BLE001 — every rejection is one fact
        raise MotionAuthoringError(
            f"the templates module refused {spec!r}: {type(exc).__name__}: {exc}"
        ) from exc

    return spec


def has_motion_spec(generation_params: Any) -> bool:
    """Whether a scene already carries a template. ``{}`` and ``None`` do not.

    The GUI flip leaves ``{}`` — an object that exists and says nothing — and
    ``{}`` is falsy, so a bare truth test would have been right by accident.
    Written out because the distinction is the whole defect.
    """
    return isinstance(generation_params, dict) and bool(generation_params.get("template"))


async def author_params_for_scene(
    db: AsyncSession,
    *,
    project_id: UUID,
    narration: str,
    visual_description: str,
    project_name: str,
    project_description: str,
) -> Dict[str, Any]:
    """Ask the storyboard model for this scene's template + parameters.

    Runs on the **storyboard-generation binding**, deliberately and for the same
    reason ``adapt-description`` does: RULE 8 is a storyboard rule, and the model
    that writes storyboards is the one that has been told what these templates
    are. It does not fall back to another model.
    """
    from app.services.adaptation_service import _call_model, _resolve_binding

    resolved = await _resolve_binding(db, project_id)
    prompt = build_prompt(
        narration=narration,
        visual_description=visual_description,
        project_name=project_name,
        project_description=project_description,
    )
    answer = await _call_model(
        prompt,
        endpoint=resolved["endpoint"],
        model=resolved["model"],
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    spec = parse_and_validate(answer.get("content", ""))
    logger.info(
        "motion_spec_authored project=%s template=%s params=%s binding=%s",
        project_id, spec.get("template"),
        {k: v for k, v in spec.items() if k != "template"},
        resolved["binding"],
    )
    return spec
