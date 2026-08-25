"""An alert rule that references a metric nothing produces is not an alert.

WP-54. Three instances of one shape have now been found in this system:

  * a backup task returning ``{'status': 'failed'}`` that Celery recorded as
    SUCCESS (fixed 2026-08-14),
  * a quality gate that could not fail an asset (WP-44),
  * ``GPUOvertemperature`` — severity critical, page-on-call — matching two
    metric names no exporter on this fleet emits (WP-53, found by accident
    while doing something else).

The shape: a mechanism that is present, configured, and INERT, where the inert
state and the healthy state produce identical evidence. A rule matching nothing
looks exactly like a rule whose condition is not met. Nobody notices, because
nothing is wrong on the surface — and that is the whole problem.

WP-54 measured all twelve rules and found five inert, three of them critical.
This module is the gate that stops a sixth arriving unnoticed.

WHY IT ASSERTS AGAINST LIVE PROMETHEUS AND NOT A FIXTURE
--------------------------------------------------------
The defect is a mismatch between what the rules NAME and what the fleet
PRODUCES. A fixture would be a third statement of what someone believed the
metric names were, which is the thing that was already wrong three times over.
Only the running instance knows. This is the same principle as WP-45's
broker-message assertions: assert the mechanism can act, not that it returned a
success code.

WHY THERE IS AN EXEMPTION LIST AND WHY IT IS NOT A SKIP MARKER
---------------------------------------------------------------
Five rules are inert TODAY and must not be deleted — deleting them would remove
the only record that the fleet is supposed to watch those things, which is the
gap-hiding move this package exists to prevent. They are listed below with what
is missing and a ledger id, and `test_no_exemption_has_quietly_become_available`
makes the list self-expiring: the moment someone ships the exporter, the
exemption fails and has to be removed. An exemption that could outlive its cause
would be a skip marker wearing a better hat.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from tests_system.service_urls import PROMETHEUS_URL

REPO_ROOT = Path(__file__).resolve().parents[1]
RULE_FILES = [REPO_ROOT / "ivgs-infra" / "configs" / "prometheus" / "alert_rules.yml"]

# ---------------------------------------------------------------------------
# Ledgered exemptions — rules kept deliberately with no metric behind them.
#
# Each entry is {alert name: (missing metric names, ledger id)}. Measured
# 2026-08-25: none of these names is produced by any target, and none appears
# anywhere in the IVGS tree either — they were written against §13.1 Table 13-3,
# the design, and nothing was ever built to emit them. The data exists in
# Postgres in every case; the gap is an exporter, and its root cause is shared
# with P2.62 (ivgs-api serves no /metrics endpoint at all).
#
# To retire an entry: ship the metric, then delete the line. Do not delete the
# line to make this file green.
# ---------------------------------------------------------------------------
KNOWN_INERT: dict[str, tuple[tuple[str, ...], str]] = {
    "WorkerDown": (("ivgs_worker_last_heartbeat_timestamp",), "P2.64"),
    "DLQHighCount": (("ivgs_dlq_message_count",), "P2.64"),
    "JobFailureRateHigh": (
        ("ivgs_pipeline_jobs_failed_total", "ivgs_pipeline_jobs_total"),
        "P2.64",
    ),
    "RenderQueueBacklog": (("ivgs_render_queue_pending_segments",), "P2.64"),
    "StorageQuotaAlert": (
        ("ivgs_user_storage_used_bytes", "ivgs_user_storage_quota_bytes"),
        "P2.64",
    ),
}

# PromQL keywords, aggregation operators and functions. Anything matching one of
# these is not a metric name. Kept explicit rather than clever: a regex that
# tried to be smart here would be one more thing asserting what it believes.
_NOT_METRICS = {
    "abs", "absent", "absent_over_time", "and", "atan2", "avg", "avg_over_time",
    "bool", "bottomk", "by", "ceil", "changes", "clamp", "clamp_max",
    "clamp_min", "count", "count_over_time", "count_values", "day_of_month",
    "day_of_week", "days_in_month", "delta", "deriv", "exp", "floor", "group",
    "group_left", "group_right", "histogram_quantile", "hour", "idelta",
    "ignoring", "increase", "irate", "label_join", "label_replace", "last_over_time",
    "ln", "log10", "log2", "max", "max_over_time", "min", "min_over_time",
    "minute", "month", "offset", "on", "or", "predict_linear", "present_over_time",
    "quantile", "quantile_over_time", "rate", "resets", "round", "scalar",
    "sgn", "sort", "sort_desc", "sqrt", "stddev", "stdvar", "sum", "sum_over_time",
    "time", "timestamp", "topk", "unless", "vector", "without", "year",
}

_IDENT = re.compile(r"\b[a-zA-Z_:][a-zA-Z0-9_:]*\b")
_LABEL_SELECTOR = re.compile(r"\{[^}]*\}")
_GROUPING = re.compile(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)")


def metric_names(expr: str) -> set[str]:
    """Metric names referenced by a PromQL expression.

    Label selectors and `by (...)` / `on (...)` groupings are stripped first,
    so label names never masquerade as metrics — `avg by (instance, node)`
    would otherwise contribute two phantom "absent metrics" and make this gate
    cry wolf on a rule that is perfectly healthy.
    """
    stripped = _LABEL_SELECTOR.sub(" ", expr)
    stripped = _GROUPING.sub(" ", stripped)
    return {
        tok
        for tok in _IDENT.findall(stripped)
        if tok not in _NOT_METRICS and not tok[0].isdigit()
    }


def load_rules() -> list[tuple[str, str, str]]:
    """Every alerting rule as (alert name, severity, expression)."""
    out: list[tuple[str, str, str]] = []
    for path in RULE_FILES:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for group in doc.get("groups", []):
            for rule in group.get("rules", []):
                if "alert" not in rule:
                    continue  # recording rules have no alert name
                out.append(
                    (
                        rule["alert"],
                        (rule.get("labels") or {}).get("severity", "unset"),
                        rule.get("expr", ""),
                    )
                )
    return out


def produced_metric_names() -> set[str]:
    """Metric names the live Prometheus currently holds.

    Skips — loudly — rather than passing when Prometheus is unreachable. A
    silent pass here would be this module committing the exact defect it exists
    to catch.
    """
    url = f"{PROMETHEUS_URL}/api/v1/label/__name__/values"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = json.load(resp)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        pytest.skip(
            f"Prometheus unreachable at {PROMETHEUS_URL} ({exc}). This gate "
            f"asserts against the LIVE metric set on purpose; it cannot run "
            f"without it, and it will not pass by pretending otherwise. "
            f"Set IVGS_TEST_PROMETHEUS_URL if it is published elsewhere."
        )
    if body.get("status") != "success":
        pytest.fail(f"Prometheus returned status={body.get('status')!r} for {url}")
    return set(body["data"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_the_rule_files_parse_and_contain_alerts():
    """A guard on the guard: an empty parse would make every check below vacuous."""
    rules = load_rules()
    assert rules, f"no alerting rules found in {[str(p) for p in RULE_FILES]}"
    assert len(rules) >= 12, f"expected at least 12 rules, parsed {len(rules)}"


def test_every_alert_rule_metric_is_produced():
    """No rule may reference a metric name no target produces.

    This is the gate. A new rule written against a metric that does not exist —
    the GPUOvertemperature defect — fails here instead of sitting inert for
    however long it takes someone to notice by accident.
    """
    produced = produced_metric_names()

    offenders: list[str] = []
    for name, severity, expr in load_rules():
        missing = sorted(m for m in metric_names(expr) if m not in produced)
        if not missing:
            continue
        exempt = KNOWN_INERT.get(name)
        if exempt is not None and set(missing) <= set(exempt[0]):
            continue
        offenders.append(
            f"  {name} [{severity}] references {missing}, produced by no target"
        )

    assert not offenders, (
        "Alert rules reference metrics that nothing on this fleet produces.\n"
        "Such a rule can never fire, and an alert that cannot fire is "
        "indistinguishable from one whose condition is not met.\n\n"
        + "\n".join(offenders)
        + "\n\nEither correct the metric name against the live set, or — if no "
        "equivalent metric exists — add the rule to KNOWN_INERT in this file "
        "with a ledger id, so the monitoring gap is recorded rather than hidden."
    )


def test_no_exemption_has_quietly_become_available():
    """An exemption must expire the moment its metric exists.

    Without this, KNOWN_INERT would rot into a permanent allowlist — a skip
    marker with better manners. If someone ships the exporter, the rule starts
    working and this test demands the exemption be deleted.
    """
    produced = produced_metric_names()

    resolved: list[str] = []
    for alert, (metrics, ledger) in KNOWN_INERT.items():
        now_present = sorted(m for m in metrics if m in produced)
        if now_present:
            resolved.append(f"  {alert} ({ledger}): {now_present} now produced")

    assert not resolved, (
        "These metrics now exist, so their rules are no longer inert.\n"
        "Remove the entries from KNOWN_INERT and close the ledger item — the "
        "exemption has served its purpose.\n\n" + "\n".join(resolved)
    )


def test_every_exemption_names_a_rule_that_still_exists():
    """Static, and runs with no Prometheus.

    Catches the other direction of rot: an exemption left behind after its rule
    was renamed or removed, which would silently stop covering anything while
    still reading like a considered decision.
    """
    rule_names = {name for name, _, _ in load_rules()}
    orphans = sorted(set(KNOWN_INERT) - rule_names)
    assert not orphans, (
        f"KNOWN_INERT exempts rules that no longer exist in the rule files: "
        f"{orphans}. Delete the entries."
    )


def test_every_exemption_carries_a_ledger_id():
    """A gap without an id is a gap nobody is accountable for."""
    for alert, (metrics, ledger) in KNOWN_INERT.items():
        assert metrics, f"{alert}: exemption lists no missing metric"
        assert re.fullmatch(r"[A-Z]\d+(\.\d+)*", ledger), (
            f"{alert}: {ledger!r} is not a ledger id"
        )
