"""
Quality score service: scoring queries, approve/reject with audit logging.

Per §5.2.3 — provides read access to automated quality scores and
manual review actions for flagged assets. CLIP scoring execution
happens in the worker pipeline (Phase 8).
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.quality_score import AssetQualityScore
from app.models.asset import Asset
from app.models.project import Project
from app.models.render_job import RenderJob
from app.schemas.quality import (
    QualityScoreResponse,
    FlaggedAssetResponse,
    JobQualityResponse,
)

logger = logging.getLogger(__name__)


class QualityService:
    """Business logic for quality score management and review."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_job_quality(self, job_id: UUID) -> Optional[JobQualityResponse]:
        """
        Get all quality scores for a job with per-asset breakdown.

        Returns None if the job does not exist.
        """
        job_result = await self.db.execute(
            select(RenderJob).where(RenderJob.id == job_id)
        )
        if job_result.scalar_one_or_none() is None:
            return None

        result = await self.db.execute(
            select(AssetQualityScore)
            .where(AssetQualityScore.job_id == job_id)
            .order_by(AssetQualityScore.created_at)
        )
        scores = result.scalars().all()

        approved = sum(1 for s in scores if s.decision == "approved")
        flagged = sum(1 for s in scores if s.decision == "flagged")
        rejected = sum(1 for s in scores if s.decision == "rejected")

        quality_values = [s.quality_score for s in scores if s.quality_score is not None]
        safety_values = [s.safety_score for s in scores if s.safety_score is not None]

        avg_quality = (
            round(sum(quality_values) / len(quality_values), 4)
            if quality_values
            else None
        )
        avg_safety = (
            round(sum(safety_values) / len(safety_values), 4)
            if safety_values
            else None
        )

        return JobQualityResponse(
            job_id=job_id,
            total_assets=len(scores),
            approved_count=approved,
            flagged_count=flagged,
            rejected_count=rejected,
            average_quality_score=avg_quality,
            average_safety_score=avg_safety,
            scores=[QualityScoreResponse.model_validate(s) for s in scores],
        )

    async def list_flagged(
        self,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[FlaggedAssetResponse], int]:
        """
        List assets needing human review (decision = flagged).

        Joins with assets and projects to provide context.
        """
        query = (
            select(AssetQualityScore)
            .where(AssetQualityScore.decision == "flagged")
        )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(AssetQualityScore.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        scores = result.scalars().all()

        responses = []
        for score in scores:
            asset_type = None
            project_id = None
            project_name = None

            asset_result = await self.db.execute(
                select(Asset).where(Asset.id == score.asset_id)
            )
            asset = asset_result.scalar_one_or_none()
            if asset:
                asset_type = asset.asset_type
                project_id = asset.project_id
                proj_result = await self.db.execute(
                    select(Project.name).where(Project.id == asset.project_id)
                )
                proj_row = proj_result.first()
                if proj_row:
                    project_name = proj_row[0]

            responses.append(
                FlaggedAssetResponse(
                    id=score.id,
                    asset_id=score.asset_id,
                    job_id=score.job_id,
                    quality_score=score.quality_score,
                    safety_score=score.safety_score,
                    scoring_details=score.scoring_details,
                    decision=score.decision,
                    created_at=score.created_at,
                    asset_type=asset_type,
                    project_id=project_id,
                    project_name=project_name,
                )
            )

        return responses, total

    async def approve_score(
        self,
        score_id: UUID,
        reviewed_by: str,
        notes: Optional[str] = None,
    ) -> Optional[QualityScoreResponse]:
        """
        Manually approve a flagged asset.

        Sets decision to 'approved' and records the reviewer.
        """
        result = await self.db.execute(
            select(AssetQualityScore).where(AssetQualityScore.id == score_id)
        )
        score = result.scalar_one_or_none()
        if score is None:
            return None

        if score.decision != "flagged":
            raise ValueError(
                f"Cannot approve score with decision '{score.decision}'. "
                f"Only 'flagged' scores can be approved."
            )

        score.decision = "approved"
        score.reviewed_by = reviewed_by
        score.reviewed_at = datetime.now(timezone.utc)
        score.review_notes = notes

        await self.db.commit()
        await self.db.refresh(score)

        logger.info(
            f"Quality score approved: id={score_id} asset={score.asset_id} "
            f"by={reviewed_by}"
        )
        return QualityScoreResponse.model_validate(score)

    async def reject_score(
        self,
        score_id: UUID,
        reviewed_by: str,
        notes: Optional[str] = None,
        regenerate: bool = True,
    ) -> Optional[QualityScoreResponse]:
        """
        Manually reject a flagged asset (optionally triggers regeneration).

        Sets decision to 'rejected' and records the reviewer.
        Phase 8: triggers asset regeneration via Celery task.
        """
        result = await self.db.execute(
            select(AssetQualityScore).where(AssetQualityScore.id == score_id)
        )
        score = result.scalar_one_or_none()
        if score is None:
            return None

        if score.decision != "flagged":
            raise ValueError(
                f"Cannot reject score with decision '{score.decision}'. "
                f"Only 'flagged' scores can be rejected."
            )

        score.decision = "rejected"
        score.reviewed_by = reviewed_by
        score.reviewed_at = datetime.now(timezone.utc)
        score.review_notes = notes

        await self.db.commit()
        await self.db.refresh(score)

        logger.info(
            f"Quality score rejected: id={score_id} asset={score.asset_id} "
            f"by={reviewed_by} regenerate={regenerate}"
        )

        if regenerate:
            # Phase 8: dispatch regeneration task
            # asset = await self.db.get(Asset, score.asset_id)
            # if asset and asset.generation_prompt_id:
            #     celery_app.send_task(
            #         "pipeline.regenerate_asset",
            #         args=[str(score.asset_id)],
            #     )
            logger.info(
                f"Regeneration queued for asset={score.asset_id} "
                f"(stub — Phase 8)"
            )

        return QualityScoreResponse.model_validate(score)
