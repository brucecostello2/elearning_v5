"""WP-IVGS-10 — Stage 2 delivers what the storyboard model authored.

⛔ **FREEZE EXCEPTION #2, GRANTED BY THE OPERATOR 2026-08-29.** These tests
pinned a DEFECT until that ruling and pin the FIX after it. The change of sense
is deliberate and the history is the point, so it is written down rather than
rewritten away.

WHAT WAS WRONG. `stage2_storyboard.py` lost the storyboard model's authored
fields TWICE:

  1. `_validate_storyboard_json` built each scene from an EXPLICIT EIGHT-KEYWORD
     CONSTRUCTOR and never passed the rest. The worker's `StoryboardScene` IS
     `extra="allow"` — and `extra` keeps keys that are SUPPLIED, so the fields
     were gone there, **before the stage's own checkpoint was written**.
  2. `_save_storyboard_scenes` then POSTed five of the eight survivors.

**So RULE 8 had never worked at birth.** v6 asked the model for a motion
template from 2026-08-26 and v7 added two more declarations; not one could reach
the database. Measured on project `5d58f2f5`, checkpoint `f9545dae`: twelve
scenes, eight keys each, no `generation_params` on any of the five the model
chose as `motion_graphics`.

THE OPERATOR'S REASONING FOR THE EXCEPTION, verbatim: *"the Temporal conformance
target (the RUN-2 golden bank) is NOT yet recorded; banking a run through the
current body would enshrine the params-dropping defect as the behavior M3.3
activities must reproduce to pass conformance. The only cheap moment for this
edit is now, pre-bank. Unlike exception #1, the premise here is measured to the
wire."*

⚠ **AND THE WRAPPER IS GONE.** `app/services/storyboard_reconcile.py` existed
only to recover these fields from the checkpoint without editing a frozen body.
It is deleted, not left dormant: a recovery path that runs beside a working
delivery path makes the two indistinguishable, and the re-proof this package
owes could not then tell "the model authored it and it arrived" from "something
recovered it afterwards".
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.checkpoint import PipelineCheckpoint
from app.models.render_job import RenderJob
from app.models.storyboard_scene import StoryboardScene

# No module-level `pytest.mark.asyncio`: this file mixes async tests with
# synchronous ones that read the stage body off disk, and a blanket mark warns
# on every one of those. `pyproject.toml` sets `asyncio_mode = auto`.

STAGE2 = (
    Path(__file__).resolve().parents[2]
    / "ivgs-workers" / "tasks" / "stage2_storyboard.py"
)

#: The three fields the v7 CONTRACT declares. Named in both stage-2 sites and
#: here; a fourth would need this list and both sites, and that cost is stated
#: in the stage body rather than hidden.
DECLARED = ("generation_params", "media_rationale", "text_carried_by")


# ---------------------------------------------------------------------------
# SITE 1 — the constructor now forwards what the model authored
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", DECLARED)
def test_the_validator_forwards_every_declared_field(field):
    """⛔ THE FIRST LOSS SITE, NOW CLOSED.

    Reading the constructor is what settles this. An earlier draft of this
    package reasoned from `ConfigDict(extra="allow")` that the fields survived
    into the checkpoint, and the acceptance run disproved it — `extra` keeps
    keys that are SUPPLIED, and an explicit keyword call supplies none.
    """
    body = STAGE2.read_text(encoding="utf-8")
    ctor = body.split("scene = StoryboardScene(", 1)[1].split("            )", 1)[0]
    assert f"{field}=raw_scene.get(\"{field}\")" in ctor


def test_the_constructor_is_still_NAMED_and_not_an_open_splat():
    """The exception was granted for three declared keys, not for a passthrough.

    A filtered `**raw_scene` would carry whatever a model happened to invent
    into the checkpoint and on to the API. If someone later widens this to a
    splat that is a new decision, and this test is where it has to be argued.
    """
    body = STAGE2.read_text(encoding="utf-8")
    ctor = body.split("scene = StoryboardScene(", 1)[1].split("            )", 1)[0]
    # COMMENTS STRIPPED FIRST. The block carries a long prose justification and
    # markdown bold in it would make this assertion fire on the explanation
    # rather than on the code — which it did, first time.
    code = "\n".join(
        line for line in ctor.splitlines() if not line.strip().startswith("#")
    )
    assert "**" not in code


def test_the_worker_scene_model_keeps_them_as_extras():
    """`extra="allow"` is why the fix is three lines and not a schema change."""
    body = (
        Path(__file__).resolve().parents[2]
        / "ivgs-workers" / "models" / "task_result.py"
    ).read_text(encoding="utf-8")
    block = body.split("class StoryboardScene(BaseModel):", 1)[1].split(
        "class StoryboardGenerationInput", 1
    )[0]
    assert 'extra="allow"' in block


# ---------------------------------------------------------------------------
# SITE 2 — the POST now carries them, and only when they exist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", DECLARED)
def test_the_post_carries_every_declared_field(field):
    body = STAGE2.read_text(encoding="utf-8")
    block = body.split("payload = {", 1)[1].split("try:", 1)[0]
    assert field in block


def test_the_post_omits_a_field_the_scene_does_not_carry():
    """⚠ THE WIRE SHAPE OF A v6-ERA STORYBOARD DOES NOT MOVE.

    The three keys are added only when not None, so a scene carrying none
    produces the byte-identical five-key request this function sent before the
    exception. That is what makes the edit safe to deploy against storyboards
    already in flight.
    """
    body = STAGE2.read_text(encoding="utf-8")
    block = body.split("payload = {", 1)[1].split("try:", 1)[0]
    assert "if _value is not None:" in block
    assert 'getattr(scene, _declared, None)' in block


def test_the_five_original_keys_are_untouched():
    body = STAGE2.read_text(encoding="utf-8")
    block = body.split("payload = {", 1)[1].split("}", 1)[0]
    for key in ("scene_index", "narration_text", "visual_description",
                "media_type", "duration_seconds"):
        assert f'"{key}"' in block


# ---------------------------------------------------------------------------
# the exception's SCOPE — two sites, and no more
# ---------------------------------------------------------------------------

def test_the_exception_touched_exactly_two_sites():
    """⛔ THE OPERATOR'S SCOPE CONDITION, AS A TEST.

    *"SCOPE: those two sites only… If the fix needs a third site, STOP."* The
    marker appears once per authorized site and nowhere else in the file, so a
    third edit smuggled in under the same banner fails here.
    """
    body = STAGE2.read_text(encoding="utf-8")
    assert body.count("FREEZE EXCEPTION #2") == 2
    assert body.count("SITE 1 OF TWO") == 1
    assert body.count("SITE 2 OF TWO") == 1


def test_the_retired_wrapper_is_gone_not_dormant():
    """A recovery path running beside a working delivery path makes the two
    indistinguishable — and the re-proof needed to tell them apart."""
    assert not (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "storyboard_reconcile.py"
    ).exists()



async def _seed(db_session, project, scenes):
    """Scenes and a completed storyboard job for one project."""
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


# ---------------------------------------------------------------------------
# ⛔ THE TWO SITES, EXECUTED — not read off disk
# ---------------------------------------------------------------------------
#
# The tests above assert the SHAPE of the two edits. These call the real
# functions with a raw scene carrying a v7 template and assert the value comes
# out the other end, which is the property RC-P1 is actually about.
#
# WHY THIS EXISTS ALONGSIDE THE LIVE RE-PROOF. The live run proves the whole
# chain but depends on what the model happens to choose, and the model does not
# choose `motion_graphics` every time: two consecutive v7 runs on the identical
# transcript produced 5 motion scenes and then 0. A proof that can come up
# empty is not a regression test. This one is deterministic and runs in
# milliseconds.

def _stage2():
    """Import the frozen stage body by file location.

    `ivgs-workers` is not on this suite's `pythonpath` (the renderer tree has
    the same problem and solves it the same way), and importing the package
    would pull in Celery.
    """
    import importlib.util
    import os
    import sys

    workers = Path(__file__).resolve().parents[2] / "ivgs-workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))

    # ⚠ THE STAGE BODY REFUSES TO IMPORT WITHOUT ITS ENDPOINTS, and that refusal
    # is deliberate (WP-46: a receiver rejects, it does not infer). These two
    # functions never open a socket, so stub values are supplied for the import
    # and removed again — the test asserts about data shape, not about vLLM.
    # Exactly the three `_env_required` names in `ivgs-workers/config.py`, read
    # from that file rather than guessed — the first cut listed eight plausible
    # ones and still missed VLLM_SECONDARY_URL.
    stubbed = {
        "VLLM_PRIMARY_URL": "http://stub:8000",
        "VLLM_SECONDARY_URL": "http://stub:8000",
        "VLLM_MIDSIZE_URL": "http://stub:8000",
    }
    added = [k for k in stubbed if k not in os.environ]
    os.environ.update({k: v for k, v in stubbed.items() if k in added})
    try:
        spec = importlib.util.spec_from_file_location(
            "wpivgs10_stage2", workers / "tasks" / "stage2_storyboard.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for k in added:
            os.environ.pop(k, None)
    return module


TEMPLATE_SPEC = {
    "template": "column_multiplication_step",
    "top": 23, "bottom": 14, "step": 0, "phase": "start",
}

RAW_SCENE = {
    "scene_index": 2,
    "narration_text": "Multiply 4 times 3, which equals 12, and carry the 1.",
    "visual_description": "the carry travelling to the tens column",
    "media_type": "motion_graphics",
    "duration_seconds": 8.0,
    "generation_params": TEMPLATE_SPEC,
    "media_rationale": "motion_graphics: a digit is written and a carry travels.",
}


def test_site_1_a_template_survives_validation_into_the_scene_object():
    """⛔ RULE 8 AT BIRTH, at the first loss site.

    Before FREEZE EXCEPTION #2 this returned a scene with no
    `generation_params` at all, and the checkpoint written from it carried
    eight keys.
    """
    stage2 = _stage2()
    scenes = stage2._validate_storyboard_json([dict(RAW_SCENE)], max_duration=300)
    assert len(scenes) == 1
    assert scenes[0].media_type == "motion_graphics"
    assert scenes[0].generation_params == TEMPLATE_SPEC
    assert scenes[0].media_rationale.startswith("motion_graphics:")


def test_site_1_the_field_reaches_the_checkpoint_payload():
    """The checkpoint is written from `model_dump`, so what survives the
    constructor is what M3.3's conformance bank will contain."""
    stage2 = _stage2()
    scene = stage2._validate_storyboard_json([dict(RAW_SCENE)], max_duration=300)[0]
    dumped = scene.model_dump(mode="json")
    assert dumped["generation_params"]["phase"] == "start"
    assert "media_rationale" in dumped
    assert "text_carried_by" in dumped


