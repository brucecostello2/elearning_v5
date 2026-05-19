"""
Quality Assurance API endpoints per §5.2.3.

Endpoints:
- GET    /api/v1/jobs/{id}/quality                 — All quality scores for a job
- GET    /api/v1/quality/flagged                   — Assets needing human review
- POST   /api/v1/quality/{score_id}/approve        — Approve flagged asset
- POST   /api/v1/quality/{score_id}/reject         — Reject flagged asset

RBAC: All authenticated users can read. Admin only for approve/reject.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_admin
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.quality import (
    QualityScoreResponse,
    FlaggedAssetResponse,
    QualityApproveRequest,
    QualityRejectRequest,
    JobQualityResponse,
)
from app.services.quality_service import QualityService

logger = logging.getLogger(__name__)

job_quality_router = APIRouter(prefix="/jobs", tags=["Quality Assurance"])
quality_router = APIRouter(prefix="/quality", tags=["Quality Assurance"])


@job_quality_router.get(
    "/{job_id}/quality",
    response_model=JobQualityResponse,
    summary="Get quality scores for a job",
)
async def get_job_quality(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """All quality scores for a job with per-asset breakdown."""
    service = QualityService(db)
    result = await service.get_job_quality(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            },
        )
    return result


@quality_router.get(
    "/flagged",
    response_model=PaginatedResponse[FlaggedAssetResponse],
    summary="List flagged assets",
)
async def list_flagged_assets(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Assets needing human review (decision = flagged)."""
    service = QualityService(db)
    flagged, total = await service.list_flagged(page=page, per_page=per_page)
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return PaginatedResponse(
        data=flagged,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@quality_router.post(
    "/{score_id}/approve",
    response_model=QualityScoreResponse,
    summary="Approve flagged asset",
)
async def approve_quality_score(
    score_id: UUID,
    data: QualityApproveRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Manually approve a flagged asset (admin only)."""
    service = QualityService(db)
    try:
        result = await service.approve_score(
            score_id, current_user.username, notes=data.notes
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                }
            },
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Quality score {score_id} not found",
                }
            },
        )
    return result


@quality_router.post(
    "/{score_id}/reject",
    response_model=QualityScoreResponse,
    summary="Reject flagged asset",
)
async def reject_quality_score(
    score_id: UUID,
    data: QualityRejectRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Manually reject a flagged asset — triggers regeneration (admin only)."""
    service = QualityService(db)
    try:
        result = await service.reject_score(
            score_id,
            current_user.username,
            notes=data.notes,
            regenerate=data.regenerate,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                }
            },
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Quality score {score_id} not found",
                }
            },
        )
    return result
