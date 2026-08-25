"""
Prompt API endpoints per §5.1.6 and §9.

Endpoints:
- GET    /api/v1/prompts                            — List global prompts
- POST   /api/v1/prompts                            — Create global prompt version
- POST   /api/v1/prompts/test                       — Prompt Playground
- GET    /api/v1/prompts/resolve                    — Resolve effective prompt
- PUT    /api/v1/prompts/{id}                       — Update prompt
- DELETE /api/v1/prompts/{id}                       — Delete prompt
- GET    /api/v1/prompts/{id}/versions              — Version history
- POST   /api/v1/prompts/{id}/restore               — Restore previous version
- POST   /api/v1/prompts/{id}/rollback              — Rollback (alias for restore)
- GET    /api/v1/prompts/library                    — List library prompts
- DELETE /api/v1/prompts/library/{id}               — Remove from library
- POST   /api/v1/playground/execute                 — Execute playground
- POST   /api/v1/playground/save                    — Save playground result
- GET    /api/v1/projects/{id}/prompts              — List project prompts with effective source
- POST   /api/v1/projects/{id}/prompts              — Create project-level override
- POST   /api/v1/projects/{id}/scenes/{sid}/prompts — Create scene-level override
"""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import (
    require_admin,
    require_operator_or_admin,
    require_service_or_privileged_user,
)
from app.models.user import User
from app.schemas.prompt import (
    PromptCreate,
    PromptUpdate,
    PromptResponse,
    PromptVersionHistory,
    PromptTestRequest,
    PromptTestResponse,
    EffectivePrompt,
)
from app.services.llm_playground import PlaygroundError
from app.services.prompt_service import PromptService

logger = logging.getLogger(__name__)

global_router = APIRouter(prefix="/prompts", tags=["Prompts"])
library_router = APIRouter(prefix="/prompts/library", tags=["Prompt Library"])
playground_router = APIRouter(prefix="/playground", tags=["Playground"])
project_prompt_router = APIRouter(prefix="/projects/{project_id}/prompts", tags=["Prompts"])
scene_prompt_router = APIRouter(
    prefix="/projects/{project_id}/scenes/{scene_id}/prompts",
    tags=["Prompts"],
)


# --- Global prompt endpoints ---

