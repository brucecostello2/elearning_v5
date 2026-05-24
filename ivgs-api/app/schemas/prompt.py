"""
Prompt Pydantic schemas per §5.1.6 and §9.

Includes: PromptCreate, PromptUpdate, PromptResponse, PromptTestRequest,
PromptTestResponse, PromptRenderRequest.
"""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


VALID_PROMPT_TYPES = {
    "master", "transcript_refinement", "storyboard_generation",
    "image_generation", "video_generation", "animation_generation",
    "tts_voice", "talking_head", "composition", "translation",
}


class PromptCreate(BaseModel):
    """
    Schema for creating a new prompt version.

    Used for:
    - POST /api/v1/prompts (global)
    - POST /api/v1/projects/{id}/prompts (project-level)
    - POST /api/v1/projects/{id}/scenes/{sid}/prompts (scene-level)
    """

    prompt_type: str = Field(description="One of the 10 prompt types per §9.2")
    prompt_text: str = Field(min_length=1, max_length=50000, description="Full Jinja2 prompt content")
    change_note: str = Field(
        min_length=1,
        max_length=500,
        description="Required description of changes",
    )

    @field_validator("prompt_type")
    @classmethod
    def validate_prompt_type(cls, v: str) -> str:
        if v not in VALID_PROMPT_TYPES:
            raise ValueError(
                f"Invalid prompt_type '{v}'. Must be one of: {', '.join(sorted(VALID_PROMPT_TYPES))}"
            )
        return v


class PromptUpdate(BaseModel):
    """
    Schema for updating a prompt (creating new version per §9.3).

    Separate from PromptCreate because prompt_type is determined by the
    existing prompt being updated, not by the caller.

    Used for:
    - PUT /api/v1/prompts/{id}
    """

    prompt_text: str = Field(
        min_length=1,
        max_length=50000,
        description="Updated Jinja2 prompt content",
    )
    change_note: str = Field(
        min_length=1,
        max_length=500,
        description="Required description of changes",
    )


class PromptResponse(BaseModel):
    """Full prompt response with scope and version info."""

    id: UUID
    project_id: Optional[UUID] = None
    scene_id: Optional[UUID] = None
    prompt_type: str
    prompt_text: str
    version: int
    is_active: bool
    scope: str  # "GLOBAL", "PROJECT", "SCENE"
    created_by: Optional[str] = None
    created_at: datetime
    change_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PromptVersionHistory(BaseModel):
    """Prompt version for version history listing (includes text for diff)."""

    id: UUID
    version: int
    prompt_text: str
    is_active: bool
    created_by: Optional[str] = None
    created_at: datetime
    change_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EffectivePrompt(BaseModel):
    """
    Resolved effective prompt showing source tier.

    Used in GET /api/v1/projects/{id}/prompts to show which tier each
    prompt_type resolves to.
    """

    prompt_type: str
    prompt_id: UUID
    prompt_text: str
    version: int
    source: str  # "GLOBAL", "PROJECT", "SCENE"
    scene_id: Optional[UUID] = None


class PromptTestRequest(BaseModel):
    """
    Schema for POST /api/v1/prompts/test — Prompt Playground.

    Sends prompt to a selected self-hosted model for testing.
    """

    prompt_text: str = Field(min_length=1, max_length=50000)
    model_id: str = Field(
        default="llama-3.3-70b",
        description="Self-hosted model identifier",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Model parameters: temperature, max_tokens, top_p",
    )
    template_variables: Optional[Dict[str, str]] = Field(
        default=None,
        description="Jinja2 template variable values for rendering before sending",
    )


class PromptTestResponse(BaseModel):
    """Response from Prompt Playground test."""

    rendered_prompt: str
    model_id: str
    model_response: str
    usage: Optional[Dict[str, Any]] = None


class PromptRenderRequest(BaseModel):
    """
    Request to render a Jinja2 prompt template with provided variables.

    Variables available per §9.4:
    project_title, project_description, target_audience, scene_number,
    scene_title, narration_text, visual_description, target_language,
    max_duration_seconds, total_runtime_seconds
    """

    prompt_text: str = Field(min_length=1)
    variables: Dict[str, str] = Field(default_factory=dict)
