"""
WP-IVGS-0.3 — the production tier must be reachable.

Defect: neither dispatch payload set ``tier``, so ``PipelineJobContext.tier``
defaulted to "prototype" and every ``get_binding(..., tier=...)`` in every stage
resolved prototype. The production tier could not be reached from the API at
all.

These tests assert the tier survives the whole worker-side path: job context ->
stage input -> the tier the stage hands to get_binding.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from models.task_result import PipelineJobContext, PipelineStage


def _context(tier: str) -> PipelineJobContext:
    return PipelineJobContext(
        job_id="job-1",
        project_id="11111111-1111-1111-1111-111111111111",
        project_name="P",
        tier=tier,
    )


class TestTierReachesTheStageInput:
    @pytest.mark.parametrize("tier", ["prototype", "production"])
    def test_stage_input_carries_the_dispatched_tier(self, tier):
        from config import WorkerConfig
        from tasks import pipeline_orchestrator_v2 as orch

        with patch.object(orch, "_fetch_transcripts", return_value=[]):
            task_input = orch._build_stage_input(
                PipelineStage.TRANSCRIPT_REFINEMENT.value,
                _context(tier),
                WorkerConfig(),
            )

        assert task_input["job_context"]["tier"] == tier
        # The flat-input stages (3, 5, 6) read it off the top level.
        assert task_input["tier"] == tier

    def test_tier_survives_into_a_later_stage(self):
        """handle_stage_completion passes job_context=None; the store must win."""
        from config import WorkerConfig
        from tasks import pipeline_orchestrator_v2 as orch

        with patch.object(
            orch, "_get_job_context",
            return_value=_context("production").model_dump(mode="json"),
        ):
            task_input = orch._build_stage_input(
                PipelineStage.STORYBOARD_GENERATION.value,
                None,
                WorkerConfig(),
                {"job_id": "job-1", "project_id": "p-1"},
            )

        assert task_input["tier"] == "production"
        assert task_input["job_context"]["tier"] == "production"


class TestStagePassesTierToGetBinding:
    @pytest.mark.asyncio
    async def test_stage5_asks_get_binding_for_the_dispatched_tier(self):
        """The end of the chain: what tier does get_binding actually receive?"""
        from unittest.mock import AsyncMock

        from utils.llm_binding import resolve_text_llm_binding

        stub = AsyncMock()
        stub.return_value = _fake_vllm_binding()
        with patch("utils.llm_binding.get_binding", stub):
            await resolve_text_llm_binding(
                "transcript_refinement",
                project_id="11111111-1111-1111-1111-111111111111",
                tier="production",
                purpose="test",
            )

        assert stub.await_args.kwargs["tier"] == "production"


def _fake_vllm_binding():
    import uuid

    from shared.providers.binding import ModelBinding

    return ModelBinding(
        model_id=uuid.uuid4(),
        name="m",
        display_name="M",
        stage="transcript_refinement",
        engine="vllm",
        tier="production",
        endpoint="http://192.168.1.91:8000",
    )
