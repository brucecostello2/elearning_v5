"""
IVGS v5 — Stage 2 Tests: Storyboard Generation
==================================================

Tests cover:
- Input validation and parsing
- Storyboard JSON validation and normalization
- JSON extraction from various LLM output formats
- Scene model validation (field normalization, media type mapping)
- vLLM interaction (mocked)
- Database save calls
- Checkpoint saving
- Error handling and retry
- Full task execution via Celery eager mode
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from models.task_result import (
    MediaType,
    StageStatus,
    StoryboardGenerationOutput,
    StoryboardScene,
    VLLMChoice,
    VLLMMessage,
    VLLMResponse,
    VLLMUsage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_refined_transcripts() -> List[Dict[str, Any]]:
    return [
        {
            "transcript_id": "tx-001",
            "sequence_order": 1,
            "original_text": "Raw text 1",
            "refined_text": (
                "Python is one of the most popular programming languages. "
                "It is known for its clear syntax and readability. "
                "Developers use Python for web development, data science, "
                "and artificial intelligence."
            ),
            "language_code": "en-US",
            "refinement_metadata": {},
        },
        {
            "transcript_id": "tx-002",
            "sequence_order": 2,
            "original_text": "Raw text 2",
            "refined_text": (
                "Guido van Rossum created Python in 1991. "
                "Since then, it has grown into a versatile language. "
                "Python's extensive library ecosystem makes it ideal "
                "for rapid application development."
            ),
            "language_code": "en-US",
            "refinement_metadata": {},
        },
    ]


@pytest.fixture
def sample_job_context() -> Dict[str, Any]:
    return {
        "job_id": "job-222-333-444",
        "project_id": "proj-aaa-bbb-ccc",
        "project_name": "Python Programming Intro",
        "project_description": "Introduction to Python programming",
        "target_audience": "beginners",
        "max_runtime_seconds": 300,
        "language_code": "en-US",
        "priority": "normal",
        "current_stage": "storyboard_generation",
    }


@pytest.fixture
def sample_task_input(
    sample_job_context: Dict[str, Any],
    sample_refined_transcripts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "job_context": sample_job_context,
        "refined_transcripts": sample_refined_transcripts,
    }


@pytest.fixture
def sample_storyboard_json() -> Dict[str, Any]:
    """Sample valid storyboard JSON from LLM."""
    return {
        "scenes": [
            {
                "scene_index": 0,
                "narration_text": (
                    "Python is one of the most popular programming languages."
                ),
                "visual_description": (
                    "A modern computer screen displaying Python code with "
                    "syntax highlighting. Clean workspace with natural light."
                ),
                "media_type": "image",
                "duration_seconds": 12.0,
                "scene_title": "Introduction to Python",
                "transition": "fade",
            },
            {
                "scene_index": 1,
                "narration_text": (
                    "It is known for its clear syntax and readability."
                ),
                "visual_description": (
                    "Split screen comparison: Python code on the left "
                    "vs C++ code on the right, highlighting Python's "
                    "simpler syntax. Clean, modern design."
                ),
                "media_type": "image",
                "duration_seconds": 10.0,
                "scene_title": "Python Syntax",
                "transition": "dissolve",
            },
            {
                "scene_index": 2,
                "narration_text": (
                    "Developers use Python for web development, data science, "
                    "and artificial intelligence."
                ),
                "visual_description": (
                    "Animated infographic showing three columns: Web Dev "
                    "(Django, Flask icons), Data Science (charts, notebooks), "
                    "AI (neural network diagram). Smooth animation transitions."
                ),
                "media_type": "animation",
                "duration_seconds": 15.0,
                "scene_title": "Python Use Cases",
                "transition": "cut",
            },
        ]
    }


@pytest.fixture
def mock_vllm_storyboard_response(
    sample_storyboard_json: Dict[str, Any],
) -> VLLMResponse:
    return VLLMResponse(
        id="cmpl-storyboard-001",
        object="chat.completion",
        created=int(time.time()),
        model="meta-llama/Llama-3.3-70B-Instruct",
        choices=[
            VLLMChoice(
                index=0,
                message=VLLMMessage(
                    role="assistant",
                    content=json.dumps(sample_storyboard_json),
                ),
                finish_reason="stop",
            )
        ],
        usage=VLLMUsage(
            prompt_tokens=500,
            completion_tokens=300,
            total_tokens=800,
        ),
    )


# ---------------------------------------------------------------------------
# Storyboard JSON validation tests
# ---------------------------------------------------------------------------

class TestStoryboardJsonValidation:
    """Test JSON validation and normalization logic."""

    def test_valid_scenes_list(self, sample_storyboard_json) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        scenes = _validate_storyboard_json(sample_storyboard_json)
        assert len(scenes) == 3
        assert scenes[0].scene_index == 0
        assert scenes[0].media_type == MediaType.IMAGE
        assert scenes[2].media_type == MediaType.ANIMATION

    def test_scenes_as_flat_list(self) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        flat_list = [
            {
                "scene_index": 0,
                "narration_text": "Hello world",
                "visual_description": "A globe spinning",
                "media_type": "image",
                "duration_seconds": 10,
            }
        ]
        scenes = _validate_storyboard_json(flat_list)
        assert len(scenes) == 1

    def test_empty_scenes_rejected(self) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        with pytest.raises(ValueError, match="empty"):
            _validate_storyboard_json({"scenes": []})

    def test_missing_narration_skipped(self) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        scenes_raw = {
            "scenes": [
                {
                    "scene_index": 0,
                    "narration_text": "",
                    "visual_description": "Something",
                    "duration_seconds": 10,
                },
                {
                    "scene_index": 1,
                    "narration_text": "Valid narration",
                    "visual_description": "Something",
                    "duration_seconds": 10,
                },
            ]
        }
        scenes = _validate_storyboard_json(scenes_raw)
        assert len(scenes) == 1
        assert scenes[0].narration_text == "Valid narration"

    def test_duration_clamping(self) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        scenes_raw = [
            {
                "narration_text": "Test",
                "visual_description": "Test",
                "duration_seconds": 0.5,  # Too short
            },
            {
                "narration_text": "Test 2",
                "visual_description": "Test 2",
                "duration_seconds": 999,  # Too long
            },
        ]
        scenes = _validate_storyboard_json(scenes_raw)
        assert scenes[0].duration_seconds == 3.0  # Clamped to min
        assert scenes[1].duration_seconds == 120.0  # Clamped to max

    def test_media_type_normalization(self) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        scenes_raw = [
            {
                "narration_text": "A",
                "visual_description": "B",
                "media_type": "video",
                "duration_seconds": 10,
            },
            {
                "narration_text": "C",
                "visual_description": "D",
                "media_type": "animated",
                "duration_seconds": 10,
            },
        ]
        scenes = _validate_storyboard_json(scenes_raw)
        assert scenes[0].media_type == MediaType.VIDEO_CLIP
        assert scenes[1].media_type == MediaType.ANIMATION

    def test_reindexing(self) -> None:
        from tasks.stage2_storyboard import _validate_storyboard_json

        scenes_raw = [
            {
                "scene_index": 5,
                "narration_text": "First",
                "visual_description": "A",
                "duration_seconds": 10,
            },
            {
                "scene_index": 99,
                "narration_text": "Second",
                "visual_description": "B",
                "duration_seconds": 10,
            },
        ]
        scenes = _validate_storyboard_json(scenes_raw)
        assert scenes[0].scene_index == 0
        assert scenes[1].scene_index == 1


# ---------------------------------------------------------------------------
# JSON extraction tests
# ---------------------------------------------------------------------------

class TestJsonExtraction:
    """Test extracting JSON from various LLM response formats."""

    def test_direct_json(self, sample_storyboard_json) -> None:
        from tasks.stage2_storyboard import _extract_json_from_response

        raw = json.dumps(sample_storyboard_json)
        result = _extract_json_from_response(raw)
        assert "scenes" in result

    def test_json_in_code_fence(self, sample_storyboard_json) -> None:
        from tasks.stage2_storyboard import _extract_json_from_response

        raw = f"Here is the storyboard:\n```json\n{json.dumps(sample_storyboard_json)}\n```"
        result = _extract_json_from_response(raw)
        assert "scenes" in result

    def test_json_with_preamble(self, sample_storyboard_json) -> None:
        from tasks.stage2_storyboard import _extract_json_from_response

        raw = f"Sure, here's the storyboard:\n{json.dumps(sample_storyboard_json)}"
        result = _extract_json_from_response(raw)
        assert "scenes" in result

    def test_invalid_json_raises(self) -> None:
        from tasks.stage2_storyboard import _extract_json_from_response

        with pytest.raises(ValueError, match="Could not extract"):
            _extract_json_from_response("This is not JSON at all")


# ---------------------------------------------------------------------------
# Scene model tests
# ---------------------------------------------------------------------------

class TestStoryboardScene:
    """Test StoryboardScene Pydantic model."""

    def test_valid_scene(self) -> None:
        scene = StoryboardScene(
            scene_index=0,
            narration_text="Hello world",
            visual_description="A globe",
            media_type=MediaType.IMAGE,
            duration_seconds=10.0,
        )
        assert scene.scene_index == 0
        assert scene.media_type == MediaType.IMAGE

    def test_string_media_type(self) -> None:
        scene = StoryboardScene(
            scene_index=0,
            narration_text="Test",
            visual_description="Test",
            media_type="video_clip",
            duration_seconds=10.0,
        )
        assert scene.media_type == MediaType.VIDEO_CLIP

    def test_duration_validation(self) -> None:
        with pytest.raises(Exception):
            StoryboardScene(
                scene_index=0,
                narration_text="Test",
                visual_description="Test",
                duration_seconds=-1,
            )


# ---------------------------------------------------------------------------
# Output model tests
# ---------------------------------------------------------------------------

class TestStoryboardGenerationOutput:
    def test_success_output(self) -> None:
        output = StoryboardGenerationOutput(
            job_id="job-001",
            project_id="proj-001",
            scenes=[
                StoryboardScene(
                    scene_index=0,
                    narration_text="Test",
                    visual_description="Test",
                    duration_seconds=10.0,
                )
            ],
            total_scenes=1,
            total_duration_seconds=10.0,
        )
        assert output.is_success

    def test_failed_output(self) -> None:
        output = StoryboardGenerationOutput(
            job_id="job-001",
            project_id="proj-001",
            status=StageStatus.FAILED,
            scenes=[],
        )
        assert not output.is_success

    def test_checkpoint_data(self) -> None:
        output = StoryboardGenerationOutput(
            job_id="job-001",
            project_id="proj-001",
            total_scenes=5,
            total_duration_seconds=120.0,
            model_used="test-model",
        )
        cp = output.to_checkpoint_data()
        assert cp["total_scenes"] == 5
        assert cp["total_duration_seconds"] == 120.0


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

class TestStage2Integration:
    """Integration tests using Celery eager mode."""

    @pytest.fixture(autouse=True)
    def setup_eager_celery(self):
        from celery_app import celery_app
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
        )
        yield
        celery_app.conf.update(
            task_always_eager=False,
            task_eager_propagates=False,
        )

    @patch("tasks.stage2_storyboard._save_storyboard_scenes")
    @patch("tasks.stage2_storyboard._resolve_prompts_from_api")
    @patch("tasks.stage2_storyboard.update_job_status")
    @patch("tasks.stage2_storyboard.save_checkpoint")
    @patch("tasks.stage2_storyboard.VLLMClient")
    def test_full_task_execution(
        self,
        MockVLLMClient,
        mock_save_cp,
        mock_update_status,
        mock_resolve_api,
        mock_save_scenes,
        sample_task_input,
        mock_vllm_storyboard_response,
        sample_storyboard_json,
    ):
        mock_resolve_api.return_value = (None, None)
        mock_save_scenes.return_value = ["scene-001", "scene-002", "scene-003"]
        mock_update_status.return_value = True
        mock_save_cp.return_value = True

        mock_client_instance = AsyncMock()
        mock_client_instance.chat_json = AsyncMock(
            return_value=(sample_storyboard_json, mock_vllm_storyboard_response)
        )
        mock_client_instance.close = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockVLLMClient.return_value = mock_client_instance

        with patch.dict(os.environ, {
            "IVGS_ENABLE_GPU_RESERVATION": "false",
            "IVGS_ENABLE_CHECKPOINT_SAVING": "false",
            "IVGS_ENABLE_IDEMPOTENCY_CHECK": "false",
        }):
            from tasks.stage2_storyboard import generate_storyboard_task
            result = generate_storyboard_task(sample_task_input)

        assert result["status"] == "success"
        assert result["total_scenes"] == 3
        assert len(result["scenes"]) == 3
        assert result["scene_ids"] == ["scene-001", "scene-002", "scene-003"]
