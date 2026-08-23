"""
WP-24 — the Node Monitor must not assert things it has not measured.

These tests are written against the HONEST behaviour, not the behaviour that
shipped. Ledger P2.22 warned specifically against tests that freeze the stub, so
nothing here asserts "status == online" as a fixed truth. What is pinned is the
set of properties that made the old page a lie:

  * a node that was not observed is `unknown`, never `offline`
  * an unmeasured metric is None, never 0
  * node-05 / node-06 are not forced online

Each test names the pre-fix behaviour it would have caught.

Hermetic: `node_health._query` is monkeypatched, so no Prometheus is contacted
and the tests do not depend on the state of the fleet.
"""
import pytest

from app.core import node_health as nh


def _fake_query(mapping):
    """Build a _query stand-in.

    `mapping` maps a PromQL expression to either a Prometheus-shaped result list,
    or None to simulate "the query could not run".
    """
    def _q(_client, expr):
        return mapping.get(expr, [])
    return _q


def _vector(pairs):
    """Prometheus instant-vector shape: [(instance, value), ...]."""
    return [
        {"metric": {"instance": inst}, "value": [0, str(val)]}
        for inst, val in pairs
    ]


ALL_NODES = ["node-01", "node-02", "node-03", "node-04", "node-05", "node-06"]


