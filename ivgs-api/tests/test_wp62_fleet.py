"""
WP-62 Task 1 (RULED, third operator report) — the GPU Fleet page shows EVERY
GPU-bearing machine.

**TWICE "FIXED" BY RELABELLING THE NARROW SOURCE.** WP-57 Task 4 and WP-60
Task 2 each made a tile say which of three defensible numbers it was (6
machines, 5 GPUs, 3 scheduler workers). Both were correct and neither was the
requirement: the page still DREW only the scheduler's registry, so node-05
(48 GB, serving Qwen) and node-06 (16 GB, serving the CLIP scorer) did not
appear on a page titled GPU Fleet Status at all.

They could not, by construction. A node enters that registry by running a
Celery worker that calls `POST /register`. Neither runs one, deliberately, and
neither ever will under AD-02. No amount of relabelling was going to put them
on the page.

`test_every_gpu_bearing_machine_is_returned` is RED against the old service.
"""
from __future__ import annotations

import pytest

from app.services.gpu_service import GpuService


SCHEDULER_FLEET = {
    "nodes": [
        {
            "node_id": "node-02:gpu0", "gpu_index": 0,
            "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "total_vram_mb": 97887, "used_vram_mb": 0, "status": "online",
            "current_jobs": [], "loaded_models": [],
            "last_heartbeat": "2026-08-26T10:00:00Z",
        },
        {
            "node_id": "node-03:gpu0", "gpu_index": 0,
            "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "total_vram_mb": 97887, "used_vram_mb": 0, "status": "online",
            "current_jobs": [], "loaded_models": [],
            "last_heartbeat": "2026-08-26T10:00:00Z",
        },
        {
            "node_id": "node-04:gpu0", "gpu_index": 0,
            "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "total_vram_mb": 97887, "used_vram_mb": 4096, "status": "online",
            "current_jobs": [], "loaded_models": [],
            "last_heartbeat": "2026-08-26T10:00:00Z",
        },
    ],
}

# The Prometheus readings measured on the live fleet 2026-08-26. node-03 has
# NO series (WP61-L4, a real finding: reachable, exporter not scraped), which
# is why it is absent here rather than zeroed.
HEALTH = {
    "node-02": {"used_vram_mb": 88494.0, "gpu_utilization_pct": 0.0,
                "temperature_c": 31.0, "power_draw_w": 16.24},
    "node-04": {"used_vram_mb": 28509.0, "gpu_utilization_pct": 0.0,
                "temperature_c": 33.0, "power_draw_w": 19.43},
    "node-05": {"used_vram_mb": 42694.0, "gpu_utilization_pct": 0.0,
                "temperature_c": 37.0, "power_draw_w": 14.07},
    "node-06": {"used_vram_mb": 964.0, "gpu_utilization_pct": 0.0,
                "temperature_c": 34.0, "power_draw_w": 4.38},
}


@pytest.fixture
def fleet(monkeypatch):
    async def _fleet(*_a, **_k):
        return dict(SCHEDULER_FLEET)

    def _health(node_ids):
        out = {}
        for node_id in node_ids:
            metrics = HEALTH.get(node_id)
            out[node_id] = {
                "status": "online",
                "status_basis": "node-exporter-scrape",
                "status_reason": "answered the last scrape",
                "metrics": metrics or {
                    "used_vram_mb": None, "gpu_utilization_pct": None,
                    "temperature_c": None, "power_draw_w": None,
                },
                "telemetry": {
                    "available": metrics is not None,
                    "source": "prometheus:nvidia-gpu-exporter",
                    "reason": (
                        "nvidia-gpu-exporter scraped by Prometheus"
                        if metrics
                        else "no GPU telemetry: Prometheus holds no "
                             "nvidia-gpu-exporter series for this node."
                    ),
                    "as_of": "2026-08-26T10:00:00Z",
                },
            }
        return out

    monkeypatch.setattr("app.services.gpu_service.fetch_fleet", _fleet)
    monkeypatch.setattr("app.services.gpu_service.collect_fleet_health", _health)


class TestEveryGpuIsShown:
    async def test_every_gpu_bearing_machine_is_returned(self, db_session, fleet):
        """RED AGAINST THE OLD SERVICE, which returned the scheduler's three."""
        nodes, total = await GpuService(db_session).list_nodes()
        names = sorted(n.node_hostname for n in nodes)
        assert names == ["node-02", "node-03", "node-04", "node-05", "node-06"]
        assert total == 5

    async def test_node_01_is_not_on_the_page(self, db_session, fleet):
        """It is CPU-only infrastructure. Including it is the WP-57 defect in
        the other direction -- "GPU Nodes Online" once counted all six."""
        nodes, _ = await GpuService(db_session).list_nodes()
        assert "node-01" not in [n.node_hostname for n in nodes]

    async def test_the_scheduler_subset_is_marked_as_a_subset(
        self, db_session, fleet,
    ):
        """The header renders "5 GPUs - 3 scheduler workers" off ONE payload,
        so the two counts cannot drift the way two tiles reading two endpoints
        did."""
        nodes, _ = await GpuService(db_session).list_nodes()
        by_name = {n.node_hostname: n for n in nodes}
        assert [n.node_hostname for n in nodes if n.in_scheduler] == [
            "node-02", "node-03", "node-04",
        ]
        assert by_name["node-05"].in_scheduler is False
        assert by_name["node-06"].in_scheduler is False

    async def test_non_scheduler_nodes_carry_a_role_and_no_drain(
        self, db_session, fleet,
    ):
        """A non-scheduler node has no active jobs and never will. Without its
        role the card is four readings and a blank space that reads as idle;
        node-05 is not idle, it is holding 27B of FP8 weights."""
        nodes, _ = await GpuService(db_session).list_nodes()
        by_name = {n.node_hostname: n for n in nodes}
        assert "Qwen" in (by_name["node-05"].role or "")
        assert by_name["node-05"].supports_drain is False
        assert by_name["node-06"].supports_drain is False
        for name in ("node-02", "node-03", "node-04"):
            assert by_name[name].supports_drain is True
            assert by_name[name].role


