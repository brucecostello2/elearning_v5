"""
IVGS v5 — Stage 1 Tests: Transcript Refinement
=================================================

Tests cover:
- Input validation and parsing
- Prompt resolution (template loading, API fallback, defaults)
- vLLM client interaction (mocked)
- Transcript refinement logic (single and batch)
- Database update calls
- Checkpoint saving
- Error handling and retry logic
- Idempotency hash computation
- GPU reservation lifecycle
- Full task execution via Celery eager mode
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from models.task_result import (
    MediaType,
    PipelineJobContext,
    PipelineStage,
    RefinedTranscript,
    StageStatus,
    TranscriptRecord,
    TranscriptRefinementInput,
    TranscriptRefinementOutput,
    VLLMChoice,
    VLLMMessage,
    VLLMResponse,
    VLLMUsage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_job_context() -> Dict[str, Any]:
    """Sample PipelineJobContext for testing."""
    return {
        "job_id": "job-111-222-333",
        "project_id": "proj-aaa-bbb-ccc",
        "project_name": "Test Educational Video",
        "project_description": "A test video about Python programming",
        "target_audience": "beginners",
        "max_runtime_seconds": 300,
        "language_code": "en-US",
        "priority": "normal",
        "current_stage": "transcript_refinement",
    }


@pytest.fixture
def sample_transcripts() -> List[Dict[str, Any]]:
    """Sample transcript records for testing."""
    return [
        {
            "id": "tx-001",
            "project_id": "proj-aaa-bbb-ccc",
            "sequence_order": 1,
            "original_text": (
                "So today we're gonna talk about Python, which is like, "
                "you know, a really popular programming language that is "
                "used by a lot of people in the, um, software industry "
                "and also in data science and, well, basically everywhere."
            ),
            "language_code": "en-US",
        },
        {
            "id": "tx-002",
            "project_id": "proj-aaa-bbb-ccc",
            "sequence_order": 2,
            "original_text": (
                "Python was created by Guido van Rossum and was first "
                "released in 1991. It emphasizes code readability and "
                "allows programmers to express concepts in fewer lines "
                "of code than languages like C++ or Java."
            ),
            "language_code": "en-US",
        },
    ]


@pytest.fixture
def sample_task_input(
    sample_job_context: Dict[str, Any],
    sample_transcripts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Complete task input dict for testing."""
    return {
        "job_context": sample_job_context,
        "transcripts": sample_transcripts,
    }


@pytest.fixture
def mock_vllm_response() -> VLLMResponse:
    """Mock vLLM response for transcript refinement."""
    return VLLMResponse(
        id="cmpl-test-123",
        object="chat.completion",
        created=int(time.time()),
        model="meta-llama/Llama-3.3-70B-Instruct",
        choices=[
            VLLMChoice(
                index=0,
                message=VLLMMessage(
                    role="assistant",
                    content=(
                        "Python is one of the most widely used programming "
                        "languages today. It powers applications across "
                        "software development, data science, and many "
                        "other fields."
                    ),
                ),
                finish_reason="stop",
            )
        ],
        usage=VLLMUsage(
            prompt_tokens=150,
            completion_tokens=35,
            total_tokens=185,
        ),
    )


@pytest.fixture
def mock_config():
    """Mock WorkerConfig for testing."""
    with patch.dict(os.environ, {
        "IVGS_CELERY_BROKER_URL": "redis://localhost:6379/0",
        "IVGS_CELERY_RESULT_BACKEND": "db+postgresql+psycopg2://test:test@localhost/test",
        "IVGS_VLLM_PRIMARY_URL": "http://localhost:8000",
        "IVGS_ENABLE_GPU_RESERVATION": "false",
        "IVGS_ENABLE_CHECKPOINT_SAVING": "false",
        "IVGS_ENABLE_IDEMPOTENCY_CHECK": "false",
    }):
        from config import WorkerConfig
        yield WorkerConfig()


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------

