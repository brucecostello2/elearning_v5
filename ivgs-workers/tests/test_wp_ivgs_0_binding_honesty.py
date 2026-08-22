"""
WP-IVGS-0.2 — a stage must run the model it reports.

Defect: Stage 1, Stage 3's prompt writer and Stage 5's text optimiser all made
their vLLM call with ``model=vllm_config["model"], base_url=vllm_config["base_url"]``
— the env profile — while reporting the AD-01 binding they had selected.
Stage 5 asked for the ``image_generation`` profile to do a text job. Stage 2
was already correct and is the pattern all three now follow.

Each test stubs a binding whose endpoint and model differ from the env config
and asserts the HTTP call went to the BINDING.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from clients.vllm_client import (
    VLLMChoice,
    VLLMMessage,
    VLLMResponse,
    VLLMUsage,
)
from models.task_result import TranscriptRecord
from shared.providers.binding import ModelBinding

# Deliberately unlike anything the env config can produce.
BINDING_ENDPOINT = "http://192.168.1.99:9999"
BINDING_ENGINE_MODEL = "bound-model-engine-handle"


def _binding(engine: str = "vllm", name: str = "bound-model-store-name"):
    return ModelBinding(
        model_id=__import__("uuid").uuid4(),
        name=name,
        display_name=name,
        stage="transcript_refinement",
        engine=engine,
        tier="prototype",
        endpoint=BINDING_ENDPOINT,
        default_params={"engine_model": BINDING_ENGINE_MODEL},
    )


def _response(content: str = "refined text") -> VLLMResponse:
    return VLLMResponse(
        id="cmpl-1",
        model="served-model-reported-by-engine",
        choices=[
            VLLMChoice(
                index=0,
                message=VLLMMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=VLLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _env_config_differs(config, stage: str) -> None:
    """Guard: the test is meaningless if env and binding happen to agree."""
    env = config.get_vllm_config_for_stage(stage)
    assert env["base_url"] != BINDING_ENDPOINT
    assert env["model"] != BINDING_ENGINE_MODEL


# ---------------------------------------------------------------------------
# Site 1 — Stage 1 transcript refinement
# ---------------------------------------------------------------------------

class TestStage1UsesTheBinding:
    @pytest.mark.asyncio
    async def test_call_goes_to_the_binding_not_the_env_config(self):
        from config import WorkerConfig
        from tasks.stage1_transcript import _refine_single_transcript

        config = WorkerConfig()
        _env_config_differs(config, "transcript_refinement")

        client = SimpleNamespace(chat=AsyncMock(return_value=_response()))
        result, error = await _refine_single_transcript(
            transcript=TranscriptRecord(
                id="t-1", project_id="p-1", sequence_order=1,
                original_text="Raw.", language_code="en-US",
            ),
            system_prompt="sys",
            user_prompt_template="{{ transcript_text }}",
            job_context={"project_name": "P", "max_runtime_seconds": 1800},
            vllm_client=client,
            binding=_binding(),
            config=config,
        )

        assert error is None
        kwargs = client.chat.await_args.kwargs
        assert kwargs["model"] == BINDING_ENGINE_MODEL
        assert kwargs["base_url"] == BINDING_ENDPOINT

    def test_model_used_is_what_ran_not_what_was_selected(self):
        """output.model_used must be the engine's served model."""
        import asyncio

        from config import WorkerConfig
        from tasks.stage1_transcript import _refine_single_transcript

        client = SimpleNamespace(chat=AsyncMock(return_value=_response()))
        result, _ = asyncio.run(
            _refine_single_transcript(
                transcript=TranscriptRecord(
                    id="t-1", project_id="p-1", sequence_order=1,
                    original_text="Raw.", language_code="en-US",
                ),
                system_prompt="sys",
                user_prompt_template="{{ transcript_text }}",
                job_context={},
                vllm_client=client,
                binding=_binding(),
                config=WorkerConfig(),
            )
        )
        # The task copies this into output.model_used.
        assert result.refinement_metadata["model"] == (
            "served-model-reported-by-engine"
        )
        assert result.refinement_metadata["model"] != "bound-model-store-name"


