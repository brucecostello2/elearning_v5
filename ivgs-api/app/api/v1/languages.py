"""
Language variant API endpoints per §5.1.8.

Endpoints:
- GET    /api/v1/projects/{id}/languages               — List variants
- POST   /api/v1/projects/{id}/languages               — Add localization target
- POST   /api/v1/projects/{id}/languages/{lid}/retry   — Retry failed localization
- POST   /api/v1/projects/{id}/languages/{lid}/translate — Translate the source
                                                           narration (WP-61)
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
from app.services.translation_service import (
    TranslationContractError,
    TranslationError,
    TranslationService,
)

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


@router.post(
    "/{variant_id}/translate",
    response_model=LanguageVariantResponse,
    summary="Translate the source narration into this variant's language",
)
async def translate_variant(
    project_id: UUID,
    variant_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Translate every scene of this project into the variant's language.

    WP-61 Task 3. **This is the first translation path IVGS has ever had.**
    Before it, `prompts.prompt_type='translation'` held one row that nothing
    rendered, `language_variants` held 16 rows all `pending`, and
    `/retry` re-rendered the SOURCE narration with the target language's voice
    and said so in its own docstring.

    **It is deliberately NOT a pipeline stage.** Task 3(a) rules that where the
    executing body is absent, no new stage body is written pre-cutover. This is
    a synchronous API-side call — the same shape as the CLIP scorer proxy — and
    it registers no Celery task and appears in no `STAGE_TASK_MAP`. After the
    M3.3 Temporal cutover the translation activity calls
    `TranslationService.translate_variant`; it does not reimplement it.

    **The contract is fail-and-flag** (Task 3(c), ruled). The model is
    instructed to translate faithfully and never to correct the source, and to
    emit one `IVGS-TRANSLATION-FLAG:` line if it believes the source is wrong.
    That line is stripped from the deliverable and the variant goes to
    `flagged` instead of `complete`. The route answers 409 rather than
    translating at all if the active prompt does not carry that contract:
    under the old prompt the model corrected the source silently and inline, in
    all four languages, and this path would have recorded the corrected text as
    `complete`.
    """
    service = TranslationService(db)
    try:
        variant = await service.translate_variant(project_id, variant_id)
    except TranslationContractError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "TRANSLATION_CONTRACT_MISSING",
                    "message": str(e),
                }
            },
        )
    except TranslationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "TRANSLATION_FAILED", "message": str(e)}},
        )
    if variant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Language variant {variant_id} not found",
                }
            },
        )
    return LanguageVariantResponse.model_validate(variant)
