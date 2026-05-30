"""
Node IP registry configuration schemas (admin commissioning tool).

The node IP registry (NODE_01_IP..NODE_06_IP) is the single source for every
per-node address in the stack; it lives in ivgs-infra/.env and is applied to the
running containers when the stack is (re)started. This endpoint lets an admin
view the applied registry and *stage* a change. A host-side apply script writes
.env and restarts. See spec 2.3 (192.168.1.0/24) and Appendix A.2.
"""
import ipaddress
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

NODE_IDS = ("node-01", "node-02", "node-03", "node-04", "node-05", "node-06")


class NodeEntry(BaseModel):
    """A single node: its id, role label, the applied IP, and the staged IP (if any)."""

    node_id: str = Field(description="Node identifier, e.g. node-04")
    role: str = Field(description="Human-readable role of the node")
    applied_ip: Optional[str] = Field(
        default=None,
        description="IP the running stack is currently using (from the container env)",
    )
    pending_ip: Optional[str] = Field(
        default=None,
        description="Staged IP not yet applied; null when there is no pending change",
    )


class NodeConfigResponse(BaseModel):
    """The node IP registry with applied + pending state and any advisories."""

    nodes: List[NodeEntry]
    restart_required: bool = Field(
        description="True if any node has a staged IP that differs from the applied IP"
    )
    expected_subnet: str = Field(
        default="192.168.1.0/24",
        description="Spec 2.3 mandated subnet (advisory; not enforced)",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Soft advisories (e.g. out-of-subnet or duplicate IPs)",
    )


class NodeIPUpdate(BaseModel):
    """One node IP assignment within an update request."""

    node_id: str
    ip: str

    @field_validator("node_id")
    @classmethod
    def known_node(cls, v: str) -> str:
        if v not in NODE_IDS:
            raise ValueError(
                f"Unknown node_id '{v}'; expected one of {', '.join(NODE_IDS)}"
            )
        return v

    @field_validator("ip")
    @classmethod
    def valid_ipv4(cls, v: str) -> str:
        candidate = v.strip()
        try:
            addr = ipaddress.IPv4Address(candidate)
        except ipaddress.AddressValueError:
            raise ValueError(f"'{v}' is not a valid IPv4 address")
        return str(addr)


class NodeConfigUpdate(BaseModel):
    """Admin update: the node IP assignments to stage."""

    nodes: List[NodeIPUpdate] = Field(min_length=1, max_length=6)
