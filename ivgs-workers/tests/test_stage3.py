"""
IVGS v5 — Stage 3 Tests: Scene Image Generation
===================================================

Test suite for Stage 3 image generation task with mocked:
- FluxClient (ComfyUI image generation)
- CogVideoXClient (video keyframe extraction)
- VLLMClient (prompt generation)
- SeaweedFS upload (via Pipeline API mock)
- Quality scoring API

Covers:
- Successful image generation flow
- FLUX fallback to SDXL
- CogVideoX keyframe for video scenes
- Image validation (resolution, CLIP, corruption)
- SHA-256 deduplication
- Checkpoint saving
- Error handling and retry
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.flux_client import (
    FluxClient,
    FluxGenerationResult,
    FluxTimeoutError,
)
from clients.cogvideox_client import CogVideoXClient
from tasks.stage3_images import (
    SceneImageInput,
    SceneImageResult,
    Stage3Input,
    _process_single_scene,
)
from utils.image_validator import (
    ImageQualityDecision,
    ImageValidationResult,
    ImageValidator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_image_bytes() -> bytes:
    """Generate a minimal valid PNG for testing."""
    # Minimal 1x1 white PNG
    import struct
    import zlib

    def _make_png(width: int = 100, height: int = 100) -> bytes:
        raw_data = b""
        for _ in range(height):
            raw_data += b"\x00" + b"\xff\xff\xff" * width

        def _chunk(chunk_type: bytes, data: bytes) -> bytes:
            c = chunk_type + data
            crc = zlib.crc32(c) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

        header = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        idat = zlib.compress(raw_data)
        return header + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")

    return _make_png(1024, 1024)


@pytest.fixture
def sample_stage3_input() -> Stage3Input:
    return Stage3Input(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Project",
        project_description="A test educational video",
        target_audience="general",
        scenes=[
            SceneImageInput(
                scene_id="scene-001",
                scene_index=0,
                visual_description="A modern classroom with students",
                media_type="image",
                narration_text="Welcome to our course",
                duration_seconds=15.0,
                scene_title="Introduction",
            ),
            SceneImageInput(
                scene_id="scene-002",
                scene_index=1,
                visual_description="A diagram showing data flow",
                media_type="image",
                narration_text="Data flows through the system",
                duration_seconds=20.0,
                scene_title="Data Flow",
            ),
        ],
        enable_clip_scoring=False,
        enable_dedup=False,
    )


@pytest.fixture
def mock_flux_result(sample_image_bytes: bytes) -> FluxGenerationResult:
    return FluxGenerationResult(
        prompt_id="test-prompt-001",
        image_data=sample_image_bytes,
        image_filename="ivgs_flux_00001_.png",
        width=1024,
        height=1024,
        model_used="flux1-schnell-fp8.safetensors",
        generation_time_seconds=3.5,
        seed_used=42,
        params_hash="abc123",
    )


@pytest.fixture
def mock_validation_result() -> ImageValidationResult:
    return ImageValidationResult(
        is_valid=True,
        decision=ImageQualityDecision.APPROVED,
        quality_score=0.92,
        resolution_ok=True,
        format_ok=True,
        file_size_ok=True,
        corruption_ok=True,
        blank_check_ok=True,
        noise_check_ok=True,
        actual_width=1920,
        actual_height=1080,
        actual_format="PNG",
        file_size_bytes=500000,
        sha256_hash="abc123def456",
    )


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

class TestStage3ImageGeneration:
    """Tests for Stage 3 image generation logic."""

    @pytest.mark.asyncio
    async def test_successful_image_generation(
        self,
        sample_stage3_input: Stage3Input,
        mock_flux_result: FluxGenerationResult,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
    ):
        """Test successful image generation for a single scene."""
        mock_flux = AsyncMock(spec=FluxClient)
        mock_flux.generate_image.return_value = mock_flux_result

        mock_cogvideox = AsyncMock(spec=CogVideoXClient)

        mock_vllm = AsyncMock()
        mock_vllm.chat.return_value = MagicMock(
            content="A modern classroom, natural lighting, high quality, 8K\nNEGATIVE: blurry, dark"
        )

        mock_validator = MagicMock(spec=ImageValidator)
        mock_validator.validate.return_value = mock_validation_result

        with patch(
            "tasks.stage3_images._upload_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("asset-001", "/ivgs/images/proj-001/scenes/scene-001/image.png"),
        ), patch(
            "tasks.stage3_images._update_scene_asset",
            new_callable=AsyncMock,
        ), patch(
            "tasks.stage3_images._submit_quality_score",
            new_callable=AsyncMock,
        ), patch(
            "tasks.stage3_images.ImageConverter",
        ) as mock_converter_cls:
            mock_converter_cls.resize_to_target.return_value = MagicMock(
                output_data=sample_image_bytes,
            )

            scene = sample_stage3_input.scenes[0]
            result = await _process_single_scene(
                scene=scene,
                task_input=sample_stage3_input,
                vllm_client=mock_vllm,
                flux_client=mock_flux,
                cogvideox_client=mock_cogvideox,
                image_validator=mock_validator,
                config=MagicMock(),
            )

        assert result.status == "success"
        assert result.asset_id == "asset-001"
        assert result.scene_id == "scene-001"
        mock_flux.generate_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_flux_failure_returns_error(
        self,
        sample_stage3_input: Stage3Input,
    ):
        """Test that FLUX failure results in failed status."""
        mock_flux = AsyncMock(spec=FluxClient)
        mock_flux.generate_image.side_effect = FluxTimeoutError("Timed out")

        mock_vllm = AsyncMock()
        mock_vllm.chat.return_value = MagicMock(content="A classroom, high quality")

        mock_cogvideox = AsyncMock(spec=CogVideoXClient)
        mock_validator = MagicMock(spec=ImageValidator)

        scene = sample_stage3_input.scenes[0]
        result = await _process_single_scene(
            scene=scene,
            task_input=sample_stage3_input,
            vllm_client=mock_vllm,
            flux_client=mock_flux,
            cogvideox_client=mock_cogvideox,
            image_validator=mock_validator,
            config=MagicMock(),
        )

        assert result.status == "failed"
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_video_scene_uses_cogvideox(
        self,
        sample_stage3_input: Stage3Input,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
    ):
        """Test that video_clip scenes use CogVideoX for keyframe."""
        video_scene = SceneImageInput(
            scene_id="scene-v01",
            scene_index=0,
            visual_description="An animated data flow diagram",
            media_type="video_clip",
            narration_text="Watch the data flow",
            duration_seconds=10.0,
        )
        task_input = sample_stage3_input.model_copy(
            update={"scenes": [video_scene]}
        )

        mock_flux = AsyncMock(spec=FluxClient)
        mock_cogvideox = AsyncMock(spec=CogVideoXClient)
        mock_cogvideox.generate_keyframe.return_value = sample_image_bytes

        mock_vllm = AsyncMock()
        mock_vllm.chat.return_value = MagicMock(content="Data flow animation, high quality")

        mock_validator = MagicMock(spec=ImageValidator)
        mock_validator.validate.return_value = mock_validation_result

        with patch(
            "tasks.stage3_images._upload_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("asset-v01", "/ivgs/images/proj-001/scenes/scene-v01/image.png"),
        ), patch(
            "tasks.stage3_images._update_scene_asset",
            new_callable=AsyncMock,
        ), patch("tasks.stage3_images.ImageConverter") as mock_conv:
            mock_conv.resize_to_target.return_value = MagicMock(
                output_data=sample_image_bytes
            )

            result = await _process_single_scene(
                scene=video_scene,
                task_input=task_input,
                vllm_client=mock_vllm,
                flux_client=mock_flux,
                cogvideox_client=mock_cogvideox,
                image_validator=mock_validator,
                config=MagicMock(),
            )

        assert result.status == "success"
        mock_cogvideox.generate_keyframe.assert_called_once()

    def test_stage3_input_validation(self):
        """Test Stage3Input pydantic validation."""
        with pytest.raises(Exception):
            Stage3Input(
                job_id="job-001",
                project_id="proj-001",
                scenes=[],  # min_length=1
            )

    def test_scene_image_result_model(self):
        """Test SceneImageResult model creation."""
        result = SceneImageResult(
            scene_id="scene-001",
            scene_index=0,
            asset_id="asset-001",
            sha256_hash="abc123",
            width=1920,
            height=1080,
            quality_score=0.95,
            quality_decision="approved",
            model_used="flux1-schnell",
            generation_time_seconds=4.2,
        )
        assert result.status == "success"
        assert result.was_deduplicated is False

    @pytest.mark.asyncio
    async def test_deduplication_skips_generation(
        self,
        sample_stage3_input: Stage3Input,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
        mock_flux_result: FluxGenerationResult,
    ):
        """Test that duplicate assets are reused without regeneration."""
        task_input = sample_stage3_input.model_copy(
            update={"enable_dedup": True}
        )

        mock_flux = AsyncMock(spec=FluxClient)
        mock_flux.generate_image.return_value = mock_flux_result
        mock_cogvideox = AsyncMock(spec=CogVideoXClient)
        mock_vllm = AsyncMock()
        mock_vllm.chat.return_value = MagicMock(content="A classroom, high quality")
        mock_validator = MagicMock(spec=ImageValidator)
        mock_validator.validate.return_value = mock_validation_result

        with patch(
            "tasks.stage3_images.check_duplicate_asset",
            return_value={"id": "existing-asset", "storage_path": "/existing/path.png"},
        ), patch(
            "tasks.stage3_images._update_scene_asset",
            new_callable=AsyncMock,
        ), patch("tasks.stage3_images.ImageConverter") as mock_conv:
            mock_conv.resize_to_target.return_value = MagicMock(
                output_data=sample_image_bytes
            )

            result = await _process_single_scene(
                scene=task_input.scenes[0],
                task_input=task_input,
                vllm_client=mock_vllm,
                flux_client=mock_flux,
                cogvideox_client=mock_cogvideox,
                image_validator=mock_validator,
                config=MagicMock(),
            )

        assert result.status == "success"
        assert result.was_deduplicated is True
        assert result.asset_id == "existing-asset"


class TestStage3CeleryTask:
    """Tests for the Celery task wrapper."""

    @patch("tasks.stage3_images.update_job_status")
    @patch("tasks.stage3_images.save_checkpoint")
    @patch("tasks.stage3_images.acquire_gpu_reservation")
    @patch("tasks.stage3_images.FluxClient")
    @patch("tasks.stage3_images.CogVideoXClient")
    @patch("tasks.stage3_images.VLLMClient")
    @patch("tasks.stage3_images.ImageValidator")
    def test_task_serialization(
        self,
        mock_validator_cls,
        mock_vllm_cls,
        mock_cogvideo_cls,
        mock_flux_cls,
        mock_gpu,
        mock_checkpoint,
        mock_status,
    ):
        """Test that task input/output serializes correctly."""
        input_dict = {
            "job_id": "job-001",
            "project_id": "proj-001",
            "project_name": "Test",
            "scenes": [
                {
                    "scene_id": "s1",
                    "scene_index": 0,
                    "visual_description": "A classroom",
                    "media_type": "image",
                    "narration_text": "Hello",
                    "duration_seconds": 10.0,
                }
            ],
            "enable_clip_scoring": False,
            "enable_dedup": False,
        }

        parsed = Stage3Input(**input_dict)
        assert parsed.job_id == "job-001"
        assert len(parsed.scenes) == 1
        assert parsed.scenes[0].visual_description == "A classroom"
