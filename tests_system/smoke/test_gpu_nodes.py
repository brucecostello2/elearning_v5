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
#   node-06: Remotion renderer (NVIDIA RTX 5080 — WP-53; was "Intel GPU acceleration")
# =============================================================================

import os
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

# Endpoints resolve from the canonical node registry (single source: node-01 .env /
# x-gpu-service-urls anchor) -- never hardcoded IPs. Spec 2.3 (192.168.1.0/24) + A.2.
# gpu_exporter has no canonical service URL, so it is built from NODE_0x_IP + its port.
# WP-53: node-06 was 9401, the Intel exporter port. The card is NVIDIA and the
# exporter is nvidia_smi_* on 9400, same as every other GPU node. Matches the
# ivgs-infra/configs/prometheus/prometheus.yml change in the same commit.
_EXPORTER_PORT = {"node-02": 9400, "node-03": 9400, "node-04": 9400, "node-05": 9400, "node-06": 9400}


def _exporter(node_ip_var: str, node: str) -> str:
    ip = os.environ.get(node_ip_var, "")
    return f"http://{ip}:{_EXPORTER_PORT[node]}" if ip else ""


NODE_ENDPOINTS = {
    "node-02": {"vllm": os.environ.get("VLLM_PRIMARY_URL", ""),
                "gpu_exporter": _exporter("NODE_02_IP", "node-02")},
    "node-03": {"vllm": os.environ.get("VLLM_SECONDARY_URL", ""),
                "gpu_exporter": _exporter("NODE_03_IP", "node-03")},
    "node-04": {"vllm": os.environ.get("VLLM_MIDSIZE_URL", ""),
                "comfyui": os.environ.get("COMFYUI_PRIMARY_URL", ""),
                "coqui_tts": os.environ.get("COQUI_TTS_URL", ""),
                "latentsync": os.environ.get("LATENTSYNC_URL", ""),
                "gpu_exporter": _exporter("NODE_04_IP", "node-04")},
    "node-05": {"comfyui": os.environ.get("COMFYUI_FALLBACK_URL", ""),
                "ollama": os.environ.get("OLLAMA_URL", ""),
                "gpu_exporter": _exporter("NODE_05_IP", "node-05")},
    "node-06": {"remotion": os.environ.get("REMOTION_URL", ""),
                "gpu_exporter": _exporter("NODE_06_IP", "node-06")},
}


# These smoke tests hit the live GPU fleet; only runnable when the registry env is
# present (a configured node / the live cluster). Skip cleanly otherwise so the suite
# still collects and runs on node-01 (which has no GPU services).
_REQUIRED_ENV = ("VLLM_PRIMARY_URL", "VLLM_SECONDARY_URL", "VLLM_MIDSIZE_URL",
                 "COMFYUI_PRIMARY_URL", "COMFYUI_FALLBACK_URL", "COQUI_TTS_URL",
                 "LATENTSYNC_URL", "OLLAMA_URL", "REMOTION_URL",
                 "NODE_02_IP", "NODE_03_IP", "NODE_04_IP", "NODE_05_IP", "NODE_06_IP")
pytestmark = pytest.mark.skipif(
    any(not os.environ.get(v) for v in _REQUIRED_ENV),
    reason="GPU smoke tests need the node registry env (configured node / live fleet)",
)


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
# node-06: Remotion / NVIDIA GPU (WP-53: was "Intel GPU")
# ---------------------------------------------------------------------------
class TestNode06:
    """node-06 smoke tests — NVIDIA GeForce RTX 5080, 16303 MiB.

    CORRECTED 2026-08-25 (WP-53); read "Intel B70 Pro 32 GB". node-06 has held
    an NVIDIA card since the swap and holds a consumer 5080 today. These tests
    skip without the node-registry env, so the wrong docstring was never going
    to be contradicted by a run.
    """

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
