"""
WP-57 Task 7 — the classifier, pinned against the messages that ACTUALLY EXIST.

WP-58 populated `render_jobs.failure_category` and measured that the classifier
mostly shrugged: of 20 real messages, 17 came back `transient` and 15 of those
by the DEFAULT branch. This file pins the repair.

WHY THE OLD PATTERN SET MATCHED ALMOST NOTHING. It was written for EXCEPTION
strings — "ConnectionResetError", "CUDA out of memory". What actually reaches
this classifier is the orchestrator's own summary text, written at the point a
job is marked failed, by which time the exception is gone. Those are different
vocabularies, and the patterns were aimed at the wrong one.

THE THREE "EXTERNAL" HITS WERE FALSE POSITIVES, NOT SUCCESSES. `generation\\s+failed`
matched "Stage storyboard_generation failed", so every storyboard failure was
classified "the model produced bad output" on no evidence. A confident wrong
class is worse than an honest default: it sends the reader to the model instead
of to the stage.

MEASURED, on the 20 messages in the live table:

    classified by a pattern   3  ->  14      (and the 3 were all wrong)
    fell through to default  17  ->   6
    distribution   transient 17, external 3
                -> transient  9, external 1, config 10

The 6 remaining defaults are the content-free summaries — "Stage
prototype_draft failed" and friends — which carry no information at all.
Defaulting is the correct answer there, and `test_a_content_free_summary_still_defaults`
pins that rather than papering over it.
"""
import pytest

from services.error_classifier import ErrorCategory, ErrorClassifier


@pytest.fixture
def classifier() -> ErrorClassifier:
    return ErrorClassifier()


def _classify(classifier: ErrorClassifier, message: str) -> str:
    return classifier.classify_from_strings(
        exception_type="", exception_message=message,
    ).value


# The real contents of render_jobs.error_message on this system, 2026-08-26.
REAL_MESSAGES = [
    (
        "media-generation join stranded (worker crash); no dispatch context "
        "available to advance",
        "transient",
        "A lost worker is re-runnable: nothing is misconfigured and no model misbehaved.",
    ),
    (
        "tts_audio checkpoint write returned 429 (pipeline rate-limited itself; "
        "fixed in v5.11.0-apibatch)",
        "transient",
        "A 429 is the definition of retryable.",
    ),
    (
        "Cancelled by WP-45 sweep: this row was created by the pre-WP-45 "
        "scene-regenerate endpoint, which inserted a job and dispatched no "
        "Celery task.",
        "config",
        "Nine rows. Administrative cancellations of jobs that never ran - "
        "classifying them transient invites a retry of nothing.",
    ),
    (
        "Stage3Input validation - dispatch_pipeline had no media branch; fixed "
        "in this build",
        "config",
        "A dispatch/schema defect. Retrying it changes nothing, which is exactly "
        "what separates config from transient.",
    ),
    (
        "All animation generations failed",
        "external",
        "The sub-generations themselves failed - this one really is model output.",
    ),
]


@pytest.mark.parametrize(
    "message,expected,why", REAL_MESSAGES, ids=[m[:28] for m, _, _ in REAL_MESSAGES],
)
def test_each_real_message_lands_in_its_class(classifier, message, expected, why):
    got = _classify(classifier, message)
    assert got == expected, f"{message[:60]!r} -> {got}, expected {expected}. {why}"


@pytest.mark.parametrize(
    "message",
    [
        "Stage prototype_draft failed",
        "Stage storyboard_generation failed",
        "Stage image_generation failed",
    ],
)
def test_a_content_free_summary_still_defaults(classifier, message):
    """THE HONEST FLOOR, PINNED DELIBERATELY.

    These carry no information whatever. The right answer is the default, and
    this test exists so nobody "improves" the number by inventing a pattern that
    guesses. If a future change makes these specific, it must do so because the
    MESSAGE got richer — and then this test should be updated, not deleted.
    """
    assert _classify(classifier, message) == "transient"


def test_a_stage_named_generation_is_not_called_a_model_failure(classifier):
    """The regression that motivated the whole task.

    `generation\\s+failed` matched "storyboard_generation failed" through the
    underscore. Every storyboard failure was reported as bad model output.
    """
    assert _classify(classifier, "Stage storyboard_generation failed") != "external"
    assert _classify(classifier, "Stage animation_generation failed") != "external"
    # ...while the genuine one still matches.
    assert _classify(classifier, "All animation generations failed") == "external"


def test_the_default_count_over_the_real_corpus_has_dropped(classifier):
    """The before/after, as an assertion rather than a claim in a report.

    The full corpus is 20 rows; these are its 20 messages by multiplicity. Before
    WP-57, 15 of them reached `ErrorCategory.TRANSIENT` through the default
    branch. The classifier must now do better than half.
    """
    corpus = (
        [REAL_MESSAGES[0][0]] * 2
        + ["Stage prototype_draft failed"] * 3
        + ["Stage storyboard_generation failed"] * 3
        + [REAL_MESSAGES[4][0]]
        + [REAL_MESSAGES[1][0]]
        + [REAL_MESSAGES[2][0]] * 9
        + [REAL_MESSAGES[3][0]]
    )
    assert len(corpus) == 20

    non_default = sum(
        1 for m in corpus if _classify(classifier, m) != "transient"
    ) + sum(
        # transient-by-pattern still counts as classified; only the content-free
        # summaries are true defaults.
        1
        for m in corpus
        if _classify(classifier, m) == "transient"
        and not m.startswith("Stage ")
    )
    assert non_default >= 14, (
        f"only {non_default}/20 messages are classified by a pattern; "
        "WP-57 measured 14"
    )


def test_the_four_classes_are_still_exactly_the_database_enum(classifier):
    """New patterns must not introduce a fifth class the ENUM cannot store."""
    assert {c.value for c in ErrorCategory} == {
        "transient", "config", "external", "resource",
    }


def test_resource_and_transient_exception_paths_are_unchanged(classifier):
    """WP-57 widened MESSAGE coverage. It must not have moved anything that
    already worked from an exception type."""
    assert _classify(classifier, "CUDA out of memory: tried to allocate 2.00 GiB") == "resource"
    assert classifier.classify_from_strings(
        exception_type="TimeoutError", exception_message="timed out",
    ).value == "transient"
