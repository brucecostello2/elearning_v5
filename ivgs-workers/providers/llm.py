"""ARCH-1 LLM engine builder (``vllm``).

Wraps the existing ``VLLMClient`` — which already implements the shared
``LLMProvider`` ABC and accepts a base URL — behind the selection-aware
factory. The binding, not task code, supplies the endpoint and model.

**No client-side failover (ARCH-1, mirrors the Stage-6 exemplar).** The
stock client can fan out to secondary vLLM URLs; here ``failover_urls`` is
forced empty. Under AD-01 the fallback model/endpoint is a *selection* (and,
once the poller lands, a node-availability) decision — not a hidden client
behaviour. High-availability across vLLM servers rides on the M2 scheduler
work, not on this constructor.
"""
from __future__ import annotations

from typing import Any

from clients.vllm_client import VLLMClient

from providers._common import engine_model_id, resolve_timeout
from shared.providers import ModelBinding, register_engine_builder


def build_vllm(binding: ModelBinding, **kwargs: Any) -> VLLMClient:
    timeout = resolve_timeout(binding, kwargs, default=120.0)
    return VLLMClient(
        base_url=binding.endpoint,
        model=engine_model_id(binding),
        timeout=timeout,
        failover_urls=[],  # ARCH-1: failover is a selection/scheduler concern
        **kwargs,
    )


def register() -> None:
    register_engine_builder("vllm", build_vllm)