def test_site_2_the_template_reaches_the_wire():
    """⛔ RULE 8 AT BIRTH, at the second loss site.

    The POST body is captured rather than mocked away, because the defect was
    IN the body: five keys where eight were needed.
    """
    stage2 = _stage2()
    scene = stage2._validate_storyboard_json([dict(RAW_SCENE)], max_duration=300)[0]
    sent = _capture_post(stage2, [scene])
    assert sent["generation_params"] == TEMPLATE_SPEC
    assert sent["media_rationale"].startswith("motion_graphics:")


def test_site_2_a_scene_without_them_sends_the_ORIGINAL_five_keys():
    """⚠ The wire shape of a v6-era storyboard does not move.

    This is what makes the exception safe against storyboards already in
    flight, and it is asserted as an exact key set rather than a subset.
    """
    stage2 = _stage2()
    plain = {k: v for k, v in RAW_SCENE.items()
             if k not in ("generation_params", "media_rationale")}
    plain["media_type"] = "image"
    scene = stage2._validate_storyboard_json([plain], max_duration=300)[0]
    sent = _capture_post(stage2, [scene])
    assert set(sent) == {
        "scene_index", "narration_text", "visual_description",
        "media_type", "duration_seconds",
    }


def _capture_post(stage2, scenes):
    """Run `_save_storyboard_scenes` against a stub client and return the body."""
    import types

    captured = {}

    class _Resp:
        status_code = 201

        @staticmethod
        def json():
            return {"id": "00000000-0000-0000-0000-000000000000"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            captured.update(json or {})
            return _Resp()

    real = stage2.httpx.Client
    stage2.httpx.Client = _Client
    try:
        config = types.SimpleNamespace(
            pipeline_api=types.SimpleNamespace(
                full_base_url="http://stub/api/v1",
                timeout_seconds=5,
                service_token="stub",
            )
        )
        stage2._save_storyboard_scenes("p", scenes, config)
    finally:
        stage2.httpx.Client = real
    return captured
