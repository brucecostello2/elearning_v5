"""
IVGS v5 — Stage 1: Transcript Refinement Task
================================================

Pipeline Stage 1 per §6.1:
- Trigger: User uploads transcripts and triggers pipeline
- Input: One or more transcript records with extracted text
- LLM Engine: vLLM — Llama 3.3 70B on node-02/03
- Prompt: transcript_refinement type (3-tier hierarchy resolution)
- LLM persona: Instructional designer
- Processing rules:
    * Reduce complexity
    * Eliminate redundancy
    * Align with max_runtime_seconds
    * Apply Mayer's Multimedia Learning principles
    * Maintain learning intent
    * Target Flesch-Kincaid Grade 8
- Output: Refined transcript stored in transcripts table
- Timeout: 120 seconds
- Checkpoint: Saved after each transcript file refinement
- Retry: 4 retries with 5→15→45→135s backoff (Table 6-4)
- On exhaustion: Route to DLQ
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
import structlog
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError, select_autoescape

from celery_app import IVGSBaseTask, celery_app
from clients.vllm_client import (
    VLLMClient,
    VLLMError,
    VLLMTimeoutError,
)
from config import WorkerConfig
from models.task_result import (
    PipelineStage,
    RefinedTranscript,
    StageStatus,
    TranscriptRecord,
    TranscriptRefinementInput,
    TranscriptRefinementOutput,
)
from providers import ensure_registered
from shared.providers.factory import build_provider, get_binding
from utils.error_handler import (
    compute_backoff_delay,
    save_checkpoint,
    update_job_status,
)
from utils.gpu_utils import (
    acquire_gpu_reservation,
    get_vram_requirement,
)

logger = structlog.get_logger("ivgs.stage1.transcript")

# Jinja2 environment for prompt template rendering
jinja_env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(default_for_string=False, default=False),
    keep_trailing_newline=True,
)


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def _load_template(template_name: str) -> str:
    """
    Load a Jinja2 template from the prompts directory.
    Falls back to built-in templates if file not found.
    """
    config = WorkerConfig()
    template_path = os.path.join(config.prompt_template_dir, template_name)

    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    raise FileNotFoundError(
        f"Prompt template not found: {template_path}"
    )


def _resolve_prompts(
    task_input: TranscriptRefinementInput,
) -> Tuple[str, str]:
    """
    Resolve system and user prompts for transcript refinement.

    Priority (per §9.1 3-tier hierarchy):
    1. Explicit override in task input (from API caller)
    2. Database prompt (resolved via PromptService 3-tier chain)
    3. Local Jinja2 template file (fallback for offline/testing)

    Returns (system_prompt, user_prompt_template)
    """
    system_prompt = task_input.system_prompt
    user_template = task_input.user_prompt_template

    # Try loading from local templates as fallback
    if not system_prompt:
        try:
            system_prompt = _load_template("stage1_system.j2")
        except FileNotFoundError:
            logger.warning("stage1_system_template_not_found_using_default")
            system_prompt = _DEFAULT_SYSTEM_PROMPT

    if not user_template:
        try:
            user_template = _load_template("stage1_user.j2")
        except FileNotFoundError:
            logger.warning("stage1_user_template_not_found_using_default")
            user_template = _DEFAULT_USER_PROMPT

    return system_prompt, user_template


def _render_user_prompt(
    template_str: str,
    transcript: TranscriptRecord,
    context: Dict[str, Any],
) -> str:
    """
    Render Jinja2 user prompt with transcript and project context.

    Available template variables per §9.4:
        {{ project_title }}
        {{ project_description }}
        {{ target_audience }}
        {{ max_duration_seconds }}
        {{ transcript_text }}
        {{ sequence_order }}
        {{ language_code }}
        {{ total_transcripts }}
    """
    try:
        template = jinja_env.from_string(template_str)
        return template.render(
            project_title=context.get("project_name", ""),
            project_description=context.get("project_description", ""),
            target_audience=context.get("target_audience", "general"),
            max_duration_seconds=context.get("max_runtime_seconds", 600),
            transcript_text=transcript.original_text,
            sequence_order=transcript.sequence_order,
            language_code=transcript.language_code or "en-US",
            total_transcripts=context.get("total_transcripts", 1),
        )
    except TemplateSyntaxError as e:
        raise ValueError(f"Jinja2 syntax error in user prompt: {e}") from e
    except UndefinedError as e:
        raise ValueError(
            f"Undefined variable in user prompt template: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Database interaction helpers (via Pipeline API)
# ---------------------------------------------------------------------------

def _fetch_transcripts(
    project_id: str, config: WorkerConfig
) -> List[TranscriptRecord]:
    """
    Fetch transcript records from the Pipeline API.
    GET /api/v1/projects/{project_id}/transcripts
    """
    api_url = (
        f"{config.pipeline_api.full_base_url}"
        f"/projects/{project_id}/transcripts"
    )

    with httpx.Client(
        timeout=config.pipeline_api.timeout_seconds,
        headers={
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = client.get(api_url)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch transcripts: HTTP {resp.status_code} — {resp.text}"
            )

        data = resp.json()
        transcripts = []
        for item in data if isinstance(data, list) else data.get("items", data.get("transcripts", [])):
            transcripts.append(
                TranscriptRecord(
                    id=item["id"],
                    project_id=item.get("project_id", project_id),
                    sequence_order=item.get("sequence_order", 0),
                    original_text=item.get("refined_text") or item.get("original_text", ""),
                    refined_text=item.get("refined_text"),
                    language_code=item.get("language_code"),
                    original_asset_id=item.get("original_asset_id"),
                )
            )

        transcripts.sort(key=lambda t: t.sequence_order)
        return transcripts


def _update_transcript(
    transcript_id: str,
    project_id: str,
    refined_text: str,
    config: WorkerConfig,
) -> bool:
    """
    Update refined transcript text via Pipeline API.
    PATCH /api/v1/projects/{project_id}/transcripts/{transcript_id}
    """
    api_url = (
        f"{config.pipeline_api.full_base_url}"
        f"/projects/{project_id}/transcripts/{transcript_id}"
    )

    with httpx.Client(
        timeout=config.pipeline_api.timeout_seconds,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = client.patch(api_url, json={"refined_text": refined_text})
        if resp.status_code == 200:
            logger.info(
                "transcript_updated",
                transcript_id=transcript_id,
            )
            return True
        logger.warning(
            "transcript_update_failed",
            transcript_id=transcript_id,
            status_code=resp.status_code,
        )
        return False


def _resolve_prompts_from_api(
    project_id: str,
    config: WorkerConfig,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve prompts from the Pipeline API 3-tier hierarchy.
    GET /api/v1/projects/{project_id}/prompts?prompt_type=transcript_refinement
    """
    api_url = (
        f"{config.pipeline_api.full_base_url}"
        f"/projects/{project_id}/prompts"
    )

    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.pipeline_api.service_token}",
            },
        ) as client:
            resp = client.get(
                api_url,
                params={"prompt_type": "transcript_refinement"},
            )
            if resp.status_code == 200:
                prompts = resp.json()
                # Find system and user prompts from resolved list
                system_prompt = None
                user_prompt = None
                for p in (
                    prompts if isinstance(prompts, list)
                    else prompts.get("items", [])
                ):
                    text = p.get("prompt_text", "")
                    _scope = p.get("scope", p.get("source", ""))  # noqa: F841
                    if "system" in p.get("prompt_type", "").lower() or "system" in text[:100].lower():
                        system_prompt = text
                    else:
                        user_prompt = text

                return system_prompt, user_prompt
    except Exception as e:
        logger.warning(
            "prompt_api_resolution_failed",
            project_id=project_id,
            error=str(e),
        )

    return None, None


