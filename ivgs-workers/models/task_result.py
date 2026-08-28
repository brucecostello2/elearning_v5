"""
IVGS v5 – Pipeline Task Result Models
======================================

Pydantic models and enums consumed by every worker task in the IVGS pipeline.
This is the **single source of truth** for inter-stage data contracts.

Symbols exported (17):
  Enums       – PipelineStage, StageStatus, FailureCategory, MediaType
  Context     – PipelineJobContext
  Stage 1 I/O – TranscriptRecord, RefinedTranscript,
                TranscriptRefinementInput, TranscriptRefinementOutput
  Stage 2 I/O – StoryboardScene, StoryboardGenerationInput,
                StoryboardGenerationOutput
  vLLM        – VLLMUsage, VLLMMessage, VLLMChoice, VLLMResponse
  Error       – ErrorDetail
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStage(str, Enum):
    """All stages in the 8-stage IVGS video-generation pipeline.

    Members use UPPER_SNAKE naming; `.value` is the lower_snake string
    stored in the DB and passed over the wire.
    """

    TRANSCRIPT_REFINEMENT = "transcript_refinement"
    STORYBOARD_GENERATION = "storyboard_generation"
    IMAGE_GENERATION = "image_generation"
    COMPOSITION_MANIFEST = "composition_manifest"
    TTS_AUDIO = "tts_audio"
    TALKING_HEAD_RENDER = "talking_head_render"
    PROTOTYPE_DRAFT = "prototype_draft"
    FINAL_RENDER = "final_render"

    # Parallel media-generation stages dispatched alongside IMAGE_GENERATION
    VIDEO_GENERATION = "video_generation"
    ANIMATION_GENERATION = "animation_generation"
    # WP-IVGS-09. The fourth media branch gets its own label for the reason
    # WP-39 gave animation one: the media join counts ONE report per dispatched
    # media STAGE and guards each with a (job_id, stage) idempotency key, so two
    # branches reporting under one label means the second is dropped as a
    # duplicate and the join hangs with every asset already in SeaweedFS
    # (measured on job bd99fe37, 2026-08-23). Sharing `animation_generation`
    # with Wan — which is where MBCP's taxonomy puts both, and why WP-67
    # registers `maths_motion` there — would reproduce exactly that.
    #
    # Safe against the schema: `pipeline_checkpoints.stage_name`,
    # `render_jobs.resume_from_stage` and `task_retries.stage_name` are all
    # varchar. The `model_stage` DB enum is MBCP's NINE-value taxonomy and is a
    # different thing entirely (dev/CLAUDE.md §11 terminology trap); it is not
    # touched, and motion graphics remain `animation_generation` to AD-01.
    MOTION_GRAPHICS = "motion_graphics"


class StageStatus(str, Enum):
    """Outcome status for a completed pipeline stage."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class FailureCategory(str, Enum):
    """Classification bucket for task failures.

    Used by the error handler to decide retry-ability.
    """

    TRANSIENT = "transient"      # Network / timeout – safe to retry
    RESOURCE = "resource"        # OOM, GPU unavailable – retry with backoff
    CONFIG = "config"            # Bad configuration – do NOT retry
    EXTERNAL = "external"        # Third-party service error


class MediaType(str, Enum):
    """Media asset types produced during the pipeline."""

    IMAGE = "image"
    VIDEO_CLIP = "video_clip"
    ANIMATION = "animation"


# ---------------------------------------------------------------------------
# Pipeline job context
# ---------------------------------------------------------------------------

class PipelineJobContext(BaseModel):
    """Top-level context dict that travels with every pipeline dispatch.

    Constructed once by the API when a job is created and passed
    through the orchestrator into each stage task.
    """

    job_id: str
    project_id: str
    project_name: str = ""
    project_description: str = ""
    target_audience: str = ""
    max_runtime_seconds: int = 600
    language_code: str = "en-US"
    priority: str = "normal"
    # ARCH-1/AD-01: which model tier (prototype vs production) this job renders.
    # Set by the API at job creation; drives get_binding's tier resolution.
    tier: str = "prototype"
    current_stage: str = ""
    resume_from_stage: Optional[str] = None

    class Config:
        extra = "allow"  # forward-compat: ignore unknown fields


# ---------------------------------------------------------------------------
# vLLM response models
# ---------------------------------------------------------------------------