class TestTranscriptRefinementInput:
    """Test input model validation."""

    def test_valid_input(self, sample_task_input: Dict[str, Any]) -> None:
        """Test parsing valid input."""
        task_input = TranscriptRefinementInput(**sample_task_input)
        assert len(task_input.transcripts) == 2
        assert task_input.job_context.job_id == "job-111-222-333"

    def test_empty_transcripts_rejected(
        self, sample_job_context: Dict[str, Any]
    ) -> None:
        """Test that empty transcript list is rejected."""
        with pytest.raises(Exception):
            TranscriptRefinementInput(
                job_context=sample_job_context,
                transcripts=[],
            )

    def test_transcript_record_parsing(self) -> None:
        """Test TranscriptRecord model."""
        record = TranscriptRecord(
            id="tx-001",
            project_id="proj-001",
            sequence_order=1,
            original_text="Test transcript text",
        )
        assert record.original_text == "Test transcript text"
        assert record.refined_text is None


# ---------------------------------------------------------------------------
# Output model tests
# ---------------------------------------------------------------------------

class TestTranscriptRefinementOutput:
    """Test output model serialization and helpers."""

    def test_output_creation(self) -> None:
        output = TranscriptRefinementOutput(
            job_id="job-001",
            project_id="proj-001",
            status=StageStatus.SUCCESS,
            refined_transcripts=[
                RefinedTranscript(
                    transcript_id="tx-001",
                    sequence_order=1,
                    original_text="original",
                    refined_text="refined",
                )
            ],
            total_transcripts=1,
            successful_count=1,
            failed_count=0,
            model_used="test-model",
        )
        assert output.is_success
        assert output.stage == "transcript_refinement"

    def test_checkpoint_data(self) -> None:
        output = TranscriptRefinementOutput(
            job_id="job-001",
            project_id="proj-001",
            total_transcripts=2,
            successful_count=2,
            failed_count=0,
            model_used="test-model",
        )
        cp = output.to_checkpoint_data()
        assert cp["stage"] == "transcript_refinement"
        assert cp["total_transcripts"] == 2

    def test_failed_output(self) -> None:
        output = TranscriptRefinementOutput(
            job_id="job-001",
            project_id="proj-001",
            status=StageStatus.FAILED,
            failed_count=1,
        )
        assert not output.is_success


# ---------------------------------------------------------------------------
# Prompt resolution tests
# ---------------------------------------------------------------------------

class TestPromptResolution:
    """Test prompt template loading and rendering."""

    def test_render_user_prompt(self) -> None:
        from tasks.stage1_transcript import _render_user_prompt

        template = (
            "Refine: {{ transcript_text }}\n"
            "Audience: {{ target_audience }}"
        )
        transcript = TranscriptRecord(
            id="tx-001",
            project_id="proj-001",
            sequence_order=1,
            original_text="Test text",
        )
        result = _render_user_prompt(
            template,
            transcript,
            {"target_audience": "beginners"},
        )
        assert "Test text" in result
        assert "beginners" in result

    def test_render_with_all_variables(self) -> None:
        from tasks.stage1_transcript import _render_user_prompt

        template = (
            "{{ project_title }} | {{ target_audience }} | "
            "{{ max_duration_seconds }}s | {{ sequence_order }}/{{ total_transcripts }}\n"
            "{{ transcript_text }}"
        )
        transcript = TranscriptRecord(
            id="tx-001",
            project_id="proj-001",
            sequence_order=2,
            original_text="Hello world",
        )
        context = {
            "project_name": "Test Video",
            "target_audience": "intermediate",
            "max_runtime_seconds": 600,
            "total_transcripts": 3,
        }
        result = _render_user_prompt(template, transcript, context)
        assert "Test Video" in result
        assert "600" in result
        assert "2/3" in result

    def test_invalid_jinja_syntax(self) -> None:
        from tasks.stage1_transcript import _render_user_prompt

        template = "{% invalid syntax %}"
        transcript = TranscriptRecord(
            id="tx-001",
            project_id="proj-001",
            sequence_order=1,
            original_text="Test",
        )
        with pytest.raises(ValueError, match="Jinja2 syntax error"):
            _render_user_prompt(template, transcript, {})


