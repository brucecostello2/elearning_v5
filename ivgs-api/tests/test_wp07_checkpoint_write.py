"""
WP-07-CHECKPOINTS - the checkpoint write path (ledger P1.2)

`POST /api/v1/jobs/{job_id}/checkpoints` did not exist. The workers'
`save_checkpoint` (ivgs-workers/utils/error_handler.py:427) has POSTed to it since
the pipeline was built and received 405 Method Not Allowed every time - measured
2026-08-23 against the running ivgs-fastapi (v5.5.3-arch1), with
`pipeline_checkpoints` holding 0 rows. The helper logged a warning and returned
False; none of its 15 call sites checked.

These tests run against a real Postgres with the full migration chain applied
(TEST_DATABASE_URL must name a database ending in `_test`; conftest refuses
otherwise). The status mapping and the enum constraint cannot be proven against
SQLite or a mock - `checkpoint_status` is a Postgres ENUM.
"""
import uuid

import pytest
from httpx import AsyncClient

# What the 15 worker call sites actually send. Only "failed" is a valid
# checkpoint_status label; the rest must be mapped or they fail on the enum.
WORKER_SENT_STATUSES = ["running", "success", "partial_success", "failed"]
EXPECTED_MAPPED = ["pending", "complete", "complete", "failed"]


def _payload(**over):
    body = {
        "stage_name": "transcript_refinement",
        "stage_index": 1,
        "status": "running",
        "checkpoint_data": {"started_at": "2026-08-23T00:00:00Z"},
    }
    body.update(over)
    return body


@pytest.mark.asyncio
class TestRouteExists:
    async def test_post_is_no_longer_405(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        """The whole defect, in one assertion."""
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=_payload(),
        )
        assert response.status_code != 405, "POST /checkpoints is still not routed"
        assert response.status_code == 201, response.text

    async def test_a_row_is_actually_written(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        """Not 'the endpoint returned 201' - the row is read back."""
        job_id = empty_job["id"]
        await client.post(
            f"/api/v1/jobs/{job_id}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=_payload(stage_name="storyboard_generation", stage_index=2,
                          status="success"),
        )
        got = await client.get(
            f"/api/v1/jobs/{job_id}/checkpoints/storyboard_generation",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert got.status_code == 200, got.text
        data = got.json()
        assert data["stage_name"] == "storyboard_generation"
        assert data["stage_index"] == 2
        assert data["status"] == "complete"
        assert data["completed_at"] is not None

    async def test_404_for_an_unknown_job(
        self, client: AsyncClient, operator_token: str
    ):
        response = await client.post(
            f"/api/v1/jobs/{uuid.uuid4()}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=_payload(),
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestStatusVocabulary:
    """The workers and the Postgres enum did not share a single value but 'failed'."""

    @pytest.mark.parametrize(
        "sent,expected", list(zip(WORKER_SENT_STATUSES, EXPECTED_MAPPED))
    )
    async def test_every_status_a_worker_sends_is_accepted(
        self, client: AsyncClient, operator_token: str, empty_job: dict,
        sent: str, expected: str,
    ):
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=_payload(stage_name=f"stage_for_{sent}", status=sent),
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == expected

    @pytest.mark.parametrize("label", ["pending", "complete", "failed", "skipped"])
    async def test_the_enums_own_labels_pass_through(
        self, client: AsyncClient, operator_token: str, empty_job: dict, label: str
    ):
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=_payload(stage_name=f"stage_{label}", status=label),
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == label

    async def test_an_unknown_status_is_rejected_not_coerced(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        """A typo must 422, not silently become 'pending'."""
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=_payload(status="compleat"),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestUpsertSemantics:
    """Every stage writes twice: 'running' at entry, its outcome at exit."""

    async def test_second_write_updates_rather_than_duplicates(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        job_id = empty_job["id"]
        h = {"Authorization": f"Bearer {operator_token}"}

        await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                          json=_payload(status="running"))
        await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                          json=_payload(status="success",
                                        checkpoint_data={"transcripts": 6}))

        listing = await client.get(f"/api/v1/jobs/{job_id}/checkpoints", headers=h)
        data = listing.json()
        rows = [c for c in data["checkpoints"]
                if c["stage_name"] == "transcript_refinement"]
        assert len(rows) == 1, "two writes for one stage must not leave two rows"
        assert rows[0]["status"] == "complete"

    async def test_started_at_survives_the_second_write(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        """started_at + completed_at is the per-stage duration the exit gate needs."""
        job_id = empty_job["id"]
        h = {"Authorization": f"Bearer {operator_token}"}

        first = await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                                  json=_payload(status="running"))
        started = first.json()["started_at"]
        assert first.json()["completed_at"] is None, "a running stage is not complete"

        second = await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                                   json=_payload(status="success"))
        assert second.json()["started_at"] == started
        assert second.json()["completed_at"] is not None

    async def test_checkpoint_data_is_replaced_not_merged(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        job_id = empty_job["id"]
        h = {"Authorization": f"Bearer {operator_token}"}
        await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                          json=_payload(checkpoint_data={"a": 1}))
        r = await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                              json=_payload(status="success",
                                            checkpoint_data={"b": 2}))
        assert r.json()["checkpoint_data"] == {"b": 2}

    async def test_distinct_stages_get_distinct_rows(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        job_id = empty_job["id"]
        h = {"Authorization": f"Bearer {operator_token}"}
        for idx, name in enumerate(
            ["transcript_refinement", "storyboard_generation", "image_generation"], 1
        ):
            await client.post(f"/api/v1/jobs/{job_id}/checkpoints", headers=h,
                              json=_payload(stage_name=name, stage_index=idx,
                                            status="success"))
        listing = await client.get(f"/api/v1/jobs/{job_id}/checkpoints", headers=h)
        data = listing.json()
        assert data["total_stages"] == 3
        assert data["completed_stages"] == 3
        assert data["last_successful_stage"] == "image_generation"


@pytest.mark.asyncio
class TestRbac:
    async def test_unauthenticated_is_rejected(
        self, client: AsyncClient, empty_job: dict
    ):
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints", json=_payload()
        )
        assert response.status_code in (401, 403)

    async def test_viewer_cannot_write(
        self, client: AsyncClient, viewer_token: str, empty_job: dict
    ):
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json=_payload(),
        )
        assert response.status_code == 403

    async def test_admin_can_write(
        self, client: AsyncClient, admin_token: str, empty_job: dict
    ):
        response = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=_payload(),
        )
        assert response.status_code == 201, response.text
