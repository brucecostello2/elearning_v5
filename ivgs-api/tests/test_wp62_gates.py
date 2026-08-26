"""
WP-62 Task 2 — the two human review gates, and what refuses without them.

**WP-45 STANDARD THROUGHOUT: the refusals are asserted on the BROKER, not on a
status code.** A 409 that arrives after the dispatch is not a gate. The whole
finding this task started from is that a button answered 200, dispatched nine
scenes to GPU work, and left no record that anybody had approved anything --
measured on project 64207933 at 2026-08-26T09:07:47.255Z.

The one that matters most is
`test_media_generation_never_reaches_the_broker_without_an_approval`: it
constructs a project sitting exactly where the old code dispatched from, and is
RED without the enforcement.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text


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


@pytest.fixture
def broker():
    b = Broker()
    with patch("app.services.celery_producer.celery_app", b):
        yield b


@pytest_asyncio.fixture
async def storyboarded_project(db_session, operator_token):
    """A project paused at the storyboard gate: scenes persisted, one job.

    This is the exact shape `approve_storyboard` accepted and dispatched from
    before WP-62. It needs a render job because the release path resumes one.
    """
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.models.storyboard_scene import StoryboardScene

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(), name="WP-62 gate", state="STORYBOARD_GENERATION",
        created_by=owner, created_at=now, updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()
    for i in range(3):
        db_session.add(
            StoryboardScene(
                id=uuid.uuid4(), project_id=project.id, scene_index=i,
                narration_text=f"Scene {i}", visual_description="a board",
                media_type="image", duration_seconds=5.0,
                created_at=now, updated_at=now,
            )
        )
    db_session.add(
        RenderJob(
            id=uuid.uuid4(), project_id=project.id,
            job_type="storyboard_generation", status="success",
            created_at=now, completed_at=now,
        )
    )
    await db_session.commit()
    return str(project.id)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# (a) What the button did before, pinned so it cannot come back
# ---------------------------------------------------------------------------


class TestTheOldSurfaceStillExistsAndIsNoLongerABypass:
    async def test_the_approve_endpoint_is_still_there(self, client, operator_token):
        """The surface is unchanged: the enforcement was built BEHIND it.

        A second Approve button would have left this one working as a bypass of
        the gate it was supposed to be.
        """
        import main

        paths = {getattr(r, "path", "") for r in main.app.routes}
        assert "/api/v1/projects/{project_id}/scenes/approve" in paths

    async def test_approving_through_the_old_endpoint_writes_a_decision_row(
        self, client, operator_token, storyboarded_project, db_session, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{storyboarded_project}/scenes/approve?tier=prototype",
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        rows = (await db_session.execute(
            text(
                "SELECT gate, decision, artifact_version FROM "
                "project_gate_decisions WHERE project_id = :p"
            ),
            {"p": storyboarded_project},
        )).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "storyboard"
        assert rows[0][1] == "approved"
        # NOT NULL and not a placeholder: the decision names the artifact.
        assert rows[0][2].startswith("sb-3-")


# ---------------------------------------------------------------------------
# (c) Enforcement, asserted on the broker
# ---------------------------------------------------------------------------


class TestMediaGenerationRefusesWithoutAnApproval:
    async def test_media_generation_never_reaches_the_broker_without_an_approval(
        self, storyboarded_project, db_session, broker,
    ):
        """RED WITHOUT THE ENFORCEMENT.

        `approve_storyboard` is called directly, bypassing the route that
        records the decision. Before WP-62 this dispatched
        `dispatch_media_generation` and moved the project to MEDIA_GENERATION.
        """
        from app.models.user import User
        from app.services.gate_service import GateBlocked
        from app.services.project_service import ProjectService
        from sqlalchemy import select

        user = await db_session.scalar(select(User).limit(1))
        with pytest.raises(GateBlocked):
            await ProjectService(db_session).approve_storyboard(
                uuid.UUID(storyboarded_project), user,
            )
        assert broker.sent == [], (
            "media generation was dispatched for a project with no recorded "
            "storyboard approval"
        )

    async def test_approving_then_releasing_does_dispatch(
        self, client, operator_token, storyboarded_project, broker,
    ):
        """The gate is a gate, not a wall. Approval releases."""
        resp = await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "approved", "note": "looks right"},
        )
        assert resp.status_code == 200, resp.text
        names = [m["name"] for m in broker.sent]
        assert names == [
            "tasks.pipeline_orchestrator_v2.dispatch_media_generation"
        ], names

    async def test_a_rejection_dispatches_nothing_and_re_opens_the_gate(
        self, client, operator_token, storyboarded_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "rejected", "note": "scene 2 is wrong"},
        )
        assert resp.status_code == 200, resp.text
        assert broker.sent == [], "a REJECTION dispatched GPU work"
        gates = resp.json()["gates"]
        assert gates["storyboard"]["approved"] is False
        assert gates["storyboard"]["open"] is True

    async def test_an_upstream_rerun_invalidates_the_approval(
        self, client, operator_token, storyboarded_project, db_session, broker,
    ):
        """THE INVALIDATION, and it needs no invalidation write.

        Approve, then move a scene's `updated_at` the way a Stage-2 re-run
        does. The approval names the old fingerprint; currency is recomputed on
        read, so it stops being current by arithmetic.
        """
        await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "approved"},
        )
        gates = (await client.get(
            f"/api/v1/projects/{storyboarded_project}/gates",
            headers=_h(operator_token),
        )).json()["gates"]
        assert gates["storyboard"]["approved"] is True

        await db_session.execute(
            text(
                "UPDATE storyboard_scenes SET updated_at = now() + interval "
                "'1 second' WHERE project_id = :p AND scene_index = 1"
            ),
            {"p": storyboarded_project},
        )
        await db_session.commit()

        gates = (await client.get(
            f"/api/v1/projects/{storyboarded_project}/gates",
            headers=_h(operator_token),
        )).json()["gates"]
        assert gates["storyboard"]["approved"] is False
        assert "changed since" in gates["storyboard"]["reason"]

    async def test_a_stale_approval_does_not_release_the_broker(
        self, client, operator_token, storyboarded_project, db_session, broker,
    ):
        """The invalidation is not cosmetic: it stops the dispatch."""
        await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "approved"},
        )
        broker.sent.clear()
        await db_session.execute(
            text(
                "UPDATE storyboard_scenes SET updated_at = now() + interval "
                "'2 seconds' WHERE project_id = :p"
            ),
            {"p": storyboarded_project},
        )
        await db_session.commit()

        from app.models.user import User
        from app.services.gate_service import GateBlocked
        from app.services.project_service import ProjectService
        from sqlalchemy import select

        user = await db_session.scalar(select(User).limit(1))
        with pytest.raises(GateBlocked):
            await ProjectService(db_session).approve_storyboard(
                uuid.UUID(storyboarded_project), user,
            )
        assert broker.sent == []


class TestFinalRenderRefusesWithoutADraftApproval:
    @pytest_asyncio.fixture
    async def reviewable_project(self, db_session, operator_token):
        """USER_REVIEW with a prototype_draft checkpoint — gate 2's condition."""
        from app.core.security import decode_token
        from app.models.checkpoint import PipelineCheckpoint
        from app.models.project import Project
        from app.models.render_job import RenderJob

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        now = datetime.now(timezone.utc)
        project = Project(
            id=uuid.uuid4(), name="WP-62 draft gate", state="USER_REVIEW",
            created_by=owner, created_at=now, updated_at=now,
        )
        db_session.add(project)
        await db_session.flush()
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id,
            job_type="transcript_refinement", status="success",
            created_at=now, completed_at=now,
        )
        db_session.add(job)
        await db_session.flush()
        db_session.add(
            PipelineCheckpoint(
                id=uuid.uuid4(), job_id=job.id, stage_name="prototype_draft",
                stage_index=7, status="complete", created_at=now,
            )
        )
        await db_session.commit()
        return str(project.id)

    async def test_the_render_trigger_never_reaches_the_broker_unapproved(
        self, client, operator_token, reviewable_project, broker,
    ):
        """RED WITHOUT THE ENFORCEMENT.

        `POST /trigger` from USER_REVIEW IS the final render. Before WP-62 it
        moved the project to FINAL_RENDER and dispatched, with nothing
        anywhere recording that a human had looked at the draft.
        """
        resp = await client.post(
            f"/api/v1/projects/{reviewable_project}/trigger?tier=prototype",
            headers=_h(operator_token),
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error"]["code"] == "GATE_NOT_APPROVED"
        assert broker.sent == [], "the final render was dispatched unapproved"

    async def test_the_project_is_not_moved_by_a_refused_trigger(
        self, client, operator_token, reviewable_project, db_session, broker,
    ):
        """A refused trigger leaves the project exactly as it found it."""
        await client.post(
            f"/api/v1/projects/{reviewable_project}/trigger",
            headers=_h(operator_token),
        )
        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"),
            {"i": reviewable_project},
        )).scalar()
        assert state == "USER_REVIEW"
        jobs = (await db_session.execute(
            text(
                "SELECT count(*) FROM render_jobs WHERE project_id = :i "
                "AND job_type = 'final_render'"
            ),
            {"i": reviewable_project},
        )).scalar()
        assert jobs == 0, "a refused trigger inserted a job row"

    async def test_approving_the_draft_releases_the_render(
        self, client, operator_token, reviewable_project, broker,
    ):
        resp = await client.post(
            f"/api/v1/projects/{reviewable_project}/gates/draft",
            headers=_h(operator_token),
            json={"decision": "approved", "note": "ship it"},
        )
        assert resp.status_code == 200, resp.text
        # THE DRAFT GATE DOES NOT DISPATCH. §6.1 keeps the render an explicit
        # action; collapsing them would make an approval silently spend GPU
        # time.
        assert broker.sent == []

        resp = await client.post(
            f"/api/v1/projects/{reviewable_project}/trigger?tier=prototype",
            headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        assert [m["name"] for m in broker.sent] == [
            "tasks.pipeline_orchestrator_v2.dispatch_pipeline"
        ]


# ---------------------------------------------------------------------------
# (b) The contract, and (e) the audit
# ---------------------------------------------------------------------------


class TestContractAndAudit:
    async def test_both_gate_endpoints_exist_under_the_ruled_paths(self):
        import main

        paths = {getattr(r, "path", "") for r in main.app.routes}
        assert "/api/v1/projects/{project_id}/gates/storyboard" in paths
        assert "/api/v1/projects/{project_id}/gates/draft" in paths

    async def test_the_response_carries_the_m33_signal_shape(
        self, client, operator_token, storyboarded_project, broker,
    ):
        """Signal-compatible for M3.3, today.

        §6.4 implements both gates as Temporal signals. Fixing the payload
        shape now means the audit of a Celery-era decision and a Temporal-era
        one are the same object, rather than the shape being invented under
        time pressure at cutover.
        """
        resp = await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "approved"},
        )
        signal = resp.json()["signal"]
        assert signal["name"] == "gate_storyboard"
        for key in (
            "gate", "decision", "artifact_version", "upstream_version",
            "note", "decided_by", "decided_at",
        ):
            assert key in signal["payload"], key

    @pytest.mark.parametrize(
        "decision", ["approved", "rejected", "regenerate"],
    )
    async def test_every_decision_writes_audit_log(
        self, client, operator_token, storyboarded_project, db_session, broker,
        decision,
    ):
        """(e) EVERY decision, not every approval.

        An unrecorded rejection is exactly as bad as an unrecorded approval
        when somebody later asks why a project sat for three days.
        """
        await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": decision, "note": "because"},
        )
        rows = (await db_session.execute(
            text(
                "SELECT action_type, after_payload->>'decision' FROM audit_log "
                "WHERE resource_id = :p AND action_type LIKE 'GATE_%'"
            ),
            {"p": storyboarded_project},
        )).fetchall()
        assert len(rows) == 1, rows
        assert rows[0][0] == f"GATE_STORYBOARD_{decision.upper()}"
        assert rows[0][1] == decision

    async def test_an_unknown_decision_is_a_400_not_a_row(
        self, client, operator_token, storyboarded_project, db_session,
    ):
        resp = await client.post(
            f"/api/v1/projects/{storyboarded_project}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "maybe"},
        )
        assert resp.status_code == 400
        count = (await db_session.execute(
            text("SELECT count(*) FROM project_gate_decisions WHERE project_id = :p"),
            {"p": storyboarded_project},
        )).scalar()
        assert count == 0

    async def test_a_decision_cannot_be_recorded_against_no_artifact(
        self, client, operator_token, db_session,
    ):
        """An approval that names nothing is a timestamp, not a gate record."""
        from app.core.security import decode_token
        from app.models.project import Project

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        now = datetime.now(timezone.utc)
        project = Project(
            id=uuid.uuid4(), name="empty", state="DRAFT",
            created_by=owner, created_at=now, updated_at=now,
        )
        db_session.add(project)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/projects/{project.id}/gates/storyboard",
            headers=_h(operator_token),
            json={"decision": "approved"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"]["code"] == "GATE_ARTIFACT_ABSENT"


class TestFrozenStageBodiesAreUntouched:
    def test_no_stage_task_body_imports_the_gate_service(self):
        """(f) AD-05 section 8 freezes the eight stage task bodies.

        The enforcement lives at the TRIGGER layer. If it had needed a hook
        inside a stage, this package's instruction was to STOP that half and
        report; it did not need one, and this test is what keeps that true.
        """
        import pathlib

        repo = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for path in (repo / "ivgs-workers" / "tasks").glob("stage*.py"):
            body = path.read_text(encoding="utf-8")
            if "gate_service" in body or "GateService" in body:
                offenders.append(path.name)
        for name in ("video_generation_task.py", "talking_head_task.py"):
            path = repo / "ivgs-workers" / "tasks" / name
            if path.exists():
                body = path.read_text(encoding="utf-8")
                if "gate_service" in body or "GateService" in body:
                    offenders.append(name)
        assert not offenders, (
            "a frozen stage body reaches into the gate service: "
            + ", ".join(offenders)
        )
