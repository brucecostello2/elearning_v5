# WP-54-SILENT-ALARMS — every alert rule checked against the metrics that exist

**Date:** 2026-08-25 · **Node:** node-01 only · **Status:** complete, committed, HELD

| | |
|---|---|
| **Commits** | 4, held on `main`, nothing pushed |
| **Zero new failures** | confirmed against the corrected baseline, all five trees |
| **Inert alert rules found** | **5 of 12 — 3 of them CRITICAL** |
| **Repaired** | 2 rules, both now FIRING on real conditions |
| **Phantom imports** | 14 → **0 unexplained**; 9 repaired, 5 recorded with a ledger id |
| **Nodes visited** | none. node-03, node-05 and .62 untouched |
| **Deploy** | none needed — rule changes applied by `POST /-/reload`, never a restart |
| **Live data changed** | none |

---

## 1. Headline

WP-53 found one alert that could never fire. This package assumed there were more and measured.

**Five of twelve rules were incapable of firing. Three of those are severity `critical`.**

| | |
|---|---|
| Capable, condition not met (healthy) | 4 |
| Capable, firing on a real condition | 3 |
| **INERT — no metric behind them** | **5** |

Two of the five were repairable and are repaired; both are now **firing on true positives**. The remaining three critical rules — `WorkerDown`, `DLQHighCount`, `JobFailureRateHigh` — cannot be repaired, cannot be tested, and are the substance of this report.

The seven missing metric names appear in Prometheus **and in the IVGS tree** exactly zero times. They were written against §13.1 Table 13-3 — the design — and nothing was ever built to emit them.

---

## 2. Task 1 — every rule, against the metrics that exist

Metric names were **queried** from `/api/v1/label/__name__/values`, never inferred from exporter documentation. The DCGM-vs-`nvidia_smi` prefix has already caught this fleet once and `DCGM_FI_DEV_GPU_TEMP` is still in the label index today with **zero live series** — a name that looks right and produces nothing, which is the whole hazard in one string.

| Rule | Sev | Metric(s) | Status | Verdict |
|---|---|---|---|---|
| GPUOvertemperature | crit | `nvidia_smi_temperature_gpu` | PRODUCED | Capable — 36–37 °C, condition not met (**healthy**) |
| WorkerDown | crit | `ivgs_worker_last_heartbeat_timestamp` | **ABSENT** | **INERT** — no equivalent exists |
| DLQHighCount | crit | `ivgs_dlq_message_count` | **ABSENT** | **INERT** — no equivalent exists |
| JobFailureRateHigh | crit | `ivgs_pipeline_jobs_failed_total`, `ivgs_pipeline_jobs_total` | **ABSENT** | **INERT** — no equivalent exists |
| BackupFailed | crit | `ivgs_backup_last_status` | PRODUCED | Capable — **FIRING** |
| BackupStale | crit | `ivgs_backup_last_timestamp` | PRODUCED | Capable — condition not met (**healthy**) |
| GPUUtilizationLow | warn | ~~`nvidia_gpu_utilization_pct`~~ → `nvidia_smi_utilization_gpu_ratio` | **ABSENT → REPAIRED** | Capable — **FIRING** |
| RenderQueueBacklog | warn | `ivgs_render_queue_pending_segments` | **ABSENT** | **INERT** — no equivalent exists |
| GPUVRAMHigh | warn | ~~`nvidia_gpu_memory_{used,total}_bytes`~~ → `nvidia_smi_memory_{used,total}_bytes` | **ABSENT → REPAIRED** | Capable — **FIRING** |
| NodeHighCPU | warn | `node_cpu_seconds_total` | PRODUCED | Capable — 416 series, condition not met (**healthy**) |
| NodeHighRAM | warn | `node_memory_MemAvailable_bytes`, `node_memory_MemTotal_bytes` | PRODUCED | Capable — condition not met (**healthy**) |
| StorageQuotaAlert | info | `ivgs_user_storage_used_bytes`, `ivgs_user_storage_quota_bytes` | **ABSENT** | **INERT** — no equivalent exists |

