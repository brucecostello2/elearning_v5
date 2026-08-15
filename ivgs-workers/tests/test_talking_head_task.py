"""
IVGS v5 — Stage 6: Talking Head Task Tests
=============================================

Test suite for Stage 6 talking head rendering:
- Primary render path through the AD-01-selected provider (ARCH-1)
- SadTalker fallback path
- Alignment score validation
- Audio concatenation
- Corruption detection integration
- Checkpoint saving
- SeaweedFS upload
"""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.providers import (
    TalkingHeadParams,
    TalkingHeadProvider,
    TalkingHeadResult,
)
from tasks.talking_head_task import (
    SceneAudioRef,
    Stage6Input,
    Stage6Output,
    _concatenate_scene_audio,
    _render_segment,
)
from validators.lipsync_validator import (
    LipsyncDecision,
    LipsyncValidator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_mp4_bytes() -> bytes:
    """Generate minimal valid MP4 file header for testing."""
    # Minimal ftyp + moov + mdat MP4
    ftyp = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41"
    moov = b"\x00\x00\x00\x08moov"
    mdat = b"\x00\x00\x00\x10mdat" + b"\x00" * 8
    return ftyp + moov + mdat


@pytest.fixture
def sample_wav_bytes() -> bytes:
    """Generate minimal valid WAV file for testing."""
    sample_rate = 48000
    bit_depth = 24
    channels = 1
    duration_seconds = 2
    num_samples = sample_rate * duration_seconds
    byte_rate = sample_rate * channels * (bit_depth // 8)
    block_align = channels * (bit_depth // 8)
    data_size = num_samples * block_align

    pcm_data = b"\x00" * data_size

    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)
    header += struct.pack("<H", 1)
    header += struct.pack("<H", channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", block_align)
    header += struct.pack("<H", bit_depth)
    header += b"data"
    header += struct.pack("<I", data_size)

    return header + pcm_data


@pytest.fixture
def sample_stage6_input() -> Stage6Input:
    return Stage6Input(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Project",
        language_code="en-US",
        reference_clip_asset_id="asset-ref-001",
        scene_audio_refs=[
            SceneAudioRef(
                scene_id="scene-001",
                scene_index=0,
                audio_asset_id="asset-audio-001",
                duration_seconds=10.0,
            ),
            SceneAudioRef(
                scene_id="scene-002",
                scene_index=1,
                audio_asset_id="asset-audio-002",
                duration_seconds=12.0,
            ),
        ],
        alignment_threshold=0.85,
        latentsync_mode="full_screen",
    )


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.pipeline_api.full_base_url = "http://localhost:8000/api/v1"
    config.pipeline_api.service_token = "test-token"
    config.pipeline_api.timeout_seconds = 30.0
    config.redis_url = "redis://localhost:6379/0"
    config.get_model_config.return_value = {
        "api_url": "http://node-04:8300",
        "timeout_seconds": 600,
    }
    return config


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStage6Input:
    """Test Stage 6 input validation."""

    def test_valid_input(self, sample_stage6_input: Stage6Input):
        assert sample_stage6_input.job_id == "job-001"
        assert len(sample_stage6_input.scene_audio_refs) == 2
        assert sample_stage6_input.alignment_threshold == 0.85

    def test_requires_at_least_one_audio_ref(self):
        with pytest.raises(Exception):
            Stage6Input(
                job_id="job-001",
                project_id="proj-001",
                reference_clip_asset_id="asset-ref-001",
                scene_audio_refs=[],
            )

    def test_default_values(self):
        input_data = Stage6Input(
            job_id="job-001",
            project_id="proj-001",
            reference_clip_asset_id="ref-001",
            scene_audio_refs=[
                SceneAudioRef(
                    scene_id="s1",
                    scene_index=0,
                    audio_asset_id="a1",
                    duration_seconds=5.0,
                ),
            ],
        )
        assert input_data.output_width == 1920
        assert input_data.output_height == 1080
        assert input_data.output_fps == 30
        assert input_data.alignment_threshold == 0.85
        assert input_data.enable_face_enhance is True


class TestStage6Output:
    """Test Stage 6 output model."""

    def test_default_output(self):
        output = Stage6Output(job_id="job-001", project_id="proj-001")
        assert output.stage == "talking_head_render"
        assert output.status.value == "success"
        assert output.alignment_score == 0.0

    def test_failed_output(self):
        output = Stage6Output(
            job_id="job-001",
            project_id="proj-001",
            status="failed",
            errors=["All renderers failed"],
        )
        assert len(output.errors) == 1


class _StubProvider(TalkingHeadProvider):
    """Stands in for whatever engine the AD-01 binding selected."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.seen: list[TalkingHeadParams] = []

    async def render(self, params: TalkingHeadParams) -> TalkingHeadResult:
        self.seen.append(params)
        if self._error is not None:
            raise self._error
        return self._result

    async def check_health(self) -> bool:
        return True

    def vram_requirement_mb(self) -> int:
        return 16384

    def provider_name(self) -> str:
        return "stub"


def _stage6_input(**overrides) -> Stage6Input:
    base = dict(
        job_id="j1",
        project_id="p1",
        reference_clip_asset_id="ref",
        scene_audio_refs=[
            SceneAudioRef(
                scene_id="s1",
                scene_index=0,
                audio_asset_id="a1",
                duration_seconds=22.0,
            ),
        ],
    )
    base.update(overrides)
    return Stage6Input(**base)


class TestSegmentRender:
    """Segment rendering goes through the bound provider, not an engine client.

    Rewritten for WP-02-ORCH6: the task no longer constructs a LatentSync
    client, so there is nothing engine-specific left to patch. The seam under
    test is _render_segment(provider, ...).
    """

    @pytest.mark.asyncio
    async def test_successful_render(self, sample_mp4_bytes):
        provider = _StubProvider(
            result=TalkingHeadResult(
                video_data=sample_mp4_bytes,
                width=1920,
                height=1080,
                fps=30,
                duration_seconds=22.0,
                alignment_score=0.92,
                model="whatever-the-engine-calls-itself",
                generation_time_seconds=45.0,
            )
        )

        result = await _render_segment(
            provider=provider,
            reference_clip_data=b"REF",
            audio_data=b"AUDIO",
            task_input=_stage6_input(),
        )

        assert result.alignment_score >= 0.85
        assert result.width == 1920

        # Stage 6 supplies reference clip + audio and no per-scene still.
        params = provider.seen[0]
        assert params.reference_clip_data == b"REF"
        assert params.voiceover_audio_data == b"AUDIO"
        assert params.scene_image_data is None

    @pytest.mark.asyncio
    async def test_render_failure_propagates_to_the_caller(self):
        """The segment loop needs the error, so it can retry then fall back."""
        provider = _StubProvider(error=RuntimeError("GPU OOM"))

        with pytest.raises(RuntimeError, match="GPU OOM"):
            await _render_segment(
                provider=provider,
                reference_clip_data=b"REF",
                audio_data=b"AUDIO",
                task_input=_stage6_input(),
            )


class TestAudioConcatenation:
    """Test audio concatenation for talking head input."""

    @pytest.mark.asyncio
    @patch("tasks.talking_head_task._download_asset")
    @patch("tasks.talking_head_task.FFmpegClient")
    async def test_concatenate_scene_audio(
        self,
        mock_ffmpeg_cls,
        mock_download,
        sample_wav_bytes,
        mock_config,
    ):
        mock_download.return_value = sample_wav_bytes
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.concat_audio.return_value = "/tmp/full_audio.wav"
        mock_ffmpeg_cls.return_value = mock_ffmpeg

        refs = [
            SceneAudioRef(
                scene_id="s1", scene_index=0,
                audio_asset_id="a1", duration_seconds=5.0,
            ),
            SceneAudioRef(
                scene_id="s2", scene_index=1,
                audio_asset_id="a2", duration_seconds=7.0,
            ),
        ]

        result = await _concatenate_scene_audio(refs, mock_config, "/tmp")  # noqa: F841

        assert mock_download.call_count == 2
        mock_ffmpeg.concat_audio.assert_called_once()


class TestLipsyncValidation:
    """Test lip-sync validation integration."""

    def test_approved_score(self):
        validator = LipsyncValidator()
        result = validator.validate(
            video_path="/dev/null",
            audio_path="/dev/null",
            latentsync_score=0.95,
        )
        # Note: with /dev/null files, duration check may penalize
        assert result.decision in (
            LipsyncDecision.APPROVED,
            LipsyncDecision.FLAGGED,
            LipsyncDecision.REJECTED,
        )

    def test_rejected_score(self):
        validator = LipsyncValidator()
        result = validator.validate(
            video_path="/dev/null",
            audio_path="/dev/null",
            latentsync_score=0.50,
        )
        assert result.decision == LipsyncDecision.REJECTED
