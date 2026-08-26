"""ONE computation of where a project is, feeding every surface that shows it.

WP-62 Task 3, RULED: the 11-step stepper IS the progress display.

-----------------------------------------------------------------------------
WHAT WAS MEASURED FIRST, AND WHY THIS IS NOT JUST A COLOUR CHANGE
-----------------------------------------------------------------------------

`projects.state` was frozen fleet-wide, and the reason was not "no writer".
A writer exists: WP-45 built `advance_project_state` in the worker and
`PATCH /projects/{id}/state` in the API, and it WORKS -- measured 2026-08-26
on project 64207933, `{"new_state": "STORYBOARD_GENERATION", "event":
"project_state_advanced"}` at 09:00:36, a 200.

What stopped it is `reset_after_terminal_failure` (P1.4q). On the same
project, 400 milliseconds after a human approved the storyboard, a STALE job's
failure callback returned the project to DRAFT; the run carried on through
stages 4, 5 and 6, and all three of its state hops were refused:

    09:07:49  MANIFEST_GENERATION   409 "Invalid state transition: DRAFT -> ..."
    09:07:53  AUDIO_GENERATION      409
    09:08:24  TALKING_HEAD_RENDER   409

c12fa967 is the same story with older timestamps: reset to DRAFT by a failed
`image_generation` at 15:31:10 on 2026-08-25, then a `final_render` that
SUCCEEDED at 15:39:57 whose COMPLETE hop had nowhere legal to go.

The writer is fixed at that choke point (`app/api/v1/jobs.py`). This module is
the other half of the ruling, and it is the half that makes EXISTING projects
true without a hand-edited row.

-----------------------------------------------------------------------------
RECOMPUTE-ON-READ, AS RULED
-----------------------------------------------------------------------------

The ruling offers "recompute-on-read, or an operator block (dry-run first)".
Recompute is the better half of that choice and it is what is built:

  * It needs no write, so no existing project's stored state is touched --
    which the package's own rules require.
  * It is correct for a project whose state column is stale for a reason
    nobody has diagnosed yet, which is every project on this fleet today.
  * It cannot drift, because there is no second copy to drift.

The stepper is computed from THREE facts, in this order of authority:

  1. `pipeline_checkpoints` -- what actually EXECUTED. A checkpoint is written
     by the stage that ran; it is the only record that cannot be wrong about
     whether a stage happened.
  2. The gate decisions -- whether a human is being waited on.
  3. `projects.state` -- where the state machine THINKS the project is. Used
     for the live/active step and for terminal states, never to decide whether
     an earlier stage completed. It has been demonstrably wrong; the
     checkpoints have not.

Checkpoints are read ACROSS every job of the project, not from one run. That
is a deliberate departure from `lib/pipeline-run.ts`, which picks one job and
says so: the Overview run panel answers "how did THIS run go", where a
cross-job merge would paint a stage red that a later run completed. The
stepper answers "how far has this PROJECT got", where the union is the honest
answer -- and it takes the LATEST outcome per stage rather than a pessimistic
merge, so a stage that failed at 15:24 and succeeded at 16:03 is green.

Both surfaces keep their own question. This module does not replace the run
panel; the Overview page renders both, and the WP-60 provenance labels on the
run panel are untouched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import PipelineCheckpoint
from app.models.project import Project
from app.models.project_gate import GATE_DRAFT, GATE_STORYBOARD
from app.models.render_job import RenderJob
from app.services.gate_service import GateService
from app.services.project_service import active_job

logger = logging.getLogger(__name__)

#: The five colours the stepper draws, RULED.
COMPLETE = "complete"   # green
ACTIVE = "active"       # blue
FAILED = "failed"       # red
GATED = "gated"         # amber
PENDING = "pending"     # grey


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    #: Worker `stage_name` values whose checkpoints mark this step as executed.
    #: Empty for the two steps that are not stages: DRAFT is the resting state
    #: before anything runs, and USER_REVIEW is a GATE - nothing executes at
    #: it, a human decides. Colouring them from checkpoints would be inventing
    #: a stage to justify a circle.
    stages: tuple[str, ...] = ()
    #: The gate whose state colours this step amber, if any.
    gate: Optional[str] = None


#: The 11 steps. Identical in order and naming to `ProjectState`'s linear path
#: (shared/models/enums.py) so the stepper and the state machine cannot mean
#: different things by the same word.
STEPS: tuple[Step, ...] = (
    Step("DRAFT", "Draft"),
    Step("TRANSCRIPT_REFINEMENT", "Transcript", ("transcript_refinement",)),
    Step(
        "STORYBOARD_GENERATION", "Storyboard",
        ("storyboard_generation",), gate=GATE_STORYBOARD,
    ),
    Step(
        "MEDIA_GENERATION", "Media",
        ("image_generation", "video_generation", "animation_generation"),
    ),
    Step("MANIFEST_GENERATION", "Manifest", ("composition_manifest",)),
    Step("AUDIO_GENERATION", "Audio", ("tts_audio",)),
    Step("TALKING_HEAD_RENDER", "Talking Head", ("talking_head_render",)),
    Step("PROTOTYPE_DRAFT", "Draft Render", ("prototype_draft",)),
    #: Stage 9 (1-indexed) — Review. THE DRAFT GATE'S HOME, per the ruling.
    Step("USER_REVIEW", "Review", (), gate=GATE_DRAFT),
    Step("FINAL_RENDER", "Final Render", ("final_render",)),
    Step("COMPLETE", "Complete"),
)

STEP_INDEX: Dict[str, int] = {s.key: i for i, s in enumerate(STEPS)}

#: Project tab id -> the step whose status the tab's indicator shows.
#: WP-62 Task 3: the per-tab indicators come from THIS computation, so a tab
#: cannot show a dot the stepper disagrees with. Tabs that are not a pipeline
#: stage (Overview, Prompts, Jobs, Languages) get no indicator rather than a
#: grey one, because a grey dot on Jobs would read as "no jobs".
TAB_STEP: Dict[str, str] = {
    "transcripts": "TRANSCRIPT_REFINEMENT",
    "storyboard": "STORYBOARD_GENERATION",
    "assets": "MEDIA_GENERATION",
    "audio": "AUDIO_GENERATION",
    "talking-head": "TALKING_HEAD_RENDER",
    "draft": "PROTOTYPE_DRAFT",
    "renders": "FINAL_RENDER",
}

#: `render_jobs.job_type` -> the step a running job of that type is working on.
#: Used only to colour the ACTIVE step when a run is in flight and has not yet
#: written a checkpoint for the stage it is on.
JOB_TYPE_STEP: Dict[str, str] = {
    "transcript_refinement": "TRANSCRIPT_REFINEMENT",
    "storyboard_generation": "STORYBOARD_GENERATION",
    "image_generation": "MEDIA_GENERATION",
    "video_generation": "MEDIA_GENERATION",
    "animation_generation": "MEDIA_GENERATION",
    "composition_manifest": "MANIFEST_GENERATION",
    "tts_audio": "AUDIO_GENERATION",
    "talking_head_render": "TALKING_HEAD_RENDER",
    "prototype_draft": "PROTOTYPE_DRAFT",
    "final_render": "FINAL_RENDER",
    "localisation": "FINAL_RENDER",
}


class ProjectProgressService:
    """The stepper, the tab indicators and the run summary, from one read."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _stage_outcomes(
        self, project_id: UUID,
    ) -> Dict[str, tuple[str, datetime]]:
        """Latest outcome per worker stage name, across every job.

        LATEST rather than pessimistic. `lib/pipeline-run.ts` explains why a
        cross-job merge is wrong for the RUN panel -- c12fa967 holds a
        `storyboard_generation` that failed at 15:24 and one that completed at
        16:03, and "any failure wins" would paint a demonstrably completed
        stage red. For the PROJECT stepper the question is "where has this
        project got to", and the last word on a stage is the true one.
        """
        rows = (
            await self.db.execute(
                select(
                    PipelineCheckpoint.stage_name,
                    PipelineCheckpoint.status,
                    PipelineCheckpoint.created_at,
                )
                .join(RenderJob, RenderJob.id == PipelineCheckpoint.job_id)
                .where(RenderJob.project_id == project_id)
                .order_by(PipelineCheckpoint.created_at.asc())
            )
        ).all()
        outcomes: Dict[str, tuple[str, datetime]] = {}
        for stage_name, cp_status, created in rows:
            if not stage_name:
                continue
            outcomes[stage_name] = (cp_status or "", created)
        return outcomes

    async def compute(self, project: Project) -> Dict[str, Any]:
        """Everything the stepper, the tabs and the Overview panel need."""
        project_id = project.id
        outcomes = await self._stage_outcomes(project_id)
        running = await active_job(self.db, project_id)
        gates = await GateService(self.db).all_statuses(project_id)

        state = (project.state or "").upper()
        state_index = STEP_INDEX.get(state, -1)

        # Which step a live run is working on, if any.
        active_key: Optional[str] = None
        if running is not None:
            active_key = JOB_TYPE_STEP.get((running.job_type or "").lower())
            if active_key is None and state_index >= 0:
                active_key = state

        statuses: Dict[str, str] = {}
        for idx, step in enumerate(STEPS):
            statuses[step.key] = self._step_status(
                step, idx, outcomes, state, state_index, active_key, gates,
            )

        # DRAFT is complete the moment anything downstream has happened. A
        # project that has run is not still "in draft", and a green first step
        # is what makes the strip readable as a progress bar rather than a row
        # of lights.
        if any(
            statuses[s.key] in (COMPLETE, ACTIVE, FAILED, GATED)
            for s in STEPS[1:]
        ):
            statuses["DRAFT"] = COMPLETE
        elif state == "DRAFT":
            statuses["DRAFT"] = ACTIVE

        return {
            "project_id": str(project_id),
            "stored_state": project.state,
            # WHETHER THE STORED COLUMN AGREES WITH THE DERIVED POSITION.
            # Not hidden and not corrected: an operator looking at a project
            # whose column says DRAFT over a green Final Render needs to see
            # both facts, because the gap is the WP-62 Task 3 defect and it
            # will exist on every project that ran before this package.
            "derived_state": self._derived_state(statuses),
            "stored_state_matches": self._derived_state(statuses) == project.state,
            "steps": [
                {
                    "index": i + 1,
                    "key": s.key,
                    "label": s.label,
                    "status": statuses[s.key],
                    "gate": s.gate,
                }
                for i, s in enumerate(STEPS)
            ],
            "tabs": {
                tab: statuses[step_key] for tab, step_key in TAB_STEP.items()
            },
            "gates": {name: st.as_dict() for name, st in gates.items()},
            "active_run": (
                {
                    "id": str(running.id),
                    "job_type": running.job_type,
                    "status": running.status,
                    "started_at": (
                        running.started_at.isoformat()
                        if running.started_at else None
                    ),
                    "step": active_key,
                }
                if running is not None
                else None
            ),
        }

    def _step_status(
        self,
        step: Step,
        idx: int,
        outcomes: Dict[str, tuple[str, datetime]],
        state: str,
        state_index: int,
        active_key: Optional[str],
        gates: Dict[str, Any],
    ) -> str:
        # --- gates first. An open gate is the reason the pipeline is not
        # moving, so it outranks everything else this step could be.
        if step.gate is not None:
            gate = gates.get(step.gate)
            if gate is not None and gate.open:
                return GATED

        # --- what actually executed
        seen = [outcomes[name] for name in step.stages if name in outcomes]
        if seen:
            latest_status = max(seen, key=lambda pair: pair[1])[0].lower()
            if latest_status in ("complete", "completed", "success"):
                # A completed stage whose step also carries an APPROVED gate is
                # complete. The gated branch above already returned for an open
                # one.
                return COMPLETE
            if latest_status == "failed":
                return FAILED
            # `pending` / `skipped` checkpoints: the stage was reached and did
            # not finish. Blue if a run is on it, grey otherwise - never green.
            return ACTIVE if active_key == step.key else PENDING

        # --- nothing executed here
        if active_key == step.key:
            return ACTIVE
        if step.key == "COMPLETE" and state == "COMPLETE":
            return COMPLETE
        if state == "ERROR" and state_index == -1 and idx == 0:
            # ERROR has no position on the linear path. The strip says so in
            # the caption rather than colouring a step it does not belong to.
            return PENDING
        return PENDING

    @staticmethod
    def _derived_state(statuses: Dict[str, str]) -> str:
        """The state the stepper implies, for comparison with the column.

        The furthest step that is complete, active, failed or gated. Reported
        rather than written: this package writes no project state by hand.
        """
        furthest = "DRAFT"
        for step in STEPS:
            if statuses[step.key] in (COMPLETE, ACTIVE, FAILED, GATED):
                furthest = step.key
        return furthest
