"""Recover the storyboard fields Stage 2 authors and then drops in transit.

⛔ ARMED AND INERT TODAY, AND SAYING SO IS THE POINT. Read this whole docstring
before using or removing this module: it recovers nothing on the current fleet,
for a reason that is measured, and it starts working the moment a single frozen
function is edited.

THE DEFECT, MEASURED TWICE ON 2026-08-29 (WP-IVGS-10 Task 1 and Task 5).

v7 asks the storyboard model for three fields beyond the five that reach the
database: ``generation_params`` (RULE 8, asked for since v6 on 2026-08-26),
``media_rationale`` (RULE 9) and ``text_carried_by`` (RULE 1-EXTENDED).
**None of them can arrive.** ``stage2_storyboard.py`` loses them TWICE, and the
second loss is the one this module was first written against — wrongly:

  1. ``_validate_storyboard_json:315-324`` builds each scene with an EXPLICIT
     EIGHT-KEYWORD CONSTRUCTOR::

         scene = StoryboardScene(
             scene_index=..., narration_text=..., visual_description=...,
             media_type=..., duration_seconds=...,
             scene_title=..., transition=..., notes=...,
         )

     Every other key the model emitted is simply not passed. The worker's
     ``StoryboardScene`` IS ``extra="allow"`` — but ``extra`` keeps keys that
     are SUPPLIED, and none are. So the fields are gone here, before the
     checkpoint is written.

  2. ``_save_storyboard_scenes:434-440`` then POSTs five of the eight
     survivors, dropping ``scene_title``, ``transition`` and ``notes``.

⚠ **AN EARLIER DRAFT OF THIS MODULE ASSERTED THAT LOSS (2) WAS THE ONLY ONE**
and that the data survived into ``pipeline_checkpoints`` via ``extra="allow"``.
That was inferred from the model config and it is FALSE, and the acceptance run
is what proved it: project ``5d58f2f5``, storyboard checkpoint
``f9545dae-1948-4b9c-9abe-aa0424b4049b``, 2026-08-29 — twelve scenes, and every
one carries exactly eight keys with no ``generation_params`` on any of the five
the model chose as ``motion_graphics``. Reading the constructor would have said
the same thing; believing the model config did not.

⛔ SO RULE 8 HAS NEVER WORKED AT BIRTH, and this is the third and deepest
reason. WP-IVGS-10 also found that Stage 2 could not even RECEIVE a
``motion_graphics`` scene until this package added the value to ``MediaType``.
Every motion spec that has ever reached a renderer on this fleet was authored
LATER, from the narration alone, by WP-IVGS-09c's Regen path or WP-IVGS-09f's
release path.

WHY THIS MODULE EXISTS ANYWAY, RATHER THAN BEING DELETED.

The fix is inside ``stage2_storyboard.py``, one of the eight FROZEN stage task
bodies (`dev/CLAUDE.md` §3, AD-05 §8: *"Wrapping is allowed; editing is not"*).
This package does not edit it. **Both edits are filed as RC-P1 for the M3.3-R3
window, where the frozen-body edits execute**, and they are small: pass
``**{k: v for k, v in raw_scene.items() if k not in ...}`` at the constructor,
and add the three keys to the payload.

On the day that lands, the checkpoint will carry the fields and this module
recovers them onto rows written before the fix — with every constraint below
already proven by test. Until then it is a no-op that reports honestly
(``reconcile`` returns ``{"filled": 0, "reason": ...}``), and
``test_wpivgs10_reconcile_and_gate.py`` pins BOTH losses so the day somebody
edits either one, the test says so and this module can be retired or activated
deliberately rather than by accident.

TWO USES, ONE SOURCE OF TRUTH

* :func:`authored_fields` READS. It is called on the gate's read path, where a
  write would be a side effect on a GET.
* :func:`reconcile` WRITES, and only ever into a field that is EMPTY. It is
  called from the gate's decision path, which is a POST.

⛔ IT NEVER OVERWRITES. A row whose ``generation_params`` was authored by
WP-IVGS-09f's guarded path, or edited by an operator, is left exactly as it is —
the checkpoint records what the model first said, which is older and less
checked than either. And a scene is matched to its checkpoint entry by
**verbatim narration**, not by index: a re-run that produces a different number
of scenes leaves the indices meaning different things, and matching on them
would attach one scene's template to another scene's words, which is the single
worst outcome available here.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select

from app.models.checkpoint import PipelineCheckpoint
from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene

logger = logging.getLogger(__name__)

#: The fields v7 authors that the frozen stage body's five-key payload drops.
#: Named here once; both the read and the write path iterate this tuple.
CARRIED_FIELDS = ("generation_params", "media_rationale", "text_carried_by")

STAGE_NAME = "storyboard_generation"


def _empty(value: Any) -> bool:
    """Whether a row's field counts as unfilled.

    ``{}`` is empty and ``None`` is empty. The distinction matters: the GUI flip
    leaves ``generation_params = {}`` — an object that exists and says nothing —
    and treating it as filled is precisely the bug WP-IVGS-09c had to write
    ``has_motion_spec`` to avoid.
    """
    if value is None:
        return True
    if isinstance(value, (dict, list, str)) and len(value) == 0:
        return True
    return False


async def _latest_checkpoint_scenes(
    db, project_id: UUID,
) -> List[Dict[str, Any]]:
    """The scene objects from this project's newest storyboard checkpoint.

    Newest rather than first: a storyboard that was regenerated has more than
    one, and the scenes on the table are the ones the newest run wrote.
    """
    row = await db.scalar(
        select(PipelineCheckpoint)
        .join(RenderJob, RenderJob.id == PipelineCheckpoint.job_id)
        .where(
            RenderJob.project_id == project_id,
            PipelineCheckpoint.stage_name == STAGE_NAME,
        )
        .order_by(PipelineCheckpoint.created_at.desc())
        .limit(1)
    )
    if row is None:
        return []
    data = row.checkpoint_data or {}
    scenes = data.get("scenes") if isinstance(data, dict) else None
    return [s for s in scenes if isinstance(s, dict)] if isinstance(scenes, list) else []


async def authored_fields(db, project_id: UUID) -> Dict[str, Dict[str, Any]]:
    """``{verbatim narration: {field: value}}`` for what Stage 2 actually wrote.

    Keyed on the narration because that is the only field that survives the
    transit intact and identifies a scene independently of its position. Only
    the carried fields are returned, and only when they hold something.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for scene in await _latest_checkpoint_scenes(db, project_id):
        key = (scene.get("narration_text") or "").strip()
        if not key:
            continue
        carried = {
            name: scene[name]
            for name in CARRIED_FIELDS
            if name in scene and not _empty(scene[name])
        }
        if carried:
            out[key] = carried
    return out


