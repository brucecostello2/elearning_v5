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
    """Response schema for a language variant."""

    id: UUID
    project_id: UUID
    language_code: str
    state: str
    final_render_1080p_id: Optional[UUID] = None
    final_render_4k_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
