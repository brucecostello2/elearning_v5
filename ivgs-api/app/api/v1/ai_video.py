"""REST endpoints for AI video generation status and analytics."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from app.core.database import get_db
from app.models.ai_video import AiVideoGeneration
from app.schemas.ai_video import (
    AiVideoGenerationResponse, AiVideoStatsResponse,
)

router = APIRouter(prefix="/api/v1", tags=["ai-video"])


@router.get("/jobs/{job_id}/ai-video/generations",
            response_model=List[AiVideoGenerationResponse])
async def list_ai_video_generations(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List all AI video generation attempts for a job."""
    records = db.query(AiVideoGeneration).filter_by(
        job_id=job_id).order_by(
        AiVideoGeneration.created_at.desc()).all()
    return [AiVideoGenerationResponse.from_orm(r) for r in records]


@router.get("/ai-video/stats", response_model=AiVideoStatsResponse)
async def get_ai_video_stats(
    hours: int = 24,
    db: Session = Depends(get_db),
):
    """Fleet-wide AI video generation stats for the last N hours."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    records = db.query(AiVideoGeneration).filter(
        AiVideoGeneration.created_at >= cutoff).all()
    if not records:
        return AiVideoStatsResponse(total=0, success_rate=0.0,
                                    avg_duration_s=0.0, fallback_rate=0.0)
    total = len(records)
    successes = [r for r in records if r.status == "complete"]
    l1 = [r for r in successes if r.fallback_level_used == 1]
    return AiVideoStatsResponse(
        total=total,
        success_rate=len(successes) / total,
        avg_duration_s=sum(r.generation_duration_seconds or 0
                           for r in successes) / max(len(successes), 1),
        fallback_rate=1.0 - (len(l1) / max(len(records), 1)),
    )


@router.get("/jobs/{job_id}/ai-video/generations/{gen_id}",
            response_model=AiVideoGenerationResponse)
async def get_ai_video_generation(
    job_id: uuid.UUID,
    gen_id: int,
    db: Session = Depends(get_db),
):
    record = db.query(AiVideoGeneration).filter_by(
        id=gen_id, job_id=job_id).first()
    if not record:
        raise HTTPException(404, "Generation record not found")
    return AiVideoGenerationResponse.from_orm(record)
