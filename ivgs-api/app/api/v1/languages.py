"""
Language variant API endpoints per §5.1.8.

Endpoints:
- GET    /api/v1/projects/{id}/languages               — List variants
- POST   /api/v1/projects/{id}/languages               — Add localization target
- POST   /api/v1/projects/{id}/languages/{lid}/retry   — Retry failed localization
"""
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.language_variant import LanguageVariantCreate, LanguageVariantResponse
from app.schemas.render_job import JobResponse
from app.services.language_service import LanguageService, LocalisationDispatchError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/languages", tags=["Languages"])


@router.get("", response_model=List[LanguageVariantResponse], summary="List language variants")
async def list_variants(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List language variants with status badges and derived progress.

    WP-45 Task 6(c): ``progress_percent`` is computed here from each variant's
    own pipeline checkpoints, on every request. It is null - never 0 - when
    there is nothing to measure, because "no run yet" and "a run that has
    completed nothing" are different facts, and rendering the first as 0% is the
    defect WP-43 §3.3 found beside a language with a finished draft on disk.
    """
    service = LanguageService(db)
    out: List[LanguageVariantResponse] = []
    for variant, progress in await service.variants_with_progress(project_id):
        response = LanguageVariantResponse.model_validate(variant)
        response.progress_percent = progress["progress_percent"]
        response.completed_stages = progress["completed_stages"]
        response.total_stages = progress["total_stages"]
        response.progress_source = progress["progress_source"]
        out.append(response)
    return out


@router.post(
    "",
    response_model=LanguageVariantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add localization target",
)
async def create_variant(
    project_id: UUID,
    data: LanguageVariantCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Add localization target. Body: {language_code, translation_prompt_override?}."""
    service = LanguageService(db)
    try:
        variant = await service.create_variant(
            project_id=project_id,
            language_code=data.language_code,
            translation_prompt_override=data.translation_prompt_override,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    return LanguageVariantResponse.model_validate(variant)


@router.post(
    "/{variant_id}/retry",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed localization",
)
async def retry_variant(
    project_id: UUID,
    variant_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Retry a failed localization by re-running the back half in that language.

    WP-45 Task 3, site 5. This used to reset the variant to ``pending``, insert
    a ``localisation`` job row and dispatch nothing - the stub named
    ``pipeline.localise``, a task that is not registered anywhere in the fleet.

    **Honest scope:** IVGS has no translation stage. The retry re-runs TTS,
    talking head, draft and final render with the variant's ``language_code``,
    so the target language's voice is used - but the scene narration is stored
    once, in the source language, and nothing translates it. Recorded as a gap
    rather than implied to be closed.
    """
    service = LanguageService(db)
    try:
        job = await service.retry_variant(project_id, variant_id)
    except LocalisationDispatchError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "DISPATCH_FAILED", "message": str(e)}},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "INVALID_STATE_TRANSITION", "message": str(e)}},
        )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Language variant {variant_id} not found"}},
        )
    return JobResponse.model_validate(job)
