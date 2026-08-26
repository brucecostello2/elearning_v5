"""
IVGS v5 — Error Classifier
========================================

Classify errors into four categories per §6.2:
- transient: Temporary failures (timeouts, connection resets, 503s)
- config:    Configuration errors (invalid API keys, bad model names)
- external:  External service failures (model quality, API changes)
- resource:  Resource exhaustion (OOM, disk full, VRAM exhausted)

Classification drives:
- Retry eligibility (config errors → no retry, immediate DLQ)
- DLQ categorization (failure_category column in Table 15)
- Dashboard filtering and prioritization
- Monitoring alert routing

Error pattern matching uses exception type + message analysis.
"""

from __future__ import annotations

import re
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class ErrorCategory(str, Enum):
    """Error classification categories per §6.2."""

    TRANSIENT = "transient"
    CONFIG = "config"
    EXTERNAL = "external"
    RESOURCE = "resource"


# ---------------------------------------------------------------------------
# Pattern Definitions
# ---------------------------------------------------------------------------

# Transient error patterns — retryable
TRANSIENT_EXCEPTION_TYPES: frozenset[str] = frozenset({
    "TimeoutError",
    "asyncio.TimeoutError",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectionRefusedError",
    "BrokenPipeError",
    "OSError",
    "httpx.ConnectTimeout",
    "httpx.ReadTimeout",
    "httpx.WriteTimeout",
    "httpx.PoolTimeout",
    "httpx.ConnectError",
    "httpx.RemoteProtocolError",
    "celery.exceptions.WorkerLostError",
    "celery.exceptions.TimeLimitExceeded",
    "celery.exceptions.SoftTimeLimitExceeded",
    "redis.exceptions.ConnectionError",
    "redis.exceptions.TimeoutError",
    "sqlalchemy.exc.OperationalError",
    "sqlalchemy.exc.DisconnectionError",
    "urllib3.exceptions.ReadTimeoutError",
    "urllib3.exceptions.ConnectTimeoutError",
    "requests.exceptions.ConnectionError",
    "requests.exceptions.Timeout",
})

# WP-57 Task 7 additions are marked. Each was written against a message that is
# ACTUALLY IN `render_jobs.error_message` on this system (WP-58 report S6), not
# against an imagined one - which is why the previous set matched almost nothing:
# it was written for exception strings, and what reaches this classifier is the
# orchestrator's own summary text.
TRANSIENT_MESSAGE_PATTERNS: list[re.Pattern[str]] = [
    # WP-57 Task 7 — real message: "tts_audio checkpoint write returned 429
    # (pipeline rate-limited itself; fixed in v5.11.0-apibatch)".
    re.compile(r"\b429\b", re.IGNORECASE),
    re.compile(r"rate[\s_-]?limit", re.IGNORECASE),
    # WP-57 Task 7 — real message: "media-generation join stranded (worker
    # crash); no dispatch context available to advance". A lost worker is the
    # definition of transient: the work is re-runnable, nothing is misconfigured.
    re.compile(r"worker\s+crash", re.IGNORECASE),
    re.compile(r"\bstranded\b", re.IGNORECASE),
    re.compile(r"worker\s+lost", re.IGNORECASE),
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"connection\s+(refused|reset|aborted)", re.IGNORECASE),
    re.compile(r"temporarily\s+unavailable", re.IGNORECASE),
    re.compile(r"503\s+service\s+unavailable", re.IGNORECASE),
    re.compile(r"502\s+bad\s+gateway", re.IGNORECASE),
    re.compile(r"504\s+gateway\s+timeout", re.IGNORECASE),
    re.compile(r"429\s+too\s+many\s+requests", re.IGNORECASE),
    re.compile(r"rate\s+limit", re.IGNORECASE),
    re.compile(r"broken\s+pipe", re.IGNORECASE),
    re.compile(r"connection\s+pool\s+exhausted", re.IGNORECASE),
    re.compile(r"retry\s+after", re.IGNORECASE),
    re.compile(r"server\s+busy", re.IGNORECASE),
    re.compile(r"ECONNRESET", re.IGNORECASE),
    re.compile(r"ETIMEDOUT", re.IGNORECASE),
]

