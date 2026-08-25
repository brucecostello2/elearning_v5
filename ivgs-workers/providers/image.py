"""ARCH-1 ComfyUI engine builder (``comfyui``).

Wraps ``FluxClient`` (which drives ComfyUI and already implements the shared
``ImageProvider`` ABC) behind the selection-aware factory. Engine key is
``comfyui`` to match the Model Store (Appendix AD-B: ``flux1-dev`` /
``flux1-schnell`` / ``sdxl-1.0`` all have ``engine=comfyui``); the concrete
checkpoint is the engine-native id from the binding.

``fallback_url=None`` — cross-endpoint fallback is an AD-01 selection
concern, not a client trick (mirrors the Stage-6 exemplar).

**WP-46 — one engine key, two provider shapes.** ComfyUI is a graph runner,
not a model, and MBCP registers Wan2.2-Animate under this same ``comfyui``
key (its SSOT value). An animation binding therefore arrives here and must not
be handed a ``FluxClient``: the two drive different graphs against different
instances. The registry is keyed by engine alone (``factory._BUILDERS``), so
the discrimination happens on ``binding.stage`` — the one other fact the
binding carries that distinguishes them. A stage-aware registry key is the
proper fix and is a follow-on; this keeps ``build_provider`` honest today.
"""
from __future__ import annotations

from typing import Any

from clients.flux_client import FluxClient

from providers._common import engine_model_id, resolve_timeout
from shared.providers import ModelBinding, register_engine_builder


def build_comfyui(binding: ModelBinding, **kwargs: Any) -> Any:
    if binding.stage == "animation_generation":
        # Imported lazily: the animation client loads the certified workflow
        # graph off disk, and an image-only worker has no reason to.
        from clients.wan_animate_client import WanAnimateClient

        return WanAnimateClient(
            base_url=binding.endpoint,
            model=engine_model_id(binding),
            timeout=resolve_timeout(binding, kwargs, default=120.0),
            default_params=dict(binding.default_params or {}),
            **kwargs,
        )
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