class TestReachabilityHonesty:
    def test_down_nodes_report_offline_not_online(self, monkeypatch):
        """PRE-FIX: nodes.py:83 returned "online" for all six unconditionally,
        so node-05 and node-06 -- physically powered off -- showed Online."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([
                ("node-02", 1), ("node-03", 1), ("node-04", 1),
                ("node-05", 0), ("node-06", 0),
            ]),
        }))
        h = nh.collect_fleet_health(ALL_NODES)
        assert h["node-05"]["status"] == nh.STATUS_OFFLINE
        assert h["node-06"]["status"] == nh.STATUS_OFFLINE
        assert h["node-02"]["status"] == nh.STATUS_ONLINE

    def test_failed_probe_is_unknown_never_offline(self, monkeypatch):
        """The failure mode must not invent a verdict.

        Reporting `offline` when the probe itself broke would be a new lie in
        the opposite direction -- the fleet would look dead during a Prometheus
        outage."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: None,   # probe could not run
        }))
        h = nh.collect_fleet_health(ALL_NODES)
        for node_id in ALL_NODES:
            if node_id == nh.SELF_NODE_ID:
                continue
            assert h[node_id]["status"] == nh.STATUS_UNKNOWN, node_id
            assert h[node_id]["status"] != nh.STATUS_OFFLINE, node_id
            assert h[node_id]["status_basis"] == nh.BASIS_UNAVAILABLE

    def test_node_with_no_scrape_target_is_unknown(self, monkeypatch):
        """Prometheus answered but has never heard of this node.

        That is ignorance, not evidence of death."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-02", 1)]),
        }))
        h = nh.collect_fleet_health(["node-02", "node-06"])
        assert h["node-02"]["status"] == nh.STATUS_ONLINE
        assert h["node-06"]["status"] == nh.STATUS_UNKNOWN

    def test_self_node_is_online_even_when_probe_fails(self, monkeypatch):
        """node-01 runs this process. ufw makes every probe of it time out, so
        probing would report the healthiest node in the fleet as down."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: None,
        }))
        h = nh.collect_fleet_health(["node-01"])
        assert h["node-01"]["status"] == nh.STATUS_ONLINE
        assert h["node-01"]["status_basis"] == nh.BASIS_SELF

    def test_every_status_carries_its_basis_and_reason(self, monkeypatch):
        """A status with no stated basis is how the original stub passed review."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-02", 1), ("node-05", 0)]),
        }))
        h = nh.collect_fleet_health(["node-01", "node-02", "node-05"])
        for node_id, entry in h.items():
            assert entry["status_basis"], node_id
            assert entry["status_reason"], node_id


class TestTelemetryHonesty:
    def test_absent_gpu_telemetry_is_none_not_zero(self, monkeypatch):
        """PRE-FIX: nodes.py:85-87 hardcoded used_vram_mb=0,
        gpu_utilization_pct=0.0, temperature_c=0.0. The dashboard drew that as
        six GPUs measured idle at 0 C. This is the core defect of WP-24."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-04", 1)]),
            # no GPU series at all -- the real fleet state, P2.6a
        }))
        h = nh.collect_fleet_health(["node-04"])
        m = h["node-04"]["metrics"]
        for field in ("used_vram_mb", "gpu_utilization_pct", "temperature_c"):
            assert m[field] is None, f"{field} must be None, got {m[field]!r}"
            assert m[field] != 0, f"{field} must not be a zero reading"
        assert h["node-04"]["telemetry"]["available"] is False
        assert h["node-04"]["telemetry"]["reason"]

    def test_present_gpu_telemetry_is_converted(self, monkeypatch):
        """When a reading does exist it must arrive in the units the UI expects:
        bytes -> MB, and the exporter's 0..1 ratio -> percent."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-04", 1)]),
            nh.GPU_QUERIES["used_vram_mb"]: _vector([("node-04", 40173142016)]),
            nh.GPU_QUERIES["gpu_utilization_pct"]: _vector([("node-04", 0.37)]),
            nh.GPU_QUERIES["temperature_c"]: _vector([("node-04", 32)]),
        }))
        h = nh.collect_fleet_health(["node-04"])
        m = h["node-04"]["metrics"]
        assert m["used_vram_mb"] == pytest.approx(38312.0, abs=2.0)
        assert m["gpu_utilization_pct"] == pytest.approx(37.0, abs=0.1)
        assert m["temperature_c"] == pytest.approx(32.0)
        assert h["node-04"]["telemetry"]["available"] is True

    def test_a_real_zero_reading_survives(self, monkeypatch):
        """The fix must not overcorrect. A GPU genuinely at 0% is a fact, and
        must be reported as 0 -- distinguishable from 'not measured' only
        because one is 0.0 and the other is None."""
        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-04", 1)]),
            nh.GPU_QUERIES["gpu_utilization_pct"]: _vector([("node-04", 0.0)]),
            nh.GPU_QUERIES["temperature_c"]: _vector([("node-04", 31)]),
        }))
        h = nh.collect_fleet_health(["node-04"])
        m = h["node-04"]["metrics"]
        # 0.0 is a measurement here, not a placeholder.
        assert m["gpu_utilization_pct"] == 0.0
        assert m["gpu_utilization_pct"] is not None
        assert m["used_vram_mb"] is None      # this one really was not measured
        assert h["node-04"]["telemetry"]["available"] is True


class TestPayloadContract:
    def test_payload_never_emits_zero_for_an_unmeasured_metric(self, monkeypatch):
        """End-to-end guard on the wire shape the frontend consumes."""
        from app.api.v1.nodes import NODE_TOPOLOGY, _node_payload

        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-04", 1)]),
        }))
        health = nh.collect_fleet_health(NODE_TOPOLOGY.keys())
        for node_id, info in NODE_TOPOLOGY.items():
            p = _node_payload(node_id, info, health[node_id])
            for field in ("used_vram_mb", "gpu_utilization_pct", "temperature_c"):
                assert p[field] is None, (
                    f"{node_id}.{field} is {p[field]!r}; with no exporter running "
                    "it must be null, not a number"
                )

    def test_topology_reports_measured_hardware_for_node_04(self):
        """node-04 was declared as an RTX 5000 Pro with 49152 MB. nvidia-smi on
        the box reports an RTX PRO 6000 Blackwell with 97887 MiB -- the wrong
        card at half the real VRAM. Capacity planning read this page."""
        from app.api.v1.nodes import NODE_TOPOLOGY

        n4 = NODE_TOPOLOGY["node-04"]
        assert n4["total_vram_mb"] == 97887
        assert "PRO 6000" in n4["gpu_model"]
        assert n4["topology_verified"] is True

    def test_offline_nodes_are_flagged_as_unverified_topology(self):
        """node-05/06 cannot be measured while powered off, so their declared
        hardware must not be presented as established fact."""
        from app.api.v1.nodes import NODE_TOPOLOGY

        assert NODE_TOPOLOGY["node-05"]["topology_verified"] is False
        assert NODE_TOPOLOGY["node-06"]["topology_verified"] is False

    def test_node_07_is_absent(self):
        """WP-24 D-1: node-07 hosts Temporal only. It is not a pipeline node and
        must not enter the 'N online' denominator."""
        from app.api.v1.nodes import NODE_TOPOLOGY

        assert "node-07" not in NODE_TOPOLOGY
        assert len(NODE_TOPOLOGY) == 6
