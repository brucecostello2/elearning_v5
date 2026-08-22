"""Exact-type selection of a resolved prompt (IVGS-0.4).

The workers request ``GET /projects/{id}/prompts?prompt_type=<type>``. Before
IVGS-0.4 the endpoint ignored that parameter and returned all ten types, and the
worker classified them by testing whether the substring ``"system"`` appeared in
the type name. No PromptType contains it, so every prompt fell through to the
"user prompt" branch and the LAST enum member — TRANSLATION — won. Its variables
(``target_language``, ``narration_text``) are never passed, Jinja rendered them
empty, and the transcript vanished.

This module refuses to guess. It takes the requested type and returns only a
prompt that declares exactly that type; anything else raises.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import structlog

logger = structlog.get_logger("ivgs.prompts.selection")


class PromptTypeMismatchError(RuntimeError):
    """The API returned a prompt whose declared type is not the one requested."""


def _as_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
    return []


def _select_prompt_text(
    payload: Any,
    requested_type: str,
    *,
    strict: bool = True,
) -> Optional[str]:
    """Return the prompt text for ``requested_type``, or None if absent.

    Raises ``PromptTypeMismatchError`` when the response carries prompts and
    NONE of them is the requested type — that is the endpoint ignoring the
    filter, which is exactly the failure this replaces. Silently substituting
    another type is never acceptable: it is how the translation template came
    to stand in for Stage 1's.
    """
    prompts = _as_list(payload)
    if not prompts:
        return None

    exact = [p for p in prompts if p.get("prompt_type") == requested_type]
    if exact:
        if len(prompts) > len(exact):
            logger.warning(
                "prompt_filter_not_honoured_by_api",
                requested_type=requested_type,
                returned_types=sorted(
                    {str(p.get("prompt_type")) for p in prompts}
                ),
                detail=(
                    "the endpoint returned more than the requested type; "
                    "selecting by exact type locally"
                ),
            )
        return exact[0].get("prompt_text") or None

    returned = sorted({str(p.get("prompt_type")) for p in prompts})
    if strict:
        raise PromptTypeMismatchError(
            f"requested prompt_type {requested_type!r} but the API returned "
            f"only {returned}. Refusing to substitute another prompt type."
        )
    logger.error(
        "prompt_type_not_returned",
        requested_type=requested_type,
        returned_types=returned,
    )
    return None


def iter_prompt_types(payload: Any) -> Iterable[str]:
    """Declared types in a prompts response (diagnostic helper)."""
    return (str(p.get("prompt_type")) for p in _as_list(payload))