# Config error patterns — not retryable
CONFIG_EXCEPTION_TYPES: frozenset[str] = frozenset({
    "ValueError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "pydantic.ValidationError",
    "pydantic_core._pydantic_core.ValidationError",
    "jsonschema.exceptions.ValidationError",
    "yaml.YAMLError",
    "yaml.scanner.ScannerError",
})

CONFIG_MESSAGE_PATTERNS: list[re.Pattern[str]] = [
    # WP-57 Task 7 — real message: "Stage3Input validation - dispatch_pipeline
    # had no media branch; fixed in this build". A schema/dispatch defect is a
    # config fault: retrying it changes nothing, which is exactly the distinction
    # `transient` vs `config` is for.
    re.compile(r"\bvalidation\b", re.IGNORECASE),
    re.compile(r"no\s+media\s+branch", re.IGNORECASE),
    # WP-57 Task 7 — real message, NINE rows: "Cancelled by WP-45 sweep: this row
    # was created by the pre-WP-45 scene-regenerate endpoint, which inserted a job
    # and dispatched no Celery task". These are administrative cancellations of
    # rows that were never renders. Classifying them `transient` invites a retry
    # of something that never ran; `config` says the fault is in how the job was
    # created, which is true.
    re.compile(r"cancelled\s+by", re.IGNORECASE),
    re.compile(r"dispatched\s+no\s+celery\s+task", re.IGNORECASE),
    re.compile(r"invalid\s+(api[_ ]?key|token|credential)", re.IGNORECASE),
    re.compile(r"model\s+not\s+found", re.IGNORECASE),
    re.compile(r"invalid\s+model\s+name", re.IGNORECASE),
    re.compile(r"missing\s+required\s+(field|parameter|config)", re.IGNORECASE),
    re.compile(r"validation\s+error", re.IGNORECASE),
    re.compile(r"schema\s+(mismatch|violation|error)", re.IGNORECASE),
    re.compile(r"unsupported\s+(format|type|version)", re.IGNORECASE),
    re.compile(r"permission\s+denied", re.IGNORECASE),
    re.compile(r"401\s+unauthorized", re.IGNORECASE),
    re.compile(r"403\s+forbidden", re.IGNORECASE),
    re.compile(r"invalid\s+configuration", re.IGNORECASE),
]

# Resource error patterns — retryable with caution
RESOURCE_EXCEPTION_TYPES: frozenset[str] = frozenset({
    "MemoryError",
    "torch.cuda.OutOfMemoryError",
    "RuntimeError",  # Often CUDA OOM
})

RESOURCE_MESSAGE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"out\s+of\s+memory", re.IGNORECASE),
    re.compile(r"CUDA\s+out\s+of\s+memory", re.IGNORECASE),
    re.compile(r"OOM", re.IGNORECASE),
    re.compile(r"VRAM\s+(exhausted|insufficient|full)", re.IGNORECASE),
    re.compile(r"disk\s+(full|space)", re.IGNORECASE),
    re.compile(r"no\s+space\s+left", re.IGNORECASE),
    re.compile(r"quota\s+exceeded", re.IGNORECASE),
    re.compile(r"resource\s+exhausted", re.IGNORECASE),
    re.compile(r"too\s+many\s+open\s+files", re.IGNORECASE),
    re.compile(r"cannot\s+allocate\s+memory", re.IGNORECASE),
    re.compile(r"ENOMEM", re.IGNORECASE),
    re.compile(r"ENOSPC", re.IGNORECASE),
]