**"Healthy" and "inert" are stated separately on purpose.** Both render as `state: inactive` and both return no data from the thresholded expression. Distinguishing them requires evaluating the *base selectors* without the threshold — which is the measurement that separates "no GPU has overheated" from "this alert is incapable of noticing". That distinction is the entire package.

### 2.1 The two repairs, and what nearly went wrong

**GPUVRAMHigh** — `nvidia_gpu_memory_{used,total}_bytes` → `nvidia_smi_*`. Straight rename, same unit.

It is now **firing on node-02 at 90.40%** — `92792684544 / 102641958912`, measured. That is a **true positive**: vLLM preallocates its KV cache, so an LLM node sits near the top of VRAM by design. A rule that had never been able to speak, repaired, reporting a real condition four minutes later.

**GPUUtilizationLow** — `nvidia_gpu_utilization_pct` → `nvidia_smi_utilization_gpu_ratio`, **and `* 100`**.

The unit change is the load-bearing half and a bare rename would have been a worse bug than the one being fixed. The exporter emits a **ratio in [0,1]** against a rule written in **percent**. `avg(ratio) < 30` is true for every value the metric can take — an alert that cannot stop firing, the mirror image of one that cannot start. It would have survived review today only because an idle fleet reads `0` either way, and would have surfaced the moment the fleet did some work. Measured both forms before choosing.

### 2.2 The five with no metric — kept, not deleted

Per the order: not deleted, no substitute invented. Each now carries an in-file banner naming what is missing and why it stays.

**In every case the data exists in Postgres and nothing exports it:**

| Rule | Source table | Rows |
|---|---|---|
| WorkerDown | `worker_heartbeats` | 0 |
| DLQHighCount | `dead_letter_messages` | 0 |
| JobFailureRateHigh | `render_jobs` | **35** — exportable today with no new plumbing |
| RenderQueueBacklog | `render_segments` | 0 |
| StorageQuotaAlert | `storage_quotas` | 0 |

**One missing exporter explains all five silent alarms**, and it is one WP-53 already ledgered: **P2.62 — `ivgs-api` serves no `/metrics` endpoint at all.** That is where all five of these metrics belong. Ledger **P2.64**.

**Explicitly not substituted:** `RenderQueueBacklog` with `ivgs_scheduler_queue_depth`. It measures the GPU admission queue, is a different quantity, and is itself unreliable (P2.46). A plausible-looking substitute would have been worse than the gap — it would have closed the ledger entry without closing the gap, which is this package's failure mode in miniature.

Two of the empty tables are worth a second look. `dead_letter_messages` has 0 rows and, until WP-53 repaired `fallback_chain.py`, the worker could not write to it at all — so `DLQHighCount` has been a silent alert about a queue nothing could reach. `worker_heartbeats` has 0 rows while `WorkerDown` watches for stale ones.

---

## 3. Task 2 — proving the critical rules can fire

| Rule | Method | Result |
|---|---|---|
| **BackupFailed** | None needed — observed live | **FIRING** in Prometheus and `active` in Alertmanager. The real thing is the evidence. |
| **GPUOvertemperature** | Threshold-shift probe (cannot overheat a GPU) | **FIRED**, 2 alerts (node-02 37 °C, node-04 36 °C) |
| **BackupStale** | Threshold-shift probe (26 h window → 60 s) | **FIRED**, 2 alerts |
| **WorkerDown** | — | **NOT PROVEN AND CANNOT BE.** No metric. Stays on the list. |
| **DLQHighCount** | — | **NOT PROVEN AND CANNOT BE.** No metric. |
| **JobFailureRateHigh** | — | **NOT PROVEN AND CANNOT BE.** No metric. |

The probes used the **same metric and the same operator** as the real rule, with only the threshold moved to one the current data crosses, and were loaded via `POST /-/reload`. They were labelled `severity: critical` deliberately so they exercised the `critical-webhook` route rather than only the evaluation step.

**The full chain was observed, not assumed:** evaluate → firing in Prometheus → `active` in Alertmanager with `severity=critical` → four `Alert received` entries in the `ivgs-fastapi` log. Probes then removed and reloaded; verified back to 12 rules with no `WP54*` rule remaining.

