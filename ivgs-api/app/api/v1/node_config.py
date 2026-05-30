"""
Node IP registry configuration endpoints (admin commissioning tool).

- GET /api/v1/node-config   — applied registry (from container env) + any staged change
- PUT /api/v1/node-config   — validate and *stage* a new registry (admin only)

Staging only: the API writes a pending file under its existing /ivgs mount and
never touches ivgs-infra/.env or docker. Applying is a deliberate host step:

    scripts/apply-node-config.sh

which backs up .env, rewrites the NODE_0x_IP registry, and recreates the stack.

Spec refs: 2.3 (192.168.1.0/24 VLAN) and Appendix A.2 (env template). This is
distinct from the /nodes endpoint (Phase-8 GPU status), which is read-only state.
"""
import ipaddress
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends

from app.core import node_registry as reg
from app.core.rbac import require_admin
from app.models.user import User
from app.schemas.node_config import (
    NodeConfigResponse,
    NodeConfigUpdate,
    NodeEntry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/node-config", tags=["Node Configuration"])

_EXPECTED_SUBNET = "192.168.1.0/24"


def _build_response(warnings: Optional[List[str]] = None) -> NodeConfigResponse:
    applied = reg.applied_ips()
    pending = reg.read_pending()
    entries: List[NodeEntry] = []
    restart_required = False
    for node_id in reg.NODE_IDS:
        applied_ip = applied.get(node_id)
        staged = pending.get(node_id)
        # Only surface a pending_ip when it actually differs from the applied IP.
        pending_ip = staged if (staged is not None and staged != applied_ip) else None
        if pending_ip is not None:
            restart_required = True
        entries.append(
            NodeEntry(
                node_id=node_id,
                role=reg.NODE_ROLES[node_id],
                applied_ip=applied_ip,
                pending_ip=pending_ip,
            )
        )
    return NodeConfigResponse(
        nodes=entries,
        restart_required=restart_required,
        expected_subnet=_EXPECTED_SUBNET,
        warnings=warnings or [],
    )


@router.get(
    "",
    response_model=NodeConfigResponse,
    summary="Get the node IP registry (applied + staged)",
)
async def get_node_config(current_user: User = Depends(require_admin)):
    """Return the applied node IP registry and any staged (pending) change. Admin only."""
    return _build_response()


@router.put(
    "",
    response_model=NodeConfigResponse,
    summary="Stage a node IP registry change (admin only)",
)
async def update_node_config(
    data: NodeConfigUpdate,
    current_user: User = Depends(require_admin),
):
    """
    Validate and stage a new node IP registry (admin only).

    This does NOT apply the change. The submitted IPs are merged over the applied
    registry and written to a pending file; run scripts/apply-node-config.sh and
    restart the stack to make them live.
    """
    applied = reg.applied_ips()
    desired = dict(applied)
    for item in data.nodes:
        desired[item.node_id] = item.ip  # IPv4 already validated by the schema

    warnings: List[str] = []
    network = ipaddress.ip_network(_EXPECTED_SUBNET)
    for node_id, ip in desired.items():
        try:
            if ipaddress.ip_address(ip) not in network:
                warnings.append(
                    f"{node_id} ({ip}) is outside the spec subnet {_EXPECTED_SUBNET}"
                )
        except ValueError:
            pass

    by_ip: dict = {}
    for node_id, ip in desired.items():
        by_ip.setdefault(ip, []).append(node_id)
    for ip, ids in by_ip.items():
        if len(ids) > 1:
            warnings.append(f"IP {ip} is assigned to multiple nodes: {', '.join(sorted(ids))}")

    if desired == applied:
        reg.clear_pending()
        logger.info(
            "node-config: submitted registry equals applied; cleared pending (user=%s)",
            current_user.username,
        )
    else:
        reg.write_pending(desired)
        logger.info(
            "node-config: staged registry change (user=%s)", current_user.username
        )

    return _build_response(warnings=warnings)
