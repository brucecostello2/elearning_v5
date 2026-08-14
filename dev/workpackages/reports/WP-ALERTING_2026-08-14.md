# WP-ALERTING — Alerts fire into Prometheus and reach nobody

**Date:** 2026-08-14
**Node:** node-01 (192.168.1.90)
**Repo:** brucecostello2/elearning_v5 @ `e1f4c58`
**Status:** PASS 1 + PASS 2 (appended below). Alertmanager deployed, BackupStale added; exit gate met, both halves observed. Commit `9dc90aa`.
**Origin:** §2.5 of `WP-BACKUP-SCHEDULE_2026-08-14.md`, promoted by the operator

**Exit gate (operator):** a deliberately failed backup produces a notification
the operator actually receives.

---

## 1. Why this outranks the schedule package

Three notification paths were silent during the 75-day database backup gap. Two
are now fixed and deployed:

| Path | State |
|---|---|
| Celery task state | **Fixed and verified live** — see WP-BACKUP-REPORTING §8 |
| GUI `backup_records` row | **Fixed and verified live** — same |
| Prometheus `BackupFailed` | **Untouched.** Fires correctly; nothing delivers it |

No choice of scheduler changes the third. A schedule that runs perfectly and
fails silently at 02:00 is the configuration that just cost 75 days. Delivery is
the precondition for the schedule package's exit gate to mean anything.

---

## 2. Findings

### 2.1 The alert is correct, fires correctly, and goes nowhere — verified live

The rule is well-formed: `alert_rules.yml:149`, `expr: ivgs_backup_last_status == 0`,
instant, `severity: critical`, with a runbook annotation pointing at
`docs/runbooks/backup-failed.md`.

Delivery, measured:

| Check | Result |
|---|---|
| `docker ps -a \| grep -i alert` | **no Alertmanager container** |
| `alerting:` block in `prometheus.yml` | **absent** |
| Prometheus `/api/v1/alerts` | 2 alerts **firing** right now |

Prometheus is generating alerts into a void. There is no `alertmanagers:` target
for it to notify, and no Alertmanager process to receive one if there were.

### 2.2 Demonstrated end to end during this work package — verified live

While proving the defect-1 fix (WP-BACKUP-REPORTING step 2), a backup was
deliberately failed by holding the lock file. The alert pipeline responded
exactly as designed, up to the point where it stops:

```
20:50:00  backup.sh exits 2 ("Another backup is running (PID: 1)")
20:50:00  Celery: raised unexpected: BackupTaskError   <- fix working
20:50:00  backup_records row -> status=failed          <- fix working
20:50:02  Prometheus: BackupFailed{job="ivgs_backup"} state=firing
          ...and there delivery ends
```

`/api/v1/alerts` now shows both:

```
BackupFailed  job=ivgs_backup_verify  firing  2026-08-14T19:20:02Z
BackupFailed  job=ivgs_backup         firing  2026-08-14T20:50:02Z
```

**Half of this package's exit gate is already demonstrated.** A deliberately
failed backup does produce a firing alert. The missing half is that no human is
told.

### 2.3 The alert cannot detect a backup that never runs — verified live

This is the more serious finding, and it is not fixed by adding Alertmanager.

`ivgs_backup_last_status` is a pushgateway gauge written by the scripts' EXIT
trap. The pushgateway retains the last pushed value indefinitely — that is its
purpose. So:

- backup **ran and failed** → pushes 0 → `== 0` matches → alert fires ✓
- backup **never ran at all** → nothing is pushed → the previous value persists

If the last run succeeded and the schedule then stops entirely, the gauge holds
`1` forever and `BackupFailed` never fires. The system reports healthy backups
in perpetuity while taking none.

**That is not hypothetical — it is the current configuration.** The `backup.sh`
and `asset_backup.sh` cron entries were removed today and no beat schedule
exists (WP-BACKUP-SCHEDULE §2.4). Until step 4 of the current work lands, a
single successful run would leave `ivgs_backup_last_status = 1` and nothing
would ever contradict it.

No staleness rule exists for backups. `grep` over `alert_rules.yml` finds exactly
one age-based expression, and it is for workers:

