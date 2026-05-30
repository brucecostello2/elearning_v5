"""
Node IP registry helper (admin commissioning tool).

This module keeps the API strictly least-privilege: it never reads or writes
ivgs-infra/.env and never talks to docker. It only:

- applied_ips():  the IPs the running stack is using, read from the container
                  environment (NODE_01_IP..NODE_06_IP, passed through in
                  docker-compose.node01.yml).
- read_pending() / write_pending() / clear_pending():
                  a staged-change file under the API's existing /ivgs mount.

Applying a staged change is a deliberate host operation performed by
scripts/apply-node-config.sh, which consumes the pending file, rewrites the
NODE_0x_IP registry in .env (with a backup), and restarts the stack.
"""
import json
import logging
import os
import tempfile
from typing import Dict

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

DEFAULT_PENDING_PATH = "/ivgs/node-config.pending.json"


def _env_key(node_id: str) -> str:
    """'node-04' -> 'NODE_04_IP'."""
    return "NODE_" + node_id.split("-")[1] + "_IP"


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


def read_pending() -> Dict[str, str]:
    """Staged (not-yet-applied) IPs, or {} when there is no valid pending file."""
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
        if k in NODE_IDS and str(v).strip()
    }


def write_pending(mapping: Dict[str, str]) -> None:
    """Atomically write the staged IP registry to the pending file under /ivgs."""
    path = pending_path()
    payload = {"nodes": {k: mapping[k] for k in NODE_IDS if k in mapping}}
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
