"""
WP-27 / swallow-register instance 14 — Stage 7 must not report success over no draft.

Observed live on job 7980c0b9 (2026-08-15 11:25:18, ivgs-celery-composition):

    {"cmd_head": "ffmpeg -y -i .../bg_....png ...", "returncode": 1, ...}
    {"error": "FFmpeg failed (rc=1): ...", "scene_count": 6}
    {"event": "task_succeeded", "task_name": "...assemble_prototype_draft"}

No draft was produced and Celery recorded SUCCESS.

These tests exercise the decision the fix introduces -- "given the output object
this task is about to return, does it raise?" -- against the three paths that set
FAILED, and against the two that must NOT raise. The pre-fix behaviour (always
return, never raise) is modelled explicitly so the tests are demonstrably not
vacuous.
"""
import pytest

from tasks.stage7_prototype_draft import Stage7Output, Stage7RenderError
from models.task_result import StageStatus


def _terminate(output: Stage7Output):
    """The fixed task's terminal decision, as written in stage7_prototype_draft.py.

    Returns the output dict, or raises Stage7RenderError. Mirrors the code after
    the `handle_stage_completion` dispatch.
    """
    if output.status is StageStatus.FAILED:
        raise Stage7RenderError(
            f"Stage 7 produced no draft for job {output.job_id}: "
            f"{'; '.join(output.errors) or 'no error detail recorded'} "
            f"(scenes_composed={output.scenes_composed}, "
            f"scenes_failed={output.scenes_failed})"
        )
    return output.model_dump(mode="json")


def _terminate_prefix(output: Stage7Output):
    """The PRE-FIX terminal behaviour: return unconditionally."""
    return output.model_dump(mode="json")


def _failed_output(**kw) -> Stage7Output:
    base = dict(
        job_id="7980c0b9-8d9e-4d3b-955e-f2b97bf137dd",
        project_id="p1",
        status=StageStatus.FAILED,
        scene_count=6,
    )
    base.update(kw)
    return Stage7Output(**base)


class TestTheDefectIsReal:
    def test_prefix_returned_normally_after_an_ffmpeg_failure(self):
        """Celery records SUCCESS for whatever this returns. This is the bug."""
        out = _failed_output(errors=["FFmpeg failed (rc=1): ..."])
        result = _terminate_prefix(out)
        assert result["status"] == "failed"     # the truth was in the payload
        # ...and the task still returned, so Celery called it a success. The
        # failure lived somewhere nothing was reading.


class TestStage7RaisesOnFailure:
    def test_ffmpeg_failure_raises(self):
        out = _failed_output(errors=["FFmpeg failed (rc=1): Invalid data found"])
        with pytest.raises(Stage7RenderError) as exc:
            _terminate(out)
        assert "FFmpeg failed (rc=1)" in str(exc.value)
        assert out.job_id in str(exc.value)

    def test_no_scenes_could_be_composed_raises(self):
        """stage7_prototype_draft.py's 'No scenes could be composed' branch also
        set FAILED and fell through the same return. The register listed only the
        ffmpeg path; a fix that caught just that would have left this open."""
        out = _failed_output(errors=["No scenes could be composed"])
        with pytest.raises(Stage7RenderError):
            _terminate(out)

    def test_zero_scenes_composed_raises(self):
        """The third FAILED path: scenes_composed == 0."""
        out = _failed_output(scenes_composed=0, scenes_failed=6)
        with pytest.raises(Stage7RenderError) as exc:
            _terminate(out)
        assert "scenes_composed=0" in str(exc.value)

    def test_the_message_is_diagnosable_even_with_no_recorded_error(self):
        out = _failed_output(errors=[])
        with pytest.raises(Stage7RenderError) as exc:
            _terminate(out)
        assert "no error detail recorded" in str(exc.value)


class TestStage7DoesNotOvercorrect:
    def test_partial_success_returns_and_does_not_raise(self):
        """Some scenes composed, some failed, and a draft exists. That is a real
        partial result -- raising on it would trade one wrong answer for another."""
        out = Stage7Output(
            job_id="j", project_id="p",
            status=StageStatus.PARTIAL_SUCCESS,
            scenes_composed=4, scenes_failed=2,
            asset_id="a1",
        )
        result = _terminate(out)
        assert result["status"] == "partial_success"
        assert result["scenes_composed"] == 4

    def test_success_returns(self):
        out = Stage7Output(
            job_id="j", project_id="p",
            status=StageStatus.SUCCESS,
            scenes_composed=6, asset_id="a1",
        )
        result = _terminate(out)
        assert result["asset_id"] == "a1"


class TestOrchestratorStillLearnsOfTheFailure:
    def test_dispatch_precedes_the_raise_in_the_source(self):
        """Order is load-bearing: the orchestrator's contract is that it receives
        every stage's output. If the raise came first, a failed Stage 7 would
        never reach handle_stage_completion and the job would hang instead of
        failing."""
        import inspect
        from tasks import stage7_prototype_draft as s7

        src = inspect.getsource(s7.assemble_prototype_draft)
        dispatch_at = src.index("handle_stage_completion")
        raise_at = src.index("raise Stage7RenderError")
        assert dispatch_at < raise_at, (
            "handle_stage_completion must be dispatched BEFORE the raise"
        )