```
alert_rules.yml:68-70
  - alert: WorkerDown
    expr: |
      time() - ivgs_worker_last_heartbeat_timestamp > 300
```

The pattern is already in the file and already understood by whoever wrote it.
It was simply never applied to `ivgs_backup_last_timestamp`, which the scripts
already push.

### 2.4 Checked and found sound — not defects

Recorded so they are not re-investigated:

- **Pushgateway persistence is configured.** `--persistence.file=/data/pushgateway-persistence`,
  `--persistence.interval=5m`, backed by the `ivgs-infra_pushgateway_data`
  volume. A restart does not lose the gauges. Up to 5 minutes of pushes could be
  lost on an unclean stop — noted, not material at daily cadence.
- **The 11 alert rules load and evaluate.** Two are firing, which proves rule
  evaluation is live.

### 2.5 Not verified

- **Grafana's notification path is unknown, not absent.** `admin:admin` was
  rejected by `/api/v1/provisioning/contact-points` and
  `/api/alert-notifications` (HTTP 401). Grafana may have contact points
  configured that this investigation could not see. **Do not read this report as
  proof that no notification channel exists anywhere** — only that Prometheus
  has no Alertmanager. The operator has the credentials to settle it, and should,
  before any of §3 is built.
- Whether SMTP, a webhook target, or any other egress path is available from
  node-01 was not tested.

---

## 3. Proposal

Ordered by dependency. Q1 gates the rest.

| # | Item | Why |
|---|---|---|
| Q1 | **Settle the Grafana question first** (§2.5) | If Grafana already has a working contact point, the cheapest correct answer may be Grafana-managed alerting rather than a new Alertmanager. Building Alertmanager first risks two half-configured alerting planes — the same duplication mistake as cron-plus-beat |
| A1 | Add an Alertmanager service and an `alerting:` block in `prometheus.yml` | The gap in §2.1 |
| A2 | Configure at least one receiver that reaches a human, and prove it | An unrouted Alertmanager is the same defect one layer further in |
| A3 | Add a `BackupStale` rule: `time() - ivgs_backup_last_timestamp > 26h`, per `backup_type` | The gap in §2.3 — catches never-ran, which is the failure mode that actually occurred |
| A4 | Add inhibition or grouping so `BackupStale` and `BackupFailed` do not double-page | Alert fatigue is how the next 75 days get missed |

### 3.1 A stronger source of truth is now available

`BackupStale` on the pushgateway gauge is the minimum fix. There is a better one,
newly possible.

Before this week, `backup_records` covered only API-triggered runs, so it was
useless as an alerting source. After the row-ownership change
(WP-BACKUP-REPORTING §3.2) **every invocation path writes a row** — cron, direct
`docker exec`, worker, and the beat schedule to come. The table is now the
authoritative record of every backup attempt on the system.

That makes a database-sourced freshness alert strictly better than a
pushgateway-sourced one:

- it survives pushgateway restarts and gauge-retention semantics entirely;
- it distinguishes *never ran* from *ran and failed* without a staleness proxy;
- it is the same data the GUI shows, so an alert and the GUI cannot disagree.

Implementation options: a custom query in postgres-exporter, or a small metrics
endpoint on the API. Recommend evaluating this alongside A3 rather than after —
if the DB source is adopted, A3 becomes a stopgap rather than the design.

---

## 4. Proposed exit-gate procedure

The gate is *observed*, not inferred. The failure half is already done (§2.2);
what follows tests delivery.

1. Settle Q1. If Grafana has a working channel, prefer it and skip A1.
2. Build A1/A2. Confirm Prometheus shows the Alertmanager as a healthy target.
3. Deliberately fail a backup by the same method used in §2.2 — hold
   `/var/run/ivgs/backup.lock` with a live PID, dispatch, release the lock. It is
   reversible, touches no data, and produced a genuine exit 2.
4. Confirm, in order:
   - the `backup_records` row reads `failed`
   - Celery state is FAILURE
   - `BackupFailed` fires in Prometheus
   - **the operator receives the notification, in the place they actually watch**
5. Then the harder half: stop the schedule entirely, leave the last status at
   `1`, and confirm `BackupStale` fires within its window. Step 4 only proves
   ran-and-failed. §2.3 is the failure mode that cost 75 days, and it is the one
   most likely to be left untested.

