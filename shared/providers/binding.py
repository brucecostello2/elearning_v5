"""ARCH-1 ModelBinding — the resolved (model, engine, node, endpoint) tuple.

``get_binding`` (factory.py) turns an AD-01 selection row into one of these;
``build_provider`` turns it into a live provider. The binding is a plain
dataclass so Celery task code can log/serialise it without ORM entanglement.

Endpoint resolution: per-engine env override first, then the same defaults
``ivgs-workers/config.py`` ships (kept in lockstep — H.1 tracks the
latentsync/sadtalker port question; env wins without a code edit).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from shared.providers.errors import EndpointResolutionError

# engine -> (env var, default URL). Mirrors ivgs-workers/config.py defaults.
_ENGINE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "latentsync": ("IVGS_LATENTSYNC_URL", "http://node-04:8300"),
    "sadtalker": ("IVGS_SADTALKER_URL", "http://node-04:8301"),
    "cogvideox": ("IVGS_COGVIDEOX_URL", "http://cogvideox-server:8200"),
    "wan21": ("IVGS_WAN21_URL", "http://node-02:8210"),
    "vllm": ("IVGS_VLLM_URL", "http://node-02:8000"),
    "ollama": ("IVGS_OLLAMA_URL", "http://node-01:11434"),
    "comfyui": ("IVGS_COMFYUI_URL", "http://node-04:8188"),
    "coqui": ("IVGS_COQUI_URL", "http://node-05:8020"),
    "kokoro": ("IVGS_KOKORO_URL", "http://node-05:8021"),
    "animatediff": ("IVGS_ANIMATEDIFF_URL", "http://node-04:8188"),
    "remotion": ("IVGS_REMOTION_URL", "http://node-06:8400"),
}


# (engine, stage) -> (env var, default URL). WP-61 Task 3(b).
#
# WHY A SECOND MAP EXISTS, AND WHY IT IS NOT A GENERALISATION.
#
# Three IVGS stages run on `vllm`: transcript_refinement, storyboard_generation
# and translation. Until WP-61 they all resolved through the single
# ``IVGS_VLLM_URL``, which is correct only while they share one server. The
# WP-61 ruling routes TRANSLATION to Qwen on node-05 and holds storyboard and
# transcript on Llama until after M3.3 -- precisely so the Temporal conformance
# baseline (reference-run-2026-08-23) is not re-scored against a different
# model while the orchestration migration is being diffed. One env var cannot
# express that; setting ``IVGS_VLLM_URL`` to node-05 would move all three.
#
# So the override is scoped to the PAIR, and it is deliberately a short,
# explicit table rather than a computed ``IVGS_VLLM_TRANSLATION_URL``-style
# name derived from the arguments. A derived name means any typo in a stage
# string silently produces a variable nobody set, which resolves to the
# unscoped default and moves the model without saying so. This table can only
# be extended by editing it.
_STAGE_ENGINE_ENDPOINTS: dict[tuple[str, str], tuple[str, str]] = {
    ("vllm", "translation"): (
        "IVGS_VLLM_TRANSLATION_URL",
        "http://node-05:8000",
    ),
}


def resolve_endpoint(
    engine: str,
    node_id: str | None = None,
    *,
    stage: str | None = None,
) -> str:
    """Return the serving base URL for ``engine``, optionally scoped to ``stage``.

    Order: ``IVGS_<ENGINE>_<STAGE>_URL`` (only for the pairs listed in
    ``_STAGE_ENGINE_ENDPOINTS``) -> ``IVGS_<ENGINE>_URL`` -> shipped default.
    ``node_id`` is accepted for forward-compat (per-node endpoint maps are an
    AD-01.9 scheduler-integration follow-on) but does not alter resolution today.

    A stage that is not in the pair table resolves EXACTLY as it did before this
    parameter existed. That is the property that keeps storyboard and transcript
    on Llama while translation moves to Qwen, and it is asserted by test.
    """
    if stage is not None:
        scoped = _STAGE_ENGINE_ENDPOINTS.get((engine, stage))
        if scoped is not None:
            env_var, default = scoped
            url = os.environ.get(env_var, "").strip() or default
            if not url:
                raise EndpointResolutionError(
                    f"engine {engine!r} stage {stage!r} resolved to an empty "
                    f"endpoint ({env_var})"
                )
            return url

    entry = _ENGINE_ENDPOINTS.get(engine)
    if entry is None:
        raise EndpointResolutionError(f"no endpoint mapping for engine {engine!r}")
    env_var, default = entry
    url = os.environ.get(env_var, "").strip() or default
    if not url:
        raise EndpointResolutionError(
            f"engine {engine!r} resolved to an empty endpoint ({env_var})"
        )
    return url


@dataclass
class ModelBinding:
    """The effective model choice for one (stage, project[, scene], tier)."""

    model_id: UUID
    name: str
    display_name: str
    stage: str
    engine: str
    tier: str
    endpoint: str
    node_id: str | None = None
    vram_requirement_mb: int | None = None
    dynamically_loadable: bool = True
    default_params: dict[str, Any] = field(default_factory=dict)
    selection_id: UUID | None = None
    selected_by: str | None = None  # auto / manual / default-fallback
    rationale: str = ""

    def describe(self) -> str:
        """One-line human-readable summary for logs."""
        via = self.selected_by or "default"
        return (
            f"{self.name} [{self.engine}] tier={self.tier} via={via} "
            f"endpoint={self.endpoint}"
        )
