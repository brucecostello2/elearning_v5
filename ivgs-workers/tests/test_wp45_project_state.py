"""WP-45 Task 2(a) — the state machine finally gets a caller (ORCH-5).

`ProjectService.transition_state` has been implemented and validated against
`PROJECT_STATE_TRANSITIONS` since Phase 3, with no route and no caller. Only
three writers ever touched `projects.state`: `trigger_pipeline`,
`approve_storyboard`, and WP-38's scene-write edge. So five of the thirteen
declared states — MANIFEST_GENERATION, AUDIO_GENERATION, TALKING_HEAD_RENDER,
PROTOTYPE_DRAFT, USER_REVIEW — could not appear on any project, and spec §6.1's
"post-assembly: project state transitions to USER_REVIEW", which the whole
draft-review gate depends on, never happened. `stage7_prototype_draft.py` lists
it as step 9 in its own docstring and no code performs it (WP-39 §4 Gap A).

The orchestrator is the caller because it is the only component that knows a
stage finished and which one runs next. These tests pin the map and the
call-site behaviour without a broker or an API.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _import_orchestrator():
    """Import the orchestrator, or skip with the reason.

    It imports celery_app, which asserts several environment variables at
    module scope. Where those are absent the map itself is still worth
    checking, so the tests that need only the constants say so.
    """
    try:
        import tasks.pipeline_orchestrator_v2 as orchestrator
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"orchestrator not importable in this environment: {exc}")
    return orchestrator


class TestTheStateMapCoversTheBackHalf:

    def test_every_stage_maps_to_a_project_state(self):
        orchestrator = _import_orchestrator()
        from models.task_result import PipelineStage

        for stage in PipelineStage:
            assert stage.value in orchestrator.STAGE_PROJECT_STATE, stage.value

    def test_the_five_unreachable_states_are_now_reachable(self):
        # The exact five WP-39 §4 named. If any of these ever drops out of the
        # map, the back half goes back to being invisible.
        orchestrator = _import_orchestrator()
        produced = set(orchestrator.STAGE_PROJECT_STATE.values()) | set(
            orchestrator.GATE_PROJECT_STATE.values()
        )
        for state in (
            "MANIFEST_GENERATION", "AUDIO_GENERATION", "TALKING_HEAD_RENDER",
            "PROTOTYPE_DRAFT", "USER_REVIEW",
        ):
            assert state in produced, state

    def test_the_three_media_stages_all_mean_media_generation(self):
        orchestrator = _import_orchestrator()
        from models.task_result import PipelineStage

        for stage in (
            PipelineStage.IMAGE_GENERATION,
            PipelineStage.VIDEO_GENERATION,
            PipelineStage.ANIMATION_GENERATION,
        ):
            assert orchestrator.STAGE_PROJECT_STATE[stage.value] == "MEDIA_GENERATION"

    def test_a_finished_draft_leaves_the_project_in_user_review(self):
        # Spec §6.1, and the state POST /projects/{id}/trigger accepts. This
        # single entry is what makes "Start final render" reachable at all.
        orchestrator = _import_orchestrator()
        from models.task_result import PipelineStage

        assert orchestrator.GATE_PROJECT_STATE[
            PipelineStage.PROTOTYPE_DRAFT.value
        ] == "USER_REVIEW"

    def test_a_finished_render_completes_the_project(self):
        orchestrator = _import_orchestrator()
        from models.task_result import PipelineStage

        assert orchestrator.GATE_PROJECT_STATE[
            PipelineStage.FINAL_RENDER.value
        ] == "COMPLETE"

    def test_the_storyboard_gate_is_deliberately_absent(self):
        # The project is already in STORYBOARD_GENERATION and the next write
        # belongs to approve_storyboard - the human's decision, not the
        # pipeline's. Pinned so it is not "helpfully" added later.
        orchestrator = _import_orchestrator()
        from models.task_result import PipelineStage

        assert PipelineStage.STORYBOARD_GENERATION.value not in (
            orchestrator.GATE_PROJECT_STATE
        )

    def test_every_hop_the_map_produces_is_one_the_spec_sanctions(self):
        # This adds a CALLER, not a new rule. Each stage transition must
        # produce a project-state hop the §6.1 table already permits.
        orchestrator = _import_orchestrator()
        from shared.models.enums import PROJECT_STATE_TRANSITIONS, ProjectState

        for completed, next_stage in orchestrator.STAGE_TRANSITIONS.items():
            if next_stage is None:
                continue
            before = orchestrator.STAGE_PROJECT_STATE.get(completed)
            after = orchestrator.STAGE_PROJECT_STATE.get(next_stage)
            if before is None or after is None or before == after:
                continue
            allowed = PROJECT_STATE_TRANSITIONS[ProjectState(before)]
            assert ProjectState(after) in allowed, (
                f"{completed} -> {next_stage} implies {before} -> {after}, "
                "which the §6.1 transition table does not permit"
            )

    def test_the_gate_hops_are_sanctioned_too(self):
        orchestrator = _import_orchestrator()
        from shared.models.enums import PROJECT_STATE_TRANSITIONS, ProjectState

        for completed, gate_state in orchestrator.GATE_PROJECT_STATE.items():
            before = orchestrator.STAGE_PROJECT_STATE[completed]
            allowed = PROJECT_STATE_TRANSITIONS[ProjectState(before)]
            assert ProjectState(gate_state) in allowed, (
                f"gate after {completed}: {before} -> {gate_state}"
            )


class TestAdvanceProjectStateIsLoudButNotFatal:
    """The helper that calls PATCH /projects/{id}/state."""

    def _patched(self, status_code, text=""):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        client = MagicMock()
        client.patch.return_value = response
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client

    def test_a_200_is_true(self):
        from utils import error_handler

        with patch("httpx.Client", return_value=self._patched(200)):
            assert error_handler.advance_project_state("p1", "USER_REVIEW", "gate") is True

    def test_the_body_carries_the_state_and_the_reason(self):
        from utils import error_handler

        client = self._patched(200)
        with patch("httpx.Client", return_value=client):
            error_handler.advance_project_state("p1", "USER_REVIEW", "gate after draft")
        body = client.patch.call_args.kwargs["json"]
        assert body == {"state": "USER_REVIEW", "reason": "gate after draft"}

    def test_a_failure_is_false_and_never_raises(self):
        # A project-state write is a record of where the pipeline is. The
        # pipeline itself is the thing that matters and must not stop because
        # bookkeeping failed.
        from utils import error_handler

        with patch("httpx.Client", side_effect=OSError("api down")):
            assert error_handler.advance_project_state("p1", "USER_REVIEW") is False

    def test_a_failure_is_logged_loudly_with_its_consequence(self):
        # Not the silent False the swallow register exists to catch.
        from utils import error_handler

        with patch("httpx.Client", return_value=self._patched(500, "boom")):
            with patch.object(error_handler, "logger") as log:
                error_handler.advance_project_state("p1", "USER_REVIEW")
        assert log.error.called
        assert log.error.call_args[0][0] == "project_state_advance_failed"
        assert "stale" in log.error.call_args.kwargs["consequence"]

    def test_a_409_is_a_warning_not_an_error(self):
        # The state machine refused the hop - usually because a human moved the
        # project while a stage was running. That is information about the run,
        # not a fault in this call.
        from utils import error_handler

        with patch("httpx.Client", return_value=self._patched(409, "invalid")):
            with patch.object(error_handler, "logger") as log:
                assert error_handler.advance_project_state("p1", "COMPLETE") is False
        assert log.warning.called
        assert not log.error.called

    def test_a_missing_project_id_is_skipped_rather_than_requested(self):
        from utils import error_handler

        with patch("httpx.Client") as client:
            assert error_handler.advance_project_state("", "USER_REVIEW") is False
        assert not client.called
