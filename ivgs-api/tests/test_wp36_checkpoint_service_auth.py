"""
WP-36 — the checkpoint write path must accept the caller that actually uses it.

`POST /api/v1/jobs/{job_id}/checkpoints` was added by WP-07 behind
`require_operator_or_admin`, which resolves through `get_current_user` and so
rejects the internal service token outright with **401**, before any role is
examined. The only caller in production is the worker fleet, which holds no human
JWT — so every checkpoint the pipeline tried to write was refused.

Measured 2026-08-23 from inside `ivgs-celery-node02`, with the worker's own
credential, same client and same host:

    PATCH /api/v1/jobs/<bogus>              -> 404   (auth accepted, job absent)
    POST  /api/v1/jobs/<bogus>/checkpoints  -> 401   AUTHENTICATION_REQUIRED

**Why the existing 19 WP-07 tests missed it: every one of them authenticates as
`operator_token`, a human JWT.** The route was never exercised as the caller that
actually uses it. These tests send the shape the worker really sends —
`Authorization: Bearer <IVGS_SERVICE_TOKEN>` against a seeded `svc-pipeline`
account — which is the gap, not the guard, that let this ship.
"""
import uuid

import pytest
from httpx import AsyncClient

from shared.config import settings

# Exactly what ivgs-workers/utils/error_handler.py:save_checkpoint sends.
SERVICE_HEADERS = {
    "Authorization": f"Bearer {settings.IVGS_SERVICE_TOKEN}",
    "Content-Type": "application/json",
}
BOGUS_JOB = "00000000-0000-0000-0000-000000000000"


def _worker_payload(**over):
    """The body save_checkpoint posts."""
    body = {
        "stage_name": "transcript_refinement",
        "stage_index": 1,
        "status": "running",
        "checkpoint_data": {"started_at": "2026-08-23T14:49:48Z"},
    }
    body.update(over)
    return body


