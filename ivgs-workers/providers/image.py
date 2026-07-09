"""ARCH-1 image engine builder (``comfyui``).

Wraps ``FluxClient`` (which drives ComfyUI and already implements the shared
``ImageProvider`` ABC) behind the selection-aware factory. Engine key is
``comfyui`` to match the Model Store (Appendix AD-B: ``flux1-dev`` /
``flux1-schnell`` / ``sdxl-1.0`` all have ``engine=comfyui``); the concrete
checkpoint is the engine-native id from the binding.

``fallback_url=None`` — cross-endpoint fallback is an AD-01 selection
concern, not a client trick (mirrors the Stage-6 exemplar).
"""
from __future__ import annotations

from typing import Any

from clients.flux_client import FluxClient

from providers._common import engine_model_id, resolve_timeout
from shared.providers import ModelBinding, register_engine_builder


def build_comfyui(binding: ModelBinding, **kwargs: Any) -> FluxClient:
    timeout = resolve_timeout(binding, kwargs, default=300.0)
    return FluxClient(
        base_url=binding.endpoint,
        model=engine_model_id(binding),
        timeout=timeout,
        fallback_url=None,  # ARCH-1: fallback is a selection, not a client trick
        **kwargs,
    )


def register() -> None:
    register_engine_builder("comfyui", build_comfyui)
