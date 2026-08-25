"""Per-node container logs, read from each node's `ivgs-node-logs` source (WP-48).

WHY THIS EXISTS. The Node Monitor detail modal advertised, verbatim:

    Live log streaming via WebSocket - connect to
    ws://node-01:8000/api/v1/nodes/{hostname}/logs/stream

That endpoint has never existed. A *different* one did --
``WS /api/v1/ws/nodes/{node_id}/logs`` in ``app/api/v1/ws_logs.py`` -- and it
could not have worked either: it ran ``ssh <ip> 'docker compose logs --follow'``
from inside this container, and this container has no ``ssh`` binary, no key, and
no ``docker`` CLI (measured 2026-08-25: ``command -v ssh`` and ``command -v
docker`` both empty in ``ivgs-fastapi``). So the panel promised a stream that
nothing on either end could produce, and showed a blank pane on every node since
the page shipped.

WHAT REPLACES IT. Each node runs `ivgs-node-logs` from the tracked overlay
``ivgs-infra/docker-compose.telemetry.yml``: nginx over that node's Docker
socket, serving exactly two GET routes and 403 for everything else --

    GET /containers/json          the container list
    GET /containers/<id>/logs     that container's logs

This module is the only consumer. It is a POLLED TAIL, not a stream: the panel
asks for the last N lines every few seconds. That is the honest minimum, and the
limits are stated in ``node_logs_notes()`` and served to the UI rather than
buried here.

WHAT IT DELIBERATELY CANNOT DO. The allowlist refuses ``/containers/<id>/json``,
so this module can never read a container's environment -- which is where the
tokens are. It refuses every non-GET, so it can never start, stop or exec
anything. Widening that allowlist is a security decision, not a convenience.

node-01 IS THE EXCEPTION, for the same reason it is in node_health.py: ufw admits
only 192.168.1.0/24 to the host and the compose bridge is 172.x, so this
container cannot reach node-01's own published ports. node-01's source therefore
publishes no host port and is reached by container DNS
(``http://ivgs-node-logs:9430``) over ivgs-infra_ivgs-net.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# The port `ivgs-node-logs` publishes on every node but node-01.
DEFAULT_NODE_LOGS_PORT = 9430
# node-01 is reached by container DNS, not host port. See the module docstring.
DEFAULT_SELF_URL = "http://ivgs-node-logs:9430"
SELF_NODE_ID = "node-01"

# The Node Monitor polls this; it has to finish well inside that poll.
REQUEST_TIMEOUT_SECONDS = 4.0
# Ceiling on a single tail request. The panel defaults far below this.
MAX_TAIL = 2000
DEFAULT_TAIL = 200

# Engines colour their own output (ComfyUI, uvicorn, vLLM all do). Left in, the
# escape sequences render as literal "[32m[INFO[0m" mojibake in the panel.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# A docker container name or id, and nothing that could climb out of the path.
# The nginx allowlist enforces the same shape; this is the near side of it.
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_LEVEL_PATTERNS = (
    ("critical", re.compile(r"\b(CRITICAL|FATAL|PANIC)\b", re.I)),
    ("error", re.compile(r"\b(ERROR|ERR|EXCEPTION|Traceback)\b", re.I)),
    ("warning", re.compile(r"\b(WARNING|WARN)\b", re.I)),
    ("debug", re.compile(r"\bDEBUG\b", re.I)),
    ("info", re.compile(r"\b(INFO|NOTICE)\b", re.I)),
)


def node_logs_port() -> int:
    raw = os.environ.get("IVGS_NODE_LOGS_PORT", "").strip()
    try:
        return int(raw) if raw else DEFAULT_NODE_LOGS_PORT
    except ValueError:
        return DEFAULT_NODE_LOGS_PORT


def node_logs_base_url(node_id: str) -> Optional[str]:
    """Base URL of a node's log source, or None if the node has no registry entry.

    None means "we do not know where this node is", which the caller must report
    as such. It is not the same as "the node has no log source", which is a
    connection failure, and both are different from "the node is down".
    """
    if node_id == SELF_NODE_ID:
        return (os.environ.get("IVGS_NODE_LOGS_SELF_URL", "").strip()
                or DEFAULT_SELF_URL)
    if not node_id.startswith("node-"):
        return None
    suffix = node_id.split("-")[-1]
    ip = (os.environ.get(f"NODE_{suffix}_IP") or "").strip()
    if not ip:
        return None
    return f"http://{ip}:{node_logs_port()}"


def _unreachable(base_url: Optional[str], exc: Exception) -> str:
    return (
        f"no log source answered at {base_url}: {type(exc).__name__}. "
        "Either ivgs-node-logs is not deployed on this node "
        "(ivgs-infra/docker-compose.telemetry.yml), or the node is unreachable."
    )


def list_containers(node_id: str) -> Dict[str, Any]:
    """The node's containers. Never raises; reports why when it cannot answer."""
    base_url = node_logs_base_url(node_id)
    if base_url is None:
        return {
            "available": False,
            "source": None,
            "reason": f"no registry entry (NODE_xx_IP) for {node_id}",
            "containers": [],
        }
    try:
        resp = httpx.get(
            f"{base_url}/containers/json",
            params={"all": "true"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        logger.warning("node_logs_list_failed node=%s error=%s", node_id, exc)
        return {
            "available": False,
            "source": base_url,
            "reason": _unreachable(base_url, exc),
            "containers": [],
        }

    containers = []
    for item in raw or []:
        names = item.get("Names") or []
        name = (names[0] if names else item.get("Id", ""))[:128].lstrip("/")
        containers.append({
            "name": name,
            "image": item.get("Image"),
            "state": item.get("State"),
            "status": item.get("Status"),
        })
    containers.sort(key=lambda c: (c["state"] != "running", c["name"]))
    return {
        "available": True,
        "source": base_url,
        "reason": None,
        "containers": containers,
    }


def _demux(payload: bytes) -> str:
    """Decode a Docker log payload, multiplexed or raw.

    A container started WITHOUT a TTY gets the multiplexed framing: an 8-byte
    header per frame (1 byte stream id, 3 bytes padding, 4 bytes big-endian
    length). One started WITH a TTY gets raw bytes. Both occur in this fleet, so
    the format is detected rather than assumed -- and a wrong guess here does not
    fail loudly, it silently renders header bytes as mojibake in the panel.
    """
    if not payload:
        return ""
    # A multiplexed frame always begins stream-id in 0..2 followed by three
    # zero bytes. Raw log text effectively never does.
    if not (payload[0] in (0, 1, 2) and payload[1:4] == b"\x00\x00\x00"):
        return payload.decode("utf-8", errors="replace")

    out: List[str] = []
    i = 0
    n = len(payload)
    while i + 8 <= n:
        length = int.from_bytes(payload[i + 4:i + 8], "big")
        chunk = payload[i + 8:i + 8 + length]
        out.append(chunk.decode("utf-8", errors="replace"))
        i += 8 + length
    if i < n:  # a truncated trailing frame; keep what arrived
        out.append(payload[i:].decode("utf-8", errors="replace"))
    return "".join(out)


def _classify(message: str) -> Optional[str]:
    """Best-effort log level. None means 'this line does not say'.

    Deliberately nullable: guessing `info` for every unlabelled line would make
    the panel's level filter quietly lie about what it is hiding.
    """
    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(message):
            return level
    return None


def _split_timestamp(line: str) -> tuple[Optional[str], str]:
    """Peel the RFC3339 stamp docker prepends when `timestamps=1`."""
    head, sep, rest = line.partition(" ")
    if sep and len(head) >= 20 and head[4:5] == "-" and head[10:11] == "T":
        return head, rest
    return None, line


def fetch_logs(
    node_id: str,
    container: str,
    tail: int = DEFAULT_TAIL,
) -> Dict[str, Any]:
    """Tail one container's logs on one node. Never raises."""
    base_url = node_logs_base_url(node_id)
    if base_url is None:
        return {
            "available": False,
            "source": None,
            "container": container,
            "reason": f"no registry entry (NODE_xx_IP) for {node_id}",
            "lines": [],
        }
    if not _SAFE_REF.match(container or ""):
        return {
            "available": False,
            "source": base_url,
            "container": container,
            "reason": "container name is not a valid docker name or id",
            "lines": [],
        }
    tail = max(1, min(int(tail or DEFAULT_TAIL), MAX_TAIL))

    try:
        resp = httpx.get(
            f"{base_url}/containers/{container}/logs",
            params={
                "stdout": "1", "stderr": "1",
                "tail": str(tail), "timestamps": "1",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "node_logs_fetch_failed node=%s container=%s error=%s",
            node_id, container, exc,
        )
        return {
            "available": False,
            "source": base_url,
            "container": container,
            "reason": _unreachable(base_url, exc),
            "lines": [],
        }

    if resp.status_code == 404:
        return {
            "available": False,
            "source": base_url,
            "container": container,
            "reason": f"no container named {container!r} on {node_id}",
            "lines": [],
        }
    if resp.status_code != 200:
        return {
            "available": False,
            "source": base_url,
            "container": container,
            "reason": (
                f"log source returned HTTP {resp.status_code}. A 403 means the "
                "route is outside the ivgs-node-logs allowlist."
            ),
            "lines": [],
        }

    text = _demux(resp.content)
    lines: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        clean = _ANSI.sub("", raw_line)
        if not clean.strip():
            continue
        ts, message = _split_timestamp(clean)
        # A line that is nothing but a docker timestamp is a blank line in the
        # container's output. It carries nothing and only pads the panel.
        if not message.strip():
            continue
        lines.append({
            "timestamp": ts,
            "level": _classify(message),
            "message": message,
        })

    return {
        "available": True,
        "source": base_url,
        "container": container,
        "reason": None,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "lines": lines,
    }


def node_logs_notes() -> Dict[str, str]:
    """What this panel is and is not, served with the data rather than implied."""
    return {
        "source": (
            "Logs come from `ivgs-node-logs` on the node itself - nginx over that "
            "node's Docker socket, serving exactly GET /containers/json and GET "
            "/containers/<id>/logs. Deployed by "
            "ivgs-infra/docker-compose.telemetry.yml."
        ),
        "not_a_stream": (
            "This is a POLLED TAIL, not a WebSocket stream. The panel re-fetches "
            "the last N lines on an interval, so a line that scrolls past between "
            "two polls on a very chatty container can be missed. The page used to "
            "advertise `ws://node-01:8000/api/v1/nodes/{id}/logs/stream`; that "
            "endpoint never existed."
        ),
        "level": (
            "Log level is inferred from the text of each line, because docker "
            "carries no level field. A line that names no level is reported with "
            "level null and is shown under 'All levels' only."
        ),
        "unreachable": (
            "A node with no log source deployed, or one that is down, reports "
            "`available: false` with the reason. It never renders as an empty "
            "but healthy log pane."
        ),
        "node-06": (
            "node-06 is offline and has no log source. node-01 is served over the "
            "container network rather than a host port - ufw blocks a container "
            "from reaching node-01's own published ports."
        ),
    }
