"""Translation: the first execution, and the FAIL-AND-FLAG contract. WP-61 Task 3.

WHAT WAS HERE BEFORE: NOTHING, and that is the finding, not the preamble.

Measured 2026-08-26 before a line of this was written:

* ``prompts`` holds exactly one ``translation`` row — ``e16b6502-…``, global,
  active, version 1, created 2026-05-23 — and **nothing has ever rendered it**.
  Its only appearance in worker code is ``utils/prompt_selection.py``'s
  docstring, recording the IVGS-0.4 defect where it was accidentally selected
  IN PLACE OF Stage 1's prompt and rendered with empty variables.
* ``language_variants`` holds 16 rows and every one is ``pending``.
* ``ivgs-workers/tasks/`` contains no translation task. ``grep -rn 'translat'``
  over that tree returns five hits and all five are prose.
* ``LanguageService.retry_variant`` (``language_service.py``) says so in as many
  words: *"IVGS has no translation stage… a retried variant re-renders the
  SOURCE narration with the target language's voice."*

So the executing body was ABSENT, not frozen. Task 3(a) rules on that case: STOP
that half and report — **do not write a new pipeline stage body pre-cutover.**

WHAT THIS MODULE IS, THEN. It is the *consuming path*, which Task 3(a) puts in
scope regardless: prompt rendering, endpoint routing, the marker contract, the
strip, and the state transition. It is called synchronously from the API, like
``app/api/v1/clip.py``'s scorer proxy. It registers no Celery task, appears in
no ``STAGE_TASK_MAP``, and is dispatched by no orchestrator — because the eighth
stage does not exist and inventing one here would be exactly the pre-cutover
pipeline body the ruling forbids. When translation becomes a Temporal activity
after M3.3, that activity calls ``translate_variant``; it does not reimplement it.

THE CONTRACT, RULED (Task 3(c)). Measured 2026-08-25 against the live prompt on
Qwen: the model appended a correction in **all four** target languages, because
scene 5 of the reference project genuinely teaches 10x3=30, 10x2=20 => "320"
written as 230. Spanish came back with *"…es 320, pero en el paso anterior la
escribimos como 230, lo cual es incorrecto."* That is a **divergence that exists
only in languages the team cannot read** — the source narration says one thing
and the deliverable says another, and nobody who reads only English would ever
see it.

The prompt is amended to forbid correcting, and to require a marker line
INSTEAD. This module strips that marker out of the deliverable and sets the
variant to ``flagged`` rather than ``complete``.

**A flagged translation is a DELIVERABLE, not a failure.** ``failed`` means
there is no text. ``flagged`` means there is text and a human must look at it.

WHY THE PROMPT IS CHECKED BEFORE THE MODEL IS CALLED. ``_assert_prompt_carries_contract``
refuses to run a translation whose prompt does not ask for the marker. A prompt
without the contract produces a model that corrects silently and inline, which
is the exact defect this task exists to close — and the strip below would find
nothing to strip and report ``complete`` with a corrected text inside it. A
guard that only runs after the damage is not a guard.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

import httpx
from jinja2 import StrictUndefined, Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.language_variant import LanguageVariant
from app.models.project import Project
from app.models.prompt import Prompt
from app.models.storyboard_scene import StoryboardScene

logger = logging.getLogger(__name__)

#: The marker line the amended prompt asks for. Literal, anchored to the start
#: of a line, case-sensitive: a marker the model mangled must NOT be silently
#: accepted, because a half-recognised marker left inside the deliverable is
#: worse than no marker at all.
FLAG_MARKER = "IVGS-TRANSLATION-FLAG:"

#: One compiled matcher, used for BOTH the detection and the strip, so the two
#: can never disagree about what a marker is. ``^`` with MULTILINE: the prompt
#: requires the marker to begin a line, and a sentence that merely mentions the
#: token mid-paragraph is not a marker.
_FLAG_RE = re.compile(
    rf"^[ \t]*{re.escape(FLAG_MARKER)}[ \t]*(?P<reason>.*)$",
    re.MULTILINE,
)

#: Env vars that may carry node-05's Qwen endpoint, most specific first.
#:
#: The first name is the SAME variable ``shared.providers.binding`` resolves for
#: the ``(vllm, translation)`` pair, and a test pins that they stay identical.
#: Two modules that route the same call to different hosts because one of them
#: was renamed is a defect this codebase has already had.
#:
#: Endpoint resolution here does NOT go through ``binding.resolve_endpoint``,
#: for the reason ``llm_playground.py`` records: that helper ships hostname
#: defaults (``http://node-05:8000``) which the API container's network cannot
#: resolve. The API is given real URLs composed from ``NODE_05_IP``. Nothing
#: here invents a default — an unconfigured endpoint is an error naming the
#: variables, never a guess at a hostname.
TRANSLATION_URL_ENV: Tuple[str, ...] = (
    "IVGS_VLLM_TRANSLATION_URL",
    "VLLM_TRANSLATION_URL",
)

#: Qwen3.8-27B-FP8 as served on node-05 (`--served-model-name`).
DEFAULT_MODEL_NAME = "qwen38-27b"

#: Per-request, and it is worth 45 seconds. Measured 2026-08-25 on the
#: storyboard-shaped prompt: 53.9s with thinking on, 9.3s with it off, and the
#: JSON still parsed. Translation has no use for chain-of-thought — it is asked
#: to render text faithfully, not to reason about it.
THINKING_OFF: Dict[str, Any] = {"enable_thinking": False}

#: A whole transcript can be long and the caller is a human waiting on a page.
#: Long enough for a 17-scene project, short enough to fail visibly.
REQUEST_TIMEOUT_SECONDS = 300.0

#: Generous but bounded. A translation that hits the ceiling comes back with
#: ``finish_reason == "length"`` and is treated as a failure, not truncated
#: quietly into a deliverable — the WP-58 Stage-2 lesson, applied here.
MAX_TOKENS = 4096

#: Faithful rendering, not creative writing.
TEMPERATURE = 0.2

#: BCP-47 -> the name the prompt puts in front of the model. A code alone
#: ("es-ES") is a weaker instruction than a language name, and the 2026-08-25
#: evaluation used names.
LANGUAGE_NAMES: Dict[str, str] = {
    "en-US": "English (United States)",
    "en-GB": "English (United Kingdom)",
    "es-ES": "Spanish (Spain)",
    "fr-FR": "French (France)",
    "de-DE": "German (Germany)",
    "zh-CN": "Chinese (Simplified, China)",
    "ja-JP": "Japanese (Japan)",
    "ar-SA": "Arabic (Saudi Arabia)",
}


class TranslationError(RuntimeError):
    """The translation could not be produced.

    Raised, never returned as text. The route answers 502 or 409 with the
    reason, so "the model said this" is distinguishable from "the model was not
    reached" — the distinction the Phase-3 playground stub collapsed.
    """


class TranslationContractError(TranslationError):
    """The active translation prompt does not carry the fail-and-flag contract.

    Deliberately a REFUSAL rather than a warning. Running a translation under
    the old prompt is how a silent in-language correction gets written into a
    deliverable and recorded as `complete`.
    """


def resolve_translation_endpoint() -> str:
    """node-05's Qwen base URL, from this container's own environment."""
    for var in TRANSLATION_URL_ENV:
        value = os.environ.get(var, "").strip()
        if value:
            return value.rstrip("/")
    raise TranslationError(
        "no endpoint configured for translation. Set one of: "
        f"{', '.join(TRANSLATION_URL_ENV)}. This is node-05's Qwen "
        "(vllm-qwen, port 8000); see ivgs-infra/docker-compose.llm.node05.yml."
    )


def _auth_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("IVGS_VLLM_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def split_flag(raw: str) -> Tuple[str, Optional[str]]:
    """Split model output into (deliverable text, flag reason or None).

    The marker is removed from the deliverable **whether or not** the caller
    does anything with the reason. That is the ruled contract: the marker is
    machine-readable metadata and must never reach a viewer.

    More than one marker is tolerated on the STRIP side and reported as one
    reason joined by '; '. The prompt asks for at most one; a model that emits
    two must not thereby leave one embedded in the text.
    """
    reasons = [
        m.group("reason").strip()
        for m in _FLAG_RE.finditer(raw)
        if m.group("reason").strip()
    ]
    # A marker with an empty reason is still a marker: it means the model
    # doubted the source and said nothing useful about why, which is a flag.
    marker_present = bool(_FLAG_RE.search(raw))
    cleaned = _FLAG_RE.sub("", raw)
    # Collapse the blank line the removed marker leaves behind, then trim.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not marker_present:
        return cleaned, None
    return cleaned, "; ".join(reasons) if reasons else "(no reason given)"


def _assert_prompt_carries_contract(prompt_text: str) -> None:
    """Refuse to translate under a prompt that does not ask for the marker."""
    if FLAG_MARKER not in prompt_text:
        raise TranslationContractError(
            "the active translation prompt does not carry the WP-61 "
            f"fail-and-flag contract: it never mentions {FLAG_MARKER!r}. "
            "Under that prompt the model corrects the source silently and "
            "inline -- measured 2026-08-25, in all four target languages -- "
            "and this path would record the corrected text as 'complete'. "
            "Publish the amended prompt (ivgs-api/seed/default_prompts/"
            "translation.j2) as a new active version first."
        )


async def _active_translation_prompt(db: AsyncSession, project_id: UUID) -> Prompt:
    """The project's translation prompt if it has one, else the global one.

    Exact-type selection, never "the last one in the list". IVGS-0.4 records
    what happens otherwise: the worker classified prompts by testing for the
    substring "system" in the type name, no type contains it, and the LAST enum
    member -- TRANSLATION -- won every time and stood in for Stage 1's prompt.
    """
    for project_scope in (project_id, None):
        row = await db.scalar(
            select(Prompt).where(
                Prompt.prompt_type == "translation",
                Prompt.project_id == project_scope
                if project_scope is not None
                else Prompt.project_id.is_(None),
                Prompt.scene_id.is_(None),
                Prompt.is_active.is_(True),
            ).order_by(Prompt.version.desc()).limit(1)
        )
        if row is not None:
            return row
    raise TranslationError(
        "no active translation prompt exists, globally or for this project"
    )


def render_prompt(
    prompt_text: str,
    *,
    project_title: str,
    target_language: str,
    narration_text: str,
) -> str:
    """Render the stored Jinja2 template.

    ``StrictUndefined`` on purpose. The IVGS-0.4 defect that made this template
    famous was it being rendered with `target_language` and `narration_text`
    UNSET -- Jinja quietly produced empty strings and the transcript vanished.
    An unset variable now raises instead of producing a prompt that asks the
    model to translate nothing into nothing.
    """
    template = Template(prompt_text, undefined=StrictUndefined)
    return template.render(
        project_title=project_title,
        target_language=target_language,
        narration_text=narration_text,
    )


async def _call_qwen(prompt: str, *, endpoint: str, model: str) -> Dict[str, Any]:
    """One chat completion against node-05's Qwen. Raises on anything else."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        # MEASURED, not chosen: 53.9s -> 9.3s on the storyboard-shaped prompt,
        # output still parsed. vLLM must have been started with
        # `--reasoning-parser qwen3` for this to be honoured; without it ~1400
        # tokens of chain-of-thought land in `content` instead.
        "chat_template_kwargs": THINKING_OFF,
    }
    url = f"{endpoint}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=body, headers=_auth_headers())
    except Exception as exc:
        raise TranslationError(f"translation endpoint {url} unreachable: {exc}") from exc

    if resp.status_code != 200:
        raise TranslationError(
            f"translation endpoint {url} returned HTTP {resp.status_code}: "
            f"{resp.text[:300]}"
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise TranslationError(
            f"translation endpoint {url} answered 200 with an unreadable body: {exc}"
        ) from exc

    choices = payload.get("choices") or []
    if not choices:
        raise TranslationError(f"translation endpoint {url} returned no choices")
    choice = choices[0]
    finish = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise TranslationError(
            f"translation endpoint {url} returned an empty completion "
            f"(finish_reason={finish!r})"
        )
    if finish == "length":
        # WP-58's Stage-2 lesson. A truncated translation is not a short
        # translation: the tail is missing and nothing in the text says so.
        raise TranslationError(
            "the translation hit the output ceiling "
            f"(max_tokens={MAX_TOKENS}, finish_reason='length'). The "
            "deliverable would be silently truncated; refusing to store it."
        )
    return {
        "content": content,
        "finish_reason": finish,
        "usage": payload.get("usage") or {},
        "model": payload.get("model") or model,
    }


class TranslationService:
    """Translate one language variant's scene narration, under the ruled contract."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _scenes(self, project_id: UUID) -> List[StoryboardScene]:
        rows = await self.db.execute(
            select(StoryboardScene)
            .where(StoryboardScene.project_id == project_id)
            .order_by(StoryboardScene.scene_index)
        )
        return list(rows.scalars().all())

    async def translate_variant(
        self,
        project_id: UUID,
        variant_id: UUID,
    ) -> Optional[LanguageVariant]:
        """Translate every scene of ``project_id`` into the variant's language.

        Returns the updated variant, or None when it does not exist.

        STATE, and it is the whole ruling:

            no marker on any scene   -> ``complete``
            a marker on any scene    -> ``flagged``, markers captured,
                                        deliverable text free of them
            anything raised          -> ``failed``, with the reason on the row

        The scenes are translated ONE AT A TIME rather than as one blob. Two
        reasons, both measured: the reference project is 18 scenes and a single
        4096-token completion would have hit the ceiling, and a per-scene call
        attributes a flag to the scene that caused it. "Something in this
        project looks wrong" is not an actionable flag.
        """
        variant = await self.db.scalar(
            select(LanguageVariant).where(
                LanguageVariant.id == variant_id,
                LanguageVariant.project_id == project_id,
            )
        )
        if variant is None:
            return None

        if variant.state == "processing":
            raise TranslationError(
                f"variant {variant_id} is already being translated"
            )

        project = await self.db.scalar(
            select(Project).where(Project.id == project_id)
        )
        if project is None:
            return None

        scenes = await self._scenes(project_id)
        translatable = [
            s for s in scenes
            if isinstance(s.narration_text, str) and s.narration_text.strip()
        ]
        if not translatable:
            raise TranslationError(
                f"project {project_id} has no scene narration to translate"
            )

        prompt_row = await _active_translation_prompt(self.db, project_id)
        _assert_prompt_carries_contract(prompt_row.prompt_text)

        endpoint = resolve_translation_endpoint()
        model = os.environ.get(
            "IVGS_TRANSLATION_MODEL", ""
        ).strip() or DEFAULT_MODEL_NAME
        language_name = LANGUAGE_NAMES.get(
            variant.language_code, variant.language_code
        )

        variant.state = "processing"
        await self.db.commit()

        scene_results: List[Dict[str, Any]] = []
        flags: List[Dict[str, Any]] = []
        try:
            for scene in translatable:
                rendered = render_prompt(
                    prompt_row.prompt_text,
                    project_title=project.name or "",
                    target_language=language_name,
                    narration_text=scene.narration_text,
                )
                answer = await _call_qwen(
                    rendered, endpoint=endpoint, model=model,
                )
                text, reason = split_flag(answer["content"])
                if not text:
                    raise TranslationError(
                        f"scene {scene.scene_index} came back as a marker and "
                        "nothing else; there is no deliverable to store"
                    )
                scene_results.append(
                    {
                        "scene_index": scene.scene_index,
                        "scene_id": str(scene.id),
                        "text": text,
                    }
                )
                if reason is not None:
                    flags.append(
                        {
                            "scene_index": scene.scene_index,
                            "scene_id": str(scene.id),
                            "reason": reason,
                            "marker": FLAG_MARKER,
                        }
                    )
        except Exception as exc:
            variant.state = "failed"
            await self.db.commit()
            logger.error(
                "translation_failed variant=%s lang=%s error=%s",
                variant_id, variant.language_code, exc,
            )
            raise

        variant.translation = {
            "language_code": variant.language_code,
            "language_name": language_name,
            "scenes": scene_results,
            "model": model,
            "endpoint": endpoint,
            "prompt_id": str(prompt_row.id),
            "prompt_version": prompt_row.version,
            "enable_thinking": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        variant.translation_flags = flags or None
        # THE RULING, in one line. A marker anywhere means the deliverable is
        # not `complete`, however good the rest of it is.
        variant.state = "flagged" if flags else "complete"
        await self.db.commit()
        await self.db.refresh(variant)

        logger.info(
            "translation_finished variant=%s lang=%s scenes=%d flags=%d "
            "state=%s model=%s",
            variant_id, variant.language_code, len(scene_results), len(flags),
            variant.state, model,
        )
        return variant
