"""
WP-38 Task 3 — the storyboard must move the project to its review state.

Project c12fa967 completed stage 1 and stage 2 on 2026-08-23 — 18 scenes
persisted, job success — and still read `TRANSCRIPT_REFINEMENT`. Nothing
advanced `projects.state` on stage completion: the only writers were
`trigger_pipeline` (DRAFT -> TRANSCRIPT_REFINEMENT) and `approve_storyboard`
(-> MEDIA_GENERATION), and `transition_state` had no callers at all (ORCH-5).

So the review gate had no state to show, and the GUI could not reflect it.

The fix advances TRANSCRIPT_REFINEMENT -> STORYBOARD_GENERATION when a scene is
persisted, which is the moment the storyboard demonstrably exists. It is
deliberately narrow, and idempotent: 18 scenes produce one transition.
"""
import uuid

import pytest
from httpx import AsyncClient

from shared.config import settings

SERVICE_HEADERS = {"Authorization": f"Bearer {settings.IVGS_SERVICE_TOKEN}"}


def _scene(idx: int) -> dict:
    """WP-IVGS-10: a v7-valid scene. THE FIXTURE CHANGED, NOT THE ASSERTIONS.

    This file is about `projects.state` advancing when a scene is persisted.
    But `narration {idx}` contains a NUMERAL, and v7's RULE 1-EXTENDED refuses
    a diffusion scene whose narration states numeric content while the row
    declares nothing about where that content lives. The refusal is correct;
    the fixture was a storyboard v7 will not release, so it now carries the
    declaration a real scene like this would.
    """
    return {
        "scene_index": idx,
        "narration_text": f"narration {idx}",
        # ⚠ NO NUMERAL IN THIS PROSE -- see the note in test_wp62_gates.py.
        "visual_description": (
            "a working surface with a partial-product row already written "
            "above a ruled horizontal line, the answer row still empty"
        ),
        "media_type": "image",
        "duration_seconds": 10.0,
        "text_carried_by": "narration",
        "media_rationale": "image with text_carried_by narration: the number is spoken.",
    }


