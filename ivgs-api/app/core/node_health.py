"""
Node reachability and GPU telemetry, read from Prometheus (WP-24, ledger P2.22/P2.6).

WHY THIS EXISTS. `/api/v1/nodes` used to return `status="online"` for all six
nodes unconditionally, with `used_vram_mb`/`gpu_utilization_pct`/`temperature_c`
hardcoded to 0. The dashboard rendered that as "6 online | 0 offline" and six GPU
cards sitting at 0 C -- an assertion about hardware that no code path had ever
measured.

That last sentence used to read "node-05 and node-06 have been physically off the
whole time." Both halves have since been measured and both were wrong, which is
worth leaving on the record given what this module is for. node-05 was never off
-- WP-48 found its node-exporter had been UP in Prometheus throughout (it is out
of service NOW, 2026-08-25, for a RAM fault, which is a different fact). node-06
is on as of 2026-08-25 and answers on :9100. Neither claim was ever an
observation; both were repeated until they read like one. That is the failure
mode this module exists to prevent, and it was sitting in its own docstring.

WHAT IS TRUE HERE INSTEAD. Three states, and they are kept distinct:

    online   - a real observation says the node answered
    offline  - a real observation says it did not
    unknown  - we could not obtain an observation

`unknown` is the point of this module. "We could not tell" and "it is down" are
different facts, and the defect this replaces was built out of collapsing them.
A failed probe NEVER renders as `offline`.

SOURCE: Prometheus `up{job="node-exporter"}`. Chosen over ICMP/TCP because
Prometheus already scrapes every node on a schedule, is already deployed, and is
reachable from this container -- while ICMP would need CAP_NET_RAW here and a TCP
fan-out would add six dials to an endpoint the UI polls every 10 s. Read
`node_health_notes()` for the limits this choice carries.

THE node-01 EXCEPTION, and why it is not a fudge. `ufw` on node-01 admits only
192.168.1.0/24 to the host, and the compose bridge is 172.x, so a container on
node-01 cannot reach node-01's own published ports -- Prometheus's scrape of
node-01:9100 times out even though node-01 is the healthiest machine in the fleet.
Measured 2026-08-23: from inside ivgs-fastapi, node-01:9100 and 192.168.1.90:9100
both time out (curl rc=28) while node-02/03/04:9100 return 200. Any probe leaving
this container inherits that blind spot. So node-01's status is not probed at all:
this API process runs ON node-01, so if it is answering the request, node-01 is up.
That is a tautology rather than a measurement, and it is labelled `self` in the
payload so nobody mistakes it for one.

GPU TELEMETRY is read from the same Prometheus, job `nvidia-gpu-exporter`.

**CORRECTED 2026-08-25 (WP-57 Task 4). The paragraph that stood here said the
exporter "runs on NO node in the fleet" because P2.6a made it panic at startup.
That was true on 2026-08-23 and is not true now.** WP-48 fixed P2.6a with an
explicit `--query-field-names` list, and node-05 served telemetry through that
exporter on 2026-08-25. Leaving the old sentence in place would send the next
reader after a driver bug that has been fixed.

What IS true: a node can have no GPU telemetry for several different reasons, and
they are not interchangeable. node-05 is silent because **its host has a confirmed
hardware memory fault** (memtest, test 8, multiple cores, 2026-08-25) and the
machine is out of service — not because of an exporter defect. A node with no GPU
at all (node-01) has no telemetry because there is nothing to measure.

Every GPU field is None when unmeasured, carrying a reason. None means "not
measured". It must never be rendered as 0.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

# WP-57 Task 4. Which nodes have a GPU at all, so a "no telemetry" reason can
# tell the truth about WHY. node-01 is CPU-only infrastructure; every other node
# in the fleet carries a card. Kept here rather than imported from
# `api/v1/nodes.NODE_TOPOLOGY` because that module imports this one, and a
# circular import to answer a yes/no question is a poor trade.
_NODES_WITHOUT_GPU = frozenset({"node-01"})


def _node_has_gpu(node_id: str) -> bool:
    return node_id not in _NODES_WITHOUT_GPU


logger = logging.getLogger(__name__)

# Prometheus is a sibling container on ivgs-net. Verified reachable from
# ivgs-fastapi 2026-08-23 (http://prometheus:9090/-/healthy -> 200).
DEFAULT_PROMETHEUS_URL = "http://prometheus:9090"
# Kept small on purpose. This endpoint is polled every 10 s by the Node Monitor,
# so the whole probe has to finish well inside that. See the short-circuit in
# collect_fleet_health(): if the first query cannot run, the rest are skipped
# rather than each burning the full timeout.
PROMETHEUS_TIMEOUT_SECONDS = 2.0

# The node this API process runs on. Its status is asserted, not probed -- see
# the module docstring.
SELF_NODE_ID = "node-01"

STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_UNKNOWN = "unknown"

BASIS_SELF = "self"
BASIS_SCRAPE = "node-exporter-scrape"
BASIS_UNAVAILABLE = "probe-unavailable"

REACHABILITY_QUERY = 'up{job="node-exporter"}'
# vendor-neutral field -> the nvidia_gpu_exporter metric that carries it
GPU_QUERIES = {
    "used_vram_mb": 'nvidia_smi_memory_used_bytes',
    "gpu_utilization_pct": 'nvidia_smi_utilization_gpu_ratio',
    "temperature_c": 'nvidia_smi_temperature_gpu',
    "power_draw_w": 'nvidia_smi_power_draw_watts',
}


def prometheus_url() -> str:
    """Base URL of Prometheus (override with IVGS_PROMETHEUS_URL)."""
    return os.environ.get("IVGS_PROMETHEUS_URL", "").strip() or DEFAULT_PROMETHEUS_URL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _query(client: httpx.Client, expr: str) -> Optional[list]:
    """Run one instant query. Returns the result list, or None if it could not run.

    None is 'no observation', deliberately distinct from [] which is 'Prometheus
    answered and knows of no such series'. Callers must keep them apart: the first
    means unknown, the second means the exporter is genuinely absent.
    """
    try:
        resp = client.get(
            "/api/v1/query", params={"query": expr},
            timeout=PROMETHEUS_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # network, DNS, timeout
        logger.warning(
            "prometheus_query_failed expr=%s error=%s", expr, exc,
        )
        return None
    if resp.status_code != 200:
        logger.warning(
            "prometheus_query_http_error expr=%s status=%s", expr, resp.status_code,
        )
        return None
    try:
        body = resp.json()
    except ValueError as exc:
        logger.warning("prometheus_query_bad_json expr=%s error=%s", expr, exc)
        return None
    if body.get("status") != "success":
        logger.warning(
            "prometheus_query_not_success expr=%s status=%s", expr, body.get("status"),
        )
        return None
    return body.get("data", {}).get("result", [])


def _by_instance(result: list) -> Dict[str, float]:
    """Collapse a Prometheus vector to {instance-label: value}.

    The scrape targets are configured by hostname, so `instance` reads 'node-04'.
    A target addressed as 'node-04:9400' is normalised to 'node-04'.
    """
    out: Dict[str, float] = {}
    for series in result or []:
        inst = (series.get("metric", {}) or {}).get("instance", "")
        if not inst:
            continue
        node_id = inst.split(":")[0]
        try:
            out[node_id] = float(series.get("value", [None, None])[1])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def collect_fleet_health(node_ids) -> Dict[str, Dict[str, Any]]:
    """Reachability + GPU telemetry for every node id given.

    Always returns one entry per node id. Never raises: a node whose state cannot
    be established comes back as `unknown` with a reason, which is a truthful
    answer. It must not come back as `offline`.
    """
    node_ids = list(node_ids)
    reach: Optional[Dict[str, float]] = None
    gpu: Dict[str, Dict[str, float]] = {}
    probe_error: Optional[str] = None

    try:
        with httpx.Client(base_url=prometheus_url()) as client:
            raw = _query(client, REACHABILITY_QUERY)
            if raw is None:
                # Prometheus itself is unreachable. Running the four GPU queries
                # would each burn the full timeout to learn the same thing, and
                # this endpoint is polled every 10 s. Stop here.
                probe_error = "prometheus unreachable or query failed"
            else:
                reach = _by_instance(raw)
                for field, expr in GPU_QUERIES.items():
                    res = _query(client, expr)
                    if res:
                        gpu[field] = _by_instance(res)
    except Exception as exc:  # client construction; defensive
        logger.warning("fleet_health_probe_failed error=%s", exc)
        probe_error = f"probe failed: {exc}"

    as_of = _now_iso()
    out: Dict[str, Dict[str, Any]] = {}

    for node_id in node_ids:
        # --- status ---
        if node_id == SELF_NODE_ID:
            status_value, basis, reason = (
                STATUS_ONLINE, BASIS_SELF,
                "this API process runs on node-01; it answered this request",
            )
        elif reach is None:
            status_value, basis, reason = (
                STATUS_UNKNOWN, BASIS_UNAVAILABLE,
                probe_error or "reachability probe unavailable",
            )
        elif node_id in reach:
            up = reach[node_id] >= 1.0
            status_value = STATUS_ONLINE if up else STATUS_OFFLINE
            basis = BASIS_SCRAPE
            reason = (
                "node-exporter answered the last Prometheus scrape"
                if up else
                "node-exporter did not answer the last Prometheus scrape"
            )
        else:
            # Prometheus answered but has no target for this node: we know
            # nothing about it, which is not the same as it being down.
            status_value, basis, reason = (
                STATUS_UNKNOWN, BASIS_UNAVAILABLE,
                "no node-exporter scrape target is configured for this node",
            )

        # --- GPU telemetry ---
        metrics: Dict[str, Optional[float]] = {}
        for field in GPU_QUERIES:
            raw_value = gpu.get(field, {}).get(node_id)
            metrics[field] = raw_value
        if metrics.get("used_vram_mb") is not None:
            metrics["used_vram_mb"] = round(metrics["used_vram_mb"] / (1024 * 1024), 1)
        if metrics.get("gpu_utilization_pct") is not None:
            # exporter reports a 0..1 ratio
            metrics["gpu_utilization_pct"] = round(
                metrics["gpu_utilization_pct"] * 100.0, 1
            )

        has_any = any(v is not None for v in metrics.values())
        if has_any:
            telemetry_reason = "nvidia-gpu-exporter scraped by Prometheus"
        elif probe_error:
            telemetry_reason = probe_error
        else:
            # WP-57 Task 4. This used to blame ledger P2.6a - the exporter
            # panicking at startup - on EVERY node with no telemetry. WP-48
            # closed P2.6a and node-05 served telemetry through the repaired
            # exporter on 2026-08-25, so that explanation is now wrong wherever
            # it appears, and a stale explanation sends the next reader after
            # the wrong cause. The reason is now derived from what is actually
            # true of the node.
            if not _node_has_gpu(node_id):
                telemetry_reason = (
                    "no GPU telemetry: this node has no GPU"
                )
            elif status_value == "offline":
                telemetry_reason = (
                    "no GPU telemetry: the node is offline, so nothing is "
                    "reporting. Check why the node is down before looking at "
                    "the exporter."
                )
            else:
                telemetry_reason = (
                    "no GPU telemetry: Prometheus holds no nvidia-gpu-exporter "
                    "series for this node. The node is reachable, so the "
                    "exporter is not running or is not being scraped."
                )

        out[node_id] = {
            "status": status_value,
            "status_basis": basis,
            "status_reason": reason,
            "metrics": metrics,
            "telemetry": {
                "available": has_any,
                "source": "prometheus:nvidia-gpu-exporter",
                "reason": telemetry_reason,
                "as_of": as_of,
            },
        }

    return out


def node_health_notes() -> Dict[str, str]:
    """The standing caveats on these numbers, served with them rather than buried.

    A consumer that reads `status` without reading these will over-trust it.
    """
    return {
        "reachability": (
            "'online' means this node's node-exporter answered the most recent "
            "Prometheus scrape. It is a proxy for the host, not the host itself: "
            "a live node whose exporter died reads as offline."
        ),
        "node-01": (
            "node-01 is not probed. This API runs on it, so answering is proof of "
            "life. A probe would be wrong anyway - ufw on node-01 admits only "
            "192.168.1.0/24 to the host, so a container cannot reach node-01's own "
            "published ports and every probe from here times out."
        ),
        "unknown": (
            "'unknown' means the probe itself could not run. It is never a "
            "synonym for offline."
        ),
        "gpu": (
            "null GPU fields mean not measured, never zero. CORRECTED "
            "2026-08-26 (WP-61 Task 8): this note used to end 'As of "
            "2026-08-23 no node in the fleet runs a working GPU exporter "
            "(ledger P2.6a)', which this module's own docstring had already "
            "corrected two packages earlier. P2.6a was closed by WP-48 and "
            "nodes do serve nvidia-gpu-exporter. A caveat that is itself "
            "stale is worse than no caveat: it sends the reader after a fixed "
            "bug. What is true is the sentence above it - null is 'not "
            "measured', and the per-node `telemetry.reason` says why."
        ),
    }