class TestTheReadingsComeFromOnePath:
    async def test_physical_vram_is_the_prometheus_series_node_monitor_reads(
        self, db_session, fleet,
    ):
        """The card leads with what the GPU HOLDS.

        Until this package the only VRAM figure was the scheduler's
        reservation. That is why this page showed node-02 at 0.0 GB while Node
        Monitor -- same Prometheus, same instant -- showed 86.4 GB.
        """
        nodes, _ = await GpuService(db_session).list_nodes()
        by_name = {n.node_hostname: n for n in nodes}
        assert by_name["node-02"].device_used_vram_mb == 88494
        assert by_name["node-05"].device_used_vram_mb == 42694
        # And they are NOT the same number as the reservation.
        assert by_name["node-02"].reserved_vram_mb == 0

    async def test_a_node_with_no_telemetry_reports_absence_not_zero(
        self, db_session, fleet,
    ):
        """node-03 is a REAL finding, not a fixture convenience: reachable,
        exporter not scraped (WP61-L4). A zero here would assert an idle card."""
        nodes, _ = await GpuService(db_session).list_nodes()
        node3 = [n for n in nodes if n.node_hostname == "node-03"][0]
        assert node3.device_used_vram_mb is None
        assert node3.temperature_c is None
        assert node3.telemetry_source is None
        assert "nvidia-gpu-exporter" in (node3.telemetry_reason or "")

    async def test_a_non_scheduler_node_near_full_vram_is_not_an_alarm(
        self, db_session, fleet,
    ):
        """node-05 idles at 42.7 of 47.8 GB because vLLM pre-allocates its KV
        cache at --gpu-memory-utilization 0.90. The payload must carry both
        numbers so the surface can render that as a steady state; painting it
        red would train the operator to ignore the colour."""
        nodes, _ = await GpuService(db_session).list_nodes()
        node5 = [n for n in nodes if n.node_hostname == "node-05"][0]
        assert node5.total_vram_mb == 48935
        assert node5.device_used_vram_mb == 42694
        assert node5.in_scheduler is False
        assert node5.reserved_vram_mb == 0


class TestTheTwoEndpointsAnswerTwoQuestions:
    async def test_the_utilization_summary_stays_the_scheduler_subset(
        self, db_session, fleet,
    ):
        """`/gpu/utilization` is RESERVATION ACCOUNTING and admission control
        reasons about it. node-05's 48 GB is not capacity it may spend, and
        adding it would inflate that denominator."""
        summary = await GpuService(db_session).get_fleet_utilization()
        assert summary.total_nodes == 3
        assert {n.node_hostname for n in summary.nodes} == {
            "node-02", "node-03", "node-04",
        }

    async def test_draining_a_non_scheduler_node_is_refused_with_a_reason(
        self, db_session, fleet,
    ):
        """Not a 404 -- the node exists and the page draws it. Silently
        succeeding would be worse: an operator would believe they had stopped
        work reaching a node that never received any."""
        from app.services.gpu_service import DrainNotApplicable

        service = GpuService(db_session)
        nodes, _ = await service.list_nodes()
        node5 = [n for n in nodes if n.node_hostname == "node-05"][0]
        with pytest.raises(DrainNotApplicable) as exc:
            await service.drain_scheduler_node(node5.id)
        assert "not a scheduler worker" in str(exc.value)

    async def test_the_node_id_is_stable_if_a_node_later_registers(
        self, db_session, fleet,
    ):
        """The synthetic rows use the SAME UUID5 derivation over
        "{hostname}:gpu0" that the scheduler rows use, so a node that later
        registers keeps its id and the page does not appear to gain a node."""
        from uuid import uuid5

        from app.services.scheduler_fleet import NODE_ID_NAMESPACE

        nodes, _ = await GpuService(db_session).list_nodes()
        node5 = [n for n in nodes if n.node_hostname == "node-05"][0]
        assert node5.id == uuid5(NODE_ID_NAMESPACE, "node-05:gpu0")


class TestTheTopologyHasOneHome:
    def test_the_route_still_re_exports_it(self):
        """Four test modules import NODE_TOPOLOGY from `app.api.v1.nodes`. The
        move to `app.core.node_topology` must not break them."""
        from app.api.v1.nodes import NODE_TOPOLOGY as from_route
        from app.core.node_topology import NODE_TOPOLOGY as from_core

        assert from_route is from_core

    def test_gpu_node_ids_is_derived_not_listed(self):
        """A node added to the topology appears on every surface without a
        second list being edited -- the defect the frontend's hardcoded
        GPU_LABELS carried, wrong twice."""
        from app.core.node_topology import NODE_TOPOLOGY, gpu_node_ids

        assert gpu_node_ids() == [
            "node-02", "node-03", "node-04", "node-05", "node-06",
        ]
        assert all(
            NODE_TOPOLOGY[n]["total_vram_mb"] > 0 for n in gpu_node_ids()
        )
        assert "node-01" not in gpu_node_ids()
