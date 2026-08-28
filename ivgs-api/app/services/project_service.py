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

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset

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


# IVGS-0.3: the AD-01 selection tier a run renders at. It was never sent, so
# PipelineJobContext.tier defaulted to "prototype" and every get_binding call in
# every stage resolved prototype — the production tier was unreachable from the
# API. Tier belongs to the RUN, not the project: a project is drafted many times
# before it is rendered for real. The smallest honest version is therefore a
# dispatch parameter defaulting to prototype, so the plumbing exists end to end
# and the API route can surface a per-run choice later without a schema change.
DEFAULT_RENDER_TIER = "prototype"
VALID_RENDER_TIERS = ("prototype", "production")

# WP-61 Task 5 (WP-60 D-3, RULED). The statuses a render job can be in while it
# is still, in any sense, running.
#
# THE `job_status` ENUM HAS FOUR LABELS AND EXACTLY TWO ARE TERMINAL. Read off
# the live type on 2026-08-26: `pending, running, success, failed`. So
# "non-terminal" is the complement of {success, failed}, and it is written that
# way below rather than as a literal {pending, running}: a future label added to
# the enum -- `cancelling`, say -- is non-terminal by default and the guard
# covers it the day it appears. The inverse spelling would silently let a new
# state through.
TERMINAL_JOB_STATUSES = frozenset({"success", "failed"})
NON_TERMINAL_JOB_STATUSES = frozenset({"pending", "running"})


class PipelineAlreadyRunningError(ValueError):
    """A pipeline run for this project is already in flight.

    WP-61 Task 5, WP-60 D-3. **This is not hypothetical.** Six triggers from one
    browser inside 50 seconds each dispatched a full run on project 52d52867 --
    five concurrent pipelines, six talking-head renders, about 3.5 hours of GPU
    time. WP-60 Task 11 was asked to investigate a "loop"; there was no loop.
    There was an unguarded button and a person pressing it.

    A ValueError SUBCLASS deliberately, so that any existing caller that catches
    ValueError around `trigger_pipeline` keeps behaving. The route catches this
    first and answers 409 with its own code, because "you already have a run" is
    a different fact from "you cannot trigger from this state" and an operator
    needs to be able to tell them apart.
    """

    def __init__(self, message: str, *, job_id, job_type: str, status: str):
        super().__init__(message)
        self.job_id = job_id
        self.job_type = job_type
        self.status = status


def _validate_tier(tier: Optional[str]) -> str:
    """Return a known tier, or raise. Never silently coerce to prototype."""
    if tier is None:
        return DEFAULT_RENDER_TIER
    if tier not in VALID_RENDER_TIERS:
        raise ValueError(
            f"Invalid render tier '{tier}'. "
            f"Allowed: {', '.join(VALID_RENDER_TIERS)}"
        )
    return tier