@pytest.fixture
async def svc_pipeline_account(db_session):
    """Seed the service account the token resolves to.

    Mirrors app/scripts/seed_service_account.py: auth is by the shared
    IVGS_SERVICE_TOKEN, and the account's own password is never used.
    """
    import secrets

    from sqlalchemy import select

    from app.models.user import User
    from app.services.user_service import create_user

    existing = (
        await db_session.execute(select(User).where(User.username == "svc-pipeline"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # Created exactly the way app/scripts/seed_service_account.py does it, so the
    # fixture cannot drift from how the account really exists in production. The
    # password is a throwaway: authentication is by IVGS_SERVICE_TOKEN, never by
    # this account's own credentials.
    user = await create_user(
        db_session,
        username="svc-pipeline",
        password=secrets.token_urlsafe(48),
        role="admin",
    )
    # create_user only flushes (user_service.py:47). get_service_or_user resolves
    # the token against this row, so it has to be committed or the lookup misses
    # it and the request falls through to the JWT path and 401s.
    await db_session.commit()
    return user


@pytest.mark.asyncio
class TestServiceTokenIsAccepted:
    """The regression this package exists for."""

    async def test_worker_service_token_is_not_401(
        self, client: AsyncClient, svc_pipeline_account, empty_job: dict
    ):
        """THE BUG. Pre-fix this returned 401 AUTHENTICATION_REQUIRED."""
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            json=_worker_payload(),
            headers=SERVICE_HEADERS,
        )
        assert r.status_code != 401, (
            "the worker's service token was rejected by the only route it "
            f"writes to; body={r.text[:200]}"
        )
        assert r.status_code == 201, r.text

    async def test_the_checkpoint_row_is_actually_written(
        self, client: AsyncClient, svc_pipeline_account, empty_job: dict,
        operator_token: str,
    ):
        """201 is not enough - WP-07's whole point is a row landing."""
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            json=_worker_payload(stage_name="storyboard_generation", stage_index=2),
            headers=SERVICE_HEADERS,
        )
        assert r.status_code == 201, r.text
        # Read back as a HUMAN: the GET routes still use get_current_user and were
        # deliberately NOT widened, since no worker reads checkpoints.
        listed = await client.get(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert listed.status_code == 200, listed.text
        # CheckpointListResponse: {job_id, total_stages, ..., checkpoints: [...]}
        body = listed.json()
        rows = body["checkpoints"]
        assert any(c["stage_name"] == "storyboard_generation" for c in rows), body

    @pytest.mark.parametrize(
        "worker_status", ["running", "success", "partial_success", "failed"]
    )
    async def test_every_status_the_worker_sends_is_accepted_over_service_auth(
        self, client: AsyncClient, svc_pipeline_account, empty_job: dict,
        worker_status: str,
    ):
        """WP-07 proved the status mapping under a human token. It has to hold
        for the caller that actually sends these."""
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            json=_worker_payload(status=worker_status, stage_name=f"s_{worker_status}"),
            headers=SERVICE_HEADERS,
        )
        assert r.status_code == 201, f"{worker_status}: {r.text[:200]}"

    async def test_auth_is_resolved_before_the_job_is_looked_up(
        self, client: AsyncClient, svc_pipeline_account
    ):
        """The diagnostic that isolated the bug in production.

        With a nonexistent job, a route that accepts the credential answers 404;
        one that rejects it answers 401. Pre-fix this was 401 - proof the refusal
        happened at the gate, not at the job lookup."""
        r = await client.post(
            f"/api/v1/jobs/{BOGUS_JOB}/checkpoints",
            json=_worker_payload(),
            headers=SERVICE_HEADERS,
        )
        assert r.status_code == 404, (
            f"expected 404 (auth accepted, job absent), got {r.status_code}"
        )


@pytest.mark.asyncio
class TestHumanAccessIsUnchanged:
    """Widening the gate must not have widened it too far."""

    async def test_operator_still_accepted(
        self, client: AsyncClient, operator_token: str, empty_job: dict
    ):
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            json=_worker_payload(stage_name="human_operator_write"),
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 201, r.text

    async def test_viewer_is_still_denied_403(
        self, client: AsyncClient, viewer_token: str, empty_job: dict
    ):
        """require_service_or_privileged_user still enforces the role for humans -
        a viewer must not be able to write checkpoints."""
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            json=_worker_payload(),
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403, r.text

    async def test_unauthenticated_is_still_denied(
        self, client: AsyncClient, empty_job: dict
    ):
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints", json=_worker_payload()
        )
        assert r.status_code in (401, 403), r.text

    async def test_a_wrong_service_token_is_still_denied(
        self, client: AsyncClient, svc_pipeline_account, empty_job: dict
    ):
        """The gate accepts THE token, not any token."""
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints",
            json=_worker_payload(),
            headers={"Authorization": "Bearer not-the-service-token"},
        )
        assert r.status_code in (401, 403), r.text


@pytest.mark.asyncio
class TestSiblingRoutesNotWidened:
    """Only the route the worker calls was changed."""

    async def test_resume_still_rejects_the_service_token(
        self, client: AsyncClient, svc_pipeline_account, empty_job: dict
    ):
        """POST /resume is human-initiated; no worker calls it. It keeps
        require_operator_or_admin, so the service token is refused."""
        r = await client.post(
            f"/api/v1/jobs/{empty_job['id']}/resume", headers=SERVICE_HEADERS
        )
        assert r.status_code == 401, (
            f"expected the service token to be refused on /resume, got {r.status_code}"
        )

    async def test_delete_still_rejects_the_service_token(
        self, client: AsyncClient, svc_pipeline_account, empty_job: dict
    ):
        r = await client.delete(
            f"/api/v1/jobs/{empty_job['id']}/checkpoints", headers=SERVICE_HEADERS
        )
        assert r.status_code == 401, (
            f"expected the service token to be refused on DELETE, got {r.status_code}"
        )
