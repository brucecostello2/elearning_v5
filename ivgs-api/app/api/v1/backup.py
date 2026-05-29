"""
IVGS v5 — Backup REST API Endpoints
=====================================

Implements §5.2.7:
  GET  /api/v1/backup/records      — List backup records with status and size
  POST /api/v1/backup/trigger      — Trigger on-demand backup (Admin only)
  POST /api/v1/backup/{id}/verify  — Trigger integrity verification

Phase 14 Stream B refactor:
  - Replaces in-process asyncio.create_subprocess_shell with Celery task
    dispatch via .send_task().  The actual backup work happens in the
    dedicated ivgs-backup-worker container.
  - API container no longer has docker.sock or GPG keys; only dispatches
    work to the worker queue.
  - Trigger endpoint returns immediately with status='running'; the worker
    transitions through running → completed/failed.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db, require_admin
from app.models.user import User

logger = logging.getLogger("ivgs.api.backup")

router = APIRouter(tags=["Backup"])


# ---------------------------------------------------------------------------
# Celery dispatcher
# ---------------------------------------------------------------------------
# The API does NOT execute backup work in-process.  It dispatches tasks to
# the `backup` queue, which the ivgs-backup-worker container consumes.
#
# We use send_task(name=...) so the API doesn't import the worker's task
# functions (different container, different codebase).  Task names are the
# coordination contract; both ends must agree on them.
# ---------------------------------------------------------------------------

_BROKER_URL = os.environ.get("IVGS_CELERY_BROKER_URL", "redis://redis:6379/0")

# A lightweight Celery client just for dispatching.  No queues defined here
# because this app is producer-only (never consumes).
celery_client = Celery("ivgs_api_dispatcher", broker=_BROKER_URL)

# Match the backup-worker's broker_transport_options so pidbox isn't
# triggered on our side (we're a producer-only, but still).
celery_client.conf.update(
    broker_transport_options={
        "fanout_prefix": True,
        "fanout_patterns": True,
        "global_keyprefix": "ivgs_backup_",
    },
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
)

# Task name → handles  the routing.  Names must match @shared_task(name=...)
# decorators in /opt/ivgs/ivgs-backup-worker/tasks/backup_tasks.py.
_TASK_NAMES = {
    "full_database": "tasks.backup_tasks.run_full_database_backup",
    "asset_backup":  "tasks.backup_tasks.run_asset_backup",
    "config_backup": "tasks.backup_tasks.run_config_backup",
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class BackupRecord(BaseModel):
    """Single backup record."""
    id: str
    backup_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    size_bytes: Optional[int] = None
    backup_path: Optional[str] = None
    verification_checksum: Optional[str] = None
    verified_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BackupListResponse(BaseModel):
    """Paginated backup list response."""
    data: list[BackupRecord]
    page: int
    per_page: int
    total: int


class BackupTriggerRequest(BaseModel):
    """Request to trigger a backup."""
    backup_type: str = "full_database"


class BackupTriggerResponse(BaseModel):
    """Response after dispatching a backup task."""
    id: str
    backup_type: str
    status: str
    started_at: datetime
    message: str


class BackupVerifyResponse(BaseModel):
    """Response after dispatching a verification task."""
    id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# GET /records — list backup records
# ---------------------------------------------------------------------------

@router.get("/records", response_model=BackupListResponse)
async def list_backup_records(
    page: int = 1,
    per_page: int = 20,
    backup_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List backup records with optional filtering and pagination."""
    from sqlalchemy import text as sa_text

    # Build WHERE clause dynamically
    conditions = []
    params: dict = {}
    if backup_type:
        conditions.append("backup_type = :backup_type")
        params["backup_type"] = backup_type
    if status_filter:
        conditions.append("status = :status")
        params["status"] = status_filter

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    # Count total
    count_sql = f"SELECT COUNT(*) FROM backup_records {where_sql}"
    total = (await db.execute(sa_text(count_sql), params)).scalar() or 0

    # Fetch page
    offset = (page - 1) * per_page
    list_sql = (
        f"SELECT id, backup_type, status, started_at, completed_at, "
        f"       size_bytes, backup_path, verification_checksum, "
        f"       verified_at, error_message "
        f"FROM backup_records {where_sql} "
        f"ORDER BY started_at DESC "
        f"LIMIT :limit OFFSET :offset"
    )
    rows = (await db.execute(
        sa_text(list_sql),
        {**params, "limit": per_page, "offset": offset},
    )).fetchall()

    records = [
        BackupRecord(
            id=str(r.id),
            backup_type=r.backup_type,
            status=r.status,
            started_at=r.started_at,
            completed_at=r.completed_at,
            size_bytes=r.size_bytes,
            backup_path=r.backup_path,
            verification_checksum=r.verification_checksum,
            verified_at=r.verified_at,
            error_message=r.error_message,
        )
        for r in rows
    ]

    return BackupListResponse(
        data=records,
        page=page,
        per_page=per_page,
        total=total,
    )


# ---------------------------------------------------------------------------
# POST /trigger — dispatch a backup task to the worker
# ---------------------------------------------------------------------------

