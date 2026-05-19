"""
IVGS v5 — Error Handler
=========================

Centralized error handling for all pipeline worker tasks:
- Exception classification into failure categories (§6.4)
- Exponential backoff delay computation per stage type (Table 6-4)
- Dead Letter Queue routing via Pipeline API (§5.2.2)
- Structured error detail creation for DLQ payloads
- Retry decision logic (retry vs. DLQ vs. fallback)

Failure categories:
    transient   — network timeouts, temporary server errors (auto-retry)
    config      — invalid prompt, model not found (no retry)
    external    — vLLM server error, GPU OOM (retry with backoff)
    resource    — no GPU capacity, quota exceeded (retry with longer backoff)
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

from config import WorkerConfig
from models.task_result import ErrorDetail, FailureCategory

logger = structlog.get_logger("ivgs.error_handler")

# Module-level config
_config: Optional[WorkerConfig] = None


def _get_config() -> WorkerConfig:
    global _config
    if _config is None:
        _config = WorkerConfig()
    return _config


# ---------------------------------------------------------------------------
# Exception classification
# ---------------------------------------------------------------------------

# Maps exception types to failure categories
EXCEPTION_CATEGORY_MAP: Dict[str, FailureCategory] = {
    # Transient errors — safe to retry
    "ConnectionError": FailureCategory.TRANSIENT,
    "ConnectError": FailureCategory.TRANSIENT,
    "ReadTimeout": FailureCategory.TRANSIENT,
    "TimeoutError": FailureCategory.TRANSIENT,
    "VLLMTimeoutError": FailureCategory.TRANSIENT,
    "VLLMConnectionError": FailureCategory.TRANSIENT,
    "VLLMRateLimitError": FailureCategory.TRANSIENT,
    "ConnectionResetError": FailureCategory.TRANSIENT,
    "BrokenPipeError": FailureCategory.TRANSIENT,
    "OSError": FailureCategory.TRANSIENT,

    # Config errors — do not retry
    "ValueError": FailureCategory.CONFIG,
    "ValidationError": FailureCategory.CONFIG,
    "VLLMModelNotFoundError": FailureCategory.CONFIG,
    "VLLMInvalidResponseError": FailureCategory.CONFIG,
    "TemplateSyntaxError": FailureCategory.CONFIG,
    "UndefinedError": FailureCategory.CONFIG,
    "KeyError": FailureCategory.CONFIG,

    # External service errors — retry with backoff
    "VLLMServerError": FailureCategory.EXTERNAL,
    "VLLMError": FailureCategory.EXTERNAL,
    "HTTPStatusError": FailureCategory.EXTERNAL,

    # Resource errors — retry with longer backoff
    "GpuNoCapacityError": FailureCategory.RESOURCE,
    "GpuAdmissionError": FailureCategory.RESOURCE,
    "GpuCircuitBreakerError": FailureCategory.RESOURCE,
    "GpuReservationError": FailureCategory.RESOURCE,
    "MemoryError": FailureCategory.RESOURCE,
}


def classify_exception(exc: BaseException) -> FailureCategory:
    """
    Classify an exception into a failure category.

    Walks the MRO of the exception class to find the most specific match.
    """
    for cls in type(exc).__mro__:
        category = EXCEPTION_CATEGORY_MAP.get(cls.__name__)
        if category:
            return category
    return FailureCategory.TRANSIENT  # Default: assume transient


def should_retry(
    exc: BaseException,
    retry_count: int,
    max_retries: int,
) -> bool:
    """
    Determine whether a failed task should be retried.

    Config errors are never retried. All others retry up to max_retries.
    """
    category = classify_exception(exc)

    if category == FailureCategory.CONFIG:
        logger.info(
            "no_retry_config_error",
            exception_type=type(exc).__name__,
            category=category.value,
        )
        return False

    if retry_count >= max_retries:
        logger.info(
            "max_retries_exceeded",
            retry_count=retry_count,
            max_retries=max_retries,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# Backoff calculation
# ---------------------------------------------------------------------------

def compute_backoff_delay(
    retry_count: int,
    stage: str,
    config: Optional[WorkerConfig] = None,
) -> float:
    """
    Compute exponential backoff delay for a retry attempt.

    Uses the stage-specific backoff sequence from Table 6-4.
    Falls back to 2^n * base_delay if sequence is exhausted.

    Parameters
    ----------
    retry_count : int
        Current retry attempt (0-based).
    stage : str
        Pipeline stage name for looking up backoff sequence.

    Returns
    -------
    float
        Delay in seconds before next retry.
    """
    if config is None:
        config = _get_config()

    retry_config = config.get_retry_config_for_stage(stage)
    backoff_sequence: List[int] = retry_config.get(
        "backoff_sequence", [5, 15, 45, 135]
    )

    if retry_count < len(backoff_sequence):
        delay = backoff_sequence[retry_count]
    else:
        # Fallback: exponential from last value
        base = backoff_sequence[-1] if backoff_sequence else 5
        extra = retry_count - len(backoff_sequence) + 1
        delay = min(base * (2 ** extra), 600)  # Cap at 10 minutes

    # Add jitter (±10%)
    import random
    jitter = delay * 0.1
    delay = delay + random.uniform(-jitter, jitter)

    logger.info(
        "backoff_computed",
        stage=stage,
        retry_count=retry_count,
        delay_seconds=round(delay, 2),
    )

    return max(delay, 1.0)


# ---------------------------------------------------------------------------
# Error detail creation
# ---------------------------------------------------------------------------

def create_error_detail(
    task_name: str,
    task_id: str,
    exception: BaseException,
    retry_count: int = 0,
    max_retries: int = 0,
    job_id: Optional[str] = None,
    project_id: Optional[str] = None,
    stage: Optional[str] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
) -> ErrorDetail:
    """
    Create a structured ErrorDetail from an exception.
    """
    config = _get_config()

    return ErrorDetail(
        task_name=task_name,
        task_id=task_id,
        exception_type=type(exception).__name__,
        exception_message=str(exception),
        traceback=traceback.format_exc(),
        failure_category=classify_exception(exception),
        retry_count=retry_count,
        max_retries=max_retries,
        job_id=job_id,
        project_id=project_id,
        stage=stage,
        args=list(args) if args else None,
        kwargs=kwargs,
        occurred_at=datetime.now(timezone.utc),
        node_hostname=config.node_hostname,
        worker_id=config.worker_id,
    )


# ---------------------------------------------------------------------------
# DLQ routing
# ---------------------------------------------------------------------------

def route_to_dead_letter_queue(
    task_name: str,
    task_id: str,
    args: tuple,
    kwargs: dict,
    exception: BaseException,
    retry_count: int = 0,
) -> bool:
    """
    Route a failed task to the Dead Letter Queue via Pipeline API (§5.2.2).

    POST /api/v1/dlq/messages with the error detail payload.

    Returns True if successfully routed, False otherwise.
    """
    config = _get_config()

    # Extract job_id and project_id from kwargs
    job_id = kwargs.get("job_id") if kwargs else None
    project_id = kwargs.get("project_id") if kwargs else None
    stage = kwargs.get("stage") if kwargs else None

    # If not in kwargs, try first positional arg (often the input model)
    if not job_id and args:
        try:
            if hasattr(args[0], "get"):
                job_id = args[0].get("job_context", {}).get("job_id")
                project_id = args[0].get("job_context", {}).get("project_id")
        except (TypeError, AttributeError, IndexError):
            pass

    error_detail = create_error_detail(
        task_name=task_name,
        task_id=task_id,
        exception=exception,
        retry_count=retry_count,
        max_retries=config.get_retry_config_for_stage(
            stage or "unknown"
        ).get("max_retries", 3),
        job_id=job_id,
        project_id=project_id,
        stage=stage,
        args=args,
        kwargs=kwargs,
    )

    payload = error_detail.to_dlq_payload()
    # Add task args for replay capability
    payload["task_args"] = {
        "args": _safe_serialize(args),
        "kwargs": _safe_serialize(kwargs),
    }

    api_url = f"{config.pipeline_api.full_base_url}/dlq/messages"

    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            resp = client.post(api_url, json=payload)

            if resp.status_code in (200, 201):
                logger.info(
                    "dlq_routed",
                    task_name=task_name,
                    task_id=task_id,
                    job_id=job_id,
                    failure_category=error_detail.failure_category.value,
                )
                return True
            else:
                logger.error(
                    "dlq_routing_api_error",
                    task_name=task_name,
                    status_code=resp.status_code,
                    response=resp.text[:500],
                )
                return False

    except Exception as e:
        logger.critical(
            "dlq_routing_failed",
            task_name=task_name,
            task_id=task_id,
            error=str(e),
        )
        return False


def _safe_serialize(obj: Any) -> Any:
    """Safely serialize task args for DLQ storage."""
    import json
    try:
        json.dumps(obj, default=str)
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ---------------------------------------------------------------------------
# Job status update helper
# ---------------------------------------------------------------------------

def update_job_status(
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    failure_category: Optional[str] = None,
) -> bool:
    """
    Update render job status via Pipeline API.

    PATCH /api/v1/jobs/{job_id} with status and optional error details.
    """
    config = _get_config()
    api_url = f"{config.pipeline_api.full_base_url}/jobs/{job_id}"

    payload: Dict[str, Any] = {"status": status}
    if error_message:
        payload["error_message"] = error_message
    if failure_category:
        payload["failure_category"] = failure_category

    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            resp = client.patch(api_url, json=payload)
            if resp.status_code == 200:
                logger.info(
                    "job_status_updated",
                    job_id=job_id,
                    status=status,
                )
                return True
            logger.warning(
                "job_status_update_failed",
                job_id=job_id,
                status_code=resp.status_code,
            )
            return False
    except Exception as e:
        logger.error(
            "job_status_update_error", job_id=job_id, error=str(e)
        )
        return False


# ---------------------------------------------------------------------------
# Checkpoint save helper
# ---------------------------------------------------------------------------

def save_checkpoint(
    job_id: str,
    stage_name: str,
    stage_index: int,
    status: str,
    checkpoint_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Save a pipeline checkpoint via the Pipeline API (§5.2.4).

    POST /api/v1/jobs/{job_id}/checkpoints
    """
    config = _get_config()
    api_url = (
        f"{config.pipeline_api.full_base_url}/jobs/{job_id}/checkpoints"
    )

    payload = {
        "stage_name": stage_name,
        "stage_index": stage_index,
        "status": status,
        "checkpoint_data": checkpoint_data or {},
    }

    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            resp = client.post(api_url, json=payload)
            if resp.status_code in (200, 201):
                logger.info(
                    "checkpoint_saved",
                    job_id=job_id,
                    stage_name=stage_name,
                    status=status,
                )
                return True
            logger.warning(
                "checkpoint_save_failed",
                job_id=job_id,
                stage_name=stage_name,
                status_code=resp.status_code,
            )
            return False
    except Exception as e:
        logger.error(
            "checkpoint_save_error",
            job_id=job_id,
            stage_name=stage_name,
            error=str(e),
        )
        return False
