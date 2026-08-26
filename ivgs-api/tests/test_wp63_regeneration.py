"""
WP-63 Tasks 7 and 8 — regeneration, which recorded and dispatched nothing.

**MEASURED FIRST, on the running fleet, project 14f71729, 2026-08-26.** The
brief called regeneration "decorative at both levels". Half of that is exactly
right and half of it is not, and the difference matters because the two halves
need opposite fixes.

  THE GATE DECISION            genuinely dispatched nothing.
    15:17:25.362931Z  gate_decision gate=storyboard decision=regenerate -> 200
    15:17:29.616325Z  the same line again, four seconds later, because nothing
                      had happened and the operator pressed it a second time
    Two rows in `project_gate_decisions`, two audit entries, zero broker
    messages.

  THE PER-SCENE REGEN          dispatched nothing because it was REFUSED, and
                               the refusal was correct and was thrown away.
    15:15:40.605998Z  PATCH  .../scenes/bc4b52ef                    200 OK
    15:15:59.961499Z  POST   .../scenes/bc4b52ef/regenerate    409 Conflict
    The edit moved the storyboard fingerprint, so the approval recorded at
    13:41:29 no longer named the storyboard on screen and WP-62's gate refused
    the media work — with a message saying so and saying what to do. Every
    regeneration path in the storyboard UI awaited its promise inside a
    `try/finally` with no `catch`, so the operator saw nothing at all.

WP-45 STANDARD THROUGHOUT: every claim about what did or did not happen is
asserted on the BROKER. A 202 is not a dispatch.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.conftest import record_draft_approval, record_storyboard_approval

DISPATCH_MEDIA = "tasks.pipeline_orchestrator_v2.dispatch_media_generation"
DISPATCH_PIPELINE = "tasks.pipeline_orchestrator_v2.dispatch_pipeline"


class Broker:
    """Records what was published instead of publishing it."""

    def __init__(self):
        self.sent: list[dict] = []
        self.control = MagicMock()

    def send_task(self, name, args=None, kwargs=None, queue=None, **_ignored):
        self.sent.append({"name": name, "kwargs": kwargs, "queue": queue})
        result = MagicMock()
        result.id = f"celery-{len(self.sent)}"
        return result

    def names(self) -> list[str]:
        return [m["name"] for m in self.sent]


@pytest.fixture
def broker():
    b = Broker()
    with patch("app.services.celery_producer.celery_app", b):
        yield b


@pytest_asyncio.fixture
async def approved_project(db_session, operator_token):
    """Nine scenes, a completed run, and a CURRENT storyboard approval.

    The shape project 14f71729 was in at 13:41:29 on 2026-08-26 — the moment
    the operator approved and media generation was released. Scene indexes are
    zero-based here for the same reason they are everywhere else: that is what
    the flags, the logs and the checkpoints say.
    """
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.models.storyboard_scene import StoryboardScene

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(), name="WP-63 regeneration", state="STORYBOARD_GENERATION",
        created_by=owner, created_at=now, updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()
    scenes = []
    for i in range(9):
        scene = StoryboardScene(
            id=uuid.uuid4(), project_id=project.id, scene_index=i,
            narration_text=f"Scene {i} narration",
            visual_description="a teacher at a whiteboard",
            media_type="image", duration_seconds=10.0,
            created_at=now, updated_at=now,
        )
        db_session.add(scene)
        scenes.append(scene)
    db_session.add(
        RenderJob(
            id=uuid.uuid4(), project_id=project.id,
            job_type="storyboard_generation", status="success",
            created_at=now, completed_at=now,
        )
    )
    await db_session.commit()
    await record_storyboard_approval(db_session, project.id, owner)
    return {
        "project_id": str(project.id),
        "scene_ids": [str(s.id) for s in scenes],
        "owner": owner,
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Task 7(a) — one scene, its CURRENT settings, the right branch
# ---------------------------------------------------------------------------


class TestOneSceneItsCurrentSettings:
    async def test_a_regeneration_reaches_the_broker(
        self, client, operator_token, approved_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            f"/scenes/{approved_project['scene_ids'][0]}/regenerate",
            headers=_h(operator_token),
        )
        assert resp.status_code == 202, resp.text
        assert broker.names() == [DISPATCH_MEDIA]

    async def test_one_scene_not_nine(
        self, client, operator_token, approved_project, broker,
    ):
        """The project has nine scenes. Regenerating one must send one."""
        await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            f"/scenes/{approved_project['scene_ids'][2]}/regenerate",
            headers=_h(operator_token),
        )
        sent = broker.sent[0]["kwargs"]["dispatch_input"]["scenes"]
        assert len(sent) == 1
        assert sent[0]["scene_index"] == 2

    async def test_an_image_scene_switched_to_video_regenerates_as_video(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        """THE OPERATOR'S EXACT GESTURE: switch image -> video, then Regen.

        The dispatch must carry `video_clip` so `dispatch_media_generation`
        routes it to the video branch, and the job row must SAY
        video_generation rather than defaulting to images — WP-60's
        six-dispatch storm was diagnosed off `job_type`, and a row that
        misnames its own work points a fleet-wide guard at the wrong thing.
        """
        project_id = approved_project["project_id"]
        scene_id = approved_project["scene_ids"][3]

        patched = await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={"media_type": "video_clip"},
            headers=_h(operator_token),
        )
        assert patched.status_code == 200, patched.text

        # The edit moved the storyboard fingerprint, which is WP-62 working as
        # designed and is exactly what refused the operator's press. Re-approve
        # what is on screen now, as the refusal instructs.
        await record_storyboard_approval(
            db_session, uuid.UUID(project_id), approved_project["owner"],
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        assert resp.status_code == 202, resp.text
        assert resp.json()["job_type"] == "video_generation"
        sent = broker.sent[0]["kwargs"]["dispatch_input"]["scenes"]
        assert sent[0]["media_type"] == "video_clip"

    async def test_it_sends_the_stored_narration_not_the_original_arguments(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        """WP-45's ruling, pinned: the CURRENT fields, not a replay."""
        project_id = approved_project["project_id"]
        scene_id = approved_project["scene_ids"][4]
        await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={"visual_description": "92 + 230 = 322 worked on the board"},
            headers=_h(operator_token),
        )
        await record_storyboard_approval(
            db_session, uuid.UUID(project_id), approved_project["owner"],
        )
        await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        sent = broker.sent[0]["kwargs"]["dispatch_input"]["scenes"][0]
        assert sent["visual_description"] == "92 + 230 = 322 worked on the board"


