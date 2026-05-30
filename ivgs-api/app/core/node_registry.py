"""
Node IP registry helper (admin commissioning tool).

This module keeps the API strictly least-privilege: it never reads or writes
ivgs-infra/.env and never talks to docker. It only:

- applied_ips():  the IPs the running stack is using, read from the container
                  environment (NODE_01_IP..NODE_06_IP, passed through in
                  docker-compose.node01.yml).
- read_pending() / write_pending() / clear_pending():
                  a staged-change file under the API's existing /ivgs mount.

node-01 is the fixed infrastructure host (its IP is set at the router/host
level). It is immutable here: is_editable("node-01") is False, it is never
written to the pending file, and the expected subnet / advisories are computed
relative to node-01's own /24.

Applying a staged change is a deliberate host operation performed by
scripts/apply-node-config.sh, which consumes the pending file, rewrites the
NODE_0x_IP registry in .env (with a backup), and restarts the stack.
"""
import ipaddress
import json
import logging
import os
import tempfile
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

NODE_IDS = ("node-01", "node-02", "node-03", "node-04", "node-05", "node-06")

NODE_ROLES = {
    "node-01": "Infrastructure",
    "node-02": "GPU Primary LLM + Video",
    "node-03": "GPU Secondary LLM + Video",
    "node-04": "GPU Image + TTS + Talking Head",
    "node-05": "GPU Fallback Image + Ollama",
    "node-06": "Composition + Rendering",
}

# node-01 is the infrastructure host; its IP is fixed (router/host assigned).
NODE01_ID = "node-01"
# Spec 2.3 mandates a /24; the network itself is derived from node-01's IP.
SUBNET_PREFIX = 24

DEFAULT_PENDING_PATH = "/ivgs/node-config.pending.json"
# Marker the API drops to ask the host watcher to apply + recreate the stack.
DEFAULT_APPLY_REQUEST_PATH = "/ivgs/node-config.apply.request"


def _env_key(node_id: str) -> str:
    """'node-04' -> 'NODE_04_IP'."""
    return "NODE_" + node_id.split("-")[1] + "_IP"


def is_editable(node_id: str) -> bool:
    """node-01 is fixed infrastructure; every other node may be re-addressed."""
    return node_id != NODE01_ID


def pending_path() -> str:
    """Path of the staged-change file (override via IVGS_NODE_CONFIG_PENDING_PATH)."""
    return os.environ.get("IVGS_NODE_CONFIG_PENDING_PATH", DEFAULT_PENDING_PATH)


def applied_ips() -> Dict[str, str]:
    """IPs the running stack is using, read from the container environment."""
    out: Dict[str, str] = {}
    for node_id in NODE_IDS:
        val = os.environ.get(_env_key(node_id))
        if val and val.strip():
            out[node_id] = val.strip()
    return out


def node01_network(applied: Dict[str, str]) -> Optional[ipaddress.IPv4Network]:
    """The /24 derived from node-01's applied IP, or None if it is unknown/invalid."""
    ip = applied.get(NODE01_ID)
    if not ip:
        return None
    try:
        return ipaddress.ip_network(f"{ip}/{SUBNET_PREFIX}", strict=False)
    except ValueError:
        return None


def expected_subnet(applied: Dict[str, str]) -> str:
    """Human-readable subnet for the UI, e.g. '192.168.1.0/24', derived from node-01."""
    net = node01_network(applied)
    return str(net) if net is not None else f"0.0.0.0/{SUBNET_PREFIX}"


def advisories(applied: Dict[str, str], effective: Dict[str, str]) -> List[str]:
    """
    Soft advisories over the effective (to-be-applied) registry:
    - any editable node whose IP is not on node-01's /24, and
    - any IP assigned to more than one node.
    Never blocks; purely informational for the admin.
    """
    out: List[str] = []
    net = node01_network(applied)
    if net is not None:
        for node_id in NODE_IDS:
            if node_id == NODE01_ID:
                continue
            ip = effective.get(node_id)
            if not ip:
                continue
            try:
                if ipaddress.ip_address(ip) not in net:
                    out.append(
                        f"{node_id} ({ip}) is on a different subnet than node-01 ({net})."
                    )
            except ValueError:
                continue
    by_ip: Dict[str, List[str]] = {}
    for node_id in NODE_IDS:
        ip = effective.get(node_id)
        if ip:
            by_ip.setdefault(ip, []).append(node_id)
    for ip, ids in sorted(by_ip.items()):
        if len(ids) > 1:
            out.append(f"IP {ip} is assigned to multiple nodes: {', '.join(sorted(ids))}.")
    return out


def read_pending() -> Dict[str, str]:
    """Staged (not-yet-applied) IPs, or {} when there is no valid pending file.

    node-01 is never editable, so it is filtered out even if present on disk.
    """
    path = pending_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("node-config pending file unreadable at %s: %s", path, exc)
        return {}
    nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
    return {
        k: str(v).strip()
        for k, v in nodes.items()
        if k in NODE_IDS and is_editable(k) and str(v).strip()
    }


def write_pending(mapping: Dict[str, str]) -> None:
    """Atomically write the staged IP registry to the pending file under /ivgs.

    Only editable nodes are persisted; node-01 is never staged.
    """
    path = pending_path()
    payload = {
        "nodes": {k: mapping[k] for k in NODE_IDS if k in mapping and is_editable(k)}
    }
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".node-config.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clear_pending() -> None:
    """Remove the pending file if present (no error if already absent)."""
    try:
        os.unlink(pending_path())
    except FileNotFoundError:
        pass


def apply_request_path() -> str:
    """Path of the apply-request marker (override via IVGS_NODE_CONFIG_APPLY_REQUEST_PATH).

    The API drops this marker (under its existing /ivgs mount) to ask the host-side
    systemd watcher to run scripts/apply-node-config.sh. The API itself never runs
    docker or edits .env; this keeps it least-privilege.
    """
    return os.environ.get(
        "IVGS_NODE_CONFIG_APPLY_REQUEST_PATH", DEFAULT_APPLY_REQUEST_PATH
    )


def request_apply(meta: Dict[str, object]) -> None:
    """Atomically drop the apply-request marker for the host watcher to pick up."""
    path = apply_request_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".apply-request.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def apply_requested() -> bool:
    """True if an apply-request marker is currently present (apply in flight)."""
    return os.path.exists(apply_request_path())
