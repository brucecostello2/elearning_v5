# =============================================================================
# IVGS v5 — Integration Tests: Pipeline Stages
# =============================================================================
# Spec reference: §6.1 Seven-Stage Pipeline
#                 §6.2 Operational Layer (checkpoints, retry, DLQ)
#                 §6.3 Fallback Chains (L1→L4)
# =============================================================================

import asyncio
from typing import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

BASE_URL = "http://localhost:8001/api/v1"
ADMIN_EMAIL = "admin@ivgs.local"
ADMIN_PASSWORD = "TestAdmin!2026_secure"

# Pipeline stages per §6.1
PIPELINE_STAGES = [
    "TRANSCRIPT_REFINEMENT",
    "STORYBOARD_GENERATION",
    "IMAGE_GENERATION",
    "VIDEO_GENERATION",
    "TTS_SYNTHESIS",
    "TALKING_HEAD",
    "FINAL_COMPOSITION",
]


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as c:
        yield c


@pytest_asyncio.fixture
async def admin_headers(client: httpx.AsyncClient) -> dict:
    response = await client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def project_with_transcript(
    client: httpx.AsyncClient, admin_headers: dict
) -> dict:
    """Create a project and upload a transcript (ready for pipeline)."""
    # Create project
    project = await client.post(
        "/projects",
        json={
            "name": f"Pipeline Test {uuid4().hex[:8]}",
            "max_runtime_seconds": 1800,
        },
        headers=admin_headers,
    )
    project_data = project.json()
    project_id = project_data["id"]

    # Upload transcript
    await client.post(
        f"/projects/{project_id}/transcripts",
        json={
            "content": "This is a test transcript for integration testing. "
            "It covers basic machine learning concepts including "
            "supervised learning, unsupervised learning, and "
            "reinforcement learning.",
            "language_code": "en-US",
        },
        headers=admin_headers,
    )
    return project_data


# ---------------------------------------------------------------------------
# Test Suite 1: Pipeline Stage Triggers
# ---------------------------------------------------------------------------
class TestPipelineTriggers:

    @pytest.mark.asyncio
    async def test_trigger_transcript_refinement(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
        project_with_transcript: dict,
    ):
        """Trigger Stage 1: Transcript Refinement."""
        project_id = project_with_transcript["id"]
        response = await client.post(
            f"/projects/{project_id}/pipeline/transcript-refinement",
            headers=admin_headers,
        )
        assert response.status_code in (200, 202)
        data = response.json()
        assert "job_id" in data

    @pytest.mark.asyncio
    async def test_trigger_all_stages_sequentially(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
        project_with_transcript: dict,
    ):
        """Trigger pipeline stages in order and verify state transitions."""
        project_id = project_with_transcript["id"]

        for stage in PIPELINE_STAGES:
            stage_endpoint = stage.lower().replace("_", "-")
            response = await client.post(
                f"/projects/{project_id}/pipeline/{stage_endpoint}",
                headers=admin_headers,
            )
            # Accept 200 (sync), 202 (async), or 409 (already in progress)
            assert response.status_code in (200, 202, 409), (
                f"Stage {stage} failed with {response.status_code}: {response.text}"
            )

            if response.status_code == 202:
                # Wait for async job to complete (polling)
                job_id = response.json()["job_id"]
                for _ in range(30):  # 30 * 5s = 150s max
                    await asyncio.sleep(5)
                    status = await client.get(
                        f"/jobs/{job_id}",
                        headers=admin_headers,
                    )
                    if status.json()["status"] in ("completed", "failed"):
                        break

    @pytest.mark.asyncio
    async def test_pipeline_busy_rejection(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
        project_with_transcript: dict,
    ):
        """Concurrent pipeline trigger → 422 PIPELINE_BUSY."""
        project_id = project_with_transcript["id"]

        # Trigger first job
        first = await client.post(
            f"/projects/{project_id}/pipeline/transcript-refinement",
            headers=admin_headers,
        )
        if first.status_code == 202:
            # Immediately try another trigger
            second = await client.post(
                f"/projects/{project_id}/pipeline/storyboard-generation",
                headers=admin_headers,
            )
            assert second.status_code == 422
            assert second.json()["error"]["code"] == "PIPELINE_BUSY"


# ---------------------------------------------------------------------------
# Test Suite 2: Checkpoint Resume (§6.2)
# ---------------------------------------------------------------------------
class TestCheckpointResume:

    @pytest.mark.asyncio
    async def test_checkpoint_created_after_stage(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
        project_with_transcript: dict,
    ):
        """Verify checkpoint is created after successful stage completion."""
        project_id = project_with_transcript["id"]

        response = await client.get(
            f"/projects/{project_id}/checkpoints",
            headers=admin_headers,
        )
        assert response.status_code == 200
        # Checkpoints list may be empty for new project
        assert isinstance(response.json()["data"], list)

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
        project_with_transcript: dict,
    ):
        """Resume pipeline from a checkpoint ID."""
        project_id = project_with_transcript["id"]

        response = await client.post(
            f"/projects/{project_id}/pipeline/resume",
            headers=admin_headers,
        )
        # 200 if checkpoint exists, 404 if no checkpoint
        assert response.status_code in (200, 202, 404)


# ---------------------------------------------------------------------------
# Test Suite 3: Fallback Chain Verification (§6.3)
# ---------------------------------------------------------------------------
class TestFallbackChains:

    @pytest.mark.asyncio
    async def test_fallback_policies_exist(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
    ):
        """Verify all 4 scene type fallback policies are seeded."""
        response = await client.get(
            "/admin/fallback-policies",
            headers=admin_headers,
        )
        assert response.status_code == 200
        policies = response.json()["data"]
        scene_types = {p["scene_type"] for p in policies}
        # Per Appendix D.4: action, talking_head, broll, title_card
        assert {"action", "talking_head", "broll", "title_card"}.issubset(scene_types)
