"""The auto-repair pass — WP-IVGS-12i, RC-R4.

⛳ THE OPERATOR'S RULING, 2026-08-30, and it is the whole design of this module:

    a gate refusal is either MECHANICAL — a deterministic default fix exists —
    or JUDGMENT — a human must decide. Mechanical refusals are REPAIRED BY CODE
    before the gate, DECLARED, never silently. Judgment findings surface to the
    human.

Everything here follows from that one line, including the things it forbids.

WHAT A "DETERMINISTIC DEFAULT EXIT" MEANS, AND WHY THE TEST IS SO NARROW

A refusal is mechanical only when the VALIDATOR ITSELF already names the fix and
that fix needs no taste. `storyboard_completeness` emits exactly four hard
refusals and every one of them is `DELEGATES-TO-WRONG-MEDIUM`; every one of them
is answered by the same sentence its own message prints:

    "author the scene as motion_graphics with a template + parameters (RULE 8)"

That exit is judgment-free because none of its inputs are opinions: the medium
becomes a fixed constant, and the template and its numbers are read out of the
scene's OWN NARRATION by the authoring primitive WP-IVGS-09f already proved and
the Regen path already runs. Nothing is invented and nothing is rewritten.

⛔ THE OTHER EXIT THE SAME MESSAGE OFFERS IS NOT MECHANICAL AND IS NOT TAKEN.
"Set `text_carried_by='narration'` and describe the non-text situation" requires
somebody to REWRITE THE DESCRIPTION so it stops asking for the digits. That is
prose, it is a judgment, and a model asked to produce it is a prompt loop by
another name. So code takes the exit that is arithmetic and leaves the exit that
is authorship to the human — which is also why a repaired scene keeps its
original `visual_description` untouched and declares that it did.

⛔ THERE IS NO RETRY LOOP HERE, AND THAT IS A HARD RULE, NOT A PREFERENCE.
One pass. Each repaired scene gets exactly ONE authoring call — the same proven
per-scene primitive, not a new prompt — and if that call refuses, THE ORIGINAL
REFUSAL STANDS with both errors named. A repair that hid the authoring failure
would be a swallow, and this repository has a register of eighteen of those.

⛔ AND THE SCENE IS PUT BACK. When authoring refuses, `media_type` is reverted to
what it was. Leaving the flip in place would replace one honest refusal with a
different one ("motion_graphics and carries no template") and the reviewer would
be reading a defect this pass introduced.

WHAT IS *NOT* REPAIRED, ARGUED PER KIND (the operator's "argue each")

`design_review` emits sixteen hard refusal codes. **Not one of them is
mechanical**, and they fail the test for three distinct reasons:

  * `OUTCOME_UNSERVED`, `OUTCOME_UNASSESSED`, `OUTCOME_ASSESSED_TWICE`,
    `PLAN_ENTRY_UNREALIZED`, `SCENE_SERVES_NOTHING`, `EVIDENCE_NEAR_DUPLICATE`
    — the fix is a SCENE THAT DOES NOT EXIST, or a decision about which existing
    scene should carry the assessment. Authoring a scene to close a coverage gap
    is designing the course, which is the reviewer's job and the reason the gate
    is there at all.
  * `SCENE_NO_EVENT`, `SCENE_BAD_EVENT`, `SCENE_PROVENANCE_UNDECLARED`,
    `SCENE_CITES_UNKNOWN_OUTCOME`, `SCENE_SOURCED_WITHOUT_REFS` — a DECLARATION
    is missing or wrong. There is no default value for "which of Gagné's nine
    events is this": picking one would be a guess wearing a fact's clothes, and
    the declaration exists precisely so nobody guesses.
  * `OUTCOMES_COUNT_DRIFTED`, `OUTCOMES_TEXT_DRIFTED` — these are the belt that
    proves a REGRESSION shipped (RC-Q9). "Repairing" them would restore the
    operator's words over a model's paraphrase and thereby erase the evidence
    that something rewrote them. The correct response is a loud stop.
  * `MOTION_WITHOUT_TEMPLATE`, `MOTION_UNKNOWN_TEMPLATE`, `MOTION_WITHOUT_PARAMS`
    — these three describe the same state `storyboard_completeness` refuses, and
    the completeness limb is what this pass repairs. They clear as a CONSEQUENCE
    of the repair rather than by a second, separate mechanism; two repairers for
    one defect is the "two builders for one payload" mistake WP-IVGS-09f
    records. They are listed here so a reader does not think they were forgotten.

So the classification table in this module is: four mechanical, twenty judgment.
It is data, not prose, and `MECHANICAL_CODES` is the only thing that decides.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storyboard_scene import StoryboardScene
from app.services.storyboard_completeness import (
    CODE_MOTION_CONTRADICTS_NARRATION,
    CODE_MOTION_WITHOUT_TEMPLATE,
    CODE_NARRATION_TEXT_UNDECLARED,
    CODE_VISUAL_DEMANDS_TEXT,
    SEV_REFUSE,
    assess_storyboard,
)

logger = logging.getLogger(__name__)

#: The medium a mechanical repair moves a scene TO. A constant, not a choice:
#: it is the exit the validator's own refusal message names.
REPAIR_MEDIUM = "motion_graphics"

#: ⛳ THE CLASSIFICATION, AS DATA. Every hard refusal `storyboard_completeness`
#: can emit is here, because all four are `DELEGATES-TO-WRONG-MEDIUM` and all
#: four are answered by the same judgment-free exit. Nothing from
#: `design_review` is here, and the module docstring argues each of those by
#: name. A refusal whose code is absent from this set is JUDGMENT by default,
#: which is the safe direction to be wrong in.
MECHANICAL_CODES = frozenset({
    CODE_VISUAL_DEMANDS_TEXT,
    CODE_NARRATION_TEXT_UNDECLARED,
    CODE_MOTION_WITHOUT_TEMPLATE,
    CODE_MOTION_CONTRADICTS_NARRATION,
})


def is_mechanical(code: Optional[str]) -> bool:
    """Whether this refusal code has a deterministic default exit."""
    return (code or "") in MECHANICAL_CODES


@dataclass
class Correction:
    """One declared repair. ⛔ INCLUDING THE ONES THAT FAILED.

    A correction row is written whether or not the repair took. The failed ones
    are the reason this is a "System corrections" record and not a changelog:
    a reviewer who sees a scene still refused is owed the fact that code TRIED
    and what it was told when it did.
    """

    scene_index: int
    #: The refusal that triggered the repair — code and the validator's words.
    refusal_code: str
    refusal_reason: str
    #: was -> is. Equal when the scene was already `motion_graphics` and only
    #: the template was authored.
    media_type_was: str
    media_type_is: str
    #: True when the scene now carries a template and re-validates clean.
    applied: bool
    template: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    #: ⛳ PRESERVED, NEVER REWRITTEN, and recorded so the reviewer can see that.
    original_visual_description: Optional[str] = None
    #: Set only when authoring refused. Both errors are named, per the ruling.
    repair_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PrunedScene:
    """One surplus row removed because the design of record has no such scene.

    Its content is recorded in full. A row that disappears without a trace is
    the same silent correction the whole ruling forbids, and a reviewer who
    remembers a scene that is no longer there is owed the reason.
    """

    scene_index: int
    instructional_event: Optional[str] = None
    serves_outcomes: List[str] = field(default_factory=list)
    media_type: Optional[str] = None
    narration_text: Optional[str] = None
    #: When the row was last written. The whole argument in one field: every
    #: row the regeneration wrote carries its timestamp, and a pruned row does
    #: not.
    updated_at: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepairPass:
    """What one pass did, and what the gate is left holding."""

    ran_at: str
    scenes: int
    refusals_before: int
    refusals_after: int
    mechanical_before: int
    judgment_before: int
    repaired: int
    repair_refused: int
    corrections: List[Correction] = field(default_factory=list)
    #: RC-S1. Surplus rows removed before anything else ran.
    pruned: List[PrunedScene] = field(default_factory=list)
    #: Why nothing was pruned, when nothing was. ⛔ "There was no surplus" and
    #: "I could not tell whether there was a surplus" are different facts and a
    #: reviewer must be able to tell them apart.
    prune_skipped_because: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ran_at": self.ran_at,
            "pruned": [p.as_dict() for p in self.pruned],
            "prune_skipped_because": self.prune_skipped_because,
            "scenes": self.scenes,
            "refusals_before": self.refusals_before,
            "refusals_after": self.refusals_after,
            "mechanical_before": self.mechanical_before,
            "judgment_before": self.judgment_before,
            "repaired": self.repaired,
            "repair_refused": self.repair_refused,
            "corrections": [c.as_dict() for c in self.corrections],
        }


async def _rows(db: AsyncSession, project_id: UUID) -> List[StoryboardScene]:
    return list(
        (
            await db.scalars(
                select(StoryboardScene)
                .where(StoryboardScene.project_id == project_id)
                .order_by(StoryboardScene.scene_index)
            )
        ).all()
    )


async def prune_scenes_not_in_design(
    db: AsyncSession, project_id: UUID,
) -> "tuple[List[PrunedScene], Optional[str]]":
    """Remove scene rows the ACTIVE design of record does not contain.

    ⛔ WP-IVGS-12i2, RC-S1. THE DEFECT THIS CLOSES, AND IT WAS SELF-DOCUMENTED
    FOR TWO PACKAGES. `StoryboardService.create_scene` upserts by `scene_index`
    and says so in its own docstring
    (`app/services/storyboard_service.py:92-98`):

        "a re-run that produces FEWER scenes than the project already has leaves
         the surplus rows behind. This method sees one scene at a time and
         cannot know the new total ... Trimming needs the whole-storyboard write
         that Stage 2 does not make."

    ⛳ MEASURED ON THE OPERATOR'S LIVE PROJECT, 2026-08-30, and it is what broke
    the per-outcome exactly-one guarantee. The 14:12 generation wrote 19 scenes;
    the 15:42 regeneration designed 17. Rows 17 and 18 survived with
    `updated_at = 14:12:05` while every regenerated row carries `15:42:37`, and
    **row 18 is an `assess` serving LO-3** — so the gate saw LO-3 assessed by
    scene 15 (the new design) AND scene 18 (a design that no longer exists) and
    fired `OUTCOME_ASSESSED_TWICE`. ⛔ **Call 2 was innocent: the active
    contract emits `{LO-1:[9], LO-2:[12], LO-3:[15]}` — exactly one each.** The
    structural guarantee never stopped holding; the database stopped matching
    the contract.

    ⛳ THIS IS THE WHOLE-STORYBOARD WRITE, MADE WHERE IT CAN BE MADE. Not in the
    frozen stage body, and not by counting scenes — by reconciling the rows
    against `scene_designs` on the ACTIVE brief, which RC-Q18 ruled is the
    design of record. Index-set membership, not `index >= count`: a contract
    with a gap in its indices would be trimmed correctly by one and wrongly by
    the other.

    ⛔ IT REFUSES TO GUESS. No active brief, or a brief with no `scene_designs`
    (a stage-1 intent-only post), means this function cannot know what the
    design contains — so it prunes NOTHING and returns the reason, which is
    declared at the gate. A pre-v8 storyboard is left exactly as it is.

    ⚠ WHAT DELETING A ROW TAKES WITH IT, stated rather than discovered later:
    `assets.scene_id` is `ON DELETE SET NULL`, so generated media SURVIVES and
    is merely unlinked; `prompts.scene_id` and `project_model_selections.scene_id`
    are `ON DELETE CASCADE` and go. That is correct for a scene belonging to a
    superseded design, and it is why the full content of every pruned row is
    recorded in the declaration.
    """
    from app.services.design_brief_service import DesignBriefService

    brief = await DesignBriefService(db).get_active(project_id)
    if brief is None:
        return [], (
            "no active design brief — this storyboard predates the Design Core, "
            "so there is no design of record to reconcile the rows against"
        )
    designs = brief.scene_designs or []
    if not designs:
        return [], (
            "the active design brief carries no scene designs (a stage-1 "
            "intent post), so the intended scene set is unknown"
        )

    intended = {
        d.get("scene_index") for d in designs
        if isinstance(d, dict) and isinstance(d.get("scene_index"), int)
    }
    if not intended:
        return [], (
            "the active design brief's scene designs carry no scene_index, so "
            "the intended scene set is unknown"
        )

    rows = await _rows(db, project_id)
    surplus = [r for r in rows if r.scene_index not in intended]
    if not surplus:
        return [], None

    pruned = [
        PrunedScene(
            scene_index=r.scene_index,
            instructional_event=r.instructional_event,
            serves_outcomes=[str(x) for x in (r.serves_outcomes or [])],
            media_type=r.media_type,
            narration_text=r.narration_text,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in surplus
    ]
    await db.execute(
        delete(StoryboardScene).where(
            StoryboardScene.id.in_([r.id for r in surplus])
        )
    )
    await db.commit()
    logger.warning(
        "surplus_scenes_pruned project=%s removed=%s intended=%s — rows from a "
        "superseded design that survived regeneration (RC-S1)",
        project_id, [p.scene_index for p in pruned], sorted(intended),
    )
    return pruned, None


async def auto_repair_storyboard(
    db: AsyncSession, project_id: UUID, project: Any = None,
) -> RepairPass:
    """Repair every mechanical refusal, declare each, re-validate once.

    ⚠ ``authoring_will_run=False`` on BOTH assessments, and that is deliberate.
    The read-path softening exists so the gate panel does not tell a reviewer
    that approving "will be refused" when `approve_storyboard` is about to author
    the missing template anyway. This pass IS that authoring, run earlier, so it
    must see the enforcement truth on the way in and on the way out. Measuring
    the residue against the softened view would report a clean gate over scenes
    that are not.
    """
    from app.services.motion_authoring import (
        MotionAuthoringError,
        author_params_for_scene,
    )

    rows = await _rows(db, project_id)
    before = assess_storyboard(rows, authoring_will_run=False)
    refusals = [a for a in before if a.severity == SEV_REFUSE]
    mechanical = [a for a in refusals if is_mechanical(a.code)]
    judgment = [a for a in refusals if not is_mechanical(a.code)]

    by_index = {r.scene_index: r for r in rows}
    # WP-IVGS-09f's context rule, unchanged: a lesson names each sum's operands
    # once, so the neighbours travel with every authoring ask.
    context_scenes = [(r.scene_index, r.narration_text or "") for r in rows]

    corrections: List[Correction] = []
    for a in mechanical:
        row = by_index.get(a.scene_index)
        if row is None:          # pragma: no cover - index came from these rows
            continue
        was = row.media_type or "image"
        original_visual = row.visual_description
        row.media_type = REPAIR_MEDIUM
        try:
            spec = await author_params_for_scene(
                db,
                project_id=project_id,
                narration=row.narration_text or "",
                visual_description=original_visual or "",
                project_name=(getattr(project, "name", "") or ""),
                project_description=(getattr(project, "description", "") or ""),
                scene_index=row.scene_index,
                context_scenes=context_scenes,
            )
        except MotionAuthoringError as exc:
            # ⛔ THE ORIGINAL REFUSAL STANDS, AND THE SCENE GOES BACK.
            row.media_type = was
            corrections.append(Correction(
                scene_index=row.scene_index,
                refusal_code=a.code,
                refusal_reason=a.reason,
                media_type_was=was,
                media_type_is=was,
                applied=False,
                original_visual_description=original_visual,
                repair_error=str(exc),
            ))
            logger.warning(
                "auto_repair_refused project=%s scene=%s code=%s error=%s",
                project_id, row.scene_index, a.code, exc,
            )
            continue

        row.generation_params = spec
        corrections.append(Correction(
            scene_index=row.scene_index,
            refusal_code=a.code,
            refusal_reason=a.reason,
            media_type_was=was,
            media_type_is=REPAIR_MEDIUM,
            applied=True,
            template=spec.get("template"),
            params={k: v for k, v in spec.items() if k != "template"},
            original_visual_description=original_visual,
        ))
        logger.info(
            "auto_repair_applied project=%s scene=%s %s->%s template=%s",
            project_id, row.scene_index, was, REPAIR_MEDIUM,
            spec.get("template"),
        )

    if corrections:
        await db.commit()

    # ONE re-validation. Not a loop: what refuses now is the gate's honest
    # residue and it belongs to the human.
    after_rows = await _rows(db, project_id)
    after = assess_storyboard(after_rows, authoring_will_run=False)

    result = RepairPass(
        ran_at=datetime.now(timezone.utc).isoformat(),
        scenes=len(rows),
        refusals_before=len(refusals),
        refusals_after=len([a for a in after if a.severity == SEV_REFUSE]),
        mechanical_before=len(mechanical),
        judgment_before=len(judgment),
        repaired=len([c for c in corrections if c.applied]),
        repair_refused=len([c for c in corrections if not c.applied]),
        corrections=corrections,
    )
    logger.info(
        "auto_repair_pass project=%s scenes=%s refusals %s->%s "
        "(mechanical=%s judgment=%s repaired=%s refused=%s)",
        project_id, result.scenes, result.refusals_before,
        result.refusals_after, result.mechanical_before,
        result.judgment_before, result.repaired, result.repair_refused,
    )
    return result


async def repair_and_declare(
    db: AsyncSession, project_id: UUID, project: Any = None,
) -> RepairPass:
    """Run the pass and WRITE THE DECLARATION onto the active design brief.

    ⛳ THE DECLARATION IS THE POINT. A repair nobody can see is exactly the
    silent-correction failure this ruling exists to forbid, so the pass is not
    considered done until the brief carries it — and a pass that repaired
    NOTHING still writes its record, because "code looked and changed nothing"
    and "code never ran" must be distinguishable at the gate.
    """
    from app.services.design_brief_service import DesignBriefService

    # ── RC-S1 FIRST, AND THE ORDER IS THE ARGUMENT ──────────────────────────
    # A surplus row belongs to a design that no longer exists. Repairing one
    # spends an authoring call on a scene that is about to be deleted, and —
    # measured on the operator's regen, 15:42:45Z — the pass reported
    # `scenes: 19` over a 17-scene design and refused repairs on rows that were
    # not part of it. Reconcile the storyboard to its design of record, THEN
    # assess what is actually there.
    pruned, skipped = await prune_scenes_not_in_design(db, project_id)

    result = await auto_repair_storyboard(db, project_id, project)
    result.pruned = pruned
    result.prune_skipped_because = skipped

    brief = await DesignBriefService(db).get_active(project_id)
    if brief is None:
        logger.warning(
            "auto_repair_undeclared project=%s — no active design brief to "
            "record %s correction(s) and %s prune(s) on; a pre-v8 storyboard "
            "carries none",
            project_id, len(result.corrections), len(result.pruned),
        )
        return result

    brief.system_corrections = result.as_dict()
    await db.commit()
    await db.refresh(brief)
    return result