# ---------------------------------------------------------------------------
# Task 7(b) — it composes with the WP-62 guards and with gate state
# ---------------------------------------------------------------------------


class TestItComposesWithTheGuards:
    async def test_an_edit_since_the_approval_refuses_at_the_broker(
        self, client, operator_token, approved_project, broker,
    ):
        """THE MEASURED 409, RECONSTRUCTED.

        15:15:40Z the operator saved a scene; 15:15:59Z they pressed Regen and
        got 409. Not a bug — the edit moved the storyboard fingerprint and the
        approval no longer named what was on screen. Asserted on the broker,
        because a refusal that arrives after the dispatch is not a gate.
        """
        project_id = approved_project["project_id"]
        scene_id = approved_project["scene_ids"][0]
        await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={"narration_text": "edited after approval"},
            headers=_h(operator_token),
        )
        resp = await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        assert resp.status_code == 409
        assert broker.sent == []

    async def test_the_refusal_says_which_gate_and_what_to_do(
        self, client, operator_token, approved_project, broker,
    ):
        """The message is the whole reason surfacing it is worth doing."""
        project_id = approved_project["project_id"]
        scene_id = approved_project["scene_ids"][0]
        await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={"narration_text": "edited after approval"},
            headers=_h(operator_token),
        )
        resp = await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        body = resp.json()["detail"]["error"]
        assert body["code"] == "GATE_NOT_APPROVED"
        assert "storyboard" in body["message"].lower()
        assert "approve" in body["message"].lower()

    async def test_a_second_press_while_the_first_runs_produces_no_second_dispatch(
        self, client, operator_token, approved_project, broker,
    ):
        """WP-45(c): a no-op click produces exactly one dispatch, never two.

        The first regeneration leaves a `running` job on the project, so the
        second press meets WP-62's in-flight guard.
        """
        project_id = approved_project["project_id"]
        scene_id = approved_project["scene_ids"][0]
        first = await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        second = await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        assert first.status_code == 202
        assert second.status_code == 409
        assert second.json()["detail"]["error"]["code"] == "PIPELINE_ALREADY_RUNNING"
        assert len(broker.sent) == 1

    async def test_a_refused_regeneration_leaves_no_pending_job_row(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        """A refused request must not leave a row to be counted or resumed."""
        project_id = approved_project["project_id"]
        scene_id = approved_project["scene_ids"][0]
        await client.patch(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}",
            json={"narration_text": "edited after approval"},
            headers=_h(operator_token),
        )
        await client.post(
            f"/api/v1/projects/{project_id}/scenes/{scene_id}/regenerate",
            headers=_h(operator_token),
        )
        pending = (await db_session.execute(
            text(
                "SELECT count(*) FROM render_jobs "
                "WHERE project_id = :p AND status = 'pending'"
            ),
            {"p": project_id},
        )).scalar()
        assert pending == 0