@global_router.get(
    "",
    response_model=List[PromptResponse],
    summary="List global prompts",
)
async def list_global_prompts(
    prompt_type: Optional[str] = Query(default=None, description="Filter by prompt type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List global prompts. Supports ?prompt_type= filter."""
    service = PromptService(db)
    prompts = await service.list_global_prompts(prompt_type)
    return [
        PromptResponse(
            id=p.id,
            project_id=p.project_id,
            scene_id=p.scene_id,
            prompt_type=p.prompt_type,
            prompt_text=p.prompt_text,
            version=p.version,
            is_active=p.is_active,
            scope=p.scope,
            created_by=p.created_by,
            created_at=p.created_at,
            change_note=p.change_note,
        )
        for p in prompts
    ]


@global_router.post(
    "",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create global prompt version",
)
async def create_global_prompt(
    data: PromptCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create new global prompt version. Body: {prompt_type, prompt_text, change_note}."""
    service = PromptService(db)
    prompt = await service.create_prompt(
        prompt_type=data.prompt_type,
        prompt_text=data.prompt_text,
        change_note=data.change_note,
        created_by=current_user.username,
    )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )


@global_router.post(
    "/{prompt_id}/restore",
    response_model=PromptResponse,
    summary="Restore previous prompt version",
)
async def restore_prompt_version(
    prompt_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Restore a previous version (set is_active = true for that version)."""
    service = PromptService(db)
    prompt = await service.restore_version(prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Prompt {prompt_id} not found"}},
        )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )


@global_router.post(
    "/test",
    response_model=PromptTestResponse,
    summary="Prompt Playground",
)
async def test_prompt(
    data: PromptTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Prompt Playground: send prompt to selected self-hosted model.

    Body: {prompt_text, model_id, parameters, template_variables}
    """
    service = PromptService(db)
    try:
        result = await service.test_prompt(
            prompt_text=data.prompt_text,
            model_id=data.model_id,
            parameters=data.parameters,
            template_variables=data.template_variables,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    except PlaygroundError as e:
        # WP-45 Task 3: the model was not reached, or refused. Said plainly,
        # with the server's own message, instead of returning a well-formed
        # 200 whose model_response is a sentence nobody generated.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "MODEL_UNAVAILABLE", "message": str(e)}},
        )
    return PromptTestResponse(**result)


@global_router.get(
    "/resolve",
    response_model=EffectivePrompt,
    summary="Resolve effective prompt",
)
async def resolve_prompt(
    prompt_type: str = Query(..., description="Prompt type to resolve"),
    project_id: Optional[UUID] = Query(default=None, description="Project ID"),
    scene_id: Optional[UUID] = Query(default=None, description="Scene ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Resolve the effective prompt for a given type, walking SCENE → PROJECT → GLOBAL."""
    service = PromptService(db)
    result = await service.resolve_single_prompt(prompt_type, project_id, scene_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"No prompt found for type '{prompt_type}'"}},
        )
    return result


# --- Parameterised prompt endpoints (MUST come after /test, /resolve) ---

@global_router.put(
    "/{prompt_id}",
    response_model=PromptResponse,
    summary="Update prompt",
)
async def update_prompt(
    prompt_id: UUID,
    data: PromptUpdate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update prompt text and/or change note."""
    service = PromptService(db)
    prompt = await service.update_prompt(
        prompt_id=prompt_id,
        prompt_text=data.prompt_text,
        change_note=data.change_note,
        updated_by=current_user.username,
    )
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Prompt {prompt_id} not found"}},
        )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )


@global_router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete prompt",
)
async def delete_prompt(
    prompt_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Soft-delete a prompt (set is_active = false)."""
    service = PromptService(db)
    success = await service.delete_prompt(prompt_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Prompt {prompt_id} not found"}},
        )
    return None


@global_router.get(
    "/{prompt_id}/versions",
    response_model=List[PromptVersionHistory],
    summary="Version history",
)
async def get_version_history(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get version history for a prompt type starting from the given prompt."""
    service = PromptService(db)
    prompt = await service.get_prompt_by_id(prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Prompt {prompt_id} not found"}},
        )
    versions = await service.get_version_history(
        prompt_type=prompt.prompt_type,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
    )
    return versions


@global_router.post(
    "/{prompt_id}/rollback",
    response_model=PromptResponse,
    summary="Rollback to previous version",
)
async def rollback_prompt_version(
    prompt_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Rollback to a previous version (alias for restore)."""
    service = PromptService(db)
    prompt = await service.restore_version(prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Prompt {prompt_id} not found"}},
        )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )


# --- Library endpoints ---

@library_router.get(
    "",
    response_model=List[PromptResponse],
    summary="List library prompts",
)
async def list_library_prompts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all prompts marked as library templates."""
    service = PromptService(db)
    prompts = await service.list_library_prompts()
    return [
        PromptResponse(
            id=p.id,
            project_id=p.project_id,
            scene_id=p.scene_id,
            prompt_type=p.prompt_type,
            prompt_text=p.prompt_text,
            version=p.version,
            is_active=p.is_active,
            scope=p.scope,
            created_by=p.created_by,
            created_at=p.created_at,
            change_note=p.change_note,
        )
        for p in prompts
    ]


@library_router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove from library",
)
async def remove_from_library(
    prompt_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Remove a prompt from the library (unset is_library_template)."""
    service = PromptService(db)
    success = await service.remove_from_library(prompt_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Prompt {prompt_id} not found"}},
        )
    return None


# --- Playground endpoints ---

@playground_router.post(
    "/execute",
    response_model=PromptTestResponse,
    summary="Execute prompt in playground",
)
async def playground_execute(
    data: PromptTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Execute a prompt in the playground (alias for /prompts/test)."""
    service = PromptService(db)
    try:
        result = await service.test_prompt(
            prompt_text=data.prompt_text,
            model_id=data.model_id,
            parameters=data.parameters,
            template_variables=data.template_variables,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    except PlaygroundError as e:
        # WP-45 Task 3: the model was not reached, or refused. Said plainly,
        # with the server's own message, instead of returning a well-formed
        # 200 whose model_response is a sentence nobody generated.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "MODEL_UNAVAILABLE", "message": str(e)}},
        )
    return PromptTestResponse(**result)


@playground_router.post(
    "/save",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save playground result as prompt",
)
async def playground_save(
    data: PromptCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Save a playground result as a new prompt version."""
    service = PromptService(db)
    prompt = await service.create_prompt(
        prompt_type=data.prompt_type,
        prompt_text=data.prompt_text,
        change_note=data.change_note or "Saved from playground",
        created_by=current_user.username,
    )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )


# --- Project-level prompt endpoints ---

@project_prompt_router.get(
    "",
    response_model=List[EffectivePrompt],
    summary="List project prompts with effective source",
)
async def list_project_prompts(
    project_id: UUID,
    prompt_type: Optional[str] = Query(
        default=None,
        description=(
            "Return only this prompt type. Callers that need one type MUST "
            "pass it: the unfiltered response is all ten types in enum order."
        ),
    ),
    # WP-37, and the same defect class WP-36 fixed on the checkpoint route.
    # This is the route the WORKER reads its prompts from - stage 1
    # (stage1_transcript.py:275) and stage 2 (stage2_storyboard.py:161) both GET
    # it with the internal service token. get_current_user rejects that token
    # outright with 401, so every attempt fell back to the baked-in .j2
    # templates and the DB-managed prompts were never used by anything. The
    # pipeline ran, so nothing looked broken - it just silently ignored the
    # prompt-management feature entirely.
    #
    # require_service_or_privileged_user (rbac.py:88) accepts the service token
    # (resolving to the seeded svc-pipeline admin) or an operator/admin human,
    # and still denies viewers 403.
    #
    # Read-only, and the ONLY prompt route widened. Every write and admin route
    # in this file keeps require_operator_or_admin / require_admin - no worker
    # writes prompts, and tests pin that they still refuse the service token.
    current_user: User = Depends(require_service_or_privileged_user),
    db: AsyncSession = Depends(get_session),
):
    """List project-level prompts with effective source (SCENE/PROJECT/GLOBAL).

    IVGS-0.4: the workers have always sent ``?prompt_type=...`` and this
    endpoint has always ignored it, returning all ten types. The worker then
    picked one by substring, and the last enum member — TRANSLATION — won.
    The filter is now honoured, and an unknown type is a 400 rather than an
    empty list that a caller could mistake for "not configured".
    """
    if prompt_type is not None:
        from shared.models.enums import PromptType

        valid = {pt.value for pt in PromptType}
        if prompt_type not in valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": (
                            f"Unknown prompt_type '{prompt_type}'. "
                            f"Allowed: {', '.join(sorted(valid))}"
                        ),
                    }
                },
            )

    service = PromptService(db)
    effective = await service.resolve_effective_prompts(project_id)
    if prompt_type is not None:
        effective = [p for p in effective if p.prompt_type == prompt_type]
    return effective