# ---------------------------------------------------------------------------
# Core refinement logic
# ---------------------------------------------------------------------------

async def _refine_single_transcript(
    transcript: TranscriptRecord,
    system_prompt: str,
    user_prompt_template: str,
    job_context: Dict[str, Any],
    vllm_client: VLLMClient,
    config: WorkerConfig,
) -> Tuple[Optional[RefinedTranscript], Optional[Dict[str, Any]]]:
    """
    Refine a single transcript using vLLM.

    Returns (RefinedTranscript, None) on success,
    or (None, error_dict) on failure.
    """
    start_time = time.monotonic()
    vllm_config = config.get_vllm_config_for_stage("transcript_refinement")

    # Render user prompt
    user_prompt = _render_user_prompt(
        template_str=user_prompt_template,
        transcript=transcript,
        context={
            "project_name": job_context.get("project_name", ""),
            "project_description": job_context.get("project_description", ""),
            "target_audience": job_context.get("target_audience", "general"),
            "max_runtime_seconds": job_context.get("max_runtime_seconds", 600),
            "total_transcripts": job_context.get("total_transcripts", 1),
        },
    )

    try:
        response = await vllm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=vllm_config["model"],
            base_url=vllm_config["base_url"],
            max_tokens=vllm_config["max_tokens"],
            temperature=vllm_config["temperature"],
            timeout=vllm_config["timeout"],
        )

        refined_text = response.content.strip()

        # Try to parse as JSON in case LLM returns structured output
        try:
            parsed = json.loads(refined_text)
            if isinstance(parsed, dict):
                refined_text = parsed.get(
                    "refined_text",
                    parsed.get("text", refined_text),
                )
        except json.JSONDecodeError:
            pass  # Plain text response, use as-is

        if not refined_text:
            return None, {
                "transcript_id": transcript.id,
                "error": "Empty response from vLLM",
            }

        elapsed = time.monotonic() - start_time
        usage = response.usage

        return (
            RefinedTranscript(
                transcript_id=transcript.id,
                sequence_order=transcript.sequence_order,
                original_text=transcript.original_text,
                refined_text=refined_text,
                language_code=transcript.language_code or "en-US",
                refinement_metadata={
                    "model": response.model,
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "processing_seconds": round(elapsed, 3),
                    "finish_reason": response.finish_reason,
                },
            ),
            None,
        )

    except VLLMTimeoutError as e:
        elapsed = time.monotonic() - start_time
        logger.warning(
            "transcript_refinement_timeout",
            transcript_id=transcript.id,
            elapsed=round(elapsed, 3),
        )
        return None, {
            "transcript_id": transcript.id,
            "error": f"vLLM timeout after {elapsed:.1f}s: {e}",
            "exception_type": "VLLMTimeoutError",
        }

    except VLLMError as e:
        return None, {
            "transcript_id": transcript.id,
            "error": str(e),
            "exception_type": type(e).__name__,
        }

    except Exception as e:
        return None, {
            "transcript_id": transcript.id,
            "error": str(e),
            "exception_type": type(e).__name__,
        }


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.stage1_transcript.refine_transcript_task",
    max_retries=4,
    soft_time_limit=120,
    time_limit=150,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="gpu_llm",
)
def refine_transcript_task(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task for Stage 1: Transcript Refinement.

    Accepts serialized TranscriptRefinementInput dict, processes all
    transcripts through vLLM, saves results to DB, and creates checkpoint.

    Parameters
    ----------
    task_input_dict : dict
        Serialized TranscriptRefinementInput.

    Returns
    -------
    dict
        Serialized TranscriptRefinementOutput.
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_refinement(self, task_input_dict)
    )


