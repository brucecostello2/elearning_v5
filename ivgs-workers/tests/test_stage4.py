"""
IVGS v5 — Stage 4 Tests: Voiceover Synthesis
================================================

Test suite for Stage 4 voiceover task with mocked:
- CoquiClient (Coqui XTTS v2 TTS)
- VLLMClient (text optimization)
- AudioValidator (SNR, clipping)
- AudioConverter (normalization)
- SeaweedFS upload
"""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.coqui_client import (
    CoquiClient,
    CoquiSynthesisResult,
    CoquiTimeoutError,
)
# WP-32.3: the MODULE is tasks/stage5_voiceover.py; the Celery task it
# registers is named `tasks.stage4_voiceover.generate_voiceover_task`
# (stage5_voiceover.py:493). The test imported by the registered name, which
# is not an importable path. CLAUDE.md s7: filenames are not task identities.
# The registered name is deliberately NOT changed -- it is what the
# orchestrator dispatches and what any in-flight message carries.
from tasks.stage5_voiceover import (
    SceneVoiceoverInput,
    Stage4Input,
    _process_single_voiceover,
)
from utils.audio_validator import (
    AudioQualityDecision,
    AudioValidationResult,
    AudioValidator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_wav_bytes() -> bytes:
    """Generate a minimal valid WAV file for testing."""
    sample_rate = 48000
    bit_depth = 24
    channels = 1
    duration_seconds = 2
    num_samples = sample_rate * duration_seconds
    byte_rate = sample_rate * channels * (bit_depth // 8)
    block_align = channels * (bit_depth // 8)
    data_size = num_samples * block_align

    # Generate silent audio
    pcm_data = b"\x00" * data_size

    # WAV header
    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)  # fmt chunk size
    header += struct.pack("<H", 1)   # PCM format
    header += struct.pack("<H", channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", block_align)
    header += struct.pack("<H", bit_depth)
    header += b"data"
    header += struct.pack("<I", data_size)

    return header + pcm_data


@pytest.fixture
def sample_stage4_input() -> Stage4Input:
    return Stage4Input(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Project",
        target_audience="general",
        language_code="en-US",
        scenes=[
            SceneVoiceoverInput(
                scene_id="scene-001",
                scene_index=0,
                narration_text="Welcome to this educational course about Python programming.",
                duration_seconds=15.0,
                scene_title="Introduction",
                language_code="en-US",
            ),
            SceneVoiceoverInput(
                scene_id="scene-002",
                scene_index=1,
                narration_text="Python is a versatile programming language.",
                duration_seconds=10.0,
                scene_title="What is Python",
                language_code="en-US",
            ),
        ],
        optimize_text=False,
        enable_dedup=False,
    )


@pytest.fixture
def mock_synthesis_result(sample_wav_bytes: bytes) -> CoquiSynthesisResult:
    return CoquiSynthesisResult(
        audio_data=sample_wav_bytes,
        sample_rate=48000,
        bit_depth=24,
        channels=1,
        duration_seconds=15.0,
        language="en",
        model_used="coqui-xtts-v2",
        generation_time_seconds=5.2,
        params_hash="test_hash_123",
        text_length=60,
    )


@pytest.fixture
def mock_audio_validation() -> AudioValidationResult:
    return AudioValidationResult(
        is_valid=True,
        decision=AudioQualityDecision.APPROVED,
        quality_score=0.90,
        format_ok=True,
        sample_rate_ok=True,
        bit_depth_ok=True,
        channels_ok=True,
        duration_ok=True,
        snr_ok=True,
        clipping_ok=True,
        silence_ok=True,
        corruption_ok=True,
        actual_sample_rate=48000,
        actual_bit_depth=24,
        actual_channels=1,
        actual_duration_seconds=15.0,
        snr_db=35.0,
        clipping_pct=0.01,
        file_size_bytes=len(b"" * 100),
        sha256_hash="testhash",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStage4VoiceoverSynthesis:
    """Tests for Stage 4 voiceover generation logic."""

    @pytest.mark.asyncio
    async def test_successful_voiceover_generation(
        self,
        sample_stage4_input: Stage4Input,
        mock_synthesis_result: CoquiSynthesisResult,
        mock_audio_validation: AudioValidationResult,
    ):
        """Test successful voiceover generation for a single scene."""
        mock_coqui = AsyncMock(spec=CoquiClient)
        mock_coqui.synthesize.return_value = mock_synthesis_result

        mock_validator = MagicMock(spec=AudioValidator)
        mock_validator.validate.return_value = mock_audio_validation

        mock_converter = MagicMock()
        mock_converter.normalize_wav.return_value = MagicMock(
            output_data=mock_synthesis_result.audio_data
        )

        with patch(
            "tasks.stage4_voiceover._upload_audio_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("audio-asset-001", "/ivgs/audio/proj-001/scene-001/en-US.wav"),
        ), patch(
            "tasks.stage4_voiceover._update_scene_audio",
            new_callable=AsyncMock,
        ):
            result = await _process_single_voiceover(
                scene=sample_stage4_input.scenes[0],
                task_input=sample_stage4_input,
                coqui_client=mock_coqui,
                vllm_client=None,
                audio_validator=mock_validator,
                audio_converter=mock_converter,
                config=MagicMock(),
            )

        assert result.status == "success"
        assert result.asset_id == "audio-asset-001"
        assert result.snr_db == 35.0
        mock_coqui.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_coqui_failure_returns_error(
        self,
        sample_stage4_input: Stage4Input,
    ):
        """Test that Coqui failure returns failed status."""
        mock_coqui = AsyncMock(spec=CoquiClient)
        mock_coqui.synthesize.side_effect = CoquiTimeoutError("TTS timed out")

        mock_validator = MagicMock(spec=AudioValidator)
        mock_converter = MagicMock()

        result = await _process_single_voiceover(
            scene=sample_stage4_input.scenes[0],
            task_input=sample_stage4_input,
            coqui_client=mock_coqui,
            vllm_client=None,
            audio_validator=mock_validator,
            audio_converter=mock_converter,
            config=MagicMock(),
        )

        assert result.status == "failed"
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_low_snr_rejects_audio(
        self,
        sample_stage4_input: Stage4Input,
        mock_synthesis_result: CoquiSynthesisResult,
    ):
        """Test that low SNR audio is rejected."""
        mock_coqui = AsyncMock(spec=CoquiClient)
        mock_coqui.synthesize.return_value = mock_synthesis_result

        rejected_validation = AudioValidationResult(
            is_valid=False,
            decision=AudioQualityDecision.REJECTED,
            quality_score=0.3,
            snr_ok=False,
            corruption_ok=True,
            actual_duration_seconds=15.0,
            snr_db=12.0,
            errors=["SNR too low: 12.0dB (min: 20.0dB)"],
        )

        mock_validator = MagicMock(spec=AudioValidator)
        mock_validator.validate.return_value = rejected_validation

        mock_converter = MagicMock()
        mock_converter.normalize_wav.return_value = MagicMock(
            output_data=mock_synthesis_result.audio_data
        )

        result = await _process_single_voiceover(
            scene=sample_stage4_input.scenes[0],
            task_input=sample_stage4_input,
            coqui_client=mock_coqui,
            vllm_client=None,
            audio_validator=mock_validator,
            audio_converter=mock_converter,
            config=MagicMock(),
        )

        assert result.status == "failed"
        assert result.snr_db == 12.0

    def test_stage4_input_validation(self):
        """Test Stage4Input pydantic validation."""
        with pytest.raises(Exception):
            Stage4Input(
                job_id="job-001",
                project_id="proj-001",
                scenes=[],
            )

    def test_supported_languages(self):
        """Test that all 8 supported languages are mapped."""
        from clients.coqui_client import SUPPORTED_LANGUAGES
        assert len(SUPPORTED_LANGUAGES) == 8
        assert "en-US" in SUPPORTED_LANGUAGES
        assert "zh-CN" in SUPPORTED_LANGUAGES
        assert "ar-SA" in SUPPORTED_LANGUAGES
