"""
WP-44-QUALITY — the two API routes the quality gate needs and did not have.

`POST /api/v1/quality-scores`
    The worker has POSTed to this exact path since Phase 4
    (`tasks/stage3_images.py::_submit_quality_score`). The route did not exist.
    A 404 raises nothing inside `except Exception`, so every automated verdict
    of the first e2e run was discarded in silence, and `asset_quality_scores`
    holds **zero rows** for that run. That is why the "18 stale flagged review
    items" cannot be cleared or re-scored: they were never written.

`POST /api/v1/clip/score`
    The scorer stage 3 constructs a URL for. Also absent, also 404ing, and the
    old validator credited the full CLIP weight for the miss (swallow register
    instance 24). It is a thin proxy to the node-05 scoring service; when that
    service is not configured or does not answer, this route returns **503 with
    no score field**, never a number.
"""
import pytest
from uuid import uuid4

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# POST /api/v1/quality-scores
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestQualityScoreSubmission:

    async def test_the_route_exists_at_the_path_the_worker_calls(
        self, client: AsyncClient, operator_token: str, asset_id: str
    ):
        """The whole defect was that this returned 404."""
        response = await client.post(
            "/api/v1/quality-scores",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "asset_id": asset_id,
                "quality_score": 0.85,
                "decision": "flagged",
                "scoring_details": {"clip_status": "unavailable"},
            },
        )
        assert response.status_code != 404, (
            "POST /api/v1/quality-scores must exist — the worker has been "
            "calling it since Phase 4"
        )
        assert response.status_code == 201

    async def test_the_verdict_is_actually_persisted_and_readable(
        self, client: AsyncClient, operator_token: str, asset_id: str
    ):
        submit = await client.post(
            "/api/v1/quality-scores",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "asset_id": asset_id,
                "quality_score": 0.7143,
                "decision": "flagged",
                "scoring_details": {
                    "clip_score": "unavailable",
                    "clip_status": "unavailable",
                    "checks_missing": ["clip_ok"],
                    "check_coverage": 0.85,
                    "quality_score_complete": False,
                },
            },
        )
        assert submit.status_code == 201
        body = submit.json()
        assert body["asset_id"] == asset_id
        assert body["decision"] == "flagged"
        assert body["quality_score"] == pytest.approx(0.7143)

        # An automated verdict is unreviewed: that is what distinguishes it
        # from a human decision in the review queue.
        assert body["reviewed_by"] is None
        assert body["reviewed_at"] is None

        listed = await client.get(
            "/api/v1/quality/flagged",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert listed.status_code == 200
        ids = [row["id"] for row in listed.json()["data"]]
        assert body["id"] in ids

    async def test_the_missing_check_record_survives_the_round_trip(
        self, client: AsyncClient, operator_token: str, asset_id: str
    ):
        """A score whose checks were incomplete must SAY so, in the database.

        This is the field that would have made the first run's sixteen 1.0s
        readable for what they were.
        """
        details = {
            "clip_score": "unavailable",
            "clip_status": "unavailable",
            "checks_missing": ["blank_check_ok", "clip_ok", "noise_check_ok"],
            "check_coverage": 0.6,
            "quality_score_complete": False,
        }
        submit = await client.post(
            "/api/v1/quality-scores",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "asset_id": asset_id,
                "quality_score": 1.0,
                "decision": "flagged",
                "scoring_details": details,
            },
        )
        assert submit.status_code == 201
        stored = submit.json()["scoring_details"]
        assert stored["clip_score"] == "unavailable"
        assert stored["quality_score_complete"] is False
        assert sorted(stored["checks_missing"]) == [
            "blank_check_ok",
            "clip_ok",
            "noise_check_ok",
        ]
        assert stored["check_coverage"] == pytest.approx(0.6)

    async def test_unknown_asset_is_404_not_an_orphan_row(
        self, client: AsyncClient, operator_token: str
    ):
        response = await client.post(
            "/api/v1/quality-scores",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "asset_id": str(uuid4()),
                "quality_score": 0.5,
                "decision": "flagged",
            },
        )
        assert response.status_code == 404

    async def test_an_invalid_decision_is_refused(
        self, client: AsyncClient, operator_token: str, asset_id: str
    ):
        response = await client.post(
            "/api/v1/quality-scores",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={
                "asset_id": asset_id,
                "quality_score": 0.5,
                "decision": "excellent",
            },
        )
        assert response.status_code == 422

    async def test_a_viewer_cannot_submit_a_verdict(
        self, client: AsyncClient, viewer_token: str, asset_id: str
    ):
        response = await client.post(
            "/api/v1/quality-scores",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "asset_id": asset_id,
                "quality_score": 1.0,
                "decision": "approved",
            },
        )
        assert response.status_code == 403

    async def test_unauthenticated_is_refused(
        self, client: AsyncClient, asset_id: str
    ):
        response = await client.post(
            "/api/v1/quality-scores",
            json={"asset_id": asset_id, "quality_score": 1.0, "decision": "approved"},
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/v1/clip/score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestClipProxy:

    async def test_the_route_exists_at_the_path_stage_3_builds(
        self, client: AsyncClient, operator_token: str
    ):
        """stage3 posts to `{base_url}/api/v1/clip` + `/score`."""
        response = await client.post(
            "/api/v1/clip/score",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"image_base64": "aGVsbG8=", "text": "a cat"},
        )
        assert response.status_code != 404, (
            "the route stage 3 has always called must exist"
        )

    async def test_no_backend_configured_is_503_with_no_score(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        """An unconfigured scorer returns nothing, not a default."""
        from app.api.v1 import clip as clip_module

        monkeypatch.setattr(clip_module, "CLIP_SERVICE_URL", "")
        response = await client.post(
            "/api/v1/clip/score",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"image_base64": "aGVsbG8=", "text": "a cat"},
        )
        assert response.status_code == 503
        assert "score" not in response.json()
        assert response.json()["detail"]["error"]["code"] == "SCORER_UNAVAILABLE"

    async def test_unreachable_backend_is_503_with_no_score(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        from app.api.v1 import clip as clip_module

        monkeypatch.setattr(clip_module, "CLIP_SERVICE_URL", "http://127.0.0.1:1")
        response = await client.post(
            "/api/v1/clip/score",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"image_base64": "aGVsbG8=", "text": "a cat"},
        )
        assert response.status_code == 503
        assert "score" not in response.json()

    async def test_a_real_backend_score_is_passed_through_unchanged(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        import httpx as _httpx
        from app.api.v1 import clip as clip_module

        class _Resp:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "score": 0.2871,
                    "model": "openai/clip-vit-base-patch32",
                    "served_by": "node-05",
                    "device": "cuda",
                    "latency_ms": 7.4,
                }

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(clip_module, "CLIP_SERVICE_URL", "http://node-05:8300")
        monkeypatch.setattr(_httpx, "AsyncClient", _Client)

        response = await client.post(
            "/api/v1/clip/score",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"image_base64": "aGVsbG8=", "text": "a cat"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["score"] == pytest.approx(0.2871)
        assert body["model"] == "openai/clip-vit-base-patch32"
        assert body["served_by"] == "node-05"

    async def test_a_backend_answering_without_a_score_is_503(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        """A 200 with a useless body must not become 0.0."""
        import httpx as _httpx
        from app.api.v1 import clip as clip_module

        class _Resp:
            status_code = 200
            text = "{}"

            def json(self):
                return {"detail": "no model loaded"}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(clip_module, "CLIP_SERVICE_URL", "http://node-05:8300")
        monkeypatch.setattr(_httpx, "AsyncClient", _Client)

        response = await client.post(
            "/api/v1/clip/score",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"image_base64": "aGVsbG8=", "text": "a cat"},
        )
        assert response.status_code == 503
        assert "score" not in response.json()

    async def test_a_backend_4xx_is_passed_through_not_called_unavailable(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        """A malformed image is not an unavailable scorer.

        The scorer being reachable and the input being usable are two different
        facts, and collapsing them would be the same imprecision this package
        exists to remove.
        """
        import httpx as _httpx
        from app.api.v1 import clip as clip_module

        class _Resp:
            status_code = 400
            text = '{"detail":{"error":{"code":"BAD_IMAGE"}}}'

            def json(self):
                return {"detail": {"error": {"code": "BAD_IMAGE"}}}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(clip_module, "CLIP_SERVICE_URL", "http://node-05:8300")
        monkeypatch.setattr(_httpx, "AsyncClient", _Client)

        response = await client.post(
            "/api/v1/clip/score",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"image_base64": "", "text": "a cat"},
        )
        assert response.status_code == 400, "a client error must not become a 503"
        body = response.json()
        assert body["detail"]["error"]["code"] == "BAD_SCORING_REQUEST"
        assert "score" not in body

    async def test_health_reports_unavailable_honestly(
        self, client: AsyncClient, operator_token: str, monkeypatch
    ):
        from app.api.v1 import clip as clip_module

        monkeypatch.setattr(clip_module, "CLIP_SERVICE_URL", "")
        response = await client.get(
            "/api/v1/clip/health",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is False
        assert body["reason"]
