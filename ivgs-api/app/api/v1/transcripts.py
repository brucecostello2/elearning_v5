"""
Transcript API endpoints per §5.1.3.

Endpoints:
- GET    /api/v1/projects/{id}/transcripts          — List transcripts
- POST   /api/v1/projects/{id}/transcripts/upload   — Upload transcript files
- PATCH  /api/v1/projects/{id}/transcripts/{tid}    — Update transcript
- POST   /api/v1/projects/{id}/transcripts/reorder  — Bulk reorder
- DELETE /api/v1/projects/{id}/transcripts/{tid}    — Delete transcript
"""
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user, is_service_principal
from app.core.rbac import require_operator_or_admin
from app.models.user import User
from app.schemas.transcript import (
    TranscriptResponse,
    TranscriptUpdate,
    TranscriptReorderRequest,
)
from app.services.transcript_service import TranscriptService
from app.core.auth import get_service_or_user
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/transcripts", tags=["Transcripts"])


@router.get("", response_model=List[TranscriptResponse], summary="List transcripts")
async def list_transcripts(
    project_id: UUID,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """List transcripts ordered by sequence_order."""
    # Verify project access
    project_service = ProjectService(db)
    project = await project_service.get_project(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )

    service = TranscriptService(db)
    transcripts = await service.list_transcripts(project_id)
    return [TranscriptResponse.model_validate(t) for t in transcripts]


@router.post(
    "/upload",
    response_model=List[TranscriptResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload transcript files",
)
async def upload_transcripts(
    project_id: UUID,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """
    Upload transcript files (PDF/DOCX/TXT, multipart). Text extracted server-side.

    Accepts multiple files in a single request.
    """
    # Verify project access
    project_service = ProjectService(db)
    project = await project_service.get_project(project_id, current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project {project_id} not found"}},
        )

    # Validate file types
    allowed_types = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    for f in files:
        if f.content_type and f.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"Invalid file type '{f.content_type}' for '{f.filename}'. Allowed: PDF, DOCX, TXT",
                    }
                },
            )

    service = TranscriptService(db)
    transcripts = await service.upload_transcripts(
        project_id=project_id,
        files=files,
        current_username=current_user.username,
    )
    return [TranscriptResponse.model_validate(t) for t in transcripts]


@router.patch(
    "/{transcript_id}",
    response_model=TranscriptResponse,
    summary="Update transcript",
)
async def update_transcript(
    project_id: UUID,
    transcript_id: UUID,
    data: TranscriptUpdate,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """Update refined_text inline or reorder sequence_order.

    ⛔ RC-Q15. `by_service` tells the service WHO is writing, and it changes what
    happens to `refined_text` on an uploaded script. Stage 1's callback carries a
    service token and its `refined_text` is the model's echo of a script the
    database already holds — that echo is discarded and `source_text` is written
    instead (`TranscriptService.update_transcript` carries the measurement). A
    real user on this same route is editing deliberately and is honoured.

    ⚠ The test is the AUTHENTICATED PRINCIPAL, not a flag the caller can set.
    `get_service_or_user` already distinguishes them, so a worker cannot present
    itself as a person to keep its paraphrase.
    """
    service = TranscriptService(db)
    transcript = await service.update_transcript(
        project_id=project_id,
        transcript_id=transcript_id,
        refined_text=data.refined_text,
        sequence_order=data.sequence_order,
        language_code=data.language_code,
        by_service=is_service_principal(current_user),
    )
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Transcript {transcript_id} not found"}},
        )
    return TranscriptResponse.model_validate(transcript)


@router.post("/reorder", response_model=List[TranscriptResponse], summary="Bulk reorder transcripts")
async def reorder_transcripts(
    project_id: UUID,
    data: TranscriptReorderRequest,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Bulk reorder. Body: [{id, sequence_order}]."""
    service = TranscriptService(db)
    try:
        transcripts = await service.reorder_transcripts(project_id, data.items)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )
    return [TranscriptResponse.model_validate(t) for t in transcripts]


@router.delete(
    "/{transcript_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete transcript",
)
async def delete_transcript(
    project_id: UUID,
    transcript_id: UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_session),
):
    """Remove transcript from project."""
    service = TranscriptService(db)
    deleted = await service.delete_transcript(project_id, transcript_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Transcript {transcript_id} not found"}},
        )
