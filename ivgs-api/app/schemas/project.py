"""
Project Pydantic schemas per §5.1.2 and Appendix C.3.

Includes: ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    """Schema for POST /api/v1/projects."""

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Video title",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Short description for dashboard display",
    )
    max_runtime_seconds: Optional[int] = Field(
        default=None,
        ge=60,
        le=7200,
        description="Target maximum video runtime (60–7200 seconds)",
    )
    target_languages: Optional[List[str]] = Field(
        default=None,
        description="List of BCP-47 language codes for localization",
    )
    # WP-64 Task 6(a). Longer than `description` on purpose: `description` is a
    # dashboard blurb capped at 1000 and this is several outcome statements the
    # model reasons from. Capped so a paste of an entire syllabus fails at the
    # API with a message rather than silently consuming the prompt budget.
    learning_outcomes: Optional[str] = Field(
        default=None,
        max_length=4000,
        description=(
            "What the viewer should be able to DO after watching. Free text, one statement or several. Fed to storyboard generation as RULE 0: the scene mix and each scene's visual are judged against it. Editing it after a storyboard exists feeds the NEXT run and does not rewrite existing scenes."
        ),
    )

    @field_validator("target_languages")
    @classmethod
    def validate_languages(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            allowed = {"en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "zh-CN", "ja-JP", "ar-SA"}
            for lang in v:
                if lang not in allowed:
                    raise ValueError(
                        f"Invalid language code '{lang}'. "
                        f"Allowed: {', '.join(sorted(allowed))}"
                    )
        return v


class ProjectUpdate(BaseModel):
    """Schema for PATCH /api/v1/projects/{id}."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    max_runtime_seconds: Optional[int] = Field(default=None, ge=60, le=7200)
    # WP-64 Task 6(b): editable after creation. Not retroactive -- see the
    # column docstring and the notice the Overview panel renders beside it.
    learning_outcomes: Optional[str] = Field(
        default=None,
        max_length=4000,
        description=(
            "What the viewer should be able to DO after watching. Free text, one statement or several. Fed to storyboard generation as RULE 0: the scene mix and each scene's visual are judged against it. Editing it after a storyboard exists feeds the NEXT run and does not rewrite existing scenes."
        ),
    )


class ActiveJobInfo(BaseModel):
    """Embedded active job summary in project response (C.3)."""

    id: UUID
    job_type: str
    status: str
    started_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LanguageVariantSummary(BaseModel):
    """Embedded language variant summary in project response (C.3)."""

    language_code: str
    state: str

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    """
    Project response per Appendix C.3.

    Includes computed fields: scene_count, total_duration_estimate_seconds,
    hero_image_url, active_job, language_variants.
    """

    id: UUID
    name: str
    description: Optional[str] = None
    # WP-64 Task 6. Returned so the Overview panel can show it and the editor
    # can seed its textarea from the same value the storyboard run will read.
    learning_outcomes: Optional[str] = None
    max_runtime_seconds: Optional[int] = None
    state: str
    hero_image_url: Optional[str] = None
    # WP-57 Task 1. An ASSET ID, not a URL, because the media routes are
    # token-guarded and a browser cannot attach a Bearer header to an `<img
    # src>`. The card fetches it through `apiClient.blob()` against
    # `/assets/{id}/thumbnail?w=`. NULL means "this project has no renderable
    # asset yet" — a real answer the card must render as words, not as an icon
    # indistinguishable from a broken image.
    thumbnail_asset_id: Optional[UUID] = None
    # WP-60 Task 4. Why there is no thumbnail, when there is none. The card
    # rendered "Preview failed to load" for a video-only project, a project with
    # nothing rendered, and a genuine transport failure alike — three different
    # facts and one sentence. Null whenever `thumbnail_asset_id` is set.
    thumbnail_unavailable_reason: Optional[str] = None
    scene_count: int = 0
    total_duration_estimate_seconds: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    language_variants: List[LanguageVariantSummary] = []
    active_job: Optional[ActiveJobInfo] = None
    created_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)
