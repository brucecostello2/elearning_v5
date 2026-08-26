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

import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

    # WP-36. This signature accepts `job_id: Optional[str] = None` and
    # `project_id: Optional[str] = None`, but ErrorDetail declares both as
    # non-optional `str = ""` (models/task_result.py:314-315). Passing None
    # therefore raised a pydantic ValidationError *inside the failure handler* -
    # observed 2026-08-23 as `dlq_routing_failed` with
    # "job_id: Input should be a valid string [input_value=None]".
    #
    # The consequence is worse than a noisy log. IVGSBaseTask._route_to_dlq
    # (celery_app.py:786) catches it and logs critical, so the DLQ record is
    # never written: the failure is dropped from the queue whose entire purpose
    # is to retain it, and only a log line survives. A failure handler must not
    # be the thing that fails.
    #
    # Coerced here rather than by widening the model, because "" is what
    # ErrorDetail already declares as its absent value and the DLQ schema and
    # table are built on that contract. This is exactly the case that hits it:
    # a task failing early enough that it never learned its own ids.
    return ErrorDetail(
        task_name=task_name or "",
        task_id=task_id or "",
        exception_type=type(exception).__name__,
        exception_message=str(exception),
        traceback=traceback.format_exc(),
        failure_category=classify_exception(exception),
        retry_count=retry_count or 0,
        max_retries=max_retries or 0,
        job_id=job_id or "",
        project_id=project_id or "",
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

# WP-58 Task 6. The statuses that mean "this job is over and it did not work".
# Kept as a named set rather than an inline == "failed" so a future terminal
# status cannot be added without this line being considered.
_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "cancelled"})

# WP-63 Task 3. The media-generation stages, whose checkpoint carries per-scene
# counts. A PARTIAL failure of one of these is the only case in which this
# module infers a failure CLASS from the ledger; see `_attribute_failure`.
_MEDIA_LEDGER_STAGES = frozenset(
    {"image_generation", "video_generation", "animation_generation",
     "media_generation"}
)


def _stage_named_in(message: str) -> Optional[str]:
    """The stage a "Stage <x> failed" summary names, if it is that shape."""
    import re

    match = re.match(r"\s*Stage\s+([A-Za-z0-9_]+)\s+failed", message or "")
    return match.group(1) if match else None


def _ledger_failure(job_id: str, config: Any) -> Optional[Dict[str, Any]]:
    """The FIRST stage this job's own checkpoints record as failed.

    Reads `GET /jobs/{id}/checkpoints`, and then that stage's detail for its
    `checkpoint_data`. Returns None on any difficulty at all: an attribution
    that cannot be made is not a reason to lose the status write.

    "First" is by `stage_index`, then by `created_at`. A run that partial-
    advances past a failed media stage and then dies downstream has two failed
    checkpoints; the earlier one is the cause and the later one is the
    consequence.
    """
    base = config.pipeline_api.full_base_url
    headers = {
        "Authorization": f"Bearer {config.pipeline_api.service_token}",
    }
    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds, headers=headers,
        ) as client:
            resp = client.get(f"{base}/jobs/{job_id}/checkpoints")
            if resp.status_code != 200:
                logger.info(
                    "failure_attribution_ledger_unavailable",
                    job_id=job_id, status_code=resp.status_code,
                )
                return None
            rows = resp.json().get("checkpoints") or []
            failed = [r for r in rows if (r.get("status") or "") == "failed"]
            if not failed:
                return None
            failed.sort(
                key=lambda r: (
                    r.get("stage_index") if r.get("stage_index") is not None else 99,
                    r.get("created_at") or "",
                )
            )
            first = failed[0]
            stage_name = first.get("stage_name") or ""
            data: Dict[str, Any] = {}
            detail = client.get(f"{base}/jobs/{job_id}/checkpoints/{stage_name}")
            if detail.status_code == 200:
                data = detail.json().get("checkpoint_data") or {}
            return {"stage_name": stage_name, "checkpoint_data": data}
    except Exception as exc:  # pragma: no cover - defensive
        logger.info(
            "failure_attribution_ledger_error", job_id=job_id, error=str(exc),
        )
        return None


