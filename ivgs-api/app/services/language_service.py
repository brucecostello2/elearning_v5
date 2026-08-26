"""
Language variant service: CRUD for localization targets.

Per §5.1.8 — manages language variant records and retry.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.models.checkpoint import PipelineCheckpoint
from app.models.language_variant import LanguageVariant
from app.models.project import Project
from app.models.render_job import RenderJob

# The eight spec stages (§6.1). The denominator of the progress figure.
SPEC_STAGES = (
    "transcript_refinement",
    "storyboard_generation",
    "media_generation",
    "manifest_generation",
    "audio_generation",
    "talking_head_render",
    "prototype_draft",
    "final_render",
)

# Checkpoints are written at WORKER stage granularity; the progress figure is
# over the eight SPEC stages. Same collapse the Pipeline Tracker applies
# (WP-40 §2.5), kept here so the two surfaces cannot drift apart in what they
# count as one stage.
WORKER_STAGE_TO_SPEC_STAGE = {
    "image_generation": "media_generation",
    "video_generation": "media_generation",
    "animation_generation": "media_generation",
    "composition_manifest": "manifest_generation",
    "tts_audio": "audio_generation",
}

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

    async def variant_progress(
        self,
        project_id: UUID,
        language_code: str,
        is_source_language: bool,
    ) -> Dict[str, Any]:
        """Per-language progress, derived from that variant's checkpoints.

        WP-45 Task 6(c) / WP-43 D-1, RULED derive-never-store.

        The measure is: of the eight pipeline stages, how many have a
        ``complete`` checkpoint on the newest job attributed to this variant.
        Checkpoints are written by the stages themselves as they finish, so this
        number cannot claim progress that did not happen - which is the exact
        property a separately-written column cannot offer.

        Attribution: a job carries ``language_code`` when it renders a specific
        variant (set by ``retry_variant``); NULL means the project's source
        language, which is what every job predating migration 0028 is. So the
        source-language variant reads the project's own pipeline jobs and a
        target-language variant reads only its own runs. A variant that has
        never been rendered returns ``progress_percent=None`` - not 0, because
        "no run" and "a run that has completed nothing" are different facts and
        conflating them is the defect WP-43 found.

        Checkpoints are counted at WORKER stage granularity and collapsed onto
        the eight spec stages, the same collapse the Pipeline Tracker does
        (WP-40 §2.5): image_generation / video_generation / animation_generation
        all belong to MEDIA_GENERATION, so three complete media checkpoints are
        one complete stage, not three.
        """
        job_query = select(RenderJob).where(RenderJob.project_id == project_id)
        if is_source_language:
            # NULL or an explicit match: pre-0028 rows have no attribution and
            # belong to the source language by definition.
            job_query = job_query.where(
                or_(
                    RenderJob.language_code.is_(None),
                    RenderJob.language_code == language_code,
                )
            )
        else:
            job_query = job_query.where(RenderJob.language_code == language_code)

        job = await self.db.scalar(
            job_query.order_by(RenderJob.created_at.desc()).limit(1)
        )
        if job is None:
            return {
                "progress_percent": None,
                "completed_stages": None,
                "total_stages": len(SPEC_STAGES),
                "progress_source": "no render job for this language yet",
            }

        rows = await self.db.execute(
            select(PipelineCheckpoint.stage_name, PipelineCheckpoint.status)
            .where(PipelineCheckpoint.job_id == job.id)
        )
        checkpoints = list(rows.all())
        if not checkpoints:
            return {
                "progress_percent": None,
                "completed_stages": None,
                "total_stages": len(SPEC_STAGES),
                "progress_source": (
                    f"job {job.id} has written no checkpoints yet"
                ),
            }

        complete: set[str] = set()
        for stage_name, cp_status in checkpoints:
            if cp_status != "complete":
                continue
            spec_stage = WORKER_STAGE_TO_SPEC_STAGE.get(stage_name, stage_name)
            if spec_stage in SPEC_STAGES:
                complete.add(spec_stage)

        completed = len(complete)
        percent = round(completed / len(SPEC_STAGES) * 100.0, 1)
        return {
            "progress_percent": percent,
            "completed_stages": completed,
            "total_stages": len(SPEC_STAGES),
            "progress_source": (
                f"derived from {len(checkpoints)} checkpoint(s) on job {job.id}"
            ),
        }

    async def variants_with_progress(
        self, project_id: UUID,
    ) -> List[Tuple[LanguageVariant, Dict[str, Any]]]:
        """Every variant for a project, each with its derived progress.

        The source language is the variant of the project's oldest variant row -
        the one created when the project was, before any localisation target was
        added. ``projects`` has no source-language column, so this is inferred
        rather than read, and the inference is stated here rather than assumed
        at the call site.
        """
        variants = await self.list_variants(project_id)
        if not variants:
            return []
        source_id = min(variants, key=lambda v: v.created_at).id
        out = []
        for variant in variants:
            progress = await self.variant_progress(
                project_id,
                variant.language_code,
                is_source_language=(variant.id == source_id),
            )
            out.append((variant, progress))
        return out

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

        # WP-62 Task 6 (WP-61 D-1, RULED: extend). The fifth dispatch-capable
        # endpoint. `retry_variant` dispatches `dispatch_pipeline` from the
        # localisation start stage over the WHOLE project, so the same argument
        # applies as at the trigger and the regenerate: the variant's own state
        # says nothing about whether a run is already in flight over the
        # project the variant belongs to.
        from app.services.project_service import (
            PipelineAlreadyRunningError,
            active_job,
        )

        running = await active_job(self.db, project_id)
        if running is not None:
            raise PipelineAlreadyRunningError(
                f"Project {project_id} already has a {running.status} "
                f"{running.job_type} run (job {running.id}). Retrying the "
                f"{variant.language_code} localisation now would dispatch a "
                "second pipeline over the same project's assets. Wait for it "
                "to finish, or cancel it.",
                job_id=running.id,
                job_type=running.job_type,
                status=running.status,
            )

        variant.state = "pending"

        job = RenderJob(
            project_id=project_id,
            job_type="localisation",
            status="pending",
            # WP-45 Task 6(c): the attribution that makes per-language progress
            # derivable at all. Without it there is no join from a variant to
            # the checkpoints of the run that produced it.
            language_code=variant.language_code,
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
