"""The Prompt Playground's model call. WP-45 Task 3, site 8.

``PromptService.test_prompt`` rendered the template, validated its Jinja2, and
then returned a hand-written string:

    "[Phase 3 stub] This is a placeholder response. In Phase 5, this will call
     the self-hosted vLLM/Ollama model. Model requested: {model_id}."

That text was returned in the ``model_response`` field, in the same shape a real
completion would occupy, with a 200. An operator tuning a storyboard prompt was
reading a sentence about the tuning tool instead of the model's answer — and
because the prefix is only visible if you read the whole response, the surface
looked like it worked. It is the same defect as the other seven, in a different
costume: the response was well-formed and empty of the thing it claimed to be.

Endpoint resolution is deliberately NOT ``shared.providers.binding.resolve_endpoint``.
That helper's shipped default for vllm is ``http://node-02:8000``, a hostname the
API container's network cannot resolve — the workers on node-02 set
``IVGS_VLLM_URL`` explicitly for exactly this reason (WP-34 S6). The API has
``VLLM_PRIMARY_URL`` / ``VLLM_SECONDARY_URL`` / ``VLLM_MIDSIZE_URL`` / ``OLLAMA_URL``
in its own environment, composed from ``NODE_0x_IP``, so those are read first and
the IVGS_* overrides still win if an operator sets one. Nothing here invents a
default: an engine with no configured URL is an error naming the variable, not a
guess at a hostname.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# engine -> the env vars that may carry its base URL, most specific first.
ENGINE_URL_ENV: Dict[str, tuple[str, ...]] = {
    "vllm": (
        "IVGS_VLLM_URL",
        "VLLM_PRIMARY_URL",
        "VLLM_SECONDARY_URL",
        "VLLM_MIDSIZE_URL",
    ),
    "ollama": ("IVGS_OLLAMA_URL", "OLLAMA_URL"),
}

# Engines that speak the OpenAI-style /v1/chat/completions API. Same set as
# ivgs-workers/utils/llm_binding.CHAT_ENGINES, and for the same reason: a
# playground call aimed at ComfyUI or Coqui is a category error, not a timeout.
CHAT_ENGINES = frozenset(ENGINE_URL_ENV)

DEFAULT_ENGINE = "vllm"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.7
# The playground is interactive: an operator is watching. A long generation is
# better cut off with a clear message than left hanging behind a proxy timeout.
REQUEST_TIMEOUT_SECONDS = 120.0


class PlaygroundError(RuntimeError):
    """The model could not be called, or answered with an error.

    Raised rather than returned as text, so the route can answer 502 and the
    operator can tell "the model said this" from "the model was not reached".
    Conflating those two is what the stub did.
    """


def resolve_engine_endpoint(engine: str) -> str:
    """Base URL for ``engine``, from this container's own environment."""
    candidates = ENGINE_URL_ENV.get(engine)
    if candidates is None:
        raise PlaygroundError(
            f"engine '{engine}' does not serve chat completions. "
            f"Playground engines: {sorted(CHAT_ENGINES)}"
        )
    for var in candidates:
        value = os.environ.get(var, "").strip()
        if value:
            return value.rstrip("/")
    raise PlaygroundError(
        f"no endpoint configured for engine '{engine}'. Set one of: "
        f"{', '.join(candidates)}"
    )


def _auth_headers(engine: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if engine == "vllm":
        key = os.environ.get("IVGS_VLLM_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    return headers


async def run_completion(
    prompt: str,
    model_id: str,
    engine: str = DEFAULT_ENGINE,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send ``prompt`` to ``model_id`` and return the model's own answer.

    Returns ``{"model_response": str, "usage": dict, "engine": str,
    "endpoint": str, "finish_reason": str}``.

    Every failure path raises ``PlaygroundError`` with the reason in it. There is
    no branch that returns a plausible-looking string when the model was not
    reached, which is the whole point of this module.
    """
    params = dict(parameters or {})
    endpoint = resolve_engine_endpoint(engine)

    body: Dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(params.pop("max_tokens", DEFAULT_MAX_TOKENS)),
        "temperature": float(params.pop("temperature", DEFAULT_TEMPERATURE)),
    }
    for passthrough in ("top_p", "top_k", "presence_penalty", "frequency_penalty", "stop", "seed"):
        if passthrough in params:
            body[passthrough] = params.pop(passthrough)
    # Anything left is sent as-is. The playground exists to try things; silently
    # dropping a parameter the operator typed would repeat this package's theme.
    body.update(params)

    url = f"{endpoint}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=body, headers=_auth_headers(engine))
    except httpx.TimeoutException as exc:
        raise PlaygroundError(
            f"{engine} at {endpoint} did not answer within "
            f"{REQUEST_TIMEOUT_SECONDS:.0f}s: {exc}"
        ) from exc
    except Exception as exc:
        raise PlaygroundError(f"could not reach {engine} at {endpoint}: {exc}") from exc

    if resp.status_code != 200:
        # The server's own message, not a paraphrase. "model not found" and
        # "context length exceeded" are things the operator can act on.
        raise PlaygroundError(
            f"{engine} at {endpoint} returned HTTP {resp.status_code}: "
            f"{resp.text[:500]}"
        )

    try:
        payload = resp.json()
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise PlaygroundError(
            f"{engine} at {endpoint} answered 200 with a body this client "
            f"could not read ({exc}): {resp.text[:300]}"
        ) from exc

    usage = payload.get("usage") or {}
    logger.info(
        "Playground completion: engine=%s model=%s endpoint=%s "
        "prompt_tokens=%s completion_tokens=%s finish=%s",
        engine, model_id, endpoint,
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
        choice.get("finish_reason"),
    )
    return {
        "model_response": content or "",
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "engine": engine,
        "endpoint": endpoint,
        "finish_reason": choice.get("finish_reason") or "",
    }