@project_prompt_router.post(
    "",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create project-level prompt override",
)
async def create_project_prompt(
    project_id: UUID,
    data: PromptCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create project-level override."""
    service = PromptService(db)
    prompt = await service.create_prompt(
        prompt_type=data.prompt_type,
        prompt_text=data.prompt_text,
        change_note=data.change_note,
        created_by=current_user.username,
        project_id=project_id,
    )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )


# --- Scene-level prompt endpoints ---

@scene_prompt_router.post(
    "",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create scene-level prompt override",
)
async def create_scene_prompt(
    project_id: UUID,
    scene_id: UUID,
    data: PromptCreate,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create scene-level override."""
    service = PromptService(db)
    prompt = await service.create_prompt(
        prompt_type=data.prompt_type,
        prompt_text=data.prompt_text,
        change_note=data.change_note,
        created_by=current_user.username,
        project_id=project_id,
        scene_id=scene_id,
    )
    return PromptResponse(
        id=prompt.id,
        project_id=prompt.project_id,
        scene_id=prompt.scene_id,
        prompt_type=prompt.prompt_type,
        prompt_text=prompt.prompt_text,
        version=prompt.version,
        is_active=prompt.is_active,
        scope=prompt.scope,
        created_by=prompt.created_by,
        created_at=prompt.created_at,
        change_note=prompt.change_note,
    )