# ---------------------------------------------------------------------------
# Task 7 — the bulk route that did not exist
# ---------------------------------------------------------------------------


class TestBatchRegenerate:
    async def test_the_route_exists(self):
        """`useStoryboard.regenerateScenes` has POSTed here since WP-38.

        It answered 404 every time, and the hook's `mutate` rolled the
        optimistic state back with nothing catching, so "Regenerate Selected"
        was silent.
        """
        import main

        paths = {getattr(r, "path", "") for r in main.app.routes}
        assert (
            "/api/v1/projects/{project_id}/scenes/batch-regenerate" in paths
        )

    async def test_three_scenes_are_ONE_dispatch(
        self, client, operator_token, approved_project, broker,
    ):
        """Task 4's recovery shape: scene indexes 0, 2 and 7.

        Not three dispatches. The in-flight guard would refuse the second, and
        the media join is armed once per job — N jobs against one project is
        the stranding shape WP-06 exists to prevent.
        """
        ids = approved_project["scene_ids"]
        resp = await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            "/scenes/batch-regenerate",
            json={"scene_ids": [ids[0], ids[2], ids[7]]},
            headers=_h(operator_token),
        )
        assert resp.status_code == 202, resp.text
        assert len(broker.sent) == 1
        sent = broker.sent[0]["kwargs"]["dispatch_input"]["scenes"]
        assert [s["scene_index"] for s in sent] == [0, 2, 7]

    async def test_a_foreign_scene_id_refuses_the_whole_batch(
        self, client, operator_token, approved_project, broker,
    ):
        """No silent trimming.

        An operator who selected six scenes and got four has no way to find out
        which two were dropped.
        """
        ids = approved_project["scene_ids"]
        resp = await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            "/scenes/batch-regenerate",
            json={"scene_ids": [ids[0], str(uuid.uuid4())]},
            headers=_h(operator_token),
        )
        assert resp.status_code == 409
        assert broker.sent == []

    async def test_the_batch_is_behind_the_same_gate(
        self, client, operator_token, approved_project, broker,
    ):
        ids = approved_project["scene_ids"]
        await client.patch(
            f"/api/v1/projects/{approved_project['project_id']}/scenes/{ids[0]}",
            json={"narration_text": "edited after approval"},
            headers=_h(operator_token),
        )
        resp = await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            "/scenes/batch-regenerate",
            json={"scene_ids": [ids[0], ids[2]]},
            headers=_h(operator_token),
        )
        assert resp.status_code == 409
        assert broker.sent == []


