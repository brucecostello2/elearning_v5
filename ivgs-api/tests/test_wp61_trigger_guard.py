"""
WP-61 Task 5 (WP-60 D-3, RULED) — the render trigger's in-flight guard.

**EVERY TEST HERE ASSERTS A BROKER MESSAGE, NOT A STATUS CODE**, which is the
WP-45 standard and is the only assertion that would have caught the defect.
A 409 that arrives *after* the dispatch is not a guard, and all six of the real
presses answered 200 while dispatching.

**AND ONE OF THESE TESTS WAS WRITTEN WRONG FIRST, WHICH IS WORTH RECORDING.**
The obvious test — press the trigger twice on a DRAFT project, assert one
broker message — PASSES WITHOUT THE GUARD. The first trigger moves the project
DRAFT -> TRANSCRIPT_REFINEMENT, and the state machine then refuses the second
on its own. Verified by deleting the guard and re-running: six of eight tests
still went green. A test that passes against the defect is the thing this
series of packages exists to stop, and it nearly shipped inside the fix for it.

**So the case that matters is a project in a TRIGGERABLE state that already has
a NON-TERMINAL JOB**, which is what the project's own state cannot express:

  * a run that failed part-way and left the project back in DRAFT while its
    jobs are still `pending`/`running`;
  * two requests inside one another's window, both reading DRAFT before either
    commits (the state write and the dispatch are in the same request);
  * any path that returns a project to a triggerable state with work
    outstanding.

`TestGuardBites` constructs that condition directly and is RED without the
guard. `TestStateMachineAlsoCoversTheSimpleCase` keeps the double-press case
and says in its own name that the state machine, not the guard, is what makes
it pass — so nobody later reads it as evidence the guard works.

`send_task` is patched at `app.services.celery_producer.celery_app` — the one
producer this path imports — so a site that stops going through the producer
fails these tests rather than passing them by accident.

SCOPE, STATED. The ruling names the TRIGGER endpoint, and that is what is
guarded. The six dispatches WP-60 measured on project 52d52867 were job_type
`video_generation` / `animation_generation`, i.e. they came through
`POST /projects/{id}/scenes/{sid}/regenerate`, which this ruling does not
name. That is reported as a decision, not silently widened.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

DISPATCH = "tasks.pipeline_orchestrator_v2.dispatch_pipeline"


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
async def draft_project(db_session, operator_token):
    """A DRAFT project with a transcript — the minimum a trigger accepts."""
    from app.core.security import decode_token
    from app.models.project import Project
    from app.models.transcript import Transcript

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    project = Project(
        id=uuid.uuid4(),
        name="WP-61 trigger guard",
        state="DRAFT",
        created_by=owner,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        Transcript(
            id=uuid.uuid4(),
            project_id=project.id,
            sequence_order=1,
            refined_text="Multiply the tens first.",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    return str(project.id)


async def _trigger(client, token, project_id):
    return await client.post(
        f"/api/v1/projects/{project_id}/trigger?tier=prototype",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest_asyncio.fixture
async def draft_project_with_outstanding_job(db_session, draft_project):
    """A DRAFT project that ALREADY has a running job.

    THE CONDITION THE GUARD EXISTS FOR, and the one the project's own state
    cannot express. It is not contrived: a run that fails part-way leaves
    exactly this — a triggerable state with work still outstanding.
    """
    from app.models.render_job import RenderJob

    job = RenderJob(
        id=uuid.uuid4(),
        project_id=uuid.UUID(draft_project),
        job_type="transcript_refinement",
        status="running",
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()
    return {"project_id": draft_project, "job_id": str(job.id)}


class TestGuardBites:
    """RED without the guard. Verified by deleting it and re-running."""

    async def test_a_trigger_while_a_run_is_outstanding_publishes_NOTHING(
        self, client, operator_token, draft_project_with_outstanding_job, broker
    ):
        """THE TEST.

        The project is DRAFT, it has a transcript, and the state machine is
        perfectly happy to trigger it. Only the job table knows that a run is
        already going. Without the guard this dispatches, and the assertion
        that catches it is the BROKER COUNT — not the status code.
        """
        resp = await _trigger(
            client, operator_token, draft_project_with_outstanding_job["project_id"]
        )

        assert broker.sent == [], (
            f"a trigger published {len(broker.sent)} message(s) while a run "
            f"was already outstanding: {broker.sent}. That is one more full "
            f"pipeline and one more talking-head render on node-04."
        )
        assert resp.status_code == 409

    async def test_the_outstanding_run_is_the_one_NAMED_in_the_refusal(
        self, client, operator_token, draft_project_with_outstanding_job, broker
    ):
        resp = await _trigger(
            client, operator_token, draft_project_with_outstanding_job["project_id"]
        )
        error = resp.json()["detail"]["error"]
        assert error["code"] == "PIPELINE_ALREADY_RUNNING"
        assert error["active_job"]["id"] == draft_project_with_outstanding_job["job_id"]
        assert error["active_job"]["status"] == "running"

    async def test_nothing_is_written_by_the_refused_trigger(
        self, client, operator_token, draft_project_with_outstanding_job, broker,
        db_session,
    ):
        """The guard runs before every side effect, and this proves it.

        A guard placed after the state write would leave the project moved and
        a `render_jobs` row inserted for a run that never happened — which is
        worse than the original defect, because it looks like progress.
        """
        from sqlalchemy import text

        pid = draft_project_with_outstanding_job["project_id"]
        before_state = await db_session.scalar(
            text("SELECT state::text FROM projects WHERE id = :i"), {"i": pid}
        )
        before_jobs = await db_session.scalar(
            text("SELECT count(*) FROM render_jobs WHERE project_id = :i"),
            {"i": pid},
        )

        assert (await _trigger(client, operator_token, pid)).status_code == 409

        assert await db_session.scalar(
            text("SELECT state::text FROM projects WHERE id = :i"), {"i": pid}
        ) == before_state == "DRAFT"
        assert await db_session.scalar(
            text("SELECT count(*) FROM render_jobs WHERE project_id = :i"),
            {"i": pid},
        ) == before_jobs

    async def test_the_guard_lifts_when_the_run_reaches_a_terminal_status(
        self, client, operator_token, draft_project_with_outstanding_job, broker,
        db_session,
    ):
        """The negative, and it is what makes the guard safe to ship.

        A guard that refuses forever is an outage, not a guard.
        """
        from sqlalchemy import text

        pid = draft_project_with_outstanding_job["project_id"]
        assert (await _trigger(client, operator_token, pid)).status_code == 409
        assert broker.sent == []

        await db_session.execute(
            text("UPDATE render_jobs SET status = 'failed' WHERE project_id = :i"),
            {"i": pid},
        )
        await db_session.commit()

        resp = await _trigger(client, operator_token, pid)
        assert resp.status_code == 200, resp.text
        assert len(broker.sent) == 1
        assert broker.sent[0]["name"] == DISPATCH


class TestStateMachineAlsoCoversTheSimpleCase:
    """Double-press on a clean DRAFT project — and WHY it passes.

    Named this way deliberately. These two pass with the guard deleted, because
    the first trigger moves the project out of DRAFT and the state machine
    refuses the second. They are kept because the behaviour is worth pinning
    and because the double-press is the shape an operator actually performs —
    but they are NOT evidence that the guard works, and a name like
    `test_second_dispatch_never_reaches_the_broker` would have implied they
    were. `TestGuardBites` above is that evidence.
    """

    async def test_the_first_trigger_dispatches_exactly_once(
        self, client, operator_token, draft_project, broker
    ):
        """The guard must not have broken the thing it guards."""
        resp = await _trigger(client, operator_token, draft_project)
        assert resp.status_code == 200, resp.text
        assert len(broker.sent) == 1
        assert broker.sent[0]["name"] == DISPATCH

    async def test_six_presses_in_a_row_publish_one_message(
        self, client, operator_token, draft_project, broker
    ):
        """Six presses, 50 seconds, one project — one broker message."""
        codes = []
        for _ in range(6):
            resp = await _trigger(client, operator_token, draft_project)
            codes.append(resp.status_code)

        assert len(broker.sent) == 1, (
            f"six presses produced {len(broker.sent)} broker messages. The "
            f"real incident produced six."
        )
        assert codes[0] == 200
        assert codes[1:] == [409] * 5

    async def test_the_refusal_NAMES_the_active_run(
        self, client, operator_token, draft_project, broker
    ):
        """409 alone tells an operator nothing they can act on.

        The ruling is "refuses (409, naming the active run)". The job id has to
        be in the payload so the GUI can link to it rather than telling the
        operator to go and look for it.
        """
        await _trigger(client, operator_token, draft_project)
        resp = await _trigger(client, operator_token, draft_project)

        body = resp.json()["detail"]["error"]
        assert body["code"] == "PIPELINE_ALREADY_RUNNING"
        active = body["active_job"]
        uuid.UUID(active["id"])  # a real job id, not a placeholder
        assert active["status"] in {"pending", "running"}
        assert active["job_type"]
        assert active["id"] in body["message"]



class TestTheDefinitionOfInFlight:
    def test_non_terminal_is_the_complement_of_terminal(self):
        """Written as NOT-terminal, deliberately.

        `job_status` is `pending, running, success, failed` (read live
        2026-08-26). Spelling the guard as `IN ('pending','running')` means a
        label added later — `cancelling`, say — slips through silently. The
        complement means it is treated as in-flight until somebody decides
        otherwise, which is the safe direction for a guard.
        """
        import inspect

        from app.services import project_service as ps

        assert ps.TERMINAL_JOB_STATUSES == {"success", "failed"}
        src = inspect.getsource(ps.ProjectService._active_job)
        assert "not_in" in src
        assert "TERMINAL_JOB_STATUSES" in src

    def test_the_guard_and_the_payload_use_THE_SAME_helper(self):
        """One definition of "in flight".

        The button reads `active_job` off the project payload; the server
        refuses on its own query. Two copies of that predicate is how a button
        and a server come to disagree about whether a run exists.
        """
        import inspect

        from app.services.project_service import ProjectService

        trigger_src = inspect.getsource(ProjectService.trigger_pipeline)
        assert "self._active_job(" in trigger_src

        # `_build_project_response` (whatever it is called) must also use it,
        # so search the whole class for a second, hand-rolled version.
        class_src = inspect.getsource(ProjectService)
        assert class_src.count('RenderJob.status.in_(["pending", "running"])') == 0, (
            "a second, hand-written definition of 'active job' has reappeared "
            "in ProjectService. There must be exactly one."
        )
        assert class_src.count("await self._active_job(") >= 2
