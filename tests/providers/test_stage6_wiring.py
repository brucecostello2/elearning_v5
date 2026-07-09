"""Stage-6 ARCH-1 wiring — the per-scene path renders through the bound
provider and stamps ``binding.name`` as ``model_used``.

The Celery task body is exercised on hardware (live-verify runbook); here we
drive ``_process_single_talking_head`` directly with a fake provider and
monkeypatched asset/upload/validator seams, proving the params mapping and
model attribution without any engine service.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

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


def _binding() -> ModelBinding:
    return ModelBinding(
        model_id=uuid.uuid4(),
        name="sadtalker-v2",
        display_name="SadTalker V2",
        stage="talking_head",
        engine="sadtalker",
        tier="prototype",
        endpoint="http://node-04:8301",
    )


async def test_per_scene_path_uses_provider_and_binding(monkeypatch):
    import tasks.stage6_talking_head as stage6

    provider = FakeProvider()
    binding = _binding()

    async def fake_download(asset_id, config):
        return f"BYTES:{asset_id}".encode()

    async def fake_upload(video_data, project_id, scene_id, config):
        return ("asset-1", f"/ivgs/talking-heads/{project_id}/{scene_id}.mp4")

    async def fake_update(project_id, scene_id, asset_id, config):
        return None

    monkeypatch.setattr(stage6, "_download_asset", fake_download)
    monkeypatch.setattr(stage6, "_upload_video_to_seaweedfs", fake_upload)
    monkeypatch.setattr(stage6, "_update_scene_talking_head", fake_update)

    validation = SimpleNamespace(
        is_valid=True,
        quality_score=0.97,
        errors=[],
        decision=SimpleNamespace(value="pass"),
    )
    validator = SimpleNamespace(validate_bytes=lambda **kw: validation)
    converter = SimpleNamespace()

    scene = stage6.SceneTalkingHeadInput(
        scene_id="scene-1",
        scene_index=0,
        image_asset_id="img-1",
        audio_asset_id="aud-1",
        narration_duration_seconds=4.2,
        render_mode="pip",
    )
    task_input = stage6.Stage5Input(
        job_id="job-1",
        project_id=str(uuid.uuid4()),
        scenes=[scene],
        reference_clip_asset_id="ref-1",
        enable_dedup=False,
        auto_detect_mode=False,
    )

    result = await stage6._process_single_talking_head(
        scene=scene,
        task_input=task_input,
        reference_clip_data=b"REF-BYTES",
        provider=provider,
        binding=binding,
        vllm_client=None,
        video_validator=validator,
        video_converter=converter,
        config=stage6.WorkerConfig(),
    )

    assert result.status == "success"
    assert result.model_used == "sadtalker-v2"  # binding, not engine result
    assert result.render_mode == "pip"
    assert result.alignment_score == 0.93

    params = provider.seen[0]
    assert params.scene_image_data == b"BYTES:img-1"
    assert params.voiceover_audio_data == b"BYTES:aud-1"
    assert params.reference_clip_data == b"REF-BYTES"
    assert params.mode == "pip"
    assert params.output_width == 1920


async def test_stage6_module_has_no_hardcoded_engine():
    import inspect

    import tasks.stage6_talking_head as stage6

    source = inspect.getsource(stage6)
    assert "LatentSyncClient(" not in source
    assert "get_binding" in source
    assert "build_provider" in source
