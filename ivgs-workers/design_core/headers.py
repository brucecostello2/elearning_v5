"""Foundation §5: every per-scene generation prompt is HEADED by its scene's
instructional block.

WP-IVGS-12 Task 6.

⛔ WHAT THE SEAMS ACTUALLY ALLOW — MEASURED, AND THE SHORTFALL IS STATED

Four per-scene prompts are compiled downstream of the storyboard:

  stage3_images._generate_image_prompt      renders `stage3_system.j2` (a FILE)
                                            through a module-level `jinja_env`,
                                            with FOUR project-level variables.
  stage5_voiceover._generate_...            renders `stage4_system.j2`, same shape.
  video_generation_task                     renders `VIDEO_PROMPT_TEMPLATE`, a
                                            module CONSTANT inside a frozen file.
  motion authoring                          no LLM prompt at all; it is the API's
                                            `motion_authoring.py` acting on a
                                            template name and params.

The SCENE's identity — its index — exists only inside an f-string built in
frozen code (`stage3_images.py:210-216`). ⛔ **No seam carries it into any of
these templates.** So a header naming ONE scene cannot be delivered without
either editing a frozen body or overloading a field that means something else
(`scene_title` is the temptation, and abusing it would put pedagogy in the
storyboard UI and the composition manifest).

⛳ SO THE BLOCK IS DELIVERED AS A TABLE, KEYED BY THE SCENE NUMBER THE USER
PROMPT ALREADY NAMES. The user prompt says "Scene 4: ..."; the system prompt now
carries block 4 among the others and tells the model to look it up. That is not
a regular expression and it is not inference — it is handing the model the table
and naming the key, which is what a system prompt is for.

⚠ THE SHORTFALL, STATED RATHER THAN GLOSSED: Foundation §5 shows a single
pre-selected block at the head of one scene's prompt. What ships is the whole
table with a lookup instruction. Closing the gap needs one line inside three
frozen bodies, and R5 says to prefer the wrapper. Ledgered for the M3.3 window,
where those bodies become activities and the edit is free.

MECHANISM. Two documented Jinja APIs and no monkey-patching:

  * `Environment.globals` — a callable the FILE templates invoke. Used for
    stages 3 and 5, whose system prompts are files this package can edit.
  * A `jinja2.ext.Extension` with a `preprocess` hook, added with
    `add_extension`. Jinja's own supported way to modify template SOURCE before
    compilation, which is the only way to reach a template that is a constant
    inside a frozen module. Used for video.
"""
from __future__ import annotations

import contextvars
from typing import Any, Dict, List, Optional

import httpx
import structlog
from jinja2 import Environment
from jinja2.ext import Extension

logger = structlog.get_logger("ivgs.design_core.headers")

_project: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ivgs_header_project", default=None,
)
#: One fetch per task, not one per scene. A twelve-scene storyboard would
#: otherwise make twelve identical API calls inside the render path.
_cache: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ivgs_header_cache", default=None,
)

HEADER_OPEN = "INSTRUCTIONAL CONTEXT (binding) — one block per scene:"
HEADER_CLOSE = (
    "Use the block whose scene number matches the scene named in the user "
    "message. It states what that scene is FOR, and it binds: a `feedback` "
    "scene's warmth and an `assess` scene's neutrality are different, and the "
    "block says which this is."
)


def arm(project_id: str) -> None:
    _project.set(project_id or None)
    _cache.set(None)


def disarm() -> None:
    _project.set(None)
    _cache.set(None)


