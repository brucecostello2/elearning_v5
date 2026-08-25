"""
Language variant Pydantic schemas per §5.1.8.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


SUPPORTED_LANGUAGES = {"en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "zh-CN", "ja-JP", "ar-SA"}


class LanguageVariantCreate(BaseModel):
    """Schema for POST /api/v1/projects/{id}/languages."""

    language_code: str = Field(max_length=10, description="BCP-47 language code")
    translation_prompt_override: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="Optional override for the translation prompt",
    )

    @field_validator("language_code")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language code '{v}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )
        return v


class LanguageVariantResponse(BaseModel):
    """Response schema for a language variant.

    WP-45 Task 6(c) / WP-43 D-1, RULED derive. The Languages tab read
    ``variant.progress_percent || 0`` over a field the API had never sent, so an
    absent measurement rendered as a confident 0% beside a language with a
    finished 720p draft on disk. WP-43 replaced that with "not tracked yet" and
    recorded the backend gap; this is the gap closed.

    The figure is DERIVED, on every request, from the ``pipeline_checkpoints``
    of the newest job attributed to this variant. It is not a column, and it is
    deliberately not one: a separately-written progress column can disagree with
    what actually ran, and this system has already been bitten by exactly that
    class of drift. ``progress_source`` names where the number came from so a
    reader is never left guessing what it measures.

    ``progress_percent`` is ``None`` — never 0 — when there is nothing to
    measure. Zero means "measured, and nothing has completed".
    """

    id: UUID
    project_id: UUID
    language_code: str
    state: str
    final_render_1080p_id: Optional[UUID] = None
    final_render_4k_id: Optional[UUID] = None
    progress_percent: Optional[float] = None
    completed_stages: Optional[int] = None
    total_stages: Optional[int] = None
    progress_source: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
