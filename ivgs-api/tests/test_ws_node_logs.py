"""
WS node-log streaming — REMOVED, and pinned removed (WP-48-TELEMETRY, 2026-08-25).

WHAT THIS FILE USED TO BE. Eight tests over `WS /api/v1/ws/nodes/{node_id}/logs`:
SSH subprocess output streaming, service filter, tail parameter, process cleanup
on disconnect, SSH failure handling. Every one of them passed. Every one of them
patched `asyncio.create_subprocess_shell`.

WHY THAT MATTERED. The handler ran `ssh <node_ip> 'docker compose logs --follow'`
from inside `ivgs-fastapi`, and that container has no `ssh` binary, no key and no
`docker` CLI — measured in the running container 2026-08-25:

    $ docker exec ivgs-fastapi sh -c 'command -v ssh; command -v docker'
    (both empty)

So in production the subprocess exited immediately, `readline()` returned empty,
the loop broke, and the socket closed having sent nothing — without raising. The
Node Monitor's log pane was blank on every node since the page shipped. These
tests could not have caught that, because mocking the subprocess mocks away the
only thing that was broken. They pinned the shape of a handler that never ran.

That is the failure mode ledger P2.22 named — a test that freezes a stub — and
the swallow shape of WP-00-SWALLOWED-FAILURES: a failure that renders as silence.

WHAT REPLACES IT. `ivgs-api/tests/test_wp48_telemetry.py`, against
`app/core/node_logs.py` and the real `ivgs-node-logs` source on each node:
Docker frame demux, ANSI stripping, nullable level inference, path-traversal
refusal, and — the part that matters here — an unreachable node reporting a
*reason* rather than an empty line list.

This file is kept, rather than deleted, so the removal is visible in the tree and
cannot quietly regress.
"""


def test_the_ssh_based_node_log_route_is_gone():
    """No route in ws_logs may serve node logs.

    If this fails, something re-added a node-log WebSocket. Before doing that,
    read the module docstring above: the endpoint the UI advertised
    (`/api/v1/nodes/{id}/logs/stream`) never existed at all, and the one that did
    could not reach a node. Node logs are `GET /api/v1/nodes/{node_id}/logs`.
    """
    from app.api.v1 import ws_logs

    assert not hasattr(ws_logs, "stream_node_logs")
    paths = [getattr(r, "path", "") for r in ws_logs.router.routes]
    assert not any("nodes" in p and "logs" in p for p in paths), paths


def test_job_status_streaming_is_untouched():
    """The other WebSocket in this module is real and stays."""
    from app.api.v1 import ws_logs

    assert hasattr(ws_logs, "stream_job_status")
    paths = [getattr(r, "path", "") for r in ws_logs.router.routes]
    assert any("jobs" in p and "status" in p for p in paths), paths


def test_the_replacement_is_reachable_and_honest_about_unknown_nodes():
    """The HTTP replacement exists and refuses an unregistered node by name."""
    from app.core.node_logs import list_containers

    out = list_containers("node-99")
    assert out["available"] is False
    assert out["containers"] == []
    assert "no registry entry" in out["reason"]
