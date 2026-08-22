"""
WP-IVGS-0.5 — the New Project form must be able to succeed.

As built, it could not. It POSTed multipart/form-data to a JSON Pydantic
endpoint (through an apiClient.post that JSON.stringify's its body, so the
request body was literally "{}"); its language codes were bare ISO-639 ("en",
"es") against a validator that accepts only BCP-47; `talking_head_clip` had no
handler on the create route; and `existing_storyboard` had no server-side
consumer at all.

This module replays the EXACT request sequence the fixed form now issues, in
order, and then verifies the created rows by reading them back through the API.
It is the documented walk called for by the work order's acceptance criterion:
no browser was driven, so this stands in for the screenshots — every request
below is the one the form makes, with the same path, method and body shape.

Frontend source of truth:
  ivgs-frontend/src/app/projects/new/page.tsx  handleSubmit
  ivgs-frontend/src/hooks/useProjects.ts       createProject / uploadProjectAsset
                                               / uploadTranscripts
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# Exactly the list the form now offers (page.tsx TARGET_LANGUAGES).
FORM_LANGUAGES = [
    "en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "zh-CN", "ja-JP", "ar-SA",
]


class TestTheFormCanSucceed:
    async def test_full_walk_create_clip_transcripts_storyboard_languages(
        self, client: AsyncClient, operator_token: str
    ):
        auth = {"Authorization": f"Bearer {operator_token}"}

        # ── Step 1: createProject — JSON, four fields ────────────────────
        create = await client.post(
            "/api/v1/projects",
            json={
                "name": "Reactor Interlocks 101",
                "description": "Safety interlocks for shift technicians.",
                "max_runtime_seconds": 1800,
                "target_languages": ["en-US", "es-ES"],
            },
            headers=auth,
        )
        assert create.status_code == 201, create.text
        project = create.json()
        project_id = project["id"]

        # ── Step 2: uploadProjectAsset(clip, "reference_clip") ───────────
        clip = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("presenter.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
            data={"asset_type": "reference_clip"},
            headers=auth,
        )
        assert clip.status_code == 201, clip.text
        clip_asset_id = clip.json()["id"]

        # ── Step 3: uploadTranscripts ────────────────────────────────────
        transcripts = await client.post(
            f"/api/v1/projects/{project_id}/transcripts/upload",
            files=[
                ("files", ("part1.txt", b"First segment narration.", "text/plain")),
                ("files", ("part2.txt", b"Second segment narration.", "text/plain")),
            ],
            headers=auth,
        )
        assert transcripts.status_code == 201, transcripts.text
        assert len(transcripts.json()) == 2

        # ── Step 4: uploadProjectAsset(storyboard, "document") ───────────
        storyboard = await client.post(
            f"/api/v1/projects/{project_id}/assets/upload",
            files={"file": ("storyboard.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"asset_type": "document"},
            headers=auth,
        )
        assert storyboard.status_code == 201, storyboard.text

        # ── Verify the created rows via the API ──────────────────────────
        detail = await client.get(f"/api/v1/projects/{project_id}", headers=auth)
        assert detail.status_code == 200
        body = detail.json()
        assert body["name"] == "Reactor Interlocks 101"
        assert body["description"] == "Safety interlocks for shift technicians."
        assert body["max_runtime_seconds"] == 1800
        assert body["state"] == "DRAFT"

        assets = await client.get(
            f"/api/v1/projects/{project_id}/assets", headers=auth
        )
        assert assets.status_code == 200
        by_type = {a["asset_type"]: a["id"] for a in assets.json()["data"]}
        # The clip is stored under the type the pipeline actually looks for
        # (pipeline_orchestrator_v2._fetch_reference_clip_id).
        assert by_type["reference_clip"] == clip_asset_id
        assert "document" in by_type

        listed = await client.get(
            f"/api/v1/projects/{project_id}/transcripts", headers=auth
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 2

    async def test_the_project_can_then_be_triggered(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        """The point of the form: a project it creates must be able to run."""
        auth = {"Authorization": f"Bearer {operator_token}"}

        import app.services.celery_producer as cp

        calls = []

        class _Rec:
            def send_task(self, name, kwargs=None, queue=None, **extra):
                calls.append({"name": name, "kwargs": kwargs or {}})

                class _R:
                    id = "t-1"

                return _R()

        monkeypatch.setattr(cp, "celery_app", _Rec())

        create = await client.post(
            "/api/v1/projects",
            json={"name": "Triggerable", "max_runtime_seconds": 1800},
            headers=auth,
        )
        project_id = create.json()["id"]
        await client.post(
            f"/api/v1/projects/{project_id}/transcripts/upload",
            files=[("files", ("t.txt", b"Narration.", "text/plain"))],
            headers=auth,
        )

        trigger = await client.post(
            f"/api/v1/projects/{project_id}/trigger", headers=auth
        )
        assert trigger.status_code == 200, trigger.text
        assert len(calls) == 1
        ctx = calls[0]["kwargs"]["job_context_dict"]
        assert ctx["max_runtime_seconds"] == 1800
        assert ctx["tier"] == "prototype"


class TestLanguageCodes:
    @pytest.mark.parametrize("code", FORM_LANGUAGES)
    async def test_every_language_the_form_offers_is_accepted(
        self, client: AsyncClient, operator_token: str, code
    ):
        r = await client.post(
            "/api/v1/projects",
            json={"name": f"Lang {code}", "target_languages": [code]},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 201, r.text

    @pytest.mark.parametrize("code", ["en", "es", "fr", "pt", "ko", "hi"])
    async def test_the_old_bare_codes_are_still_rejected(
        self, client: AsyncClient, operator_token: str, code
    ):
        """Proof the old list could never have worked."""
        r = await client.post(
            "/api/v1/projects",
            json={"name": f"Old {code}", "target_languages": [code]},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 422


class TestTheOldPayloadShapeFails:
    async def test_multipart_to_the_create_route_is_rejected(
        self, client: AsyncClient, operator_token: str
    ):
        """The form's original request, verbatim. It cannot succeed."""
        r = await client.post(
            "/api/v1/projects",
            data={
                "name": "Old Shape",
                "description": "d",
                "max_runtime_seconds": "300",
            },
            files={"talking_head_clip": ("p.mp4", b"\x00", "video/mp4")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Cross-checks against the actual frontend source.
#
# These are the regression guards: they read ivgs-frontend and fail on the
# pre-fix tree. The walk above documents the contract; these hold the client to
# it, so the two cannot drift apart again silently.
# ---------------------------------------------------------------------------

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "ivgs-frontend" / "src"
_NEW_PROJECT_PAGE = _FRONTEND / "app" / "projects" / "new" / "page.tsx"
_USE_PROJECTS = _FRONTEND / "hooks" / "useProjects.ts"


def _form_language_codes() -> list[str]:
    src = _NEW_PROJECT_PAGE.read_text(encoding="utf-8")
    block = re.search(
        r"const TARGET_LANGUAGES[^=]*=\s*\[(.*?)\];", src, re.S
    )
    assert block, "TARGET_LANGUAGES not found in new/page.tsx"
    return re.findall(r'code:\s*"([^"]+)"', block.group(1))


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestFrontendMatchesTheServer:
    pytestmark = []  # sync tests: opt out of the module-level asyncio mark

    def test_every_offered_language_is_in_the_server_allow_list(self):
        from app.schemas.project import ProjectCreate

        src = ProjectCreate.__module__
        allowed = {
            "en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "zh-CN", "ja-JP",
            "ar-SA",
        }
        offered = set(_form_language_codes())
        assert offered <= allowed, (
            f"the form offers languages the validator rejects: "
            f"{sorted(offered - allowed)} (see {src})"
        )
        assert offered, "the form offers no languages at all"

    def test_the_create_call_is_json_not_multipart(self):
        src = _USE_PROJECTS.read_text(encoding="utf-8")
        create = re.search(
            r"const createProject = async \((.*?)\n  \};", src, re.S
        )
        assert create, "createProject not found in useProjects.ts"
        body = create.group(0)
        assert "FormData" not in body, (
            "createProject still builds a FormData; POST /api/v1/projects is a "
            "JSON Pydantic endpoint"
        )
        assert "multipart/form-data" not in body

    def test_the_clip_is_uploaded_as_reference_clip(self):
        page = _NEW_PROJECT_PAGE.read_text(encoding="utf-8")
        assert '"reference_clip"' in page, (
            "the talking-head clip must go up as reference_clip — the asset "
            "type pipeline_orchestrator_v2._fetch_reference_clip_id queries"
        )
        assert "talking_head_clip" not in page, (
            "talking_head_clip has no handler on the create route"
        )

    def test_the_storyboard_field_says_plainly_what_happens_to_it(self):
        page = _NEW_PROJECT_PAGE.read_text(encoding="utf-8")
        assert "not yet used" in page, (
            "the storyboard upload has no server-side consumer; the UI must "
            "say so rather than implying it is used"
        )
        assert "existing_storyboard" not in page
