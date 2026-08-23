"""
WP-36 — the failure handler must not be the thing that fails.

From the first end-to-end run, 2026-08-23: job 768c4b59 failed (correctly — the
checkpoint write was being 401'd), and the DLQ filing that should have retained
that failure **crashed on its own inputs**:

    dlq_routing_failed ... pydantic ValidationError
      job_id:     Input should be a valid string [input_value=None]
      project_id: Input should be a valid string [input_value=None]

`create_error_detail` declares `job_id: Optional[str] = None` and
`project_id: Optional[str] = None` and passes them straight into `ErrorDetail`,
where both are non-optional `str = ""` (models/task_result.py:314-315). Any task
failing early enough not to know its own ids therefore cannot be filed.

The consequence is worse than a noisy log: `IVGSBaseTask._route_to_dlq`
(celery_app.py:786) catches the ValidationError and logs `dlq_routing_failed` at
critical, so **the DLQ record is never written** — the failure is dropped from
the queue whose entire purpose is to retain it, and only a log line survives.
That is swallow-register territory, adjacent to instance 8.
"""
import pytest

from models.task_result import ErrorDetail, FailureCategory
from utils.error_handler import create_error_detail


class TestMissingIdsDoNotCrashTheErrorPath:
    def test_none_ids_are_tolerated(self):
        """THE BUG. Pre-fix this raised pydantic.ValidationError."""
        detail = create_error_detail(
            task_name="tasks.stage1_transcript.refine_transcript",
            task_id="abc-123",
            exception=RuntimeError("boom"),
            job_id=None,
            project_id=None,
        )
        assert isinstance(detail, ErrorDetail)
        assert detail.job_id == ""
        assert detail.project_id == ""

    def test_omitting_the_ids_entirely_is_tolerated(self):
        """Both parameters default to None, so a caller that never learned the
        ids hits the same path by simply not passing them."""
        detail = create_error_detail(
            task_name="tasks.stage1_transcript.refine_transcript",
            task_id="abc-123",
            exception=ValueError("no ids yet"),
        )
        assert detail.job_id == ""
        assert detail.project_id == ""

    def test_real_ids_still_pass_through_unchanged(self):
        """The coercion must not eat real values."""
        detail = create_error_detail(
            task_name="t", task_id="tid", exception=RuntimeError("x"),
            job_id="768c4b59-0000-0000-0000-000000000000",
            project_id="c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
        )
        assert detail.job_id == "768c4b59-0000-0000-0000-000000000000"
        assert detail.project_id == "c12fa967-f989-4ed4-8e20-3ea62cb92e8f"

    def test_the_error_being_reported_is_preserved(self):
        """Tolerating missing ids must not blur what actually failed - the whole
        point of the record is the exception it carries."""
        detail = create_error_detail(
            task_name="tasks.stage1_transcript.refine_transcript",
            task_id="abc-123",
            exception=RuntimeError("CheckpointWriteError: HTTP 401"),
            job_id=None, project_id=None,
        )
        assert detail.exception_type == "RuntimeError"
        assert "401" in detail.exception_message
        assert isinstance(detail.failure_category, FailureCategory)

    def test_the_record_serialises(self):
        """It is filed as JSON. A record that cannot serialise is not retained."""
        detail = create_error_detail(
            task_name="t", task_id="tid", exception=RuntimeError("x"),
            job_id=None, project_id=None,
        )
        blob = detail.model_dump(mode="json")
        assert blob["job_id"] == ""
        assert blob["project_id"] == ""

    @pytest.mark.parametrize("retries,maxr", [(None, None), (0, 0), (2, 3)])
    def test_none_retry_counters_are_tolerated(self, retries, maxr):
        """`self.request.retries` is None outside a task context, and it is
        passed straight through by _route_to_dlq."""
        detail = create_error_detail(
            task_name="t", task_id="tid", exception=RuntimeError("x"),
            retry_count=retries, max_retries=maxr,
        )
        assert isinstance(detail.retry_count, int)
        assert isinstance(detail.max_retries, int)


class TestTheDefectIsReal:
    def test_errordetail_itself_still_rejects_none(self):
        """Proof the coercion in create_error_detail is what fixes this, not a
        change in the model: ErrorDetail's contract is unchanged, and passing it
        None directly still raises exactly as it did in production."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc:
            ErrorDetail(task_name="t", task_id="tid", job_id=None, project_id=None)
        msg = str(exc.value)
        assert "job_id" in msg and "project_id" in msg
