# =============================================================================
# IVGS v5 — Integration Tests: GPU Scheduler
# =============================================================================
# Spec reference: §12.2 Admission Control (4-Check System)
#                 §12.3 GPU Scheduler API
#                 §12.4 Table 12-3 — Scheduler Metrics
# =============================================================================

from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

SCHEDULER_URL = "http://localhost:8002"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=SCHEDULER_URL, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# Test Suite 1: Fleet Status
# ---------------------------------------------------------------------------
class TestFleetStatus:

    @pytest.mark.asyncio
    async def test_fleet_returns_all_nodes(self, client: httpx.AsyncClient):
        """GET /fleet returns all 5 GPU nodes per Table 2-2."""
        response = await client.get("/fleet")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # 5 GPU nodes: node-02 through node-06
        node_ids = {n["node_id"] for n in data}
        assert len(node_ids) >= 5

    @pytest.mark.asyncio
    async def test_fleet_node_schema(self, client: httpx.AsyncClient):
        """Fleet response matches Appendix C.4 GPU Node Status Schema."""
        response = await client.get("/fleet")
        data = response.json()
        if data:
            node = data[0]
            assert "node_id" in node
            assert "status" in node
            assert "gpu_model" in node
            assert "total_vram_mb" in node
            assert "used_vram_mb" in node
            assert "gpu_utilization_pct" in node
            assert "temperature_c" in node


# ---------------------------------------------------------------------------
# Test Suite 2: Job Scheduling (§12.2 — 4-Check Admission Control)
# ---------------------------------------------------------------------------
class TestJobScheduling:

    @pytest.mark.asyncio
    async def test_schedule_job(self, client: httpx.AsyncClient):
        """POST /schedule returns reservation with node assignment."""
        response = await client.post(
            "/schedule",
            json={
                "job_id": "test-job-001",
                "model_name": "flux-dev",
                "vram_requirement_mb": 24576,
                "estimated_duration_s": 120,
                "priority": 5,
            },
        )
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert "node_id" in data
            assert "gpu_index" in data
            assert "reservation_id" in data

    @pytest.mark.asyncio
    async def test_schedule_exceeds_vram(self, client: httpx.AsyncClient):
        """Request exceeding all available VRAM → 503 NO_GPU_CAPACITY."""
        response = await client.post(
            "/schedule",
            json={
                "job_id": "test-job-overflow",
                "model_name": "impossibly-large-model",
                "vram_requirement_mb": 999999,
                "estimated_duration_s": 60,
                "priority": 1,
            },
        )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Test Suite 3: Heartbeat (§12.2 — 5-minute TTL)
# ---------------------------------------------------------------------------
class TestHeartbeat:

    @pytest.mark.asyncio
    async def test_heartbeat_update(self, client: httpx.AsyncClient):
        """PUT /heartbeat updates worker heartbeat."""
        response = await client.put(
            "/heartbeat",
            json={
                "worker_id": "test-worker-001",
                "node_hostname": "node-02",
                "gpu_index": 0,
                "current_job_id": "test-job-001",
                "heartbeat_data": {"gpu_util": 75.0, "vram_used_mb": 24000},
            },
        )
        assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Test Suite 4: Node Draining
# ---------------------------------------------------------------------------
class TestNodeDraining:

    @pytest.mark.asyncio
    async def test_drain_node(self, client: httpx.AsyncClient):
        """POST /drain/{node_id} marks node for draining."""
        response = await client.post("/drain/node-05")
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_drained_node_rejects_jobs(self, client: httpx.AsyncClient):
        """Drained node should not receive new job assignments."""
        # Drain a node first
        await client.post("/drain/node-05")

        # Try scheduling a job that would go to node-05
        response = await client.post(
            "/schedule",
            json={
                "job_id": "test-drain-job",
                "model_name": "sdxl",
                "vram_requirement_mb": 10240,
                "estimated_duration_s": 60,
                "priority": 1,
            },
        )
        if response.status_code == 200:
            # If scheduled, should not be on drained node
            assert response.json()["node_id"] != "node-05"


# ---------------------------------------------------------------------------
# Test Suite 5: Metrics Endpoint (§12.4 Table 12-3)
# ---------------------------------------------------------------------------
class TestSchedulerMetrics:

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client: httpx.AsyncClient):
        """Scheduler exposes Prometheus metrics per Table 12-3."""
        response = await client.get("/metrics")
        assert response.status_code == 200
        body = response.text
        # Verify required metrics per Table 12-3
        assert "ivgs_scheduler_queue_depth" in body
        assert "ivgs_scheduler_wait_time_seconds" in body
        assert "ivgs_scheduler_rejection_total" in body
        assert "ivgs_scheduler_circuit_breaker_state" in body
        assert "ivgs_gpu_vram_used_mb" in body
        assert "ivgs_gpu_utilization_pct" in body
