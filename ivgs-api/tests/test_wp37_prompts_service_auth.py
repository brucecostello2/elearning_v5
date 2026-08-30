"""
WP-37 Task 2 — the prompts route rejects the worker. Same defect class as WP-36.

`GET /api/v1/projects/{id}/prompts?prompt_type=...` was guarded by
`get_current_user`, which rejects the internal service token with 401. Stage 1
(`stage1_transcript.py:275`) and stage 2 (`stage2_storyboard.py:161`) both read
their prompts from it with that token, so every attempt got 401 and the worker
fell back to the baked-in `.j2` templates.

**Nothing looked broken.** The pipeline ran; it simply ignored the DB-managed
prompt feature entirely. Observed on every stage-2 attempt of job e408515a.

The WP-36 lesson applied: test as the REAL caller, not only as a human token.
These mirror `test_wp36_checkpoint_service_auth.py`.
"""
import secrets
import uuid

import pytest
from httpx import AsyncClient

from shared.config import settings

# Exactly what the worker sends.
SERVICE_HEADERS = {"Authorization": f"Bearer {settings.IVGS_SERVICE_TOKEN}"}


@pytest.fixture
async def svc_pipeline_account(db_session):
    """Seed the account the service token resolves to, the way the real seed
    script does (app/scripts/seed_service_account.py)."""
    from sqlalchemy import select

    from app.models.user import User
    from app.services.user_service import create_user

    existing = (
        await db_session.execute(select(User).where(User.username == "svc-pipeline"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user = await create_user(
        db_session,
        username="svc-pipeline",
        password=secrets.token_urlsafe(48),
        role="admin",
    )
    # create_user only flushes; get_service_or_user resolves the token against
    # this row, so it has to be committed.
    await db_session.commit()
    return user


@pytest.mark.asyncio
class TestWorkerCanReadPrompts:
    async def test_service_token_is_not_401(
        self, client: AsyncClient, svc_pipeline_account, project_id: str
    ):
        """THE BUG. Pre-fix this returned 401 and the worker silently fell back
        to its baked-in templates."""
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            headers=SERVICE_HEADERS,
        )
        assert r.status_code != 401, (
            f"the worker's service token was rejected by the prompts route it "
            f"reads from; body={r.text[:200]}"
        )
        assert r.status_code == 200, r.text

    async def test_the_prompt_type_filter_works_over_service_auth(
        self, client: AsyncClient, svc_pipeline_account, project_id: str
    ):
        """The worker always sends ?prompt_type=. IVGS-0.4 made the endpoint
        honour it; this pins that it still does for the service caller."""
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            params={"prompt_type": "storyboard_generation"},
            headers=SERVICE_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body["data"] if isinstance(body, dict) and "data" in body else body
        for row in rows:
            assert row["prompt_type"] == "storyboard_generation", row

    async def test_auth_resolves_before_the_project_is_looked_up(
        self, client: AsyncClient, svc_pipeline_account
    ):
        """The WP-36 diagnostic: with a nonexistent project, a route that
        accepts the credential answers 404 (or 200-with-nothing), never 401."""
        r = await client.get(
            f"/api/v1/projects/{uuid.uuid4()}/prompts", headers=SERVICE_HEADERS
        )
        assert r.status_code != 401, r.text


@pytest.mark.asyncio
class TestHumanAccessUnchanged:
    async def test_operator_still_reads(
        self, client: AsyncClient, operator_token: str, project_id: str
    ):
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200, r.text

    async def test_viewer_is_denied_403(
        self, client: AsyncClient, viewer_token: str, project_id: str
    ):
        """The route was readable by viewers under get_current_user. It is now
        operator-or-above; that is a deliberate narrowing for humans, recorded
        in the WP-37 report."""
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403, r.text

    async def test_unauthenticated_denied(self, client: AsyncClient, project_id: str):
        r = await client.get(f"/api/v1/projects/{project_id}/prompts")
        assert r.status_code in (401, 403), r.text

    async def test_a_wrong_service_token_is_denied(
        self, client: AsyncClient, svc_pipeline_account, project_id: str
    ):
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            headers={"Authorization": "Bearer not-the-service-token"},
        )
        assert r.status_code in (401, 403), r.text


@pytest.mark.asyncio
class TestWriteRoutesNotWidened:
    """Only the READ routes the worker calls were changed. No worker writes prompts.

    ⚠ Plural since RC-Q15: WP-37 widened the project-scoped list, and
    WP-IVGS-12's `_fetch_active_prompt` added a second reader on the GLOBAL list
    without widening it. See the re-aimed test below.
    """

    async def test_create_project_prompt_refuses_the_service_token(
        self, client: AsyncClient, svc_pipeline_account, project_id: str
    ):
        r = await client.post(
            f"/api/v1/projects/{project_id}/prompts",
            json={"prompt_type": "storyboard_generation", "prompt_text": "x"},
            headers=SERVICE_HEADERS,
        )
        assert r.status_code == 401, (
            f"prompt writes must stay human-only, got {r.status_code}"
        )

    async def test_create_global_prompt_refuses_the_service_token(
        self, client: AsyncClient, svc_pipeline_account
    ):
        r = await client.post(
            "/api/v1/prompts",
            json={"prompt_type": "storyboard_generation", "prompt_text": "x",
                  "change_note": "probe"},
            headers=SERVICE_HEADERS,
        )
        assert r.status_code == 401, r.text

    async def test_global_prompt_list_now_answers_the_service_token(
        self, client: AsyncClient, svc_pipeline_account
    ):
        """⛔ RE-AIMED BY RC-Q15, AND IT IS THE PREMISE THAT CHANGED, NOT THE CLAIM.

        This asserted **401**, and its reason was stated in one line: *"GET
        /prompts is the human library view; **no worker reads it**, so it was
        deliberately left on get_current_user."* That was true and correct on
        **2026-08-23** (`43190ac`).

        ⛳ **WP-IVGS-12 MADE IT FALSE ON 2026-08-29** (`cead433`) by adding
        `pipeline_orchestrator_v2._fetch_active_prompt`, which reads exactly this
        route with a service token to resolve the versioned SYSTEM prompt for
        stages 1 and 2 — and did not widen it. So the route answered 401, the
        fetch returned `""` on any non-200, and **every stage silently fell back
        to the `.j2` baked into its image. No published system prompt has ever
        reached a real pipeline run.**

        MEASURED live, 2026-08-30, before the fix — all three lineages resolved
        to 0 chars while their rows were active in the database. It surfaced as
        RC-Q15: stage 1 never received the extraction prompt and ran the old
        refine-for-readability text instead, paraphrasing a 3,138-byte script to
        1,647 bytes, which the whole Design Core then designed against.

        ⛳ WP-37's ACTUAL CLAIM IS UNCHANGED AND IS STILL TESTED ABOVE: **writes
        stay human-only.** Only the read this class's own docstring describes —
        *"the read route the worker calls"* — is widened, and now there are two
        of them because WP-IVGS-12 added one.
        """
        r = await client.get("/api/v1/prompts", headers=SERVICE_HEADERS)
        assert r.status_code == 200, r.text