# External error patterns — model/service quality issues
EXTERNAL_MESSAGE_PATTERNS: list[re.Pattern[str]] = [
    # WP-63 Task 3 — the validator's own rejection text, verbatim, and the
    # attributed job-row message that carries it up.
    #
    # "Image appears blank or solid color" produced 6 of the 20 rejections in
    # the 2026-08-26 reference-run rescore and killed 3 of 9 scenes in the
    # incident this package closes. Nothing matched it before, so it landed on
    # the `transient` default at the bottom of this file — and `transient`
    # means "retry it". A VALIDATOR REJECTION IS NOT TRANSIENT. Nothing about
    # the fleet was wrong; a frame was produced, measured and refused, and a
    # retry re-measures it to the same verdict. §6.2's `external` is the class
    # for model/service OUTPUT quality, which is exactly what this is.
    #
    # `colou?r` because the message is spelled "color" and a British spelling
    # of the same finding must not slip past.
    re.compile(r"appears\s+blank\s+or\s+solid\s+colou?r", re.IGNORECASE),
    re.compile(r"rejected\s+by\s+the\s+(image|video)\s+validator", re.IGNORECASE),
    # The clause `error_handler._attribute_failure` writes when a media stage
    # failed PARTIALLY. KEYED ON THE EVIDENCE, NOT ON THE FAILURE: "N of M
    # scenes produced no usable asset" is not by itself external — if M of M
    # failed, the generator being unreachable fits it just as well. What makes
    # it external is that the OTHERS SUCCEEDED, in one pass on one node against
    # one model, which leaves only the content to differ. So the pattern is the
    # sentence that states that, and a total failure — which does not contain
    # it — falls through to WP-57's honest default.
    re.compile(r"succeeded\s+in\s+the\s+same\s+pass", re.IGNORECASE),
    re.compile(r"quality\s+score\s+below", re.IGNORECASE),
    re.compile(r"safety\s+check\s+failed", re.IGNORECASE),
    re.compile(r"content\s+policy\s+violation", re.IGNORECASE),
    # WP-57 Task 7. Was r"generation\s+failed", which also matched
    # "Stage storyboard_generation failed" and "Stage image_generation failed" -
    # the orchestrator's CONTENT-FREE summary for any stage whose name ends in
    # "_generation". All three storyboard failures in the live table were
    # classified `external`, i.e. "the model produced bad output", on no evidence
    # at all. A confident wrong class is worse than the honest default, because
    # it sends the reader to the model instead of to the stage.
    # The lookbehind excludes a preceding underscore or word character, so
    # "All animation generations failed" still matches and
    # "storyboard_generation failed" no longer does.
    re.compile(r"(?<![_\w])generations?\s+failed", re.IGNORECASE),
    re.compile(r"inference\s+error", re.IGNORECASE),
    re.compile(r"model\s+output\s+invalid", re.IGNORECASE),
    re.compile(r"corrupt(ed)?\s+output", re.IGNORECASE),
    re.compile(r"empty\s+response", re.IGNORECASE),
    re.compile(r"malformed\s+output", re.IGNORECASE),
    re.compile(r"NSFW\s+detected", re.IGNORECASE),
    re.compile(r"lip[_-]?sync\s+score", re.IGNORECASE),
    re.compile(r"alignment\s+score\s+below", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Error Classifier
# ---------------------------------------------------------------------------

class ErrorClassifier:
    """
    Classify pipeline errors per §6.2.

    Four-category classification:
    - transient: Temporary failures amenable to retry
    - config:    Configuration errors requiring code/config fix
    - external:  External service / model quality issues
    - resource:  System resource exhaustion

    Classification priority (first match wins):
    1. Resource patterns (OOM, disk full) → resource
    2. Config patterns (validation, auth) → config
    3. Transient patterns (timeout, connection) → transient
    4. External patterns (quality, safety) → external
    5. Default: transient (assume retryable)

    Usage:
        classifier = ErrorClassifier()
        category = classifier.classify(exception)
        # or
        category = classifier.classify_from_strings("TimeoutError", "...")
    """

    def __init__(self) -> None:
        """Initialize error classifier with default patterns."""
        self._log = logger.bind(service="error_classifier")

    def classify(self, exception: BaseException) -> ErrorCategory:
        """
        Classify an exception into an error category.

        Examines both the exception type hierarchy and the error message
        to determine the most appropriate category.

        Args:
            exception: The exception to classify.

        Returns:
            ErrorCategory: Classification result.
        """
        exc_type = type(exception).__name__
        exc_message = str(exception)

        # Also check parent class names for inheritance chains
        exc_types = {
            cls.__name__ for cls in type(exception).__mro__
            if cls is not object
        }

        return self._classify_internal(
            exception_types=exc_types,
            exception_type_name=exc_type,
            message=exc_message,
        )

    def classify_from_strings(
        self,
        exception_type: str,
        exception_message: str,
    ) -> ErrorCategory:
        """
        Classify an error from string representations.

        Used when the original exception object is not available
        (e.g., DLQ entries stored as strings).

        Args:
            exception_type: Exception class name string.
            exception_message: Error message string.

        Returns:
            ErrorCategory: Classification result.
        """
        return self._classify_internal(
            exception_types={exception_type},
            exception_type_name=exception_type,
            message=exception_message,
        )

    def _classify_internal(
        self,
        *,
        exception_types: set[str],
        exception_type_name: str,
        message: str,
    ) -> ErrorCategory:
        """
        Internal classification logic with priority ordering.

        Priority: resource > config > transient > external > default(transient)

        Args:
            exception_types: Set of exception type names (including parents).
            exception_type_name: Primary exception type name.
            message: Error message text.

        Returns:
            ErrorCategory: Classification result.
        """
        # 1. Check resource patterns first (highest priority)
        if exception_types & RESOURCE_EXCEPTION_TYPES:
            # RuntimeError needs message check to avoid false positives
            if exception_type_name == "RuntimeError":
                if self._matches_patterns(message, RESOURCE_MESSAGE_PATTERNS):
                    self._log.debug(
                        "classified_resource_by_type_and_message",
                        exception_type=exception_type_name,
                    )
                    return ErrorCategory.RESOURCE
            else:
                self._log.debug(
                    "classified_resource_by_type",
                    exception_type=exception_type_name,
                )
                return ErrorCategory.RESOURCE

        if self._matches_patterns(message, RESOURCE_MESSAGE_PATTERNS):
            self._log.debug(
                "classified_resource_by_message",
                exception_type=exception_type_name,
                message_snippet=message[:100],
            )
            return ErrorCategory.RESOURCE

        # 2. Check config patterns
        if exception_types & CONFIG_EXCEPTION_TYPES:
            self._log.debug(
                "classified_config_by_type",
                exception_type=exception_type_name,
            )
            return ErrorCategory.CONFIG

        if self._matches_patterns(message, CONFIG_MESSAGE_PATTERNS):
            self._log.debug(
                "classified_config_by_message",
                exception_type=exception_type_name,
                message_snippet=message[:100],
            )
            return ErrorCategory.CONFIG

        # 3. Check transient patterns
        if exception_types & TRANSIENT_EXCEPTION_TYPES:
            self._log.debug(
                "classified_transient_by_type",
                exception_type=exception_type_name,
            )
            return ErrorCategory.TRANSIENT

        if self._matches_patterns(message, TRANSIENT_MESSAGE_PATTERNS):
            self._log.debug(
                "classified_transient_by_message",
                exception_type=exception_type_name,
                message_snippet=message[:100],
            )
            return ErrorCategory.TRANSIENT

        # 4. Check external patterns
        if self._matches_patterns(message, EXTERNAL_MESSAGE_PATTERNS):
            self._log.debug(
                "classified_external_by_message",
                exception_type=exception_type_name,
                message_snippet=message[:100],
            )
            return ErrorCategory.EXTERNAL

        # 5. Default to transient (assume retryable)
        self._log.info(
            "classified_default_transient",
            exception_type=exception_type_name,
            message_snippet=message[:100],
        )
        return ErrorCategory.TRANSIENT

    @staticmethod
    def _matches_patterns(
        text: str,
        patterns: list[re.Pattern[str]],
    ) -> bool:
        """
        Check if text matches any pattern in the list.

        Args:
            text: String to test against patterns.
            patterns: List of compiled regex patterns.

        Returns:
            True if any pattern matches.
        """
        return any(pattern.search(text) for pattern in patterns)
