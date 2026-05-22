"""
IVGS v5 — Stage 5 Tests: Talking Head Generation
====================================================

Test suite for Stage 5 talking head task with mocked:
- LatentSyncClient (lip-sync rendering)
- VLLMClient (render mode detection)
- VideoValidator (codec, resolution, alignment)
- Asset download/upload (SeaweedFS)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.latentsync_client import (
    LatentSyncClient,
    LatentSyncResult,
    LatentSyncTimeoutError,
)
from tasks.stage5_talking_head import (
    SceneTalkingHeadInput,
    Stage5Input,
    _process_single_talking_head,
)
from utils.video_validator import (
    VideoQualityDecision,
    VideoValidationResult,
    VideoValidator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_video_bytes() -> bytes:
    """Generate minimal bytes simulating a video file."""
    return b"\x00" * 10000  # Placeholder; real tests use file fixtures


@pytest.fixture
def sample_image_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 5000


@pytest.fixture
def sample_audio_bytes() -> bytes:
    return b"RIFF" + b"\x00" * 5000


@pytest.fixture
def sample_reference_clip() -> bytes:
    return b"\x00\x00\x00\x1cftypisom" + b"\x00" * 10000


@pytest.fixture
def sample_stage5_input() -> Stage5Input:
    return Stage5Input(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Project",
        scenes=[
            SceneTalkingHeadInput(
                scene_id="scene-001",
                scene_index=0,
                image_asset_id="img-asset-001",
                audio_asset_id="audio-asset-001",
                visual_description="A modern classroom",
                narration_duration_seconds=15.0,
                scene_title="Introduction",
                scene_type="narration",
            ),
        ],
        reference_clip_asset_id="ref-clip-001",
        auto_detect_mode=False,
        default_mode="pip",
        enable_dedup=False,
    )


@pytest.fixture
def mock_latentsync_result(sample_video_bytes: bytes) -> LatentSyncResult:
    return LatentSyncResult(
        job_id="ls-job-001",
        video_data=sample_video_bytes,
        duration_seconds=15.0,
        width=1920,
        height=1080,
        fps=30,
        alignment_score=0.92,
        model_used="latentsync",
        generation_time_seconds=45.0,
        params_hash="test_hash",
    )


@pytest.fixture
def mock_video_validation() -> VideoValidationResult:
    return VideoValidationResult(
        is_valid=True,
        decision=VideoQualityDecision.APPROVED,
        quality_score=0.90,
        codec_ok=True,
        resolution_ok=True,
        fps_ok=True,
        duration_ok=True,
        audio_ok=True,
        corruption_ok=True,
        file_size_ok=True,
        actual_width=1920,
        actual_height=1080,
        actual_fps=30.0,
        actual_duration_seconds=15.0,
        actual_video_codec="h264",
        sha256_hash="videohash",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStage5TalkingHead:
    """Tests for Stage 5 talking head generation."""

    @pytest.mark.asyncio
    async def test_successful_talking_head_generation(
        self,
        sample_stage5_input: Stage5Input,
        sample_reference_clip: bytes,
        mock_latentsync_result: LatentSyncResult,
        mock_video_validation: VideoValidationResult,
        sample_image_bytes: bytes,
        sample_audio_bytes: bytes,
    ):
        """Test successful talking head generation."""
        mock_latentsync = AsyncMock(spec=LatentSyncClient)
        mock_latentsync.render.return_value = mock_latentsync_result

        mock_validator = MagicMock(spec=VideoValidator)
        mock_validator.validate_bytes.return_value = mock_video_validation

        mock_converter = MagicMock()

        with patch(
            "tasks.stage5_talking_head._download_asset",
            new_callable=AsyncMock,
            side_effect=[sample_image_bytes, sample_audio_bytes],
        ), patch(
            "tasks.stage5_talking_head._upload_video_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("th-asset-001", "/ivgs/talking-heads/proj-001/scene-001.mp4"),
        ), patch(
            "tasks.stage5_talking_head._update_scene_talking_head",
            new_callable=AsyncMock,
        ):
            result = await _process_single_talking_head(
                scene=sample_stage5_input.scenes[0],
                task_input=sample_stage5_input,
                reference_clip_data=sample_reference_clip,
                latentsync_client=mock_latentsync,
                vllm_client=None,
                video_validator=mock_validator,
                video_converter=mock_converter,
                config=MagicMock(),
            )

        assert result.status == "success"
        assert result.asset_id == "th-asset-001"
        assert result.alignment_score == 0.92
        assert result.render_mode == "pip"
        mock_latentsync.render.assert_called_once()

    @pytest.mark.asyncio
    async def test_latentsync_timeout_fails(
        self,
        sample_stage5_input: Stage5Input,
        sample_reference_clip: bytes,
        sample_image_bytes: bytes,
        sample_audio_bytes: bytes,
    ):
        """Test LatentSync timeout results in failure."""
        mock_latentsync = AsyncMock(spec=LatentSyncClient)
        mock_latentsync.render.side_effect = LatentSyncTimeoutError("Timed out")

        mock_validator = MagicMock(spec=VideoValidator)
        mock_converter = MagicMock()

        with patch(
            "tasks.stage5_talking_head._download_asset",
            new_callable=AsyncMock,
            side_effect=[sample_image_bytes, sample_audio_bytes],
        ):
            result = await _process_single_talking_head(
                scene=sample_stage5_input.scenes[0],
                task_input=sample_stage5_input,
                reference_clip_data=sample_reference_clip,
                latentsync_client=mock_latentsync,
                vllm_client=None,
                video_validator=mock_validator,
                video_converter=mock_converter,
                config=MagicMock(),
            )

        assert result.status == "failed"
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_low_alignment_still_succeeds(
        self,
        sample_stage5_input: Stage5Input,
        sample_reference_clip: bytes,
        mock_video_validation: VideoValidationResult,
        sample_image_bytes: bytes,
        sample_audio_bytes: bytes,
        sample_video_bytes: bytes,
    ):
        """Test that low alignment score still uploads (flagged)."""
        low_align_result = LatentSyncResult(
            job_id="ls-job-002",
            video_data=sample_video_bytes,
            duration_seconds=15.0,
            width=1920,
            height=1080,
            fps=30,
            alignment_score=0.72,  # Below 0.85 threshold
            model_used="latentsync",
            generation_time_seconds=50.0,
            params_hash="test_hash_2",
        )

        mock_latentsync = AsyncMock(spec=LatentSyncClient)
        mock_latentsync.render.return_value = low_align_result

        mock_validator = MagicMock(spec=VideoValidator)
        mock_validator.validate_bytes.return_value = mock_video_validation

        mock_converter = MagicMock()

        with patch(
            "tasks.stage5_talking_head._download_asset",
            new_callable=AsyncMock,
            side_effect=[sample_image_bytes, sample_audio_bytes],
        ), patch(
            "tasks.stage5_talking_head._upload_video_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("th-asset-002", "/path"),
        ), patch(
            "tasks.stage5_talking_head._update_scene_talking_head",
            new_callable=AsyncMock,
        ):
            result = await _process_single_talking_head(
                scene=sample_stage5_input.scenes[0],
                task_input=sample_stage5_input,
                reference_clip_data=sample_reference_clip,
                latentsync_client=mock_latentsync,
                vllm_client=None,
                video_validator=mock_validator,
                video_converter=mock_converter,
                config=MagicMock(),
            )

        assert result.status == "success"
        assert result.alignment_score == 0.72

    def test_stage5_input_validation(self):
        """Test Stage5Input requires scenes and reference clip."""
        with pytest.raises(Exception):
            Stage5Input(
                job_id="job-001",
                project_id="proj-001",
                scenes=[],
                reference_clip_asset_id="ref-001",
            )

    def test_latentsync_result_quality_threshold(self):
        """Test LatentSyncResult quality threshold property."""
        good = LatentSyncResult(
            job_id="j1", video_data=b"", duration_seconds=10,
            width=1920, height=1080, fps=30,
            alignment_score=0.90, model_used="ls",
            generation_time_seconds=30, params_hash="h",
        )
        assert good.meets_quality_threshold is True

        bad = LatentSyncResult(
            job_id="j2", video_data=b"", duration_seconds=10,
            width=1920, height=1080, fps=30,
            alignment_score=0.70, model_used="ls",
            generation_time_seconds=30, params_hash="h",
        )
        assert bad.meets_quality_threshold is False
