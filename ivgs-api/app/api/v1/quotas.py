"""
IVGS v5 — Storage Quota REST API (§5.2.6)
  GET /api/v1/quotas/{entity_type}/{entity_id} — Get storage quota
  PUT /api/v1/quotas/{entity_type}/{entity_id} — Set quota limits (Admin only)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db, require_admin

router = APIRouter(tags=["Quotas"])


class QuotaResponse(BaseModel):
    entity_type: str
    entity_id: str
    quota_bytes: int
    used_bytes: int
    available_bytes: int
    usage_pct: float
    alert_threshold_pct: float
    alert_active: bool


class QuotaUpdateRequest(BaseModel):
    quota_bytes: int
    alert_threshold_pct: float = 80.0


@router.get("/{entity_type}/{entity_id}", response_model=QuotaResponse)
async def get_quota(
    entity_type: str,
    entity_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get storage quota, current usage, and alert status."""
    from sqlalchemy import text as sa_text

    row = (
        await db.execute(
            sa_text(
                "SELECT * FROM storage_quotas "
                "WHERE entity_type = :et AND entity_id = :eid"
            ),
            {"et": entity_type, "eid": entity_id},
        )
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND",
                              "message": f"No quota for {entity_type}/{entity_id}"}},
        )

    used = row.current_bytes or 0
    quota = row.max_bytes or 0
    available = max(0, quota - used)
    usage_pct = (used / quota * 100) if quota > 0 else 0.0
    alert_threshold = row.alert_threshold_pct or 80.0

    return QuotaResponse(
        entity_type=entity_type,
        entity_id=entity_id,
        quota_bytes=quota,
        used_bytes=used,
        available_bytes=available,
        usage_pct=round(usage_pct, 2),
        alert_threshold_pct=alert_threshold,
        alert_active=usage_pct >= alert_threshold,
    )


@router.put("/{entity_type}/{entity_id}", response_model=QuotaResponse)
async def set_quota(
    entity_type: str,
    entity_id: str,
    request: QuotaUpdateRequest,
    db=Depends(get_db),
    current_user=Depends(require_admin),
):
    """Set quota limits (Admin only)."""
    from sqlalchemy import text as sa_text

    await db.execute(
        sa_text(
            "INSERT INTO storage_quotas (entity_type, entity_id, max_bytes, alert_threshold_pct) "
            "VALUES (:et, :eid, :quota, :threshold) "
            "ON CONFLICT (entity_type, entity_id) "
            "DO UPDATE SET max_bytes = :quota, alert_threshold_pct = :threshold"
        ),
        {
            "et": entity_type,
            "eid": entity_id,
            "quota": request.quota_bytes,
            "threshold": request.alert_threshold_pct,
        },
    )
    await db.commit()

    return await get_quota(entity_type, entity_id, db, current_user)
