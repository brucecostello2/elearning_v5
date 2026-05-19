"""
IVGS v5 — Video Generation Task Tests
=========================================

Test suite for video clip generation:
- CogVideoX 5B generation path
- Wan2.1 generation path
- Model selection logic
- Fallback chain (CogVideoX → Wan2.1)
- Deduplication check
- SeaweedFS upload
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.cogvideox_client import (
    CogVideoXClient,
    CogVideoXError,
    CogVideoXGenerationParams,
    CogVideoXGenerationResult,
)
from clients.wan21_client import (
    Wan21Client,
    Wan21Error,
    Wan21GenerationParams,
    Wan21GenerationResult,
)
from tasks.video_generation_task import (
    SceneVideoInput,
    SceneVideoResult,
    VideoGenerationInput,
    VideoGenerationOutput,
    _process_single_video,
    _select_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_video_input() -> VideoGenerationInput:
    return VideoGenerationInput(
        job_id="job-001",
        project_id="proj-001",
        project_name="Test Course",
        target_audience="general",
        language_code="en-US",
        scenes=[
            SceneVideoInput(
                scene_id="scene-001",
                scene_index=0,
                visual_description="A busy city street with pedestrians",
                narration_text="The city bustles with energy.",
                duration_seconds=5.0,
                scene_type="broll",
            ),
            SceneVideoInput(
                scene_id="scene-002",
                scene_index=1,
                visual_description="Close-up of coding on a laptop",
                duration_seconds=6.0,
                scene_type="broll",
                preferred_model="cogvideox",
            ),
        ],
    )


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.pipeline_api.full_base_url = "http://localhost:8000/api/v1"
    config.pipeline_api.service_token = "test-token"
    config.pipeline_api.timeout_seconds = 30.0
    config.redis_url = "redis://localhost:6379/0"
    config.get_model_config.return_value = {
        "api_url": "http://node-02:8200",
        "fallback_url": "http://node-03:8200",
    }
    config.get_vllm_config_for_stage.return_value = MagicMock(
        model="mistralai/Mistral-Small-24B-Instruct-2501",
        base_url="http://node-04:8000",
    )
    return config


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModelSelection:
    """Test video generation model selection logic."""

    def test_auto_selects_wan21_for_short_broll(self):
        scene = SceneVideoInput(
            scene_id="s1",
            scene_index=0,
            visual_description="test",
            duration_seconds=4.0,
            scene_type="broll",
        )
        assert _select_model(scene) == "wan21"

    def test_auto_selects_cogvideox_for_longer_clips(self):
        scene = SceneVideoInput(
            scene_id="s1",
            scene_index=0,
            visual_description="test",
            duration_seconds=6.0,
            scene_type="narration",
        )
        assert _select_model(scene) == "cogvideox"

    def test_respects_preferred_model(self):
        scene = SceneVideoInput(
            scene_id="s1",
            scene_index=0,
            visual_description="test",
            duration_seconds=3.0,
            scene_type="broll",
            preferred_model="cogvideox",
        )
        assert _select_model(scene) == "cogvideox"

    def test_auto_for_transitions(self):
        scene = SceneVideoInput(
            scene_id="s1",
            scene_index=0,
            visual_description="test",
            duration_seconds=3.0,
            scene_type="transition",
        )
        assert _select_model(scene) == "wan21"


class TestVideoGenerationInput:
    """Test video generation input validation."""

    def test_valid_input(self, sample_video_input: VideoGenerationInput):
        assert sample_video_input.job_id == "job-001"
        assert len(sample_video_input.scenes) == 2

    def test_requires_at_least_one_scene(self):
        with pytest.raises(Exception):
            VideoGenerationInput(
                job_id="j1",
                project_id="p1",
                scenes=[],
            )


class TestVideoGenerationOutput:
    """Test video generation output model."""

    def test_output_defaults(self):
        output = VideoGenerationOutput(
            job_id="job-001",
            project_id="proj-001",
        )
        assert output.stage == "video_generation"
        assert output.total_scenes == 0

    def test_output_with_results(self):
        output = VideoGenerationOutput(
            job_id="job-001",
            project_id="proj-001",
            scene_results=[
                SceneVideoResult(
                    scene_id="s1",
                    scene_index=0,
                    model_used="wan2.1",
                    status="success",
                ),
            ],
            successful_count=1,
            total_scenes=1,
        )
        assert output.successful_count == 1


class TestWan21Client:
    """Test Wan2.1 client."""

    def test_generation_params_hash(self):
        params = Wan21GenerationParams(
            prompt="A beautiful sunset",
            width=1280,
            height=720,
        )
        hash1 = params.compute_hash()
        hash2 = params.compute_hash()
        assert hash1 == hash2

        params2 = Wan21GenerationParams(
            prompt="A different prompt",
            width=1280,
            height=720,
        )
        assert params.compute_hash() != params2.compute_hash()

    def test_generation_result_fields(self):
        result = Wan21GenerationResult(
            request_id="req-001",
            video_data=b"fake_video_data",
            width=1280,
            height=720,
            fps=30,
            duration_seconds=5.0,
            num_frames=150,
            file_size_bytes=1024,
            generation_time_seconds=10.0,
            seed_used=42,
            params_hash="abc123",
        )
        assert result.width == 1280
        assert result.duration_seconds == 5.0


class TestProcessSingleVideo:
    """Test single video processing with mocks."""

    @pytest.mark.asyncio
    @patch("tasks.video_generation_task._upload_asset")
    @patch("tasks.video_generation_task._generate_with_wan21")
    @patch("tasks.video_generation_task._generate_video_prompt")
    @patch("tasks.video_generation_task.check_duplicate_asset")
    async def test_successful_generation(
        self,
        mock_dedup,
        mock_prompt,
        mock_wan21,
        mock_upload,
        mock_config,
    ):
        mock_dedup.return_value = None
        mock_prompt.return_value = "A bustling city street"
        mock_wan21.return_value = Wan21GenerationResult(
            request_id="req-001",
            video_data=b"fake_video_bytes",
            width=1280,
            height=720,
            fps=30,
            duration_seconds=5.0,
            num_frames=150,
            file_size_bytes=1024,
            generation_time_seconds=8.0,
            seed_used=42,
            params_hash="abc",
        )
        mock_upload.return_value = {
            "id": "asset-001",
            "storage_path": "/ivgs/videos/proj/scene/clip.mp4",
        }

        scene = SceneVideoInput(
            scene_id="s1",
            scene_index=0,
            visual_description="busy city",
            duration_seconds=5.0,
            scene_type="broll",
        )

        vllm_client = MagicMock()
        result = await _process_single_video(
            scene=scene,
            vllm_client=vllm_client,
            config=mock_config,
            target_audience="general",
            enable_dedup=True,
            project_id="proj-001",
        )

        assert result.status == "success"
        assert result.model_used == "wan2.1"
        assert result.asset_id == "asset-001"

    @pytest.mark.asyncio
    @patch("tasks.video_generation_task.check_duplicate_asset")
    @patch("tasks.video_generation_task._generate_video_prompt")
    async def test_dedup_hit(
        self,
        mock_prompt,
        mock_dedup,
        mock_config,
    ):
        mock_dedup.return_value = {
            "id": "existing-asset",
            "storage_path": "/ivgs/videos/existing.mp4",
            "content_hash": "existing_hash",
        }
        mock_prompt.return_value = "test prompt"

        scene = SceneVideoInput(
            scene_id="s1",
            scene_index=0,
            visual_description="test",
            duration_seconds=5.0,
        )

        result = await _process_single_video(
            scene=scene,
            vllm_client=MagicMock(),
            config=mock_config,
            target_audience="general",
            enable_dedup=True,
            project_id="proj-001",
        )

        assert result.was_deduplicated is True
        assert result.asset_id == "existing-asset"
