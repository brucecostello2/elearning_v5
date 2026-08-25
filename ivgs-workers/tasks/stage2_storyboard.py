"""
IVGS v5 — Stage 2: Storyboard Generation Task
================================================

Pipeline Stage 2 per §6.1:
- Input: Refined transcripts from Stage 1
- LLM Engine: vLLM, Llama 3.3 70B
- Prompt: storyboard_generation type (3-tier hierarchy)
- Output JSON per scene:
    * scene_index (int)
    * narration_text (str)
    * visual_description (str)
    * media_type (image | video_clip | animation)
    * duration_seconds (float)
- Storage: storyboard_scenes table
- User gate: Review, reorder, edit, or regenerate individual scenes
- Timeout: 120 seconds
- Retry: 4 retries with 5→15→45→135s backoff (Table 6-4)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
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
    VLLMInvalidResponseError,
    VLLMTimeoutError,
)
from config import WorkerConfig
from models.task_result import (
    MEDIA_TYPE_SYNONYMS,
    PipelineStage,
    RefinedTranscript,
    StageStatus,
    StoryboardGenerationInput,
    StoryboardGenerationOutput,
    StoryboardScene,
)
from providers import ensure_registered
from providers._common import engine_model_id
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
from utils.prompt_selection import _select_prompt_text

logger = structlog.get_logger("ivgs.stage2.storyboard")

jinja_env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(default_for_string=False, default=False),
    keep_trailing_newline=True,
)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _load_template(template_name: str) -> str:
    """Load a Jinja2 template from the prompts directory."""
    config = WorkerConfig()
    template_path = os.path.join(config.prompt_template_dir, template_name)
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Prompt template not found: {template_path}")


def _resolve_prompts(
    task_input: StoryboardGenerationInput,
) -> Tuple[str, str]:
    """Resolve system and user prompts for storyboard generation."""
    system_prompt = task_input.system_prompt
    user_template = task_input.user_prompt_template

    if not system_prompt:
        try:
            system_prompt = _load_template("stage2_system.j2")
        except FileNotFoundError:
            logger.warning("stage2_system_template_not_found_using_default")
            system_prompt = _DEFAULT_SYSTEM_PROMPT

    if not user_template:
        try:
            user_template = _load_template("stage2_user.j2")
        except FileNotFoundError:
            logger.warning("stage2_user_template_not_found_using_default")
            user_template = _DEFAULT_USER_PROMPT

    return system_prompt, user_template


def _render_user_prompt(
    template_str: str,
    refined_transcripts: List[RefinedTranscript],
    context: Dict[str, Any],
) -> str:
    """Render user prompt with all refined transcripts and project context."""
    # Combine all transcripts in sequence order
    combined_transcript = "\n\n".join(
        f"[Segment {t.sequence_order}]\n{t.refined_text}"
        for t in sorted(refined_transcripts, key=lambda t: t.sequence_order)
    )

    try:
        template = jinja_env.from_string(template_str)
        return template.render(
            project_title=context.get("project_name", ""),
            project_description=context.get("project_description", ""),
            target_audience=context.get("target_audience", "general"),
            max_duration_seconds=context.get("max_runtime_seconds", 600),
            total_runtime_seconds=context.get("max_runtime_seconds", 600),
            combined_transcript=combined_transcript,
            transcript_count=len(refined_transcripts),
            target_scene_count=context.get("target_scene_count"),
            language_code=context.get("language_code", "en-US"),
        )
    except TemplateSyntaxError as e:
        raise ValueError(f"Jinja2 syntax error in storyboard prompt: {e}") from e
    except UndefinedError as e:
        raise ValueError(
            f"Undefined variable in storyboard prompt: {e}"
        ) from e


def _resolve_prompts_from_api(
    project_id: str,
    config: WorkerConfig,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the Stage 2 prompt from the Pipeline API 3-tier hierarchy.

    Returns ``(system_prompt, user_prompt_template)``. The system slot is always
    ``None``: a PromptType row carries exactly one text, so the API can only
    supply the user template. The system prompt comes from stage2_system.j2.

    IVGS-0.4: same fix as Stage 1 — exact type match, and a mismatched type is
    refused rather than substituted. That refusal is not caught here.
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
                params={"prompt_type": "storyboard_generation"},
            )
            payload = resp.json() if resp.status_code == 200 else None
    except Exception as e:
        logger.warning(
            "storyboard_prompt_api_resolution_failed",
            project_id=project_id,
            error=str(e),
        )
        return None, None

    if payload is None:
        return None, None
    return None, _select_prompt_text(payload, "storyboard_generation")


# ---------------------------------------------------------------------------
# Storyboard JSON validation
# ---------------------------------------------------------------------------

def _validate_storyboard_json(
    raw_scenes: Any,
    max_duration: int = 600,
) -> List[StoryboardScene]:
    """
    Validate and normalize the LLM-generated storyboard JSON.

    Accepts either:
    - A list of scene dicts
    - A dict with a "scenes" key containing a list

    Validates each scene has required fields and reasonable values.
    """
    scenes_list: List[Dict[str, Any]] = []

    if isinstance(raw_scenes, dict):
        # Extract scenes from wrapper object
        scenes_list = raw_scenes.get(
            "scenes",
            raw_scenes.get("storyboard", []),
        )
        if not isinstance(scenes_list, list):
            raise ValueError(
                f"Expected 'scenes' to be a list, got {type(scenes_list).__name__}"
            )
    elif isinstance(raw_scenes, list):
        scenes_list = raw_scenes
    else:
        raise ValueError(
            f"Expected list or dict, got {type(raw_scenes).__name__}"
        )

    if not scenes_list:
        raise ValueError("Storyboard is empty — no scenes generated")

    validated_scenes: List[StoryboardScene] = []
    total_duration = 0.0

    for i, raw_scene in enumerate(scenes_list):
        if not isinstance(raw_scene, dict):
            logger.warning(
                "skipping_invalid_scene",
                index=i,
                type=type(raw_scene).__name__,
            )
            continue

        # Normalize field names (handle various LLM output variations)
        narration = (
            raw_scene.get("narration_text")
            or raw_scene.get("narration")
            or raw_scene.get("narrator_text")
            or raw_scene.get("text")
            or ""
        )
        visual = (
            raw_scene.get("visual_description")
            or raw_scene.get("visual")
            or raw_scene.get("description")
            or raw_scene.get("image_description")
            or ""
        )
        media_type_raw = (
            raw_scene.get("media_type")
            or raw_scene.get("type")
            or raw_scene.get("visual_type")
            or "image"
        )
        duration = raw_scene.get(
            "duration_seconds",
            raw_scene.get("duration", 15.0),
        )
        scene_index = raw_scene.get(
            "scene_index",
            raw_scene.get("index", i),
        )

        # Validate required fields
        if not narration.strip():
            logger.warning(
                "scene_missing_narration",
                scene_index=scene_index,
            )
            continue

        if not visual.strip():
            visual = f"Visual representation of: {narration[:100]}"

        # Clamp duration
        if isinstance(duration, str):
            try:
                duration = float(duration)
            except ValueError:
                duration = 15.0

        duration = max(3.0, min(float(duration), 120.0))
        total_duration += duration

        # WP-53 (P2.54). Checked HERE, ahead of the constructor, and raised
        # rather than logged.
        #
        # The try/except below skips a scene it cannot build and carries on --
        # which for an out-of-taxonomy media_type is the wrong answer twice
        # over. Silently dropping a scene loses content the operator asked for,
        # and it would convert the loud rejection the model now performs back
        # into the quiet one this package exists to remove. A media type the
        # taxonomy does not contain is a defect in the storyboard, and Stage 2
        # is where a storyboard defect is cheap: the job stops here instead of
        # producing a still image where a video belonged, five stages later,
        # with nothing in any log to say why.
        if not isinstance(media_type_raw, str) or (
            str(media_type_raw).strip().lower() not in MEDIA_TYPE_SYNONYMS
        ):
            raise ValueError(
                f"Scene {scene_index}: media_type {media_type_raw!r} is not in the "
                f"pipeline taxonomy. Known values: "
                f"{sorted(set(MEDIA_TYPE_SYNONYMS))}. "
                f"Stage 3 dispatches on this field and has no branch for it."
            )

        try:
            scene = StoryboardScene(
                scene_index=scene_index if isinstance(scene_index, int) else i,
                narration_text=narration.strip(),
                visual_description=visual.strip(),
                media_type=media_type_raw,
                duration_seconds=duration,
                scene_title=raw_scene.get("scene_title", raw_scene.get("title")),
                transition=raw_scene.get("transition"),
                notes=raw_scene.get("notes"),
            )
            validated_scenes.append(scene)
        except Exception as e:
            logger.warning(
                "scene_validation_failed",
                scene_index=i,
                error=str(e),
            )

    if not validated_scenes:
        raise ValueError("No valid scenes after validation")

    # Re-index scenes sequentially
    for idx, scene in enumerate(validated_scenes):
        scene.scene_index = idx

    logger.info(
        "storyboard_validated",
        total_scenes=len(validated_scenes),
        total_duration=round(total_duration, 1),
    )

    return validated_scenes


def _extract_json_from_response(content: str) -> Any:
    """
    Extract JSON from LLM response, handling markdown fences and preamble.
    """
    content = content.strip()

    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    fence_pattern = r"```(?:json)?\s*\n([\s\S]*?)\n```"
    matches = re.findall(fence_pattern, content)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Try finding a JSON object or array embedded in prose.
    #
    # WP-53 (P2.55). This loop used to try "[" before "{", unconditionally. For
    # the response shape the Stage 2 prompt actually asks for --
    # `{"scenes": [...]}` with a sentence in front of it -- that found the INNER
    # array first and returned it, discarding the wrapper and every sibling
    # field on it. The direct-parse and code-fence paths above return the object
    # intact, which is exactly why only one of the three extraction tests failed
    # and the defect read as a test problem.
    #
    # Take whichever delimiter opens FIRST. That is the outermost structure by
    # definition, so it works for a wrapped object AND for a bare top-level
    # array with a preamble -- the case a naive "{" before "[" flip would have
    # broken instead.
    candidates = [
        (idx, open_char, close_char)
        for open_char, close_char in (("{", "}"), ("[", "]"))
        if (idx := content.find(open_char)) >= 0
    ]

    for _, start_char, end_char in sorted(candidates):
        start_idx = content.find(start_char)
        # Find matching closing bracket
        depth = 0
        for i in range(start_idx, len(content)):
            if content[i] == start_char:
                depth += 1
            elif content[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(content[start_idx : i + 1])
                    except json.JSONDecodeError:
                        # This span is not valid JSON; fall through to the other
                        # delimiter rather than giving up on extraction.
                        break

    raise ValueError(
        f"Could not extract valid JSON from LLM response. "
        f"First 500 chars: {content[:500]}"
    )


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _save_storyboard_scenes(
    project_id: str,
    scenes: List[StoryboardScene],
    config: WorkerConfig,
) -> List[str]:
    """
    Save validated storyboard scenes to the database via Pipeline API.
    Returns list of created scene UUIDs.
    """
    scene_ids: List[str] = []

    for scene in scenes:
        api_url = (
            f"{config.pipeline_api.full_base_url}"
            f"/projects/{project_id}/scenes"
        )

        payload = {
            "scene_index": scene.scene_index,
            "narration_text": scene.narration_text,
            "visual_description": scene.visual_description,
            "media_type": scene.media_type,
            "duration_seconds": scene.duration_seconds,
        }

        try:
            with httpx.Client(
                timeout=config.pipeline_api.timeout_seconds,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": (
                        f"Bearer {config.pipeline_api.service_token}"
                    ),
                },
            ) as client:
                # Try POST to create; if scenes already exist, try PATCH
                resp = client.post(api_url, json=payload)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    scene_id = data.get("id", "")
                    scene_ids.append(scene_id)
                    logger.info(
                        "scene_saved",
                        scene_index=scene.scene_index,
                        scene_id=scene_id,
                    )
                elif resp.status_code == 409:
                    # Scene already exists (idempotency), try update
                    logger.info(
                        "scene_already_exists",
                        scene_index=scene.scene_index,
                    )
                else:
                    logger.warning(
                        "scene_save_failed",
                        scene_index=scene.scene_index,
                        status_code=resp.status_code,
                        response=resp.text[:300],
                    )
        except Exception as e:
            logger.error(
                "scene_save_error",
                scene_index=scene.scene_index,
                error=str(e),
            )

    return scene_ids


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=IVGSBaseTask,
    name="tasks.stage2_storyboard.generate_storyboard_task",
    max_retries=4,
    soft_time_limit=120,
    time_limit=150,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="gpu_llm",
)
def generate_storyboard_task(
    self: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task for Stage 2: Storyboard Generation.

    Parameters
    ----------
    task_input_dict : dict
        Serialized StoryboardGenerationInput.

    Returns
    -------
    dict
        Serialized StoryboardGenerationOutput.
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_storyboard_generation(self, task_input_dict)
    )


async def _run_storyboard_generation(
    task: IVGSBaseTask,
    task_input_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Async implementation of storyboard generation."""
    config = WorkerConfig()
    start_time = time.monotonic()

    # Parse input
    try:
        task_input = StoryboardGenerationInput(**task_input_dict)
    except Exception as e:
        logger.error("stage2_input_parse_error", error=str(e))
        raise ValueError(f"Invalid Stage 2 input: {e}") from e

    job_context = task_input.job_context
    job_id = job_context.job_id
    project_id = job_context.project_id

    log = logger.bind(job_id=job_id, project_id=project_id, stage="stage2")
    log.info(
        "stage2_starting",
        transcript_count=len(task_input.refined_transcripts),
    )

    # Update job status
    update_job_status(job_id, "running")

    # Save initial checkpoint
    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=job_id,
            stage_name=PipelineStage.STORYBOARD_GENERATION.value,
            stage_index=2,
            status="running",
            checkpoint_data={
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ARCH-1: resolve the selection-aware binding once; reservation + client
    # both derive from it — no hard-coded model identity.
    ensure_registered()
    binding = await get_binding(
        "storyboard_generation",
        project_id=UUID(project_id),
        tier=job_context.tier,
    )
    log.info("model_bound", binding=binding.describe())

    # GPU reservation
    reservation_id = None
    if config.enable_gpu_reservation:
        # Bound before the try - see stage1_transcript.py for why.
        model_name = ""
        vram_req = 0
        try:
            model_name = binding.name
            vram_req = binding.vram_requirement_mb or get_vram_requirement(model_name)
            reservation = acquire_gpu_reservation(
                job_id=job_id,
                model_name=model_name,
                vram_requirement_mb=vram_req,
                estimated_duration_s=config.timeouts.vllm_timeout,
                priority=job_context.priority,
            )
            reservation_id = reservation.get("reservation_id")
            task._gpu_reservation_id = reservation_id
        except Exception as gpu_err:
            # FAIL-OPEN, deliberately and for now - see AD-05 O-3 / P2.6.
            # acquire RAISES (gpu_utils.py:202); the stage proceeds unreserved.
            log.warning(
                "gpu_reservation_unavailable",
                stage=PipelineStage.STORYBOARD_GENERATION.value,
                model=model_name,
                vram_mb=vram_req,
                error_type=type(gpu_err).__name__,
                error=str(gpu_err),
                fail_open=True,
            )

    # Resolve prompts
    system_prompt, user_template = _resolve_prompts(task_input)

    api_sys, api_user = _resolve_prompts_from_api(project_id, config)
    if api_sys:
        system_prompt = api_sys
    if api_user:
        user_template = api_user

    # Render user prompt
    user_prompt = _render_user_prompt(
        template_str=user_template,
        refined_transcripts=task_input.refined_transcripts,
        context={
            "project_name": job_context.project_name,
            "project_description": job_context.project_description,
            "target_audience": job_context.target_audience,
            "max_runtime_seconds": job_context.max_runtime_seconds,
            "target_scene_count": task_input.target_scene_count,
            "language_code": job_context.language_code,
        },
    )

    # Idempotency hash
    vllm_config = config.get_vllm_config_for_stage("storyboard_generation")

    # WP-58 Task 5. Scale the OUTPUT budget to the storyboard actually being
    # asked for. WP-37 raised this stage off the shared 2048-token knob onto a
    # fixed 8192, which is comfortable for the largest storyboard measured
    # (18 scenes, ~2,700 output tokens) - but a fixed ceiling is the same defect
    # one course-size larger, and 2048 was comfortable too until it was not.
    #
    # `storyboard_max_tokens_for` can only WIDEN the budget, never narrow it, so
    # a target_scene_count that is absent or wrong-low falls back to the floor
    # rather than reintroducing truncation. The finish_reason guard in
    # `VLLMClient.chat_json` remains the backstop for everything this misjudges.
    vllm_config["max_tokens"] = config.storyboard_max_tokens_for(
        task_input.target_scene_count
    )
    idempotency_hash = ""
    if config.enable_idempotency_check:
        idempotency_hash = VLLMClient.compute_request_hash(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=engine_model_id(binding),
            temperature=vllm_config["temperature"],
            max_tokens=vllm_config["max_tokens"],
        )

    # Call vLLM
    errors: List[Dict[str, Any]] = []
    scenes: List[StoryboardScene] = []
    total_input_tokens = 0
    total_output_tokens = 0
    model_used = binding.name

    try:
        async with build_provider(binding) as vllm_client:
            log.info("vllm_storyboard_request_starting")

            parsed_json, response = await vllm_client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=engine_model_id(binding),
                base_url=binding.endpoint,
                max_tokens=vllm_config["max_tokens"],
                temperature=vllm_config["temperature"],
                timeout=vllm_config["timeout"],
            )

            usage = response.usage
            total_input_tokens = usage.prompt_tokens if usage else 0
            total_output_tokens = usage.completion_tokens if usage else 0
            model_used = response.model or model_used

            log.info(
                "vllm_storyboard_response_received",
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )

            # Validate and normalize storyboard JSON
            scenes = _validate_storyboard_json(
                parsed_json,
                max_duration=job_context.max_runtime_seconds,
            )

    except VLLMInvalidResponseError as e:
        log.error("storyboard_json_parse_failed", error=str(e))

        # Try to extract JSON from raw content
        try:
            raw_content = e.response_body or ""
            extracted = _extract_json_from_response(raw_content)
            scenes = _validate_storyboard_json(
                extracted,
                max_duration=job_context.max_runtime_seconds,
            )
        except Exception as extract_err:
            errors.append({
                "error": f"JSON parse failed: {e}",
                "extraction_error": str(extract_err),
            })

    except VLLMTimeoutError as e:
        log.error("storyboard_vllm_timeout", error=str(e))
        errors.append({"error": f"vLLM timeout: {e}"})

    except VLLMError as e:
        log.error("storyboard_vllm_error", error=str(e))
        errors.append({"error": str(e)})

    except Exception as e:
        log.error(
            "storyboard_unexpected_error",
            error=str(e),
            exception_type=type(e).__name__,
        )
        errors.append({"error": str(e), "type": type(e).__name__})

    # Save scenes to database
    scene_ids: List[str] = []
    if scenes:
        scene_ids = _save_storyboard_scenes(project_id, scenes, config)

    # Compute totals
    total_duration = sum(s.duration_seconds for s in scenes)
    elapsed = time.monotonic() - start_time

    status = (
        StageStatus.SUCCESS if scenes and not errors
        else StageStatus.FAILED
    )

    output = StoryboardGenerationOutput(
        job_id=job_id,
        project_id=project_id,
        status=status,
        scenes=scenes,
        total_scenes=len(scenes),
        total_duration_seconds=round(total_duration, 2),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        processing_time_seconds=round(elapsed, 3),
        model_used=model_used,
        idempotency_hash=idempotency_hash,
        scene_ids=scene_ids,
        errors=errors,
        completed_at=datetime.now(timezone.utc),
    )

    # Save checkpoint
    if config.enable_checkpoint_saving:
        save_checkpoint(
            job_id=job_id,
            stage_name=PipelineStage.STORYBOARD_GENERATION.value,
            stage_index=2,
            status=status.value,
            checkpoint_data=output.to_checkpoint_data(),
        )

    # Handle failure with retry
    if status == StageStatus.FAILED:
        retry_count = task.request.retries
        retry_config = config.get_retry_config_for_stage(
            "storyboard_generation"
        )
        max_retries = retry_config["max_retries"]

        if retry_count < max_retries:
            delay = compute_backoff_delay(
                retry_count=retry_count,
                stage="storyboard_generation",
                config=config,
            )
            log.warning(
                "stage2_retrying",
                retry_count=retry_count + 1,
                max_retries=max_retries,
                delay=delay,
            )
            raise task.retry(
                countdown=delay,
                max_retries=max_retries,
                exc=RuntimeError(
                    f"Stage 2 failed: {errors}"
                ),
            )

    log.info(
        "stage2_completed",
        status=status.value,
        total_scenes=len(scenes),
        total_duration=round(total_duration, 1),
        elapsed=round(elapsed, 3),
    )

    output_dict = output.model_dump(mode="json")
    output_dict.setdefault("stage", PipelineStage.STORYBOARD_GENERATION.value)
    # Advance the pipeline: storyboard completion -> storyboard_review gate.
    celery_app.send_task(
        "tasks.pipeline_orchestrator_v2.handle_stage_completion",
        kwargs={"stage_output_dict": output_dict},
        queue="default",
    )
    return output_dict