@router.post("/trigger", response_model=BackupTriggerResponse)
async def trigger_backup(
    request: BackupTriggerRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    POST /api/v1/backup/trigger — Trigger on-demand backup (Admin only).

    Inserts a record with status='running', dispatches a Celery task to the
    backup queue, and returns immediately.  The worker takes ownership of
    the record's lifecycle (running → completed/failed).
    """
    from sqlalchemy import text as sa_text

    # Validate backup_type early; reject unsupported values before DB write
    if request.backup_type not in _TASK_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {
                "code": "VALIDATION_ERROR",
                "message": (
                    f"Unsupported backup_type '{request.backup_type}'. "
                    f"Supported: {sorted(_TASK_NAMES.keys())}"
                ),
            }},
        )

    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    task_name = _TASK_NAMES[request.backup_type]

    # Insert record FIRST.  If broker dispatch fails after this, we have a
    # 'running' row that will never transition.  That's acceptable for now
    # (operator can manually reconcile); future enhancement could roll back
    # the row on dispatch failure.
    await db.execute(
        sa_text(
            "INSERT INTO backup_records (id, backup_type, status, started_at) "
            "VALUES (:id, :backup_type, 'running', :started_at)"
        ),
        {"id": backup_id, "backup_type": request.backup_type, "started_at": now},
    )
    await db.commit()

    # Dispatch to the backup worker via Celery.  send_task() pushes a message
    # onto Redis; the worker picks it up and executes the script.
    try:
        celery_client.send_task(
            task_name,
            args=[backup_id],
            queue="backup",
        )
        logger.info(
            "Backup task dispatched",
            extra={
                "backup_id": backup_id,
                "backup_type": request.backup_type,
                "task_name": task_name,
            },
        )
    except Exception as exc:
        # If dispatch fails (broker down, etc.), mark the record as failed
        # so it doesn't sit at 'running' forever.
        logger.exception(
            "Failed to dispatch backup task to broker",
            extra={"backup_id": backup_id, "backup_type": request.backup_type},
        )
        await db.execute(
            sa_text(
                "UPDATE backup_records "
                "SET status = 'failed', error_message = :err, completed_at = :ts "
                "WHERE id = :id"
            ),
            {
                "id": backup_id,
                "err": f"Broker dispatch failed: {exc}"[:2000],
                "ts": datetime.now(timezone.utc),
            },
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {
                "code": "BROKER_UNAVAILABLE",
                "message": "Failed to dispatch backup task; broker may be down.",
            }},
        )

    return BackupTriggerResponse(
        id=backup_id,
        backup_type=request.backup_type,
        status="running",
        started_at=now,
        message=(
            f"Backup {request.backup_type} dispatched (id={backup_id}). "
            f"Track via GET /api/v1/backup/records."
        ),
    )


# ---------------------------------------------------------------------------
# POST /{backup_id}/verify — dispatch a verification task
# ---------------------------------------------------------------------------

@router.post("/{backup_id}/verify", response_model=BackupVerifyResponse)
async def verify_backup(
    backup_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    POST /api/v1/backup/{id}/verify — Trigger integrity verification.

    Verifies a completed backup by dispatching run_verification to the
    worker, which decrypts, restores to a temp postgres container, and
    compares row counts.  Updates the record to status='verified' on
    success.

    Pre-conditions:
      - Backup record must exist
      - Backup record must have status='completed' (DB ENUM value)
    """
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text("SELECT * FROM backup_records WHERE id = :id"),
            {"id": backup_id},
        )
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Backup record {backup_id} not found",
            }},
        )

    # DB ENUM values are: running, completed, failed, verified.
    # Verify is only valid for completed (or re-verified) backups.
    if row.status not in ("completed", "verified"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {
                "code": "VALIDATION_ERROR",
                "message": (
                    f"Cannot verify backup in '{row.status}' state; "
                    f"verify requires status in ('completed', 'verified')."
                ),
            }},
        )

    # Derive verify_date from the backup's started_at — verify_backup.sh
    # takes a date string (YYYY-MM-DD) as positional arg to locate the
    # backup files on the NAS at /mnt/backup/ivgs/db/<date>/.
    verify_date = row.started_at.strftime("%Y-%m-%d")

    # Dispatch the verification task.  Worker will update the record
    # status to 'verified' on success or 'failed' on error.
    try:
        celery_client.send_task(
            "tasks.backup_tasks.run_verification",
            args=[backup_id, verify_date],
            queue="backup",
        )
        logger.info(
            "Verification task dispatched",
            extra={"backup_id": backup_id, "verify_date": verify_date},
        )
    except Exception as exc:
        logger.exception(
            "Failed to dispatch verification task",
            extra={"backup_id": backup_id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {
                "code": "BROKER_UNAVAILABLE",
                "message": f"Failed to dispatch verification task: {exc}",
            }},
        )

    return BackupVerifyResponse(
        id=backup_id,
        status="running",
        message=(
            f"Verification dispatched for backup {backup_id} "
            f"(date {verify_date}). Track via GET /api/v1/backup/records."
        ),
    )
