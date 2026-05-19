# =============================================================================
# IVGS v5 — GPU Smoke Tests
# =============================================================================
# Spec reference: §19.3 Table 19-2 — GPU smoke tests
#                 Table B-1 — Model VRAM Requirements
#
# Tests per node:
#   node-02: vLLM (Llama 3.3 70B), CogVideoX
#   node-03: vLLM (secondary), CogVideoX
#   node-04: vLLM (Mistral 24B), ComfyUI (FLUX.1), Coqui TTS, LatentSync
#   node-05: ComfyUI (SDXL), Ollama (Llama 3.2 8B)
#   node-06: Remotion renderer (Intel GPU acceleration)
# =============================================================================

import os
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

# Node endpoints from Table 2-4
NODE_ENDPOINTS = {
    "node-02": {"vllm": "http://10.10.0.2:8000", "gpu_exporter": "http://10.10.0.2:9400"},
    "node-03": {"vllm": "http://10.10.0.3:8000", "gpu_exporter": "http://10.10.0.3:9400"},
    "node-04": {
        "vllm": "http://10.10.0.4:8000",
        "comfyui": "http://10.10.0.4:8188",
        "coqui_tts": "http://10.10.0.4:5002",
        "latentsync": "http://10.10.0.4:7860",
        "gpu_exporter": "http://10.10.0.4:9400",
    },
    "node-05": {
        "comfyui": "http://10.10.0.5:8188",
        "ollama": "http://10.10.0.5:11434",
        "gpu_exporter": "http://10.10.0.5:9400",
    },
    "node-06": {
        "remotion": "http://10.10.0.6:3002",
        "gpu_exporter": "http://10.10.0.6:9401",
    },
}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(timeout=120.0) as c:
        yield c


# ---------------------------------------------------------------------------
# node-02: vLLM Primary
# ---------------------------------------------------------------------------
class TestNode02:
    """node-02 GPU smoke tests — RTX 6000 Blackwell 96 GB."""

    @pytest.mark.asyncio
    async def test_vllm_health(self, client: httpx.AsyncClient):
        """vLLM health endpoint responds."""
        response = await client.get(f"{NODE_ENDPOINTS['node-02']['vllm']}/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_vllm_inference(self, client: httpx.AsyncClient):
        """Single LLM inference call completes."""
        response = await client.post(
            f"{NODE_ENDPOINTS['node-02']['vllm']}/v1/completions",
            json={
                "model": "llama-70b",
                "prompt": "Hello, this is a smoke test.",
                "max_tokens": 10,
            },
            headers={"Authorization": "Bearer ivgs-internal"},
        )
        assert response.status_code == 200
        assert len(response.json()["choices"]) > 0

    @pytest.mark.asyncio
    async def test_gpu_exporter_metrics(self, client: httpx.AsyncClient):
        """nvidia-gpu-exporter returns GPU metrics."""
        response = await client.get(
            f"{NODE_ENDPOINTS['node-02']['gpu_exporter']}/metrics"
        )
        assert response.status_code == 200
        assert "nvidia_gpu" in response.text


# ---------------------------------------------------------------------------
# node-03: vLLM Secondary
# ---------------------------------------------------------------------------
class TestNode03:
    """node-03 GPU smoke tests — RTX 6000 Blackwell 96 GB."""

    @pytest.mark.asyncio
    async def test_vllm_health(self, client: httpx.AsyncClient):
        response = await client.get(f"{NODE_ENDPOINTS['node-03']['vllm']}/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_vllm_inference(self, client: httpx.AsyncClient):
        response = await client.post(
            f"{NODE_ENDPOINTS['node-03']['vllm']}/v1/completions",
            json={
                "model": "llama-70b-secondary",
                "prompt": "Smoke test for node-03.",
                "max_tokens": 10,
            },
            headers={"Authorization": "Bearer ivgs-internal"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# node-04: Image, TTS, Talking Head
# ---------------------------------------------------------------------------
class TestNode04:
    """node-04 GPU smoke tests — RTX 5000 Pro Blackwell 48 GB."""

    @pytest.mark.asyncio
    async def test_vllm_midsize_health(self, client: httpx.AsyncClient):
        response = await client.get(f"{NODE_ENDPOINTS['node-04']['vllm']}/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_comfyui_health(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-04']['comfyui']}/system_stats"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_coqui_tts_health(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-04']['coqui_tts']}/health"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_coqui_tts_inference(self, client: httpx.AsyncClient):
        """Single TTS inference — generate short audio clip."""
        response = await client.post(
            f"{NODE_ENDPOINTS['node-04']['coqui_tts']}/api/tts",
            json={
                "text": "This is a smoke test.",
                "language": "en",
            },
        )
        assert response.status_code == 200
        assert int(response.headers.get("content-length", 0)) > 0

    @pytest.mark.asyncio
    async def test_latentsync_health(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-04']['latentsync']}/health"
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# node-05: Fallback Image, Utility
# ---------------------------------------------------------------------------
class TestNode05:
    """node-05 GPU smoke tests — RTX 5080 16 GB."""

    @pytest.mark.asyncio
    async def test_comfyui_fallback_health(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-05']['comfyui']}/system_stats"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ollama_health(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-05']['ollama']}/api/tags"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ollama_inference(self, client: httpx.AsyncClient):
        """Single Ollama inference call."""
        response = await client.post(
            f"{NODE_ENDPOINTS['node-05']['ollama']}/api/generate",
            json={
                "model": "llama3.2:8b-instruct-q4_0",
                "prompt": "Smoke test.",
                "stream": False,
            },
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# node-06: Remotion / Intel GPU
# ---------------------------------------------------------------------------
class TestNode06:
    """node-06 smoke tests — Intel B70 Pro 32 GB."""

    @pytest.mark.asyncio
    async def test_remotion_health(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-06']['remotion']}/health"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_intel_gpu_exporter(self, client: httpx.AsyncClient):
        response = await client.get(
            f"{NODE_ENDPOINTS['node-06']['gpu_exporter']}/metrics"
        )
        assert response.status_code == 200
