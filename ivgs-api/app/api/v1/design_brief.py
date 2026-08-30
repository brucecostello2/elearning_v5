"""Design-brief endpoints (WP-IVGS-12).

- POST /api/v1/projects/{id}/design-brief          — ingest (service token)
- GET  /api/v1/projects/{id}/design-brief          — the stored brief
- GET  /api/v1/projects/{id}/design-review         — the gate's whole review

⛳ THE INGEST IS THE OTHER END OF THE SEAM. `design_core.capture` in the worker
posts here the moment the design model's response is parsed — before the frozen
stage body has written a single scene row, and deliberately so: that body
swallows a non-2xx scene POST (recovery-plan RC-E, open and frozen), and a
brief written first survives scenes that never land.
"""
from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, get_service_or_user
from app.models.storyboard_scene import StoryboardScene
from app.models.transcript import Transcript
from app.models.user import User
from app.schemas.design_brief import (
    DesignBriefIngest,
    DesignBriefResponse,
    DesignReviewResponse,
)
from app.services.design_brief_service import DesignBriefService
from app.services.design_review import review, split
from app.services.project_service import ProjectService
from shared.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}", tags=["Design Brief"])


async def _require_project(project_id: UUID, user: User, db: AsyncSession):
    project = await ProjectService(db).get_project(project_id, user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


@router.get(
    "/design-outcomes",
    summary="This project's learning outcomes, parsed into stable ids",
)
async def get_design_outcomes(
    project_id: UUID,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    """The outcome ids the Design Contract's schema is closed to.

    ⛔ A SEPARATE ROUTE, AND `get_service_or_user`, BECAUSE THE WORKER IS THE
    CALLER. WP-IVGS-12b's first acceptance run armed no enum at all and every
    scene cited an invented `outcome_1`: the worker had been reading
    `GET /projects/{id}`, which takes `get_current_user` and answers a service
    token with 401. The failure was silent by design — `outcome_ids_for_current_project`
    returns [] on any error so a design can still be generated — so the schema
    quietly degraded to an open string and the model went back to inventing ids.

    It returns the PARSE, not the raw text, so the ids the worker closes the
    grammar with and the ids the API later stores are produced by one function.
    """
    project = await _require_project(project_id, current_user, db)
    from shared.design.outcomes import parse_outcomes

    parsed = parse_outcomes(getattr(project, "learning_outcomes", None))
    return {
        "project_id": str(project_id),
        "outcome_ids": [o["id"] for o in parsed],
        "outcomes": parsed,
    }


@router.post(
    "/design-brief",
    response_model=DesignBriefResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record the design contract stage 2 emitted",
)
async def ingest_design_brief(
    project_id: UUID,
    payload: DesignBriefIngest,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    await _require_project(project_id, current_user, db)
    brief = await DesignBriefService(db).record(
        project_id, payload.model_dump(exclude_none=False),
    )
    return DesignBriefResponse.model_validate(brief)


@router.get(
    "/design-brief",
    response_model=DesignBriefResponse,
    summary="The active design brief for this project",
)
async def get_design_brief(
    project_id: UUID,
    current_user: User = Depends(get_service_or_user),
    db: AsyncSession = Depends(get_session),
):
    await _require_project(project_id, current_user, db)
    brief = await DesignBriefService(db).get_active(project_id)
    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This project has no design brief. Storyboards authored before "
                "WP-IVGS-12, or by a pre-v8 prompt, carry none."
            ),
        )
    return DesignBriefResponse.model_validate(brief)


@router.get(
    "/design-review",
    response_model=DesignReviewResponse,
    summary="The storyboard gate's design review — outcomes, arc, evidence, rewrites, drops",
)
async def get_design_review(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Everything Foundation §7 says the reviewer must see before any pixel.

    ⚠ COMPUTED FRESH ON EVERY READ AND WRITING NOTHING, exactly like
    ``GateService.storyboard_completeness``. A stored verdict is a verdict that
    goes stale the moment a reviewer edits a scene, and this gate exists to be
    edited against.
    """
    await _require_project(project_id, current_user, db)
    service = DesignBriefService(db)
    brief = await service.get_active(project_id)

    scenes = list((await db.execute(
        select(StoryboardScene)
        .where(StoryboardScene.project_id == project_id)
        .order_by(StoryboardScene.scene_index)
    )).scalars().all())

    if brief is None:
        return DesignReviewResponse(
            has_brief=False,
            event_arc=[_arc_row(s) for s in scenes],
        )

    # The uploaded script, for the coverage check and for diffing rewrites.
    # `source_text` and NOT `refined_text`: stage 1 PATCHes its own output over
    # `refined_text`, so a span offset means nothing against it (migration 0046).
    source_rows = list((await db.execute(
        select(Transcript)
        .where(Transcript.project_id == project_id)
        .order_by(Transcript.sequence_order)
    )).scalars().all())
    source_text = "\n\n".join(t.source_text or "" for t in source_rows).strip()

    project = await _require_project(project_id, current_user, db)
    findings, rows = review(
        scenes=scenes,
        outcomes=brief.outcomes or [],
        # ⛔ WP-IVGS-12d: the evidence map is NOT passed. `review` derives it
        # from these scene ROWS, which is the live state a reviewer is editing
        # — `brief.evidence_map` was derived at capture and goes stale the
        # moment someone changes a scene's event at the gate.
        assessment_plan=brief.assessment_plan or {},
        dropped_beats=brief.dropped_beats or [],
        source_text=source_text,
        # The belt: what the operator actually typed, so a future regression
        # that routes outcome text back through a model is loud (RC-Q9).
        learning_outcomes=getattr(project, "learning_outcomes", "") or "",
    )
    refusals, flags = split(findings)

    return DesignReviewResponse(
        has_brief=True,
        brief=DesignBriefResponse.model_validate(brief),
        event_arc=[_arc_row(s) for s in scenes],
        coverage=[r.as_dict() for r in rows],
        rewrites=[_rewrite_row(s) for s in scenes if s.rewrite_of],
        dropped_beats=list(brief.dropped_beats or []),
        findings=[f.as_dict() for f in findings],
        refusals=len(refusals),
        flags=len(flags),
    )


def _arc_row(scene: StoryboardScene) -> dict:
    return {
        "scene_index": scene.scene_index,
        "instructional_event": scene.instructional_event,
        "bloom_level": scene.bloom_level,
        "media_type": scene.media_type,
        "serves_outcomes": scene.serves_outcomes or [],
        "media_rationale": scene.media_rationale,
        "scene_origin": scene.scene_origin,
        # WP-IVGS-12f. Beside the origin, never apart from it: an invented scene
        # and the reason it was invented are one fact, and the gate is where a
        # reviewer decides whether the reason is good enough.
        "designed_rationale": scene.designed_rationale,
        "narration_text": scene.narration_text,
        "text_carried_by": scene.text_carried_by,
    }


def _rewrite_row(scene: StoryboardScene) -> dict:
    """A rewrite, with the script's own words beside it.

    Ruling R1a: the designer MAY reword in service of intent, provided every
    rewrite is marked and **the original is shown beside it at the gate**. This
    is that. The reviewer compares two strings; nothing here judges them.
    """
    rewrite = scene.rewrite_of or {}
    return {
        "scene_index": scene.scene_index,
        "original": rewrite.get("original"),
        "rewritten": scene.narration_text,
        "reason": rewrite.get("reason"),
        "span": rewrite.get("span"),
    }
