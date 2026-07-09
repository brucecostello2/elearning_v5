"""ARCH-1 TTS engine builders (``coqui``, ``kokoro``).

Both clients already implement the shared ``TTSProvider`` ABC and take a base
URL; the builders bind them to the selection's endpoint. TTS model identity
is fixed per engine (voice is a per-call parameter, not a served-model
choice), so no engine-model handle is threaded here — unlike the LLM/image/
video builders.

``coqui`` supports a client-side ``fallback_url``; ARCH-1 forces it off
(fallback is a selection concern). ``kokoro`` has no fallback parameter.
"""
from __future__ import annotations

from typing import Any

from clients.coqui_client import CoquiClient
from clients.kokoro_client import KokoroClient

from providers._common import resolve_timeout
from shared.providers import ModelBinding, register_engine_builder


def build_coqui(binding: ModelBinding, **kwargs: Any) -> CoquiClient:
    timeout = resolve_timeout(binding, kwargs, default=120.0)
    return CoquiClient(
        base_url=binding.endpoint,
        timeout=timeout,
        fallback_url=None,  # ARCH-1: fallback is a selection, not a client trick
        **kwargs,
    )


def build_kokoro(binding: ModelBinding, **kwargs: Any) -> KokoroClient:
    timeout = resolve_timeout(binding, kwargs, default=120.0)
    return KokoroClient(
        base_url=binding.endpoint,
        timeout=timeout,
        **kwargs,
    )


def register() -> None:
    register_engine_builder("coqui", build_coqui)
    register_engine_builder("kokoro", build_kokoro)