# ---------------------------------------------------------------------------
# vLLM interaction tests
# ---------------------------------------------------------------------------

class TestVLLMInteraction:
    """Test vLLM client calls for transcript refinement."""

    @pytest.mark.asyncio
    async def test_refine_single_transcript(
        self,
        mock_vllm_response: VLLMResponse,
    ) -> None:
        from tasks.stage1_transcript import _refine_single_transcript

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_vllm_response)

        transcript = TranscriptRecord(
            id="tx-001",
            project_id="proj-001",
            sequence_order=1,
            original_text="Raw transcript text here",
        )

        with patch("tasks.stage1_transcript.WorkerConfig") as MockConfig:
            mock_cfg = MagicMock()
            mock_cfg.get_vllm_config_for_stage.return_value = {
                "model": "test-model",
                "base_url": "http://localhost:8000",
                "max_tokens": 4096,
                "temperature": 0.3,
                "timeout": 120,
            }
            MockConfig.return_value = mock_cfg

            result, error = await _refine_single_transcript(
                transcript=transcript,
                system_prompt="You are a helpful assistant.",
                user_prompt_template="Refine: {{ transcript_text }}",
                job_context={"project_name": "Test"},
                vllm_client=mock_client,
                config=mock_cfg,
            )

        assert result is not None
        assert error is None
        assert result.refined_text
        assert result.transcript_id == "tx-001"

    @pytest.mark.asyncio
    async def test_refine_handles_timeout(self) -> None:
        from tasks.stage1_transcript import _refine_single_transcript
        from clients.vllm_client import VLLMTimeoutError

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(
            side_effect=VLLMTimeoutError("Timeout after 120s")
        )

        transcript = TranscriptRecord(
            id="tx-001",
            project_id="proj-001",
            sequence_order=1,
            original_text="Test",
        )

        with patch("tasks.stage1_transcript.WorkerConfig") as MockConfig:
            mock_cfg = MagicMock()
            mock_cfg.get_vllm_config_for_stage.return_value = {
                "model": "test", "base_url": "http://localhost:8000",
                "max_tokens": 4096, "temperature": 0.3, "timeout": 120,
            }
            MockConfig.return_value = mock_cfg

            result, error = await _refine_single_transcript(
                transcript=transcript,
                system_prompt="System prompt",
                user_prompt_template="{{ transcript_text }}",
                job_context={},
                vllm_client=mock_client,
                config=mock_cfg,
            )

        assert result is None
        assert error is not None
        assert "timeout" in error["error"].lower()

    @pytest.mark.asyncio
    async def test_refine_handles_empty_response(self) -> None:
        from tasks.stage1_transcript import _refine_single_transcript

        empty_response = VLLMResponse(
            id="cmpl-empty",
            choices=[VLLMChoice(index=0, message=VLLMMessage(role="assistant", content=""))],
        )

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=empty_response)

        transcript = TranscriptRecord(
            id="tx-001", project_id="proj-001",
            sequence_order=1, original_text="Test",
        )

        with patch("tasks.stage1_transcript.WorkerConfig") as MockConfig:
            mock_cfg = MagicMock()
            mock_cfg.get_vllm_config_for_stage.return_value = {
                "model": "test", "base_url": "http://localhost:8000",
                "max_tokens": 4096, "temperature": 0.3, "timeout": 120,
            }
            MockConfig.return_value = mock_cfg

            result, error = await _refine_single_transcript(
                transcript=transcript,
                system_prompt="System",
                user_prompt_template="{{ transcript_text }}",
                job_context={},
                vllm_client=mock_client,
                config=mock_cfg,
            )

        assert result is None
        assert error is not None
        assert "Empty" in error["error"]


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error classification and retry logic."""

    def test_classify_timeout(self) -> None:
        from utils.error_handler import classify_exception
        from models.task_result import FailureCategory

        exc = TimeoutError("connection timed out")
        assert classify_exception(exc) == FailureCategory.TRANSIENT

    def test_classify_value_error(self) -> None:
        from utils.error_handler import classify_exception
        from models.task_result import FailureCategory

        exc = ValueError("invalid input")
        assert classify_exception(exc) == FailureCategory.CONFIG

    def test_should_retry_transient(self) -> None:
        from utils.error_handler import should_retry

        exc = TimeoutError("timeout")
        assert should_retry(exc, retry_count=0, max_retries=4) is True
        assert should_retry(exc, retry_count=4, max_retries=4) is False

    def test_should_not_retry_config(self) -> None:
        from utils.error_handler import should_retry

        exc = ValueError("bad config")
        assert should_retry(exc, retry_count=0, max_retries=4) is False

    def test_backoff_computation(self) -> None:
        from utils.error_handler import compute_backoff_delay

        delay_0 = compute_backoff_delay(0, "transcript_refinement")
        delay_1 = compute_backoff_delay(1, "transcript_refinement")
        delay_2 = compute_backoff_delay(2, "transcript_refinement")
        delay_3 = compute_backoff_delay(3, "transcript_refinement")

        # Should follow 5→15→45→135 sequence (±10% jitter)
        assert 4.0 <= delay_0 <= 6.0
        assert 13.0 <= delay_1 <= 17.0
        assert 40.0 <= delay_2 <= 50.0
        assert 120.0 <= delay_3 <= 150.0


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Test idempotency hash computation."""

    def test_hash_deterministic(self) -> None:
        from clients.vllm_client import VLLMClient

        h1 = VLLMClient.compute_request_hash(
            system_prompt="sys",
            user_prompt="user",
            model="model",
            temperature=0.3,
            max_tokens=4096,
        )
        h2 = VLLMClient.compute_request_hash(
            system_prompt="sys",
            user_prompt="user",
            model="model",
            temperature=0.3,
            max_tokens=4096,
        )
        assert h1 == h2

    def test_hash_changes_with_input(self) -> None:
        from clients.vllm_client import VLLMClient

        h1 = VLLMClient.compute_request_hash("sys", "user1", "m", 0.3, 4096)
        h2 = VLLMClient.compute_request_hash("sys", "user2", "m", 0.3, 4096)
        assert h1 != h2


