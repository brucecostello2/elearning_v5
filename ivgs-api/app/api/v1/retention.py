"""
Retention policy API endpoints per §5.2.6.

Endpoints:
- GET    /api/v1/retention/policies                — List all retention policies
- POST   /api/v1/retention/policies                — Create retention policy (admin only)
- GET    /api/v1/retention/policies/{id}           — Get retention policy detail
- PUT    /api/v1/retention/policies/{id}           — Update retention policy (admin only)
- GET    /api/v1/retention/report                  — Asset tier distribution report

RBAC: Admin only for mutations. All authenticated users can read.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from app.core.auth import get_current_user
from app.core.rbac import require_admin
from app.models.user import User
from app.schemas.retention import (
    RetentionPolicyCreate,
    RetentionPolicyUpdate,
    RetentionPolicyResponse,
    RetentionReportResponse,
)
from app.services.retention_service import RetentionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retention", tags=["Retention Policies"])


@router.get(
    "/policies",
    response_model=list[RetentionPolicyResponse],
    summary="List all retention policies",
)
async def list_retention_policies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all retention policies. Returns seeded defaults plus custom policies."""
    service = RetentionService(db)
    return await service.list_policies()


@router.post(
    "/policies",
    response_model=RetentionPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create retention policy (admin only)",
)
async def create_retention_policy(
    data: RetentionPolicyCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Create a new retention policy (admin only)."""
    service = RetentionService(db)
    try:
        return await service.create_policy(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                }
            },
        )


@router.get(
    "/policies/{policy_id}",
    response_model=RetentionPolicyResponse,
    summary="Get retention policy detail",
)
async def get_retention_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get a single retention policy by ID."""
    service = RetentionService(db)
    policy = await service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Retention policy {policy_id} not found",
                }
            },
        )
    return policy


@router.put(
    "/policies/{policy_id}",
    response_model=RetentionPolicyResponse,
    summary="Update retention policy (admin only)",
)
async def update_retention_policy(
    policy_id: UUID,
    data: RetentionPolicyUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update retention policy tiers and thresholds (admin only)."""
    service = RetentionService(db)
    try:
        policy = await service.update_policy(policy_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                }
            },
        )
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"Retention policy {policy_id} not found",
                }
            },
        )
    return policy


@router.get(
    "/report",
    response_model=RetentionReportResponse,
    summary="Asset tier distribution report",
)
async def get_retention_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Asset distribution across tiers and upcoming tier migrations."""
    service = RetentionService(db)
    return await service.get_report()
