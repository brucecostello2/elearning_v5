"""WP-IVGS-12i — mechanical refusals are repaired by code, and DECLARED.

The operator's ruling of 2026-08-30, which these tests exist to pin:

    gate refusals split into MECHANICAL (a deterministic default fix exists) and
    JUDGMENT (a human must decide). Mechanical refusals are REPAIRED BY CODE
    before the gate, declared, never silently; judgment findings surface to the
    human. The "no prompt loops" rule stands.

⛳ EVERY TEST HERE STUBS THE AUTHORING CALL, and that is not a shortcut. The
authoring primitive is `author_params_for_scene`, which reaches a live model on
the storyboard-generation binding; WP-IVGS-09f already proves what it produces
and `verify_spec_against_narration` already proves what it refuses. What is NEW
in this package is the pass around it — which refusals it selects, what it
writes, what it puts back, and what it declares — and all of that is decidable
with a stub. The acceptance run against the real engine is banked separately.

⛔ THE COUNT-THE-CALLS TEST IS THE "NO PROMPT LOOPS" RULE, MADE MECHANICAL. It
asserts ONE authoring call per mechanically-refused scene per pass. A future
refactor that "just retries once" fails it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene

# `pyproject.toml` sets `asyncio_mode = auto`; a blanket `pytest.mark.asyncio`
# here would warn on every synchronous test in this file.


# ---------------------------------------------------------------------------
# the classification, which is data and is tested as data
# ---------------------------------------------------------------------------

def test_every_hard_refusal_the_classifier_emits_is_classified():
    """No hard refusal may be silently unclassified.

    A code the classifier can emit but `storyboard_repair` has never heard of
    would be treated as judgment — the safe direction, but silently. This test
    is the thing that makes a NEW refusal kind a deliberate decision: add one to
    `storyboard_completeness` and this fails until someone argues it either into
    `MECHANICAL_CODES` or into the docstring's judgment list.
    """
    from app.services import storyboard_completeness as sc
    from app.services.storyboard_repair import MECHANICAL_CODES

    hard = {
        sc.CODE_MOTION_WITHOUT_TEMPLATE,
        sc.CODE_MOTION_CONTRADICTS_NARRATION,
        sc.CODE_VISUAL_DEMANDS_TEXT,
        sc.CODE_NARRATION_TEXT_UNDECLARED,
    }
    assert MECHANICAL_CODES == hard, (
        "every hard refusal is DELEGATES-TO-WRONG-MEDIUM and every one of them "
        "is answered by the same judgment-free exit the validator's own message "
        "names: author the scene as motion_graphics with a template"
    )


def test_the_soft_codes_are_never_mechanical():
    """A flag is not a refusal and must never be 'repaired'.

    The whole two-limb discipline WP-IVGS-10 established collapses if code
    starts acting on the subjective limb: a soft flag is the reviewer's
    judgement, and repairing one would answer a question nobody asked.
    """
    from app.services import storyboard_completeness as sc
    from app.services.storyboard_repair import is_mechanical

    for soft in (
        sc.CODE_OK,
        sc.CODE_MOTION_TEMPLATE_PENDING,
        sc.CODE_DUPLICATE_DESCRIPTION,
        sc.CODE_NO_WORKING_SURFACE,
        sc.CODE_NO_MEDIA_RATIONALE,
    ):
        assert not is_mechanical(soft), soft


def test_no_design_review_refusal_is_mechanical():
    """`design_review`'s sixteen hard codes are ALL judgment, and stay that way.

    The module docstring argues each by name. This asserts the argument was
    actually applied: not one of them appears in the mechanical set, so a future
    package cannot quietly start auto-designing a course to close a coverage gap.
    """
    from app.services.storyboard_repair import MECHANICAL_CODES

    design_codes = {
        "SCENE_SERVES_NOTHING", "SCENE_CITES_UNKNOWN_OUTCOME", "SCENE_NO_EVENT",
        "SCENE_BAD_EVENT", "SCENE_PROVENANCE_UNDECLARED",
        "SCENE_SOURCED_WITHOUT_REFS", "MOTION_UNKNOWN_TEMPLATE",
        "MOTION_WITHOUT_PARAMS", "OUTCOME_UNSERVED", "OUTCOME_UNASSESSED",
        "OUTCOME_ASSESSED_TWICE", "EVIDENCE_NEAR_DUPLICATE",
        "PLAN_ENTRY_UNREALIZED", "OUTCOMES_COUNT_DRIFTED",
        "OUTCOMES_TEXT_DRIFTED",
    }
    assert design_codes & MECHANICAL_CODES == set()


# ---------------------------------------------------------------------------
# the classifier now says WHICH rule spoke
# ---------------------------------------------------------------------------

def test_a_refusal_carries_the_code_of_the_rule_that_spoke():
    """Two refusals, two codes, and the repair pass selects on the code."""
    from app.services import storyboard_completeness as sc

    demands_text = sc.assess_scene(
        scene_index=0, media_type="image",
        narration_text="Our problem is 23 times 14.",
        visual_description="A worksheet with the problem 23 x 14 and a pencil.",
        text_carried_by="narration",
    )
    assert demands_text.severity == sc.SEV_REFUSE
    assert demands_text.code == sc.CODE_VISUAL_DEMANDS_TEXT

    undeclared = sc.assess_scene(
        scene_index=1, media_type="image",
        narration_text="Write 23 on top and 14 underneath.",
        visual_description="a calm desk in warm light",
    )
    assert undeclared.severity == sc.SEV_REFUSE
    assert undeclared.code == sc.CODE_NARRATION_TEXT_UNDECLARED

    clean = sc.assess_scene(
        scene_index=2, media_type="image",
        narration_text="Great job, you have finished the lesson.",
        visual_description="a child smiling at a desk",
    )
    assert clean.severity == sc.SEV_OK
    assert clean.code == sc.CODE_OK
    assert "code" in clean.as_dict(), "the surfaces read this off as_dict()"


# ---------------------------------------------------------------------------
# the pass itself
# ---------------------------------------------------------------------------

async def _seed(db_session, project, scenes):
    job = RenderJob(
        id=uuid.uuid4(), project_id=project.id,
        job_type="storyboard_generation", status="success",
    )
    db_session.add(job)
    await db_session.flush()
    for spec in scenes:
        db_session.add(
            StoryboardScene(
                id=uuid.uuid4(), project_id=project.id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                **spec,
            )
        )
    await db_session.commit()


#: The operator's own live storyboard, reduced to the three shapes that matter:
#: a scene refused for RULE 1, a scene that refuses nothing, and (added per
#: test) a scene whose authoring will fail.
_REFUSED = dict(
    scene_index=0, media_type="image",
    # The operands are in the words on purpose: WP-IVGS-09f's guard refuses a
    # parameter that appears nowhere in the scene's narration or its
    # neighbours', and this suite runs that guard FOR REAL on the way out. A
    # fixture whose numbers were invented would fail the re-validation for a
    # reason that has nothing to do with the repair pass.
    narration_text=(
        "Our problem is 23 times 14. Now multiply 4 times 3. 4 times 3 equals "
        "12. Write the 2 underneath and carry the 1."
    ),
    visual_description=(
        "A hand holding a pencil, writing the multiplication problem, 23 x 14, "
        "on a worksheet"
    ),
    text_carried_by="narration",
    duration_seconds=5.0,
)
_CLEAN = dict(
    scene_index=1, media_type="image",
    narration_text="Great job! You have finished the lesson.",
    visual_description="a child smiling at a desk",
    duration_seconds=5.0,
)


def _stub_authoring(monkeypatch, *, spec=None, error=None, calls=None):
    """Replace the model call. Records every invocation, in order."""
    from app.services import motion_authoring

    async def _fake(db, **kwargs):
        if calls is not None:
            calls.append(kwargs.get("scene_index"))
        if error is not None:
            raise motion_authoring.MotionAuthoringError(error)
        return dict(spec or {
            "template": "column_multiplication_step",
            "top": 23, "bottom": 14, "step": 0, "phase": "start",
        })

    monkeypatch.setattr(motion_authoring, "author_params_for_scene", _fake)


async def test_a_mechanical_refusal_is_repaired_and_the_gate_goes_clean(
    db_session, model_store_project, monkeypatch
):
    """The centerpiece: refusals in, zero mechanical refusals out."""
    from app.services.storyboard_repair import auto_repair_storyboard

    await _seed(db_session, model_store_project, [dict(_REFUSED), dict(_CLEAN)])
    _stub_authoring(monkeypatch)

    result = await auto_repair_storyboard(
        db_session, model_store_project.id, model_store_project,
    )

    assert result.refusals_before == 1
    assert result.mechanical_before == 1
    assert result.refusals_after == 0, "the mechanical refusal is gone"
    assert result.repaired == 1
    assert result.repair_refused == 0

    (c,) = result.corrections
    assert c.applied is True
    assert c.media_type_was == "image"
    assert c.media_type_is == "motion_graphics"
    assert c.template == "column_multiplication_step"
    assert c.refusal_code == "VISUAL_DEMANDS_ON_SCREEN_TEXT"
    assert c.original_visual_description == _REFUSED["visual_description"], (
        "the operator's description is preserved and declared, never rewritten"
    )


async def test_the_row_actually_changed_and_the_description_did_not(
    db_session, model_store_project, monkeypatch
):
    """The declaration and the database agree.

    A correction that claims a repair the row does not carry would be worse than
    no repair at all — it is the shape of every swallowed failure in this
    repository's own register.
    """
    from sqlalchemy import select
    from app.services.storyboard_repair import auto_repair_storyboard

    await _seed(db_session, model_store_project, [dict(_REFUSED)])
    _stub_authoring(monkeypatch)
    await auto_repair_storyboard(
        db_session, model_store_project.id, model_store_project,
    )

    row = (await db_session.scalars(
        select(StoryboardScene).where(
            StoryboardScene.project_id == model_store_project.id
        )
    )).one()
    assert row.media_type == "motion_graphics"
    assert row.generation_params["template"] == "column_multiplication_step"
    assert row.visual_description == _REFUSED["visual_description"]
    assert row.narration_text == _REFUSED["narration_text"]


async def test_when_authoring_refuses_the_original_refusal_stands(
    db_session, model_store_project, monkeypatch
):
    """⛔ REPAIR NEVER SWALLOWS, and the scene is PUT BACK.

    Leaving the medium flipped would replace one honest refusal
    (VISUAL_DEMANDS_ON_SCREEN_TEXT) with a different one the pass itself created
    (MOTION_WITHOUT_TEMPLATE), and the reviewer would be reading a defect that
    did not exist before code touched the storyboard.
    """
    from sqlalchemy import select
    from app.services.storyboard_repair import auto_repair_storyboard

    await _seed(db_session, model_store_project, [dict(_REFUSED)])
    _stub_authoring(
        monkeypatch,
        error="no operands could be established for scene 0",
    )

    result = await auto_repair_storyboard(
        db_session, model_store_project.id, model_store_project,
    )

    assert result.repaired == 0
    assert result.repair_refused == 1
    assert result.refusals_after == 1, "the original refusal survives, unchanged"

    (c,) = result.corrections
    assert c.applied is False
    assert c.media_type_is == "image", "put back"
    assert "no operands" in (c.repair_error or ""), "the authoring error, named"
    assert c.refusal_code == "VISUAL_DEMANDS_ON_SCREEN_TEXT", (
        "and the ORIGINAL refusal, named beside it — both errors, per the ruling"
    )
    assert c.refusal_reason, "in the validator's own words"

    row = (await db_session.scalars(
        select(StoryboardScene).where(
            StoryboardScene.project_id == model_store_project.id
        )
    )).one()
    assert row.media_type == "image"
    assert not (row.generation_params or {}).get("template")


async def test_one_authoring_call_per_refused_scene_and_not_one_more(
    db_session, model_store_project, monkeypatch
):
    """⛔ NO PROMPT LOOPS. One pass, one call per refusal, no retry."""
    from app.services.storyboard_repair import auto_repair_storyboard

    calls: list = []
    await _seed(db_session, model_store_project, [
        dict(_REFUSED),
        dict(_REFUSED, scene_index=2),
        dict(_CLEAN),
    ])
    _stub_authoring(monkeypatch, calls=calls)

    await auto_repair_storyboard(
        db_session, model_store_project.id, model_store_project,
    )
    assert calls == [0, 2], (
        "the two refused scenes, once each, in index order — and the clean "
        "scene was never sent to a model at all"
    )


async def test_a_clean_storyboard_is_left_entirely_alone(
    db_session, model_store_project, monkeypatch
):
    """Nothing to repair means nothing repaired, and no model call."""
    from app.services.storyboard_repair import auto_repair_storyboard

    calls: list = []
    await _seed(db_session, model_store_project, [dict(_CLEAN)])
    _stub_authoring(monkeypatch, calls=calls)

    result = await auto_repair_storyboard(
        db_session, model_store_project.id, model_store_project,
    )
    assert calls == []
    assert result.refusals_before == 0
    assert result.refusals_after == 0
    assert result.corrections == []


# ---------------------------------------------------------------------------
# the declaration
# ---------------------------------------------------------------------------

async def test_the_repair_is_declared_on_the_design_brief(
    db_session, model_store_project, monkeypatch
):
    """⛳ 'DECLARED, NEVER SILENTLY' — and a zero-repair pass is declared too."""
    from app.services.design_brief_service import DesignBriefService
    from app.services.storyboard_repair import repair_and_declare

    await _seed(db_session, model_store_project, [dict(_REFUSED), dict(_CLEAN)])
    await DesignBriefService(db_session).record(
        model_store_project.id,
        {"contract_version": "design-contract-7", "scenes": []},
    )
    _stub_authoring(monkeypatch)

    result = await repair_and_declare(
        db_session, model_store_project.id, model_store_project,
    )

    brief = await DesignBriefService(db_session).get_active(model_store_project.id)
    assert brief.system_corrections is not None, (
        "a repair nobody can see at the gate is a silent correction"
    )
    declared = brief.system_corrections
    assert declared["repaired"] == result.repaired == 1
    assert declared["refusals_before"] == 1
    assert declared["refusals_after"] == 0
    assert declared["corrections"][0]["media_type_was"] == "image"
    assert declared["corrections"][0]["media_type_is"] == "motion_graphics"
    assert declared["corrections"][0]["original_visual_description"] == (
        _REFUSED["visual_description"]
    )


async def test_a_pass_that_repaired_nothing_still_writes_its_record(
    db_session, model_store_project, monkeypatch
):
    """'Looked and found nothing' must be distinguishable from 'never looked'.

    NULL is the second of those and is what a pre-12i brief carries. A pass that
    ran and changed nothing writes `repaired: 0`, so the gate can say so.
    """
    from app.services.design_brief_service import DesignBriefService
    from app.services.storyboard_repair import repair_and_declare

    await _seed(db_session, model_store_project, [dict(_CLEAN)])
    await DesignBriefService(db_session).record(
        model_store_project.id,
        {"contract_version": "design-contract-7", "scenes": []},
    )
    _stub_authoring(monkeypatch)

    await repair_and_declare(db_session, model_store_project.id, model_store_project)
    brief = await DesignBriefService(db_session).get_active(model_store_project.id)
    assert brief.system_corrections is not None
    assert brief.system_corrections["repaired"] == 0
    assert brief.system_corrections["corrections"] == []


async def test_no_brief_means_the_repair_still_happens_and_says_so(
    db_session, model_store_project, monkeypatch
):
    """A pre-v8 storyboard has no brief. The scenes are still repaired.

    The declaration surface is missing, not the repair — and the absence is
    logged rather than raised, because refusing to repair a storyboard for want
    of a place to write about it would leave the reviewer with the refusals AND
    no explanation.
    """
    from sqlalchemy import select
    from app.services.storyboard_repair import repair_and_declare

    await _seed(db_session, model_store_project, [dict(_REFUSED)])
    _stub_authoring(monkeypatch)

    result = await repair_and_declare(
        db_session, model_store_project.id, model_store_project,
    )
    assert result.repaired == 1
    row = (await db_session.scalars(
        select(StoryboardScene).where(
            StoryboardScene.project_id == model_store_project.id
        )
    )).one()
    assert row.media_type == "motion_graphics"


# ---------------------------------------------------------------------------
# RC-R1 — the button may not lie, and neither may the endpoint behind it
# ---------------------------------------------------------------------------

async def test_approve_names_an_authoring_refusal_instead_of_answering_500(
    client, operator_token, model_store_project, db_session, monkeypatch
):
    """⛔ MEASURED 2026-08-30: THIS PATH ANSWERED HTTP 500 INTERNAL_ERROR.

    `approve_storyboard` runs `_author_missing_motion_specs` before the
    completeness check, and that helper raises `RegenerationError` when a motion
    scene's template cannot be authored from its own narration. `_gate_decision`
    caught `PipelineAlreadyRunningError`, `StoryboardIncomplete` and `ValueError`
    and not that, so the operator's press answered *"An unexpected error
    occurred"* with a request id — while the decision row was already written and
    the log held the sentence that actually explained it.

    A 500 says the system BROKE. A refusal says the system REFUSED. They are
    opposite instructions about what to do next, and the operator got the wrong
    one on a storyboard that was behaving exactly as designed.
    """
    from app.services import motion_authoring

    await _seed(db_session, model_store_project, [
        dict(scene_index=0, media_type="motion_graphics",
             narration_text="Our problem is 23 times 14. Add the two answers.",
             visual_description="the working, part done",
             duration_seconds=5.0),
    ])

    async def _refuse(db, **kwargs):
        raise motion_authoring.MotionAuthoringError(
            "scene 0: the narration announces 4 but column_addition_carry "
            "never produces 4"
        )

    monkeypatch.setattr(motion_authoring, "author_params_for_scene", _refuse)

    resp = await client.post(
        f"/api/v1/projects/{model_store_project.id}/scenes/approve",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert resp.status_code == 409, resp.text
    error = resp.json()["detail"]["error"]
    assert error["code"] == "MOTION_AUTHORING_REFUSED"
    assert "never produces 4" in error["message"], (
        "the authoring guard's own sentence is the whole answer and must survive"
    )
    assert "approval WAS recorded" in error["message"]


async def test_the_incomplete_refusal_carries_the_count_as_a_field(
    client, operator_token, model_store_project, db_session
):
    """RC-R1. The count, beside the named error — not only inside the prose.

    A surface that must render "N refusals block approval" should not have to
    parse an English sentence for N, and one that does will disagree with the
    sentence the first time it is reworded.
    """
    await _seed(db_session, model_store_project, [dict(_REFUSED), dict(_CLEAN)])

    resp = await client.post(
        f"/api/v1/projects/{model_store_project.id}/scenes/approve",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert resp.status_code == 409, resp.text
    error = resp.json()["detail"]["error"]
    assert error["code"] == "STORYBOARD_INCOMPLETE"
    assert error["refusals"] == 1
    assert error["refusals"] == len(error["scenes"])