Safe to run: the webhook receiver only logs and publishes to a Redis pub/sub channel — no persistence, no notification path off the box. **No live data was touched.**

### 3.1 Found while checking the delivery path

`ivgs-api/app/api/v1/alerts.py` is docstringed *"stores alerts in database for dashboard display"* and **stores nothing**. It logs, publishes to `ivgs:alerts` pub/sub, and returns. Pub/sub messages vanish if nobody is subscribed, so the dashboard sees an alert only if a WebSocket client happens to be connected at that instant, and there is no history at all. Another present-configured-and-inert instance, one layer down from the rules. Ledger **P2.65**.

---

## 4. Task 3 — the phantom-import family, closed

### 4.1 A correction to WP-53

WP-53 reported `tasks/periodic_tasks.py` as an unreachable parallel implementation, on the grounds that `get_beat_schedule()` is never registered. **The schedule half is true. The tasks half is not.** `celery -A celery_app inspect registered` on the live worker lists all six `periodic_tasks` entries by name. They are registered, dispatchable Celery tasks.

**Proven rather than argued** — dispatched `process_dlq` into the live default queue:

```
event=dlq_processing_started
event=dlq_processing_failed  error="No module named 'ivgs_workers'"
Task ivgs_workers.tasks.periodic_tasks.process_dlq raised unexpected: ModuleNotFoundError
state=FAILURE
```

It reaches the worker, executes, and dies at `periodic_tasks.py:166` before touching the DLQ. Safe to demonstrate: the raise happens after one log line and before any queue or database work. Worth noting it surfaces as `FAILURE` rather than being swallowed — the import is broken, the reporting around it is not.

### 4.2 The 14, grouped by root cause

**Group A — wrong module name only (3 sites). REPAIRED.**
`ivgs_workers.services.{dlq_service, orphan_cleanup, retention_migration}` → `services.*`. All three verified importable inside the running image.

**Group B — wrong module AND a symbol that does not exist (5 sites). REPAIRED.**
`ivgs_workers.config.get_db_session_factory`. `config.py` has no such function under any spelling. The real thing is `shared.database.async_session_factory`, an `async_sessionmaker` returning an `AsyncSession` with `__aenter__` — exactly the shape `async with self._db_session_factory() as session` needs, and what `shared/database.py` uses itself at `:57` and `:76`.

> **A call-shape bug caught in my own first cut**, recorded because the next person will hit it. The old code did `db_session_factory=get_db_session_factory()` — call the getter, receive a factory. `async_session_factory` **is** the factory, so aliasing it and keeping the parentheses would have passed a *Session* where a factory belongs, and `self._db_session_factory()` would then have tried to call a Session. It is passed uncalled at all five sites.

**Group C — wrong module, and no target anywhere (1 site). REPAIRED.**
`seed_fallback_policies.py:101` named `ivgs_api.app.database` **and** `get_async_session_factory`. There is no `app/database.py` in `ivgs-api` and no such function in the tree, so no rename alone could have fixed it. Now `shared.database.async_session_factory`.

**Group D — machinery absent from the worker image (5 sites). NOT REPAIRED, recorded.**
All five import `ivgs_api.app.models` from inside `ivgs-workers`. This cannot be renamed: the worker image ships `shared.models.{enums, model_store}` and nothing else — checked in the container, where `app.models` fails too. `TaskRetry`, `DeadLetterMessage` and `Asset` are defined only under `ivgs-api/app/models/`, which is not copied into the image.

**What the code assumes:** an `ivgs_api` package exposing `app.models`.
**What the image provides:** `shared.models` with two submodules.
**Scoped repair:** move those model classes into `shared/models/` — the shared location already exists and already carries `model_store` — or rewrite the five call sites against the API over HTTP, as `pipeline_orchestrator.py` already does. Ledger **P2.60**.

**One of the five is worse than the others and now says so.** `FallbackPolicyModel` (`fallback_chain.py:247`) is defined **nowhere in the repository**, in either service. That import has never had a target. It sits inside a `try/except` that falls back to `DEFAULT_FALLBACK_POLICIES`, so database-held fallback policies have never loaded and nothing has ever said so — the same present-configured-and-inert shape as the alert rules.

