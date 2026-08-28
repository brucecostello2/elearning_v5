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
from shared.providers.client_registry import family_of, resolve_client
from shared.providers.errors import EngineNotRegisteredError


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


# WP-IVGS-04 Task 2 (D-2). The builder registry is keyed on ENGINE ALONE
# (`factory.py:44`), so ONE `tts` builder has to serve BOTH families. It does
# not branch on the model name or the stage -- it asks the client registry,
# which is keyed on `(stage, engine, family)` and is the single declaration of
# which client serves which family.
#
# THIS IS DELIBERATELY NOT A CHAIN OF IFS. `providers/image.py:31-51` is the
# pattern being avoided: `if binding.stage == "animation_generation"` inside a
# builder, already two branches deep, unable to separate two families on one
# stage. The registry exists precisely so that decision lives in one auditable
# place; the builder's job is to turn the registry's answer into an instance.
#
# The two builders below are REUSED, not re-implemented, so a `tts` binding
# constructs its client through exactly the same code as a `coqui` or `kokoro`
# binding -- including Coqui's ARCH-1 `fallback_url=None`. No second
# construction path to drift.
_BUILDER_BY_CLIENT_PATH: dict[str, Any] = {
    "clients.coqui_client.CoquiClient": build_coqui,
    "clients.kokoro_client.KokoroClient": build_kokoro,
}


def build_tts(binding: ModelBinding, **kwargs: Any) -> Any:
    """Build the client for a `tts`-runtime binding, per its model family."""
    spec = resolve_client(binding)
    builder = _BUILDER_BY_CLIENT_PATH.get(spec.client_path)
    if builder is None:
        # The registry knows a client for this family but this worker has no
        # builder for it. Named, because "TTS is broken" and "one family has no
        # builder" call for different actions.
        raise EngineNotRegisteredError(
            f"model {binding.name!r} resolves to {spec.client_path!r} for "
            f"family {family_of(binding)!r}, but no TTS builder is registered "
            f"for that client (have: {', '.join(sorted(_BUILDER_BY_CLIENT_PATH))})"
        )
    return builder(binding, **kwargs)


def register() -> None:
    register_engine_builder("coqui", build_coqui)
    register_engine_builder("kokoro", build_kokoro)
    # MBCP's real runtime name for both of the above.
    register_engine_builder("tts", build_tts)
