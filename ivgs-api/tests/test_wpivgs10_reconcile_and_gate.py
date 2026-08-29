"""WP-IVGS-10 — the transit loss, its wrapper, and the gate that reads it.

⛔ THE DEFECT THESE TESTS EXIST FOR, MEASURED IN THE TREE 2026-08-28.

``stage2_storyboard._save_storyboard_scenes`` POSTs five keys — ``scene_index``,
``narration_text``, ``visual_description``, ``media_type``,
``duration_seconds``. ``generation_params`` is not among them. **So RULE 8 has
never worked at birth**: v6 has asked the storyboard model for a template and
its parameters since 2026-08-26, ``SceneCreate`` has accepted them since
migration 0028, and the worker's own payload builder discards them on the way to
the database. Every motion spec that has ever reached a renderer on this fleet
was authored LATER, from the narration alone.

That file is one of the eight FROZEN stage task bodies (`dev/CLAUDE.md` §3,
AD-05 §8: *"Wrapping is allowed; editing is not"*), so this package wraps. The
data is not lost — the worker's ``StoryboardScene`` is ``extra="allow"``, so
every key survives into the stage's own checkpoint — and
``storyboard_reconcile`` recovers it from there.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.checkpoint import PipelineCheckpoint
from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene
from app.services.storyboard_reconcile import (
    CARRIED_FIELDS,
    authored_fields,
    overlay_authored_fields,
    reconcile,
)

# No module-level `pytest.mark.asyncio`: this file mixes async tests with three
# synchronous ones that read the frozen stage body off disk, and a blanket mark
# warns on every one of those. `pyproject.toml` sets `asyncio_mode = auto`, so
# the async tests are collected without it.


# ---------------------------------------------------------------------------
# the transit loss, stated as a fact about the frozen body
# ---------------------------------------------------------------------------

def test_the_frozen_stage_body_still_posts_only_five_keys():
    """⛔ THE SECOND LOSS. A CHARACTERISATION TEST, NOT AN APPROVAL.

    It pins the defect so that the day somebody DOES edit
    ``_save_storyboard_scenes`` — which is an M3.3-R3 edit, not this package's —
    this test fails loudly and the wrapper below can be retired in the same
    commit rather than left running forever over data that no longer needs it.
    """
    from pathlib import Path

    body = (
        Path(__file__).resolve().parents[2]
        / "ivgs-workers" / "tasks" / "stage2_storyboard.py"
    ).read_text(encoding="utf-8")
    payload = body.split("payload = {", 1)[1].split("}", 1)[0]
    for key in ("scene_index", "narration_text", "visual_description",
                "media_type", "duration_seconds"):
        assert f'"{key}"' in payload
    assert '"generation_params"' not in payload, (
        "the frozen stage body now forwards generation_params -- "
        "storyboard_reconcile's whole reason for existing has gone, and it "
        "should be retired in the same commit that did this"
    )


def test_the_validator_drops_the_keys_BEFORE_the_checkpoint_is_written():
    """⛔ THE FIRST LOSS, AND THE ONE THAT WAS INFERRED WRONGLY.

    An earlier draft of `storyboard_reconcile` asserted that the fields survive
    into the stage's checkpoint because the worker's `StoryboardScene` is
    `extra="allow"`. It IS — and that changes nothing, because
    `_validate_storyboard_json` builds every scene from an EXPLICIT EIGHT-KEYWORD
    CONSTRUCTOR and never passes the rest. `extra` keeps keys that are SUPPLIED.

    Measured on the acceptance run: project 5d58f2f5, storyboard checkpoint
    f9545dae, 2026-08-29 — twelve scenes, eight keys each, and no
    `generation_params` on any of the five the model chose as motion_graphics.

    This is a characterisation test. It fails the day somebody widens that
    constructor, which is the M3.3-R3 edit (RC-P1) — and on that day the
    wrapper becomes live and should be activated deliberately.
    """
    from pathlib import Path

    body = (
        Path(__file__).resolve().parents[2]
        / "ivgs-workers" / "tasks" / "stage2_storyboard.py"
    ).read_text(encoding="utf-8")
    ctor = body.split("scene = StoryboardScene(", 1)[1].split(")", 1)[0]
    for dropped in ("generation_params", "media_rationale", "text_carried_by"):
        assert dropped not in ctor, (
            f"the frozen validator now forwards {dropped} -- the first half of "
            f"RC-P1 has landed, and storyboard_reconcile is no longer inert"
        )
    assert "**" not in ctor, (
        "the constructor now splats the raw scene, so every key the model "
        "emits survives -- RC-P1's first half has landed"
    )


def test_the_worker_scene_model_would_keep_them_if_they_were_passed():
    """`extra="allow"` is real, and is why RC-P1's fix is two lines rather than
    a schema change. It is simply unreachable through the constructor above."""
    from pathlib import Path

    body = (
        Path(__file__).resolve().parents[2]
        / "ivgs-workers" / "models" / "task_result.py"
    ).read_text(encoding="utf-8")
    scene_block = body.split("class StoryboardScene(BaseModel):", 1)[1].split(
        "class StoryboardGenerationInput", 1
    )[0]
    assert 'extra="allow"' in scene_block


# ---------------------------------------------------------------------------
# the wrapper
# ---------------------------------------------------------------------------

async def _seed(db_session, project, scenes, checkpoint_scenes):
    job = RenderJob(
        id=uuid.uuid4(), project_id=project.id,
        job_type="storyboard_generation", status="success",
    )
    db_session.add(job)
    await db_session.flush()
    rows = []
    for spec in scenes:
        row = StoryboardScene(
            id=uuid.uuid4(), project_id=project.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **spec,
        )
        db_session.add(row)
        rows.append(row)
    db_session.add(
        PipelineCheckpoint(
            id=uuid.uuid4(), job_id=job.id,
            stage_name="storyboard_generation", stage_index=2,
            status="complete",
            checkpoint_data={"stage": "storyboard_generation",
                             "scenes": checkpoint_scenes},
        )
    )
    await db_session.commit()
    return rows


async def test_the_authored_template_is_recovered_from_the_checkpoint(
    db_session, model_store_project
):
    """RULE 8, at birth, working for the first time on this fleet."""
    narration = "Multiply 4 times 3, which equals 12, and carry the 1."
    spec = {
        "template": "column_multiplication_step",
        "top": 23, "bottom": 14, "step": 0, "phase": "start",
    }
    rows = await _seed(
        db_session, model_store_project,
        scenes=[dict(scene_index=0, media_type="motion_graphics",
                     narration_text=narration, visual_description="v",
                     duration_seconds=5.0)],
        checkpoint_scenes=[{
            "scene_index": 0, "narration_text": narration,
            "visual_description": "v", "media_type": "motion_graphics",
            "duration_seconds": 5.0,
            "generation_params": spec,
            "media_rationale": "motion_graphics: a digit is written and a carry travels.",
        }],
    )
    assert rows[0].generation_params is None      # the transit loss, in the row

    summary = await reconcile(db_session, model_store_project.id)
    assert summary["matched"] == 1
    assert summary["filled"] == 2

    await db_session.refresh(rows[0])
    assert rows[0].generation_params == spec
    assert rows[0].media_rationale.startswith("motion_graphics:")


async def test_reconcile_never_overwrites_a_field_that_is_already_set(
    db_session, model_store_project
):
    """⛔ THE CHECKPOINT IS THE OLDEST AND LEAST CHECKED VERSION.

    A row's ``generation_params`` may have been authored by WP-IVGS-09f's
    guarded path — which verified it against the narration — or edited by an
    operator. The checkpoint holds what the model first said, before either.
    Overwriting would silently discard a checked spec for an unchecked one.
    """
    narration = "Multiply 4 times 3."
    kept = {"template": "column_multiplication_step", "top": 23, "bottom": 14,
            "step": 0, "phase": "start"}
    rows = await _seed(
        db_session, model_store_project,
        scenes=[dict(scene_index=0, media_type="motion_graphics",
                     narration_text=narration, visual_description="v",
                     duration_seconds=5.0, generation_params=kept)],
        checkpoint_scenes=[{
            "scene_index": 0, "narration_text": narration,
            "generation_params": {"template": "place_value_split", "number": 99},
        }],
    )
    summary = await reconcile(db_session, model_store_project.id)
    assert summary["filled"] == 0
    await db_session.refresh(rows[0])
    assert rows[0].generation_params == kept


async def test_an_empty_object_counts_as_missing(db_session, model_store_project):
    """The GUI flip leaves ``{}`` — an object that exists and says nothing.

    WP-IVGS-09c measured six scenes in that state and had to write
    ``has_motion_spec`` because a bare truth test would have been right by
    accident. The same distinction has to hold here.
    """
    narration = "Multiply 4 times 3."
    spec = {"template": "column_multiplication_step", "top": 23, "bottom": 14,
            "step": 0, "phase": "start"}
    rows = await _seed(
        db_session, model_store_project,
        scenes=[dict(scene_index=0, media_type="motion_graphics",
                     narration_text=narration, visual_description="v",
                     duration_seconds=5.0, generation_params={})],
        checkpoint_scenes=[{"scene_index": 0, "narration_text": narration,
                            "generation_params": spec}],
    )
    await reconcile(db_session, model_store_project.id)
    await db_session.refresh(rows[0])
    assert rows[0].generation_params == spec


async def test_scenes_are_matched_on_narration_and_never_on_index(
    db_session, model_store_project
):
    """⛔ THE WORST AVAILABLE OUTCOME IS ATTACHING ONE SCENE'S TEMPLATE TO
    ANOTHER SCENE'S WORDS, and matching on index is how that happens.

    A re-run that produces a different number of scenes leaves every index
    meaning something else. Here the checkpoint's scene 0 is the row's scene 1,
    and only the narration says so.
    """
    a = "Multiply 4 times 3, which equals 12."
    b = "Our first answer is 92."
    spec = {"template": "column_multiplication_step", "top": 23, "bottom": 14,
            "step": 0, "phase": "complete"}
    rows = await _seed(
        db_session, model_store_project,
        scenes=[
            dict(scene_index=0, media_type="image", narration_text=a,
                 visual_description="v", duration_seconds=5.0),
            dict(scene_index=1, media_type="motion_graphics", narration_text=b,
                 visual_description="v", duration_seconds=5.0),
        ],
        checkpoint_scenes=[
            {"scene_index": 0, "narration_text": b, "generation_params": spec},
        ],
    )
    await reconcile(db_session, model_store_project.id)
    await db_session.refresh(rows[0])
    await db_session.refresh(rows[1])
    assert rows[0].generation_params is None
    assert rows[1].generation_params == spec


async def test_reconcile_does_not_move_the_storyboard_fingerprint(
    db_session, model_store_project
):
    """⛔ RC-O12 IN MINIATURE, AND IT WAS MEASURED HAPPENING FOR REAL.

    ``GateService.storyboard_version`` hashes ``updated_at``. WP-IVGS-09f wrote
    to six scenes, moved the fingerprint, and re-opened the gate its own writes
    had invalidated — recorded in that report's data-writes section. Recovering
    a field the model already authored is not a change to the artefact a human
    reviewed; it is that artefact arriving intact, and it must not invalidate
    an approval.
    """
    from app.services.gate_service import GateService

    narration = "Multiply 4 times 3."
    rows = await _seed(
        db_session, model_store_project,
        scenes=[dict(scene_index=0, media_type="motion_graphics",
                     narration_text=narration, visual_description="v",
                     duration_seconds=5.0)],
        checkpoint_scenes=[{
            "scene_index": 0, "narration_text": narration,
            "generation_params": {"template": "place_value_split", "number": 23},
        }],
    )
    gate = GateService(db_session)
    before = await gate.storyboard_version(model_store_project.id)
    await reconcile(db_session, model_store_project.id)
    after = await gate.storyboard_version(model_store_project.id)
    assert before == after


async def test_the_read_path_overlays_without_writing(
    db_session, model_store_project
):
    """The gate's status is a GET. It must show the storyboard as authored and
    still leave the table exactly as it found it."""
    narration = "Multiply 4 times 3."
    spec = {"template": "place_value_split", "number": 23}
    rows = await _seed(
        db_session, model_store_project,
        scenes=[dict(scene_index=0, media_type="motion_graphics",
                     narration_text=narration, visual_description="v",
                     duration_seconds=5.0)],
        checkpoint_scenes=[{"scene_index": 0, "narration_text": narration,
                            "generation_params": spec}],
    )
    views = await overlay_authored_fields(db_session, model_store_project.id, rows)
    assert views[0].generation_params == spec
    # ...and the ROW is untouched, in the session and in the table.
    assert rows[0].generation_params is None
    await db_session.refresh(rows[0])
    assert rows[0].generation_params is None


async def test_a_project_with_no_checkpoint_reconciles_to_nothing(
    db_session, model_store_project
):
    summary = await reconcile(db_session, model_store_project.id)
    assert summary["filled"] == 0
    assert summary["reason"]


def test_the_carried_fields_are_exactly_v7s_three():
    """Named once. A fourth field added to v7 and not to this tuple would be
    authored by the model, dropped in transit, and silently never recovered."""
    assert CARRIED_FIELDS == (
        "generation_params", "media_rationale", "text_carried_by",
    )


# ---------------------------------------------------------------------------
# the gate surfaces it
# ---------------------------------------------------------------------------

async def test_the_gate_status_carries_every_scenes_verdict(
    db_session, model_store_project
):
    """Task 3's soft half: the reviewer sees the flags BEFORE deciding.

    Every scene appears, not only the failing ones — a list that shows only
    problems cannot be told from a list that was never computed.
    """
    from app.services.gate_service import GATE_STORYBOARD, GateService

    await _seed(
        db_session, model_store_project,
        scenes=[
            # the operator's own example, verbatim (9c29b1d1 scene 1)
            dict(scene_index=0, media_type="image",
                 narration_text=(
                     "First, we set up the problem. Write the numbers on top "
                     "and underneath, making sure the ones digits line up and "
                     "the tens digits line up. Draw a line underneath."
                 ),
                 visual_description=(
                     "A hand holding a pencil, poised over a blank sheet of "
                     "lined paper with a ruler and a soft pink pencil case "
                     "nearby, warm and gentle lighting"
                 ),
                 duration_seconds=5.0),
            dict(scene_index=1, media_type="image",
                 narration_text="Great job! You have finished the lesson.",
                 visual_description="a child smiling at a desk",
                 duration_seconds=5.0),
        ],
        checkpoint_scenes=[],
    )
    status = await GateService(db_session).status(
        model_store_project.id, GATE_STORYBOARD
    )
    payload = status.as_dict()
    assert len(payload["completeness"]) == 2, "every scene, not only the failing ones"
    assert payload["completeness_refusals"] == 1
    assert payload["completeness"][0]["verdict"] == "DELEGATES-TO-WRONG-MEDIUM"
    assert payload["completeness"][0]["severity"] == "refuse"
    assert payload["completeness"][1]["severity"] == "ok"


async def test_the_draft_gate_carries_no_completeness(
    db_session, model_store_project
):
    """It is a storyboard question. The draft gate reviews a rendered video and
    a completeness list there would be an answer to a question nobody asked."""
    from app.services.gate_service import GATE_DRAFT, GateService

    status = await GateService(db_session).status(model_store_project.id, GATE_DRAFT)
    assert status.as_dict()["completeness"] == []
