"""
WP-62 Task 3 — the frozen stepper: the choke point, and the recomputation.

**THE DEFECT WAS NOT "NO WRITER".** WP-45 built `advance_project_state` and
`PATCH /projects/{id}/state`, and both work: measured 2026-08-26 on project
64207933, `{"new_state": "STORYBOARD_GENERATION", "event":
"project_state_advanced"}` at 09:00:36, a 200.

What froze it is `reset_after_terminal_failure` firing on the failure of ANY
job of the project, including a stale one. 400 ms after a human approved the
storyboard, a superseded job's failure callback returned the project to DRAFT,
and the three stage hops that followed were all refused:

    09:07:49  MANIFEST_GENERATION   409 "Invalid state transition: DRAFT -> ..."
    09:07:53  AUDIO_GENERATION      409
    09:08:24  TALKING_HEAD_RENDER   409

`TestTheResetOnlyFiresWhenTheRunIsOver` reconstructs that exact sequence and is
RED without the fix. The rest pin the recomputation, which is what makes
EXISTING projects true without a hand-edited row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def service_token_headers(admin_token):
    """Headers for the worker-fleet callback routes.

    `PATCH /jobs/{id}` is gated by `get_service_or_user`, which accepts the
    internal service token OR a normal user JWT. An admin JWT is used because
    the service token is a deployment secret and a test suite has no business
    carrying one. Same reasoning as `test_wp45_dedup_and_gate.py:28`.
    """
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def project_factory(db_session, operator_token):
    from app.core.security import decode_token
    from app.models.project import Project

    owner = uuid.UUID(decode_token(operator_token)["sub"])

    async def make(state="DRAFT", name="WP-62 progress"):
        now = datetime.now(timezone.utc)
        p = Project(
            id=uuid.uuid4(), name=name, state=state, created_by=owner,
            created_at=now, updated_at=now,
        )
        db_session.add(p)
        await db_session.commit()
        return p

    return make


async def _job(db_session, project_id, job_type, status, minutes_ago=0):
    from app.models.render_job import RenderJob

    now = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    job = RenderJob(
        id=uuid.uuid4(), project_id=project_id, job_type=job_type,
        status=status, created_at=now,
    )
    db_session.add(job)
    await db_session.commit()
    return job


async def _checkpoint(db_session, job_id, stage, status="complete", minutes_ago=0):
    from app.models.checkpoint import PipelineCheckpoint

    cp = PipelineCheckpoint(
        id=uuid.uuid4(), job_id=job_id, stage_name=stage, stage_index=1,
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    db_session.add(cp)
    await db_session.commit()
    return cp


class TestTheResetOnlyFiresWhenTheRunIsOver:
    """RED WITHOUT THE FIX. The measured sequence, reconstructed."""

    async def test_a_stale_job_failing_mid_run_does_not_reset_the_project(
        self, client, service_token_headers, db_session, project_factory,
    ):
        project = await project_factory(state="MEDIA_GENERATION")
        stale = await _job(
            db_session, project.id, "storyboard_generation", "running",
            minutes_ago=10,
        )
        # The run that is actually in flight.
        await _job(db_session, project.id, "image_generation", "running")

        resp = await client.patch(
            f"/api/v1/jobs/{stale.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "superseded"},
        )
        assert resp.status_code == 200

        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"),
            {"i": str(project.id)},
        )).scalar()
        assert state == "MEDIA_GENERATION", (
            "the project was walked back to DRAFT while a run was still in "
            "flight; every stage hop after this point is refused as an illegal "
            "transition out of DRAFT, which is the measured 64207933 defect"
        )

    async def test_the_last_job_failing_still_resets_it(
        self, client, service_token_headers, db_session, project_factory,
    ):
        """P1.4q IS NOT REMOVED and is not weakened.

        It exists because a project stuck in an in-progress state answers 409
        forever and the operator's documented recourse was an UPDATE statement.
        When the failing job IS the last live work, the reset still fires.
        """
        project = await project_factory(state="MEDIA_GENERATION")
        job = await _job(db_session, project.id, "image_generation", "running")

        resp = await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "GPU OOM"},
        )
        assert resp.status_code == 200
        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"),
            {"i": str(project.id)},
        )).scalar()
        assert state == "DRAFT"


class TestTheStepperIsRecomputedNotRead:
    async def test_a_project_whose_column_is_stale_still_reads_true(
        self, client, operator_token, db_session, project_factory,
    ):
        """c12fa967's shape: DRAFT in the column, a final render in the record.

        This is the assertion the ruling asks for -- "c12fa967's stepper true
        with no manual edit". The column is left exactly as found.
        """
        project = await project_factory(state="DRAFT")
        job = await _job(db_session, project.id, "final_render", "success", 30)
        for stage in (
            "transcript_refinement", "storyboard_generation",
            "image_generation", "composition_manifest", "tts_audio",
            "talking_head_render", "prototype_draft", "final_render",
        ):
            await _checkpoint(db_session, job.id, stage)

        resp = await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        by_key = {s["key"]: s["status"] for s in body["steps"]}
        assert by_key["TRANSCRIPT_REFINEMENT"] == "complete"
        assert by_key["PROTOTYPE_DRAFT"] == "complete"
        assert by_key["FINAL_RENDER"] == "complete"

        # And the gap is REPORTED, not silently corrected.
        assert body["stored_state"] == "DRAFT"
        assert body["stored_state_matches"] is False
        assert body["derived_state"] != "DRAFT"

        # NOTHING WAS WRITTEN. `projects.state` is untouched by a read.
        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"),
            {"i": str(project.id)},
        )).scalar()
        assert state == "DRAFT"

    async def test_the_latest_outcome_per_stage_wins_not_the_worst(
        self, client, operator_token, db_session, project_factory,
    ):
        """A stage that failed at 15:24 and completed at 16:03 is GREEN.

        `lib/pipeline-run.ts` records why a pessimistic cross-job merge is
        wrong for the RUN panel; it is wrong here for the same reason and the
        stepper answers a different question, so it takes the last word.
        """
        project = await project_factory(state="DRAFT")
        failed = await _job(db_session, project.id, "storyboard_generation", "failed", 60)
        ok = await _job(db_session, project.id, "storyboard_generation", "success", 30)
        await _checkpoint(db_session, failed.id, "storyboard_generation", "failed", 60)
        await _checkpoint(db_session, ok.id, "storyboard_generation", "complete", 30)

        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        by_key = {s["key"]: s["status"] for s in body["steps"]}
        assert by_key["STORYBOARD_GENERATION"] in ("complete", "gated")

    async def test_a_failed_stage_is_red(
        self, client, operator_token, db_session, project_factory,
    ):
        project = await project_factory(state="DRAFT")
        job = await _job(db_session, project.id, "transcript_refinement", "failed")
        await _checkpoint(db_session, job.id, "transcript_refinement", "failed")

        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        by_key = {s["key"]: s["status"] for s in body["steps"]}
        assert by_key["TRANSCRIPT_REFINEMENT"] == "failed"

    async def test_an_open_gate_is_amber_at_the_step_that_owns_it(
        self, client, operator_token, db_session, project_factory,
    ):
        """AMBER HAD NOWHERE TO APPEAR BEFORE THIS PACKAGE.

        The gates had no record, so no surface could say "this is waiting on
        you" and a blocked pipeline simply looked stopped.
        """
        from app.models.storyboard_scene import StoryboardScene

        project = await project_factory(state="STORYBOARD_GENERATION")
        now = datetime.now(timezone.utc)
        db_session.add(
            StoryboardScene(
                id=uuid.uuid4(), project_id=project.id, scene_index=0,
                narration_text="x", visual_description="y", media_type="image",
                duration_seconds=4.0, created_at=now, updated_at=now,
            )
        )
        await db_session.commit()

        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        by_key = {s["key"]: s["status"] for s in body["steps"]}
        assert by_key["STORYBOARD_GENERATION"] == "gated"
        assert body["gates"]["storyboard"]["open"] is True

    async def test_step_9_is_review_and_it_is_the_draft_gate(
        self, client, operator_token, db_session, project_factory,
    ):
        """RULED: 'stepper stage 9 Review is the draft gate's home'."""
        project = await project_factory()
        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        step9 = [s for s in body["steps"] if s["index"] == 9][0]
        assert step9["key"] == "USER_REVIEW"
        assert step9["label"] == "Review"
        assert step9["gate"] == "draft"

    async def test_there_are_exactly_eleven_steps(
        self, client, operator_token, project_factory,
    ):
        project = await project_factory()
        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        assert len(body["steps"]) == 11

    async def test_the_step_order_matches_the_state_machine(self):
        """ONE vocabulary. The stepper and the FSM must not mean different
        things by the same word."""
        from app.services.project_progress import STEPS
        from shared.models.enums import ProjectState

        linear = [
            ProjectState.DRAFT, ProjectState.TRANSCRIPT_REFINEMENT,
            ProjectState.STORYBOARD_GENERATION, ProjectState.MEDIA_GENERATION,
            ProjectState.MANIFEST_GENERATION, ProjectState.AUDIO_GENERATION,
            ProjectState.TALKING_HEAD_RENDER, ProjectState.PROTOTYPE_DRAFT,
            ProjectState.USER_REVIEW, ProjectState.FINAL_RENDER,
            ProjectState.COMPLETE,
        ]
        assert [s.key for s in STEPS] == [s.value for s in linear]


