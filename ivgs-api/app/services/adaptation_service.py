"""Adapt one scene's visual description to a different medium. WP-64 Task 3.

THE FINDING, MEASURED IN THE TREE ON 2026-08-26.

A scene's ``visual_description`` is authored ONCE, by Stage 2, for whatever
``media_type`` Stage 2 chose. After that:

* ``PATCH /projects/{id}/scenes/{sid}`` persists a ``media_type`` change with no
  rewrite of the description at all (``app/api/v1/storyboard.py:143`` ->
  ``StoryboardService.update_scene``, which is a ``setattr`` loop);
* ``video_generation_task._generate_video_prompt`` interpolates that same
  still-authored description into the cinematographer prompt
  (``ivgs-workers/tasks/video_generation_task.py:245``);
* ``animation_generation_task._params_from_binding`` hands it to Wan2.2-Animate
  verbatim as the render prompt (``:389``).

Nothing between the editor and the engine adds the motion, the camera or the
order that a moving medium needs. So switching a scene to video or animation
dispatches the right engine into a frozen idea. This module is the operator's
explicit way to fix that, and the emphasis is on EXPLICIT.

WHAT IT DOES NOT DO, AND THAT IS THE DESIGN.

**It never writes the scene.** It returns the rewrite; the operator reads it,
edits it, and saves through the update route they already use. A description is
authored creative intent, and a feature that silently replaced an operator's
own words the moment they changed a dropdown would destroy work with no undo
and no diff. The endpoint's only durable write is the audit row that records
that a rewrite was produced.

**It does not move the model.** The rewrite runs on the AD-01 binding for
``storyboard_generation`` -- Llama 3.3 70B, resolved through the same
``get_binding`` the worker calls, so the model here cannot drift from the model
that authored the description in the first place.
``docs/reference-run-2026-08-23-correctness-annotation.md`` section 2 holds
storyboard and transcript on Llama until M3.3 and this obeys it by construction
rather than by a constant someone has to remember to update.

**It dispatches no pipeline stage** -- and it is still guarded by the in-flight
check every dispatch-capable surface carries (Task 3(c)). It consumes capacity
on the same LLM a running Stage 1 or Stage 2 is using, and an operator editing
scenes underneath a live run is editing rows that run is about to overwrite.

THE ENDPOINT AND THE MODEL COME FROM TWO PLACES, DELIBERATELY. The model
identity is AD-01's (``get_binding``). The URL is this container's own
environment, via ``llm_playground.resolve_engine_endpoint`` -- because
``shared.providers.binding`` ships hostname defaults (``http://node-02:8000``)
that the API container's network cannot resolve, which ``llm_playground``
records and ``translation_service`` works around the same way.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

import httpx
from jinja2 import StrictUndefined, Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.prompt import Prompt
from app.models.storyboard_scene import StoryboardScene

logger = logging.getLogger(__name__)

PROMPT_TYPE = "scene_media_adaptation"

#: The three values `SceneUpdate.validate_media_type` accepts, and the only
#: three the orchestrator's dispatch plan knows. Anything else would be grouped
#: into the image branch without a word (`pipeline_orchestrator_v2.py:616`).
#: WP-64's ADAPTATION targets, and DELIBERATELY NOT the same list as
#: `schemas/storyboard.MEDIA_TYPES`, which WP-68 extended with
#: `motion_graphics`. Adapt rewrites a PROSE description for a medium; a motion
#: graphic does not take prose, it takes structured parameters
#: (`{"template": "place_value_split", "number": 23}` in
#: `storyboard_scenes.generation_params`). Offering it here would ask the model
#: to write a description for a renderer that never reads one.
MEDIA_TYPES: Tuple[str, ...] = ("image", "video_clip", "animation")

#: The stage whose AD-01 binding writes storyboards, and therefore the binding
#: that must write a storyboard description's replacement.
STORYBOARD_STAGE = "storyboard_generation"

#: A rewrite is one paragraph. Generous enough that a long, careful description
#: is not clipped, small enough that a runaway completion fails visibly.
MAX_TOKENS = 800

#: Low, on purpose: this is a faithful re-expression of an existing scene in a
#: different medium, not a fresh invention. Same reasoning as translation's 0.2,
#: a little higher because the target IS prose the operator will read.
TEMPERATURE = 0.3

#: One scene, one paragraph, and a human is watching a spinner.
REQUEST_TIMEOUT_SECONDS = 120.0

#: Phrases the active prompt MUST carry before this module will run it. Same
#: discipline as `TranslationService._assert_prompt_carries_contract`: a prompt
#: that has lost the no-text rule produces a rewrite full of drawn digits, and
#: one that has lost the per-medium instructions produces a rewrite that is not
#: an adaptation at all -- and both would be returned to the operator looking
#: exactly like a good one.
CONTRACT_PHRASES: Tuple[str, ...] = (
    "NO TEXT IN THE VISUAL",
    "KEEP THE SUBJECT",
    "WRITE IT FOR THE TARGET MEDIUM",
    "pose reenactment",
)


class AdaptationError(RuntimeError):
    """The adaptation could not be produced, and nothing was written.

    Raised, never returned as text. The route answers 502 or 409 with the
    reason, so "the model said this" stays distinguishable from "the model was
    not reached" -- the distinction the Phase-3 playground stub collapsed and
    WP-61 had to rebuild.
    """


class AdaptationContractError(AdaptationError):
    """The active adaptation prompt does not carry the WP-64 contract."""


def _auth_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("IVGS_VLLM_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def _active_prompt(db: AsyncSession, project_id: UUID) -> Prompt:
    """The project's adaptation prompt if it has one, else the global one.

    Exact-type selection, never "the last one in the list". IVGS-0.4 records
    what happens otherwise.
    """
    for scope in (project_id, None):
        row = await db.scalar(
            select(Prompt)
            .where(
                Prompt.prompt_type == PROMPT_TYPE,
                Prompt.project_id == scope
                if scope is not None
                else Prompt.project_id.is_(None),
                Prompt.scene_id.is_(None),
                Prompt.is_active.is_(True),
            )
            .order_by(Prompt.version.desc())
            .limit(1)
        )
        if row is not None:
            return row
    raise AdaptationError(
        f"no active {PROMPT_TYPE} prompt exists, globally or for this project. "
        "Publish it with `python -m app.scripts.wp64_publish_adaptation_prompt` "
        "inside ivgs-fastapi. Refusing to adapt a description under an "
        "improvised prompt."
    )


def assert_prompt_carries_contract(prompt_text: str) -> None:
    """Refuse to run a prompt that has lost the rules that make it safe."""
    missing = [p for p in CONTRACT_PHRASES if p not in prompt_text]
    if missing:
        raise AdaptationContractError(
            f"the active {PROMPT_TYPE} prompt does not carry the WP-64 "
            f"contract: missing {missing!r}. Without the no-text rule the "
            "rewrite asks an image model to draw digits, which this pipeline "
            "has measured twice ('2? x 23.14'); without the keep-the-subject "
            "and per-medium rules the result is a new scene rather than the "
            "same scene in a different medium. Publish the tracked template "
            "(ivgs-api/seed/default_prompts/scene_media_adaptation.j2) as a new "
            "active version first."
        )


def render_prompt(
    prompt_text: str,
    *,
    project_title: str,
    scene_label: str,
    target_media_type: str,
    current_media_type: str,
    narration_text: str,
    current_description: str,
) -> str:
    """Render the stored template. ``StrictUndefined``, for IVGS-0.4's reason.

    An unset variable raises instead of quietly rendering an empty string. The
    defect that made that lesson expensive was a template rendered with its
    variables unset: Jinja produced empty strings and the transcript vanished
    into a prompt that asked the model to translate nothing into nothing.
    """
    return Template(prompt_text, undefined=StrictUndefined).render(
        project_title=project_title,
        scene_label=scene_label,
        target_media_type=target_media_type,
        current_media_type=current_media_type,
        narration_text=narration_text,
        current_description=current_description,
    )


async def _resolve_binding(db: AsyncSession, project_id: UUID) -> Dict[str, Any]:
    """(model handle, endpoint, binding description) for the storyboard stage.

    AD-01 for the model, this container's environment for the URL. See the
    module docstring for why those are two different questions here.
    """
    from app.services.llm_playground import PlaygroundError, resolve_engine_endpoint
    from shared.providers.factory import get_binding

    try:
        binding = await get_binding(
            STORYBOARD_STAGE, project_id=project_id, tier="prototype", session=db,
        )
    except Exception as exc:
        raise AdaptationError(
            f"could not resolve the {STORYBOARD_STAGE} model binding for "
            f"project {project_id}: {exc}. The adaptation deliberately runs on "
            "the same model that authors storyboards; it does not fall back to "
            "another one."
        ) from exc

    model = str(binding.default_params.get("engine_model") or binding.name)
    try:
        endpoint = resolve_engine_endpoint(binding.engine)
    except PlaygroundError as exc:
        raise AdaptationError(
            f"the {STORYBOARD_STAGE} binding resolved to engine "
            f"{binding.engine!r} and this container has no URL for it: {exc}"
        ) from exc

    return {
        "model": model,
        "endpoint": endpoint.rstrip("/"),
        "binding": binding.describe(),
        "model_id": str(binding.model_id),
        "engine": binding.engine,
    }


async def _call_model(
    prompt: str,
    *,
    endpoint: str,
    model: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> Dict[str, Any]:
    """One chat completion. Raises on anything that is not a usable answer.

    ``max_tokens`` and ``temperature`` default to this module's values, so every
    existing caller is byte-for-byte unchanged. WP-IVGS-09c added the overrides
    for `motion_authoring`, which asks the SAME binding for a much smaller and
    much less creative answer -- one JSON object of template + numbers. Sharing
    this function rather than copying it keeps ONE definition of the ceiling
    check below, which is the part that matters: a truncated answer is not a
    short answer, and a truncated JSON object is not JSON at all.
    """
    ceiling = MAX_TOKENS if max_tokens is None else max_tokens
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": ceiling,
        "temperature": TEMPERATURE if temperature is None else temperature,
    }
    url = f"{endpoint}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=body, headers=_auth_headers())
    except Exception as exc:
        raise AdaptationError(f"adaptation endpoint {url} unreachable: {exc}") from exc

    if resp.status_code != 200:
        raise AdaptationError(
            f"adaptation endpoint {url} returned HTTP {resp.status_code}: "
            f"{resp.text[:300]}"
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise AdaptationError(
            f"adaptation endpoint {url} answered 200 with an unreadable body: {exc}"
        ) from exc

    choices = payload.get("choices") or []
    if not choices:
        raise AdaptationError(f"adaptation endpoint {url} returned no choices")
    choice = choices[0]
    finish = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise AdaptationError(
            f"adaptation endpoint {url} returned an empty completion "
            f"(finish_reason={finish!r})"
        )
    if finish == "length":
        # WP-58's Stage-2 lesson, applied here. A truncated description is not
        # a short description: the end of the sentence is missing and nothing
        # in the text says so. The operator would paste half a shot.
        raise AdaptationError(
            f"the completion hit the output ceiling (max_tokens={ceiling}, "
            "finish_reason='length'). The answer would end mid-sentence; "
            "refusing to offer it."
        )
    return {
        "content": content,
        "finish_reason": finish,
        "usage": payload.get("usage") or {},
        "model": payload.get("model") or model,
    }


def clean_output(raw: str) -> str:
    """Strip the wrappers a chat model puts round a one-paragraph answer.

    The prompt asks for the description and nothing else. Models comply
    imperfectly: a leading "Here is the rewritten description:", a code fence,
    or the whole thing in quotation marks. Those are FORMATTING, not content,
    and leaving them in means the operator pastes them into the scene.

    Deliberately conservative. It removes only wrappers it can identify with
    certainty and never rewrites the prose itself -- an over-eager cleaner that
    ate a legitimate sentence would be a silent content edit, which is the class
    of defect this whole module is built to avoid.
    """
    text = (raw or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        text = "\n".join(lines).strip()

    lowered = text.lower()
    for lead in (
        "here is the rewritten description:",
        "here's the rewritten description:",
        "rewritten description:",
        "adapted description:",
        "visual description:",
    ):
        if lowered.startswith(lead):
            text = text[len(lead):].strip()
            break

    if len(text) >= 2 and text[0] in "\"'“" and text[-1] in "\"'”":
        text = text[1:-1].strip()

    return text


class AdaptationService:
    """Produce a medium-appropriate rewrite of one scene's visual description."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def adapt_description(
        self,
        project_id: UUID,
        scene_id: UUID,
        target_media_type: str,
        *,
        actor: Optional[Any] = None,
        client_ip: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Rewrite this scene's description for ``target_media_type``.

        Returns the payload the modal renders, or ``None`` when the scene does
        not exist in this project -- the route turns that into a 404.

        THE SCENE ROW IS NOT TOUCHED. The only write is the audit entry.
        """
        from app.services.project_service import (
            PipelineAlreadyRunningError,
            active_job,
        )

        target = (target_media_type or "").strip()
        if target not in MEDIA_TYPES:
            raise ValueError(
                f"Invalid target media type '{target_media_type}'. "
                f"Allowed: {', '.join(MEDIA_TYPES)}."
            )

        scene = await self.db.scalar(
            select(StoryboardScene).where(
                StoryboardScene.id == scene_id,
                StoryboardScene.project_id == project_id,
            )
        )
        if scene is None:
            return None

        current_description = (scene.visual_description or "").strip()
        if not current_description:
            raise ValueError(
                f"Scene {scene_id} has no visual description to adapt. There is "
                "nothing to rewrite; write one first, or regenerate the "
                "storyboard."
            )

        # Task 3(c). THE IN-FLIGHT GUARD, and it runs before the model call.
        # This dispatches no pipeline stage, and it is guarded anyway: it
        # consumes capacity on the very LLM a running Stage 1 or Stage 2 is
        # using, and the scene rows an operator is adapting under a live run
        # are rows that run may be about to rewrite. Same question, same
        # answer, same 409 code as every other dispatch-capable surface --
        # `active_job` is the one definition (WP-61 Task 5 / WP-62 Task 6).
        running = await active_job(self.db, project_id)
        if running is not None:
            raise PipelineAlreadyRunningError(
                f"Project {project_id} already has a {running.status} "
                f"{running.job_type} run (job {running.id}). Adapting a scene "
                "description consumes the same LLM the run is using, and the "
                "scene it rewrites may be one the run is about to overwrite. "
                "Wait for it to finish, or cancel it.",
                job_id=running.id,
                job_type=running.job_type,
                status=running.status,
            )

        project = await self.db.scalar(
            select(Project).where(Project.id == project_id)
        )
        if project is None:
            return None

        prompt_row = await _active_prompt(self.db, project_id)
        assert_prompt_carries_contract(prompt_row.prompt_text)

        current_media_type = (scene.media_type or "image").strip() or "image"
        scene_label = f"scene index {scene.scene_index}"
        if getattr(scene, "title", None):
            scene_label = f"{scene_label} - {scene.title}"

        rendered = render_prompt(
            prompt_row.prompt_text,
            project_title=project.name or "",
            scene_label=scene_label,
            target_media_type=target,
            current_media_type=current_media_type,
            narration_text=(scene.narration_text or "").strip(),
            current_description=current_description,
        )

        resolved = await _resolve_binding(self.db, project_id)
        answer = await _call_model(
            rendered, endpoint=resolved["endpoint"], model=resolved["model"],
        )
        adapted = clean_output(answer["content"])
        if not adapted:
            raise AdaptationError(
                "the model returned only formatting and no description."
            )

        # Task 3(d). The adaptation is an authored change to creative intent,
        # so it is recorded even though the scene row is untouched: "who asked
        # the model to rewrite scene 4 for video, under which prompt version,
        # and what did it say" is a question that has to be answerable
        # afterwards, whether or not the operator went on to save it.
        self.db.add(
            AuditLog(
                user_id=getattr(actor, "id", None),
                action_type="SCENE_DESCRIPTION_ADAPTED",
                resource_type="scenes",
                resource_id=scene_id,
                before_payload={
                    "project_id": str(project_id),
                    "scene_index": scene.scene_index,
                    "media_type": current_media_type,
                    "visual_description": current_description,
                },
                after_payload={
                    "target_media_type": target,
                    "adapted_description": adapted,
                    "prompt_id": str(prompt_row.id),
                    "prompt_version": prompt_row.version,
                    "model": answer["model"],
                    "binding": resolved["binding"],
                    "usage": answer["usage"],
                    # The whole point of the feature, recorded as a fact rather
                    # than left to be inferred from the absence of a scene diff.
                    "scene_written": False,
                    "note": (
                        "Proposal returned to the operator. The scene row was "
                        "NOT modified by this action; saving is a separate "
                        "PATCH the operator makes after reading it."
                    ),
                },
                client_ip=client_ip,
            )
        )
        await self.db.commit()

        logger.info(
            "Scene description adapted: project=%s scene=%s %s -> %s "
            "prompt=v%s model=%s (scene row NOT written)",
            project_id, scene_id, current_media_type, target,
            prompt_row.version, answer["model"],
        )

        return {
            "scene_id": scene_id,
            "scene_index": scene.scene_index,
            "current_media_type": current_media_type,
            "target_media_type": target,
            "current_description": current_description,
            "adapted_description": adapted,
            "prompt_version": prompt_row.version,
            "prompt_id": prompt_row.id,
            "model": answer["model"],
            "binding": resolved["binding"],
            "scene_written": False,
            "generated_at": datetime.now(timezone.utc),
        }
