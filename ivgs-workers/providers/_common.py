"""Shared helpers for the ARCH-1 worker-side engine builders.

Keeps the per-engine builder modules (``llm``, ``image``, ``video``, ``tts``)
DRY without coupling them: each maps an AD-01 ``ModelBinding`` to a concrete
engine client, and the two concerns every builder shares live here.

**Store name vs engine-native id (AD-01).** ``binding.name`` is the Model
Store's clean name (e.g. ``flux1-dev``); the engine wants its native handle
(e.g. ``flux1-dev-fp8.safetensors`` for a ComfyUI checkpoint, or a served
model tag for vLLM). We decouple the two: the seed (AD-01.7) may set
``default_params["engine_model"]``; absent that, the store name is used
verbatim. Store names never have to encode engine internals.
"""
from __future__ import annotations

from typing import Any

from shared.providers.binding import ModelBinding


def engine_model_id(binding: ModelBinding) -> str:
    """Engine-native model handle for ``binding`` (see module docstring)."""
    override = binding.default_params.get("engine_model")
    return str(override) if override else binding.name


def resolve_timeout(
    binding: ModelBinding, kwargs: dict[str, Any], *, default: float
) -> float:
    """Timeout precedence: explicit builder kwarg -> seed
    ``default_params["timeout_seconds"]`` -> the engine client's default.

    Pops ``timeout`` from ``kwargs`` so the caller can splat the remainder
    into the client constructor without a duplicate-arg clash.
    """
    explicit = kwargs.pop("timeout", None)
    if explicit is not None:
        return float(explicit)
    seeded = binding.default_params.get("timeout_seconds")
    if seeded is not None:
        return float(seeded)
    return float(default)
