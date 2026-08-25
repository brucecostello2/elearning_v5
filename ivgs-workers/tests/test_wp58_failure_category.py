"""
WP-58 Task 6 — `render_jobs.failure_category`, declared and written by nothing.

WP-56 §6.4 found the column NULL on all 19 failed jobs. Every link in the chain
was already present except a caller:

  * the PostgreSQL ENUM `failure_category` exists (migration 0006);
  * `render_jobs.failure_category` exists;
  * `JobStatusUpdate.failure_category` is declared and written
    (ivgs-api/app/api/v1/jobs.py:179, :207);
  * `update_job_status(..., failure_category=...)` has always accepted it;
  * `ErrorClassifier` produces exactly the four ENUM values.

Thirty-one call sites, none passing a category.

WHY THE DERIVATION IS AT THE CHOKE POINT. Most terminal-failure calls are inside
the eight stage task bodies, which AD-05 §8 and CLAUDE.md §3 freeze. Classifying
in `update_job_status` fills the column for every caller and edits none of them.
"""
from unittest.mock import MagicMock, patch

import pytest

from utils.error_handler import _TERMINAL_FAILURE_STATUSES, update_job_status


def _captured_payload(mock_client) -> dict:
    """The JSON body actually PATCHed to the API."""
    return mock_client.return_value.__enter__.return_value.patch.call_args.kwargs["json"]


@pytest.fixture
def http(monkeypatch):
    """Intercept the PATCH and report success, so the tests assert on the body."""
    mock = MagicMock()
    response = MagicMock()
    response.status_code = 200
    mock.return_value.__enter__.return_value.patch.return_value = response
    monkeypatch.setattr("utils.error_handler.httpx.Client", mock)
    return mock


class TestCategoryIsDerived:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Stage 3 error: Connection timed out talking to ComfyUI", "transient"),
            ("CUDA out of memory: tried to allocate 2.00 GiB", "resource"),
            ("invalid configuration value for model", "config"),
        ],
    )
    def test_a_terminal_failure_carries_a_category(self, http, message, expected):
        assert update_job_status("job-1", "failed", error_message=message) is True
        payload = _captured_payload(http)
        assert payload["failure_category"] == expected, (
            f"{message!r} classified as {payload.get('failure_category')!r}"
        )

    def test_every_terminal_failure_gets_some_category(self, http):
        """Whatever the message, the column must not come back NULL — that is
        the defect. The classifier's own default is `transient`."""
        update_job_status("job-1", "failed", error_message="something went wrong")
        payload = _captured_payload(http)
        assert payload.get("failure_category")
        assert payload["failure_category"] in {
            "transient", "config", "external", "resource",
        }

    def test_an_explicit_category_wins(self, http):
        """A caller that knows the real cause beats a regex over its own string."""
        update_job_status(
            "job-1", "failed",
            error_message="CUDA out of memory",
            failure_category="external",
        )
        assert _captured_payload(http)["failure_category"] == "external"


class TestItStaysOutOfTheWay:
    def test_a_successful_job_gets_no_category(self, http):
        update_job_status("job-1", "success")
        assert "failure_category" not in _captured_payload(http)

    def test_a_running_job_with_a_message_gets_no_category(self, http):
        """`update_job_status` is called on every stage transition. Only a
        TERMINAL failure may be classified."""
        update_job_status("job-1", "running", error_message="retrying after timeout")
        assert "failure_category" not in _captured_payload(http)

    def test_a_failure_with_no_message_is_left_unclassified(self, http):
        """There is nothing to classify from. A guessed category would be worse
        than an absent one."""
        update_job_status("job-1", "failed")
        assert "failure_category" not in _captured_payload(http)

    def test_the_terminal_set_is_explicit(self):
        assert "failed" in _TERMINAL_FAILURE_STATUSES
        assert "success" not in _TERMINAL_FAILURE_STATUSES
        assert "running" not in _TERMINAL_FAILURE_STATUSES


class TestClassificationNeverCostsTheStatusWrite:
    def test_a_classifier_explosion_still_writes_the_status(self, http):
        """The job status is what matters; a missing category is a worse report,
        not a worse outcome."""
        with patch(
            "services.error_classifier.ErrorClassifier.classify_from_strings",
            side_effect=RuntimeError("classifier is broken"),
        ):
            assert update_job_status(
                "job-1", "failed", error_message="Stage 7 error: boom",
            ) is True
        payload = _captured_payload(http)
        assert payload["status"] == "failed"
        assert payload["error_message"] == "Stage 7 error: boom"
        assert "failure_category" not in payload


class TestTheEnumsAgree:
    def test_classifier_values_are_exactly_the_database_enum(self):
        """Four values, two definitions, no mapping table to drift."""
        from services.error_classifier import ErrorCategory

        assert {c.value for c in ErrorCategory} == {
            "transient", "config", "external", "resource",
        }


class TestTheLimitationIsVisible:
    """MEASURED, and recorded here so nobody reads a filled column as a
    diagnosed one.

    Classifying from `error_message` alone is weak for the messages the
    ORCHESTRATOR writes, because by the time it writes "Stage 7 error: ..." the
    exception TYPE - the thing `ErrorClassifier` is actually built around - has
    been discarded. Run against the 19 real failure messages in the live
    database on 2026-08-25, 17 came back `transient` and 15 of those reached it
    through the classifier's DEFAULT branch rather than any pattern.

    The column is still worth filling: a specific message classifies correctly
    (see above), and a default is recoverable where a NULL is not. But the
    durable fix is to pass the category from the site that still holds the
    exception - `IVGSBaseTask.on_failure` and the stage bodies - which is
    WP-58 D-4.
    """

    def test_an_orchestrator_summary_message_falls_through_to_the_default(self, http):
        """Pinning the weakness rather than hiding it. If a future classifier
        improvement makes this specific, this test should be UPDATED, not
        deleted - the change is the point."""
        update_job_status(
            "job-1", "failed", error_message="Stage prototype_draft failed",
        )
        assert _captured_payload(http)["failure_category"] == "transient"

    def test_a_specific_message_still_classifies_specifically(self, http):
        """The half that works, and the reason filling the column beats NULL."""
        update_job_status(
            "job-1", "failed",
            error_message="CUDA out of memory: tried to allocate 2.00 GiB",
        )
        assert _captured_payload(http)["failure_category"] == "resource"