def _attribute_failure(
    job_id: str, error_message: str, config: Any,
) -> tuple[str, Optional[str], Optional[str]]:
    """Name the stage the CHECKPOINT recorded, not the one that reported last.

    Returns ``(error_message, stage, failure_category_hint)``. Any of the three
    may come back unchanged / None; this function never raises.

    THE INCIDENT (operator-measured, 2026-08-26, project 14f71729, job
    d4b41765). Three surfaces told three different stories about one failure:

        render_jobs row      "Stage talking_head_render failed",
                             failure_category = transient
        checkpoint ledger    image_generation FAILED
                             (failed_count 3, successful_count 6);
                             tts_audio complete
        stepper              Media

    **The checkpoints were right.** Stage 3 rejected 3 of 9 scenes, the media
    join drained and partial-advanced by design (a failed scene must not strand
    the pipeline), stages 4 and 5 ran, and the run finally died at stage 6 with
    3 of 9 scenes carrying no image. `handle_stage_completion` writes
    ``f"Stage {completed_stage} failed"``
    (`tasks/pipeline_orchestrator_v2.py:409`) for whichever stage reported the
    terminal failure — and under partial-advance that is never the stage that
    actually failed. The job row named the symptom.

    So the attribution is taken from the ledger. The stage writes its own
    checkpoint; the orchestrator's summary is a report from downstream.

    THE ONE CLASS INFERENCE, and its limit. When the ledger's failed stage is a
    MEDIA stage and the failure was PARTIAL — some scenes succeeded and some
    did not, in the same pass, on the same node, against the same model — the
    difference between them is the CONTENT, not the infrastructure. That is
    `external` (§6.2: model/service quality), and it is emphatically not
    `transient`: a rejected frame recurs on retry, because nothing about the
    conditions that produced it has changed. When EVERY media task failed, no
    such inference is available — that shape is equally consistent with the
    generator being unreachable — and this function offers no category, leaving
    WP-57's classifier and its honest default in charge. WP-57's rule stands:
    a confident wrong class is worse than the honest default.
    """
    reported_stage = _stage_named_in(error_message)
    ledger = _ledger_failure(job_id, config)
    if ledger is None:
        return error_message, None, None

    ledger_stage = ledger["stage_name"]
    if not ledger_stage or ledger_stage == reported_stage:
        return error_message, ledger_stage or None, None

    data = ledger["checkpoint_data"] or {}
    failed_count = data.get("failed_count")
    successful_count = data.get("successful_count")

    parts = [f"Stage {ledger_stage} failed (the stage's own checkpoint)."]
    category: Optional[str] = None

    if (
        ledger_stage in _MEDIA_LEDGER_STAGES
        and isinstance(failed_count, int)
        and isinstance(successful_count, int)
        and failed_count > 0
    ):
        total = failed_count + successful_count
        parts.append(
            f"{failed_count} of {total} scenes produced no usable asset."
        )
        if successful_count > 0:
            parts.append(
                f"The other {successful_count} succeeded in the same pass, so "
                "the difference is the generated content, not the fleet."
            )
            category = "external"

    if reported_stage and reported_stage != ledger_stage:
        parts.append(
            f"The terminal failure was reported at stage {reported_stage}, "
            "which ran after it under partial-advance; the checkpoint ledger "
            "is authoritative for which stage failed."
        )

    return " ".join(parts), ledger_stage, category