@pytest.fixture
async def svc_pipeline_account(db_session):
    import secrets

    from sqlalchemy import select

    from app.models.user import User
    from app.services.user_service import create_user

    existing = (
        await db_session.execute(select(User).where(User.username == "svc-pipeline"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user = await create_user(
        db_session, username="svc-pipeline",
        password=secrets.token_urlsafe(48), role="admin",
    )
    await db_session.commit()
    return user


async def _state_of(client, token, project_id) -> str:
    """Read the state back THROUGH THE API - the way the GUI sees it.

    Deliberately not a direct db_session read: the route commits on its own
    connection, and re-reading through the test session collides with the app's
    event loop (asyncpg futures are loop-bound). Going through the API also
    tests the thing that matters, which is what a client observes.
    """
    r = await client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["state"]


@pytest.fixture
async def refining_project(db_session, operator_token):
    """A project mid-run, exactly as stage 2 finds it."""
    from datetime import datetime, timezone

    from app.core.security import decode_token
    from app.models.project import Project

    owner = uuid.UUID(decode_token(operator_token)["sub"])
    p = Project(
        id=uuid.uuid4(), name="WP-38 state", state="TRANSCRIPT_REFINEMENT",
        created_by=owner, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(p)
    await db_session.flush()

    # approve_storyboard also requires a render job to resume - without one it
    # 409s on "no render job found", which would have made the continuation test
    # pass for the wrong reason.
    from app.models.render_job import RenderJob

    db_session.add(
        RenderJob(
            id=uuid.uuid4(), project_id=p.id, status="running",
            job_type="storyboard_generation",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
class TestStoryboardAdvancesTheProject:
    async def test_first_scene_advances_to_storyboard_generation(
        self, client: AsyncClient, svc_pipeline_account, refining_project,
        operator_token: str,
    ):
        """THE BUG. Pre-fix the project stayed in TRANSCRIPT_REFINEMENT forever."""
        assert refining_project.state == "TRANSCRIPT_REFINEMENT"
        r = await client.post(
            f"/api/v1/projects/{refining_project.id}/scenes",
            json=_scene(0), headers=SERVICE_HEADERS,
        )
        assert r.status_code == 201, r.text
        assert await _state_of(client, operator_token, refining_project.id) == "STORYBOARD_GENERATION"

    async def test_eighteen_scenes_produce_one_transition(
        self, client: AsyncClient, svc_pipeline_account, refining_project,
        operator_token: str,
    ):
        """The real run posts 18. The advance must be idempotent, not 18 writes
        fighting each other."""
        for i in range(18):
            r = await client.post(
                f"/api/v1/projects/{refining_project.id}/scenes",
                json=_scene(i), headers=SERVICE_HEADERS,
            )
            assert r.status_code == 201, f"scene {i}: {r.text[:150]}"
        assert await _state_of(client, operator_token, refining_project.id) == "STORYBOARD_GENERATION"

    async def test_scenes_are_all_persisted(
        self, client: AsyncClient, svc_pipeline_account, refining_project, operator_token
    ):
        """The state change must not cost us the scenes."""
        for i in range(3):
            await client.post(
                f"/api/v1/projects/{refining_project.id}/scenes",
                json=_scene(i), headers=SERVICE_HEADERS,
            )
        listed = await client.get(
            f"/api/v1/projects/{refining_project.id}/scenes",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert listed.status_code == 200
        body = listed.json()
        assert isinstance(body, list), "the route returns a BARE ARRAY - WP-38 Task 1"
        assert len(body) == 3


@pytest.mark.asyncio
class TestTheAdvanceIsNarrow:
    @pytest.mark.parametrize("state", ["DRAFT", "MEDIA_GENERATION", "COMPLETE"])
    async def test_other_states_are_untouched(
        self, client: AsyncClient, svc_pipeline_account, db_session,
        operator_token, state,
    ):
        """Only the TRANSCRIPT_REFINEMENT edge fires. A re-run from a later state
        must not be dragged backwards."""
        import uuid as _u
        from datetime import datetime, timezone

        from app.core.security import decode_token
        from app.models.project import Project

        owner = _u.UUID(decode_token(operator_token)["sub"])
        p = Project(
            id=_u.uuid4(), name=f"WP-38 {state}", state=state, created_by=owner,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        db_session.add(p)
        await db_session.commit()

        r = await client.post(
            f"/api/v1/projects/{p.id}/scenes", json=_scene(0), headers=SERVICE_HEADERS,
        )
        assert r.status_code == 201, r.text
        assert await _state_of(client, operator_token, p.id) == state, (
            f"state {state} must not be changed by a scene write"
        )


@pytest.mark.asyncio
class TestContinuationIsLegalFromTheReviewState:
    async def test_approve_accepts_storyboard_generation(
        self, client: AsyncClient, svc_pipeline_account, operator_token,
        refining_project,
    ):
        """The point of the whole change: after the advance, the operator's
        continuation call is legal without hand-written SQL.

        Spec Table 4-3 sanctions STORYBOARD_GENERATION -> MEDIA_GENERATION.
        """
        for i in range(2):
            await client.post(
                f"/api/v1/projects/{refining_project.id}/scenes",
                json=_scene(i), headers=SERVICE_HEADERS,
            )
        assert await _state_of(client, operator_token, refining_project.id) == "STORYBOARD_GENERATION"

        r = await client.post(
            f"/api/v1/projects/{refining_project.id}/scenes/approve",
            params={"tier": "prototype"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # 404 only if no render job exists for the project; the state guard must
        # NOT be what rejects it.
        assert r.status_code != 409, (
            f"approve must be legal from STORYBOARD_GENERATION; got 409 {r.text[:200]}"
        )
