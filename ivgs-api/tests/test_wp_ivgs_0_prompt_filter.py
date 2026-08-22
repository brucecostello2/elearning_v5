"""
WP-IVGS-0.4 — GET /projects/{id}/prompts must honour ?prompt_type=.

The workers have always sent the parameter; the endpoint has always ignored it
and returned all ten types. The worker then picked by substring and the LAST
enum member, TRANSLATION, won — so Stage 1 rendered the translation template
with none of its variables bound and the transcript vanished.
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from shared.models.enums import PromptType

pytestmark = pytest.mark.asyncio

ALL_TEN = [pt.value for pt in PromptType]


@pytest.fixture
async def all_ten_seeded(db_session):
    """Seed one active GLOBAL prompt for every one of the ten types."""
    from app.models.prompt import Prompt

    for pt in ALL_TEN:
        db_session.add(
            Prompt(
                id=uuid.uuid4(),
                project_id=None,
                scene_id=None,
                prompt_type=pt,
                prompt_text=f"TEXT FOR {pt}",
                version=1,
                is_active=True,
                created_by="test",
                created_at=datetime.now(timezone.utc),
            )
        )
    await db_session.commit()
    return ALL_TEN


class TestPromptTypeFilter:
    async def test_unfiltered_still_returns_all_ten(
        self, client: AsyncClient, operator_token: str, project_id: str, all_ten_seeded
    ):
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        assert {p["prompt_type"] for p in r.json()} == set(ALL_TEN)

    async def test_filter_returns_only_the_requested_type(
        self, client: AsyncClient, operator_token: str, project_id: str, all_ten_seeded
    ):
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            params={"prompt_type": "transcript_refinement"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["prompt_type"] == "transcript_refinement"
        assert body[0]["prompt_text"] == "TEXT FOR transcript_refinement"

    async def test_translation_is_no_longer_what_stage1_receives(
        self, client: AsyncClient, operator_token: str, project_id: str, all_ten_seeded
    ):
        """The exact regression: translation is last in the enum."""
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            params={"prompt_type": "transcript_refinement"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert "translation" not in {p["prompt_type"] for p in r.json()}

    @pytest.mark.parametrize("pt", ALL_TEN)
    async def test_every_type_is_individually_addressable(
        self, client: AsyncClient, operator_token: str, project_id: str,
        all_ten_seeded, pt,
    ):
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            params={"prompt_type": pt},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 200
        assert [p["prompt_type"] for p in r.json()] == [pt]

    async def test_an_unknown_type_is_a_400_not_an_empty_list(
        self, client: AsyncClient, operator_token: str, project_id: str, all_ten_seeded
    ):
        """An empty list would read as 'not configured'. It is a bad request."""
        r = await client.get(
            f"/api/v1/projects/{project_id}/prompts",
            params={"prompt_type": "not_a_real_type"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "VALIDATION_ERROR"