# ---------------------------------------------------------------------------
# Task 8 — the gate's regenerate decision does what it says
# ---------------------------------------------------------------------------


class TestTheGateRegenerateDispatches:
    async def test_storyboard_regenerate_dispatches_exactly_one_run(
        self, client, operator_token, approved_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            "/gates/storyboard",
            json={"decision": "regenerate", "note": "the visuals say nothing"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        assert broker.names() == [DISPATCH_PIPELINE]
        ctx = broker.sent[0]["kwargs"]["job_context_dict"]
        assert ctx["resume_from_stage"] == "storyboard_generation"

    async def test_the_job_row_is_run_typed(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        """Not `final_render` borrowed as a sentinel.

        The resume route does that, and it is how a fleet-wide guard reading
        `job_type` gets pointed at the wrong work.
        """
        await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            "/gates/storyboard",
            json={"decision": "regenerate"},
            headers=_h(operator_token),
        )
        row = (await db_session.execute(
            text(
                "SELECT job_type, status, resume_from_stage FROM render_jobs "
                "WHERE project_id = :p ORDER BY created_at DESC LIMIT 1"
            ),
            {"p": approved_project["project_id"]},
        )).fetchone()
        assert row[0] == "storyboard_generation"
        assert row[1] == "running"
        assert row[2] == "storyboard_generation"

    async def test_the_decision_row_is_still_written_and_is_the_audit(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        await client.post(
            f"/api/v1/projects/{approved_project['project_id']}"
            "/gates/storyboard",
            json={"decision": "regenerate", "note": "generic filler"},
            headers=_h(operator_token),
        )
        rows = (await db_session.execute(
            text(
                "SELECT decision, note FROM project_gate_decisions "
                "WHERE project_id = :p AND gate = 'storyboard' "
                "ORDER BY decided_at DESC LIMIT 1"
            ),
            {"p": approved_project["project_id"]},
        )).fetchall()
        assert rows[0][0] == "regenerate"
        assert rows[0][1] == "generic filler"

    async def test_approve_and_reject_dispatch_no_pipeline_rerun(
        self, client, operator_token, approved_project, broker,
    ):
        """Broker-level proof both ways.

        `regenerate` -> exactly one dispatch of the right run type.
        `reject`     -> zero dispatches.
        `approve`    -> the media release only, never a stage re-run.
        """
        project_id = approved_project["project_id"]
        rejected = await client.post(
            f"/api/v1/projects/{project_id}/gates/storyboard",
            json={"decision": "rejected", "note": "no"},
            headers=_h(operator_token),
        )
        assert rejected.status_code == 200, rejected.text
        assert broker.sent == []

        approved = await client.post(
            f"/api/v1/projects/{project_id}/gates/storyboard",
            json={"decision": "approved"},
            headers=_h(operator_token),
        )
        assert approved.status_code == 200, approved.text
        assert DISPATCH_PIPELINE not in broker.names()
        assert broker.names() == [DISPATCH_MEDIA]

    async def test_a_second_press_produces_no_second_dispatch(
        self, client, operator_token, approved_project, broker,
    ):
        """The measured double-press, four seconds apart, now costs one run.

        The second decision is still RECORDED — a reviewer pressed it and that
        is a fact — and the release is refused with the reason.
        """
        project_id = approved_project["project_id"]
        first = await client.post(
            f"/api/v1/projects/{project_id}/gates/storyboard",
            json={"decision": "regenerate"},
            headers=_h(operator_token),
        )
        second = await client.post(
            f"/api/v1/projects/{project_id}/gates/storyboard",
            json={"decision": "regenerate"},
            headers=_h(operator_token),
        )
        assert first.status_code == 200
        assert second.status_code == 409
        assert second.json()["detail"]["error"]["code"] == "PIPELINE_ALREADY_RUNNING"
        assert len(broker.sent) == 1

    async def test_the_second_decision_is_still_recorded(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        project_id = approved_project["project_id"]
        await client.post(
            f"/api/v1/projects/{project_id}/gates/storyboard",
            json={"decision": "regenerate"},
            headers=_h(operator_token),
        )
        await client.post(
            f"/api/v1/projects/{project_id}/gates/storyboard",
            json={"decision": "regenerate"},
            headers=_h(operator_token),
        )
        count = (await db_session.execute(
            text(
                "SELECT count(*) FROM project_gate_decisions "
                "WHERE project_id = :p AND decision = 'regenerate'"
            ),
            {"p": project_id},
        )).scalar()
        assert count == 2

    async def test_draft_regenerate_re_runs_the_draft_assembly(
        self, client, operator_token, approved_project, broker, db_session,
    ):
        project_id = approved_project["project_id"]
        await record_draft_approval(
            db_session, uuid.UUID(project_id), approved_project["owner"],
        )
        resp = await client.post(
            f"/api/v1/projects/{project_id}/gates/draft",
            json={"decision": "regenerate"},
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        assert broker.names() == [DISPATCH_PIPELINE]
        ctx = broker.sent[0]["kwargs"]["job_context_dict"]
        assert ctx["resume_from_stage"] == "prototype_draft"


# ---------------------------------------------------------------------------
# Task 8 — the storyboard re-run had to become possible before it could ship
# ---------------------------------------------------------------------------


class TestAStoryboardRerunDoesNotDuplicateTheScenes:
    async def test_re_persisting_a_scene_index_replaces_rather_than_adds(
        self, client, operator_token, approved_project, db_session,
    ):
        """Stage 2 POSTs one scene per index. It used to INSERT every time.

        A second Stage-2 run over a 9-scene project left 18 rows — and Task 8's
        gate `regenerate` makes exactly that re-run happen, so this had to be
        true before that could ship. Stage 2's own code expected it: *"Try POST
        to create; if scenes already exist, try PATCH"*.
        """
        project_id = approved_project["project_id"]
        resp = await client.post(
            f"/api/v1/projects/{project_id}/scenes",
            json={
                "scene_index": 4,
                "narration_text": "re-run narration",
                "visual_description": "92 + 230 = 322 written out on the board",
                "media_type": "image",
                "duration_seconds": 12.0,
            },
            headers=_h(operator_token),
        )
        assert resp.status_code == 201, resp.text
        count = (await db_session.execute(
            text(
                "SELECT count(*) FROM storyboard_scenes "
                "WHERE project_id = :p AND scene_index = 4"
            ),
            {"p": project_id},
        )).scalar()
        assert count == 1, "a re-run must not leave two scenes at one index"

    async def test_the_scene_id_survives_so_its_assets_stay_attached(
        self, client, operator_token, approved_project, db_session,
    ):
        """Recreating the row would orphan the six good images."""
        project_id = approved_project["project_id"]
        before = approved_project["scene_ids"][4]
        resp = await client.post(
            f"/api/v1/projects/{project_id}/scenes",
            json={
                "scene_index": 4,
                "narration_text": "re-run narration",
                "visual_description": "a new description",
                "media_type": "image",
                "duration_seconds": 12.0,
            },
            headers=_h(operator_token),
        )
        assert resp.json()["id"] == before

    async def test_the_re_run_re_opens_the_gate(
        self, client, operator_token, approved_project, db_session,
    ):
        """For free, from WP-62's mechanism: the fingerprint moved."""
        from app.services.gate_service import GateService

        project_id = approved_project["project_id"]
        service = GateService(db_session)
        before = await service.status(uuid.UUID(project_id), "storyboard")
        assert before.approved is True

        await client.post(
            f"/api/v1/projects/{project_id}/scenes",
            json={
                "scene_index": 4,
                "narration_text": "re-run narration",
                "visual_description": "a new description",
                "media_type": "image",
                "duration_seconds": 12.0,
            },
            headers=_h(operator_token),
        )
        after = await GateService(db_session).status(
            uuid.UUID(project_id), "storyboard",
        )
        assert after.approved is False
        assert after.open is True
