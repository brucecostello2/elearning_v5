"""
Node IP registry configuration endpoints (admin commissioning tool).

- GET /api/v1/node-config   — applied registry (from container env) + any staged change
- PUT /api/v1/node-config   — validate and *stage* a new registry (admin only)

Staging only: the API writes a pending file under its existing /ivgs mount and
never touches ivgs-infra/.env or docker. Applying is a deliberate host step:

    scripts/apply-node-config.sh

which backs up .env, rewrites the NODE_0x_IP registry, and recreates the stack.

node-01 (infrastructure host) is reported with editable=False and can never be
staged here; its IP is fixed at the router/host level. The expected subnet and
advisories are computed relative to node-01's own /24.

Spec refs: 2.3 (192.168.1.0/24 VLAN) and Appendix A.2 (env template). This is
distinct from the /nodes endpoint (Phase-8 GPU status), which is read-only state.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

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


def _build_response(extra_warnings: Optional[List[str]] = None) -> NodeConfigResponse:
    applied = reg.applied_ips()
    pending = reg.read_pending()  # already filtered to editable nodes
    entries: List[NodeEntry] = []
    effective: Dict[str, str] = dict(applied)
    restart_required = False
    for node_id in reg.NODE_IDS:
        applied_ip = applied.get(node_id)
        staged = pending.get(node_id)
        # Only surface a pending_ip when it actually differs from the applied IP.
        pending_ip = staged if (staged is not None and staged != applied_ip) else None
        if pending_ip is not None:
            restart_required = True
            effective[node_id] = pending_ip
        entries.append(
            NodeEntry(
                node_id=node_id,
                role=reg.NODE_ROLES[node_id],
                applied_ip=applied_ip,
                pending_ip=pending_ip,
                editable=reg.is_editable(node_id),
            )
        )
    warnings = list(extra_warnings or []) + reg.advisories(applied, effective)
    return NodeConfigResponse(
        nodes=entries,
        restart_required=restart_required,
        expected_subnet=reg.expected_subnet(applied),
        warnings=warnings,
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

    This does NOT apply the change. Submitted IPs for editable nodes are merged
    over the applied registry and written to a pending file; run
    scripts/apply-node-config.sh and restart the stack to make them live.

    node-01 is fixed infrastructure: any submitted node-01 change is ignored
    (with an advisory), never staged.
    """
    applied = reg.applied_ips()
    submitted: Dict[str, str] = {item.node_id: item.ip for item in data.nodes}

    extra: List[str] = []
    node01_submitted = submitted.get(reg.NODE01_ID)
    if node01_submitted is not None and node01_submitted != applied.get(reg.NODE01_ID):
        extra.append(
            "node-01 IP is fixed (router/host assigned) and cannot be changed here; "
            "the submitted node-01 value was ignored."
        )

    # Stage only editable nodes whose submitted IP differs from the applied IP.
    new_pending: Dict[str, str] = {
        node_id: ip
        for node_id, ip in submitted.items()
        if reg.is_editable(node_id) and ip != applied.get(node_id)
    }

    if new_pending:
        reg.write_pending(new_pending)
        logger.info(
            "node-config: staged registry change for %s (user=%s)",
            ", ".join(sorted(new_pending)),
            current_user.username,
        )
    else:
        reg.clear_pending()
        logger.info(
            "node-config: no editable change to stage; cleared pending (user=%s)",
            current_user.username,
        )

    return _build_response(extra_warnings=extra)


@router.post(
    "/apply",
    response_model=NodeConfigResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Apply the staged node IPs and recreate the stack (admin only)",
)
async def apply_node_config(current_user: User = Depends(require_admin)):
    """
    Request that the staged node IP change be applied (admin only).

    The API stays least-privilege: it does NOT edit .env or run docker. It drops
    an apply-request marker under its existing /ivgs mount; a host-side systemd
    watcher on node-01 sees the marker and runs scripts/apply-node-config.sh,
    which backs up + rewrites .env and recreates the stack. The API will be
    briefly unavailable while it is recreated; poll GET /node-config to confirm.

    Returns 409 if there is nothing staged to apply.
    """
    applied = reg.applied_ips()
    pending = reg.read_pending()
    staged = {
        node_id: ip
        for node_id, ip in pending.items()
        if ip and ip != applied.get(node_id)
    }
    if not staged:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "NO_PENDING_CHANGE",
                    "message": "There is no staged change to apply.",
                }
            },
        )

    reg.request_apply(
        {
            "requested_by": current_user.username,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "nodes": staged,
        }
    )
    logger.info(
        "node-config: apply requested by %s for %s",
        current_user.username,
        ", ".join(sorted(staged)),
    )
    return _build_response()
