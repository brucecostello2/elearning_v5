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
from app.models.project import Project
from shared.design.evidence import derive_evidence_map
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

        outcomes_from_project = await self._outcomes_from_the_project(
            project_id, payload.get("outcome_notes") or {},
        )
        brief = StoryboardDesignBrief(
            project_id=project_id,
            job_id=_as_uuid(payload.get("job_id")),
            is_active=True,
            # ⛔ THE OUTCOMES COME FROM THE OPERATOR'S OWN COLUMN, NOT FROM THE
            # MODEL. WP-IVGS-12b, RC-Q9. See `_outcomes_from_the_project`.
            outcomes=outcomes_from_project,
            dropped_beats=payload.get("dropped_beats") or [],
            # ⛔ WP-IVGS-12d: RE-DERIVED HERE, not taken from the payload. The
            # worker derives it too, but it has no outcome-id list at capture
            # time, so its keys are whatever the scenes happened to cite. This
            # derivation is keyed by the OPERATOR's ids, so an outcome no scene
            # assesses gets an explicit `[]` — which is the finding the gate
            # refuses on, and it must not be missing merely because no scene
            # mentioned it.
            evidence_map=derive_evidence_map(
                payload.get("scenes") or [],
                [o["id"] for o in outcomes_from_project],
            ),
            assessment_plan=payload.get("assessment_plan") or {},
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

    async def _outcomes_from_the_project(
        self, project_id: UUID, notes: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """The outcomes, parsed from `projects.learning_outcomes` BY CODE.

        ⛔ THIS IS THE STRUCTURAL CURE FOR RC-Q9 AND IT IS WHY THE MODEL IS NO
        LONGER ASKED. Three consecutive generations transcribed three ABCD
        outcomes as two, reworded, and marked them measurable. A prompt cannot
        fix it and a JSON Schema cannot either, because a paraphrase is a valid
        string. So the text is never round-tripped through the model: code reads
        the column the operator typed into, assigns stable ids, and the model's
        `outcome_notes` — a Bloom level, a measurability judgment, an optional
        ABCD proposal — are merged onto it BY ID.

        The operator's words land in `text` untouched. A refinement lands in
        `proposed_refinement` beside them and is never applied (ruling 1c).
        """
        from shared.design.outcomes import parse_outcomes

        project = await self.db.scalar(
            select(Project).where(Project.id == project_id)
        )
        raw = getattr(project, "learning_outcomes", None) if project else None
        outcomes: List[Dict[str, Any]] = []
        for parsed in parse_outcomes(raw):
            note = notes.get(parsed["id"]) if isinstance(notes, dict) else None
            note = note if isinstance(note, dict) else {}
            outcomes.append({
                "id": parsed["id"],
                # VERBATIM. The one field the model has no way to touch.
                "text": parsed["text"],
                "source": parsed["source"],
                "bloom_level": note.get("bloom_level"),
                "measurable": bool(note.get("measurable", True)),
                "proposed_refinement": note.get("proposed_refinement"),
                "authored_by": "operator",
            })
        return outcomes

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
    """One scene's declarations, WHOLE — every field, with None where absent.

    ⛔ IT WRITES ALL SEVEN OR NONE, AND THAT WAS EARNED BY A CHECK VIOLATION.
    The first draft omitted absent fields, so an UPDATE merged into whatever the
    PREVIOUS generation had left on the row. Measured on 12b's acceptance run:
    generation 1 left scene 6 `sourced` with `source_refs`; generation 2 called
    it `designed`; the update set `scene_origin='designed'` and left the old
    refs behind, and PostgreSQL refused the row —

        new row for relation "storyboard_scenes" violates check constraint
        "ck_storyboard_scenes_source_xor_designed"

    — which cost the whole brief, because the ingest is one transaction.

    ⛳ THE CONSTRAINT WAS RIGHT AND THE WRITER WAS WRONG, which is the good way
    round: the XOR caught a stale declaration that a merge would otherwise have
    left readable and false. Writing the declaration whole also clears the
    leftovers of a design that no longer exists — the RC-Q10 problem, for the
    fields this package owns.
    """
    out: Dict[str, Any] = {field: None for field in SCENE_DESIGN_FIELDS}
    for field in SCENE_DESIGN_FIELDS:
        value = scene_design.get(field)
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

    # The XOR, mirrored from the CHECK so a bad pair is neutralised here rather
    # than aborting the transaction that is storing an otherwise good brief.
    # `sourced` with no usable refs is not a source claim; `designed` never
    # carries refs, and saying so EXPLICITLY is what clears a stale pair.
    origin, refs = out["scene_origin"], out["source_refs"]
    if origin == "sourced" and not (isinstance(refs, list) and refs):
        out["scene_origin"] = None
        out["source_refs"] = None
    if origin == "designed":
        out["source_refs"] = None
    return out
