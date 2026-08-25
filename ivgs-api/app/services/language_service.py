"""
Language variant service: CRUD for localization targets.

Per §5.1.8 — manages language variant records and retry.
"""
import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.models.language_variant import LanguageVariant
from app.models.project import Project
from app.models.render_job import RenderJob

logger = logging.getLogger(__name__)

# WP-45 Task 3, site 5.
#
# The stub named ``pipeline.localise``. **No such task is registered anywhere in
# the fleet** - a grep across ivgs-workers/tasks for a localisation task name
# returns nothing, and there is no translation stage in STAGE_TASK_MAP. IVGS has
# eight pipeline stages and localisation is not one of them; MBCP's taxonomy has
# a `translation` capability, but that is MBCP's taxonomy, not a stage this
# orchestrator can dispatch (dev/CLAUDE.md §11.1, terminology trap).
#
# What DOES exist is a per-language re-run of the back half: TTS in the target
# language, then talking head, draft and final render, all of which read
# ``language_code`` off the job context. That is what a retry dispatches, and it
# is a real message to a real registered task rather than a name nobody serves.
#
# What it is NOT: a translation. Scene narration is stored once, in the source
# language, and nothing in IVGS translates it. So a retried variant re-renders
# the SOURCE narration with the target language's voice. That is a genuine gap,
# it is recorded in the WP-45 report and the backlog rather than papered over
# here, and the response says so in as many words so an operator pressing Retry
# is not told a translation happened.
LOCALISATION_START_STAGE = "tts_audio"
DISPATCH_PIPELINE_TASK = "tasks.pipeline_orchestrator_v2.dispatch_pipeline"


class LocalisationDispatchError(RuntimeError):
    """A language-variant retry could not be dispatched."""


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
        logger.info("Language variant created: %s for project=%s", language_code, project_id)
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

        project = await self.db.scalar(
            select(Project).where(Project.id == project_id)
        )

        job_context = {
            "job_id": str(job.id),
            "project_id": str(project_id),
            "project_name": getattr(project, "name", "") or "",
            "project_description": getattr(project, "description", "") or "",
            "target_audience": getattr(project, "target_audience", "") or "general",
            # The whole point of the run: every downstream stage reads
            # language_code off the job context.
            "language_code": variant.language_code,
            "priority": "normal",
            "tier": "prototype",
            "current_stage": LOCALISATION_START_STAGE,
        }
        max_runtime = getattr(project, "max_runtime_seconds", None)
        if max_runtime is not None:
            job_context["max_runtime_seconds"] = int(max_runtime)

        from app.services.celery_producer import celery_app as pipeline_celery

        try:
            dispatch = pipeline_celery.send_task(
                DISPATCH_PIPELINE_TASK,
                kwargs={"job_context_dict": job_context},
                queue="default",
            )
        except Exception as exc:
            # The variant goes back to failed and the job row says why. Leaving
            # the variant at 'pending' after a dispatch that did not happen is
            # how the old code made a retry look like it was running.
            variant.state = "failed"
            job.status = "failed"
            job.error_message = f"Localisation dispatch failed: {exc}"
            job.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise LocalisationDispatchError(
                f"could not dispatch localisation for variant {variant_id}: {exc}"
            ) from exc

        job.celery_task_id = dispatch.id
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(
            "Language variant retry dispatched: variant=%s lang=%s job=%s "
            "celery_task=%s start_stage=%s (source narration is NOT translated - "
            "no translation stage exists in IVGS)",
            variant_id, variant.language_code, job.id, dispatch.id,
            LOCALISATION_START_STAGE,
        )

        return job
