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

# Static node topology per §2.2; node-02/03/06 per AD-02 Draft 3
# (node-02 LLM-only, node-03 video-only, node-06 = 2nd CUDA video + compositor + LLM failover)
NODE_TOPOLOGY = {
    "node-01": {
        "hostname": "node-01",
        "role": "Infrastructure",
        "gpu_model": None,
        "total_vram_mb": 0,
        "topology_verified": True,
        "services": ["postgres", "redis", "seaweedfs", "ivgs-api", "ivgs-scheduler", "nginx"],
    },
    "node-02": {
        "hostname": "node-02",
        "role": "GPU LLM (fp8 Llama-3.3-70B)",
        # Measured 2026-08-23 (WP-24): nvidia-smi reports 97887 MiB, not 98304.
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "topology_verified": True,
        "services": ["vllm-primary", "celery-worker"],
    },
    "node-03": {
        "hostname": "node-03",
        "role": "GPU Video (CogVideoX/Wan2.1)",
        # Measured 2026-08-23 (WP-24): nvidia-smi reports 97887 MiB, not 98304.
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "topology_verified": True,
        "services": ["cogvideox-server", "cogvideox-worker"],
    },
    "node-04": {
        "hostname": "node-04",
        "role": "GPU Image + TTS + Talking Head",
        # CORRECTED 2026-08-23 (WP-24). This read "NVIDIA RTX 5000 Pro Blackwell"
        # / 49152 MB -- the wrong card at half the real VRAM. Measured on the box:
        # nvidia-smi reports "NVIDIA RTX PRO 6000 Blackwell Workstation Edition,
        # 97887 MiB". Capacity read off this page would have sized jobs against
        # 48 GB on a 96 GB card.
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "topology_verified": True,
        "services": ["comfyui-primary", "coqui-tts", "kokoro-tts", "whisperx",
                     "latentsync", "vllm-midsize", "celery-worker"],
    },
    "node-05": {
        "hostname": "node-05",
        "role": "Quality services (earmarked)",
        # CORRECTED 2026-08-25 (WP-48). This read "NVIDIA RTX 5080" / 16384 MB
        # and the node was documented OFFLINE everywhere -- CLAUDE.md s2,
        # README, AD-02, the functional spec. All three claims were wrong.
        # Measured on the box the same day: nvidia-smi reports "NVIDIA RTX PRO
        # 5000 Blackwell, 48935 MiB, driver 580.173.02", the node answers, and
        # its node-exporter has been UP in Prometheus throughout. A fallback
        # sized against 16 GB on a 48 GB card is the same class of error WP-24
        # corrected on node-04, in the other direction.
        "gpu_model": "NVIDIA RTX PRO 5000 Blackwell",
        "total_vram_mb": 48935,
        "topology_verified": True,
        # Earmarked, not deployed. Listing services it does not run would put
        # this row straight back into the state WP-24 removed.
        "services": ["node-exporter", "nvidia-gpu-exporter", "node-logs"],
    },
    "node-06": {
        "hostname": "node-06",
        # DISPUTED, and left as-is on purpose. AD-02 gave node-06 an on-demand
        # fp8-70B LLM-failover leg, which was sized against the 96 GB this row
        # used to claim. The card is 16 GB. That leg is not possible on this
        # hardware and the role needs an operator re-ruling, not a silent edit
        # here -- WP-53 D-1. Correcting the measured facts below without
        # touching the role keeps the contradiction visible, which is the point.
        "role": "GPU Video + Compositor + LLM failover",
        # CORRECTED 2026-08-25 (WP-53). This read "NVIDIA RTX 6000 Blackwell" /
        # 98304 MB with topology_verified False, carrying WP-24 D-5's DISPUTED
        # flag because the node was off and could not be measured.
        #
        # It is on now, and it was measured: nvidia-smi reports "NVIDIA GeForce
        # RTX 5080", 16303 MiB, driver 580.173.02. A Proxmox VM on host rtx5080
        # with the card passed through. So the swap CLAUDE.md recorded did not
        # put a 96 GB card in this box -- it is a 16 GB consumer 5080, six times
        # smaller than the row claimed, and the third node-06 hardware claim in
        # this file's history.
        #
        # topology_verified True: this is now a measurement, not a declaration.
        "gpu_model": "NVIDIA GeForce RTX 5080",
        "total_vram_mb": 16303,
        "topology_verified": True,
        # DECLARED, not observed. node-06 has never been provisioned -- it has no
        # /opt/ivgs and, measured from node-01 the same day, only :9100
        # (node-exporter) answers; 9400 and 9430 are closed. Provisioning is an
        # operator job and is deliberately not part of WP-53.
        "services": ["cogvideox", "remotion", "ffmpeg", "celery-worker"],
    },
}


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