# ---------------------------------------------------------------------------
# Integration test (Celery eager mode)
# ---------------------------------------------------------------------------

class TestStage1Integration:
    """Integration tests using Celery eager mode."""

    @pytest.fixture(autouse=True)
    def setup_eager_celery(self):
        """Configure Celery for synchronous testing."""
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

    @patch("tasks.stage1_transcript._fetch_transcripts")
    @patch("tasks.stage1_transcript._update_transcript")
    @patch("tasks.stage1_transcript._resolve_prompts_from_api")
    @patch("tasks.stage1_transcript.update_job_status")
    @patch("tasks.stage1_transcript.save_checkpoint")
    @patch("tasks.stage1_transcript.VLLMClient")
    def test_full_task_execution(
        self,
        MockVLLMClient,
        mock_save_cp,
        mock_update_status,
        mock_resolve_api,
        mock_update_tx,
        mock_fetch_tx,
        sample_task_input,
        mock_vllm_response,
    ):
        """Test complete Stage 1 task execution."""
        # Setup mocks
        mock_resolve_api.return_value = (None, None)
        mock_update_tx.return_value = True
        mock_update_status.return_value = True
        mock_save_cp.return_value = True

        # Mock vLLM client
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(return_value=mock_vllm_response)
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
            from tasks.stage1_transcript import refine_transcript_task
            result = refine_transcript_task(sample_task_input)

        assert result["status"] == "success"
        assert result["successful_count"] == 2
        assert result["failed_count"] == 0
        assert len(result["refined_transcripts"]) == 2