async def _run_refinement(
    task: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Async implementation of transcript refinement."""
    config = WorkerConfig()
    start_time = time.monotonic()

    # Parse input
    try:
        task_input = TranscriptRefinementInput(**task_input_dict)
    except Exception as e:
        logger.error("stage1_input_parse_error", error=str(e))
        raise ValueError(f"Invalid Stage 1 input: {e}") from e

    job_context = task_input.job_context
    job_id = job_context.job_id
    project_id = job_context.project_id

    log = logger.bind(job_id=job_id, project_id=project_id, stage="stage1")
    log.info(
        "stage1_starting",
        transcript_count=len(task_input.transcripts),
    )

    # Update job status to running
    update_job_status(job_id, "running")

    # Save initial checkpoint
    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=job_id,
            stage_name=PipelineStage.TRANSCRIPT_REFINEMENT.value,
            stage_index=1,
            status="running",
            checkpoint_data={"started_at": datetime.now(timezone.utc).isoformat()},
        )

    # ARCH-1: resolve the selection-aware binding once; the GPU reservation
    # and the vLLM client both derive from it — no hard-coded model identity.
    ensure_registered()
    binding = await get_binding(
        "transcript_refinement",
        project_id=UUID(project_id),
        tier=job_context.tier,
    )
    log.info("model_bound", binding=binding.describe())

    # GPU reservation (if enabled)
    reservation_id = None
    if config.enable_gpu_reservation:
        try:
            model_name = binding.name
            vram_req = binding.vram_requirement_mb or get_vram_requirement(model_name)
            reservation = acquire_gpu_reservation(
                job_id=job_id,
                model_name=model_name,
                vram_requirement_mb=vram_req,
                estimated_duration_s=config.timeouts.vllm_timeout
                    * len(task_input.transcripts),
                priority=job_context.priority,
            )
            reservation_id = reservation.get("reservation_id")
            task._gpu_reservation_id = reservation_id
            log.info(
                "gpu_reserved",
                reservation_id=reservation_id,
                node_id=reservation.get("node_id"),
            )
        except Exception as gpu_err:
            log.warning(
                "gpu_reservation_skipped",
                error=str(gpu_err),
            )

    # Resolve prompts
    system_prompt, user_template = _resolve_prompts(task_input)

    # Try API-based prompt resolution
    api_sys, api_user = _resolve_prompts_from_api(project_id, config)
    if api_sys:
        system_prompt = api_sys
    if api_user:
        user_template = api_user

    # Idempotency check
    idempotency_hash = ""
    if config.enable_idempotency_check:
        from clients.vllm_client import VLLMClient as VC
        idempotency_hash = VC.compute_request_hash(
            system_prompt=system_prompt,
            user_prompt=user_template,
            model=binding.name,
            temperature=config.vllm.temperature,
            max_tokens=config.vllm.max_tokens,
        )

    # Fetch transcripts if not provided in input
    transcripts = task_input.transcripts
    if not transcripts or not transcripts[0].original_text:
        try:
            transcripts = _fetch_transcripts(project_id, config)
            log.info(
                "transcripts_fetched_from_api",
                count=len(transcripts),
            )
        except Exception as fetch_err:
            log.error("transcript_fetch_failed", error=str(fetch_err))
            raise

    # Process each transcript through vLLM
    refined_results: List[RefinedTranscript] = []
    errors: List[Dict[str, Any]] = []
    total_input_tokens = 0
    total_output_tokens = 0

    async with build_provider(binding) as vllm_client:
        for transcript in transcripts:
            log.info(
                "refining_transcript",
                transcript_id=transcript.id,
                sequence_order=transcript.sequence_order,
                text_length=len(transcript.original_text),
            )

            result, error = await _refine_single_transcript(
                transcript=transcript,
                system_prompt=system_prompt,
                user_prompt_template=user_template,
                job_context={
                    "project_name": job_context.project_name,
                    "project_description": job_context.project_description,
                    "target_audience": job_context.target_audience,
                    "max_runtime_seconds": job_context.max_runtime_seconds,
                    "total_transcripts": len(transcripts),
                },
                vllm_client=vllm_client,
                config=config,
            )

            if result:
                refined_results.append(result)
                meta = result.refinement_metadata
                total_input_tokens += meta.get("prompt_tokens", 0)
                total_output_tokens += meta.get("completion_tokens", 0)

                # Save to DB immediately
                _update_transcript(
                    transcript_id=transcript.id,
                    project_id=project_id,
                    refined_text=result.refined_text,
                    config=config,
                )

                # Per-transcript checkpoint
                if config.enable_checkpoint_saving:
                    save_checkpoint(
                        job_id=job_id,
                        stage_name=PipelineStage.TRANSCRIPT_REFINEMENT.value,
                        stage_index=1,
                        status="running",
                        checkpoint_data={
                            "completed_transcripts": len(refined_results),
                            "total_transcripts": len(transcripts),
                            "last_transcript_id": transcript.id,
                        },
                    )

                log.info(
                    "transcript_refined",
                    transcript_id=transcript.id,
                    original_length=len(transcript.original_text),
                    refined_length=len(result.refined_text),
                )
            else:
                errors.append(error or {"transcript_id": transcript.id})
                log.warning(
                    "transcript_refinement_failed",
                    transcript_id=transcript.id,
                    error=error,
                )

    # Build output
    elapsed = time.monotonic() - start_time
    status = (
        StageStatus.SUCCESS
        if not errors
        else StageStatus.FAILED if len(errors) == len(transcripts) else StageStatus.SUCCESS
    )

    output = TranscriptRefinementOutput(
        job_id=job_id,
        project_id=project_id,
        status=status,
        refined_transcripts=refined_results,
        total_transcripts=len(transcripts),
        successful_count=len(refined_results),
        failed_count=len(errors),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        processing_time_seconds=round(elapsed, 3),
        model_used=binding.name,
        idempotency_hash=idempotency_hash,
        errors=errors,
        completed_at=datetime.now(timezone.utc),
    )

    # Final checkpoint
    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=job_id,
            stage_name=PipelineStage.TRANSCRIPT_REFINEMENT.value,
            stage_index=1,
            status=status.value,
            checkpoint_data=output.to_checkpoint_data(),
        )

    # Handle failures with retry
    if status == StageStatus.FAILED:
        retry_count = task.request.retries
        retry_config = config.get_retry_config_for_stage("transcript_refinement")
        max_retries = retry_config["max_retries"]

        if retry_count < max_retries:
            delay = compute_backoff_delay(
                retry_count=retry_count,
                stage="transcript_refinement",
                config=config,
            )
            log.warning(
                "stage1_retrying",
                retry_count=retry_count + 1,
                max_retries=max_retries,
                delay=delay,
            )
            raise task.retry(
                countdown=delay,
                max_retries=max_retries,
                exc=RuntimeError(
                    f"Stage 1 failed: {len(errors)} transcript(s) failed"
                ),
            )

    log.info(
        "stage1_completed",
        status=status.value,
        refined_count=len(refined_results),
        failed_count=len(errors),
        elapsed=round(elapsed, 3),
        total_tokens=total_input_tokens + total_output_tokens,
    )

    output_dict = output.model_dump(mode="json")
    output_dict.setdefault("stage", PipelineStage.TRANSCRIPT_REFINEMENT.value)
    # Advance the pipeline: notify the orchestrator this stage completed.
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )
    return output_dict


# ---------------------------------------------------------------------------
# Default prompts (fallback if templates not found)
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """You are an expert instructional designer specializing in \
educational video content. Your task is to refine raw transcripts into clear, \
well-structured educational narrations.

Follow these rules strictly:
1. Target Flesch-Kincaid Grade Level 8 readability
2. Apply Mayer's Multimedia Learning principles
3. Eliminate jargon and redundancy while preserving accuracy
4. Maintain the original learning intent and key concepts
5. Structure content into timed segments suitable for video narration
6. Use a neutral, professional tone throughout
7. Ensure content flows naturally when read aloud

Output the refined transcript as plain text, ready for narration."""

_DEFAULT_USER_PROMPT = """Please refine the following transcript for an educational video.

Project: {{ project_title }}
Target Audience: {{ target_audience }}
Maximum Video Duration: {{ max_duration_seconds }} seconds
Transcript Section: {{ sequence_order }} of {{ total_transcripts }}

--- RAW TRANSCRIPT ---
{{ transcript_text }}
--- END TRANSCRIPT ---

Produce a refined version that is clear, concise, and suitable for video narration. \
Maintain all factual content while simplifying language to Grade 8 reading level."""
