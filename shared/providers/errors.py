"""ARCH-1 provider-factory exceptions (§19.1 / AD-01.9)."""
from __future__ import annotations


class ProviderError(Exception):
    """Base class for provider-factory failures."""


class SelectionError(ProviderError):
    """No effective selection: no scene/project row and no ``is_default``
    model exists for the requested (stage, tier). AD-01.6 step 4 surfaces
    this to the operator as a planning error."""


class SelectionIntegrityError(ProviderError):
    """A selection row exists but its model is not servable (retired,
    disabled, or candidate). The binding fails closed rather than silently
    substituting a different model."""


class EngineNotRegisteredError(ProviderError):
    """``build_provider`` was asked for an engine with no registered
    builder — the worker image lacks the adapter for that engine."""


class EndpointResolutionError(ProviderError):
    """No serving endpoint could be resolved for (engine, node)."""