**Acceptance met:** no import in the tree names a package that does not exist, except five that carry a comment recording why they remain and a ledger id.

---

## 5. Task 4 — the gate

`tests_system/test_alert_rules_have_metrics.py` — 5 tests. Fails when an alert rule references a metric name no configured target produces.

**It asserts against the live Prometheus metric set, not a fixture.** A fixture would be a third statement of what someone believed the metric names were, which is precisely what has now been wrong three times. Only the running instance knows. Same principle as WP-45's broker-message assertions: assert the mechanism can act, not that it returned a success code.

**Proven to catch the defect, not merely written.** A deliberately broken rule was added to the rule file and the gate failed with:

```
WP54DeliberatelyBrokenRule [critical] references
['ivgs_metric_that_does_not_exist'], produced by no target
```

then removed, and the gate went green again. A guard nobody has watched fail is in the same state as the alerts it guards.

**The exemption list is not a skip marker.** The five inert rules are listed with their missing metrics and ledger `P2.64`, and three further tests stop the list rotting into a permanent allowlist:

* `test_no_exemption_has_quietly_become_available` — fails the moment an exempted metric starts being produced. Ship the exporter, delete the exemption.
* `test_every_exemption_names_a_rule_that_still_exists` — static; catches an exemption left behind after a rule was renamed.
* `test_every_exemption_carries_a_ledger_id` — a gap without an id is a gap nobody is accountable for.

**When Prometheus is unreachable it skips with a reason that says so, rather than passing.** A gate that quietly passed without its evidence source would be committing the defect it exists to catch.

Wired into `.github/workflows/ci.yml`. The static half runs on the runner; the two live assertions skip there and run on node-01, with `-rs` so the CI log says which half executed.

### 5.1 Found while wiring it

CI's *"Run Integration tests"* step ran `pytest tests/`. **That directory has not existed since WP-32.1** renamed it to `tests_system/` to break the module-name collision with `ivgs-api/tests`. `pytest` exits 4 on a missing path, so the step has been failing for its own reason rather than running the suite it names. Corrected in the same commit.

`PyYAML==6.0.3` declared in `requirements-dev.txt`. It was already in `.venv` as somebody else's transitive dependency — exactly the accident that breaks a clean install.

---

## 6. Verification — zero new failures

| Tree | Baseline | This package |
|---|---|---|
| `ivgs-api` | 843 / 0 | **843 / 0** |
| `ivgs-workers` | 766 / 18 / 48 skip / 15 err | **766 / 18 / 48 / 15** |
| `ivgs-scheduler` | 22 / 21 | **22 / 21** |
| `ivgs-backup-worker` | 4 / 0 | **4 / 0** |
| `tests_system` | 30 / 16 / 15 skip / 30 err | **35** / 16 / 15 / 30 |

Baseline updated in the same commit as the change that moved it: `tests_system` 30 → 35, total 1665 → 1670.

**The nine import repairs moved no test outcome at all**, which is itself the finding: none of those paths is covered by a test, which is why five of them could name a non-existent symbol for as long as they have.

### 6.1 Observed live, with output

* All 12 rule expressions evaluated against the live metric set, base selectors and thresholds separately.
* `GPUVRAMHigh` transition `pending` → **`firing`** at 20:24:20, node-02, value 9.040424 (×10 %).
* `GPUUtilizationLow` **firing** after its 15 m clock.
* Both probes firing in Prometheus, `active` in Alertmanager, four webhook deliveries logged by the API.
* Probes removed; 12 rules, no `WP54*` rule remaining.
* `process_dlq` dispatched into the live queue and observed failing at `periodic_tasks.py:166`.
* All nine corrected import targets resolved **inside the running worker container**.
* `promtool check rules`: SUCCESS at every step (12 → 14 → 12 rules).
* The negative-control rule failing the new gate, then removed.

### 6.2 Not observed, and not claimed

