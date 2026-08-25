"""
WP-48 — fleet GPU telemetry and real per-node logs.

Three defects are pinned here, each written against the behaviour that shipped:

  * the Power column. `power_draw_w` was served ONLY by the detail route, while
    the card that renders Power reads the LIST route. Prometheus held a live
    reading the whole time. The test asserts the field is present on both.
  * the log source. `node_logs` must report WHY it cannot answer, and must never
    return an empty line list that reads as "this container is quiet".
  * path safety. The container reference reaches an HTTP path, so a reference
    that is not a plain docker name must be refused before it is sent.

Hermetic: no node, no Prometheus and no Docker socket is contacted. The
transport is monkeypatched at `httpx.get`.
"""
import pytest

from app.core import node_health as nh
from app.core import node_logs as nl


def _vector(pairs):
    return [{"metric": {"instance": inst}, "value": [0, str(val)]} for inst, val in pairs]


def _fake_query(mapping):
    def _q(_client, expr):
        return mapping.get(expr, [])
    return _q


# --------------------------------------------------------------------------- #
# Task 2 — the Power column
# --------------------------------------------------------------------------- #
class TestPowerReachesTheCard:

    def test_power_is_on_the_list_payload_not_only_the_detail_payload(self, monkeypatch):
        """THE WP-48 Task 2 defect, exactly.

        `_node_payload(..., detail=False)` omitted `power_draw_w`. `/api/v1/nodes`
        -- the route the Node Monitor CARD polls every 10 s -- calls it with
        detail=False, so the card's Power cell read "no data" on every node
        including node-04, whose exporter was healthy and whose
        nvidia_smi_power_draw_watts Prometheus had been storing for hours.
        """
        from app.api.v1.nodes import NODE_TOPOLOGY, _node_payload

        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-04", 1)]),
            nh.GPU_QUERIES["power_draw_w"]: _vector([("node-04", 18.87)]),
        }))
        health = nh.collect_fleet_health(["node-04"])["node-04"]

        listed = _node_payload("node-04", NODE_TOPOLOGY["node-04"], health)
        detail = _node_payload("node-04", NODE_TOPOLOGY["node-04"], health, detail=True)

        assert "power_draw_w" in listed, "the card polls the list route"
        assert listed["power_draw_w"] == pytest.approx(18.87)
        assert detail["power_draw_w"] == pytest.approx(18.87)

    def test_power_is_none_not_zero_when_unmeasured(self, monkeypatch):
        """A node with no power series reports None. WP-24's rule, applied to the
        field WP-24 did not reach: 0 W would read as a card that is idle."""
        from app.api.v1.nodes import NODE_TOPOLOGY, _node_payload

        monkeypatch.setattr(nh, "_query", _fake_query({
            nh.REACHABILITY_QUERY: _vector([("node-02", 1)]),
        }))
        health = nh.collect_fleet_health(["node-02"])["node-02"]
        payload = _node_payload("node-02", NODE_TOPOLOGY["node-02"], health)

        assert payload["power_draw_w"] is None
        assert payload["power_draw_w"] != 0

    def test_power_query_is_the_metric_the_exporter_actually_emits(self):
        """utkuozdemir/nvidia_gpu_exporter renames `power.draw` to
        `nvidia_smi_power_draw_watts`. Verified against the live exporters on
        nodes 02/03/04/05, 2026-08-25."""
        assert nh.GPU_QUERIES["power_draw_w"] == "nvidia_smi_power_draw_watts"


# --------------------------------------------------------------------------- #
# Task 5 — node-05 is measured now
# --------------------------------------------------------------------------- #
class TestNode05Topology:

    def test_node05_declares_the_card_that_is_actually_in_it(self):
        """Docs said RTX 5080 / 16 GB / offline. nvidia-smi on the box says
        RTX PRO 5000 Blackwell / 48935 MiB, and it answers. Sizing a job against
        16 GB on a 48 GB card is the node-04 error of WP-24, inverted."""
        from app.api.v1.nodes import NODE_TOPOLOGY

        n5 = NODE_TOPOLOGY["node-05"]
        assert "PRO 5000" in n5["gpu_model"]
        assert n5["total_vram_mb"] == 48935
        assert n5["topology_verified"] is True


# --------------------------------------------------------------------------- #
# Task 3 — the log source
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestNodeLogsAddressing:

    def test_unknown_node_is_named_as_unknown_not_silently_empty(self, monkeypatch):
        monkeypatch.delenv("NODE_99_IP", raising=False)
        out = nl.list_containers("node-99")
        assert out["available"] is False
        assert out["containers"] == []
        assert "no registry entry" in out["reason"]

    def test_node01_is_reached_by_container_dns_not_a_host_port(self, monkeypatch):
        """node-01's own published ports are unreachable from inside a container
        (ufw admits only 192.168.1.0/24; the compose bridge is 172.x). Its log
        source therefore publishes no host port -- the same exception
        node_health.py carries for the reachability probe."""
        monkeypatch.delenv("IVGS_NODE_LOGS_SELF_URL", raising=False)
        url = nl.node_logs_base_url("node-01")
        assert url == nl.DEFAULT_SELF_URL
        assert "192.168.1.90" not in url

    def test_other_nodes_come_from_the_ip_registry(self, monkeypatch):
        monkeypatch.setenv("NODE_04_IP", "192.168.1.93")
        assert nl.node_logs_base_url("node-04") == "http://192.168.1.93:9430"