def update_job_status(
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    failure_category: Optional[str] = None,
    stage: Optional[str] = None,
) -> bool:
    """
    Update render job status via Pipeline API.

    PATCH /api/v1/jobs/{job_id} with status and optional error details.

    WP-58 Task 6: when ``status`` is a terminal failure and the caller supplied
    no ``failure_category``, one is derived from ``error_message`` by
    ``ErrorClassifier``. See the inline note below for why the derivation lives
    here rather than at the 31 call sites.

    WP-63 Task 3: a terminal failure is also ATTRIBUTED before it is written.
    The job row names the stage this job's own checkpoint ledger records as
    failed, not the stage that happened to report last — under partial-advance
    those are routinely different, and the measured incident had them three
    stages apart. ``_attribute_failure`` carries the evidence.

    HISTORICAL ROWS STAY NULL. No backfill is performed and none is in scope:
    the 19 existing failures were classified by nobody at the time, and writing
    a category onto them now would be this package's guess presented as the
    pipeline's record - the same class of defect as inventing
    ``actors.engine_bindings`` (WP-56). A NULL that means "never recorded" is
    honest; a value that means "WP-58 guessed in 2026-08" is not.
    """
    config = _get_config()
    api_url = f"{config.pipeline_api.full_base_url}/jobs/{job_id}"

    # WP-58 Task 6. `render_jobs.failure_category` was NULL on all 19 failed
    # jobs (WP-56 §6.4): the column exists, the PostgreSQL ENUM exists, this
    # function has always ACCEPTED the parameter, and `JobStatusUpdate`
    # (ivgs-api/app/api/v1/jobs.py:179) has always declared and written it. Every
    # link was present except a caller. Thirty-one sites call this function and
    # not one passed a category.
    #
    # CLASSIFIED HERE, NOT AT THE CALL SITES, AND THAT IS THE DESIGN. Most
    # terminal-failure calls live inside the eight stage task bodies
    # (stage7_prototype_draft, stage8_final_render, talking_head_task,
    # video_generation_task, animation_generation_task), which AD-05 §8 and
    # CLAUDE.md §3 freeze: "Wrapping is allowed; editing is not." Deriving the
    # category at this choke point fills the column for all 31 callers while
    # touching none of them.
    #
    # An explicitly-passed category always wins - a caller that knows the real
    # cause knows better than a regex over its own error string.
    #
    # ErrorCategory's four values are transient | config | external | resource,
    # which is the `failure_category` ENUM exactly; there is no mapping table to
    # drift. A classification failure must not cost the status write, so it is
    # caught: the job status is the thing that matters and a missing category is
    # a worse report, not a worse outcome.
    #
    # WP-63 Task 3 EXTENDS THIS CHOKE POINT, IT DOES NOT FORK IT. The
    # attribution runs FIRST, so the classification below sees the corrected
    # message rather than the summary of a downstream symptom. Both run at the
    # same single site and for the same reason: most terminal-failure calls
    # live inside frozen stage bodies (AD-05 section 8), so anything that has
    # to be true of every one of the 31 callers has to be true here.
    if status in _TERMINAL_FAILURE_STATUSES and error_message and job_id:
        try:
            error_message, ledger_stage, hint = _attribute_failure(
                job_id, error_message, config,
            )
            if ledger_stage and not stage:
                # `stage` lands on `render_jobs.resume_from_stage`
                # (`ivgs-api/app/api/v1/jobs.py`). A resume must restart at the
                # stage that FAILED; the incident's row said
                # `talking_head_render`, three stages past the real fault, so a
                # resume would have skipped the work that needed redoing. An
                # explicit `stage=` from the caller still wins.
                stage = ledger_stage
            if hint and not failure_category:
                failure_category = hint
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "failure_attribution_failed", job_id=job_id, error=str(exc),
            )

    if status in _TERMINAL_FAILURE_STATUSES and not failure_category and error_message:
        try:
            from services.error_classifier import ErrorClassifier

            failure_category = ErrorClassifier().classify_from_strings(
                exception_type="", exception_message=error_message,
            ).value
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "failure_category_classification_failed",
                job_id=job_id, error=str(exc),
            )

    payload: Dict[str, Any] = {"status": status}
    if error_message:
        payload["error_message"] = error_message
    if failure_category:
        payload["failure_category"] = failure_category
    if stage:
        payload["stage"] = stage

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


