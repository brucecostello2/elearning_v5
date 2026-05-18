"""REST API endpoints for quality score management."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.quality import AssetQualityScore
from app.schemas.quality import QualityScoreResponse, FlaggedAssetResponse

router = APIRouter(prefix="/api/v1", tags=["quality"])


@router.get("/jobs/{job_id}/quality")
def list_job_quality_scores(
    job_id: str, db: Session = Depends(get_db)
):
    """Return all quality scores for a specific job."""
    scores = (db.query(AssetQualityScore)
              .filter(AssetQualityScore.job_id == job_id)
              .order_by(AssetQualityScore.created_at.desc())
              .all())
    return [QualityScoreResponse.model_validate(s) for s in scores]


@router.get("/quality/flagged")
def list_flagged_assets(
    asset_type: Optional[str] = None,
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    max_score: float = Query(0.9, ge=0.0, le=1.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Return assets in the human review queue (decision='flagged')."""
    query = (db.query(AssetQualityScore)
             .filter(AssetQualityScore.decision == 'flagged',
                     AssetQualityScore.reviewed_by.is_(None)))
    if asset_type:
        query = query.filter(AssetQualityScore.asset_type == asset_type)
    query = query.filter(
        AssetQualityScore.quality_score.between(min_score, max_score)
    )
    total = query.count()
    scores = (query.order_by(AssetQualityScore.quality_score.asc())
              .offset((page - 1) * page_size)
              .limit(page_size)
              .all())
    return {"total": total, "page": page,
            "items": [FlaggedAssetResponse.model_validate(s) for s in scores]}


@router.post("/quality/{score_id}/approve")
def approve_asset(
    score_id: int,
    reviewer: str = "ops",
    db: Session = Depends(get_db),
):
    """Approve a flagged asset for downstream processing."""
    score = db.query(AssetQualityScore).filter(
        AssetQualityScore.id == score_id
    ).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    score.decision = 'approved'
    score.reviewed_by = reviewer
    from datetime import datetime
    score.reviewed_at = datetime.utcnow()
    db.commit()
    return {"status": "approved", "score_id": score_id}


@router.post("/quality/{score_id}/reject")
def reject_asset(
    score_id: int,
    reason: str = "",
    reviewer: str = "ops",
    db: Session = Depends(get_db),
):
    """Reject a flagged asset — triggers regeneration pipeline."""
    score = db.query(AssetQualityScore).filter(
        AssetQualityScore.id == score_id
    ).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    score.decision = 'rejected'
    score.rejection_reason = reason
    score.reviewed_by = reviewer
    from datetime import datetime
    score.reviewed_at = datetime.utcnow()
    db.commit()
    # TODO: trigger regeneration task
    return {"status": "rejected", "score_id": score_id,
            "regeneration_queued": False}
