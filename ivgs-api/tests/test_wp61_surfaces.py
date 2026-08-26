"""
WP-61 Tasks 2 and 8 — node-05 has a GPU and no worker, and the fleet card's
readings come from Prometheus.

TWO THINGS ARE BEING PINNED AND THEY PULL IN OPPOSITE DIRECTIONS.

Task 2 is about a node that CHANGED: node-05 came back into service and became
the Qwen LLM node, so any surface still calling it "quality services" or "out of
service" is now wrong. The tests here pin the new facts AND the one fact that
did NOT change — it is still not in the scheduler's count, for a new reason.

Task 8 is about numbers that were never going to arrive. `temperature_c`,
`gpu_utilization_pct` and `power_draw_w` reach the scheduler registry on a
worker heartbeat, and the heartbeat sender obtains them by shelling out to
`nvidia-smi` inside the worker container. **The workers image has no such
binary** — `exec: "nvidia-smi": executable file not found in $PATH`, proven
2026-08-26. WP-60 made the card say "not reported" instead of "0 C", which was
the right repair of a lie. This is the repair of the absence behind it: "not
reported" was TRUE and PERMANENT while the numbers sat one container away in
Prometheus, which Node Monitor has been reading all along.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.api.v1.nodes import NODE_TOPOLOGY
from app.schemas.gpu import GpuNodeResponse
from app.services.gpu_service import GpuService


# ---------------------------------------------------------------------------
# Task 2 — node-05's row
# ---------------------------------------------------------------------------

class TestNode05Topology:
    def test_the_role_no_longer_claims_quality_services(self):
        """The earmark is superseded and the scorer is not here.

        The CLIP scorer runs on node-06 and node-06 is its sole host (verified
        `served_by: node-06`). A card reading "Quality services (earmarked)"
        would send an operator to the wrong machine to debug a score.
        """
        role = NODE_TOPOLOGY["node-05"]["role"]
        assert "Quality" not in role
        assert "quality" not in role
        assert "LLM" in role
        assert "Qwen" in role

    def test_node_05_is_NOT_in_the_scheduler_fleet(self):
        """The count stays 3. What changed is WHY.

        node-05 now has a GPU serving a model and no Celery worker — exactly
        node-06's shape. A vLLM server is not a Celery consumer, and AD-02's
        `dynamically_loadable=false` stands: the model is fixed at container
        start by `--model` and cannot be swapped at runtime.
        """
        assert NODE_TOPOLOGY["node-05"]["runs_pipeline_worker"] is False
        assert NODE_TOPOLOGY["node-06"]["runs_pipeline_worker"] is False
        assert (
            sum(
                1 for n in NODE_TOPOLOGY.values()
                if n.get("runs_pipeline_worker")
            )
            == 3
        ), "the scheduler fleet count moved. node-05 must not be added to it."

    def test_the_declared_services_name_the_llm_container(self):
        services = NODE_TOPOLOGY["node-05"]["services"]
        assert "vllm-qwen" in services
        # And the services it has never run are still absent. WP-24 removed a
        # page that listed six nodes' services as observed fact; putting
        # ComfyUI or Ollama back here would restore that.
        assert "comfyui" not in services
        assert "ollama" not in services
        assert "clip-scorer" not in services

    def test_the_hardware_row_is_unchanged(self):
        """WP-48's measurement stands; only the role moved.

        nvidia-smi on the box: "NVIDIA RTX PRO 5000 Blackwell, 48935 MiB".
        A role change is not licence to re-guess the hardware.
        """
        assert NODE_TOPOLOGY["node-05"]["total_vram_mb"] == 48935
        assert NODE_TOPOLOGY["node-05"]["gpu_model"] == "NVIDIA RTX PRO 5000 Blackwell"
        assert NODE_TOPOLOGY["node-05"]["topology_verified"] is True

    def test_no_topology_row_still_calls_node_05_out_of_service(self):
        """The whole table, not just its own row.

        The reason node-05 sat outside the scheduler count was written into
        node-06's comment as well as node-05's, and a stale reason in a
        neighbouring row is exactly how WP-60 S21.1's comment came to describe
        the opposite of the code beneath it.
        """
        import inspect

        from app.api.v1 import nodes as nodes_module

        src = inspect.getsource(nodes_module)
        # The phrase may appear only where it is explicitly labelled as a
        # correction of what the file used to say.
        for line in src.splitlines():
            if "node-05" in line and "out of service" in line:
                assert (
                    "read" in line or "UPDATED" in line or "which was" in line
                ), f"a live claim that node-05 is out of service: {line.strip()}"

    def test_the_stale_gpu_caveat_is_gone_from_the_health_notes(self):
        """A caveat that is itself stale is worse than no caveat.

        `node_health_notes()["gpu"]` ended "As of 2026-08-23 no node in the
        fleet runs a working GPU exporter (ledger P2.6a)" — which this module's
        own docstring had already corrected two packages earlier. P2.6a was
        closed by WP-48 and nodes do serve the exporter. It sent the reader
        after a fixed bug.
        """
        from app.core.node_health import node_health_notes

        gpu_note = node_health_notes()["gpu"]
        assert "null GPU fields mean not measured, never zero" in gpu_note
        # If P2.6a is mentioned at all it must be as history, not as the
        # current state of the fleet.
        if "P2.6a" in gpu_note:
            assert "CORRECTED" in gpu_note or "used to" in gpu_note


# ---------------------------------------------------------------------------
# Task 8 — the fleet card's readings come from Prometheus
# ---------------------------------------------------------------------------

def _view(hostname: str = "node-04", **over):
    v = {
        "id": None,
        "scheduler_node_id": f"{hostname}:gpu0",
        "node_hostname": hostname,
        "raw_hostname": hostname,
        "gpu_index": 0,
        "gpu_model": "card",
        "total_vram_mb": 97887,
        "used_vram_mb": 16384,
        "reserved_vram_mb": 16384,
        "available_vram_mb": 81503,
        "gpu_utilization_pct": None,
        "temperature_c": None,
        "power_draw_w": None,
        "status": "online",
        "registered_at": None,
        "last_heartbeat_at": None,
        "current_jobs": [],
        "loaded_models": [],
        "circuit_breaker_state": "closed",
    }
    v.update(over)
    return v


HEALTHY = {
    "node-04": {
        "status": "online",
        "status_basis": "node-exporter-scrape",
        "status_reason": "answered",
        "metrics": {
            "used_vram_mb": 16000.0,
            "gpu_utilization_pct": 73.5,
            "temperature_c": 61.0,
            "power_draw_w": 310.0,
        },
        "telemetry": {
            "available": True,
            "source": "prometheus:nvidia-gpu-exporter",
            "reason": "nvidia-gpu-exporter scraped by Prometheus",
            "as_of": "2026-08-26T09:00:00+00:00",
        },
    }
}

SILENT = {
    "node-04": {
        "status": "online",
        "status_basis": "node-exporter-scrape",
        "status_reason": "answered",
        "metrics": {
            "used_vram_mb": None,
            "gpu_utilization_pct": None,
            "temperature_c": None,
            "power_draw_w": None,
        },
        "telemetry": {
            "available": False,
            "source": "prometheus:nvidia-gpu-exporter",
            "reason": (
                "no GPU telemetry: Prometheus holds no nvidia-gpu-exporter "
                "series for this node."
            ),
            "as_of": "2026-08-26T09:00:00+00:00",
        },
    }
}


class TestTelemetryOverlay:
    def test_readings_arrive_from_prometheus_and_are_LABELLED_as_such(self):
        views = [_view()]
        with patch(
            "app.services.gpu_service.collect_fleet_health", return_value=HEALTHY
        ):
            GpuService._overlay_device_telemetry(views)

        assert views[0]["temperature_c"] == pytest.approx(61.0)
        assert views[0]["power_draw_w"] == pytest.approx(310.0)
        assert views[0]["gpu_utilization_pct"] == pytest.approx(73.5)
        # THE LABEL. Two kinds of number live on this card and they are not
        # interchangeable; a surface that shows both without saying which is
        # which is how node-02 read "0.0 GB / 95.6 GB" here while Node Monitor
        # showed 86.4 GB on the same machine at the same moment.
        assert views[0]["telemetry_source"] == "prometheus:nvidia-gpu-exporter"

    def test_reservation_accounting_is_NOT_overwritten_by_the_device_reading(self):
        """`used_vram_mb` stays the scheduler's, per WP-60 Task 2(b).

        Prometheus reports 16000 MiB for this node and the registry reserves
        16384. They are different facts — what the card physically holds versus
        what the scheduler has promised to admitted jobs — and they
        legitimately differ. Overwriting one with the other would destroy the
        distinction WP-60 spent a task establishing.
        """
        views = [_view()]
        with patch(
            "app.services.gpu_service.collect_fleet_health", return_value=HEALTHY
        ):
            GpuService._overlay_device_telemetry(views)

        assert views[0]["used_vram_mb"] == 16384
        assert views[0]["reserved_vram_mb"] == 16384

    def test_an_absent_reading_stays_None_and_carries_a_REASON(self):
        """Never zero, and never a bare null either.

        A null with no reason puts the reader back where WP-60 left them:
        "not reported" with a tooltip telling them to check whether nvidia-smi
        succeeds on the node — a condition that is structurally unreachable.
        """
        views = [_view()]
        with patch(
            "app.services.gpu_service.collect_fleet_health", return_value=SILENT
        ):
            GpuService._overlay_device_telemetry(views)

        assert views[0]["temperature_c"] is None
        assert views[0]["power_draw_w"] is None
        assert views[0]["gpu_utilization_pct"] is None
        assert views[0]["telemetry_source"] is None
        assert "Prometheus" in views[0]["telemetry_reason"]

    def test_a_failed_probe_does_not_take_down_the_fleet_page(self):
        views = [_view()]
        with patch(
            "app.services.gpu_service.collect_fleet_health",
            side_effect=RuntimeError("prometheus is gone"),
        ):
            GpuService._overlay_device_telemetry(views)

        assert views[0]["telemetry_source"] is None
        assert "prometheus is gone" in views[0]["telemetry_reason"]
        # And no fabricated numbers were left behind.
        assert views[0]["temperature_c"] is None

    def test_the_overlay_keys_on_the_RAW_hostname_not_the_display_name(self):
        """A node registered without IVGS_NODE_NAME must still get telemetry.

        `node_display_name` renders such a node as `unnamed (61c7c02b3a…)` —
        deliberately, so the operator can see which nodes have had the WP-45
        identity block applied. Its Prometheus `instance` label is still the
        real hostname. Matching on the pretty string would silently drop
        telemetry for exactly the nodes that need the most attention.
        """
        views = [_view(node_hostname="unnamed (61c7c02b3a)", raw_hostname="node-04")]
        with patch(
            "app.services.gpu_service.collect_fleet_health", return_value=HEALTHY
        ) as probe:
            GpuService._overlay_device_telemetry(views)

        probe.assert_called_once_with(["node-04"])
        assert views[0]["temperature_c"] == pytest.approx(61.0)


class TestSchemaCarriesTheSource:
    def test_the_response_schema_defaults_the_source_to_None(self):
        """Absent means absent. WP-60's rule, applied to the new field."""
        node = GpuNodeResponse(
            id="00000000-0000-0000-0000-000000000001",
            node_hostname="node-04",
            gpu_index=0,
            status="online",
            registered_at="2026-08-26T09:00:00+00:00",
        )
        assert node.telemetry_source is None
        assert node.telemetry_reason is None
        assert node.temperature_c is None
        assert node.power_draw_w is None
        assert node.gpu_utilization_pct is None

    def test_gpu_utilization_is_actually_PASSED_on_the_fleet_route(self):
        """The fifth site, and it was never populated at all.

        `_scheduler_node_response` listed sixteen fields and
        `gpu_utilization_pct` was not one of them — so the schema default
        supplied None and the card said "not reported" whatever the registry
        held. WP-60 fixed temperature and power on this constructor and this
        one was simply absent from the list, which no test of a default could
        ever see. Asserted on the SOURCE for that reason.
        """
        import inspect

        src = inspect.getsource(GpuService._scheduler_node_response)
        assert "gpu_utilization_pct=view" in src
        assert "telemetry_source=view" in src
