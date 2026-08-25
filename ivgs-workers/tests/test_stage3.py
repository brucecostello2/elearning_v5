"""
IVGS v5 — Stage 3 Tests: Scene Image Generation
===================================================

Test suite for Stage 3 image generation, mocked at the seams the task actually
uses after the provider-factory rewrite:

- ``get_binding`` / ``build_provider``  (ARCH-1 scene-scoped model selection)
- ``ImageValidator``                    (constructed INSIDE the function)
- ``_upload_to_seaweedfs`` / ``_submit_quality_score``
- ``find_duplicate_or_none``            (SHA-256 dedup)
- ``ImageConverter``                    (upscale to 1920x1080)
- ``VLLMClient.chat``                   (prompt writer, exercised for real)

Covers:
- Successful image generation flow
- Image-generation failure surfaces as a failed SceneImageResult
- CogVideoX keyframe for video_clip scenes, and its FLUX fallback
- SHA-256 deduplication
- Model validation of the task's input/output contracts

WP-52 (ledger P2.45) rewrote four of these. They had been red on ``main`` since
the provider-factory rewrite, from three causes, all of them in this file:

  1. Three ``patch`` targets named ``tasks.stage3_images._update_scene_asset``.
     No such attribute has ever existed in that module -- ``patch`` raises
     ``AttributeError`` at setup, so the tests never reached an assertion.
  2. One named ``tasks.stage3_images.CogVideoXClient``. The module imports
     ``CogVideoXGenerationParams`` and ``CogVideoXModel`` from that client, not
     the client class; the class arrives via ``build_provider``.
  3. Four calls passed ``flux_client=`` / ``cogvideox_client=``. Those
     parameters are gone: ``_process_single_scene`` now takes
     ``prompt_binding`` plus keyword-only ``project_id`` and ``tier``, and
     resolves the image/video provider per scene.

Two further things the rewrite had to respect, both easy to get silently wrong:

  * ``project_id`` and ``scene_id`` are fed to ``UUID(...)`` inside the
    function. The old fixtures used ``"proj-001"`` / ``"scene-001"``, which
    raise ``ValueError`` -- and the function catches every exception and
    returns ``status="failed"``. A test asserting ``status == "failed"`` would
    therefore have passed for entirely the wrong reason. Every id here is a
    real UUID.
  * ``_process_single_scene`` still ACCEPTS an ``image_validator`` argument and
    then ignores it: step 4 constructs its own ``ImageValidator(...)`` so it can
    pass the CLIP URL and service token. Mocking the argument validates
    nothing. These tests patch the class. The dead parameter is a real (if
    harmless) defect in the code under test and is ledgered, not fixed here.

``tests/test_wp44_quality_gate.py::TestStage3CarriesTheRecord`` covers the
WP-44 quality-record seam by source assertion. It is deliberately not
duplicated below.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from clients.flux_client import (
    FluxGenerationResult,
    FluxModel,
    FluxTimeoutError,
)
from clients.cogvideox_client import CogVideoXModel
from shared.providers.binding import ModelBinding
from tasks.stage3_images import (
    SceneImageInput,
    SceneImageResult,
    Stage3Input,
    _process_single_scene,
)
from utils.image_validator import (
    ImageQualityDecision,
    ImageValidationResult,
)


# ---------------------------------------------------------------------------
# Ids. Real UUIDs, because the function parses them as such.
# ---------------------------------------------------------------------------

PROJECT_ID = str(uuid4())
SCENE_ID_1 = str(uuid4())
SCENE_ID_2 = str(uuid4())
VIDEO_SCENE_ID = str(uuid4())


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


def _binding(stage: str, engine: str, name: str) -> ModelBinding:
    """A resolved ARCH-1 binding, as `get_binding` would return one.

    `engine_model_id` reads `default_params["engine_model"]` before falling back
    to `name`, and the task feeds that string straight into `FluxModel(...)` /
    `CogVideoXModel(...)`, so it has to be a real enum member.
    """
    return ModelBinding(
        model_id=uuid4(),
        name=name,
        display_name=name,
        stage=stage,
        engine=engine,
        tier="prototype",
        endpoint=f"http://{engine}-test:8000",
        vram_requirement_mb=16384,
        selected_by="auto",
    )


@pytest.fixture
def image_binding() -> ModelBinding:
    return _binding("image_generation", "comfyui", FluxModel.FLUX_SCHNELL.value)


@pytest.fixture
def video_binding() -> ModelBinding:
    return _binding("video_generation", "cogvideox", CogVideoXModel.COGVIDEOX_5B.value)


@pytest.fixture
def sample_stage3_input() -> Stage3Input:
    return Stage3Input(
        job_id="job-001",
        project_id=PROJECT_ID,
        project_name="Test Project",
        project_description="A test educational video",
        target_audience="general",
        scenes=[
            SceneImageInput(
                scene_id=SCENE_ID_1,
                scene_index=0,
                visual_description="A modern classroom with students",
                media_type="image",
                narration_text="Welcome to our course",
                duration_seconds=15.0,
                scene_title="Introduction",
            ),
            SceneImageInput(
                scene_id=SCENE_ID_2,
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


@pytest.fixture
def mock_vllm() -> AsyncMock:
    """The prompt writer. `_generate_image_prompt` runs for real against this."""
    client = AsyncMock()
    client.chat.return_value = MagicMock(
        content=(
            "A modern classroom, natural lighting, high quality, 8K\n"
            "NEGATIVE: blurry, dark"
        )
    )
    return client


@pytest.fixture
def prompt_binding() -> ModelBinding:
    return _binding("storyboard_generation", "vllm", "mistral-small-24b")


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

class TestStage3ImageGeneration:
    """Tests for Stage 3 image generation logic."""

    @pytest.mark.asyncio
    async def test_successful_image_generation(
        self,
        sample_stage3_input: Stage3Input,
        prompt_binding: ModelBinding,
        image_binding: ModelBinding,
        mock_vllm: AsyncMock,
        mock_flux_result: FluxGenerationResult,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
    ):
        """Test successful image generation for a single scene."""
        flux_provider = AsyncMock()
        flux_provider.generate_image.return_value = mock_flux_result

        validator_instance = MagicMock()
        validator_instance.validate.return_value = mock_validation_result

        with patch(
            "tasks.stage3_images.get_binding",
            new_callable=AsyncMock,
            return_value=image_binding,
        ) as mock_get_binding, patch(
            "tasks.stage3_images.build_provider",
            return_value=flux_provider,
        ) as mock_build_provider, patch(
            "tasks.stage3_images.ImageValidator",
            return_value=validator_instance,
        ), patch(
            "tasks.stage3_images._upload_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("asset-001", f"/ivgs/images/{PROJECT_ID}/scenes/{SCENE_ID_1}/image.png"),
        ), patch(
            "tasks.stage3_images._submit_quality_score",
            new_callable=AsyncMock,
        ) as mock_submit, patch(
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
                prompt_binding=prompt_binding,
                image_validator=validator_instance,
                config=MagicMock(),
                project_id=PROJECT_ID,
                tier="prototype",
            )

        assert result.status == "success", result.errors
        assert result.asset_id == "asset-001"
        assert result.scene_id == SCENE_ID_1
        flux_provider.generate_image.assert_called_once()

        # The image binding is resolved per scene, scoped to project AND scene.
        mock_get_binding.assert_awaited_once()
        assert mock_get_binding.await_args.args[0] == "image_generation"
        assert mock_get_binding.await_args.kwargs["project_id"] == UUID(PROJECT_ID)
        assert mock_get_binding.await_args.kwargs["scene_id"] == UUID(SCENE_ID_1)
        mock_build_provider.assert_called_once_with(image_binding)

        # `model_used` is the binding's name, not the engine handle.
        assert result.model_used == image_binding.name

        # WP-44: the quality record is submitted whether or not CLIP ran.
        mock_submit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flux_failure_returns_error(
        self,
        sample_stage3_input: Stage3Input,
        prompt_binding: ModelBinding,
        image_binding: ModelBinding,
        mock_vllm: AsyncMock,
    ):
        """Test that a FLUX failure results in failed status."""
        flux_provider = AsyncMock()
        flux_provider.generate_image.side_effect = FluxTimeoutError("Timed out")

        with patch(
            "tasks.stage3_images.get_binding",
            new_callable=AsyncMock,
            return_value=image_binding,
        ), patch(
            "tasks.stage3_images.build_provider",
            return_value=flux_provider,
        ):
            scene = sample_stage3_input.scenes[0]
            result = await _process_single_scene(
                scene=scene,
                task_input=sample_stage3_input,
                vllm_client=mock_vllm,
                prompt_binding=prompt_binding,
                image_validator=MagicMock(),
                config=MagicMock(),
                project_id=PROJECT_ID,
                tier="prototype",
            )

        assert result.status == "failed"
        assert len(result.errors) > 0
        # Pin the CAUSE, not just the status. Every id above is a valid UUID and
        # every seam is patched, so the only thing left to fail is the generator
        # -- which is what this test is about.
        assert "Timed out" in result.errors[0]
        # The provider is closed even on the failure path (`finally`).
        flux_provider.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_video_scene_uses_cogvideox(
        self,
        sample_stage3_input: Stage3Input,
        prompt_binding: ModelBinding,
        video_binding: ModelBinding,
        mock_vllm: AsyncMock,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
    ):
        """Test that video_clip scenes use CogVideoX for the keyframe."""
        video_scene = SceneImageInput(
            scene_id=VIDEO_SCENE_ID,
            scene_index=0,
            visual_description="An animated data flow diagram",
            media_type="video_clip",
            narration_text="Watch the data flow",
            duration_seconds=10.0,
        )
        task_input = sample_stage3_input.model_copy(
            update={"scenes": [video_scene]}
        )

        cogvideox_provider = AsyncMock()
        cogvideox_provider.generate_keyframe.return_value = sample_image_bytes

        validator_instance = MagicMock()
        validator_instance.validate.return_value = mock_validation_result

        with patch(
            "tasks.stage3_images.get_binding",
            new_callable=AsyncMock,
            return_value=video_binding,
        ) as mock_get_binding, patch(
            "tasks.stage3_images.build_provider",
            return_value=cogvideox_provider,
        ), patch(
            "tasks.stage3_images.ImageValidator",
            return_value=validator_instance,
        ), patch(
            "tasks.stage3_images._upload_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("asset-v01", f"/ivgs/images/{PROJECT_ID}/scenes/{VIDEO_SCENE_ID}/image.png"),
        ), patch(
            "tasks.stage3_images._submit_quality_score",
            new_callable=AsyncMock,
        ), patch("tasks.stage3_images.ImageConverter") as mock_conv:
            mock_conv.resize_to_target.return_value = MagicMock(
                output_data=sample_image_bytes
            )

            result = await _process_single_scene(
                scene=video_scene,
                task_input=task_input,
                vllm_client=mock_vllm,
                prompt_binding=prompt_binding,
                image_validator=validator_instance,
                config=MagicMock(),
                project_id=PROJECT_ID,
                tier="prototype",
            )

        assert result.status == "success", result.errors
        cogvideox_provider.generate_keyframe.assert_awaited_once()
        # A video scene must bind the VIDEO stage, never the image stage.
        assert mock_get_binding.await_args.args[0] == "video_generation"
        assert result.model_used == video_binding.name

    @pytest.mark.asyncio
    async def test_video_keyframe_failure_falls_back_to_flux(
        self,
        sample_stage3_input: Stage3Input,
        prompt_binding: ModelBinding,
        video_binding: ModelBinding,
        image_binding: ModelBinding,
        mock_vllm: AsyncMock,
        mock_flux_result: FluxGenerationResult,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
    ):
        """An empty keyframe falls back to a still image, and says which model made it.

        The fallback resolves the IMAGE binding lazily, which is the branch a
        video-only project depends on. Nothing covered it before.
        """
        video_scene = SceneImageInput(
            scene_id=VIDEO_SCENE_ID,
            scene_index=0,
            visual_description="An animated data flow diagram",
            media_type="video_clip",
            narration_text="Watch the data flow",
            duration_seconds=10.0,
        )
        task_input = sample_stage3_input.model_copy(update={"scenes": [video_scene]})

        cogvideox_provider = AsyncMock()
        cogvideox_provider.generate_keyframe.return_value = b""  # keyframe failed
        flux_provider = AsyncMock()
        flux_provider.generate_image.return_value = mock_flux_result

        validator_instance = MagicMock()
        validator_instance.validate.return_value = mock_validation_result

        async def _binding_for(stage, **kwargs):
            return video_binding if stage == "video_generation" else image_binding

        with patch(
            "tasks.stage3_images.get_binding", side_effect=_binding_for
        ) as mock_get_binding, patch(
            "tasks.stage3_images.build_provider",
            side_effect=[cogvideox_provider, flux_provider],
        ), patch(
            "tasks.stage3_images.ImageValidator", return_value=validator_instance
        ), patch(
            "tasks.stage3_images._upload_to_seaweedfs",
            new_callable=AsyncMock,
            return_value=("asset-v02", "/ivgs/images/fallback.png"),
        ), patch(
            "tasks.stage3_images._submit_quality_score", new_callable=AsyncMock
        ), patch("tasks.stage3_images.ImageConverter") as mock_conv:
            mock_conv.resize_to_target.return_value = MagicMock(
                output_data=sample_image_bytes
            )

            result = await _process_single_scene(
                scene=video_scene,
                task_input=task_input,
                vllm_client=mock_vllm,
                prompt_binding=prompt_binding,
                image_validator=validator_instance,
                config=MagicMock(),
                project_id=PROJECT_ID,
                tier="prototype",
            )

        assert result.status == "success", result.errors
        flux_provider.generate_image.assert_awaited_once()
        assert [c.args[0] for c in mock_get_binding.await_args_list] == [
            "video_generation",
            "image_generation",
        ]
        # Provenance must name the model that actually produced the pixels.
        assert result.model_used == image_binding.name

    def test_stage3_input_validation(self):
        """Test Stage3Input pydantic validation."""
        with pytest.raises(Exception):
            Stage3Input(
                job_id="job-001",
                project_id=PROJECT_ID,
                scenes=[],  # min_length=1
            )

    def test_scene_image_result_model(self):
        """Test SceneImageResult model creation."""
        result = SceneImageResult(
            scene_id=SCENE_ID_1,
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
    async def test_deduplication_skips_upload(
        self,
        sample_stage3_input: Stage3Input,
        prompt_binding: ModelBinding,
        image_binding: ModelBinding,
        mock_vllm: AsyncMock,
        mock_validation_result: ImageValidationResult,
        sample_image_bytes: bytes,
        mock_flux_result: FluxGenerationResult,
    ):
        """A content-hash hit reuses the existing asset and skips the upload.

        Renamed from `test_deduplication_skips_generation`: WP-45 moved the
        check to AFTER generation deliberately -- it hashes bytes that now
        exist -- so what dedup saves is the upload and the duplicate row, not
        the GPU time. The old name asserted a behaviour the code does not have
        and was never going to have.
        """
        task_input = sample_stage3_input.model_copy(update={"enable_dedup": True})

        flux_provider = AsyncMock()
        flux_provider.generate_image.return_value = mock_flux_result

        validator_instance = MagicMock()
        validator_instance.validate.return_value = mock_validation_result

        with patch(
            "tasks.stage3_images.get_binding",
            new_callable=AsyncMock,
            return_value=image_binding,
        ), patch(
            "tasks.stage3_images.build_provider", return_value=flux_provider
        ), patch(
            "tasks.stage3_images.ImageValidator", return_value=validator_instance
        ), patch(
            "tasks.stage3_images.find_duplicate_or_none",
            return_value={"id": "existing-asset", "storage_path": "/existing/path.png"},
        ) as mock_find, patch(
            "tasks.stage3_images._upload_to_seaweedfs", new_callable=AsyncMock
        ) as mock_upload, patch(
            "tasks.stage3_images._submit_quality_score", new_callable=AsyncMock
        ) as mock_submit, patch("tasks.stage3_images.ImageConverter") as mock_conv:
            mock_conv.resize_to_target.return_value = MagicMock(
                output_data=sample_image_bytes
            )

            result = await _process_single_scene(
                scene=task_input.scenes[0],
                task_input=task_input,
                vllm_client=mock_vllm,
                prompt_binding=prompt_binding,
                image_validator=validator_instance,
                config=MagicMock(),
                project_id=PROJECT_ID,
                tier="prototype",
            )

        assert result.status == "success", result.errors
        assert result.was_deduplicated is True
        assert result.asset_id == "existing-asset"
        mock_find.assert_called_once()
        assert mock_find.call_args.kwargs["hash_kind"] == "content"
        # The point of the branch: no upload, no second quality submission.
        mock_upload.assert_not_awaited()
        mock_submit.assert_not_awaited()


class TestStage3CeleryTask:
    """Tests for the Celery task wrapper."""

    def test_task_serialization(self):
        """Test that task input deserialises from the orchestrator's dict.

        WP-52: the seven `@patch` decorators this test used to carry patched
        `tasks.stage3_images.CogVideoXClient` and `tasks.stage3_images.FluxClient`,
        neither of which the module imports any more, so `patch` raised
        `AttributeError` at setup. They were dead weight regardless -- the body
        constructs a `Stage3Input` and asserts on it, and touches no client, no
        GPU reservation and no checkpoint.
        """
        input_dict = {
            "job_id": "job-001",
            "project_id": PROJECT_ID,
            "project_name": "Test",
            "scenes": [
                {
                    "scene_id": SCENE_ID_1,
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
        # Defaults the orchestrator relies on and does not send.
        assert parsed.tier == "prototype"
        assert parsed.target_width == 1920
        assert parsed.target_height == 1080
        assert parsed.join_stage is None
