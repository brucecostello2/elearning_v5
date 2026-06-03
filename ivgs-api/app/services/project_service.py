"""
Project service: business logic for project CRUD and state machine.

Enforces:
- 13-state machine transitions per §4.3
- RBAC: operators see own projects, admins see all
- Cascade delete (admin only)
- Pipeline trigger dispatch (stub for Phase 5)
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.render_job import RenderJob
from app.models.language_variant import LanguageVariant
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ActiveJobInfo,
    LanguageVariantSummary,
)
from shared.models.enums import ProjectState, PROJECT_STATE_TRANSITIONS, UserRole

logger = logging.getLogger(__name__)


class ProjectService:
    """Business logic for project management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_projects(
        self,
        current_user: User,
        page: int = 1,
        per_page: int = 50,
        state_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[ProjectResponse], int]:
        """
        List projects with pagination, filtering, and RBAC.

        - Admin: sees all projects
        - Operator: sees own projects only
        - Viewer: sees all projects (read-only)
        """
        query = select(Project).options(
            selectinload(Project.language_variants),
            selectinload(Project.scenes),
        )

        # RBAC: operators see own projects only
        if current_user.role == UserRole.OPERATOR.value:
            query = query.where(Project.created_by == current_user.id)

        # State filter
        if state_filter:
            query = query.where(Project.state == state_filter)

        # Search filter
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Project.name.ilike(search_pattern),
                    Project.description.ilike(search_pattern),
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(Project.updated_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        projects = result.scalars().unique().all()

        responses = []
        for project in projects:
            responses.append(await self._to_response(project))

        return responses, total

    async def get_project(
        self,
        project_id: UUID,
        current_user: User,
    ) -> Optional[ProjectResponse]:
        """Get a single project by ID with RBAC enforcement."""
        project = await self._get_project_or_none(project_id, current_user)
        if project is None:
            return None
        return await self._to_response(project)

    async def get_project_model(
        self,
        project_id: UUID,
        current_user: User,
    ) -> Optional[Project]:
        """Get raw Project model for internal service use."""
        return await self._get_project_or_none(project_id, current_user)

    async def create_project(
        self,
        data: ProjectCreate,
        current_user: User,
    ) -> ProjectResponse:
        """Create a new project in DRAFT state."""
        project = Project(
            name=data.name,
            description=data.description,
            max_runtime_seconds=data.max_runtime_seconds,
            state=ProjectState.DRAFT.value,
            created_by=current_user.id,
        )
        self.db.add(project)
        await self.db.flush()

        # Create language variants if target_languages provided
        if data.target_languages:
            for lang_code in data.target_languages:
                variant = LanguageVariant(
                    project_id=project.id,
                    language_code=lang_code,
                    state="pending",
                )
                self.db.add(variant)

        await self.db.commit()
        await self.db.refresh(project)
        logger.info("Project created: id=%s name=%s by=%s", project.id, repr(project.name), current_user.username)
        return await self._to_response(project)

    async def update_project(
        self,
        project_id: UUID,
        data: ProjectUpdate,
        current_user: User,
    ) -> Optional[ProjectResponse]:
        """Update project metadata (name, description, max_runtime_seconds)."""
        project = await self._get_project_or_none(project_id, current_user)
        if project is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)

        project.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(project)
        logger.info("Project updated: id=%s fields=%s", project.id, list(update_data.keys()))
        return await self._to_response(project)

    async def delete_project(
        self,
        project_id: UUID,
        current_user: User,
    ) -> bool:
        """
        Delete project and all associated assets (admin only, handled by RBAC dep).

        Cascade delete removes transcripts, scenes, assets, prompts, jobs, variants.
        """
        project = await self._get_project_or_none(project_id, current_user, admin_override=True)
        if project is None:
            return False

        await self.db.delete(project)
        await self.db.commit()
        logger.info("Project deleted: id=%s by=%s", project_id, current_user.username)
        return True

    async def transition_state(
        self,
        project_id: UUID,
        new_state: ProjectState,
        current_user: User,
    ) -> Optional[ProjectResponse]:
        """
        Transition project to a new state with validation.

        Enforces valid transitions per §4.3 PROJECT_STATE_TRANSITIONS.
        Raises ValueError on invalid transition.
        """
        project = await self._get_project_or_none(project_id, current_user)
        if project is None:
            return None

        current_state = ProjectState(project.state)
        valid_next = PROJECT_STATE_TRANSITIONS.get(current_state, [])

        if new_state not in valid_next:
            raise ValueError(
                f"Invalid state transition: {current_state.value} → {new_state.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )

        project.state = new_state.value
        project.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(project)
        logger.info(
            f"Project state transition: id={project.id} "
            f"{current_state.value} → {new_state.value}"
        )
        return await self._to_response(project)

    async def trigger_pipeline(
        self,
        project_id: UUID,
        current_user: User,
    ) -> Optional[ProjectResponse]:
        """
        Trigger pipeline execution from current state.

        Stub: In Phase 5, this dispatches a Celery task.
        For now, validates the project is in a triggerable state
        and transitions to the next pipeline stage.
        """
        project = await self._get_project_or_none(project_id, current_user)
        if project is None:
            return None

        current_state = ProjectState(project.state)

        # Only DRAFT and USER_REVIEW are user-triggerable states
        triggerable_states = {
            ProjectState.DRAFT: ProjectState.TRANSCRIPT_REFINEMENT,
            ProjectState.USER_REVIEW: ProjectState.FINAL_RENDER,
        }

        if current_state not in triggerable_states:
            raise ValueError(
                f"Cannot trigger pipeline from state '{current_state.value}'. "
                f"Triggerable states: {[s.value for s in triggerable_states.keys()]}"
            )

        # Check that the project has at least one transcript (for DRAFT → TRANSCRIPT_REFINEMENT)
        if current_state == ProjectState.DRAFT:
            transcript_count = await self.db.scalar(
                select(func.count()).select_from(
                    select(1).where(
                        __import__("app.models.transcript", fromlist=["Transcript"]).Transcript.project_id == project_id
                    ).subquery()
                )
            )
            if not transcript_count:
                raise ValueError("Cannot trigger pipeline: no transcripts uploaded")

        new_state = triggerable_states[current_state]
        project.state = new_state.value
        project.updated_at = datetime.now(timezone.utc)

        # Create a render job record
        job = RenderJob(
            project_id=project.id,
            job_type=new_state.value.lower(),
            status="pending",
        )
        self.db.add(job)

        await self.db.commit()
        await self.db.refresh(project)

        logger.info(
            f"Pipeline triggered: project={project.id} "
            f"{current_state.value} → {new_state.value} "
            f"job={job.id}"
        )

        # P1.5: dispatch the worker orchestrator's real entrypoint.
        # DRAFT -> TRANSCRIPT_REFINEMENT is the pipeline start. USER_REVIEW -> FINAL_RENDER
        # (post-storyboard media resume) is wired separately (P1.5 item 2 / Stage 3).
        if current_state == ProjectState.DRAFT:
            from app.services.celery_producer import celery_app as _pipeline_celery

            job_context = {
                "job_id": str(job.id),
                "project_id": str(project.id),
                "project_name": getattr(project, "name", "") or "",
                "project_description": getattr(project, "description", "") or "",
                "target_audience": getattr(project, "target_audience", "") or "",
                "language_code": getattr(project, "language_code", "en-US") or "en-US",
                "priority": "normal",
                "current_stage": "transcript_refinement",
            }
            dispatch = _pipeline_celery.send_task(
                "tasks.pipeline_orchestrator_v2.dispatch_pipeline",
                kwargs={"job_context_dict": job_context},
                queue="default",
            )
            job.celery_task_id = dispatch.id
            await self.db.commit()
            logger.info(
                f"Pipeline dispatched: project={project.id} job={job.id} "
                f"celery_task={dispatch.id} -> tasks.pipeline_orchestrator_v2.dispatch_pipeline"
            )

        return await self._to_response(project)


    async def approve_storyboard(
        self,
        project_id: UUID,
        current_user: User,
    ) -> Optional[ProjectResponse]:
        """
        P1.5 item 2 - approve the storyboard and start media generation.

        Precondition: the storyboard stage ran and persisted scenes (pipeline paused
        at the post-storyboard gate). Advances the project to MEDIA_GENERATION and
        dispatches dispatch_media_generation, which fans each scene to
        gpu_image / gpu_video by media_type.
        """
        project = await self._get_project_or_none(project_id, current_user)
        if project is None:
            return None

        current_state = ProjectState(project.state)

        if current_state in (
            ProjectState.MEDIA_GENERATION, ProjectState.MANIFEST_GENERATION,
            ProjectState.AUDIO_GENERATION, ProjectState.TALKING_HEAD_RENDER,
            ProjectState.PROTOTYPE_DRAFT, ProjectState.USER_REVIEW,
            ProjectState.FINAL_RENDER, ProjectState.COMPLETE,
        ):
            raise ValueError(
                f"Cannot approve storyboard from state '{current_state.value}': "
                f"media generation already started or past."
            )

        from app.models.storyboard_scene import StoryboardScene

        scene_rows = (
            await self.db.scalars(
                select(StoryboardScene)
                .where(StoryboardScene.project_id == project_id)
                .order_by(StoryboardScene.scene_index)
            )
        ).all()
        if not scene_rows:
            raise ValueError(
                "Cannot approve storyboard: no storyboard scenes persisted for this project."
            )

        job = await self.db.scalar(
            select(RenderJob)
            .where(RenderJob.project_id == project_id)
            .order_by(RenderJob.created_at.desc())
            .limit(1)
        )
        if job is None:
            raise ValueError(
                "Cannot approve storyboard: no render job found for this project."
            )

        scenes = [
            {
                "scene_id": str(s.id),
                "scene_index": s.scene_index,
                "narration_text": s.narration_text,
                "visual_description": s.visual_description,
                "media_type": s.media_type or "image",
                "duration_seconds": s.duration_seconds,
            }
            for s in scene_rows
        ]

        project.state = ProjectState.MEDIA_GENERATION.value
        project.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(project)

        from app.services.celery_producer import celery_app as _pipeline_celery

        dispatch_input = {
            "job_id": str(job.id),
            "project_id": str(project.id),
            "project_name": getattr(project, "name", "") or "",
            "target_audience": getattr(project, "target_audience", "") or "general",
            "language_code": getattr(project, "language_code", "en-US") or "en-US",
            "scenes": scenes,
        }
        dispatch = _pipeline_celery.send_task(
            "tasks.pipeline_orchestrator_v2.dispatch_media_generation",
            kwargs={"dispatch_input": dispatch_input},
            queue="default",
        )
        logger.info(
            f"Storyboard approved: project={project.id} job={job.id} "
            f"scenes={len(scenes)} prev_state={current_state.value} "
            f"celery_task={dispatch.id}"
        )

        return await self._to_response(project)

    async def _get_project_or_none(
        self,
        project_id: UUID,
        current_user: User,
        admin_override: bool = False,
    ) -> Optional[Project]:
        """Fetch project with RBAC enforcement."""
        query = (
            select(Project)
            .options(
                selectinload(Project.language_variants),
                selectinload(Project.scenes),
            )
            .where(Project.id == project_id)
        )

        # RBAC: operators can only access own projects
        if current_user.role == UserRole.OPERATOR.value and not admin_override:
            query = query.where(Project.created_by == current_user.id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _to_response(self, project: Project) -> ProjectResponse:
        """Convert a Project model to a ProjectResponse."""
        # Compute scene count and total duration
        scene_count = len(project.scenes) if project.scenes else 0
        total_duration = None
        if project.scenes:
            durations = [s.duration_seconds for s in project.scenes if s.duration_seconds]
            if durations:
                total_duration = sum(durations)

        # Get hero image URL
        hero_image_url = None
        if project.hero_image_asset_id:
            hero_image_url = f"/api/v1/assets/{project.hero_image_asset_id}/download"

        # Get active job
        active_job = None
        job_result = await self.db.execute(
            select(RenderJob)
            .where(
                and_(
                    RenderJob.project_id == project.id,
                    RenderJob.status.in_(["pending", "running"]),
                )
            )
            .order_by(RenderJob.created_at.desc())
            .limit(1)
        )
        active_job_model = job_result.scalar_one_or_none()
        if active_job_model:
            active_job = ActiveJobInfo(
                id=active_job_model.id,
                job_type=active_job_model.job_type,
                status=active_job_model.status,
                started_at=active_job_model.started_at,
            )

        # Language variant summaries
        variant_summaries = []
        if project.language_variants:
            variant_summaries = [
                LanguageVariantSummary(
                    language_code=v.language_code,
                    state=v.state,
                )
                for v in project.language_variants
            ]

        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            max_runtime_seconds=project.max_runtime_seconds,
            state=project.state,
            hero_image_url=hero_image_url,
            scene_count=scene_count,
            total_duration_estimate_seconds=total_duration,
            created_at=project.created_at,
            updated_at=project.updated_at,
            language_variants=variant_summaries,
            active_job=active_job,
            created_by=project.created_by,
        )