def advance_project_state(
    project_id: str,
    new_state: str,
    reason: str = "",
) -> bool:
    """Advance a project through the §6.1 lifecycle. WP-45 Task 2(a) / ORCH-5.

    PATCH /api/v1/projects/{id}/state, the route that did not exist until this
    package. ``ProjectService.transition_state`` has been implemented and
    validated since Phase 3 with **no route and no caller**, so nothing in the
    system ever advanced a project past MEDIA_GENERATION. MANIFEST_GENERATION,
    AUDIO_GENERATION, TALKING_HEAD_RENDER, PROTOTYPE_DRAFT and USER_REVIEW were
    states the schema declared and the running system could not reach - and
    spec §6.1's "post-assembly: project state transitions to USER_REVIEW", on
    which the whole draft-review gate depends, simply never happened
    (WP-39 §4 Gap A).

    Returns True when the project is now in ``new_state``.

    **This does not raise, and that is deliberate.** A project-state write is a
    record of where the pipeline is; the pipeline itself is the thing that
    matters and it must not stop because a bookkeeping call failed. But the
    failure is loud - one greppable ``project_state_advance_failed`` carrying
    the status code - rather than the silent False that the swallow register
    exists to catch. A 409 is logged separately at warning: it means the state
    machine refused the hop, which is information about the run, not a fault in
    this call.
    """
    if not project_id or not new_state:
        logger.warning(
            "project_state_advance_skipped",
            project_id=project_id,
            new_state=new_state,
            reason="missing project_id or state",
        )
        return False

    config = _get_config()
    api_url = f"{config.pipeline_api.full_base_url}/projects/{project_id}/state"

    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            resp = client.patch(
                api_url, json={"state": new_state, "reason": reason},
            )
    except Exception as exc:
        logger.error(
            "project_state_advance_failed",
            project_id=project_id,
            new_state=new_state,
            error=str(exc),
            consequence="pipeline continues; projects.state is now stale",
        )
        return False

    if resp.status_code == 200:
        logger.info(
            "project_state_advanced",
            project_id=project_id,
            new_state=new_state,
            reason=reason,
        )
        return True

    if resp.status_code == 409:
        # The state machine refused it. Usually because a human moved the
        # project while a stage was running, which is legitimate.
        logger.warning(
            "project_state_transition_refused",
            project_id=project_id,
            new_state=new_state,
            detail=resp.text[:300],
        )
        return False

    logger.error(
        "project_state_advance_failed",
        project_id=project_id,
        new_state=new_state,
        status_code=resp.status_code,
        detail=resp.text[:300],
        consequence="pipeline continues; projects.state is now stale",
    )
    return False


# ---------------------------------------------------------------------------
# Checkpoint save helper
# ---------------------------------------------------------------------------

class CheckpointWriteError(RuntimeError):
    """A pipeline checkpoint could not be written.

    Ledger P1.2 / WP-07, and swallow-register entry 3. This used to be a logged
    warning and a `False` return that none of the fifteen call sites checked, so
    every checkpoint write in the system's history failed silently against a route
    that did not exist (405 Method Not Allowed, measured 2026-08-23 with
    `pipeline_checkpoints` holding 0 rows).

    It raises now because an unrecorded stage is an unresumable stage: continuing
    past a failed checkpoint write produces exactly the job this package exists to
    abolish - one that must be re-run from the top. Callers that genuinely do not
    need the checkpoint pass `required=False` and get the old behaviour, explicitly.
    """


def save_checkpoint(
    job_id: str,
    stage_name: str,
    stage_index: int,
    status: str,
    checkpoint_data: Optional[Dict[str, Any]] = None,
    required: bool = True,
) -> bool:
    """
    Save a pipeline checkpoint via the Pipeline API (§5.2.4).

    POST /api/v1/jobs/{job_id}/checkpoints

    Raises CheckpointWriteError on failure unless `required=False`, in which case
    it returns False as it always did. No current call site passes `required`.
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
            logger.error(
                "checkpoint_save_failed",
                job_id=job_id,
                stage_name=stage_name,
                status_code=resp.status_code,
                required=required,
            )
            if required:
                raise CheckpointWriteError(
                    f"checkpoint write for job {job_id} stage {stage_name} "
                    f"returned HTTP {resp.status_code} from {api_url}. "
                    "The stage is not resumable without it."
                )
            return False
    except CheckpointWriteError:
        raise
    except Exception as e:
        logger.error(
            "checkpoint_save_error",
            job_id=job_id,
            stage_name=stage_name,
            error=str(e),
            required=required,
        )
        if required:
            raise CheckpointWriteError(
                f"checkpoint write for job {job_id} stage {stage_name} failed: "
                f"{e}. The stage is not resumable without it."
            ) from e
        return False
