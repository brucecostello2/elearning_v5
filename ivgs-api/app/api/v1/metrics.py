"""Prometheus exporter — the metrics five alert rules have always referenced.

WP-55 (ledger P2.64, and WP-53's P2.62). WP-54 measured all twelve alert rules
against the metric names Prometheus actually holds and found five INERT: their
metrics are produced by nothing and appear nowhere in the tree. They were
written against §13.1 Table 13-3 — the design — and the exporters were never
built. Three of the five are severity **critical**, so the fleet has had no
page-on-call coverage for a dead worker, a filling DLQ, or a job-failure spike.

This module emits exactly those metrics and nothing else. It is not a metrics
framework: every series here exists because a specific rule references it by
name, and the rule's threshold was checked against this metric's unit.

    ivgs_worker_last_heartbeat_timestamp   unix SECONDS   WorkerDown
    ivgs_dlq_message_count                 COUNT          DLQHighCount
    ivgs_pipeline_jobs_total               COUNT          JobFailureRateHigh
    ivgs_pipeline_jobs_failed_total        COUNT          JobFailureRateHigh
    ivgs_render_queue_pending_segments     COUNT          RenderQueueBacklog
    ivgs_user_storage_used_bytes           BYTES          StorageQuotaAlert
    ivgs_user_storage_quota_bytes          BYTES          StorageQuotaAlert

UNITS ARE STATED BECAUSE THE UNIT IS WHERE THIS GOES WRONG. WP-54 found
`GPUUtilizationLow` needed a unit change as well as a rename: the exporter
emitted a RATIO and the rule was written in PERCENT, so a bare rename would have
produced an alert that could never stop firing — and it would have looked
correct on the day, because an idle fleet reads 0 either way. Each metric below
names its unit, and the matching rule's threshold is in the same one:

    WorkerDown         time() - ts > 300      both unix seconds
    DLQHighCount       count > 10             both counts
    JobFailureRateHigh (rate/rate)*100 > 10   ratio scaled to percent
    RenderQueueBacklog count > 20             both counts
    StorageQuotaAlert  (used/quota)*100 > 80  bytes/bytes scaled to percent

VALUES ARE READ AT SCRAPE TIME, FROM THE DATABASE, NOT ACCUMULATED IN PROCESS.
That is deliberate for the two `_total` counters. An in-process counter resets
to zero whenever the API restarts, which `rate()` handles as a counter reset but
which also means the API's uptime silently becomes part of the measurement. A
count read from `render_jobs` is the same number before and after a restart,
and it is the number an operator would get by querying the table themselves.

NOT AUTHENTICATED, consistent with `/api/v1/health`. Prometheus scrapes it over
the compose network; the endpoint exposes counts and one per-user byte figure,
no content and no secrets. Worth knowing that the API's port is published on
192.168.1.90, so this is reachable from the LAN — flagged in the WP-55 report
rather than silently accepted.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterable

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from sqlalchemy import text
from starlette.responses import Response

from shared.database import async_session_factory

logger = logging.getLogger("ivgs.api.metrics")

router = APIRouter(tags=["Metrics"])

#: Written by every worker's liveness beacon (ivgs-workers/utils/liveness.py).
LIVENESS_KEY = "ivgs:worker_last_seen"


async def _scalar(session, sql: str) -> int:
    result = await session.execute(text(sql))
    return int(result.scalar() or 0)


async def _collect_db() -> dict:
    """One session, five cheap aggregate queries.

    Every failure is reported as a failure, not as a zero. A metric that reads
    0 because the query broke is indistinguishable from a metric that reads 0
    because there is nothing there — which is the exact defect this package
    exists to remove, so the counts come back as None and the series is simply
    not emitted.
    """
    out: dict = {
        "dlq_pending": None,
        "jobs_total": None,
        "jobs_failed": None,
        "segments_pending": None,
        "quotas": None,
    }
    try:
        async with async_session_factory() as session:
            out["dlq_pending"] = await _scalar(
                session,
                "SELECT count(*) FROM dead_letter_messages WHERE resolution IS NULL",
            )
            out["jobs_total"] = await _scalar(
                session, "SELECT count(*) FROM render_jobs"
            )
            out["jobs_failed"] = await _scalar(
                session,
                "SELECT count(*) FROM render_jobs WHERE status = 'failed'",
            )
            out["segments_pending"] = await _scalar(
                session,
                "SELECT count(*) FROM render_segments WHERE status = 'pending'",
            )
            rows = (
                await session.execute(
                    text(
                        "SELECT entity_type, entity_id::text, current_bytes, max_bytes "
                        "FROM storage_quotas"
                    )
                )
            ).all()
            out["quotas"] = [tuple(r) for r in rows]
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("metrics_db_collection_failed error=%s", exc)
    return out


async def _collect_workers() -> list[tuple[str, str, float]]:
    """(worker_id, node, last_seen_unix_seconds) for every worker ever seen.

    Read from Redis rather than asked of the workers. `celery inspect ping`
    from this container answers for one worker in five (measured 2026-08-25),
    and a critical alert built on that would have reported four healthy workers
    as dead. The beacon writes; this reads.

    A dead worker keeps its entry, with a timestamp that stops advancing. That
    is what lets `time() - ts > 300` fire at all — see the module docstring in
    ivgs-workers/utils/liveness.py.
    """
    try:
        import redis.asyncio as aioredis

        from shared.config import settings

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            raw = await client.hgetall(LIVENESS_KEY)
        finally:
            await client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_worker_liveness_read_failed error=%s", exc)
        return []

    workers: list[tuple[str, str, float]] = []
    for worker_id, blob in (raw or {}).items():
        try:
            rec = json.loads(blob)
            workers.append(
                (worker_id, str(rec.get("node", "unknown")), float(rec["ts"]))
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            logger.warning("metrics_worker_liveness_entry_unreadable id=%s", worker_id)
    return workers


def _families(db: dict, workers: Iterable[tuple[str, str, float]]):
    """Build the exposition families. Nothing here invents a value."""

    # --- WorkerDown -------------------------------------------------------
    hb = GaugeMetricFamily(
        "ivgs_worker_last_heartbeat_timestamp",
        "Unix timestamp (seconds) when this Celery worker last reported alive.",
        labels=["worker_id", "node"],
    )
    for worker_id, node, ts in workers:
        hb.add_metric([worker_id, node], ts)
    yield hb

    # --- DLQHighCount -----------------------------------------------------
    if db["dlq_pending"] is not None:
        yield GaugeMetricFamily(
            "ivgs_dlq_message_count",
            "Dead-letter messages awaiting an operator decision (resolution IS NULL).",
            value=db["dlq_pending"],
        )

    # --- JobFailureRateHigh ----------------------------------------------
    # Counters, and monotonic in practice: render_jobs rows are inserted and
    # their status only moves forward. Read from the table so an API restart
    # does not reset them.
    if db["jobs_total"] is not None:
        yield CounterMetricFamily(
            "ivgs_pipeline_jobs",
            "Render jobs created, all time.",
            value=db["jobs_total"],
        )
    if db["jobs_failed"] is not None:
        yield CounterMetricFamily(
            "ivgs_pipeline_jobs_failed",
            "Render jobs in status 'failed', all time.",
            value=db["jobs_failed"],
        )

    # --- RenderQueueBacklog ----------------------------------------------
    if db["segments_pending"] is not None:
        yield GaugeMetricFamily(
            "ivgs_render_queue_pending_segments",
            "Render segments in status 'pending'.",
            value=db["segments_pending"],
        )

    # --- StorageQuotaAlert -----------------------------------------------
    if db["quotas"] is not None:
        used = GaugeMetricFamily(
            "ivgs_user_storage_used_bytes",
            "Bytes currently attributed to this quota holder.",
            labels=["entity_type", "user_id"],
        )
        limit = GaugeMetricFamily(
            "ivgs_user_storage_quota_bytes",
            "Byte ceiling for this quota holder.",
            labels=["entity_type", "user_id"],
        )
        for entity_type, entity_id, current_bytes, max_bytes in db["quotas"]:
            used.add_metric([entity_type, entity_id], float(current_bytes or 0))
            # A zero ceiling would make the rule's (used/quota) a division by
            # zero; skip it rather than emit a series that cannot be divided.
            if max_bytes:
                limit.add_metric([entity_type, entity_id], float(max_bytes))
        yield used
        yield limit


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Scrape endpoint. Values are read now, not remembered."""
    started = time.monotonic()
    db = await _collect_db()
    workers = await _collect_workers()

    registry = CollectorRegistry()

    class _Snapshot:
        def collect(self):
            yield from _families(db, workers)
            # How long this scrape took to assemble. Not for an alert -- for
            # the person who eventually asks why the API got slow.
            dur = GaugeMetricFamily(
                "ivgs_api_metrics_collection_seconds",
                "Seconds spent assembling this scrape.",
            )
            dur.add_metric([], time.monotonic() - started)
            yield dur

    registry.register(_Snapshot())
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
