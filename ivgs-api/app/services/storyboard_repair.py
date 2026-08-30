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
from app.services.design_review import covered_character_count
from app.services.scene_split import (
    Partition, child_events, partition_narration, split_durations,
)
from app.services.storyboard_completeness import (
    CODE_MOTION_CONTRADICTS_NARRATION,
    CODE_MOTION_WITHOUT_TEMPLATE,
    CODE_NARRATION_TEXT_UNDECLARED,
    CODE_VISUAL_DEMANDS_TEXT,
    SEV_REFUSE,
    assess_scene,
    assess_storyboard,
)
from app.services.visual_redescribe import (
    RedescribeRefused, redescribe_scene, redescription_is_legal,
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
    #: WHICH EXIT TOOK IT. "a" author-as-motion-graphics, "c" scene split,
    #: "b" redescribe, or "none" when all three refused. The ruled order is
    #: a → c → b, and a reader must be able to see which one ran without
    #: inferring it from the other fields.
    exit_taken: str = "a"
    template: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    #: ⛳ PRESERVED, NEVER REWRITTEN, and recorded so the reviewer can see that.
    original_visual_description: Optional[str] = None
    #: Set only when authoring refused. Both errors are named, per the ruling.
    repair_error: Optional[str] = None
    #: Exit (b): the description as it now reads. The original is above.
    redescribed_to: Optional[str] = None
    #: Exit (b), when it was not even attempted: WHY the amendment forbade it.
    redescribe_forbidden_because: Optional[str] = None
    #: Exit (c): the child scene's index and the sentence partition, shown so a
    #: reviewer can check that no word moved and none was lost.
    split_into: List[int] = field(default_factory=list)
    split_partition: Dict[str, Any] = field(default_factory=dict)

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
    #: RC-T2. Characters of the uploaded script the design accounts for, before
    #: and after this pass. A DROP is a stage failure — see `stage_failure`.
    coverage_before: int = 0
    coverage_after: int = 0
    #: RC-T2. Mechanical refusals still standing after all three exits ran.
    #: The invariant is that this is ZERO.
    mechanical_after: int = 0
    #: RC-T2. The surviving refusals THEMSELVES, read off the re-validation.
    #:
    #: ⛔ NOT DERIVED FROM `corrections`, AND THAT WAS A DEFECT MEASURED ON THE
    #: ACCEPTANCE RUN. The first cut counted survivors as "corrections that did
    #: not apply", which misses a scene that was never a correction's subject at
    #: all — and it printed a failure saying "1 scene(s) survived" above an
    #: empty list. A message that states a count it cannot name is worse than no
    #: message. These come from the assessment, so the count and the names are
    #: one fact.
    survivors: List[Dict[str, Any]] = field(default_factory=list)

    def stage_failure(self) -> Optional[str]:
        """⛔ THE STAGE-COMPLETE INVARIANT (RC-T2). None means approvable.

        The operator's principle, 2026-08-30: **a correctly completed storyboard
        stage arrives at the gate with ZERO mechanical refusals — only judgment
        flags.** So a surviving mechanical refusal is not a gate finding to be
        rendered in red and shrugged at; it is a STAGE FAILURE, and it says so
        with every scene named and every exit's own sentence quoted.

        ⛳ AND FIDELITY IS PART OF THE SAME INVARIANT. A pass that lowered
        script coverage bought its clean gate by deleting content, which is the
        dilution the amendment forbids. Both conditions are checked here so
        neither can be satisfied at the other's expense.
        """
        problems: List[str] = []
        if self.coverage_after < self.coverage_before:
            problems.append(
                f"the repair pass LOWERED script coverage from "
                f"{self.coverage_before} to {self.coverage_after} characters. A "
                f"repair may never buy a clean gate by losing content "
                f"(operator ruling, 2026-08-30)."
            )
        tried = {c.scene_index: c for c in self.corrections if not c.applied}
        if self.survivors or self.mechanical_after > 0:
            lines = []
            for survivor in self.survivors:
                index = survivor.get("scene_index")
                line = (
                    f"  scene {index} ({survivor.get('code')}): "
                    f"{survivor.get('reason')}"
                )
                correction = tried.get(index)
                if correction is not None:
                    line += (
                        f"\n      exits tried -> "
                        f"{correction.repair_error or 'none recorded'}"
                    )
                    if correction.redescribe_forbidden_because:
                        line += (
                            f"\n      exit (b) forbidden: "
                            f"{correction.redescribe_forbidden_because}"
                        )
                else:
                    line += (
                        "\n      no exit was attempted for this scene — it was "
                        "not among the refusals the pass set out to repair, "
                        "which means it appeared or changed during the pass"
                    )
                lines.append(line)
            problems.append(
                f"{self.mechanical_after or len(self.survivors)} scene(s) "
                f"survived every exit and still delegate written or numeric "
                f"content to a medium that cannot draw it:\n"
                + ("\n".join(lines) if lines else
                   "  (the re-validation reported none by name — this is itself "
                   "a defect in the pass and must be investigated)")
            )
        if not problems:
            return None
        return (
            "STAGE NOT APPROVABLE. A completed storyboard stage must reach the "
            "gate with ZERO mechanical refusals — only judgment flags.\n\n"
            + "\n\n".join(problems)
            + "\n\nRegenerate the storyboard, or edit the named scenes and "
            "re-run. The gate's refusal machinery still stands behind this as "
            "the belt; this is the stage refusing to report success it did not "
            "have."
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ran_at": self.ran_at,
            "pruned": [p.as_dict() for p in self.pruned],
            "prune_skipped_because": self.prune_skipped_because,
            "coverage_before": self.coverage_before,
            "coverage_after": self.coverage_after,
            "mechanical_after": self.mechanical_after,
            "survivors": list(self.survivors),
            "stage_failure": self.stage_failure(),
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



class SceneSplitRefused(RuntimeError):
    """The split could not be made, and the sentence says why."""


async def _split_scene(
    db: AsyncSession,
    *,
    project_id: UUID,
    parent: StoryboardScene,
    part: Partition,
    project: Any,
    context_scenes: List[Any],
) -> int:
    """Exit (c). Cut one scene in two and author the digit half. Returns the
    child's `scene_index`.

    ⛔ THE ORDER OF WRITES MATTERS AND IS NOT INTERCHANGEABLE.

      1. **Author the digit child's template FIRST, before any row moves.** If
         the authoring refuses, this function raises and nothing has been
         written — the storyboard is exactly as it was and the caller records a
         refusal naming both exits. Renumbering first and failing second would
         leave the storyboard shuffled by a repair that did not happen.
      2. Shift every later scene up by one, **descending**, so no two rows hold
         one index even transiently.
      3. Insert the child immediately after its parent.
      4. ⛳ **Rewrite the ACTIVE BRIEF's `scene_designs` to match.** This is not
         bookkeeping, it is load-bearing: RC-S1's `prune_scenes_not_in_design`
         deletes any row the design of record does not contain, so a child that
         is not added to the contract would be **deleted by the very next pass**
         — and every later scene's design entry would point at the wrong row.
    """
    from app.services.motion_authoring import author_params_for_scene
    from app.services.design_brief_service import DesignBriefService

    if not part.is_mixed:                    # pragma: no cover - caller checks
        raise SceneSplitRefused("the narration does not mix content and context")

    # 1. the digit child's template, before anything moves.
    spec = await author_params_for_scene(
        db,
        project_id=project_id,
        narration=part.digit_text,
        visual_description=parent.visual_description or "",
        project_name=(getattr(project, "name", "") or ""),
        project_description=(getattr(project, "description", "") or ""),
        scene_index=parent.scene_index,
        context_scenes=context_scenes,
    )

    parent_index = parent.scene_index
    child_index = parent_index + 1
    context_event, digit_event = child_events(parent.instructional_event)
    context_seconds, digit_seconds = split_durations(
        parent.duration_seconds, part,
    )

    # 2. make room, descending.
    later = [
        r for r in await _rows(db, project_id) if r.scene_index > parent_index
    ]
    for row in sorted(later, key=lambda r: r.scene_index, reverse=True):
        row.scene_index += 1

    # 3. the parent keeps the CONTEXT half and its medium; the child takes the
    #    digits and is drawn.
    parent.narration_text = part.context_text
    parent.instructional_event = context_event
    parent.duration_seconds = context_seconds

    child = StoryboardScene(
        project_id=project_id,
        scene_index=child_index,
        narration_text=part.digit_text,
        # ⛳ The parent's description travels with the child unchanged. The
        # renderer draws from the template and never reads it, and rewriting it
        # here would be exit (b) smuggled in under exit (c).
        visual_description=parent.visual_description,
        media_type=REPAIR_MEDIUM,
        generation_params=spec,
        duration_seconds=digit_seconds,
        instructional_event=digit_event,
        # BOTH children, unchanged — this is what makes the spans reunite.
        serves_outcomes=list(parent.serves_outcomes or []),
        bloom_level=parent.bloom_level,
        text_carried_by=parent.text_carried_by,
        media_rationale=(
            f"split from scene {parent_index} by the auto-repair pass: this "
            f"half is digit work and is drawn from a template, so the numerals "
            f"cannot be misspelled"
        ),
        # ⛔ THE CHILD INHERITS ITS PARENT'S PROVENANCE EXACTLY, AND THIS WAS A
        # DESIGN ERROR CAUGHT BY MIGRATION 0048's XOR CONSTRAINT RATHER THAN BY
        # ME. The first cut marked every child `designed` while still copying
        # the parent's `source_refs`, and the database refused it:
        # `ck_storyboard_scenes_source_xor_designed` says a designed scene
        # carries no spans and a sourced scene carries at least one.
        #
        # ⛳ THE CONSTRAINT WAS RIGHT AND THE CODE WAS WRONG. A split MOVES
        # sentences; it does not write them. The digit half of a `sourced`
        # scene's narration came from the uploaded script exactly as much as the
        # parent's did, so calling the child `designed` would claim this pass
        # invented words it only relocated — and would drop the spans, which is
        # the fidelity loss RC-T2 exists to forbid. The child is therefore
        # `sourced` with the parent's spans when the parent was, and `designed`
        # with no spans when the parent was, in both cases carrying the parent's
        # own rationale plus a note that a split happened.
        scene_origin=parent.scene_origin,
        source_refs=(
            [dict(r) for r in (parent.source_refs or [])]
            if (parent.scene_origin or "") == "sourced" else None
        ),
        designed_rationale=(
            (
                (parent.designed_rationale or "")
                + (" " if parent.designed_rationale else "")
                + f"Split from scene {parent_index} by WP-IVGS-12i3 exit (c): "
                f"the scene mixed context with digit work and one medium could "
                f"not serve both. The narration was partitioned at sentence "
                f"boundaries by code; no word was changed."
            ).strip()
            if (parent.scene_origin or "") == "designed" else None
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(child)
    await db.flush()

    # 4. the design of record must contain the child, or the prune eats it.
    service = DesignBriefService(db)
    brief = await service.get_active(project_id)
    if brief is None:
        raise SceneSplitRefused(
            "there is no active design brief to record the new scene on, and a "
            "child absent from the design of record would be pruned by the very "
            "next pass"
        )
    designs = [dict(d) for d in (brief.scene_designs or []) if isinstance(d, dict)]
    for design in designs:
        index = design.get("scene_index")
        if isinstance(index, int) and index > parent_index:
            design["scene_index"] = index + 1
    parent_design = next(
        (d for d in designs if d.get("scene_index") == parent_index), {},
    )
    child_design = dict(parent_design)
    child_design.update({
        "scene_index": child_index,
        "instructional_event": digit_event,
        "scene_origin": child.scene_origin,
        "source_refs": child.source_refs,
        "designed_rationale": child.designed_rationale,
        "narration_text": part.digit_text,
    })
    if parent_design:
        parent_design["instructional_event"] = context_event
        parent_design["narration_text"] = part.context_text
    designs.append(child_design)
    designs.sort(key=lambda d: d.get("scene_index", 0))
    brief.scene_designs = designs
    await db.flush()
    return child_index


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

        def _survives(exits: str, forbidden: Optional[str] = None) -> None:
            corrections.append(Correction(
                scene_index=row.scene_index,
                refusal_code=a.code, refusal_reason=a.reason,
                media_type_was=was, media_type_is=was,
                applied=False, exit_taken="none",
                original_visual_description=original_visual,
                repair_error=exits,
                redescribe_forbidden_because=forbidden,
            ))
            logger.warning(
                "auto_repair_refused project=%s scene=%s code=%s exits=%s",
                project_id, row.scene_index, a.code, exits,
            )

        async def _try_redescribe(after: str) -> bool:
            """Exit (b). Returns True when it was applied.

            ⛔ NARROWED BY THE AMENDMENT OF 2026-08-30: legal ONLY where the
            on-screen text is incidental to the scene's declared purpose. The
            legality test reads the design contract — `instructional_event` and
            `media_rationale` — and is applied BEFORE any model is called, so a
            content scene is never even offered for rewriting.
            """
            legal, why = redescription_is_legal(
                instructional_event=row.instructional_event,
                narration_text=row.narration_text,
                media_rationale=row.media_rationale,
            )
            if not legal:
                _survives(after, forbidden=why)
                return False
            if a.code != CODE_VISUAL_DEMANDS_TEXT:
                _survives(
                    f"{after}  ||  exit (b): not applicable — this refusal is "
                    f"{a.code}, so the DESCRIPTION demands nothing and "
                    f"rewriting it would change nothing"
                )
                return False
            try:
                rewritten = await redescribe_scene(
                    db, project_id=project_id,
                    narration=row.narration_text or "",
                    visual_description=original_visual or "",
                    scene_index=row.scene_index,
                )
            except Exception as red_exc:
                if not isinstance(red_exc, RedescribeRefused):
                    logger.warning(
                        "redescribe_call_failed project=%s scene=%s error=%s",
                        project_id, row.scene_index, red_exc,
                    )
                _survives(f"{after}  ||  exit (b): {red_exc}")
                return False
            row.visual_description = rewritten
            corrections.append(Correction(
                scene_index=row.scene_index,
                refusal_code=a.code, refusal_reason=a.reason,
                media_type_was=was, media_type_is=was,
                applied=True, exit_taken="b",
                original_visual_description=original_visual,
                redescribed_to=rewritten,
                repair_error=after,
            ))
            logger.info(
                "auto_repair_redescribed project=%s scene=%s",
                project_id, row.scene_index,
            )
            return True

        # ── THE RULED ORDER, AND ITS GUARDS ARE CONDITIONS, NOT JUST SEQUENCE ─
        #
        #   (a) author the whole scene as motion_graphics WHERE THE TEMPLATE
        #       FITS THE WHOLE NARRATION
        #   (c) SPLIT WHERE THE NARRATION MIXES CONTENT AND CONTEXT
        #   (b) redescribe ONLY WHERE THE TEXT DEMAND IS INCIDENTAL
        #
        # ⛔ SO A MIXED NARRATION GOES STRAIGHT TO (c), AND THIS IS A CORRECTION
        # TO THIS PASS'S FIRST CUT. That version attempted (a) first and fell
        # through to (c) only when authoring REFUSED — but on the operator's own
        # opener, *"Hi! Today… That might sound tricky, but don't worry… By the
        # end, you'll be able to solve a problem like 23 times 14 all by
        # yourself"*, exit (a) SUCCEEDS: the words contain "multiply", 23 and 14,
        # so a `column_multiplication_step` is authored and the guard passes it.
        # The result would be a warm welcome to an anxious nine-year-old
        # rendered as an animated column sum. That is precisely the failure the
        # amendment describes, reached by a repair that reported success.
        #
        # "Fits the whole narration" is the test, and a narration that mixes a
        # welcome with an operand does not meet it.
        part = partition_narration(row.narration_text)
        if part.is_mixed:
            try:
                child_index = await _split_scene(
                    db, project_id=project_id, parent=row, part=part,
                    project=project, context_scenes=context_scenes,
                )
            except (MotionAuthoringError, SceneSplitRefused) as split_exc:
                await _try_redescribe(f"exit (c): {split_exc}")
                continue
            corrections.append(Correction(
                scene_index=row.scene_index,
                refusal_code=a.code, refusal_reason=a.reason,
                media_type_was=was, media_type_is=was,
                applied=True, exit_taken="c",
                original_visual_description=original_visual,
                split_into=[row.scene_index, child_index],
                split_partition=part.as_dict(),
            ))
            logger.info(
                "auto_repair_split project=%s parent=%s child=%s "
                "digit_sentences=%s context_sentences=%s",
                project_id, row.scene_index, child_index,
                len(part.digit_sentences), len(part.context_sentences),
            )

            # ── THE CONTEXT PARENT IS RE-EXAMINED ONCE, AND THIS IS NOT A LOOP.
            #
            # ⛔ MEASURED ON THE ACCEPTANCE RUN, 2026-08-30, AND IT IS THE ONE
            # THING THE SPLIT DOES NOT FINISH BY ITSELF. Scene 6 narrated *"Do
            # not worry, this is easier than it looks. Now multiply 4 times 3…"*
            # under the description *"A worksheet showing the multiplication
            # problem and the calculations."* The split moved the digits out of
            # the NARRATION and left the DESCRIPTION still demanding them, so the
            # parent went on refusing and the stage failed over a scene the pass
            # had just repaired.
            #
            # ⛳ THE PARENT'S INPUTS CHANGED, so re-examining it is not a retry
            # of anything: the legality test now reads a narration that states
            # no written or numeric content at all, which is precisely the case
            # where a leftover text demand IS incidental. One further exit-(b)
            # call for the parent, at most, and never a second attempt at the
            # same call with the same inputs.
            parent_now = assess_scene(
                scene_index=row.scene_index,
                media_type=row.media_type,
                narration_text=row.narration_text,
                visual_description=row.visual_description,
                generation_params=row.generation_params,
                text_carried_by=row.text_carried_by,
                media_rationale=row.media_rationale,
                context_text=" ".join(t or "" for _, t in context_scenes),
            )
            if parent_now.severity == SEV_REFUSE and is_mechanical(parent_now.code):
                a, original_visual = parent_now, row.visual_description
                await _try_redescribe(
                    f"exit (c) split this scene at {row.scene_index}; its "
                    f"description still asked for text afterwards"
                )
            continue

        # ── EXIT (a): the template fits the whole narration ──────────────────
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
            # ⛔ THE SCENE GOES BACK FIRST, ALWAYS — leaving the flip in place
            # would replace one honest refusal with a different one this pass
            # created.
            row.media_type = was
            await _try_redescribe(f"exit (a): {exc}")
            continue

        row.generation_params = spec
        corrections.append(Correction(
            scene_index=row.scene_index,
            refusal_code=a.code,
            refusal_reason=a.reason,
            media_type_was=was,
            media_type_is=REPAIR_MEDIUM,
            applied=True,
            exit_taken="a",
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

    after_refusals = [a for a in after if a.severity == SEV_REFUSE]
    result = RepairPass(
        ran_at=datetime.now(timezone.utc).isoformat(),
        scenes=len(after_rows),
        refusals_before=len(refusals),
        refusals_after=len(after_refusals),
        mechanical_after=len([a for a in after_refusals if is_mechanical(a.code)]),
        survivors=[
            {"scene_index": a.scene_index, "code": a.code, "reason": a.reason}
            for a in after_refusals if is_mechanical(a.code)
        ],
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



async def _fidelity_inputs(
    db: AsyncSession, project_id: UUID,
) -> "tuple[str, List[Dict[str, Any]]]":
    """The uploaded script and the design's declared drops, for the coverage
    measurement.

    ⛳ `source_text` and NOT `refined_text`, for RC-Q2's reason: stage 1 PATCHes
    its own output over `refined_text`, so a span offset means nothing against
    it. The same column `design_review` measures against, so the number this
    pass reports and the number the gate reports cannot disagree.
    """
    from app.models.transcript import Transcript
    from app.services.design_brief_service import DesignBriefService

    rows = list((await db.scalars(
        select(Transcript)
        .where(Transcript.project_id == project_id)
        .order_by(Transcript.sequence_order)
    )).all())
    source_text = "\n\n".join(t.source_text or "" for t in rows).strip()
    brief = await DesignBriefService(db).get_active(project_id)
    dropped = list(brief.dropped_beats or []) if brief is not None else []
    return source_text, dropped


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

    # RC-T2. Fidelity is measured on the way IN and on the way OUT, over the
    # same script and the same merge the gate uses. A pass that lowers it has
    # traded content for a clean gate.
    source_text, dropped = await _fidelity_inputs(db, project_id)
    coverage_before = covered_character_count(
        await _rows(db, project_id), dropped, source_text,
    )

    result = await auto_repair_storyboard(db, project_id, project)
    result.pruned = pruned
    result.prune_skipped_because = skipped
    result.coverage_before = coverage_before
    result.coverage_after = covered_character_count(
        await _rows(db, project_id), dropped, source_text,
    )

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
