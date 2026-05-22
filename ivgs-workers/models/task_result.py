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

from pydantic import BaseModel, Field


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

class StoryboardScene(BaseModel):
    """One scene produced by the storyboard-generation LLM pass."""

    scene_index: int = 0
    narration_text: str = ""
    visual_description: str = ""
    media_type: str = "image"
    duration_seconds: float = 10.0
    scene_title: Optional[str] = None
    transition: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        extra = "allow"


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
