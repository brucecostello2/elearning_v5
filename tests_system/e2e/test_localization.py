# =============================================================================
# IVGS v5 — End-to-End Test: Localization Pipeline
# =============================================================================
# Spec reference: §17.1 Table 17-1 — Supported Languages
#                 §17.2 Table 17-2 — Localization Stage Execution
#                 §17.3 — Caption Rendering
# =============================================================================

import asyncio
import os
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8001/api/v1")
ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@ivgs.local")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "TestAdmin!2026_secure")

STAGE_TIMEOUT = 600
POLL_INTERVAL = 10


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
async def completed_project(
    client: httpx.AsyncClient, admin_headers: dict
) -> str:
    """Get or create a completed English project for localization."""
    # List existing complete projects
    response = await client.get(
        "/projects?state=COMPLETE&per_page=1",
        headers=admin_headers,
    )
    data = response.json()
    if data["data"]:
        return data["data"][0]["id"]

    pytest.skip("No completed project available for localization E2E test")


class TestLocalizationPipeline:
    """E2E test: trigger localization and verify output."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(1800)
    async def test_localization_to_spanish(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict,
        completed_project: str,
    ):
        """
        Localize a completed English project to Spanish (es-ES).
        Per §17.2 Table 17-2:
          Stage 1: Transcript Translation — EXECUTE (vLLM translation)
          Stage 2: Scene Images — SKIP (language-neutral, reuse)
          Stage 3: Animation/Video — SKIP (language-neutral, reuse)
          Stage 4: TTS Audio — EXECUTE (Coqui XTTS v2 in Spanish)
          Stage 5: Talking Head Lip-Sync — EXECUTE (LatentSync re-render)
          Stage 6: Caption Generation — EXECUTE (WhisperX SRT)
          Stage 7: Final Composition — EXECUTE (FFmpeg composite)
        """
        project_id = completed_project

        # Trigger localization
        response = await client.post(
            f"/projects/{project_id}/languages",
            json={"language_code": "es-ES"},
            headers=admin_headers,
        )
        assert response.status_code in (200, 202)

        if response.status_code == 202:
            job_id = response.json()["job_id"]
            # Poll for completion
            elapsed = 0
            while elapsed < STAGE_TIMEOUT:
                status = await client.get(
                    f"/jobs/{job_id}", headers=admin_headers
                )
                if status.json()["status"] == "completed":
                    break
                if status.json()["status"] == "failed":
                    pytest.fail(
                        f"Localization failed: {status.json().get('error')}"
                    )
                await asyncio.sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL

        # Verify language variant exists
        project = await client.get(
            f"/projects/{project_id}", headers=admin_headers
        )
        variants = project.json().get("language_variants", [])
        es_variant = next(
            (v for v in variants if v["language_code"] == "es-ES"), None
        )
        assert es_variant is not None, "Spanish variant not found"
        assert es_variant["state"] == "COMPLETE"

        # Verify localized render is downloadable
        download = await client.get(
            f"/projects/{project_id}/render/download?language=es-ES",
            headers=admin_headers,
        )
        assert download.status_code == 200
        assert int(download.headers.get("content-length", 0)) > 0
