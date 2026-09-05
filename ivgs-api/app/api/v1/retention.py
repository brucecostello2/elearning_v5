"""
Retention policy API endpoints per §5.2.6.

Endpoints:
- GET    /api/v1/retention/policies                — List all retention policies
- POST   /api/v1/retention/policies                — Create retention policy (admin only)
- GET    /api/v1/retention/policies/{id}           — Get retention policy detail
- PUT    /api/v1/retention/policies/{id}           — Update retention policy (admin only)
- GET    /api/v1/retention/report                  — Asset tier distribution report
- POST   /api/v1/retention/run                     — Run the retention migration now (admin only)

RBAC: Admin only for mutations. All authenticated users can read.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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


# ── WP-70 fix S4: the "Run cleanup" button ────────────────────────────────
#
# Admin -> Retention -> "Run cleanup" has POSTed /api/v1/retention/run since the
# page was written, and no route served it: every press was a 404 and the
# success toast never showed. The route enqueues the nightly beat task once,
# under the beat entry's own name and kwargs (ivgs-workers/celery_app.py,
# "retention-migration"), so a manual run IS the nightly run.

# WP-70 fix D-6: the task NAME is passed to send_task as a string literal
# (below), not through a constant — dev/audit/build_consumer_index.py's D3
# check verifies a literal against the registered task names and files a
# variable as "dynamic task name", unchecked. TestS4RetentionRun pins the
# literal to the beat entry's name.
RETENTION_BEAT_QUEUE = "default"
RETENTION_BEAT_PRIORITY = 2
RETENTION_BEAT_KWARGS = {"dry_run": False, "max_transitions": 500}


class RetentionRunResponse(BaseModel):
    """The Celery task id of the enqueued retention migration."""

    task_id: str


@router.post(
    "/run",
    response_model=RetentionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the retention migration now (admin only)",
)
async def run_retention_migration_now(
    current_user: User = Depends(require_admin),
):
    """Enqueue one run of the retention migration beat task (admin only).

    Returns 202 with the task id. A broker failure is a 503, not a 500: the
    request was well-formed and nothing was enqueued.
    """
    from app.services.celery_producer import celery_app as pipeline_celery

    try:
        result = pipeline_celery.send_task(
            "ivgs_workers.tasks.periodic_tasks.run_retention_migration",
            kwargs=dict(RETENTION_BEAT_KWARGS),
            queue=RETENTION_BEAT_QUEUE,
            priority=RETENTION_BEAT_PRIORITY,
        )
    except Exception as exc:
        logger.error(
            "retention_run_enqueue_failed user=%s error=%s", current_user.id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "BROKER_UNAVAILABLE",
                    "message": f"Could not enqueue the retention migration task: {exc}",
                }
            },
        ) from exc
    logger.info(
        "retention_run_enqueued user=%s task_id=%s", current_user.id, result.id
    )
    return RetentionRunResponse(task_id=str(result.id))
