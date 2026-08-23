"""ARCH-1 factory tests (no DB) — registry, builders, endpoint resolution."""
from __future__ import annotations

import uuid

import pytest

from shared.providers import (
    EngineNotRegisteredError,
    build_provider,
    register_engine_builder,
    registered_engines,
    resolve_endpoint,
)
from shared.providers.errors import EndpointResolutionError

pytestmark = pytest.mark.asyncio


async def test_build_provider_unregistered_engine():
    from shared.providers.binding import ModelBinding

    binding = ModelBinding(
        model_id=uuid.uuid4(),
        name="x",
        display_name="X",
        stage="talking_head",
        engine="nonexistent-engine",
        tier="prototype",
        endpoint="http://nowhere:1",
    )
    with pytest.raises(EngineNotRegisteredError):
        build_provider(binding)


async def test_register_and_build(monkeypatch):
    from shared.providers.binding import ModelBinding

    captured = {}

    class FakeProvider:
        def __init__(self, binding, **kwargs):
            captured["binding"] = binding
            captured["kwargs"] = kwargs

    register_engine_builder("fake-engine", FakeProvider)
    assert "fake-engine" in registered_engines()
    binding = ModelBinding(
        model_id=uuid.uuid4(),
        name="fake",
        display_name="Fake",
        stage="talking_head",
        engine="fake-engine",
        tier="prototype",
        endpoint="http://fake:1",
    )
    provider = build_provider(binding, alignment_threshold=0.9)
    assert isinstance(provider, FakeProvider)
    assert captured["binding"] is binding
    assert captured["kwargs"] == {"alignment_threshold": 0.9}


def test_resolve_endpoint_env_override(monkeypatch):
    monkeypatch.setenv("IVGS_LATENTSYNC_URL", "http://gpu-lab:9999")
    assert resolve_endpoint("latentsync") == "http://gpu-lab:9999"
    monkeypatch.delenv("IVGS_LATENTSYNC_URL")
    assert resolve_endpoint("latentsync") == "http://node-04:8300"


def test_resolve_endpoint_unknown_engine():
    with pytest.raises(EndpointResolutionError):
        resolve_endpoint("not-an-engine")