def instructional_blocks() -> str:
    """The table, as text. Empty string when there is no design brief.

    ⚠ Returns "" rather than raising or writing a placeholder. A project with no
    brief — every pre-v8 storyboard — must produce the prompt it always did,
    byte for byte, and a prompt that says "INSTRUCTIONAL CONTEXT: (none)"
    invites the model to reason about the absence.
    """
    cached = _cache.get()
    if cached is not None:
        return cached
    project_id = _project.get()
    if not project_id:
        _cache.set("")
        return ""
    try:
        blocks = _render(_fetch(project_id))
    except Exception as exc:                                     # noqa: BLE001
        logger.warning(
            "instructional_blocks_unavailable",
            project_id=project_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        blocks = ""
    _cache.set(blocks)
    return blocks


def _fetch(project_id: str) -> Dict[str, Any]:
    from config import WorkerConfig

    config = WorkerConfig()
    with httpx.Client(
        timeout=config.pipeline_api.timeout_seconds,
        headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
    ) as client:
        resp = client.get(
            f"{config.pipeline_api.full_base_url}"
            f"/projects/{project_id}/design-review"
        )
    if resp.status_code != 200:
        return {}
    return resp.json() or {}


def _render(review: Dict[str, Any]) -> str:
    if not review.get("has_brief"):
        return ""
    arc: List[Dict[str, Any]] = review.get("event_arc") or []
    if not arc:
        return ""
    coverage = {c.get("outcome_id"): c for c in (review.get("coverage") or [])}
    total = len(arc)

    lines: List[str] = [HEADER_OPEN, ""]
    for i, scene in enumerate(arc):
        idx = scene.get("scene_index")
        serves = scene.get("serves_outcomes") or []
        # Foundation §5's `evidence_link`: which later scene proves this.
        evidence: List[str] = []
        for oid in serves:
            row = coverage.get(oid) or {}
            for assessed in (row.get("assessed_by") or []):
                if assessed != idx:
                    evidence.append(f"scene {assessed}")
        # `learner_state`: what the learner has already been shown. Derived from
        # the arc rather than asked of the model, so it cannot disagree with it.
        prior = [
            f"scene {p.get('scene_index')} ({p.get('instructional_event')})"
            for p in arc[:i]
            if set(p.get("serves_outcomes") or []) & set(serves)
        ][-2:]
        lines.append(f"  Scene {idx}:")
        lines.append(f"    serves_outcomes: {serves or '(none declared)'}"
                     f"    bloom: {scene.get('bloom_level') or '—'}")
        lines.append(f"    event: {scene.get('instructional_event') or '—'}"
                     f"    arc position: {i + 1} of {total}")
        lines.append(f"    learner_state: "
                     f"{'has seen ' + ', '.join(prior) if prior else 'new to this outcome'}")
        lines.append(f"    evidence_link: "
                     f"{'proven later in ' + ', '.join(sorted(set(evidence))) if evidence else 'this scene is where it is proven'}")
        lines.append(f"    modality_rationale: {scene.get('media_rationale') or '—'}")
        if scene.get("text_carried_by"):
            lines.append(
                "    signalling: the written/numeric content is carried by the "
                "NARRATION; this visual depicts the situation, never the text."
            )
        lines.append("")
    lines.append(HEADER_CLOSE)
    return "\n".join(lines)


class InstructionalHeaderExtension(Extension):
    """Prepends the table to every template this Environment compiles.

    Jinja's documented `preprocess` hook. It is the only way to reach a template
    that is a module constant inside a frozen body — `VIDEO_PROMPT_TEMPLATE` —
    without editing that body.

    ⚠ It prepends as a COMMENT-FREE plain block, so a template that is itself
    the whole prompt gains the header and nothing else changes.
    """

    def preprocess(self, source: str, name: Optional[str],
                   filename: Optional[str] = None) -> str:
        try:
            blocks = instructional_blocks()
        except Exception:                                        # noqa: BLE001
            return source
        if not blocks:
            return source
        return f"{blocks}\n\n{source}"


def install(env: Environment, *, preprocess: bool = False) -> None:
    """Register on one stage's Jinja environment. Idempotent."""
    env.globals.setdefault("instructional_blocks", instructional_blocks)
    if preprocess and not any(
        isinstance(e, InstructionalHeaderExtension) for e in env.extensions.values()
    ):
        env.add_extension(InstructionalHeaderExtension)