class TestOneComputationFeedsEverySurface:
    async def test_the_tab_indicators_come_from_the_same_payload(
        self, client, operator_token, db_session, project_factory,
    ):
        """RULED: one computation feeds stepper, per-tab indicators and the
        Overview run panel. If the tabs were computed separately they could
        disagree, which is the class of defect this package exists to close."""
        project = await project_factory(state="DRAFT")
        job = await _job(db_session, project.id, "transcript_refinement", "success")
        await _checkpoint(db_session, job.id, "transcript_refinement")

        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        by_key = {s["key"]: s["status"] for s in body["steps"]}
        assert body["tabs"]["transcripts"] == by_key["TRANSCRIPT_REFINEMENT"]
        assert body["tabs"]["draft"] == by_key["PROTOTYPE_DRAFT"]
        # Tabs that are not a pipeline stage get no indicator at all: a grey
        # dot on Jobs would read as "no jobs".
        for non_stage in ("overview", "jobs", "prompts", "languages"):
            assert non_stage not in body["tabs"]

    async def test_an_active_run_colours_its_step_blue(
        self, client, operator_token, db_session, project_factory,
    ):
        project = await project_factory(state="MEDIA_GENERATION")
        await _job(db_session, project.id, "image_generation", "running")

        body = (await client.get(
            f"/api/v1/projects/{project.id}/progress", headers=_h(operator_token),
        )).json()
        by_key = {s["key"]: s["status"] for s in body["steps"]}
        assert by_key["MEDIA_GENERATION"] == "active"
        assert body["active_run"]["job_type"] == "image_generation"
        assert body["active_run"]["step"] == "MEDIA_GENERATION"
