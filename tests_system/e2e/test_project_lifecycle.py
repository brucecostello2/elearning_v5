# =============================================================================
# IVGS v5 — End-to-End Test: Full Project Lifecycle
# =============================================================================
# Spec reference: §6.1 Seven-Stage Pipeline
#                 §19.3 Table 19-2 — E2E test requirement
#                 §4.3 Pipeline State Machine
#
# Lifecycle: create → transcript → storyboard → image → video → TTS →
#            talking head → final composition → download
# =============================================================================

import asyncio
import os
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

from tests_system.service_urls import API_BASE_URL as BASE_URL  # WP-52: was hardcoded localhost:8001
ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@ivgs.local")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "TestAdmin!2026_secure")

# Maximum wait time per pipeline stage (seconds)
STAGE_TIMEOUT = 600  # 10 minutes per stage
POLL_INTERVAL = 10   # Check every 10 seconds


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
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def wait_for_job(
    client: httpx.AsyncClient,
    headers: dict,
    job_id: str,
    timeout: int = STAGE_TIMEOUT,
) -> dict:
    """Poll job status until completion or timeout."""
    elapsed = 0
    while elapsed < timeout:
        response = await client.get(f"/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        job = response.json()
        if job["status"] == "completed":
            return job
        if job["status"] == "failed":
            pytest.fail(f"Job {job_id} failed: {job.get('error', 'unknown')}")
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    pytest.fail(f"Job {job_id} timed out after {timeout}s")


async def trigger_stage(
    client: httpx.AsyncClient,
    headers: dict,
    project_id: str,
    stage: str,
) -> dict:
    """Trigger a pipeline stage and wait for completion."""
    response = await client.post(
        f"/projects/{project_id}/pipeline/{stage}",
        headers=headers,
    )
    assert response.status_code in (200, 202), (
        f"Stage {stage} trigger failed: {response.status_code} {response.text}"
    )

    if response.status_code == 202:
        job_id = response.json()["job_id"]
        return await wait_for_job(client, headers, job_id)
    return response.json()


# ---------------------------------------------------------------------------
# E2E Test: Full Pipeline Lifecycle
# ---------------------------------------------------------------------------
class TestProjectLifecycle:
    """Full lifecycle: create → transcript → all 7 stages → download."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(3600)  # 1 hour max for full pipeline
    async def test_full_pipeline_lifecycle(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
    ):
        """
        End-to-end test executing the complete IVGS pipeline:
        1. Create project
        2. Upload transcript
        3. Trigger transcript refinement (Stage 1)
        4. Trigger storyboard generation (Stage 2)
        5. Trigger image generation (Stage 3)
        6. Trigger video generation (Stage 4)
        7. Trigger TTS synthesis (Stage 5)
        8. Trigger talking head (Stage 6)
        9. Trigger final composition (Stage 7)
        10. Download final render
        """
        # Step 1: Create project
        project_response = await client.post(
            "/projects",
            json={
                "name": "E2E Lifecycle Test",
                "description": "Full pipeline end-to-end test",
                "max_runtime_seconds": 1800,
            },
            headers=admin_headers,
        )
        assert project_response.status_code == 201
        project = project_response.json()
        project_id = project["id"]
        assert project["state"] == "DRAFT"

        # Step 2: Upload transcript
        transcript_response = await client.post(
            f"/projects/{project_id}/transcripts",
            json={
                "content": (
                    "Welcome to this introduction to machine learning. "
                    "Machine learning is a subset of artificial intelligence "
                    "that enables systems to learn from data. "
                    "In this video, we will cover three key concepts: "
                    "supervised learning, unsupervised learning, and "
                    "reinforcement learning. Let's begin with supervised "
                    "learning, which uses labeled training data to make "
                    "predictions on new, unseen data."
                ),
                "language_code": "en-US",
            },
            headers=admin_headers,
        )
        assert transcript_response.status_code == 201

        # Step 3: Stage 1 — Transcript Refinement
        await trigger_stage(
            client, admin_headers, project_id, "transcript-refinement"
        )
        project_check = await client.get(
            f"/projects/{project_id}", headers=admin_headers
        )
        assert project_check.json()["state"] == "TRANSCRIPT_REFINED"

        # Step 4: Stage 2 — Storyboard Generation
        await trigger_stage(
            client, admin_headers, project_id, "storyboard-generation"
        )
        project_check = await client.get(
            f"/projects/{project_id}", headers=admin_headers
        )
        assert project_check.json()["state"] == "STORYBOARD_GENERATED"
        assert project_check.json()["scene_count"] > 0

        # Step 5: Stage 3 — Image Generation
        await trigger_stage(
            client, admin_headers, project_id, "image-generation"
        )

        # Step 6: Stage 4 — Video Generation
        await trigger_stage(
            client, admin_headers, project_id, "video-generation"
        )

        # Step 7: Stage 5 — TTS Synthesis
        await trigger_stage(
            client, admin_headers, project_id, "tts-synthesis"
        )

        # Step 8: Stage 6 — Talking Head
        await trigger_stage(
            client, admin_headers, project_id, "talking-head"
        )

        # Step 9: Stage 7 — Final Composition
        await trigger_stage(
            client, admin_headers, project_id, "final-composition"
        )

        # Step 10: Verify final state and download
        final_project = await client.get(
            f"/projects/{project_id}", headers=admin_headers
        )
        assert final_project.status_code == 200
        assert final_project.json()["state"] == "COMPLETE"

        # Verify render is downloadable
        render_response = await client.get(
            f"/projects/{project_id}/render/download",
            headers=admin_headers,
        )
        assert render_response.status_code == 200
        assert int(render_response.headers.get("content-length", 0)) > 0
        assert "video/mp4" in render_response.headers.get("content-type", "")
