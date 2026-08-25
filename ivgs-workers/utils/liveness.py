"""Worker liveness beacon — the source `WorkerDown` never had.

WP-55 (ledger P2.64). `WorkerDown` is severity critical and page-on-call. Its
metric, ``ivgs_worker_last_heartbeat_timestamp``, has never existed, so the
fleet has had no alerting coverage for a dead worker at all. This module is the
half of the repair that lives on the worker; ``ivgs-api``'s ``/metrics``
endpoint reads what it writes.

WHY NOT THE THREE THINGS THAT ALREADY LOOK LIKE THIS
-----------------------------------------------------
Each was tried and rejected on measurement, not taste:

1. ``worker_heartbeats`` (the table the schema was designed around) has **0
   rows** and nothing writes it. Its supposed supervisor,
   ``pipeline_orchestrator.supervise_worker_heartbeats``, does not read or write
   that table either — it polls the GPU scheduler's ``/fleet``, whose registry
   is itself unreliable (P2.46).

2. ``gpu_utils.start_heartbeat_loop`` exists and is started from
   ``worker_ready`` — but only when ``register_node()`` returns a node id, which
   it does not for a worker with no GPU identity. node-01's ``default-worker``
   and ``composition-worker`` therefore never heartbeat at all, and it reports
   to the same empty scheduler registry.

3. Celery's own pidbox broadcast (``inspect ping``). It works from inside a
   worker container — all five workers answer — and does NOT work from the API:
   measured 2026-08-25 from ``ivgs-fastapi`` with the workers' exact
   ``broker_transport_options``, ``control.ping()`` returned **1 of 5** workers,
   repeatedly, at 2 s and 6 s timeouts. Building a critical alert on a
   broadcast that silently answers for one worker in five would have produced
   four permanently-dead-looking workers, which is worse than no metric.

So the worker asserts its own liveness, unconditionally, to a store the API can
read. No GPU identity required, no scheduler involved, no broadcast.

WHY IT MUST BE A LAST-SEEN TIMESTAMP AND NOT AN UP/DOWN FLAG
--------------------------------------------------------------
``WorkerDown`` is ``time() - ivgs_worker_last_heartbeat_timestamp > 300``. That
only fires while the SERIES STILL EXISTS and its value is stale. If a dead
worker's series simply vanished, Prometheus would drop it after ~5 minutes of
staleness and the alert would never fire — the death would erase the evidence
of the death. Writing a durable last-seen value per worker means a dead
worker's timestamp stops advancing while the series stays, ``time() - ts``
grows past 300, and the alert fires. That is the whole reason for the shape.

Entries carry a long TTL so a worker that is decommissioned rather than dead
eventually disappears — but only long after it would have alerted.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

import structlog

logger = structlog.get_logger("ivgs.worker.liveness")

#: Redis hash: field = celery worker hostname, value = JSON {ts, node}.
LIVENESS_KEY = "ivgs:worker_last_seen"

#: How often each worker refreshes its own field. Well under WorkerDown's 300 s
#: threshold, so a single missed write can never look like a death.
DEFAULT_INTERVAL_SECONDS = 15

#: A worker that has not written for this long is not dead, it is gone: its
#: field is dropped so a decommissioned worker does not alert forever. Far
#: longer than the alert threshold, so a death always alerts before it expires.
STALE_AFTER_SECONDS = 7 * 24 * 3600

_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def node_label(worker_id: str, configured: str) -> str:
    """The stable node name for this worker.

    `WorkerConfig.node_hostname` falls back to the CONTAINER hostname when
    `IVGS_NODE_NAME` is unset — a 12-character hex id that changes on every
    recreate. node-01's workers have no `IVGS_NODE_NAME`, so the first cut of
    this beacon labelled them `2807c417948c` and `12f7e72c557b`. That is the
    same defect `config.py:282` documents for the GPU scheduler registry, where
    it produced 21 "nodes" on a fleet of three, reappearing in a new metric.

    Celery's worker hostname already carries the node after the `@` and is set
    from compose, so it is preferred over a hex id. Normalised to the
    `node-0N` spelling every other label in Prometheus uses, so the `node`
    label joins across jobs instead of nearly-joining.
    """
    if configured and not _looks_like_container_id(configured):
        return _normalise(configured)
    if "@" in worker_id:
        return _normalise(worker_id.rsplit("@", 1)[1])
    return _normalise(configured or "unknown")


def _looks_like_container_id(value: str) -> bool:
    return len(value) == 12 and all(c in "0123456789abcdef" for c in value.lower())


def _normalise(value: str) -> str:
    """`node01` -> `node-01`; anything else is returned unchanged."""
    import re as _re

    m = _re.fullmatch(r"node-?(\d{1,2})", value.strip().lower())
    return f"node-{int(m.group(1)):02d}" if m else value.strip()


def _redis_client():
    """A plain sync Redis client. Constructed per loop iteration is wasteful;
    constructed once and held is what a background thread wants."""
    import redis

    from shared.config import settings

    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def record_liveness(worker_id: str, node_hostname: str) -> bool:
    """Write one last-seen record. Returns True if it landed.

    Never raises: a broker hiccup must not take down a worker, and the alert
    itself is the thing that reports a sustained failure to write — a worker
    that cannot reach Redis stops advancing its timestamp and trips
    ``WorkerDown``, which is the correct outcome.
    """
    try:
        client = _redis_client()
        now = time.time()
        client.hset(
            LIVENESS_KEY,
            worker_id,
            json.dumps({"ts": now, "node": node_hostname}),
        )
        _prune(client, now)
        return True
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("worker_liveness_write_failed", error=str(exc))
        return False


def _prune(client, now: float) -> None:
    """Drop fields older than STALE_AFTER_SECONDS.

    Cheap: the hash holds one field per worker the fleet has ever run, which is
    single digits.
    """
    try:
        for field, raw in (client.hgetall(LIVENESS_KEY) or {}).items():
            try:
                ts = float(json.loads(raw).get("ts", 0))
            except (ValueError, TypeError, json.JSONDecodeError):
                client.hdel(LIVENESS_KEY, field)
                continue
            if now - ts > STALE_AFTER_SECONDS:
                client.hdel(LIVENESS_KEY, field)
                logger.info("worker_liveness_entry_expired", worker_id=field)
    except Exception as exc:  # noqa: BLE001
        logger.warning("worker_liveness_prune_failed", error=str(exc))


def _loop(worker_id: str, node_hostname: str, interval: int) -> None:
    node = node_label(worker_id, node_hostname)
    while not _stop.is_set():
        record_liveness(worker_id, node)
        _stop.wait(interval)


def start_liveness_beacon(
    worker_id: str,
    node_hostname: str,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> Optional[threading.Thread]:
    """Start the beacon. Idempotent; returns the thread, or None if already up."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return None
    _stop.clear()
    _thread = threading.Thread(
        target=_loop,
        args=(worker_id, node_hostname, interval_seconds),
        name="ivgs-worker-liveness",
        daemon=True,
    )
    _thread.start()
    logger.info(
        "worker_liveness_beacon_started",
        worker_id=worker_id,
        node=node_hostname,
        interval_seconds=interval_seconds,
    )
    return _thread


def stop_liveness_beacon() -> None:
    """Stop the beacon. Deliberately does NOT delete the worker's field.

    A clean shutdown still leaves the last-seen timestamp behind, so a worker
    that is stopped and not restarted trips ``WorkerDown`` five minutes later.
    Deleting the field on shutdown would make an intentional stop and a crash
    look identical from the outside, which is the whole class of defect WP-54
    was about.
    """
    _stop.set()
