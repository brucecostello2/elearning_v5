"""ARCH-1 video engine builder (``cogvideox``).

Wraps ``CogVideoXClient`` (already implements the shared ``VideoProvider``
ABC) behind the selection-aware factory. The binding supplies endpoint and
the engine-native model id.

``fallback_url=None`` — fallback is an AD-01 selection concern, not a client
trick (mirrors the Stage-6 exemplar).
"""
from __future__ import annotations

from typing import Any

from clients.cogvideox_client import CogVideoXClient

from providers._common import engine_model_id, resolve_timeout
from shared.providers import ModelBinding, register_engine_builder


def build_cogvideox(binding: ModelBinding, **kwargs: Any) -> CogVideoXClient:
    timeout = resolve_timeout(binding, kwargs, default=1800.0)
    return CogVideoXClient(
        base_url=binding.endpoint,
        model=engine_model_id(binding),
        timeout=timeout,
        fallback_url=None,  # ARCH-1: fallback is a selection, not a client trick
        **kwargs,
    )


def register() -> None:
    register_engine_builder("cogvideox", build_cogvideox)
