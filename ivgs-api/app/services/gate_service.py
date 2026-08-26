"""The two human review gates: what they are, and what refuses without them.

WP-62 Task 2. Spec v5.1 §6.1 stage sequence -- 1 -> 2 -> *[gate]* -> 3 -> 4 ->
5 -> 6 -> 7 -> *[gate]* -> 8 -- and §6.4: "the two human review gates
(storyboard approval, draft approval) are implemented as workflow signals: the
workflow blocks at the gate for an unbounded period ... Gates additionally
accept `reject` / `regenerate` signals."

(a) WHAT THE BUTTON DID BEFORE THIS PACKAGE, measured on the running system
2026-08-26 and reported before anything was written:

    surface   ivgs-frontend/src/app/projects/[id]/storyboard/page.tsx:431
              PipelineGateButton label="Approve storyboard"
    endpoint  POST /api/v1/projects/{id}/scenes/approve?tier=
              (ivgs-api/app/api/v1/storyboard.py:232)
    body      ProjectService.approve_storyboard (project_service.py:522)
    writes    projects.state = 'MEDIA_GENERATION'; nothing else
    dispatch  tasks.pipeline_orchestrator_v2.dispatch_media_generation
    readers   NONE

    Live evidence, project 64207933 on 2026-08-26 09:07:47.255Z:
    "Storyboard approved: project=64207933 job=8b881252 scenes=9
     prev_state=STORYBOARD_GENERATION celery_task=36498351". Nine scenes
    released to GPU work, and the only trace of the human decision is that log
    line and a state column that was overwritten 0.4 seconds later.

    The button was therefore a DISPATCHER, not a gate. It had no memory, so it
    had no authority: nothing downstream could ask "was this approved?", so
    nothing refused. That is why this module builds the enforcement BEHIND the
    existing surface rather than adding a second Approve button beside it.

(b) THE ARTIFACT VERSION, and why currency is recomputed rather than stored.

An approval that names only a project claims the project is fine forever. Every
decision here names the artifact it was taken against, and
``storyboard_approval`` / ``draft_approval`` decide currency by recomputing
that fingerprint and comparing. Consequences, all of them wanted:

  * "upstream re-run invalidates downstream approvals" needs no invalidation
    write. Re-running Stage 2 rewrites ``storyboard_scenes.updated_at``, the
    fingerprint moves, and both approvals go stale in the same instant.
  * There is no window in which a crashed invalidator leaves a stale approval
    standing, because nothing was ever asked to invalidate anything.
  * An approval on a project whose artifact then reverts to the approved bytes
    becomes current again, which is correct: the human approved those bytes.

(c) WHAT REFUSES. ``require_*`` are the enforcement points, and they are called
from the trigger layer -- never from inside a stage body. AD-05 §8 freezes the
eight stage task bodies and this package does not touch one.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.checkpoint import PipelineCheckpoint
from app.models.project_gate import (
    DECISION_APPROVE,
    DECISION_REGENERATE,
    DECISION_REJECT,
    DECISIONS,
    GATE_DRAFT,
    GATE_STORYBOARD,
    GATES,
    ProjectGateDecision,
)
from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene
from app.models.user import User

logger = logging.getLogger(__name__)

#: Written when an artifact the gate reviews does not exist yet. It is a real
#: version string rather than None so that a decision row can never be written
#: against "nothing" by accident -- ``decide`` refuses on it explicitly.
ABSENT = "absent"


class GateError(RuntimeError):
    """A gate decision could not be recorded."""


class GateBlocked(RuntimeError):
    """An action was refused because its gate is not currently approved.

    Carries the machine-readable reason so the route can answer 409 with a code
    a surface can branch on, and the human-readable one so the operator is told
    which gate, in which state, over which artifact.
    """

    def __init__(self, message: str, *, gate: str, reason: str):
        super().__init__(message)
        self.gate = gate
        self.reason = reason


@dataclass
class GateStatus:
    """One gate, as the API reports it and as the stepper colours it."""

    gate: str
    #: The artifact as it stands NOW.
    artifact_version: str
    #: True when the newest decision is an approval OF THIS artifact version
    #: (and, for the draft gate, under this storyboard version).
    approved: bool
    #: Whether the gate is waiting on a human right now. A gate whose artifact
    #: does not exist yet is not open -- there is nothing to review.
    open: bool
    decision: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by_name: Optional[str] = None
    note: Optional[str] = None
    #: Why the current decision is not in force, when it is not. Words, not a
    #: boolean: "approved, but the storyboard has been re-run since" and "never
    #: approved" are different situations and an operator must be able to tell
    #: them apart from the payload alone.
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "artifact_version": self.artifact_version,
            "approved": self.approved,
            "open": self.open,
            "decision": self.decision,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by_name": self.decided_by_name,
            "note": self.note,
            "reason": self.reason,
        }


class GateService:
    """Artifact versions, gate state, decisions, and the refusals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -- artifact versions ------------------------------------------------

    async def storyboard_version(self, project_id: UUID) -> str:
        """A fingerprint of the storyboard a human would be approving.

        Over ``(scene_id, scene_index, updated_at)`` for every scene, ordered.
        NOT over the narration text: an edit that changes a scene's text
        without changing its row would be invisible to a text hash only if the
        row did not move, and it always does. Using the ids as well as the
        timestamps means a scene DELETED without any other scene being touched
        still moves the fingerprint.

        Returns ``ABSENT`` when the project has no scenes. That is not a
        version of an empty storyboard; it is the absence of one, and
        ``decide`` refuses to record an approval against it.
        """
        rows = (
            await self.db.execute(
                select(
                    StoryboardScene.id,
                    StoryboardScene.scene_index,
                    StoryboardScene.updated_at,
                )
                .where(StoryboardScene.project_id == project_id)
                .order_by(StoryboardScene.scene_index, StoryboardScene.id)
            )
        ).all()
        if not rows:
            return ABSENT
        digest = hashlib.sha256()
        for scene_id, index, updated in rows:
            digest.update(
                f"{scene_id}|{index}|{updated.isoformat() if updated else ''}\n"
                .encode("utf-8")
            )
        return f"sb-{len(rows)}-{digest.hexdigest()[:32]}"

    async def draft_version(self, project_id: UUID) -> str:
        """A fingerprint of the prototype draft a human would be approving.

        The newest ``prototype_draft`` checkpoint on any of this project's jobs
        IS the draft: it is written by Stage 7 when the draft is produced, and
        its job id plus timestamp identify which run's draft is on screen. A
        re-run of Stage 7 writes a new checkpoint, so the fingerprint moves and
        the previous approval stops being current -- which is the requirement.

        Deliberately NOT ``projects.state == 'USER_REVIEW'``: that column is a
        position, not an artifact, and it has been demonstrably wrong on this
        fleet (WP-62 Task 3). A gate must be anchored to the thing reviewed.
        """
        row = (
            await self.db.execute(
                select(
                    PipelineCheckpoint.id,
                    PipelineCheckpoint.job_id,
                    PipelineCheckpoint.created_at,
                )
                .join(RenderJob, RenderJob.id == PipelineCheckpoint.job_id)
                .where(
                    RenderJob.project_id == project_id,
                    PipelineCheckpoint.stage_name == "prototype_draft",
                )
                .order_by(PipelineCheckpoint.created_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return ABSENT
        _cp_id, job_id, created = row
        stamp = created.isoformat() if created else ""
        return f"dr-{str(job_id)[:8]}-{hashlib.sha256(f'{job_id}|{stamp}'.encode()).hexdigest()[:24]}"

    async def scene_media_version(self, project_id: UUID) -> str:
        """A fingerprint of the CURRENT scene media this project holds.

        WP-63 Task 7(b). A regeneration does not touch a scene row, so it does
        not move ``storyboard_version`` — and it must not, or the approval that
        AUTHORISED the regeneration would be invalidated by its own effect and
        the second regeneration would be refused by the gate that released the
        first.

        What a regeneration does change is the media a draft was assembled
        from. So the DRAFT gate's upstream fingerprint covers the media as well
        as the storyboard: regenerate a scene after the draft was approved and
        that approval stops being current, because the draft on screen was
        built from a frame that is no longer the scene's frame.

        Over the CURRENT (non-superseded) scene-linked assets only. That is
        what makes it move on a regeneration: the new asset joins the set and
        the old one leaves it (migration 0036), so the digest changes even
        though the count does not. Same mechanism as everything else in this
        module — recomputed on read, no invalidation write, nothing to forget.
        """
        from app.models.asset import Asset

        rows = (
            await self.db.execute(
                select(Asset.id, Asset.scene_id, Asset.asset_type)
                .where(
                    Asset.project_id == project_id,
                    Asset.scene_id.isnot(None),
                    Asset.superseded_by.is_(None),
                )
                .order_by(Asset.scene_id, Asset.asset_type, Asset.id)
            )
        ).all()
        if not rows:
            return "media-0"
        digest = hashlib.sha256()
        for asset_id, scene_id, asset_type in rows:
            digest.update(f"{scene_id}|{asset_type}|{asset_id}\n".encode("utf-8"))
        return f"media-{len(rows)}-{digest.hexdigest()[:24]}"

    async def draft_upstream_version(self, project_id: UUID) -> str:
        """Everything a draft is downstream OF: the storyboard and the media.

        Recorded on a draft decision as ``upstream_version`` and recomputed on
        read, so re-running Stage 2 OR regenerating one scene's media both
        invalidate a draft approval.
        """
        return (
            f"{await self.storyboard_version(project_id)}"
            f"+{await self.scene_media_version(project_id)}"
        )

    async def artifact_version(self, project_id: UUID, gate: str) -> str:
        if gate == GATE_STORYBOARD:
            return await self.storyboard_version(project_id)
        if gate == GATE_DRAFT:
            return await self.draft_version(project_id)
        raise GateError(f"unknown gate {gate!r}; known gates: {list(GATES)}")

    # -- gate state -------------------------------------------------------

    async def _latest(
        self, project_id: UUID, gate: str,
    ) -> Optional[ProjectGateDecision]:
        return await self.db.scalar(
            select(ProjectGateDecision)
            .where(
                ProjectGateDecision.project_id == project_id,
                ProjectGateDecision.gate == gate,
            )
            .order_by(ProjectGateDecision.decided_at.desc())
            .limit(1)
        )

    async def status(self, project_id: UUID, gate: str) -> GateStatus:
        """One gate's current state, recomputed from the artifact every time."""
        current = await self.artifact_version(project_id, gate)
        upstream_now = (
            await self.draft_upstream_version(project_id)
            if gate == GATE_DRAFT
            else None
        )
        latest = await self._latest(project_id, gate)

        if current == ABSENT:
            return GateStatus(
                gate=gate,
                artifact_version=current,
                approved=False,
                open=False,
                decision=latest.decision if latest else None,
                decided_at=latest.decided_at if latest else None,
                decided_by_name=latest.decided_by_name if latest else None,
                note=latest.note if latest else None,
                reason=(
                    "the storyboard has not been generated yet"
                    if gate == GATE_STORYBOARD
                    else "no prototype draft has been produced yet"
                ),
            )

        if latest is None:
            return GateStatus(
                gate=gate, artifact_version=current, approved=False, open=True,
                reason="awaiting review: no decision has been recorded",
            )

        stale_artifact = latest.artifact_version != current
        stale_upstream = (
            gate == GATE_DRAFT
            and latest.upstream_version is not None
            and upstream_now is not None
            and latest.upstream_version != upstream_now
        )

        if latest.decision != DECISION_APPROVE:
            reason = (
                f"the last decision was '{latest.decision}'"
                + (" (against an earlier version)" if stale_artifact else "")
            )
            return GateStatus(
                gate=gate, artifact_version=current, approved=False, open=True,
                decision=latest.decision, decided_at=latest.decided_at,
                decided_by_name=latest.decided_by_name, note=latest.note,
                reason=reason,
            )

        if stale_artifact:
            return GateStatus(
                gate=gate, artifact_version=current, approved=False, open=True,
                decision=latest.decision, decided_at=latest.decided_at,
                decided_by_name=latest.decided_by_name, note=latest.note,
                reason=(
                    "approved, but the artifact has changed since: the "
                    f"approval names {latest.artifact_version}, the current "
                    f"one is {current}. Re-approve what is on screen now."
                ),
            )
        if stale_upstream:
            return GateStatus(
                gate=gate, artifact_version=current, approved=False, open=True,
                decision=latest.decision, decided_at=latest.decided_at,
                decided_by_name=latest.decided_by_name, note=latest.note,
                reason=(
                    "approved, but what this draft was built FROM has changed "
                    "since - the storyboard has been re-run, or a scene's "
                    "media has been regenerated. The draft on screen was "
                    "assembled from material that is no longer current."
                ),
            )

        return GateStatus(
            gate=gate, artifact_version=current, approved=True, open=False,
            decision=latest.decision, decided_at=latest.decided_at,
            decided_by_name=latest.decided_by_name, note=latest.note,
            reason="approved and current",
        )

    async def all_statuses(self, project_id: UUID) -> Dict[str, GateStatus]:
        return {g: await self.status(project_id, g) for g in GATES}

    # -- decisions --------------------------------------------------------

    async def decide(
        self,
        project_id: UUID,
        gate: str,
        decision: str,
        *,
        actor: Optional[User],
        note: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> ProjectGateDecision:
        """Record one decision, and write the audit row for it.

        (e) EVERY DECISION WRITES ``audit_log``. Not "every approval": a
        rejection is the decision that stops a render, and an unrecorded
        rejection is exactly as bad as an unrecorded approval when somebody
        later asks why a project sat for three days.
        """
        if gate not in GATES:
            raise GateError(f"unknown gate {gate!r}; known gates: {list(GATES)}")
        if decision not in DECISIONS:
            raise GateError(
                f"unknown decision {decision!r}; the gate accepts "
                f"{list(DECISIONS)}"
            )

        version = await self.artifact_version(project_id, gate)
        if version == ABSENT:
            raise GateError(
                f"there is nothing to decide about at the {gate} gate: the "
                + (
                    "storyboard has not been generated"
                    if gate == GATE_STORYBOARD
                    else "prototype draft has not been produced"
                )
                + ". A decision recorded now would name no artifact."
            )

        upstream = (
            await self.draft_upstream_version(project_id)
            if gate == GATE_DRAFT
            else None
        )
        row = ProjectGateDecision(
            project_id=project_id,
            gate=gate,
            decision=decision,
            artifact_version=version,
            upstream_version=upstream,
            note=note,
            decided_by=actor.id if actor is not None else None,
            decided_by_name=getattr(actor, "username", None),
        )
        self.db.add(row)
        await self.db.flush()

        self.db.add(
            AuditLog(
                user_id=actor.id if actor is not None else None,
                action_type=f"GATE_{gate.upper()}_{decision.upper()}",
                resource_type="project",
                resource_id=project_id,
                before_payload={
                    "gate": gate,
                    "artifact_version": version,
                    "upstream_version": upstream,
                },
                after_payload={
                    "decision": decision,
                    "note": note,
                    "decided_by_name": getattr(actor, "username", None),
                    "gate_decision_id": str(row.id),
                    # The M3.3 signal body, recorded at the moment of the
                    # decision. At cutover the same object is what gets
                    # signalled to the workflow; writing it now means the audit
                    # of a Celery-era decision and a Temporal-era one are the
                    # same shape.
                    "signal": {
                        "name": f"gate_{gate}",
                        "payload": row.signal_payload(),
                    },
                },
                client_ip=client_ip,
            )
        )
        await self.db.commit()
        await self.db.refresh(row)

        logger.info(
            "gate_decision project=%s gate=%s decision=%s version=%s by=%s",
            project_id, gate, decision, version,
            getattr(actor, "username", None) or "-",
        )
        return row

    # -- enforcement ------------------------------------------------------

    async def require_storyboard_approval(self, project_id: UUID) -> GateStatus:
        """Refuse unless the storyboard gate is approved for the CURRENT scenes.

        Called from every path that dispatches media generation. It is NOT
        called from inside a stage body: AD-05 §8 freezes those, and this
        package touches none of them.
        """
        status = await self.status(project_id, GATE_STORYBOARD)
        if not status.approved:
            raise GateBlocked(
                "Media generation is refused: the storyboard review gate is "
                f"not currently approved for this project - {status.reason}. "
                "Approve the storyboard that is on screen now, then retry. "
                "Spec v5.1 section 6.1 makes this gate blocking.",
                gate=GATE_STORYBOARD,
                reason=status.reason,
            )
        return status

    async def require_draft_approval(self, project_id: UUID) -> GateStatus:
        """Refuse unless the draft gate is approved for the CURRENT draft."""
        status = await self.status(project_id, GATE_DRAFT)
        if not status.approved:
            raise GateBlocked(
                "The final render is refused: the draft review gate is not "
                f"currently approved for this project - {status.reason}. "
                "Approve the draft on the Draft Preview tab, then start the "
                "render. Spec v5.1 section 6.1 makes this gate blocking.",
                gate=GATE_DRAFT,
                reason=status.reason,
            )
        return status

    async def history(
        self, project_id: UUID, gate: Optional[str] = None, limit: int = 50,
    ) -> List[ProjectGateDecision]:
        query = select(ProjectGateDecision).where(
            ProjectGateDecision.project_id == project_id
        )
        if gate is not None:
            query = query.where(ProjectGateDecision.gate == gate)
        rows = await self.db.execute(
            query.order_by(ProjectGateDecision.decided_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())
