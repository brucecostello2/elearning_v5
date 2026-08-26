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

from sqlalchemy import select, func, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quality_score import AssetQualityScore
from app.models.asset import Asset
from app.models.project import Project
from app.models.render_job import RenderJob
from app.schemas.quality import (
    QualityScoreResponse,
    FlaggedAssetResponse,
    JobQualityResponse,
    QualityScoreCreateRequest,
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
            .where(AssetQualityScore.decision.cast(String) == "flagged")
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

    async def record_score(
        self,
        data: QualityScoreCreateRequest,
    ) -> QualityScoreResponse:
        """Persist one automated quality verdict from the pipeline.

        WP-44. Raises ``LookupError`` if the asset does not exist — a quality
        score for an asset that is not there is not a record, it is noise, and
        the caller turns it into a 404 rather than writing an orphan row.

        Automated verdicts are written unreviewed: ``reviewed_by`` and
        ``reviewed_at`` stay NULL and are what separate a machine decision from
        a human one in the review queue.
        """
        decision = (data.decision or "").strip().lower()
        allowed = ("approved", "flagged", "rejected")
        if decision not in allowed:
            raise ValueError(
                f"decision must be one of {allowed}, got {data.decision!r}"
            )

        asset_result = await self.db.execute(
            select(Asset).where(Asset.id == data.asset_id)
        )
        if asset_result.scalar_one_or_none() is None:
            raise LookupError(f"Asset {data.asset_id} not found")

        score = AssetQualityScore(
            asset_id=data.asset_id,
            job_id=data.job_id,
            quality_score=data.quality_score,
            safety_score=data.safety_score,
            scoring_details=data.scoring_details,
            decision=decision,
        )
        self.db.add(score)
        await self.db.commit()
        await self.db.refresh(score)

        logger.info(
            f"Quality score recorded: id={score.id} asset={data.asset_id} "
            f"decision={decision} score={data.quality_score} "
            f"complete={(data.scoring_details or {}).get('quality_score_complete')}"
        )
        return QualityScoreResponse.model_validate(score)

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

        regeneration_note: Optional[str] = None

        if regenerate:
            # WP-45 Task 3, site 6. This logged "Regeneration queued for
            # asset=... (stub - Phase 8)" and queued nothing. A reviewer
            # rejecting a flagged asset and ticking "regenerate" got a rejection
            # that stuck and a regeneration that never happened, with the word
            # "stub" visible only in the server log.
            #
            # The rejection is already committed above, deliberately: a reviewer's
            # verdict is theirs and stands whether or not the fleet can act on it
            # right now. What must not happen is reporting the regeneration as
            # queued when it was not, so a dispatch failure is recorded on the
            # response instead of being logged and dropped.
            from app.services.regeneration import (
                RegenerationError,
                dispatch_scene_media_regeneration,
                scene_for_asset,
            )
            from app.services.gate_service import GateBlocked
            from app.services.project_service import PipelineAlreadyRunningError

            asset = await self.db.scalar(
                select(Asset).where(Asset.id == score.asset_id)
            )
            if asset is None:
                regeneration_note = (
                    f"Asset {score.asset_id} no longer exists; nothing to regenerate."
                )
                logger.warning(regeneration_note)
            else:
                try:
                    scene = await scene_for_asset(self.db, asset.scene_id, asset.id)
                    job = await dispatch_scene_media_regeneration(
                        self.db, scene,
                        reason=f"quality_reject:{score_id}",
                    )
                    regeneration_note = (
                        f"Regeneration dispatched as job {job.id} "
                        f"(celery task {job.celery_task_id})."
                    )
                    logger.info(
                        "Quality rejection regeneration dispatched: score=%s "
                        "asset=%s scene=%s job=%s",
                        score_id, asset.id, scene.id, job.id,
                    )
                except (
                    RegenerationError,
                    PipelineAlreadyRunningError,
                    GateBlocked,
                ) as exc:
                    # WP-62 Tasks 2(c) and 6. The two new refusals join the
                    # existing one HERE rather than propagating, because this
                    # path's contract (established by WP-45) is that the
                    # REJECTION stands whether or not the fleet can act on it,
                    # and the response says which happened. A 409 from here
                    # would roll a reviewer's recorded verdict back because a
                    # run was in flight.
                    regeneration_note = (
                        f"Rejection recorded, but regeneration was NOT "
                        f"dispatched: {exc}"
                    )
                    logger.warning(
                        "Quality rejection regeneration NOT dispatched: "
                        "score=%s asset=%s reason=%s",
                        score_id, score.asset_id, exc,
                    )

        response = QualityScoreResponse.model_validate(score)
        response.regeneration_note = regeneration_note
        return response