class VLLMUsage(BaseModel):
    """Token usage counters returned by the vLLM /v1/chat/completions API."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class VLLMMessage(BaseModel):
    """A single message within a vLLM chat-completion choice."""

    role: str = "assistant"
    content: str = ""


class VLLMChoice(BaseModel):
    """One of the N choices in a vLLM chat-completion response."""

    index: int = 0
    message: VLLMMessage = Field(default_factory=VLLMMessage)
    finish_reason: Optional[str] = None


class VLLMResponse(BaseModel):
    """Top-level response from the vLLM /v1/chat/completions endpoint.

    Compatible with the OpenAI-style JSON returned by vLLM.
    """

    id: str = ""
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: List[VLLMChoice] = Field(default_factory=list)
    usage: Optional[VLLMUsage] = None

    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# Stage 1 – Transcript Refinement
# ---------------------------------------------------------------------------

class TranscriptRecord(BaseModel):
    """A single raw transcript segment fetched from the API."""

    id: str
    project_id: str = ""
    sequence_order: int = 0
    original_text: str = ""
    refined_text: Optional[str] = None
    language_code: str = "en-US"

    class Config:
        extra = "allow"


class RefinedTranscript(BaseModel):
    """Result of refining one transcript segment through the LLM."""

    transcript_id: str
    sequence_order: int = 0
    original_text: str = ""
    refined_text: str = ""
    language_code: str = "en-US"
    refinement_metadata: Dict[str, Any] = Field(default_factory=dict)


class TranscriptRefinementInput(BaseModel):
    """Input payload for the Stage 1 transcript-refinement Celery task."""

    job_context: PipelineJobContext
    transcripts: List[TranscriptRecord] = Field(..., min_length=1)
    system_prompt: str = ""
    user_prompt_template: str = ""


class TranscriptRefinementOutput(BaseModel):
    """Output payload returned by the Stage 1 transcript-refinement task."""

    job_id: str = ""
    project_id: str = ""
    status: StageStatus = StageStatus.SUCCESS
    refined_transcripts: List[RefinedTranscript] = Field(default_factory=list)
    total_transcripts: int = 0
    successful_count: int = 0
    failed_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    processing_time_seconds: float = 0.0
    model_used: str = ""
    idempotency_hash: str = ""
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Convenience properties used by tests and orchestrator
    # ------------------------------------------------------------------

    @property
    def stage(self) -> str:
        """Return the canonical stage name."""
        return PipelineStage.TRANSCRIPT_REFINEMENT.value

    @property
    def is_success(self) -> bool:
        return self.status == StageStatus.SUCCESS

    def to_checkpoint_data(self) -> Dict[str, Any]:
        """Serialise to a dict suitable for the checkpoint store."""
        data = self.model_dump(mode="json")
        data["stage"] = self.stage
        return data


# ---------------------------------------------------------------------------
# Stage 2 – Storyboard Generation
# ---------------------------------------------------------------------------

#: Synonyms the storyboard LLM is known to emit for a MediaType member.
#:
#: WP-53 (P2.54). This is a CLOSED table, not a guess. It exists because the
#: prompt asks for a media type in prose and the model answers in prose --
#: "video", not "video_clip". Anything not in the enum and not in this table is
#: REJECTED, loudly, at Stage 2. That is the WP-46 rule: a receiver rejects, it
#: does not infer. An open-ended normaliser (strip, lowercase, startswith,
#: fuzzy-match) would be inference, and inference is what produced the defect
#: below in the first place.
MEDIA_TYPE_SYNONYMS: dict[str, str] = {
    "video": MediaType.VIDEO_CLIP.value,
    "video_clip": MediaType.VIDEO_CLIP.value,
    "animated": MediaType.ANIMATION.value,
    "animation": MediaType.ANIMATION.value,
    "image": MediaType.IMAGE.value,
    "still": MediaType.IMAGE.value,
}


class StoryboardScene(BaseModel):
    """One scene produced by the storyboard-generation LLM pass.

    WP-53 (P2.54). ``media_type`` was a bare ``str`` with no coercion and no
    validation, and ``duration_seconds`` a bare ``float`` with no bound.

    The bare string was not cosmetic. ``stage3_images.py`` branches on
    ``scene.media_type == MediaType.VIDEO_CLIP.value``, so a Stage 2 output of
    ``"video"`` -- which is what the LLM actually writes -- fell through to the
    ELSE branch and the scene was rendered as a still image. No exception, no
    warning, no failed job: a video scene silently became a picture, and the
    only way to find out was to watch the finished render.

    ``use_enum_values`` is deliberate. The field VALIDATES against ``MediaType``
    but STORES the plain string, so every existing consumer -- the
    ``temporal_pipeline.payloads`` mirror that declares ``media_type: str``,
    the ``Counter`` in ``client.py:94``, the ``== "image"`` in
    ``stage8_final_render.py:419``, and anything that interpolates the value
    into a path or a log line -- sees exactly what it saw before. The gain is
    the rejection; nothing downstream has to change to collect it.
    """

    scene_index: int = 0
    narration_text: str = ""
    visual_description: str = ""
    media_type: MediaType = MediaType.IMAGE
    # gt=0: a negative or zero-length scene is not a scene. Stage 2's own
    # clamp already keeps generated values in [3, 120]; this catches every
    # OTHER construction path, which is where a -1 would actually arrive from.
    duration_seconds: float = Field(default=10.0, gt=0)
    scene_title: Optional[str] = None
    transition: Optional[str] = None
    notes: Optional[str] = None

    # validate_default: without it `use_enum_values` applies only to values that
    # were VALIDATED, so `StoryboardScene()` stored the enum MEMBER while
    # `StoryboardScene(media_type="image")` stored the string -- the same field
    # holding two different types depending on how the object was built.
    model_config = ConfigDict(
        extra="allow", use_enum_values=True, validate_default=True
    )

    @field_validator("media_type", mode="before")
    @classmethod
    def _canonicalise_media_type(cls, v: Any) -> Any:
        """Map a known synonym onto its MediaType value; leave the rest alone.

        Leaving an unknown value alone is the point -- enum validation then
        rejects it with the offending value in the message, which is a better
        error than anything this hook could raise itself.
        """
        if isinstance(v, str):
            return MEDIA_TYPE_SYNONYMS.get(v.strip().lower(), v)
        return v


class StoryboardGenerationInput(BaseModel):
    """Input payload for the Stage 2 storyboard-generation Celery task."""

    job_context: PipelineJobContext
    refined_transcripts: List[RefinedTranscript] = Field(default_factory=list)
    system_prompt: str = ""
    user_prompt_template: str = ""
    target_scene_count: int = 0


class StoryboardGenerationOutput(BaseModel):
    """Output payload returned by the Stage 2 storyboard-generation task."""

    job_id: str = ""
    project_id: str = ""
    status: StageStatus = StageStatus.SUCCESS
    scenes: List[StoryboardScene] = Field(default_factory=list)
    total_scenes: int = 0
    total_duration_seconds: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    processing_time_seconds: float = 0.0
    model_used: str = ""
    idempotency_hash: str = ""
    scene_ids: List[str] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    completed_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def stage(self) -> str:
        return PipelineStage.STORYBOARD_GENERATION.value

    @property
    def is_success(self) -> bool:
        return self.status == StageStatus.SUCCESS

    def to_checkpoint_data(self) -> Dict[str, Any]:
        data = self.model_dump(mode="json")
        data["stage"] = self.stage
        return data


# ---------------------------------------------------------------------------
# Error detail
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """Structured error record created by the error handler.

    Stored in the dead-letter queue and attached to failed job records.
    """

    task_name: str = ""
    task_id: str = ""
    exception_type: str = ""
    exception_message: str = ""
    traceback: str = ""
    failure_category: FailureCategory = FailureCategory.TRANSIENT
    retry_count: int = 0
    max_retries: int = 0
    job_id: str = ""
    project_id: str = ""
    stage: Optional[str] = None
    args: Optional[List[Any]] = None
    kwargs: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    node_hostname: str = ""
    worker_id: str = ""

    class Config:
        extra = "allow"

    def to_dlq_payload(self) -> Dict[str, Any]:
        """The dead-letter record, in the shape `dead_letter_messages` holds.

        ⛔ THIS METHOD DID NOT EXIST, AND ITS ONLY CALLER HAS ALWAYS CALLED IT.
        `utils/error_handler.py:295` does `error_detail.to_dlq_payload()`, which
        raised `AttributeError: 'ErrorDetail' object has no attribute
        'to_dlq_payload'` -- caught by the bare `except` around the HTTP call and
        logged `dlq_routing_failed` at CRITICAL. Every dead-letter routing
        attempt has died here, before the request was ever built. Measured four
        times on project 9c29b1d1's stage-7 failures alone, 2026-08-28.

        Keys are the table's own columns (`dead_letter_messages`), so the
        payload cannot drift from the thing it is meant to become. `task_args`
        is added by the caller, which is the only field it knows and this
        does not.

        ⚠ FIXING THIS DOES NOT MAKE DLQ ROUTING WORK, and saying so is the
        point. There is no `POST /api/v1/dlq/messages` route and no create
        method on `DLQService` -- the whole write side is absent, and
        `dead_letter_messages` has never held a row. What this changes is the
        failure: a CRITICAL `AttributeError` becomes a `dlq_routing_api_error`
        naming a missing endpoint, which is the true state.
        """
        return {
            "task_name": self.task_name,
            "task_kwargs": self.kwargs or {},
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "traceback": self.traceback,
            "failure_category": self.failure_category.value,
            "retry_count_exhausted": self.retry_count,
            # Not columns of `dead_letter_messages`, and sent anyway: they are
            # what an operator needs to find the run this record belongs to, and
            # the ingest that does not yet exist will want them.
            "task_id": self.task_id,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "stage": self.stage,
            "max_retries": self.max_retries,
            "node_hostname": self.node_hostname,
            "worker_id": self.worker_id,
            "occurred_at": (
                self.occurred_at.isoformat() if self.occurred_at else None
            ),
        }
