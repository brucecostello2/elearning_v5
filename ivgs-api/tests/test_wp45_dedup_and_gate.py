"""WP-45 Tasks 1, 2, 4, 5 and 6 — dedup, gate 2, timestamps, the fleet, riders.

The common shape of every defect here is a system that answered confidently
about something it had not measured:

* a dedup probe that could not run reported "no duplicate" (Task 1)
* a state machine with no caller left five of thirteen states unreachable, so a
  finished draft never reached the state its own review gate requires (Task 2)
* two timestamp columns nothing wrote (Task 5)
* an empty table read as a fleet of zero GPUs while three were working (Task 4)
* a progress field that did not exist rendering as 0% (Task 6c)

So these tests are mostly about the difference between a value and an absence.
"""
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text


@pytest.fixture
def service_token_headers(admin_token):
    """Headers for the worker-fleet callback routes.

    `PATCH /jobs/{id}` is gated by `get_service_or_user`, which accepts the
    internal service token OR a normal user JWT. The tests use an admin JWT
    because the service token is a deployment secret and a test suite has no
    business carrying one.
    """
    return {"Authorization": f"Bearer {admin_token}"}


# ===========================================================================
# TASK 1 — asset dedup and provenance
# ===========================================================================

@pytest.fixture
async def dedup_project(db_session, operator_token):
    from app.core.security import decode_token
    from app.models.project import Project

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    project = Project(
        id=uuid.uuid4(), name="dedup project", state="MEDIA_GENERATION",
        created_by=owner,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    await db_session.commit()
    return project


@pytest.fixture
def seaweed():
    """SeaweedFS, stubbed. These tests are about the metadata, not the bytes."""
    with patch(
        "app.services.asset_service.seaweedfs_client"
    ) as client:
        client.upload_file = AsyncMock(return_value="3,01deadbeef")
        client.download_file = AsyncMock(return_value=b"stored bytes")
        client.delete = AsyncMock(return_value=True)
        yield client


@pytest.mark.asyncio
class TestTask1DuplicateCheckRoute:
    """`GET /api/v1/assets?sha256=` — the route that did not exist."""

    async def test_the_route_exists_at_all(
        self, client: AsyncClient, operator_token,
    ):
        # THE DEFECT: asset_router carried only /{asset_id} and its children, so
        # FastAPI matched the bare path to nothing and answered 404. The worker
        # helper caught it and returned None, which its four callers read as
        # "no duplicate exists" — so dedup was dead fleet-wide for image, video,
        # animation and audio, and reported itself as working.
        resp = await client.get(
            "/api/v1/assets?sha256=" + "0" * 64,
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code != 404, (
            "the dedup probe route must exist; a 404 here IS the original bug"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_no_duplicate_is_an_empty_list_not_an_error(
        self, client: AsyncClient, operator_token,
    ):
        # "checked, nothing there" must be distinguishable from "could not
        # check". An empty 200 is the first; a non-200 is the second.
        resp = await client.get(
            "/api/v1/assets?content_hash=" + "b" * 64,
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_an_unfiltered_probe_is_refused(
        self, client: AsyncClient, operator_token,
    ):
        # Without a hash this would be an unbounded asset dump. The project
        # route serves that, and says so in the message.
        resp = await client.get(
            "/api/v1/assets",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    async def test_it_finds_by_content_hash(
        self, client: AsyncClient, operator_token, db_session, dedup_project,
    ):
        from app.models.asset import Asset

        digest = hashlib.sha256(b"the frame").hexdigest()
        asset = Asset(
            id=uuid.uuid4(), project_id=dedup_project.id, asset_type="image",
            content_hash=digest, storage_tier="hot",
            seaweedfs_path="/ivgs/images/x/image.png",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(asset)
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/assets?sha256={digest}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == str(asset.id)
        # The worker reads this key off the payload. Three call sites used to
        # read `storage_path`, which the API has never sent, so a dedup hit
        # lost the path.
        assert body[0]["seaweedfs_path"] == "/ivgs/images/x/image.png"

    async def test_it_finds_by_generation_params_hash(
        self, client: AsyncClient, operator_token, db_session, dedup_project,
    ):
        # The expensive one. Video and animation probe on the params hash
        # BEFORE rendering, so a hit skips the GPU work, not just the upload.
        from app.models.asset import Asset

        params = hashlib.sha256(b"prompt+seed+inputs").hexdigest()
        asset = Asset(
            id=uuid.uuid4(), project_id=dedup_project.id, asset_type="video",
            content_hash="c" * 64, generation_params_hash=params,
            storage_tier="hot", created_at=datetime.now(timezone.utc),
        )
        db_session.add(asset)
        await db_session.commit()

        for query in (f"sha256={params}", f"generation_params_hash={params}"):
            resp = await client.get(
                f"/api/v1/assets?{query}",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            assert [a["id"] for a in resp.json()] == [str(asset.id)], query

    async def test_a_deleted_asset_is_not_a_dedup_target(
        self, client: AsyncClient, operator_token, db_session, dedup_project,
    ):
        from app.models.asset import Asset

        digest = "d" * 64
        db_session.add(Asset(
            id=uuid.uuid4(), project_id=dedup_project.id, asset_type="image",
            content_hash=digest, storage_tier="deleted",
            created_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/assets?sha256={digest}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.json() == [], "a tombstone must not be re-referenced"


@pytest.mark.asyncio
class TestTask1UploadPersistsWhatCallersSend:
    """The three form fields the route discarded in silence."""

    def _upload(self, client, token, project_id, data, content=b"the bytes"):
        return client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("image.png", content, "image/png")},
            data=data,
        )

    async def test_content_hash_params_hash_and_metadata_are_all_stored(
        self, client: AsyncClient, admin_token, dedup_project, db_session, seaweed,
    ):
        content = b"an image"
        provenance = {
            "engine": "comfyui",
            "model": "flux1-schnell",
            "prompt_id": "abc-123",
            "reference_image_asset_id": str(uuid.uuid4()),
        }
        resp = await self._upload(
            client, admin_token, dedup_project.id,
            {
                "asset_type": "image",
                "content_hash": hashlib.sha256(content).hexdigest(),
                "generation_params_hash": "e" * 64,
                "metadata": json.dumps(provenance),
            },
            content=content,
        )
        assert resp.status_code == 201, resp.text

        row = (await db_session.execute(
            text(
                "SELECT generation_params_hash, generation_metadata "
                "FROM assets WHERE id = :i"
            ),
            {"i": resp.json()["id"]},
        )).first()
        # THE DEFECT: FastAPI drops form fields a signature does not declare,
        # without an error on either side, so every one of these went nowhere
        # and no caller could tell (WP-46 addendum A5.2 / ledger L-7).
        assert row[0] == "e" * 64
        assert row[1] == provenance
        assert row[1]["engine"] == "comfyui"

    async def test_a_content_hash_that_does_not_match_the_bytes_is_refused(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        # A caller's hash is a CLAIM about what it sent. Storing bytes under a
        # hash that is not theirs poisons every future lookup with a row that
        # can never be found by its real content.
        resp = await self._upload(
            client, admin_token, dedup_project.id,
            {"asset_type": "image", "content_hash": "f" * 64},
        )
        assert resp.status_code == 400
        assert "does not match" in resp.text

    async def test_a_malformed_content_hash_is_refused_by_shape(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        resp = await self._upload(
            client, admin_token, dedup_project.id,
            {"asset_type": "image", "content_hash": "not-a-hash"},
        )
        assert resp.status_code == 400
        assert "64 lowercase hex" in resp.text

    async def test_metadata_that_is_not_an_object_is_refused(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        # A list would store, and then no reader could ask it "which engine
        # made this?".
        resp = await self._upload(
            client, admin_token, dedup_project.id,
            {"asset_type": "image", "metadata": json.dumps(["a", "b"])},
        )
        assert resp.status_code == 400
        assert "must be a JSON object" in resp.text

    async def test_broken_json_metadata_is_refused_with_the_parse_error(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        resp = await self._upload(
            client, admin_token, dedup_project.id,
            {"asset_type": "image", "metadata": "{not json"},
        )
        assert resp.status_code == 400
        assert "not valid JSON" in resp.text

    async def test_omitting_the_new_fields_still_works(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        # Every existing caller in the fleet must keep working unchanged.
        resp = await self._upload(
            client, admin_token, dedup_project.id, {"asset_type": "image"},
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestTask1DedupHitsOnIdenticalInputs:
    """The point of all of it: a repeat produces a hit, not a second copy."""

    async def _upload(self, client, token, project_id, content, **extra):
        return await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("m.png", content, "image/png")},
            data={"asset_type": "image", **extra},
        )

    async def test_identical_bytes_dedup_and_say_so(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        content = b"identical output"
        first = await self._upload(client, admin_token, dedup_project.id, content)
        second = await self._upload(client, admin_token, dedup_project.id, content)

        assert first.json()["id"] == second.json()["id"]
        assert first.json()["was_deduplicated"] is False
        # The response used to be byte-identical for a store and a re-reference,
        # so the caller could not tell which had happened.
        assert second.json()["was_deduplicated"] is True
        assert second.json()["reference_count"] == 2

    async def test_identical_generation_params_dedup_even_on_different_bytes(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        # This is the case that saves GPU time: the same request, rendered
        # again. A diffusion model is not bit-reproducible, so the bytes differ
        # and only the params hash can match.
        params = "1" * 64
        first = await self._upload(
            client, admin_token, dedup_project.id, b"render one",
            generation_params_hash=params,
        )
        second = await self._upload(
            client, admin_token, dedup_project.id, b"render two, same request",
            generation_params_hash=params,
        )
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["was_deduplicated"] is True

    async def test_different_inputs_do_not_dedup(
        self, client: AsyncClient, admin_token, dedup_project, seaweed,
    ):
        a = await self._upload(client, admin_token, dedup_project.id, b"one")
        b = await self._upload(client, admin_token, dedup_project.id, b"two")
        assert a.json()["id"] != b.json()["id"]
        assert b.json()["was_deduplicated"] is False

    async def test_a_dedup_hit_backfills_a_params_hash_the_original_lacked(
        self, client: AsyncClient, admin_token, dedup_project, db_session, seaweed,
    ):
        # Assets stored before this fix have no params hash and would stay
        # invisible to a params probe forever. The first re-upload repairs them.
        content = b"stored before the fix"
        first = await self._upload(client, admin_token, dedup_project.id, content)
        await self._upload(
            client, admin_token, dedup_project.id, content,
            generation_params_hash="2" * 64,
        )
        stored = (await db_session.execute(
            text("SELECT generation_params_hash FROM assets WHERE id = :i"),
            {"i": first.json()["id"]},
        )).scalar()
        assert stored == "2" * 64


# ===========================================================================
# TASK 2 — gate 2
# ===========================================================================

@pytest.mark.asyncio
class TestTask2ProjectStateRoute:
    """ORCH-5: transition_state was implemented and had no route or caller."""

    async def _project(self, db_session, token, state):
        from app.core.security import decode_token
        from app.models.project import Project

        project = Project(
            id=uuid.uuid4(), name=f"state {state}", state=state,
            created_by=uuid.UUID(decode_token(token)["sub"]),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.commit()
        return project

    async def test_the_route_exists(
        self, client: AsyncClient, operator_token, db_session,
    ):
        project = await self._project(db_session, operator_token, "MEDIA_GENERATION")
        resp = await client.patch(
            f"/api/v1/projects/{project.id}/state",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"state": "MANIFEST_GENERATION", "reason": "test"},
        )
        assert resp.status_code != 404, "the state route must exist (ORCH-5)"
        assert resp.status_code == 200
        assert resp.json()["state"] == "MANIFEST_GENERATION"

    async def test_the_back_half_is_reachable_state_by_state(
        self, client: AsyncClient, operator_token, db_session,
    ):
        # WP-39 §4 Gap A: MANIFEST_GENERATION, AUDIO_GENERATION,
        # TALKING_HEAD_RENDER, PROTOTYPE_DRAFT and USER_REVIEW could not appear
        # on any project, because nothing advanced state past MEDIA_GENERATION.
        project = await self._project(db_session, operator_token, "MEDIA_GENERATION")
        chain = [
            "MANIFEST_GENERATION", "AUDIO_GENERATION", "TALKING_HEAD_RENDER",
            "PROTOTYPE_DRAFT", "USER_REVIEW",
        ]
        for target in chain:
            resp = await client.patch(
                f"/api/v1/projects/{project.id}/state",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"state": target},
            )
            assert resp.status_code == 200, f"{target}: {resp.text}"
            assert resp.json()["state"] == target

        # And USER_REVIEW is the state the gate needs: spec §6.1's
        # "post-assembly: project state transitions to USER_REVIEW".
        assert resp.json()["state"] == "USER_REVIEW"

    async def test_an_illegal_hop_is_a_409_naming_the_legal_set(
        self, client: AsyncClient, operator_token, db_session,
    ):
        project = await self._project(db_session, operator_token, "DRAFT")
        resp = await client.patch(
            f"/api/v1/projects/{project.id}/state",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"state": "COMPLETE"},
        )
        assert resp.status_code == 409
        assert "Valid transitions" in resp.text

    async def test_it_is_idempotent_because_the_worker_retries_it(
        self, client: AsyncClient, operator_token, db_session,
    ):
        project = await self._project(db_session, operator_token, "MEDIA_GENERATION")
        for _ in range(3):
            resp = await client.patch(
                f"/api/v1/projects/{project.id}/state",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"state": "MANIFEST_GENERATION"},
            )
            assert resp.status_code == 200

    async def test_an_unknown_state_is_a_400_not_a_500(
        self, client: AsyncClient, operator_token, db_session,
    ):
        project = await self._project(db_session, operator_token, "DRAFT")
        resp = await client.patch(
            f"/api/v1/projects/{project.id}/state",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"state": "NEARLY_DONE"},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestTask2Stage8IsDispatched:
    """Gap B: /trigger from USER_REVIEW flipped state and sent no message."""

    async def _reviewed_project(self, db_session, token):
        from app.core.security import decode_token
        from app.models.project import Project

        project = Project(
            id=uuid.uuid4(), name="reviewed draft", state="USER_REVIEW",
            description="a draft the operator has approved",
            created_by=uuid.UUID(decode_token(token)["sub"]),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.commit()
        return project

    async def test_triggering_from_user_review_produces_a_broker_message(
        self, client: AsyncClient, operator_token, db_session,
    ):
        from tests.test_wp45_dispatch import Broker

        project = await self._reviewed_project(db_session, operator_token)
        broker = Broker()
        with patch("app.services.celery_producer.celery_app", broker):
            resp = await client.post(
                f"/api/v1/projects/{project.id}/trigger",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "FINAL_RENDER"

        # THE ASSERTION. The state flipped and the row was inserted before this
        # fix too; the send_task was gated on DRAFT, so Stage 8 never ran and
        # "Start final render" was a button with nothing behind it.
        assert len(broker.sent) == 1, "gate 2 must dispatch Stage 8"
        assert broker.sent[0].name == (
            "tasks.pipeline_orchestrator_v2.dispatch_pipeline"
        )
        assert broker.sent[0].kwargs["job_context_dict"]["current_stage"] == (
            "final_render"
        )

    async def test_the_draft_path_still_dispatches_stage_1(
        self, client: AsyncClient, operator_token, project_with_transcript,
    ):
        from tests.test_wp45_dispatch import Broker

        broker = Broker()
        with patch("app.services.celery_producer.celery_app", broker):
            resp = await client.post(
                f"/api/v1/projects/{project_with_transcript['id']}/trigger",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200, resp.text
        assert broker.sent[0].kwargs["job_context_dict"]["current_stage"] == (
            "transcript_refinement"
        )


@pytest.mark.asyncio
class TestTask2FailedPathReset:
    """P1.4q, ruled: a terminal failure returns the project to DRAFT."""

    async def _running(self, db_session, token, state="MEDIA_GENERATION"):
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        project = Project(
            id=uuid.uuid4(), name="will fail", state=state,
            created_by=uuid.UUID(decode_token(token)["sub"]),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="image_generation",
            status="running", created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()
        return project, job

    async def test_a_terminal_failure_returns_the_project_to_draft(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        project, job = await self._running(db_session, operator_token)
        resp = await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "GPU OOM"},
        )
        assert resp.status_code == 200

        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"), {"i": str(project.id)},
        )).scalar()
        # Without this the project stays in MEDIA_GENERATION and POST /trigger
        # answers 409 INVALID_STATE_TRANSITION forever. The operator's
        # documented recourse was an UPDATE statement.
        assert state == "DRAFT"

    async def test_the_job_history_keeps_the_record(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        # No new project state is needed precisely because this survives.
        project, job = await self._running(db_session, operator_token)
        await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "GPU OOM"},
        )
        row = (await db_session.execute(
            text("SELECT status, error_message FROM render_jobs WHERE id = :i"),
            {"i": str(job.id)},
        )).first()
        assert row[0] == "failed"
        assert row[1] == "GPU OOM"

    async def test_a_success_does_not_reset_anything(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        project, job = await self._running(db_session, operator_token)
        await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "success"},
        )
        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"), {"i": str(project.id)},
        )).scalar()
        assert state == "MEDIA_GENERATION"

    async def test_a_repeated_failure_callback_does_not_reset_twice(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        # The worker retries this call. A second "failed" must not walk the
        # project back to DRAFT after somebody has deliberately moved it on.
        project, job = await self._running(db_session, operator_token)
        await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "GPU OOM"},
        )
        await db_session.execute(
            text("UPDATE projects SET state = 'TRANSCRIPT_REFINEMENT' WHERE id = :i"),
            {"i": str(project.id)},
        )
        await db_session.commit()

        await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "GPU OOM"},
        )
        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"), {"i": str(project.id)},
        )).scalar()
        assert state == "TRANSCRIPT_REFINEMENT"

    async def test_a_complete_project_is_not_undone_by_a_late_failure(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        project, job = await self._running(db_session, operator_token, state="COMPLETE")
        await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers,
            json={"status": "failed", "error_message": "a late straggler"},
        )
        state = (await db_session.execute(
            text("SELECT state FROM projects WHERE id = :i"), {"i": str(project.id)},
        )).scalar()
        assert state == "COMPLETE"


# ===========================================================================
# TASK 5 — job timestamps
# ===========================================================================

@pytest.mark.asyncio
class TestTask5JobTimestamps:
    """render_jobs.started_at / .completed_at were dead columns."""

    async def _job(self, db_session, token, status="pending"):
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        project = Project(
            id=uuid.uuid4(), name="timed", state="MEDIA_GENERATION",
            created_by=uuid.UUID(decode_token(token)["sub"]),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="image_generation",
            status=status, created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()
        return job

    async def test_running_stamps_started_at(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        job = await self._job(db_session, operator_token)
        resp = await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers, json={"status": "running"},
        )
        # NULL on all 23 rows on the fleet before this: a grep for either
        # identifier across ivgs-api, ivgs-workers and shared/ found only reads.
        assert resp.json()["started_at"] is not None
        assert resp.json()["completed_at"] is None

    async def test_terminal_stamps_completed_at(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        job = await self._job(db_session, operator_token)
        await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers, json={"status": "running"},
        )
        resp = await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers, json={"status": "success"},
        )
        assert resp.json()["completed_at"] is not None

    async def test_started_at_is_not_overwritten_by_a_second_running(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        # A retry re-announces "running". The duration must be measured from
        # the first start, not reset by every retry.
        job = await self._job(db_session, operator_token)
        first = (await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers, json={"status": "running"},
        )).json()["started_at"]
        second = (await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers, json={"status": "running"},
        )).json()["started_at"]
        assert first == second

    async def test_a_job_that_never_started_keeps_a_null_start(
        self, client: AsyncClient, service_token_headers, db_session, operator_token,
    ):
        # Recording created_at as the start would be an invention. NULL says
        # "not measured", which is the truth.
        job = await self._job(db_session, operator_token)
        resp = await client.patch(
            f"/api/v1/jobs/{job.id}",
            headers=service_token_headers, json={"status": "failed"},
        )
        assert resp.json()["started_at"] is None
        assert resp.json()["completed_at"] is not None

    async def test_cancel_stamps_a_completion(
        self, client: AsyncClient, operator_token, db_session,
    ):
        from tests.test_wp45_dispatch import Broker

        job = await self._job(db_session, operator_token, status="running")
        with patch("app.services.celery_producer.celery_app", Broker()):
            resp = await client.post(
                f"/api/v1/jobs/{job.id}/cancel",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.json()["completed_at"] is not None


# ===========================================================================
# TASK 6(a) — the cross-project job route
# ===========================================================================

@pytest.mark.asyncio
class TestTask6aCrossProjectJobs:

    async def test_the_route_exists(self, client: AsyncClient, operator_token):
        resp = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code != 404, (
            "no cross-project job route existed, so the tracker made 1+N requests"
        )
        assert resp.status_code == 200

    async def test_it_returns_jobs_from_more_than_one_project(
        self, client: AsyncClient, operator_token, db_session,
    ):
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        for n in range(3):
            project = Project(
                id=uuid.uuid4(), name=f"p{n}", state="DRAFT", created_by=owner,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db_session.add(project)
            await db_session.flush()
            db_session.add(RenderJob(
                id=uuid.uuid4(), project_id=project.id,
                job_type="image_generation", status="pending",
                created_at=datetime.now(timezone.utc) + timedelta(seconds=n),
            ))
        await db_session.commit()

        resp = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {operator_token}"},
        )
        body = resp.json()
        assert body["total"] == 3
        assert len({j["project_id"] for j in body["data"]}) == 3

    async def test_the_status_filter_actually_filters(
        self, client: AsyncClient, operator_token, db_session,
    ):
        # The tracker's filters used to be sent to the projects route, which
        # ignores every one of them, so no filter control did anything.
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        owner = uuid.UUID(decode_token(operator_token)["sub"])
        project = Project(
            id=uuid.uuid4(), name="mixed", state="DRAFT", created_by=owner,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        for status_value in ("pending", "running", "failed", "failed"):
            db_session.add(RenderJob(
                id=uuid.uuid4(), project_id=project.id,
                job_type="image_generation", status=status_value,
                created_at=datetime.now(timezone.utc),
            ))
        await db_session.commit()

        resp = await client.get(
            "/api/v1/jobs?status=failed",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.json()["total"] == 2

    async def test_an_operator_sees_only_their_own_projects_jobs(
        self, client: AsyncClient, operator_token, admin_token, db_session,
    ):
        from app.core.security import decode_token
        from app.models.project import Project
        from app.models.render_job import RenderJob

        other = uuid.UUID(decode_token(admin_token)["sub"])
        project = Project(
            id=uuid.uuid4(), name="not yours", state="DRAFT", created_by=other,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        db_session.add(RenderJob(
            id=uuid.uuid4(), project_id=project.id,
            job_type="image_generation", status="pending",
            created_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.get(
            "/api/v1/jobs", headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.json()["total"] == 0


# ===========================================================================
# TASK 6(c) — derived per-language progress
# ===========================================================================

@pytest.mark.asyncio
class TestTask6cLanguageProgress:

    async def _project_with_variants(self, db_session, token):
        from app.core.security import decode_token
        from app.models.language_variant import LanguageVariant
        from app.models.project import Project

        owner = uuid.UUID(decode_token(token)["sub"])
        project = Project(
            id=uuid.uuid4(), name="multilingual", state="COMPLETE",
            created_by=owner,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.flush()
        source = LanguageVariant(
            id=uuid.uuid4(), project_id=project.id, language_code="en-US",
            state="complete",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        target = LanguageVariant(
            id=uuid.uuid4(), project_id=project.id, language_code="fr-FR",
            state="pending", created_at=datetime.now(timezone.utc),
        )
        db_session.add_all([source, target])
        await db_session.commit()
        return project, source, target

    async def test_no_run_is_null_and_never_zero(
        self, client: AsyncClient, operator_token, db_session,
    ):
        project, _source, _target = await self._project_with_variants(
            db_session, operator_token,
        )
        resp = await client.get(
            f"/api/v1/projects/{project.id}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # THE DEFECT: `variant.progress_percent || 0` over a field that did not
        # exist rendered as a confident 0% beside a language with a finished
        # 720p draft on disk. Null and zero must stay different values.
        for variant in resp.json():
            assert variant["progress_percent"] is None
            assert variant["progress_source"]

    async def test_progress_is_derived_from_that_variants_checkpoints(
        self, client: AsyncClient, operator_token, db_session,
    ):
        from app.models.checkpoint import PipelineCheckpoint
        from app.models.render_job import RenderJob

        project, _source, target = await self._project_with_variants(
            db_session, operator_token,
        )
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="localisation",
            status="running", language_code="fr-FR",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.flush()
        for i, stage in enumerate(["audio_generation", "talking_head_render"]):
            db_session.add(PipelineCheckpoint(
                id=uuid.uuid4(), job_id=job.id, stage_name=stage,
                stage_index=i, status="complete",
                created_at=datetime.now(timezone.utc),
            ))
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/projects/{project.id}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        fr = next(v for v in resp.json() if v["language_code"] == "fr-FR")
        assert fr["completed_stages"] == 2
        assert fr["total_stages"] == 8
        assert fr["progress_percent"] == 25.0
        assert "derived from" in fr["progress_source"]

    async def test_the_three_media_stages_collapse_to_one(
        self, client: AsyncClient, operator_token, db_session,
    ):
        # Checkpoints are written at WORKER granularity; the figure is over the
        # eight SPEC stages. Three complete media checkpoints are ONE complete
        # stage, not three - the same collapse the Pipeline Tracker applies.
        from app.models.checkpoint import PipelineCheckpoint
        from app.models.render_job import RenderJob

        project, _source, _target = await self._project_with_variants(
            db_session, operator_token,
        )
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="localisation",
            status="running", language_code="fr-FR",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.flush()
        for i, stage in enumerate(
            ["image_generation", "video_generation", "animation_generation"]
        ):
            db_session.add(PipelineCheckpoint(
                id=uuid.uuid4(), job_id=job.id, stage_name=stage,
                stage_index=i, status="complete",
                created_at=datetime.now(timezone.utc),
            ))
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/projects/{project.id}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        fr = next(v for v in resp.json() if v["language_code"] == "fr-FR")
        assert fr["completed_stages"] == 1

    async def test_an_incomplete_checkpoint_does_not_count(
        self, client: AsyncClient, operator_token, db_session,
    ):
        from app.models.checkpoint import PipelineCheckpoint
        from app.models.render_job import RenderJob

        project, _source, _target = await self._project_with_variants(
            db_session, operator_token,
        )
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="localisation",
            status="running", language_code="fr-FR",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.flush()
        db_session.add(PipelineCheckpoint(
            id=uuid.uuid4(), job_id=job.id, stage_name="audio_generation",
            stage_index=0, status="failed",
            created_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/projects/{project.id}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        fr = next(v for v in resp.json() if v["language_code"] == "fr-FR")
        # A run exists, and nothing has completed. 0 is a MEASUREMENT here, and
        # the distinction from the null above is the whole point.
        assert fr["progress_percent"] == 0.0
        assert fr["completed_stages"] == 0

    async def test_the_source_language_reads_the_projects_own_jobs(
        self, client: AsyncClient, operator_token, db_session,
    ):
        # Every job predating migration 0028 has language_code NULL and belongs
        # to the source language by definition.
        from app.models.checkpoint import PipelineCheckpoint
        from app.models.render_job import RenderJob

        project, _source, _target = await self._project_with_variants(
            db_session, operator_token,
        )
        job = RenderJob(
            id=uuid.uuid4(), project_id=project.id, job_type="final_render",
            status="success", language_code=None,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.flush()
        db_session.add(PipelineCheckpoint(
            id=uuid.uuid4(), job_id=job.id, stage_name="transcript_refinement",
            stage_index=0, status="complete",
            created_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/projects/{project.id}/languages",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        by_code = {v["language_code"]: v for v in resp.json()}
        assert by_code["en-US"]["completed_stages"] == 1
        # ...and it must not leak into the target-language variant.
        assert by_code["fr-FR"]["progress_percent"] is None


# ===========================================================================
# TASK 6(d) — the five scene fields
# ===========================================================================

@pytest.mark.asyncio
class TestTask6dSceneFields:

    async def test_all_five_fields_round_trip(
        self, client: AsyncClient, operator_token, scene_fixture,
    ):
        body = {
            "camera_angle": "close-up",
            "transition_type": "dissolve",
            "effects": ["ken_burns", "vignette"],
            "timing_offset_ms": -250,
            "generation_params": {"seed": 42, "steps": 30},
        }
        resp = await client.patch(
            f"/api/v1/projects/{scene_fixture['project_id']}"
            f"/scenes/{scene_fixture['id']}",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=body,
        )
        assert resp.status_code == 200, resp.text
        for key, value in body.items():
            assert resp.json()[key] == value, key

        # Read back independently: Pydantic accepting a key is not the same as
        # a column storing it, and that gap is the entire WP-43 D-2 defect.
        again = await client.get(
            f"/api/v1/projects/{scene_fixture['project_id']}/scenes",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        stored = next(
            s for s in again.json() if s["id"] == scene_fixture["id"]
        )
        assert stored["camera_angle"] == "close-up"
        assert stored["generation_params"] == {"seed": 42, "steps": 30}

    async def test_an_omitted_field_is_left_alone(
        self, client: AsyncClient, operator_token, scene_fixture,
    ):
        url = (
            f"/api/v1/projects/{scene_fixture['project_id']}"
            f"/scenes/{scene_fixture['id']}"
        )
        headers = {"Authorization": f"Bearer {operator_token}"}
        await client.patch(url, headers=headers, json={"camera_angle": "wide"})
        resp = await client.patch(
            url, headers=headers, json={"narration_text": "changed"},
        )
        assert resp.json()["camera_angle"] == "wide"

    async def test_an_explicit_null_clears_a_field(
        self, client: AsyncClient, operator_token, scene_fixture,
    ):
        # Under the old fixed signature "clear this" and "I did not mention it"
        # both arrived as None and neither could be told from the other.
        url = (
            f"/api/v1/projects/{scene_fixture['project_id']}"
            f"/scenes/{scene_fixture['id']}"
        )
        headers = {"Authorization": f"Bearer {operator_token}"}
        await client.patch(url, headers=headers, json={"camera_angle": "wide"})
        resp = await client.patch(url, headers=headers, json={"camera_angle": None})
        assert resp.json()["camera_angle"] is None

    async def test_the_bounds_are_enforced_with_a_message(
        self, client: AsyncClient, operator_token, scene_fixture,
    ):
        url = (
            f"/api/v1/projects/{scene_fixture['project_id']}"
            f"/scenes/{scene_fixture['id']}"
        )
        headers = {"Authorization": f"Bearer {operator_token}"}

        too_far = await client.patch(
            url, headers=headers, json={"timing_offset_ms": 120000},
        )
        assert too_far.status_code == 422

        too_many = await client.patch(
            url, headers=headers, json={"effects": [f"e{i}" for i in range(40)]},
        )
        assert too_many.status_code == 422
        assert "At most 32 effects" in too_many.text

        blank = await client.patch(
            url, headers=headers, json={"effects": ["ok", "   "]},
        )
        assert blank.status_code == 422
        assert "cannot be blank" in blank.text


# ===========================================================================
# TASK 6(e) — attestation evidence length
# ===========================================================================

class TestTask6eAttestationLength:
    """512 characters is not an attestation, it is a note."""

    def test_a_real_vetting_reference_now_fits(self):
        from app.schemas.model_store import ApproveIn

        # WP-46 §A8's reference is 1,912 characters and is a SHORT one: it names
        # the certification, the run, the result, the hardware profile, the
        # measured VRAM and generation time, the engine digest, the graph SHA,
        # the nine weight bundles and the report that verified them.
        reference = (
            "MBCP certification eb032794-e46e-4787-a399-b45a548c52e5 "
            "(Wan2.2-Animate, family wan_animate, engine comfyui), ingested "
            "into IVGS 2026-07-10 as attestation dc110421. " + "x" * 1800
        )
        assert len(reference) > 512
        approval = ApproveIn(
            attested_by="operator",
            vetting_reference=reference,
            checklist={"reviewed": True},
        )
        assert approval.vetting_reference == reference

    def test_a_blank_reference_is_refused_with_the_reason(self):
        import pydantic
        from app.schemas.model_store import ApproveIn

        with pytest.raises(pydantic.ValidationError) as exc:
            ApproveIn(
                attested_by="operator", vetting_reference="   ",
                checklist={"reviewed": True},
            )
        assert "not an attestation" in str(exc.value)

    def test_there_is_still_an_upper_bound(self):
        import pydantic
        from app.schemas.model_store import ApproveIn, MAX_VETTING_REFERENCE

        with pytest.raises(pydantic.ValidationError):
            ApproveIn(
                attested_by="operator",
                vetting_reference="x" * (MAX_VETTING_REFERENCE + 1),
                checklist={"reviewed": True},
            )


# ===========================================================================
# TASK 4 — the GPU fleet, read through
# ===========================================================================

FLEET = {
    "total_nodes": 3,
    "alive_nodes": 2,
    "draining_nodes": 1,
    "total_vram_mb": 293661,
    "used_vram_mb": 24576,
    "available_vram_mb": 269085,
    "fleet_utilization_pct": 8.4,
    "queue_depth": {"urgent": 0, "normal": 0, "batch": 0},
    "nodes": [
        {
            "node_id": "node-02:gpu0", "gpu_index": 0,
            "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "total_vram_mb": 97887, "used_vram_mb": 24576,
            "available_vram_mb": 73311, "gpu_utilization_pct": 42.0,
            "current_jobs": [], "last_heartbeat": "2026-08-25T13:00:00+00:00",
            "is_alive": True, "is_draining": False,
            "loaded_models": ["llama-3.3-70b"], "circuit_breaker_state": "closed",
        },
        {
            "node_id": "node-03:gpu0", "gpu_index": 0,
            "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "total_vram_mb": 97887, "used_vram_mb": 0,
            "available_vram_mb": 97887, "gpu_utilization_pct": 0.0,
            "current_jobs": [], "last_heartbeat": "2026-08-25T13:00:00+00:00",
            "is_alive": True, "is_draining": True,
            "loaded_models": [], "circuit_breaker_state": "closed",
        },
        {
            # A worker started without IVGS_NODE_NAME: the container's own hex
            # hostname. One of these per container ever run - 21 of them on the
            # real fleet, on three GPUs.
            "node_id": "61c7c02b3a8a:gpu0", "gpu_index": 0,
            "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "total_vram_mb": 97887, "used_vram_mb": 0,
            "available_vram_mb": 97887, "gpu_utilization_pct": 0.0,
            "current_jobs": [], "last_heartbeat": "2026-08-23T17:41:32+00:00",
            "is_alive": False, "is_draining": False,
            "loaded_models": [], "circuit_breaker_state": "closed",
        },
    ],
}


@pytest.mark.asyncio
class TestTask4GpuReadThrough:

    async def test_the_fleet_comes_from_the_scheduler_not_the_empty_table(
        self, client: AsyncClient, operator_token,
    ):
        # gpu_nodes has always had zero rows: workers register with the
        # SCHEDULER and nothing in ivgs-workers has ever called
        # POST /api/v1/gpu/nodes. "GPU Nodes Online" read 0/0 while three GPUs
        # were alive and working.
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=FLEET)
        ):
            resp = await client.get(
                "/api/v1/gpu/nodes",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    async def test_utilization_reports_real_vram(
        self, client: AsyncClient, operator_token,
    ):
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=FLEET)
        ):
            resp = await client.get(
                "/api/v1/gpu/utilization",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        body = resp.json()
        assert body["total_nodes"] == 3
        assert body["total_vram_mb"] == 97887 * 3
        assert body["online_nodes"] == 1     # node-02
        assert body["draining_nodes"] == 1   # node-03
        assert body["offline_nodes"] == 1    # the hex one

    async def test_a_container_hex_node_is_labelled_not_hidden(
        self, client: AsyncClient, operator_token,
    ):
        # Whether the IVGS_NODE_NAME fix has reached a given node is exactly the
        # thing an operator needs to see. Prettifying it would conceal that.
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=FLEET)
        ):
            resp = await client.get(
                "/api/v1/gpu/nodes",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        names = [n["node_hostname"] for n in resp.json()["data"]]
        assert "node-02" in names
        assert any(n.startswith("unnamed (") for n in names)

    async def test_node_ids_are_stable_across_calls(
        self, client: AsyncClient, operator_token,
    ):
        # GpuNodeResponse.id is a UUID and the scheduler's id is a string. The
        # UUID5 derivation must be stable or /gpu/nodes/{id} could never resolve.
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=FLEET)
        ):
            first = await client.get(
                "/api/v1/gpu/nodes",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            second = await client.get(
                "/api/v1/gpu/nodes",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert [n["id"] for n in first.json()["data"]] == (
            [n["id"] for n in second.json()["data"]]
        )

    async def test_one_node_can_be_fetched_by_its_derived_id(
        self, client: AsyncClient, operator_token,
    ):
        with patch(
            "app.services.gpu_service.fetch_fleet", AsyncMock(return_value=FLEET)
        ):
            listing = await client.get(
                "/api/v1/gpu/nodes",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            node_id = listing.json()["data"][0]["id"]
            resp = await client.get(
                f"/api/v1/gpu/nodes/{node_id}",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == node_id

    async def test_an_unreachable_scheduler_is_a_503_not_an_empty_fleet(
        self, client: AsyncClient, operator_token,
    ):
        # THE POINT. "no nodes" and "I could not ask" render identically on a
        # tile, and that conflation is what made the old 0/0 look trustworthy.
        from app.services.scheduler_fleet import SchedulerUnavailable

        with patch(
            "app.services.gpu_service.fetch_fleet",
            AsyncMock(side_effect=SchedulerUnavailable("connection refused")),
        ):
            for path in ("/api/v1/gpu/nodes", "/api/v1/gpu/utilization"):
                resp = await client.get(
                    path, headers={"Authorization": f"Bearer {operator_token}"},
                )
                assert resp.status_code == 503, path
                assert "connection refused" in resp.text


class TestTask4NodeNameMapping:
    """The pure mapping, without a fleet or a database."""

    def test_a_node_name_is_kept_as_is(self):
        from app.services.scheduler_fleet import node_display_name

        assert node_display_name("node-04") == "node-04"

    def test_a_hex_hostname_is_labelled(self):
        from app.services.scheduler_fleet import node_display_name

        assert node_display_name("61c7c02b3a8a").startswith("unnamed (")

    def test_the_scheduler_id_splits_into_host_and_index(self):
        from app.services.scheduler_fleet import split_node_id

        assert split_node_id("node-04:gpu1") == ("node-04", 1)
        assert split_node_id("node-04") == ("node-04", 0)
        assert split_node_id("weird::shape") == ("weird", 0)

    def test_the_derived_uuid_is_deterministic_and_distinct_per_node(self):
        from app.services.scheduler_fleet import node_uuid

        assert node_uuid("node-02:gpu0") == node_uuid("node-02:gpu0")
        assert node_uuid("node-02:gpu0") != node_uuid("node-02:gpu1")
        assert node_uuid("node-02:gpu0") != node_uuid("node-03:gpu0")

    def test_draining_wins_over_alive(self):
        from app.services.scheduler_fleet import node_status

        # A draining node is still heartbeating; what the operator needs to know
        # is that it is not taking new work.
        assert node_status({"is_alive": True, "is_draining": True}) == "draining"
        assert node_status({"is_alive": True, "is_draining": False}) == "online"
        assert node_status({"is_alive": False, "is_draining": False}) == "offline"
