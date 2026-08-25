"""The exporter emits exactly the names five alert rules reference, in their units.

WP-55 (P2.64 / P2.62). WorkerDown, DLQHighCount and JobFailureRateHigh are
severity critical and had no metric behind them at all — the fleet had no
page-on-call coverage for a dead worker, a filling DLQ, or a job-failure spike.
This module pins the contract between `app/api/v1/metrics.py` and
`ivgs-infra/configs/prometheus/alert_rules.yml`.

The contract is a set of exact strings. A metric renamed here, or a `_total`
suffix lost to a prometheus_client upgrade, silently returns those alerts to the
inert state WP-54 spent a package measuring — and the inert state looks exactly
like the healthy one. So the names are asserted literally, not derived.

Units are asserted too, because the unit is where this goes wrong. WP-54 found
`GPUUtilizationLow` needed a unit change as well as a rename: a ratio metric
against a percent threshold would have produced an alert that could never stop
firing, and it looked correct on the day because an idle fleet reads 0 either
way.
"""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.api.v1 import metrics as metrics_mod

pytestmark = pytest.mark.asyncio


def _render(db: dict, workers: list) -> dict[str, float]:
    """Exposition output as {series_line_without_value: value}."""
    registry = CollectorRegistry()

    class _S:
        def collect(self):
            yield from metrics_mod._families(db, workers)

    registry.register(_S())
    out: dict[str, float] = {}
    for line in generate_latest(registry).decode().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, _, value = line.rpartition(" ")
        out[name] = float(value)
    return out


FULL_DB = {
    "dlq_pending": 12,
    "jobs_total": 35,
    "jobs_failed": 19,
    "segments_pending": 7,
    "quotas": [("user", "u-1", 900, 1000)],
}
FULL_WORKERS = [
    ("default-worker@node01", "node-01", 1_787_600_000.0),
    ("cogvideox-worker@node03", "node-03", 1_787_600_001.0),
]


async def test_every_name_an_alert_rule_references_is_emitted():
    """The five rules name seven metrics. All seven, spelled exactly."""
    rendered = _render(FULL_DB, FULL_WORKERS)
    names = {line.split("{")[0] for line in rendered}

    for required in (
        "ivgs_worker_last_heartbeat_timestamp",  # WorkerDown
        "ivgs_dlq_message_count",                # DLQHighCount
        "ivgs_pipeline_jobs_total",              # JobFailureRateHigh
        "ivgs_pipeline_jobs_failed_total",       # JobFailureRateHigh
        "ivgs_render_queue_pending_segments",    # RenderQueueBacklog
        "ivgs_user_storage_used_bytes",          # StorageQuotaAlert
        "ivgs_user_storage_quota_bytes",         # StorageQuotaAlert
    ):
        assert required in names, (
            f"{required} is referenced by an alert rule and is not emitted. "
            f"That rule is inert again, and an inert rule is indistinguishable "
            f"from a healthy one."
        )


async def test_the_counter_suffix_survives():
    """`_total` is added by prometheus_client, not written in the source.

    `CounterMetricFamily("ivgs_pipeline_jobs", ...)` exposes
    `ivgs_pipeline_jobs_total`. That suffix is a library convention, so it is
    pinned here rather than trusted: JobFailureRateHigh references the suffixed
    name and would match nothing without it.
    """
    names = {line.split("{")[0] for line in _render(FULL_DB, FULL_WORKERS)}
    assert "ivgs_pipeline_jobs_total" in names
    assert "ivgs_pipeline_jobs_failed_total" in names
    assert "ivgs_pipeline_jobs" not in names


async def test_units_match_the_thresholds_the_rules_compare_against():
    """Each value is in the unit its rule's threshold is written in."""
    rendered = _render(FULL_DB, FULL_WORKERS)

    # WorkerDown: `time() - metric > 300`. Both sides unix SECONDS.
    hb = rendered['ivgs_worker_last_heartbeat_timestamp{node="node-01",worker_id="default-worker@node01"}']
    assert hb == 1_787_600_000.0
    assert 1e9 < hb < 4e9, "not a unix timestamp in seconds"

    # DLQHighCount: `> 10`. A COUNT, passed through unscaled.
    assert rendered["ivgs_dlq_message_count"] == 12

    # RenderQueueBacklog: `> 20`. A COUNT.
    assert rendered["ivgs_render_queue_pending_segments"] == 7

    # JobFailureRateHigh divides the two counters and scales by 100, so the
    # 10 threshold is 10 PERCENT. Counts here; the percent is the rule's.
    assert rendered["ivgs_pipeline_jobs_total"] == 35
    assert rendered["ivgs_pipeline_jobs_failed_total"] == 19

    # StorageQuotaAlert: `(used/quota)*100 > 80`. BYTES on both sides.
    used = rendered['ivgs_user_storage_used_bytes{entity_type="user",user_id="u-1"}']
    quota = rendered['ivgs_user_storage_quota_bytes{entity_type="user",user_id="u-1"}']
    assert (used / quota) * 100 == 90.0


async def test_workers_are_distinguishable_not_a_fleet_count():
    """WorkerDown must say WHICH worker died.

    node-03's worker runs under a different service name from 02 and 04
    (`cogvideox-worker`, not `celery-worker`), so a fleet-wide count would not
    only fail to name the casualty, it would hide that the fleet is not
    homogeneous.
    """
    rendered = _render(FULL_DB, FULL_WORKERS)
    series = [k for k in rendered if k.startswith("ivgs_worker_last_heartbeat_timestamp")]
    assert len(series) == 2
    assert any('worker_id="cogvideox-worker@node03"' in s for s in series)
    assert any('node="node-03"' in s for s in series)


async def test_a_broken_query_omits_the_series_rather_than_reporting_zero():
    """A failed collection must not look like an empty queue.

    `_collect_db` returns None for anything it could not read. Emitting 0 there
    would make a broken query indistinguishable from a healthy system with
    nothing in the DLQ — the exact substitution this whole line of work exists
    to remove. The series is omitted instead, and the rule goes to no-data,
    which the WP-54 gate reports as a rule that cannot fire.
    """
    broken = {
        "dlq_pending": None,
        "jobs_total": None,
        "jobs_failed": None,
        "segments_pending": None,
        "quotas": None,
    }
    names = {line.split("{")[0] for line in _render(broken, [])}
    assert "ivgs_dlq_message_count" not in names
    assert "ivgs_pipeline_jobs_total" not in names
    assert "ivgs_render_queue_pending_segments" not in names


async def test_a_zero_quota_ceiling_is_not_emitted():
    """The rule divides by the ceiling; a zero would be a division by zero."""
    db = dict(FULL_DB, quotas=[("user", "u-zero", 500, 0)])
    rendered = _render(db, [])
    assert 'ivgs_user_storage_used_bytes{entity_type="user",user_id="u-zero"}' in rendered
    assert 'ivgs_user_storage_quota_bytes{entity_type="user",user_id="u-zero"}' not in rendered


async def test_the_endpoint_is_registered_unauthenticated():
    """Prometheus scrapes it without a token, like /health."""
    paths = [r.path for r in metrics_mod.router.routes]
    assert "/metrics" in paths
    route = next(r for r in metrics_mod.router.routes if r.path == "/metrics")
    assert not getattr(route, "dependencies", []), (
        "the scrape endpoint must not require auth; Prometheus sends no token"
    )