# ---------------------------------------------------------------------------
# Site 2 — Stage 3 image-prompt writer
# ---------------------------------------------------------------------------

class TestStage3PromptWriterUsesTheBinding:
    @pytest.mark.asyncio
    async def test_call_goes_to_the_binding_not_the_env_config(self):
        from config import WorkerConfig
        from tasks.stage3_images import SceneImageInput, _generate_image_prompt

        config = WorkerConfig()
        _env_config_differs(config, "image_generation")

        client = SimpleNamespace(
            chat=AsyncMock(return_value=_response("a lit control room"))
        )
        await _generate_image_prompt(
            scene=SceneImageInput(
                scene_id="s-1", scene_index=0, visual_description="control room",
            ),
            project_context={"project_name": "P"},
            vllm_client=client,
            prompt_binding=_binding(),
            config=config,
        )

        kwargs = client.chat.await_args.kwargs
        assert kwargs["model"] == BINDING_ENGINE_MODEL
        assert kwargs["base_url"] == BINDING_ENDPOINT


# ---------------------------------------------------------------------------
# Site 3 — Stage 5 narration text optimiser
# ---------------------------------------------------------------------------

class TestStage5TextOptimiserUsesTheBinding:
    @pytest.mark.asyncio
    async def test_call_goes_to_the_binding_not_the_env_config(self):
        from config import WorkerConfig
        from tasks.stage5_voiceover import (
            SceneVoiceoverInput,
            _optimize_narration_text,
        )

        config = WorkerConfig()
        _env_config_differs(config, "transcript_refinement")

        client = SimpleNamespace(
            chat=AsyncMock(return_value=_response("optimised narration"))
        )
        out = await _optimize_narration_text(
            narration_text="raw narration",
            scene=SceneVoiceoverInput(
                scene_id="s-1", scene_index=0, narration_text="raw narration",
            ),
            project_context={"project_name": "P"},
            vllm_client=client,
            text_binding=_binding(),
            config=config,
        )

        assert out == "optimised narration"
        kwargs = client.chat.await_args.kwargs
        assert kwargs["model"] == BINDING_ENGINE_MODEL
        assert kwargs["base_url"] == BINDING_ENDPOINT

    def test_it_no_longer_asks_for_the_image_profile(self):
        """A TTS-adjacent text job must not request the image vLLM profile."""
        import inspect

        from tasks import stage5_voiceover

        src = inspect.getsource(stage5_voiceover._optimize_narration_text)
        assert 'get_vllm_config_for_stage("image_generation")' not in src
        assert 'get_vllm_config_for_stage("transcript_refinement")' in src


# ---------------------------------------------------------------------------
# The borrowed-binding guard
# ---------------------------------------------------------------------------

class TestTextLLMBindingGuard:
    @pytest.mark.asyncio
    async def test_a_non_chat_engine_is_refused_loudly(self):
        from utils.llm_binding import (
            TextLLMBindingError,
            resolve_text_llm_binding,
        )

        with patch(
            "utils.llm_binding.get_binding",
            AsyncMock(return_value=_binding(engine="comfyui", name="flux1-dev")),
        ):
            with pytest.raises(TextLLMBindingError, match="comfyui"):
                await resolve_text_llm_binding(
                    "image_generation",
                    project_id="11111111-1111-1111-1111-111111111111",
                    tier="prototype",
                    purpose="test",
                )

    @pytest.mark.asyncio
    async def test_a_chat_engine_is_returned(self):
        from utils.llm_binding import resolve_text_llm_binding

        with patch(
            "utils.llm_binding.get_binding",
            AsyncMock(return_value=_binding(engine="vllm")),
        ):
            b = await resolve_text_llm_binding(
                "storyboard_generation",
                project_id="11111111-1111-1111-1111-111111111111",
                tier="prototype",
                purpose="test",
            )
        assert b.endpoint == BINDING_ENDPOINT
