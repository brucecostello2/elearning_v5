"""
IVGS v5 — Backup REST API Endpoints
=====================================

Implements §5.2.7:
  GET  /api/v1/backup/records      — List backup records with status and size
  POST /api/v1/backup/trigger      — Trigger on-demand backup (Admin only)
  POST /api/v1/backup/{id}/verify  — Trigger integrity verification
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db, require_admin
from app.models.user import User

logger = logging.getLogger("ivgs.api.backup")

router = APIRouter(tags=["Backup"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class BackupRecord(BaseModel):
    id: str
    backup_type: str  # full_database | wal_archive | asset_backup | config_backup | vm_snapshot
    status: str  # pending | running | success | failed
    size_bytes: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    verification_checksum: Optional[str] = None
    backup_path: Optional[str] = None
    error_message: Optional[str] = None


class BackupListResponse(BaseModel):
    data: list[BackupRecord]
    total: int
    page: int
    per_page: int
    pages: int
    has_more: bool


class BackupTriggerRequest(BaseModel):
    backup_type: str = "full_database"  # full_database | asset_backup | config_backup


class BackupTriggerResponse(BaseModel):
    id: str
    backup_type: str
    status: str
    started_at: datetime
    message: str


class BackupVerifyResponse(BaseModel):
    id: str
    status: str
    verification_checksum: Optional[str] = None
    row_count_match: Optional[bool] = None
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/records", response_model=BackupListResponse)
async def list_backup_records(
    page: int = 1,
    per_page: int = 50,
    backup_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /api/v1/backup/records — List backup records with status and size."""
    from sqlalchemy import text as sa_text

    where_clauses = []
    params: dict = {}

    if backup_type:
        where_clauses.append("backup_type = :backup_type")
        params["backup_type"] = backup_type
    if status_filter:
        where_clauses.append("status = :status_filter")
        params["status_filter"] = status_filter

    # SECURITY NOTE: where_clauses contains only hardcoded column comparisons
    # with :named_param placeholders. Actual values are in params dict and
    # passed to execute() separately — this is parameterized, not injectable.
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Count total
    count_row = (
        await db.execute(
            sa_text(f"SELECT COUNT(*) as cnt FROM backup_records WHERE {where_sql}"),
            params,
        )
    ).fetchone()
    total = count_row.cnt

    # Fetch page
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    rows = (
        await db.execute(
            sa_text(
                f"SELECT * FROM backup_records WHERE {where_sql} "
                "ORDER BY started_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).fetchall()

    pages = max(1, (total + per_page - 1) // per_page)

    records = [
        BackupRecord(
            id=str(r.id),
            backup_type=r.backup_type,
            status=r.status,
            size_bytes=r.size_bytes,
            started_at=r.started_at,
            completed_at=r.completed_at,
            verification_checksum=r.verification_checksum,
            backup_path=r.backup_path,
            error_message=r.error_message,
        )
        for r in rows
    ]

    return BackupListResponse(
        data=records,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        has_more=page < pages,
    )


@router.post("/trigger", response_model=BackupTriggerResponse)
async def trigger_backup(
    request: BackupTriggerRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """POST /api/v1/backup/trigger — Trigger on-demand backup (Admin only)."""
    from sqlalchemy import text as sa_text

    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await db.execute(
        sa_text(
            "INSERT INTO backup_records (id, backup_type, status, started_at) "
            "VALUES (:id, :backup_type, 'running', :started_at)"
        ),
        {"id": backup_id, "backup_type": request.backup_type, "started_at": now},
    )
    await db.commit()

    # Launch backup in background
    asyncio.create_task(_run_backup(backup_id, request.backup_type, db))

    return BackupTriggerResponse(
        id=backup_id,
        backup_type=request.backup_type,
        status="running",
        started_at=now,
        message=f"Backup {request.backup_type} initiated. Track via GET /api/v1/backup/records.",
    )


@router.post("/{backup_id}/verify", response_model=BackupVerifyResponse)
async def verify_backup(
    backup_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /api/v1/backup/{id}/verify — Trigger integrity verification."""
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
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"Backup record {backup_id} not found"}},
        )

    if row.status not in ("completed", "verified"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VALIDATION_ERROR",
                              "message": f"Cannot verify backup in '{row.status}' state"}},
        )

    await db.execute(
        sa_text("UPDATE backup_records SET status = 'verifying' WHERE id = :id"),
        {"id": backup_id},
    )
    await db.commit()

    # Launch verification in background
    asyncio.create_task(_run_verification(backup_id, row.backup_path, db))

    return BackupVerifyResponse(
        id=backup_id,
        status="verifying",
        message="Backup verification initiated.",
    )


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _run_backup(backup_id: str, backup_type: str, db) -> None:
    """Execute backup shell script and update record."""
    from sqlalchemy import text as sa_text

    script_map = {
        "full_database": "/ivgs/ivgs-infra/scripts/backup.sh",
        "asset_backup": "/ivgs/ivgs-infra/scripts/backup.sh --assets-only",
        "config_backup": "/ivgs/ivgs-infra/scripts/backup.sh --config-only",
    }

    script_cmd = script_map.get(backup_type, script_map["full_database"])

    try:
        proc = await asyncio.create_subprocess_shell(
            f"{script_cmd} --backup-id={backup_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            # Parse size from script output
            size_bytes = _parse_backup_size(stdout.decode())
            backup_path = f"/mnt/backup/ivgs/db/{backup_id}"

            await db.execute(
                sa_text(
                    "UPDATE backup_records SET status = 'completed', "
                    "size_bytes = :size, backup_path = :path, "
                    "completed_at = :completed_at WHERE id = :id"
                ),
                {
                    "id": backup_id,
                    "size": size_bytes,
                    "path": backup_path,
                    "completed_at": datetime.now(timezone.utc),
                },
            )
        else:
            await db.execute(
                sa_text(
                    "UPDATE backup_records SET status = 'failed', "
                    "error_message = :error, completed_at = :completed_at "
                    "WHERE id = :id"
                ),
                {
                    "id": backup_id,
                    "error": stderr.decode()[:2000],
                    "completed_at": datetime.now(timezone.utc),
                },
            )
        await db.commit()
    except Exception as _exc:  # noqa: F841
        logger.exception("Backup task failed", extra={"backup_id": backup_id})
        await db.execute(
            sa_text(
                "UPDATE backup_records SET status = 'failed', "
                "error_message = :error WHERE id = :id"
            ),
            {"id": backup_id, "error": str(_exc)[:2000]},
        )
        await db.commit()


async def _run_verification(backup_id: str, backup_path: str, db) -> None:
    """Run backup verification: restore to temp DB, compare row counts, compute checksum."""
    from sqlalchemy import text as sa_text
    import hashlib

    try:
        proc = await asyncio.create_subprocess_shell(
            f"/ivgs/ivgs-infra/scripts/verify_backup.sh --backup-id={backup_id} "
            f"--path={backup_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            checksum = hashlib.sha256(stdout).hexdigest()
            await db.execute(
                sa_text(
                    "UPDATE backup_records SET status = 'verified', "
                    "verification_checksum = :checksum WHERE id = :id"
                ),
                {"id": backup_id, "checksum": checksum},
            )
        else:
            await db.execute(
                sa_text(
                    "UPDATE backup_records SET status = 'failed', "
                    "error_message = :error WHERE id = :id"
                ),
                {"id": backup_id, "error": f"Verification failed: {stderr.decode()[:2000]}"},
            )
        await db.commit()
    except Exception as _exc:  # noqa: F841
        logger.exception("Verification failed", extra={"backup_id": backup_id})


def _parse_backup_size(output: str) -> int:
    """Parse backup size from shell script output."""
    for line in output.split("\n"):
        if "size_bytes=" in line:
            return int(line.split("=")[1].strip())
    return 0
