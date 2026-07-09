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


def resolve_endpoint(engine: str, node_id: str | None = None) -> str:
    """Return the serving base URL for ``engine``.

    Order: ``IVGS_<ENGINE>_URL`` env override -> shipped default. ``node_id``
    is accepted for forward-compat (per-node endpoint maps are an AD-01.9
    scheduler-integration follow-on) but does not alter resolution today.
    """
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
