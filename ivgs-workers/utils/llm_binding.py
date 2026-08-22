"""Resolve the AD-01 binding for an auxiliary chat-LLM call (IVGS-0.2).

Stages 3 and 5 each make a text call to a chat LLM that is not the stage's own
model: Stage 3 writes the FLUX prompt, Stage 5 rewrites narration for the TTS
engine. Both used to call ``config.get_vllm_config_for_stage(...)`` — the env
profile — while the stage reported the AD-01 binding it had selected for its
real work. The run and the record disagreed, and Stage 5 asked for the
``image_generation`` profile to do a text job.

Those two calls have no ModelStage of their own (AD-01.5.2 has nine, none of
them "prompt writer"), so each borrows the chat-LLM stage whose work it most
resembles. The borrow is deliberate and is named at the call site.

The binding is guaranteed to exist by the time either stage runs: Stage 3
follows Stage 2, which cannot complete without a ``storyboard_generation``
binding, and Stage 5 follows Stage 1, which cannot complete without a
``transcript_refinement`` one.
"""
from __future__ import annotations

from uuid import UUID

import structlog

from shared.providers.binding import ModelBinding
from shared.providers.factory import get_binding

logger = structlog.get_logger("ivgs.providers.text_llm")

# Engines that speak the OpenAI-style /v1/chat/completions API the stage tasks
# use. A binding on any other engine cannot serve a chat call.
CHAT_ENGINES = frozenset({"vllm", "ollama"})


class TextLLMBindingError(RuntimeError):
    """The borrowed stage resolved to a model that cannot serve a chat call."""


async def resolve_text_llm_binding(
    borrowed_stage: str,
    *,
    project_id: str,
    tier: str,
    purpose: str,
) -> ModelBinding:
    """Return the chat-LLM binding for an auxiliary text call.

    ``borrowed_stage`` is the AD-01 ModelStage whose model this call reuses;
    ``purpose`` names the actual job for the log line and the error message.

    Raises ``TextLLMBindingError`` if the resolved binding is not a chat engine.
    Failing here is the point: pointing a chat call at a ComfyUI or Coqui
    endpoint is what the old env-config fallback did silently.
    """
    binding = await get_binding(
        borrowed_stage, project_id=UUID(project_id), tier=tier,
    )
    if binding.engine not in CHAT_ENGINES:
        raise TextLLMBindingError(
            f"{purpose}: the {borrowed_stage!r} binding resolved to "
            f"{binding.name!r} on engine {binding.engine!r}, which cannot "
            f"serve a chat completion. Expected one of "
            f"{', '.join(sorted(CHAT_ENGINES))}."
        )
    logger.info(
        "text_llm_bound",
        purpose=purpose,
        borrowed_stage=borrowed_stage,
        binding=binding.describe(),
    )
    return binding