class TestNodeLogsHonesty:

    def test_unreachable_source_says_so_and_names_the_url(self, monkeypatch):
        monkeypatch.setenv("NODE_06_IP", "192.168.1.95")

        def _boom(*_a, **_k):
            raise OSError("No route to host")
        monkeypatch.setattr(nl.httpx, "get", _boom)

        out = nl.fetch_logs("node-06", "ivgs-celery-node06", tail=10)
        assert out["available"] is False
        assert out["lines"] == []
        assert "192.168.1.95:9430" in out["reason"]
        # The distinction that matters: this is not "the container is quiet".
        assert "not deployed" in out["reason"] or "unreachable" in out["reason"]

    def test_a_traversing_container_ref_never_reaches_the_wire(self, monkeypatch):
        """The container reference is interpolated into an HTTP path. `../info`
        would climb out of the two-route allowlist if it were sent."""
        monkeypatch.setenv("NODE_04_IP", "192.168.1.93")
        sent = []
        monkeypatch.setattr(nl.httpx, "get", lambda url, **_k: sent.append(url) or _Resp())

        out = nl.fetch_logs("node-04", "../info", tail=10)
        assert out["available"] is False
        assert sent == [], "the request must not have been made at all"

    def test_missing_container_is_named_not_reported_as_empty(self, monkeypatch):
        monkeypatch.setenv("NODE_04_IP", "192.168.1.93")
        monkeypatch.setattr(nl.httpx, "get", lambda *_a, **_k: _Resp(status_code=404))
        out = nl.fetch_logs("node-04", "no-such-container", tail=5)
        assert out["available"] is False
        assert "no-such-container" in out["reason"]

    def test_tail_is_bounded(self, monkeypatch):
        monkeypatch.setenv("NODE_04_IP", "192.168.1.93")
        seen = {}

        def _get(url, params=None, **_k):
            seen.update(params or {})
            return _Resp(content=b"")
        monkeypatch.setattr(nl.httpx, "get", _get)

        nl.fetch_logs("node-04", "ivgs-celery-node04", tail=10 ** 6)
        assert int(seen["tail"]) == nl.MAX_TAIL


class TestDockerStreamDecoding:

    def _frame(self, stream, text):
        body = text.encode()
        return bytes([stream, 0, 0, 0]) + len(body).to_bytes(4, "big") + body

    def test_multiplexed_frames_are_demuxed(self):
        """A container started WITHOUT a TTY gets 8-byte frame headers. Left
        undecoded they render as mojibake in the panel and nothing raises --
        which is precisely why this is pinned rather than eyeballed."""
        payload = self._frame(1, "hello\n") + self._frame(2, "world\n")
        assert nl._demux(payload) == "hello\nworld\n"

    def test_raw_tty_output_passes_through(self):
        assert nl._demux(b"plain line\n") == "plain line\n"

    def test_empty_payload(self):
        assert nl._demux(b"") == ""

    def test_ansi_colour_is_stripped_and_level_inferred(self, monkeypatch):
        monkeypatch.setenv("NODE_04_IP", "192.168.1.93")
        line = "2026-08-25T04:00:00.000000000Z \x1b[32m[ERROR]\x1b[0m boom\n"
        monkeypatch.setattr(
            nl.httpx, "get",
            lambda *_a, **_k: _Resp(content=line.encode()),
        )
        out = nl.fetch_logs("node-04", "ivgs-celery-node04", tail=5)
        assert out["available"] is True
        assert out["lines"][0]["message"] == "[ERROR] boom"
        assert out["lines"][0]["level"] == "error"
        assert out["lines"][0]["timestamp"].startswith("2026-08-25T04:00:00")

    def test_a_line_that_names_no_level_reports_none_not_info(self, monkeypatch):
        """Guessing `info` would make the panel's level filter lie about what it
        is hiding."""
        monkeypatch.setenv("NODE_04_IP", "192.168.1.93")
        monkeypatch.setattr(
            nl.httpx, "get",
            lambda *_a, **_k: _Resp(content=b"2026-08-25T04:00:00.000000000Z just a line\n"),
        )
        out = nl.fetch_logs("node-04", "ivgs-celery-node04", tail=5)
        assert out["lines"][0]["level"] is None


class TestTheDeadWebsocketRouteIsGone:

    def test_ssh_based_node_log_streamer_no_longer_exists(self):
        """It shelled out to `ssh` from a container with no ssh binary, so it
        could never emit a line, and it never raised -- the WP-00 swallow shape.
        Its removal is pinned so it cannot quietly come back."""
        from app.api.v1 import ws_logs

        assert not hasattr(ws_logs, "stream_node_logs")
        assert hasattr(ws_logs, "stream_job_status")

    def test_no_route_advertises_the_endpoint_that_never_existed(self):
        from app.api.v1 import ws_logs

        paths = [getattr(r, "path", "") for r in ws_logs.router.routes]
        assert not any("nodes" in p and "logs" in p for p in paths)
