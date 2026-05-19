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
from typing import Any

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

TRANSIENT_MESSAGE_PATTERNS: list[re.Pattern[str]] = [
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
    re.compile(r"quality\s+score\s+below", re.IGNORECASE),
    re.compile(r"safety\s+check\s+failed", re.IGNORECASE),
    re.compile(r"content\s+policy\s+violation", re.IGNORECASE),
    re.compile(r"generation\s+failed", re.IGNORECASE),
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