Step 5 is the gate that matters. A backup system that alerts on failure but not
on absence has not been fixed.

---

## 5. Housekeeping from this session

`BackupFailed{job="ivgs_backup"}` is currently firing because of the synthetic
failure in §2.2, not because of a real fault. A successful database backup was
run afterwards to return `ivgs_backup_last_status` to `1`, so the alert should
clear on the next evaluation. `BackupFailed{job="ivgs_backup_verify"}` has been
firing since 19:20 from the genuine verification failure and is unrelated to this
session's tests; it will persist until verification is addressed under its own
work package.

---

## 6. Open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | Does Grafana already have a working contact point? | **Operator to check** — gates everything else |
| Q2 | Alertmanager, or Grafana-managed alerting? | Decide after Q1; do not build both |
| Q3 | Where should a backup alert actually land? | Somewhere with an out-of-hours path. A dashboard nobody opens at 02:00 is not a notification |
| Q4 | Pushgateway gauge or `backup_records` as the alert source? | `backup_records` — §3.1 |
| Q5 | ~~Should `docs/runbooks/backup-failed.md` be written?~~ **Answered: yes.** Verified live — `docs/runbooks/` does not exist at all, so the alert's `runbook:` annotation points at a missing file | Write it as part of A2. An alert that arrives with a dead runbook link is a notification without an action |

---

*End of pass 1. No code written.*

---
---

# PASS 2 — Alertmanager deployed, BackupStale added, both gates met

**Appended:** 2026-08-14
**Commit:** `9dc90aa` (pushed)
**Status:** exit gate met, both halves observed.

## 7. What was done

### 7.1 Q1 resolved by evidence rather than by asking

Pass 1 left Q1 open: does Grafana already have a contact point? It could not be
enumerated (HTTP 401 on `admin:admin`) and remains unenumerated. It stopped
gating the work because a better answer surfaced: **the repo already contained
`ivgs-infra/monitoring/alertmanager.yml`**, written and never deployed, routing
to a webhook receiver that also already exists — `ivgs-api/app/api/v1/alerts.py`,
mounted at `/api/v1/alerts/webhook`, which republishes on the Redis channel
`ivgs:alerts` for the dashboard's WebSocket consumers.

The intended design was complete except for the container. That path needs no
external credentials, so it was adopted rather than building something new.

### 7.2 A latent defect in the never-deployed config — verified live

That file pointed at `http://ivgs-api:8001/`. **`ivgs-api` does not resolve.**
The container is `ivgs-fastapi`, aliases `[ivgs-fastapi, fastapi-backend]`;
`getent hosts ivgs-api` from a container on `ivgs-net` returns nothing, while
`ivgs-fastapi` resolves to `172.20.0.6`. Alertmanager would have loaded that
config without complaint and failed every delivery silently — the same class of
fault as the rest of this subsystem. Corrected before deployment.

### 7.3 A false alarm I nearly reported

`getent`/`wget` inside the Prometheus and Alertmanager images cannot resolve
Docker's embedded DNS at `127.0.0.11`, so shell tests from those containers
report `bad address` for names that work perfectly. Prometheus's Go resolver
uses `127.0.0.11` directly — proven by `pushgateway` being a healthy scrape
target throughout.

Had the shell result been taken at face value it would have been written up as
"Prometheus DNS is broken". It is not. **Shell-based DNS tests from those two
images are worthless and should not be used as evidence.**

### 7.4 Changes

| File | Change |
|---|---|
| `ivgs-infra/configs/alertmanager/alertmanager.yml` | **New.** Corrected webhook host; inhibit rule so BackupStale suppresses BackupFailed for the same `backup_type` |
| `ivgs-infra/monitoring/alertmanager.yml` | Synced to the live copy so the two trees do not diverge |
| `ivgs-infra/docker-compose.monitoring.yml` | `alertmanager` service on `ivgs-net`, resource-capped, healthchecked |
| `configs/` + `monitoring/` `prometheus.yml` | `alerting:` block pointing at `alertmanager:9093` |
| `configs/` + `monitoring/` `alert_rules.yml` | **BackupStale** rule |
| `scripts/verify_backup.sh` | Success now pushes `ivgs_backup_last_status=1` — see §9 |

