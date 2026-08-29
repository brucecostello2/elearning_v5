"""The design brief: store what stage 2 designed, and read it back as a review.

WP-IVGS-12 Task 1/Task 5. Instructional Design Foundation §6-§7.

⛔ WHY THE WRITE PATH IS HERE AND NOT IN THE SCENE-CREATE HANDLER

The Design Contract arrives ahead of the scenes. ``design_core.capture`` flushes
it at the moment the model's response is parsed, which is BEFORE the frozen
stage body POSTs a single scene — deliberately, because
``_save_storyboard_scenes`` swallows a non-2xx (recovery-plan RC-E, still open,
still frozen) and a brief written first survives scenes that never arrive.

So the brief is stored whole, and the per-scene columns are applied twice:
once now, for scenes that already exist (a regenerate that reuses rows), and
again from ``StoryboardService.create_scene`` for each scene as it lands. Both
paths call ``apply_scene_design`` and it is idempotent. Applying it in only one
of the two places is what makes an ordering assumption, and there is no ordering
to assume.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.design_brief import StoryboardDesignBrief
from app.models.storyboard_scene import StoryboardScene
from shared.models.enums import (
    BLOOM_LEVELS,
    INSTRUCTIONAL_EVENTS,
    SCENE_ORIGINS,
)

logger = logging.getLogger(__name__)

#: Keys `apply_scene_design` will write onto a scene row. Everything else the
#: contract carries lives on the brief. Named rather than splatted, for the
#: reason freeze exception #2 records: an open passthrough carries whatever a
#: model invents straight into the table.
SCENE_DESIGN_FIELDS = (
    "serves_outcomes",
    "instructional_event",
    "bloom_level",
    "source_refs",
    "scene_origin",
    "rewrite_of",
    "signal_spec",
)


class DesignBriefService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── read ─────────────────────────────────────────────────────────────
    async def get_active(self, project_id: UUID) -> Optional[StoryboardDesignBrief]:
        result = await self.db.execute(
            select(StoryboardDesignBrief)
            .where(
                StoryboardDesignBrief.project_id == project_id,
                StoryboardDesignBrief.is_active.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_briefs(
        self, project_id: UUID, limit: int = 10,
    ) -> List[StoryboardDesignBrief]:
        result = await self.db.execute(
            select(StoryboardDesignBrief)
            .where(StoryboardDesignBrief.project_id == project_id)
            .order_by(StoryboardDesignBrief.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── write ────────────────────────────────────────────────────────────
    async def record(
        self, project_id: UUID, payload: Dict[str, Any],
    ) -> StoryboardDesignBrief:
        """Store one design, superseding the previous ACTIVE one.

        ⛳ SUPERSEDING, NOT OVERWRITING. The previous brief keeps its row with
        ``is_active = false``, so a regenerate leaves the design the reviewer
        was reading still readable. RC-E records a Regenerate button that
        discarded a storyboard with no record; this is the half of that defect
        this package can close without touching the button.
        """
        brief = await self.get_active(project_id)

        # A stage-1 intent post carries only `intent`, and it arrives BEFORE
        # any design exists. It updates the active brief when there is one and
        # opens a fresh one when there is not, so the extraction is never lost
        # waiting for a design that may fail.
        intent_only = "intent" in payload and "scenes" not in payload

        if brief is not None and not intent_only:
            await self.db.execute(
                update(StoryboardDesignBrief)
                .where(StoryboardDesignBrief.id == brief.id)
                .values(is_active=False)
            )
            # Carry the extraction forward: stage 1 wrote it, stage 2 does not
            # re-emit it, and the gate needs it to show a rewrite beside the
            # beat it came from.
            if payload.get("intent") is None and brief.intent is not None:
                payload = {**payload, "intent": brief.intent}
            brief = None

        if brief is not None and intent_only:
            brief.intent = payload.get("intent") or brief.intent
            if payload.get("job_id"):
                brief.job_id = _as_uuid(payload["job_id"])
            await self.db.flush()
            await self.db.commit()
            await self.db.refresh(brief)
            return brief

        brief = StoryboardDesignBrief(
            project_id=project_id,
            job_id=_as_uuid(payload.get("job_id")),
            is_active=True,
            outcomes=payload.get("outcomes") or [],
            dropped_beats=payload.get("dropped_beats") or [],
            evidence_map=payload.get("evidence_map") or {},
            intent=payload.get("intent"),
            raw_contract=payload.get("raw_contract"),
            scene_designs=payload.get("scenes") or [],
            contract_version=payload.get("contract_version"),
            prompt_fingerprint=payload.get("prompt_fingerprint"),
            model_used=payload.get("model_used"),
        )
        self.db.add(brief)
        await self.db.flush()

        applied = 0
        for scene_design in payload.get("scenes") or []:
            applied += await self.apply_scene_design(project_id, scene_design)

        await self.db.commit()
        await self.db.refresh(brief)
        logger.info(
            "design_brief_recorded project=%s outcomes=%d scenes_in_contract=%d "
            "scene_rows_updated=%d dropped=%d",
            project_id,
            len(brief.outcomes or []),
            len(payload.get("scenes") or []),
            applied,
            len(brief.dropped_beats or []),
        )
        return brief

    async def apply_scene_design(
        self, project_id: UUID, scene_design: Dict[str, Any],
    ) -> int:
        """Write one scene's design declarations onto its row, by scene_index.

        Returns the number of rows updated (0 when the scene has not landed
        yet — which is normal and not an error; ``create_scene`` calls this
        again as each scene arrives).

        ⚠ Values that would violate migration 0048's CHECK constraints are
        DROPPED here with a log line rather than sent to the database. The
        constraint is the backstop, not the error surface: a single bad enum
        must not abort the transaction that is storing an otherwise good brief
        for eleven other scenes.
        """
        index = scene_design.get("scene_index")
        if index is None:
            return 0
        values = _clean(scene_design)
        if not values:
            return 0
        result = await self.db.execute(
            update(StoryboardScene)
            .where(
                StoryboardScene.project_id == project_id,
                StoryboardScene.scene_index == index,
            )
            .values(**values)
        )
        return int(result.rowcount or 0)

    async def pending_design_for(
        self, project_id: UUID, scene_index: int,
    ) -> Dict[str, Any]:
        """The design declarations for one scene, off the active brief.

        Called by ``create_scene`` as each scene lands, so a scene row carries
        its declarations from birth rather than being back-filled a moment
        later — which matters because the gate can be opened by the stage
        completion that fires immediately afterwards.
        """
        brief = await self.get_active(project_id)
        if brief is None:
            return {}
        for scene in brief.scene_designs or []:
            if isinstance(scene, dict) and scene.get("scene_index") == scene_index:
                return _clean(scene)
        return {}


def _as_uuid(value: Any) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _clean(scene_design: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known fields carrying values the CHECK constraints allow."""
    out: Dict[str, Any] = {}
    for field in SCENE_DESIGN_FIELDS:
        if field not in scene_design:
            continue
        value = scene_design[field]
        if value is None:
            continue
        if field == "instructional_event" and value not in INSTRUCTIONAL_EVENTS:
            logger.warning("design_brief_bad_event value=%r dropped", value)
            continue
        if field == "bloom_level" and value not in BLOOM_LEVELS:
            logger.warning("design_brief_bad_bloom value=%r dropped", value)
            continue
        if field == "scene_origin" and value not in SCENE_ORIGINS:
            logger.warning("design_brief_bad_origin value=%r dropped", value)
            continue
        if field == "serves_outcomes" and not isinstance(value, list):
            continue
        out[field] = value
    # The XOR, mirrored from the CHECK so a bad pair is dropped rather than
    # aborting the write. `sourced` with no usable refs is NOT a source claim.
    origin = out.get("scene_origin")
    refs = out.get("source_refs")
    if origin == "sourced" and not (isinstance(refs, list) and refs):
        out.pop("scene_origin", None)
        out.pop("source_refs", None)
    if origin == "designed":
        out.pop("source_refs", None)
    return out