* **Nothing was deployed and no image was built.** The nine import repairs are in the tree; the running workers still carry `v5.12.0-correctness`, which contains the broken imports. `process_dlq` will keep failing in the fleet until the operator rebuilds — §8.
* node-03, node-05 and 192.168.1.62 were not contacted in any way. node-03's absence is visible in the data (only node-02 and node-04 report GPU metrics) and was left alone.
* `WorkerDown`, `DLQHighCount` and `JobFailureRateHigh` are **untested and untestable**. No claim is made that they work.
* The three critical rules proven by threshold-shift were proven for their **shape** — metric, operator, routing. A real 86 °C GPU was not produced and could not be.

---

## 7. Ledger

**P2.64 — five alert rules have no metric behind them, and one missing exporter explains all five.** `WorkerDown` (crit), `DLQHighCount` (crit), `JobFailureRateHigh` (crit), `RenderQueueBacklog` (warn), `StorageQuotaAlert` (info). Seven metric names, produced by nothing and defined nowhere in the tree; written against §13.1 Table 13-3 and never built. The source data is in Postgres in every case — `render_jobs` already holds 35 rows and could be exported today. Root cause is shared with **P2.62** (`ivgs-api` serves no `/metrics`). Repair: give the API a metrics endpoint and emit these seven from it; then delete the corresponding entries from `KNOWN_INERT`, which will start failing the moment the metrics appear.

**P2.65 — the alert webhook stores nothing.** `ivgs-api/app/api/v1/alerts.py` is docstringed *"stores alerts in database for dashboard display"* and only logs and publishes to a Redis pub/sub channel. No persistence, no history; the dashboard sees an alert only if a client is connected at that instant. Repair: persist to a table, or correct the docstring and the dashboard's expectations — but not both readings can stand.

**Contributed to P2.60** (WP-53) — the five `ivgs_api.app.models` imports now carry in-code banners naming what is assumed versus what the image provides, and the finding that `FallbackPolicyModel` exists nowhere in the repository at all.

---

## 8. Decisions needed

**D-1 — three critical alerts remain incapable of firing, and this is now a known state rather than an unknown one.** `WorkerDown`, `DLQHighCount`, `JobFailureRateHigh`. The fleet has no page-on-call coverage for a dead worker, a filling DLQ, or a job-failure spike. The fix is one exporter (P2.64 + P2.62) and it is not a large piece of work — `render_jobs` alone would light up `JobFailureRateHigh` immediately. **Do you want that as the next package?**

**D-2 — `GPUVRAMHigh` now fires continuously on node-02 at 90.4%, and it is correct.** vLLM preallocates its KV cache, so an LLM node will sit above 90% whenever it is serving. The alert is doing its job; the question is whether 90% is the right threshold for a node whose steady state is 90%, or whether the rule needs a per-role threshold. Left firing rather than tuned, because tuning it silently is how a true positive becomes noise and then gets ignored.

**D-3 — the nine import repairs need a worker rebuild to take effect.** They are in the tree and committed; the running image still has them broken, and `process_dlq` still fails in the fleet. Node-01 build/deploy plus the operator blocks for nodes 02/04 are below. Node-01 has no registry credentials (WP-53 D-3, unchanged), so the build block is for the operator.

**D-4 — `FallbackPolicyModel` does not exist anywhere.** `fallback_chain.py` has always silently fallen back to `DEFAULT_FALLBACK_POLICIES`. Either the DB-held policy table is a design that was never finished, or the model was lost. Worth knowing which before someone "fixes" the import.

---

## 9. Operator blocks

### 9.1 Rebuild and deploy node-01 (carries the nine import repairs)

