"""Read the GPU fleet from the scheduler's registry. WP-45 Task 4(b), D-2 ruled.

There were three node registries in this system and they disagreed (WP-40 §6):

    gpu_nodes (Postgres) -> GET /api/v1/gpu/nodes      0 rows, forever
    scheduler registry (Redis) -> :8002/fleet           the real one
    static infra inventory -> GET /api/v1/nodes         addresses, not GPUs

``gpu_nodes`` is empty for a structural reason, not a bug in either component:
``register_node`` (``ivgs-workers/utils/gpu_utils.py``) posts to ``POST /register``
on the **scheduler**. Nothing in ivgs-workers has ever called
``POST /api/v1/gpu/nodes``. So "GPU Nodes Online" read 0/0 while three GPUs were
alive and working, and that was a faithful read of an empty table rather than a
frontend misread.

**The ruling is read-through, not a sync job**: the API asks the scheduler, every
time. A periodic copy would give the fleet a fourth registry and a staleness
window; the scheduler's registry is already the one the workers write to and the
one placement decisions are made from, so it is the source of truth and the API
should not keep a second opinion.

Two shapes have to be bridged.

*Identity.* The scheduler keys nodes as ``{node_hostname}:gpu{index}`` and the
hostname it receives is whatever the worker's ``IVGS_NODE_HOSTNAME`` says - which
defaulted to the container's own hex hostname, so the registry filled up with
ids like ``61c7c02b3a8a:gpu0``, one per container recreate. WP-45 Task 4(a) gives
each node a stable ``IVGS_NODE_NAME``; this module maps whatever it is given
through ``node_display_name`` so that a node registered under a hex id still
appears, labelled as unmapped, rather than being hidden.

*Keys.* ``GpuNodeResponse.id`` is a UUID and the scheduler's id is a string.
``node_uuid`` derives a stable UUID5 from the scheduler id, so the same node
always has the same API id across restarts without anything being stored, and
``/gpu/nodes/{uuid}`` can resolve back by recomputing it over the fleet.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULER_URL = "http://ivgs-scheduler:8001"
FLEET_TIMEOUT_SECONDS = 5.0

# Stable namespace for deriving an API-side UUID from a scheduler node id.
# Fixed literal, never regenerated: changing it would change every GPU node id
# the frontend has ever seen.
NODE_ID_NAMESPACE = uuid.UUID("6f9d5b1e-0a2c-4d3f-9b7a-1c8e5f0d2a44")

# node-01..node-06 as the rest of the system spells them (app/core/node_registry).
_NODE_NAME_RE = re.compile(r"^node-0[1-9]$")


class SchedulerUnavailable(RuntimeError):
    """The scheduler could not be reached or did not answer usefully.

    Raised rather than returning an empty fleet. An empty fleet and an
    unreachable scheduler look identical on a dashboard tile, and the whole
    reason this module exists is that "0 nodes online" was being displayed as a
    fact when it was an absence of information.
    """


def scheduler_base_url() -> str:
    return (
        os.environ.get("IVGS_GPU_SCHEDULER_URL", "").strip()
        or DEFAULT_SCHEDULER_URL
    ).rstrip("/")


def split_node_id(node_id: str) -> Tuple[str, int]:
    """``'node-04:gpu0'`` -> ``('node-04', 0)``. Tolerant of unexpected shapes."""
    host, _, tail = node_id.partition(":")
    index = 0
    if tail.startswith("gpu"):
        try:
            index = int(tail[3:])
        except ValueError:
            index = 0
    return host or node_id, index


def node_uuid(node_id: str) -> uuid.UUID:
    """A stable API-side UUID for a scheduler node id."""
    return uuid.uuid5(NODE_ID_NAMESPACE, node_id)


def node_display_name(hostname: str) -> str:
    """The operator-facing name for a registry hostname.

    A hostname that already looks like ``node-0N`` is used as-is. Anything else
    is a container hex id from a worker started without ``IVGS_NODE_NAME``; it is
    labelled rather than hidden, because a node the fleet is using and cannot
    name is a fact the operator needs to see - it is exactly the condition
    Task 4(a) fixes, and silently prettifying it would conceal whether the fix
    has been applied on a given node.
    """
    if _NODE_NAME_RE.match(hostname):
        return hostname
    return f"unnamed ({hostname[:12]})"


async def fetch_fleet(timeout: float = FLEET_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """GET /fleet from the scheduler, or raise SchedulerUnavailable."""
    url = f"{scheduler_base_url()}/fleet"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
    except Exception as exc:
        raise SchedulerUnavailable(
            f"GPU scheduler at {url} could not be reached: {exc}"
        ) from exc
    if resp.status_code != 200:
        raise SchedulerUnavailable(
            f"GPU scheduler at {url} returned HTTP {resp.status_code}: "
            f"{resp.text[:200]}"
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise SchedulerUnavailable(
            f"GPU scheduler at {url} answered 200 with an unreadable body: {exc}"
        ) from exc
    if not isinstance(payload, dict) or "nodes" not in payload:
        raise SchedulerUnavailable(
            f"GPU scheduler at {url} answered without a 'nodes' list"
        )
    return payload


def _parse_heartbeat(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def node_status(node: Dict[str, Any]) -> str:
    """Map the scheduler's two booleans onto the API's three-value status.

    Draining wins over alive: a draining node is still heartbeating, and the
    thing the operator needs to know is that it is not taking new work.
    """
    if node.get("is_draining"):
        return "draining"
    return "online" if node.get("is_alive") else "offline"


def to_node_view(node: Dict[str, Any]) -> Dict[str, Any]:
    """One scheduler fleet node, in the shape the API's GPU schemas expect."""
    node_id = str(node.get("node_id", ""))
    hostname, index_from_id = split_node_id(node_id)
    total = int(node.get("total_vram_mb") or 0)
    used = int(node.get("used_vram_mb") or 0)
    heartbeat = _parse_heartbeat(node.get("last_heartbeat"))

    return {
        "id": node_uuid(node_id),
        "scheduler_node_id": node_id,
        "node_hostname": node_display_name(hostname),
        "raw_hostname": hostname,
        "gpu_index": int(node.get("gpu_index", index_from_id) or 0),
        "gpu_model": node.get("gpu_model") or None,
        "total_vram_mb": total,
        "used_vram_mb": used,
        "available_vram_mb": max(0, total - used),
        "gpu_utilization_pct": float(node.get("gpu_utilization_pct") or 0.0),
        "status": node_status(node),
        # The scheduler does not publish a registration time; the earliest thing
        # it does publish is the heartbeat. Reporting "now" would be an
        # invention, so registered_at mirrors the heartbeat and is null when
        # even that is unknown.
        "registered_at": heartbeat,
        "last_heartbeat_at": heartbeat,
        "current_jobs": list(node.get("current_jobs") or []),
        "loaded_models": list(node.get("loaded_models") or []),
        "circuit_breaker_state": node.get("circuit_breaker_state") or "unknown",
    }


def fleet_node_views(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every node in a /fleet payload, mapped and ordered by display name."""
    views = [to_node_view(n) for n in payload.get("nodes", []) if isinstance(n, dict)]
    views.sort(key=lambda v: (v["node_hostname"], v["gpu_index"]))
    return views
