"""
Quality Assurance API endpoints per §5.2.3.

Endpoints:
- POST   /api/v1/quality-scores                    — Record an automated verdict
- GET    /api/v1/jobs/{id}/quality                 — All quality scores for a job
- GET    /api/v1/quality/flagged                   — Assets needing human review
- POST   /api/v1/quality/{score_id}/approve        — Approve flagged asset
- POST   /api/v1/quality/{score_id}/reject         — Reject flagged asset

RBAC: All authenticated users can read. Admin only for approve/reject.
The submission route is service-token or operator/admin — the pipeline calls it.

WP-44. `POST /quality-scores` is NEW. The worker (`tasks/stage3_images.py
_submit_quality_score`) has been calling this exact path since Phase 4 and it
did not exist; the call was wrapped in a bare `except Exception`, a 404 raises
nothing, and so every automated verdict of the first e2e run was thrown away
in silence. `asset_quality_scores` holds zero rows for that run — which is why
the "18 flagged review items" from it cannot be cleared or re-scored: they were
never written. See the WP-44 report, S7c.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_admin, require_service_or_privileged_user
from app.models.user import User
from app.schemas.base import PaginatedResponse
from app.schemas.quality import (
    QualityScoreResponse,
    FlaggedAssetResponse,
    QualityApproveRequest,
    QualityRejectRequest,
    QualityScoreCreateRequest,
    JobQualityResponse,
)
from app.services.quality_service import QualityService

logger = logging.getLogger(__name__)

job_quality_router = APIRouter(prefix="/jobs", tags=["Quality Assurance"])
quality_router = APIRouter(prefix="/quality", tags=["Quality Assurance"])
# No prefix: the pipeline's path is /api/v1/quality-scores, which is a sibling
# of /api/v1/quality/... and not a child of it. Keeping the worker's long-
# standing path is deliberate — the contract it already speaks is the one that
# gets implemented, rather than moving the endpoint and leaving four deployed
# worker images pointing at nothing.
quality_scores_router = APIRouter(tags=["Quality Assurance"])


@quality_scores_router.post(
    "/quality-scores",
    response_model=QualityScoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an automated quality verdict",
)
async def create_quality_score(
    data: QualityScoreCreateRequest,
    current_user: User = Depends(require_service_or_privileged_user),
    db: AsyncSession = Depends(get_session),
):
    """Persist one automated quality verdict produced by the pipeline."""
    service = QualityService(db)
    try:
        return await service.record_score(data)
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": str(e),
                }
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                }
            },
        )


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
