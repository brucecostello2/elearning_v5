"""
Language variant service: CRUD for localization targets.

Per §5.1.8 — manages language variant records and retry.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.language_variant import LanguageVariant
from app.models.render_job import RenderJob

logger = logging.getLogger(__name__)


class LanguageService:
    """Business logic for language variant management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_variants(self, project_id: UUID) -> List[LanguageVariant]:
        """List language variants for a project."""
        result = await self.db.execute(
            select(LanguageVariant)
            .where(LanguageVariant.project_id == project_id)
            .order_by(LanguageVariant.language_code)
        )
        return list(result.scalars().all())

    async def get_variant(
        self, project_id: UUID, variant_id: UUID
    ) -> Optional[LanguageVariant]:
        """Get a single language variant."""
        result = await self.db.execute(
            select(LanguageVariant).where(
                LanguageVariant.id == variant_id,
                LanguageVariant.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_variant(
        self,
        project_id: UUID,
        language_code: str,
        translation_prompt_override: Optional[str] = None,
    ) -> LanguageVariant:
        """
        Add a localization target for a project.

        Optionally creates a project-level translation prompt override.
        """
        # Check for existing variant with same language
        existing = await self.db.execute(
            select(LanguageVariant).where(
                LanguageVariant.project_id == project_id,
                LanguageVariant.language_code == language_code,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Language variant '{language_code}' already exists for this project"
            )

        variant = LanguageVariant(
            project_id=project_id,
            language_code=language_code,
            state="pending",
        )
        self.db.add(variant)

        # Create translation prompt override if provided
        if translation_prompt_override:
            from app.services.prompt_service import PromptService

            prompt_service = PromptService(self.db)
            await prompt_service.create_prompt(
                prompt_type="translation",
                prompt_text=translation_prompt_override,
                change_note=f"Translation prompt override for {language_code}",
                created_by="system",
                project_id=project_id,
            )

        await self.db.commit()
        await self.db.refresh(variant)
        logger.info(f"Language variant created: {language_code} for project={project_id}")
        return variant

    async def retry_variant(
        self,
        project_id: UUID,
        variant_id: UUID,
    ) -> Optional[RenderJob]:
        """
        Retry a failed localization pipeline.

        Resets state to 'pending' and creates a render job.
        """
        variant = await self.get_variant(project_id, variant_id)
        if variant is None:
            return None

        if variant.state != "failed":
            raise ValueError(
                f"Cannot retry variant in '{variant.state}' state. "
                f"Only 'failed' variants can be retried."
            )

        variant.state = "pending"

        job = RenderJob(
            project_id=project_id,
            job_type="localisation",
            status="pending",
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(
            f"Language variant retry: variant={variant_id} "
            f"lang={variant.language_code} job={job.id}"
        )

        # Phase 5: dispatch Celery task
        # celery_app.send_task("pipeline.localise", args=[str(job.id), str(variant_id)])

        return job
