"""
WP-IVGS-0.1 — the user's runtime and description must reach the stage prompts.

Defect: the API dispatch payload omitted ``max_runtime_seconds``, so
``PipelineJobContext`` used its 600s default and every Stage 1/2 prompt said
"600 seconds". From Stage 2 onward ``_extract_context()`` rebuilt the context
from the previous stage's four-key output, so ``project_description`` was ``""``
for the rest of the run.

These tests render the REAL prompt templates and assert on the text the model
would actually be given.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest

from models.task_result import (
    PipelineJobContext,
    PipelineStage,
    RefinedTranscript,
    TranscriptRecord,
)

DESCRIPTION = "Reactor safety interlocks for shift technicians."
RUNTIME = 1800


def _job_context(**overrides: Any) -> PipelineJobContext:
    base: Dict[str, Any] = {
        "job_id": "job-1",
        "project_id": "11111111-1111-1111-1111-111111111111",
        "project_name": "Interlocks 101",
        "project_description": DESCRIPTION,
        "target_audience": "shift technicians",
        "max_runtime_seconds": RUNTIME,
        "language_code": "en-US",
        "current_stage": PipelineStage.TRANSCRIPT_REFINEMENT.value,
    }
    base.update(overrides)
    return PipelineJobContext(**base)


# ---------------------------------------------------------------------------
# The rendered prompts
# ---------------------------------------------------------------------------

class TestRenderedPrompts:
    def test_stage1_user_prompt_carries_runtime_and_description(self):
        from tasks.stage1_transcript import _load_template, _render_user_prompt

        ctx = _job_context()
        rendered = _render_user_prompt(
            template_str=_load_template("stage1_user.j2"),
            transcript=TranscriptRecord(
                id="t-1",
                project_id=ctx.project_id,
                sequence_order=1,
                original_text="Raw narration text.",
                language_code="en-US",
            ),
            context={
                "project_name": ctx.project_name,
                "project_description": ctx.project_description,
                "target_audience": ctx.target_audience,
                "max_runtime_seconds": ctx.max_runtime_seconds,
                "total_transcripts": 1,
            },
        )
        assert "1800" in rendered
        assert DESCRIPTION in rendered
        assert "600" not in rendered

    def test_stage2_user_prompt_carries_runtime_and_description(self):
        from tasks.stage2_storyboard import _load_template, _render_user_prompt

        ctx = _job_context()
        rendered = _render_user_prompt(
            template_str=_load_template("stage2_user.j2"),
            refined_transcripts=[
                RefinedTranscript(
                    transcript_id="t-1",
                    sequence_order=1,
                    original_text="Raw narration text.",
                    refined_text="Refined narration text.",
                )
            ],
            context={
                "project_name": ctx.project_name,
                "project_description": ctx.project_description,
                "target_audience": ctx.target_audience,
                "max_runtime_seconds": ctx.max_runtime_seconds,
                "target_scene_count": 0,
                "language_code": ctx.language_code,
            },
        )
        assert "1800" in rendered
        assert DESCRIPTION in rendered

    def test_negative_control_600_only_when_project_has_no_value(self):
        """The 600s default must be reachable ONLY through the model default."""
        from tasks.stage1_transcript import _load_template, _render_user_prompt

        # No max_runtime_seconds supplied anywhere -> the model's default.
        ctx = PipelineJobContext(job_id="job-2", project_id="p-2")
        assert ctx.max_runtime_seconds == 600

        rendered = _render_user_prompt(
            template_str=_load_template("stage1_user.j2"),
            transcript=TranscriptRecord(
                id="t-1", project_id="p-2", sequence_order=1,
                original_text="Raw.", language_code="en-US",
            ),
            context={
                "project_name": ctx.project_name,
                "project_description": ctx.project_description,
                "target_audience": ctx.target_audience,
                "max_runtime_seconds": ctx.max_runtime_seconds,
                "total_transcripts": 1,
            },
        )
        assert "600" in rendered
        assert "1800" not in rendered


# ---------------------------------------------------------------------------
# Context propagation through the orchestrator
# ---------------------------------------------------------------------------

class TestContextPropagation:
    def test_stage1_input_carries_the_full_context(self):
        from config import WorkerConfig
        from tasks import pipeline_orchestrator_v2 as orch

        ctx = _job_context()
        with patch.object(orch, "_fetch_transcripts", return_value=[]):
            task_input = orch._build_stage_input(
                PipelineStage.TRANSCRIPT_REFINEMENT.value, ctx, WorkerConfig(),
            )

        assert task_input["job_context"]["max_runtime_seconds"] == RUNTIME
        assert task_input["job_context"]["project_description"] == DESCRIPTION
        assert task_input["max_runtime_seconds"] == RUNTIME
        assert task_input["project_description"] == DESCRIPTION

    def test_later_stages_read_the_stored_context_not_the_stage_output(self):
        """The bug: handle_stage_completion passes job_context=None.

        The previous stage's output carries four keys and none of them is the
        description or the runtime. The stored context must win.
        """
        from config import WorkerConfig
        from tasks import pipeline_orchestrator_v2 as orch

        previous_output = {
            "job_id": "job-1",
            "project_id": "11111111-1111-1111-1111-111111111111",
            "project_name": "Interlocks 101",
            "language_code": "en-US",
            "stage": PipelineStage.TRANSCRIPT_REFINEMENT.value,
        }

        with patch.object(
            orch, "_get_job_context",
            return_value=_job_context().model_dump(mode="json"),
        ):
            task_input = orch._build_stage_input(
                PipelineStage.STORYBOARD_GENERATION.value,
                None,
                WorkerConfig(),
                previous_output,
            )

        assert task_input["job_context"]["max_runtime_seconds"] == RUNTIME
        assert task_input["job_context"]["project_description"] == DESCRIPTION

    def test_store_miss_is_loud_and_degraded_not_silent(self):
        """With no stored context the salvage path runs — and says so."""
        from config import WorkerConfig
        from tasks import pipeline_orchestrator_v2 as orch

        previous_output = {
            "job_id": "job-1",
            "project_id": "p-1",
            "project_name": "Interlocks 101",
            "language_code": "en-US",
        }

        with patch.object(orch, "_get_job_context", return_value=None), \
                patch.object(orch.logger, "error") as err:
            task_input = orch._build_stage_input(
                PipelineStage.STORYBOARD_GENERATION.value,
                None,
                WorkerConfig(),
                previous_output,
            )

        assert err.called
        assert err.call_args[0][0] == "job_context_store_miss"
        # The salvage really is lossy — that is why it is logged as an error.
        assert task_input["job_context"].get("project_description", "") == ""