async def active_job(db: AsyncSession, project_id: UUID) -> Optional[RenderJob]:
    """The newest NON-TERMINAL render job for a project, or None.

    WP-61 Task 5 defined this as ``ProjectService._active_job`` for the trigger
    guard. WP-62 Task 6 (WP-61 D-1, RULED: extend) needs the identical question
    answered from ``app.services.regeneration``, which has a session and no
    ProjectService, so the definition moved out here and the method below
    delegates to it. ONE definition of "a run is in flight" -- the whole value
    of the guard is that every dispatch-capable path asks the same question and
    gets the same answer.

    Written as ``NOT IN (terminal)`` rather than ``IN ('pending','running')``
    so a label added to ``job_status`` later is treated as non-terminal until
    somebody decides otherwise. That is the safe direction for a guard.
    """
    return await db.scalar(
        select(RenderJob)
        .where(
            and_(
                RenderJob.project_id == project_id,
                RenderJob.status.not_in(sorted(TERMINAL_JOB_STATUSES)),
            )
        )
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )


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
            # WP-64 Task 6(a). Authored at creation because that is when the
            # author knows what the course is FOR; it is the input the
            # storyboard model judges the scene mix against, and no wording of
            # the prompt can substitute for it not being there.
            learning_outcomes=data.learning_outcomes,
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
        """Update project metadata (name, description, runtime, outcomes).

        WP-64 Task 6(b): ``learning_outcomes`` is editable here and the write is
        NOT retroactive. Scenes are rows a completed run authored; changing this
        field changes what the NEXT storyboard generation reads. The Overview
        panel says so beside the field rather than leaving the operator to find
        out from an unchanged storyboard.
        """
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

    # ``delete_project`` was REMOVED here by WP-59 and lives in
    # ``app/services/project_deletion.ProjectDeletionService``.
    #
    # It was one ``self.db.delete(project)`` and a commit, with a docstring
    # claiming it "queues asset cleanup" -- it queued nothing. What it left
    # behind, measured against the live schema: every SeaweedFS object the
    # project owned (nothing reads the assets rows before the cascade removes
    # them, so the bytes become unreachable rather than deleted), every
    # ``dead_letter_messages`` row naming its jobs and every ``storage_quotas``
    # row (no foreign key reaches either, so they simply survive), and the
    # per-job Redis scratch. It also deleted projects with jobs still running,
    # leaving the GPU work orphaned from its row.
    #
    # It is not kept as a thin wrapper. A second entry point that skips the
    # audit record, the job check and the binary purge is precisely the "second,
    # weaker door" Task 6 forbids, and the only way to guarantee it is not used
    # is for it not to exist.

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

    async def _active_job(self, project_id: UUID) -> Optional[RenderJob]:
        """The newest NON-TERMINAL render job for this project, or None.

        WP-61 Task 5. ONE definition of "a run is in flight", used by the
        trigger guard and by the project payload the button reads. Written as
        `NOT IN (terminal)` rather than `IN ('pending','running')` so a label
        added to `job_status` later is treated as non-terminal until somebody
        decides otherwise -- the safe direction for a guard.
        """
        return await active_job(self.db, project_id)

    async def trigger_pipeline(
        self,
        project_id: UUID,
        current_user: User,
        tier: str = DEFAULT_RENDER_TIER,
    ) -> Optional[ProjectResponse]:
        """
        Trigger pipeline execution from current state.

        Validates the project is in a triggerable state, transitions to the
        next pipeline stage and dispatches the worker orchestrator.

        ``tier`` is the AD-01 selection tier this run renders at (IVGS-0.3).
        """
        tier = _validate_tier(tier)
        project = await self._get_project_or_none(project_id, current_user)
        if project is None:
            return None

        # WP-61 Task 5 (WP-60 D-3, RULED). THE IN-FLIGHT GUARD, AND IT IS FIRST.
        #
        # It runs BEFORE the state check, before the transcript check, before
        # the state write and before the job row -- because everything after it
        # has a side effect and the whole point is that the second press
        # changes nothing at all. A guard placed after the state write would
        # still leave a project moved and a row inserted for a run that never
        # happened.
        #
        # WHY THE PROJECT'S OWN STATE WAS NOT ALREADY A GUARD. It looks like it
        # should have been: DRAFT and USER_REVIEW are the only triggerable
        # states, and a dispatch moves the project out of DRAFT immediately. It
        # is not one, for two measured reasons. The state write and the
        # dispatch are in the same request, so two requests arriving inside one
        # another's window both read DRAFT. And a run that fails part-way leaves
        # the project back in a triggerable state with its jobs still
        # non-terminal. The job table is the thing that knows whether work is
        # outstanding.
        active = await self._active_job(project.id)
        if active is not None:
            raise PipelineAlreadyRunningError(
                f"Project {project_id} already has a {active.status} "
                f"{active.job_type} run (job {active.id}). Wait for it to "
                f"finish, or cancel it, before triggering another. Each "
                f"trigger dispatches a full pipeline and consumes GPU time.",
                job_id=active.id,
                job_type=active.job_type,
                status=active.status,
            )

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

        # WP-62 Task 2(c). THE DRAFT GATE, AND "TRIGGER PIPELINE" CANNOT
        # BYPASS IT.
        #
        # From USER_REVIEW this button IS the final render. Spec v5.1 §6.1 puts
        # a blocking human gate between the prototype draft and Stage 8, and
        # until this package nothing enforced it: the draft gate had a state
        # (USER_REVIEW) and no decision record, so there was nothing to consult
        # and the render started on a draft nobody had approved.
        #
        # It runs AFTER the in-flight guard and BEFORE the state write, for the
        # same reason the in-flight guard runs first: everything below has a
        # side effect, and a refused trigger must leave the project exactly as
        # it found it.
        if current_state == ProjectState.USER_REVIEW:
            from app.services.gate_service import GateService

            await GateService(self.db).require_draft_approval(project_id)

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

        # P1.5 / WP-45 Task 2(b): dispatch the worker orchestrator's real entrypoint.
        #
        # This used to run for DRAFT only. From USER_REVIEW the method flipped the
        # state to FINAL_RENDER, inserted a render_jobs row, logged "Pipeline
        # triggered" - and sent no message. The comment said the other branch was
        # "wired separately (P1.5 item 2 / Stage 3)", but that is the STORYBOARD
        # path (approve_storyboard), not this one. So the "Start final render"
        # button on a reviewed draft moved the project into FINAL_RENDER and
        # nothing ever ran: gate 2 had a door and no corridor behind it
        # (WP-39 §4 Gap B).
        #
        # Both branches now go through dispatch_pipeline, which reads
        # current_stage and builds that stage's input with the orchestrator's own
        # _build_stage_input - so Stage 8 gets its manifest, its talking-head
        # asset and its scene list from the same code path Stage 7 used, rather
        # than from a second, drifting copy of that logic living in the API.
        from app.services.celery_producer import celery_app as _pipeline_celery

        _start_stage = (
            "transcript_refinement"
            if current_state == ProjectState.DRAFT
            else "final_render"
        )
        job_context = {
            "job_id": str(job.id),
            "project_id": str(project.id),
            "project_name": getattr(project, "name", "") or "",
            "project_description": getattr(project, "description", "") or "",
            # WP-64 Task 6(c). Carried as its OWN key from here to the
            # orchestrator, which folds it into the storyboard stage's
            # project_description under an explicit delimiter. It is separate
            # here so that the one place that merges them is the one place that
            # has to be unpicked when the frozen stage body can take a template
            # variable of its own (P2.66). Omitted when the project has none, so
            # a project without outcomes carries no empty key to reason about.
            "target_audience": getattr(project, "target_audience", "") or "",
            "language_code": getattr(project, "language_code", "en-US") or "en-US",
            "priority": "normal",
            "tier": tier,
            "current_stage": _start_stage,
        }
        _outcomes = (getattr(project, "learning_outcomes", None) or "").strip()
        if _outcomes:
            job_context["learning_outcomes"] = _outcomes
        # IVGS-0.1: the project's real runtime budget must reach the stage
        # prompts. Omitted (not defaulted here) when the project genuinely
        # has no value, so PipelineJobContext's 600s default is the ONLY
        # source of that fallback and stays visible as such.
        _max_runtime = getattr(project, "max_runtime_seconds", None)
        if _max_runtime is not None:
            job_context["max_runtime_seconds"] = int(_max_runtime)
        dispatch = _pipeline_celery.send_task(
            "tasks.pipeline_orchestrator_v2.dispatch_pipeline",
            kwargs={"job_context_dict": job_context},
            queue="default",
        )
        job.celery_task_id = dispatch.id
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            f"Pipeline dispatched: project={project.id} job={job.id} "
            f"stage={_start_stage} celery_task={dispatch.id} "
            "-> tasks.pipeline_orchestrator_v2.dispatch_pipeline"
        )

        return await self._to_response(project)

    async def reset_after_terminal_failure(
        self,
        project_id: UUID,
        reason: str,
    ) -> Optional[str]:
        """Return a project to DRAFT after a terminal job failure. P1.4q, RULED.

        A render job fails; the project is left in whatever in-progress state it
        had reached; ``POST /projects/{id}/trigger`` then refuses the retry with
        409 INVALID_STATE_TRANSITION, because the state machine only admits a
        trigger from a resting state. Observed twice on 2026-08-23 during the
        first end-to-end run, and the operator's only recourse was
        ``UPDATE projects SET state='DRAFT'`` by hand.

        **The ruling is DRAFT, and no new state.** The job history keeps the
        record of what failed - render_jobs rows are not touched here - so the
        project does not need a FAILED state to remember it.

        The hop runs through ``transition_state``'s own validation twice, X ->
        ERROR -> DRAFT, rather than assigning DRAFT directly. Both hops are
        sanctioned by PROJECT_STATE_TRANSITIONS (every state may go to ERROR;
        ERROR may return to any of them), so the state machine stays the single
        authority on what is legal instead of acquiring a back door that
        bypasses it.

        Returns the state the project was in, or None if there was nothing to do.
        This is called from a worker callback, so it takes no user and does its
        own RBAC-free lookup deliberately: the pipeline is not a person.
        """
        project = await self.db.scalar(
            select(Project).where(Project.id == project_id)
        )
        if project is None:
            return None

        current_state = ProjectState(project.state)
        if current_state in (ProjectState.DRAFT, ProjectState.COMPLETE):
            # A resting state is already retriggerable. COMPLETE is deliberate:
            # a late failure on a finished project must not silently undo it.
            return None

        now = datetime.now(timezone.utc)
        if current_state is not ProjectState.ERROR:
            if ProjectState.ERROR not in PROJECT_STATE_TRANSITIONS.get(current_state, set()):
                logger.warning(
                    "P1.4q reset skipped: %s has no ERROR transition (project=%s)",
                    current_state.value, project_id,
                )
                return None
            project.state = ProjectState.ERROR.value
            project.updated_at = now
            await self.db.commit()

        project.state = ProjectState.DRAFT.value
        project.updated_at = now
        await self.db.commit()
        await self.db.refresh(project)

        logger.info(
            "P1.4q reset: project=%s %s -> ERROR -> DRAFT (reason=%s). "
            "Job history retained.",
            project_id, current_state.value, reason,
        )
        return current_state.value


    async def approve_storyboard(
        self,
        project_id: UUID,
        current_user: User,
        tier: str = DEFAULT_RENDER_TIER,
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

        # WP-62 Task 2(c). THE RELEASE REQUIRES A RECORDED, CURRENT APPROVAL.
        #
        # This method used to BE the gate: pressing the button dispatched media
        # generation and left no record, so "was this approved?" had no answer
        # and nothing downstream could refuse. It is now the RELEASE half only.
        # `GateService.decide` writes the decision, then calls this; a direct
        # call to `POST /scenes/approve` goes through the same service, so the
        # decision always exists before the dispatch does.
        #
        # The check is not ceremonial. An approval that names an earlier
        # storyboard fails it: re-running Stage 2 moves the artifact
        # fingerprint, so a stale approval cannot release scenes the human
        # never saw.
        from app.services.gate_service import GateService

        await GateService(self.db).require_storyboard_approval(project_id)

        current_state = ProjectState(project.state)

        # Tracked deviation (intentional; see OUTSTANDING_WORK.md / ORCH-5): this guard
        # rejects only MEDIA_GENERATION-and-later, so it accepts earlier states incl.
        # TRANSCRIPT_REFINEMENT. Spec Table 4-3 sanctions only STORYBOARD_GENERATION ->
        # MEDIA_GENERATION; kept lenient to accommodate ORCH-5 (projects.state stays
        # stale after a run). Tighten to require STORYBOARD_GENERATION once ORCH-5 lands.
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

        # WP-IVGS-09f. THE SAME AUTHORING GUARD THE REGEN PATH RUNS, HERE TOO.
        #
        # `_author_missing_motion_specs` gives an unauthored motion scene a
        # template, and — since this package — RE-AUTHORS one whose stored spec
        # `verify_spec_against_narration` can prove contradicts its own
        # narration. It was reachable only from Regen, so this release, which is
        # the OTHER way media gets rendered, would happily dispatch a spec the
        # regen path would have refused.
        #
        # That gap is not theoretical: it is the path that rendered scenes 2, 3,
        # 7 and 10 of project 9c29b1d1 against a sum their words never work.
        # "Must not render" has to mean on every path that renders, or it means
        # nothing. Raises before any job row exists, exactly as it does in Regen.
        from app.services.regeneration import _author_missing_motion_specs

        await _author_missing_motion_specs(self.db, list(scene_rows), project)

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

        # WP-IVGS-09f. THIS LIST USED TO BE HAND-ROLLED HERE, AND IT DROPPED FIVE
        # FIELDS — including `generation_params`, which IS a motion scene's
        # entire content.
        #
        # `regeneration.scene_payload` is the canonical builder every other
        # dispatch uses; it has carried the WP-43 D-2 fields (camera_angle,
        # transition_type, effects, timing_offset_ms, generation_params) since
        # migration 0028. This copy never learned them, so the storyboard
        # release could not dispatch a motion scene's template EVEN WHEN THE ROW
        # HELD A PERFECTLY GOOD ONE.
        #
        # Measured today: after the authoring above wrote correct specs for
        # scenes 2, 3, 7 and 10, all six motion scenes still failed in the worker
        # with "is media_type=motion_graphics but carries no generation_params"
        # — the worker was telling the truth about the MESSAGE, while the
        # database held the spec all along. Two builders for one payload is the
        # defect; there is now one.
        from app.services.regeneration import scene_payload

        scenes = [scene_payload(s) for s in scene_rows]

        project.state = ProjectState.MEDIA_GENERATION.value
        project.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(project)

        from app.services.celery_producer import celery_app as _pipeline_celery

        dispatch_input = {
            "job_id": str(job.id),
            "project_id": str(project.id),
            "project_name": getattr(project, "name", "") or "",
            # IVGS-0.1: the media-resume dispatch carries the same project facts
            # as the pipeline-start dispatch. Without them every stage from here
            # on rebuilt its context from the previous stage's 4-key output.
            "project_description": getattr(project, "description", "") or "",
            "target_audience": getattr(project, "target_audience", "") or "general",
            "language_code": getattr(project, "language_code", "en-US") or "en-US",
            "priority": "normal",
            "tier": _validate_tier(tier),
            "scenes": scenes,
        }
        _max_runtime = getattr(project, "max_runtime_seconds", None)
        if _max_runtime is not None:
            dispatch_input["max_runtime_seconds"] = int(_max_runtime)
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

        # WP-57 Task 1 — the gallery card thumbnail.
        #
        # THE CARD HAD NO PICTURE TO SHOW AND NEVER COULD. `hero_image_asset_id`
        # is NULL on all 17 projects and nothing in the system ever sets it, so
        # `hero_image_url` was always null and every card fell to a placeholder
        # icon. Worse, had it been set, the URL points at `/download`, which sits
        # behind `Depends(get_service_or_user)` — and a browser will not attach a
        # Bearer token to an `<img src>`, so it would have rendered as a broken
        # image (measured: that route answers 403 unauthenticated). WP-40 built
        # `apiClient.blob()` for exactly this and the card did not use it.
        #
        # An ASSET ID, not a URL. The frontend fetches it through the authorised
        # blob path at `GET /assets/{id}/thumbnail?w=` — the route WP-45 Task 6(b)
        # built so cards stop pulling full-size originals.
        #
        # PREFERENCE ORDER, and it is deliberate: the finished render represents
        # the project, a generated still is the next best thing, and nothing else
        # is a picture of the course. `talking_head` is excluded on purpose — a
        # presenter plate is a picture of the ACTOR, not of this project, and
        # every project sharing an actor would show the same card.
        #
        # NULL is a real answer here and the card must render it as one: a
        # project with no renderable asset yet has nothing to show, which is a
        # different fact from a thumbnail that failed to load.
        # WP-60 Task 1(4) — THE PREFERENCE ORDER POINTED AT AN ASSET THE
        # THUMBNAIL ROUTE CANNOT SERVE.
        #
        # This selected `final_render` FIRST. Every final render is an mp4, and
        # `GET /assets/{id}/thumbnail` answers **415 THUMBNAIL_UNSUPPORTED** for
        # anything that is not an `image` (`assets.py:354`, "the API image has
        # no video decoder"). Measured on the live build:
        #
        #   72964509 (double digit multiplication, final_render) -> 415
        #   d23ee9d8 (2B-scenes2-222906,          final_render) -> 415
        #   097a7b72 (e2e-photosynthesis-verify,  image)        -> JPEG bytes
        #
        # Those are exactly the two cards that read "Preview failed to load".
        # The loader was working; it was being handed an asset class the route
        # refuses. So the card reported a transport failure for what is really a
        # permanent property of the asset.
        #
        # The fix is to select what the route can actually render, and to say in
        # words when there is nothing — rather than to hand the card an id that
        # is guaranteed to 415. `talking_head` stays excluded (WP-57: a presenter
        # plate is a picture of the ACTOR, so every project sharing one would
        # show the same card).
        thumb_result = await self.db.execute(
            select(Asset.id)
            .where(
                and_(
                    Asset.project_id == project.id,
                    Asset.asset_type == "image",
                    Asset.storage_tier != "deleted",
                )
            )
            .order_by(Asset.created_at.desc())
            .limit(1)
        )
        thumbnail_asset_id = thumb_result.scalar_one_or_none()

        # When there is no still, the reason matters: a project that has never
        # rendered anything and a finished project whose only output is video
        # are different facts, and the card used to show the same sentence for
        # both (and for a genuine network failure besides).
        thumbnail_unavailable_reason: Optional[str] = None
        if thumbnail_asset_id is None:
            other_result = await self.db.execute(
                select(Asset.asset_type)
                .where(
                    and_(
                        Asset.project_id == project.id,
                        Asset.asset_type != "image",
                        Asset.storage_tier != "deleted",
                    )
                )
                .order_by(
                    case((Asset.asset_type == "final_render", 0), else_=1),
                    Asset.created_at.desc(),
                )
                .limit(1)
            )
            other_type = other_result.scalar_one_or_none()
            if other_type == "final_render":
                thumbnail_unavailable_reason = (
                    "This project's render is finished, but its only visual "
                    "output is video and this API cannot decode video to make a "
                    "still. Open the project to play it."
                )
            elif other_type is not None:
                thumbnail_unavailable_reason = (
                    f"This project has no still image yet; its newest asset is "
                    f"{other_type}."
                )
            else:
                thumbnail_unavailable_reason = "No render yet."

        # Get active job.
        #
        # WP-61 Task 5: through the SAME helper the trigger guard uses. Two
        # copies of "what counts as an active run" is how the button and the
        # server come to disagree about whether one is in flight -- and the
        # button's whole job here is to reflect the server's answer.
        active_job = None
        active_job_model = await self._active_job(project.id)
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
            learning_outcomes=project.learning_outcomes,
            max_runtime_seconds=project.max_runtime_seconds,
            state=project.state,
            hero_image_url=hero_image_url,
            thumbnail_asset_id=thumbnail_asset_id,
            thumbnail_unavailable_reason=thumbnail_unavailable_reason,
            scene_count=scene_count,
            total_duration_estimate_seconds=total_duration,
            created_at=project.created_at,
            updated_at=project.updated_at,
            language_variants=variant_summaries,
            active_job=active_job,
            created_by=project.created_by,
        )
