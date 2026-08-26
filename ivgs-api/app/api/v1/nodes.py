"""
Node status API endpoints per §5.1.7.

Endpoints:
- GET    /api/v1/nodes              — Node status for the six pipeline nodes
- GET    /api/v1/nodes/{node_id}    — Single node detail with GPU metrics

WP-24 (ledger P2.22, 2026-08-23) removed the Phase-3 stub. Both routes used to
return `status="online"` for every node unconditionally, with `used_vram_mb`,
`gpu_utilization_pct` and `temperature_c` hardcoded to 0 -- while node-05 and
node-06 were physically off and no code path had ever measured a GPU. The
dashboard rendered that as "6 online | 0 offline" over six cards at 0 C.

Status now comes from `app.core.node_health`, which reports online / offline /
**unknown** and names the basis for each. GPU fields are nullable: null means
"not measured" and is never to be rendered as a zero reading.

node-07 (192.168.1.96) is deliberately absent. It hosts the Temporal cluster
only (WP-31) -- no queue, no GPU, no pipeline service. Including it would put a
non-pipeline host into the "N online" denominator. See the WP-24 report, D-1.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user
from app.core.node_health import collect_fleet_health, node_health_notes
from app.core.node_logs import (
    DEFAULT_TAIL,
    MAX_TAIL,
    fetch_logs,
    list_containers,
    node_logs_notes,
)
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["Nodes"])

# WP-62 Task 1. The topology moved to `app/core/node_topology.py` so the GPU
# Fleet page can read the same facts this route reads. It is re-exported here
# unchanged: `from app.api.v1.nodes import NODE_TOPOLOGY` still resolves, which
# four test modules and this file's own routes depend on.
from app.core.node_topology import NODE_TOPOLOGY  # noqa: E402  (re-export)


def _node_payload(node_id, info, health, detail=False):
    """One node's payload: declared topology + observed state, kept apart.

    `total_vram_mb` is a DECLARED capacity from the topology table. Every field
    under `metrics` is an OBSERVATION, and is None when there is no observation.
    None is not zero. A caller that renders None as 0 reintroduces exactly the
    defect WP-24 removed.
    """
    metrics = health["metrics"]
    payload = {
        "node_id": node_id,
        "hostname": info["hostname"],
        "status": health["status"],
        "status_basis": health["status_basis"],
        "status_reason": health["status_reason"],
        "role": info["role"],
        "gpu_model": info["gpu_model"],
        # WP-57 Task 4. EXPLICIT rather than left to be inferred from
        # `gpu_model != null`. Two dashboards counted nodes and neither said
        # what it was counting: Operational Monitoring labelled a count of ALL
        # six nodes "GPU Nodes Online", which silently promotes node-01 - CPU-only
        # infrastructure - into the GPU fleet. A surface cannot state what it
        # counts unless the payload says what each node is.
        "has_gpu": info["gpu_model"] is not None,
        # Whether this node runs a Celery pipeline worker, i.e. whether it is in
        # the SCHEDULER's fleet. This is the distinction that made "3/3" and
        # "5 online of 6" both defensible and both unlabelled: node-06 has a GPU
        # and runs the CLIP scorer but no Celery worker, so it is not one of the
        # scheduler's three.
        #
        # UPDATED 2026-08-26 (WP-61 Task 2). The clause here read "node-05 has
        # a GPU and is out of service", which was the reason on 2026-08-25 and
        # is not the reason now: node-05 is back in service and serves Qwen on
        # :8000. It is still not one of the scheduler's three, for node-06's
        # reason rather than its own - a GPU serving a model, and no Celery
        # worker. The count is unchanged at 3; what changed is why.
        "runs_pipeline_worker": info.get("runs_pipeline_worker", False),
        "total_vram_mb": info["total_vram_mb"],
        "topology_verified": info.get("topology_verified", False),
        # Nullable observations. null == not measured.
        "used_vram_mb": metrics.get("used_vram_mb"),
        "gpu_utilization_pct": metrics.get("gpu_utilization_pct"),
        "temperature_c": metrics.get("temperature_c"),
        # WP-48 Task 2. This was inside `if detail:` and nothing else was.
        # The Node Monitor CARD reads GET /nodes (the list route), and the card
        # has a Power cell -- so Power read "no data" on every card while
        # Prometheus held a live `nvidia_smi_power_draw_watts` for the node and
        # node_health.py was already querying it. The whole defect was this one
        # field being served on a route the card does not call. It is a
        # measurement like the other three and belongs beside them.
        "power_draw_w": metrics.get("power_draw_w"),
        "telemetry": health["telemetry"],
        "services": info["services"],
        "active_jobs": [],
    }
    if detail:
        payload["last_heartbeat_at"] = None
    return payload


@router.get("", summary="List all nodes with status")
async def list_nodes(
    current_user: User = Depends(get_current_user),
):
    """
    Node status for the six pipeline nodes. Polled every 10 seconds by Node Monitor.

    `status` is one of online / offline / **unknown**, and `status_basis` says how
    it was established. GPU metric fields are null when nothing measured them --
    they are never zero-as-a-reading. See `app.core.node_health`.
    """
    health = collect_fleet_health(NODE_TOPOLOGY.keys())
    return [
        _node_payload(node_id, info, health[node_id])
        for node_id, info in NODE_TOPOLOGY.items()
    ]


@router.get("/health-notes", summary="Standing caveats on node status data")
async def get_health_notes(
    current_user: User = Depends(get_current_user),
):
    """The limits of the numbers on this page, served with them rather than buried.

    Registered before /{node_id} so the literal path wins the route match.
    """
    notes = node_health_notes()
    notes["logs"] = node_logs_notes()["not_a_stream"]
    return notes


@router.get("/{node_id}", summary="Single node detail")
async def get_node(
    node_id: str,
    current_user: User = Depends(get_current_user),
):
    """Single node detail with GPU metrics.

    Same honesty contract as the list route: status may be `unknown`, and every
    GPU field may be null meaning "not measured".
    """
    info = NODE_TOPOLOGY.get(node_id)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Node {node_id} not found"}},
        )
    health = collect_fleet_health([node_id])[node_id]
    return _node_payload(node_id, info, health, detail=True)


def _require_known_node(node_id: str) -> dict:
    info = NODE_TOPOLOGY.get(node_id)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Node {node_id} not found"}},
        )
    return info


@router.get("/{node_id}/containers", summary="Containers running on one node")
async def get_node_containers(
    node_id: str,
    current_user: User = Depends(get_current_user),
):
    """The node's container list, read from its `ivgs-node-logs` source.

    WP-48 Task 3. Same honesty contract as the rest of this router: a node with
    no log source, or an unreachable one, returns `available: false` and the
    reason. It never returns an empty list as though the node had no containers.
    """
    _require_known_node(node_id)
    return list_containers(node_id)


@router.get("/{node_id}/logs", summary="Tail one container's logs on one node")
async def get_node_logs(
    node_id: str,
    container: str = Query(..., description="Container name or id on that node"),
    tail: int = Query(DEFAULT_TAIL, ge=1, le=MAX_TAIL),
    current_user: User = Depends(get_current_user),
):
    """A bounded tail of one container's logs.

    This is a POLLED TAIL, not a stream -- see `app.core.node_logs` for why, and
    for what the page used to promise instead. `/nodes/health-notes` carries the
    same caveat to the UI.
    """
    _require_known_node(node_id)
    return fetch_logs(node_id, container, tail)