class _SceneView:
    """A scene row as the gate should READ it, with nothing written.

    Deliberately a thin view rather than a mutated ORM row: setting the
    attribute on the row would leave a dirty object in the session that the next
    ``commit()`` anywhere would flush — a write performed by a GET, by accident,
    at a distance. Everything the completeness classifier reads is copied.
    """

    __slots__ = (
        "scene_index", "media_type", "narration_text", "visual_description",
        "generation_params", "media_rationale", "text_carried_by", "id",
    )

    def __init__(self, row: StoryboardScene, overlay: Dict[str, Any]):
        self.id = row.id
        self.scene_index = row.scene_index
        self.media_type = row.media_type
        self.narration_text = row.narration_text
        self.visual_description = row.visual_description
        for name in CARRIED_FIELDS:
            current = getattr(row, name, None)
            setattr(
                self, name,
                overlay[name] if _empty(current) and name in overlay else current,
            )


async def overlay_authored_fields(
    db, project_id: UUID, scenes: Sequence[StoryboardScene],
) -> List[_SceneView]:
    """The scenes as authored, for a read-only caller. Writes nothing."""
    authored = await authored_fields(db, project_id)
    return [
        _SceneView(s, authored.get((s.narration_text or "").strip(), {}))
        for s in scenes
    ]


async def reconcile(db, project_id: UUID) -> Dict[str, Any]:
    """Persist Stage 2's authored fields onto rows that are missing them.

    Returns a summary rather than nothing, because a repair that reports nothing
    cannot be told from a repair that did nothing — and this repository has a
    standing register of exactly that failure mode.
    """
    authored = await authored_fields(db, project_id)
    if not authored:
        return {"matched": 0, "filled": 0, "fields": {}, "reason": "no storyboard checkpoint carried any of these fields"}

    rows = list(
        (
            await db.scalars(
                select(StoryboardScene)
                .where(StoryboardScene.project_id == project_id)
                .order_by(StoryboardScene.scene_index)
            )
        ).all()
    )

    matched = 0
    filled_by_field: Dict[str, int] = {}
    for row in rows:
        carried = authored.get((row.narration_text or "").strip())
        if not carried:
            continue
        matched += 1
        for name, value in carried.items():
            if not _empty(getattr(row, name, None)):
                continue          # never overwrite; see the module docstring
            setattr(row, name, value)
            filled_by_field[name] = filled_by_field.get(name, 0) + 1
            logger.info(
                "storyboard_reconcile project=%s scene_index=%s field=%s "
                "recovered_from=stage2_checkpoint value=%r",
                project_id, row.scene_index, name, value,
            )

    if filled_by_field:
        # ⛔ NOT `row.updated_at = now()`. That column is the storyboard
        # fingerprint's input (`GateService.storyboard_version`), so touching it
        # would invalidate the very approval this reconcile runs underneath —
        # which is RC-O12 in miniature, and it was measured happening for real
        # in WP-IVGS-09f. Recovering a field the model already authored is not a
        # change to the artefact the human reviewed; it is that artefact
        # arriving intact.
        await db.commit()

    return {
        "matched": matched,
        "filled": sum(filled_by_field.values()),
        "fields": filled_by_field,
        "reason": "",
    }
