"""
WP-IVGS-0 finding F9 — the project detail fetcher unwrapped a wrapper that is
not there.

`projectFetcher` in ivgs-frontend/src/hooks/useProjects.ts returned
`response.data.data` for GET /api/v1/projects/{id}. That route has
response_model=ProjectResponse and returns the project FLAT, so the project
detail page received `undefined` — on the very page the New Project form
navigates to after a successful create (IVGS-0.5).

The list route is different and genuinely does wrap. These tests pin both
shapes server-side and cross-check the client against them, so the two fetchers
cannot be "made consistent" in the wrong direction later.
"""

import re
from pathlib import Path

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_USE_PROJECTS = (
    Path(__file__).resolve().parents[2]
    / "ivgs-frontend" / "src" / "hooks" / "useProjects.ts"
)


def _fetcher_body(name: str) -> str:
    """The fetcher's CODE, with comments stripped.

    Comments are prose and must not satisfy or trip a code assertion — the
    comment on projectFetcher legitimately names the old expression it replaced.
    """
    src = _USE_PROJECTS.read_text(encoding="utf-8")
    m = re.search(
        rf"const {name} = async \(url: string\).*?\n\}};", src, re.S
    )
    assert m, f"{name} not found in useProjects.ts"
    lines = [
        ln for ln in m.group(0).splitlines()
        if not ln.lstrip().startswith("//")
    ]
    return "\n".join(lines)


class TestServerResponseShapes:
    async def test_single_project_is_returned_flat(
        self, client: AsyncClient, operator_token: str
    ):
        auth = {"Authorization": f"Bearer {operator_token}"}
        created = await client.post(
            "/api/v1/projects", json={"name": "F9 Flat"}, headers=auth
        )
        assert created.status_code == 201
        pid = created.json()["id"]

        r = await client.get(f"/api/v1/projects/{pid}", headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == pid
        assert body["name"] == "F9 Flat"
        assert "data" not in body, (
            "the single-project route is flat; if this ever changes, "
            "projectFetcher must change with it"
        )

    async def test_the_list_route_really_does_wrap(
        self, client: AsyncClient, operator_token: str
    ):
        """The asymmetry is real, not an oversight. Pin it."""
        auth = {"Authorization": f"Bearer {operator_token}"}
        await client.post(
            "/api/v1/projects", json={"name": "F9 Listed"}, headers=auth
        )
        r = await client.get("/api/v1/projects", headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["data"], list)
        assert "total" in body and "page" in body


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestClientMatchesTheServer:
    pytestmark = []  # sync tests: opt out of the module-level asyncio mark

    def test_project_fetcher_does_not_double_unwrap(self):
        body = _fetcher_body("projectFetcher")
        assert "response.data.data" not in body, (
            "projectFetcher double-unwraps: GET /api/v1/projects/{id} returns "
            "the project flat, so response.data.data is undefined"
        )
        assert "return response.data;" in body

    def test_projects_fetcher_still_unwraps(self):
        """The list route wraps. This one must keep unwrapping."""
        body = _fetcher_body("projectsFetcher")
        assert "response.data.data" in body, (
            "projectsFetcher must keep unwrapping — the list route returns "
            "PaginatedResponse. Do not make it match projectFetcher."
        )