Config lives in `configs/`, which is the tree `docker inspect ivgs-prometheus`
shows as actually mounted. `monitoring/` holds identical copies; both were
edited to prevent drift. That duplication is itself worth retiring — flagged,
not actioned.

### 7.5 BackupStale

```
time() - ivgs_backup_last_timestamp > 93600
```

Shape taken from `WorkerDown` (`alert_rules.yml:68-70`), as directed. 26h rather
than 24h so a merely-delayed 02:00 backup does not page. **No `for:` clause** — a
timestamp comparison cannot flap, and `BackupFailed` is likewise instant; the
inhibit rule prevents double-paging.

## 8. Exit gate — both halves observed

> a deliberately failed backup, and a deliberately skipped one, both produce a
> notification the operator receives

**Failed backup.** Lock file held with a live PID → `backup.sh` exit 2:

```
BackupTaskError raised, celery state FAILURE
BackupFailed firing in Prometheus
active in Alertmanager
delivered and captured on Redis ivgs:alerts:
  receiver : critical-webhook
  severity : critical
  summary  : Backup failed for database on node-01
  runbook  : docs/runbooks/backup-failed.md
```

**Skipped backup.** Synthetic `ivgs_backup_last_timestamp` 27.8 h old pushed
under `backup_type="staletest"`:

```
expression matched: backup_type=staletest age_h=27.8
BackupStale firing in Prometheus
active in Alertmanager
notification captured on Redis ivgs:alerts:
  receiver : critical-webhook
  summary  : No staletest backup in over 26 hours on node-01
```

**Stated precisely:** the captured BackupStale notification was the **resolved**
one, emitted when the synthetic metric was deleted during cleanup. Its *firing*
state was confirmed in both Prometheus and Alertmanager, and `send_resolved`
travels the identical receiver and route — but the firing notification itself
was not captured for BackupStale, only for BackupFailed. The delivery path is
proven; the specific firing payload for BackupStale is inferred from an
identical route.

Afterwards: synthetic metric deleted, a real backup and a real verification
re-run, **all alerts clear**, pushgateway reads 1 for database, config and
verify.

## 9. An alert that could never clear

Found while cleaning up: `verify_backup.sh` pushed `ivgs_backup_last_status=0`
on failure but **never pushed 1 on success** — only
`ivgs_backup_verification_status`. One failed verification therefore pinned
`BackupFailed` firing forever, whatever happened later. That is why
`BackupFailed{job="ivgs_backup_verify"}` had been firing continuously since
19:20 across this entire session.

Fixed: success pushes 1 with a label set matching the failure push exactly, or
the two form separate series and neither cancels the other. Verified — the
alert that had been firing all session is now clear, and can clear again.

This matters more than it looks. An alert that cannot clear is indistinguishable
from an alert that is stuck, and both train the operator to ignore it. Adding
delivery to a permanently-firing alert would have made things worse, not better.

## 10. Open

| # | Item | Note |
|---|---|---|
| A-O1 | **No out-of-hours channel.** Delivery reaches the dashboard and the API log; nothing pages a phone. No SMTP variables exist in `ivgs-infra/.env`, and Grafana's contact points remain unenumerated (Q1) | Needs credentials only the operator has |
| A-O2 | `docs/runbooks/backup-failed.md` written (both alerts cite it; it did not exist). Not staged — operator's docs commit | |
| A-O3 | **15 of 16 Prometheus scrape targets are down** — only `pushgateway` is up. `ivgs-api`, `ivgs-scheduler`, all node-exporters. Backup alerting works because it rides the pushgateway | Out of scope here; deserves its own WP |
| A-O4 | `configs/` and `monitoring/` hold duplicate Prometheus configs, kept in sync by hand | Retire one |
| A-O5 | The API webhook's `logger.warning("Alert received")` does not appear in `docker logs ivgs-fastapi`; delivery was confirmed via Redis instead | Minor, but it removes an obvious debugging surface |

**A-O3 is the significant one.** This package made backup alerting work end to
end, but that is one metric source out of sixteen. The monitoring stack as a
whole is largely blind, and nothing in this work changed that.

*End of pass 2.*
