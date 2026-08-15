"""Stage-6 ARCH-1 wiring — the LIVE task renders through the bound provider.

Retargeted from the dead ``tasks.stage6_talking_head`` duplicate onto the task
the orchestrator actually dispatches, ``tasks.talking_head_task`` (WP-02-ORCH6).
The dead module implemented a per-scene architecture that AD-03 Pillar 2
retired; the live task renders the whole project as one continuous head track,
segmented for bounded memory.

The Celery task body is exercised on hardware (live-verify runbook); here we
drive ``_render_segment`` directly with a fake provider, proving the params
mapping and the binding-driven model attribution without any engine service.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

# Worker config reads VLLM_*_URL at import time (see ivgs-workers/tests/
# conftest.py); setdefault keeps real env authoritative.
os.environ.setdefault("VLLM_PRIMARY_URL", "http://192.168.1.91:8000")
os.environ.setdefault("VLLM_SECONDARY_URL", "http://192.168.1.92:8000")
os.environ.setdefault("VLLM_MIDSIZE_URL", "http://192.168.1.93:8000")

WORKERS_DIR = Path(__file__).resolve().parents[2] / "ivgs-workers"
if str(WORKERS_DIR) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIR))

from shared.providers import (  # noqa: E402
    ModelBinding,
    TalkingHeadParams,
    TalkingHeadProvider,
    TalkingHeadResult,
)

pytestmark = pytest.mark.asyncio


class FakeProvider(TalkingHeadProvider):
    def __init__(self) -> None:
        self.seen: list[TalkingHeadParams] = []
        self.closed = False

    async def render(self, params: TalkingHeadParams) -> TalkingHeadResult:
        self.seen.append(params)
        return TalkingHeadResult(
            video_data=b"MP4-BYTES",
            width=params.output_width,
            height=params.output_height,
            fps=params.output_fps,
            duration_seconds=4.2,
            alignment_score=0.93,
            model="engine-side-name-ignored",
            generation_time_seconds=1.5,
        )

    async def check_health(self) -> bool:
        return True

    def vram_requirement_mb(self) -> int:
        return 8192

    def provider_name(self) -> str:
        return "fake"

    async def close(self) -> None:
        self.closed = True


def _binding(name: str = "latentsync", engine: str = "latentsync") -> ModelBinding:
    return ModelBinding(
        model_id=uuid.uuid4(),
        name=name,
        display_name=name.title(),
        stage="talking_head",
        engine=engine,
        tier="prototype",
        endpoint="http://node-04:8300",
    )


async def test_segment_render_maps_params_to_the_provider():
    """The live segment render feeds the shared contract, not an engine client."""
    import tasks.talking_head_task as th

    provider = FakeProvider()
    task_input = th.Stage6Input(
        job_id="job-1",
        project_id=str(uuid.uuid4()),
        reference_clip_asset_id="ref-1",
        latentsync_mode="pip",
        pip_position="bottom_left",
        pip_scale=0.4,
        lip_sync_strength=0.8,
        enable_face_enhance=False,
        alignment_threshold=0.9,
    )

    result = await th._render_segment(
        provider=provider,
        reference_clip_data=b"REF-BYTES",
        audio_data=b"AUDIO-BYTES",
        task_input=task_input,
    )

    assert result.alignment_score == 0.93
    assert result.width == 1920

    params = provider.seen[0]
    assert params.voiceover_audio_data == b"AUDIO-BYTES"
    assert params.reference_clip_data == b"REF-BYTES"
    # Stage 6 renders the presenter from the reference clip; there is no
    # per-scene still. A provider that requires one cannot serve this stage.
    assert params.scene_image_data is None
    assert params.mode == "pip"
    assert params.pip_position == "bottom_left"
    assert params.pip_scale == 0.4
    assert params.lip_sync_strength == 0.8
    assert params.face_enhance is False
    assert params.alignment_threshold == 0.9
    assert params.output_width == 1920
    assert params.output_height == 1080
    assert params.output_fps == 30


async def test_unknown_render_mode_falls_back_instead_of_raising():
    """Pre-ARCH-1 behaviour preserved: a bad mode degrades, it does not raise.

    The engine enum would reject an unknown mode inside the provider; the task
    normalises first, exactly as the old LatentSyncMode try/except did.
    """
    import tasks.talking_head_task as th

    assert th._resolve_render_mode("full_frame") == "full_frame"
    assert th._resolve_render_mode("pip") == "pip"
    assert th._resolve_render_mode("chroma_key") == "chroma_key"
    assert th._resolve_render_mode("overlay") == "full_frame"
    assert th._resolve_render_mode("") == "full_frame"

    provider = FakeProvider()
    task_input = th.Stage6Input(
        job_id="job-1",
        project_id=str(uuid.uuid4()),
        reference_clip_asset_id="ref-1",
        latentsync_mode="not-a-real-mode",
    )
    await th._render_segment(provider, b"REF", b"AUDIO", task_input)
    assert provider.seen[0].mode == "full_frame"


async def test_live_stage6_module_has_no_hardcoded_engine():
    """The guarantee this work package exists to deliver.

    Asserted against the module ``STAGE_TASK_MAP`` dispatches, not a duplicate.
    """
    import inspect

    import tasks.talking_head_task as th

    source = inspect.getsource(th)
    assert "LatentSyncClient(" not in source
    assert "from clients.latentsync_client import" not in source
    assert "get_binding" in source
    assert "build_provider" in source

    # The registered name is the dispatch identity and must not drift.
    assert th.render_talking_head.name == "tasks.talking_head_task.render_talking_head"


async def test_model_attribution_comes_from_the_binding():
    """``model_used`` must name the AD-01 selection, not the engine's own label.

    FakeProvider returns model="engine-side-name-ignored"; the task stamps
    ``binding.name``. Without this, a GUI swap would not be visible in the
    stage output or in the logs.
    """
    import inspect

    import tasks.talking_head_task as th

    source = inspect.getsource(th.render_talking_head)
    assert "model_used = binding.name" in source
    assert 'model_used = "latentsync"' not in source

    binding = _binding(name="latentsync-v1.6")
    assert binding.describe().startswith("latentsync-v1.6 [latentsync]")