# ---------------------------------------------------------------------------
# Default prompts
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """You are an expert storyboard designer for educational video \
production. You transform refined narration transcripts into detailed, scene-by-scene \
storyboards optimized for automated video generation.

Your storyboard output MUST be a valid JSON object containing a "scenes" array. Each \
scene object must include:
- "scene_index": integer (0-based sequential index)
- "narration_text": string (the narration for this scene)
- "visual_description": string (detailed visual description for image/video generation)
- "media_type": string ("image", "video_clip", or "animation")
- "duration_seconds": number (scene duration matching narration length)

Guidelines:
1. Each scene should be 10-30 seconds of narration
2. Visual descriptions must be detailed enough to generate images from
3. Use "image" for static concepts, "video_clip" for action/process, "animation" for data/diagrams
4. Durations should sum to approximately the total video duration
5. Ensure smooth narrative transitions between scenes
6. Visual descriptions should complement (not duplicate) the narration

Output ONLY valid JSON. No markdown, no commentary, no preamble."""

_DEFAULT_USER_PROMPT = """Generate a storyboard for the following educational video.

## Project Context
- **Title**: {{ project_title }}
{% if project_description %}- **Description**: {{ project_description }}
{% endif %}- **Target Audience**: {{ target_audience }}
- **Target Duration**: {{ max_duration_seconds }} seconds (~{{ (max_duration_seconds / 60) | round(1) }} minutes)
{% if target_scene_count %}- **Target Scene Count**: ~{{ target_scene_count }} scenes
{% endif %}

## Refined Transcript

{{ combined_transcript }}

## Requirements

Generate a JSON object with a "scenes" array. Each scene must have:
- scene_index (int, 0-based)
- narration_text (str, excerpt from the transcript for this scene)
- visual_description (str, detailed visual for image/video generation)
- media_type (str: "image", "video_clip", or "animation")
- duration_seconds (float, matching narration pace ~150 words/minute)

Total duration across all scenes should be approximately {{ max_duration_seconds }} seconds.
Output ONLY the JSON object."""
