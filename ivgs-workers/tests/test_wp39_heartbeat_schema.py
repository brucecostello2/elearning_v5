"""
WP-39 ledger (a) — heartbeat supervision was reading fields that do not exist

Every 30 seconds, on a fleet of three healthy nodes, node-01 logged:

    {"task": "heartbeat_supervision", "node_hostname": null,
     "seconds_since_heartbeat": 1787504720, "event": "worker_confirmed_dead",
     "level": "error"}   x3
    HTTP Request: PATCH http://ivgs-scheduler:8001/nodes/None "404 Not Found"  x3

`seconds_since_heartbeat` is the Unix epoch, which is the tell: the supervisor
read `last_heartbeat_epoch` off each /fleet node and defaulted it to 0.
FleetNodeStatus does not publish that field, nor `status`, nor `node_hostname`,
nor `id`. It publishes `node_id`, `last_heartbeat` (ISO-8601), `is_alive` and
`is_draining`. So every node was always past every threshold, every tick — and
a node that had genuinely died would have produced exactly the same three lines.

The payload below is a verbatim /fleet node from the live scheduler
(v5.0.0-20260522, pinned under WP-09), captured 2026-08-23T17:07Z.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import tasks.pipeline_orchestrator as orch
from tasks.pipeline_orchestrator import (
    _heartbeat_age_seconds,
    supervise_worker_heartbeats,
)


def _iso(ago_seconds: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=ago_seconds)
    ).isoformat()


def _fleet_node(ago_seconds: float = 4.0, **over) -> dict:
    node = {
        "node_id": "84859983cb87:gpu0",
        "gpu_index": 0,
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "used_vram_mb": 0,
        "available_vram_mb": 97887,
        "gpu_utilization_pct": 0.0,
        "current_jobs": [],
        "last_heartbeat": _iso(ago_seconds),
        "is_alive": True,
        "is_draining": False,
        "loaded_models": [],
        "circuit_breaker_state": "closed",
    }
    node.update(over)
    return node


class TestHeartbeatAge:

    def test_it_reads_the_iso_field_the_scheduler_actually_publishes(self):
        age = _heartbeat_age_seconds(_fleet_node(ago_seconds=4.0), time.time())
        assert age is not None
        assert 0 <= age < 60

    def test_the_pre_fix_read_produced_the_unix_epoch(self):
        """The defect, executably: the field is simply not there."""
        node = _fleet_node()
        assert "last_heartbeat_epoch" not in node
        pre_fix = time.time() - node.get("last_heartbeat_epoch", 0)
        assert pre_fix > 1_700_000_000, "pre-fix: every node is 56 years stale"

    def test_an_explicit_epoch_still_wins_if_a_future_scheduler_sends_one(self):
        now = time.time()
        node = _fleet_node(ago_seconds=9999, last_heartbeat_epoch=now - 5)
        assert 0 <= _heartbeat_age_seconds(node, now) < 10

    def test_a_z_suffixed_timestamp_parses(self):
        node = _fleet_node()
        node["last_heartbeat"] = (
            datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        )
        assert _heartbeat_age_seconds(node, time.time()) is not None

    def test_no_usable_timestamp_is_unknown_not_ancient(self):
        assert _heartbeat_age_seconds({"node_id": "n"}, time.time()) is None
        assert _heartbeat_age_seconds({"last_heartbeat": ""}, time.time()) is None
        assert _heartbeat_age_seconds({"last_heartbeat": "not a date"}, time.time()) is None


class _Fleet:
    """A scriptable /fleet, plus the client so a test can assert what was called."""

    def __init__(self, client):
        self.client = client

    def serve(self, payload):
        self.client.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=payload),
        )

    def nodes(self, nodes):
        self.serve({"nodes": nodes})


@pytest.fixture()
def fleet(monkeypatch):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(orch.httpx, "Client", MagicMock(return_value=client))
    monkeypatch.setattr(orch, "WorkerConfig", lambda *a, **k: MagicMock())
    return _Fleet(client)


class TestSupervisionAgainstTheRealPayload:

    def test_three_live_nodes_are_not_declared_dead(self, fleet):
        fleet.nodes([_fleet_node(ago_seconds=a) for a in (4.0, 8.0, 8.0)])

        result = supervise_worker_heartbeats()

        assert result["status"] == "ok"
        assert result["total_nodes"] == 3
        assert result["confirmed_dead"] == 0
        assert result["suspected_dead"] == 0
        assert result["unknown_heartbeat"] == 0

    def test_it_no_longer_patches_a_route_that_does_not_exist(self, fleet):
        fleet.nodes([_fleet_node(ago_seconds=a) for a in (4.0, 600.0, 90.0)])

        supervise_worker_heartbeats()

        # ivgs-scheduler registers no PATCH /nodes route at all: /schedule,
        # /register, /heartbeat, DELETE, /fleet, /drain/{node_id}, /health,
        # /metrics. Every one of these was a 404 with `None` in the path.
        fleet.client.patch.assert_not_called()

    def test_a_genuinely_stale_node_is_still_confirmed_dead(self, fleet):
        fleet.nodes([
            _fleet_node(ago_seconds=4.0),
            _fleet_node(node_id="dead:gpu0", ago_seconds=600.0, is_alive=False),
        ])

        result = supervise_worker_heartbeats()

        assert result["confirmed_dead"] == 1
        assert result["suspected_dead"] == 0

    def test_a_node_the_scheduler_still_calls_alive_is_not_buried(self, fleet):
        """is_alive is the registry's own verdict; only agree when it does."""
        fleet.nodes([_fleet_node(ago_seconds=600.0, is_alive=True)])
        assert supervise_worker_heartbeats()["confirmed_dead"] == 0

    def test_the_middle_band_is_suspected_not_confirmed(self, fleet):
        fleet.nodes([_fleet_node(node_id="slow:gpu0", ago_seconds=90.0, is_alive=False)])

        result = supervise_worker_heartbeats()

        assert result["suspected_dead"] == 1
        assert result["confirmed_dead"] == 0

    def test_a_row_with_no_timestamp_is_its_own_outcome(self, fleet):
        node = _fleet_node()
        del node["last_heartbeat"]
        fleet.nodes([node])

        result = supervise_worker_heartbeats()

        assert result["unknown_heartbeat"] == 1
        assert result["confirmed_dead"] == 0


class TestFleetMetrics:

    def test_alive_nodes_is_the_field_that_exists(self, fleet):
        fleet.serve({
            "total_nodes": 3, "alive_nodes": 3,
            "total_vram_mb": 293661, "used_vram_mb": 24576,
        })
        result = orch.collect_gpu_fleet_metrics()
        assert result["online_nodes"] == 3, "read 0 with three live nodes before"