```bash
# node-01
cd /opt/ivgs && \
echo "$GHCR_PAT" | docker login ghcr.io -u brucecostello2 --password-stdin && \
docker build -t ghcr.io/brucecostello2/ivgs-api:v5.13.0-silent-alarms     -f ivgs-api/Dockerfile     . && \
docker build -t ghcr.io/brucecostello2/ivgs-workers:v5.13.0-silent-alarms -f ivgs-workers/Dockerfile . && \
docker push ghcr.io/brucecostello2/ivgs-api:v5.13.0-silent-alarms && \
docker push ghcr.io/brucecostello2/ivgs-workers:v5.13.0-silent-alarms && \
sed -i 's/^IVGS_API_TAG=.*/IVGS_API_TAG=v5.13.0-silent-alarms/;s/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.13.0-silent-alarms/' ivgs-infra/.env && \
docker compose \
  -f ivgs-infra/docker-compose.node01.yml \
  -f ivgs-infra/docker-compose.override.node01.yml \
  -f ivgs-infra/docker-compose.monitoring.yml \
  --env-file ivgs-infra/.env \
  up -d --no-deps fastapi celery-default celery-composition celery-beat && \
sleep 15 && \
for c in ivgs-fastapi ivgs-celery-default ivgs-celery-composition ivgs-celery-beat; do \
  echo "$c -> $(docker inspect $c --format '{{.Config.Image}}')"; done
```

No migration this time. `--no-deps` is mandatory or Postgres restarts. Verify the image with `docker inspect`, never `docker exec env`.

**Gate the deploy on the repair actually working** — the same dispatch that proved the defect:

```bash
# node-01, after the recreate
docker exec ivgs-celery-default python -c \
  "from celery_app import celery_app; print(celery_app.send_task('ivgs_workers.tasks.periodic_tasks.process_dlq', queue='default').id)" && \
sleep 12 && \
docker logs ivgs-celery-default --since 1m 2>&1 | grep -E "process_dlq" | tail -3
```

It must no longer say `No module named 'ivgs_workers'`. It may still fail for a different reason — `_dlq_table()` imports `ivgs_api.app.models`, which is P2.60 and is *not* fixed by this package. That is the expected next failure and it is the correct one.

### 9.2 Nodes 02 and 04 worker rebuild

Run after the push. One node at a time. **node-03 and node-05 are OUT OF SERVICE — do not run this there. Do not touch 192.168.1.62.**

```bash
# node-02 (192.168.1.91), then node-04 (192.168.1.93) with its own compose file
cd /opt/ivgs && \
sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.13.0-silent-alarms/' ivgs-infra/.env && \
docker compose -f ivgs-infra/docker-compose.node02.yml --env-file ivgs-infra/.env pull celery-worker && \
docker compose -f ivgs-infra/docker-compose.node02.yml --env-file ivgs-infra/.env up -d --no-deps celery-worker && \
sleep 10 && docker inspect ivgs-celery-worker --format '{{.Config.Image}}'
```

node-04's `celery-worker` has `depends_on: comfyui`; `--no-deps` is what keeps the recreate off the engine.

### 9.3 No Prometheus action required

All rule changes are already live on node-01, applied by `POST /-/reload` and verified by `promtool check rules` before each reload. Nothing was restarted. No further operator step.

---

## 10. Commits — HELD, not pushed

```
6039fc6  test(wp-54): a gate for the class - an alert that cannot fire
dcfb2cc  fix(wp-54): the phantom-import family closed - 9 repaired, 5 recorded
860eda2  fix(wp-54): five of twelve alert rules were incapable of firing; two repaired
```

plus the documentation commit carrying this report.

### Push block — count-gated

Refuses unless exactly **4** commits are ahead of `origin/main` and all four are WP-54.

```bash
# node-01
cd /opt/ivgs && git fetch origin && \
AHEAD=$(git rev-list --count origin/main..HEAD) && \
WP54=$(git log --oneline origin/main..HEAD | grep -c 'wp-54') && \
echo "ahead=$AHEAD wp54=$WP54" && \
if [ "$AHEAD" -eq 4 ] && [ "$WP54" -eq 4 ]; then \
  git log --oneline origin/main..HEAD && \
  git push origin main && echo "PUSHED"; \
else \
  echo "REFUSING: expected 4 commits ahead, all WP-54; got ahead=$AHEAD wp54=$WP54"; \
fi
```

Nothing has been pushed. `dev/workpackages/WP-45-gpu-registry-backup-20260825-170853.txt` is WP-45's untracked artefact and was left alone.
