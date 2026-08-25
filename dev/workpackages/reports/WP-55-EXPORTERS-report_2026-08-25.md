# WP-55-EXPORTERS — the three critical alerts get metrics, and VRAM alerting gets a role

**Date:** 2026-08-25 · **Node:** node-01 only · **Status:** complete, deployed to node-01, committed, HELD

| | |
|---|---|
| **Commits** | 3, held on `main`, nothing pushed |
| **Deployed** | `v5.14.0-exporters` on node-01 (api + workers), via the artifact path |
| **Zero new failures** | confirmed against the corrected baseline, all five trees |
| **Inert alert rules** | **5 → 1**, and the one that remains is inert for a different reason |
| **Prometheus targets** | 10 up / 6 down → **11 up / 5 down**, all five downs explained |
| **Nodes visited** | none. node-05 and node-06 untouched; 02/03/04 are operator paste blocks |
| **Live data changed** | none |

---

## 1. Headline

WP-54 found five alert rules incapable of firing, three of them severity `critical`. This package built the exporter they have referenced since they were written against §13.1 Table 13-3 and never had.

| Rule | Sev | Metric produced | Rule evaluates against data | Demonstrated capable of firing, by |
|---|---|---|---|---|
| **WorkerDown** | crit | **YES** | **YES** — heartbeat age 9.0–9.2 s vs a 300 s threshold | Threshold-shift probe. Fired, 2 workers |
| **DLQHighCount** | crit | **YES** | **YES** — 0 vs a 10 threshold | Threshold-shift probe. Fired |
| **JobFailureRateHigh** | crit | **YES** | **YES** — `rate()` reads 0, see §3.1 | Threshold-shift probe at the **real 54.3%** all-time rate. Fired |
| **RenderQueueBacklog** | warn | **YES** | **YES** — 0 vs a 20 threshold | Threshold-shift probe. Fired |
| **StorageQuotaAlert** | info | **BUILT, no samples** | **NO** — `storage_quotas` holds 0 rows | **NOT PROVEN.** Stays on the list |

Plus, from Task 2:

| Rule | Sev | Evaluates against | Capable by |
|---|---|---|---|
| **GPUVRAMHigh** (now `role="image"`) | warn | node-04, 28.45 % | Probe fired |
| **GPUVRAMSaturatedVideoNode** (new) | warn | node-03, 21.72 % | Probe fired |
| **GPULLMNodeFreeVRAMLow** (new) | warn | node-02, 8.55 GiB free | Probe fired |

All eight probes reached Alertmanager and the API webhook logged the deliveries, then were removed. **`StorageQuotaAlert` is reported as untested because it is untestable today** — WP-54's discipline stands.

---

## 2. Task 0 — the premise that stopped two packages

Recorded in `dev/CLAUDE.md` §6.1 and §6.2.

WP-53 and WP-54 both declined to deploy on the grounds that node-01 "has no registry credentials". It has them, under **root** rather than the `dev` user — and more to the point **they are not needed**. Nodes 02/03/04 do not pull. Images travel as artifacts (WP-34 rule 1), and that is how `v5.12.0-correctness` and `v5.13.0-silent-alarms` each reached the fleet.

This package used that path and deployed. §6.1 also records the two-user pipe (`sudo docker save | sudo sh -c "zstd -o ..."`), because the naive form elevates only the first half and fails on the write.

§6.2 records that **node-03's worker service is `cogvideox-worker`, not `celery-worker`** — node-03 also declares a `celery-worker` under `profiles: ["standby"]` that is not running, and naming it starts a second worker competing for the same queues while leaving the real one on the old image. WP-44 S6.3 recorded that happening.

---

## 3. Task 1 — the exporter

`ivgs-api/app/api/v1/metrics.py`. **Seven series, one per name an alert rule references, and nothing else.** Not a metrics framework: every series exists because a specific rule names it.

| Metric | Unit | Source | Rule and its threshold's unit |
|---|---|---|---|
| `ivgs_worker_last_heartbeat_timestamp{worker_id,node}` | unix **seconds** | Redis liveness hash | `time() - m > 300` — seconds |
| `ivgs_dlq_message_count` | **count** | `dead_letter_messages WHERE resolution IS NULL` | `> 10` — count |
| `ivgs_pipeline_jobs_total` | **count** | `render_jobs` | ratio ×100 `> 10` — **percent** |
| `ivgs_pipeline_jobs_failed_total` | **count** | `render_jobs WHERE status='failed'` | as above |
| `ivgs_render_queue_pending_segments` | **count** | `render_segments WHERE status='pending'` | `> 20` — count |
| `ivgs_user_storage_used_bytes{...}` | **bytes** | `storage_quotas.current_bytes` | `(used/quota)×100 > 80` — **percent** |
| `ivgs_user_storage_quota_bytes{...}` | **bytes** | `storage_quotas.max_bytes` | as above |

Units are stated and tested because the unit is where this goes wrong. WP-54 found `GPUUtilizationLow` needed a unit change as well as a rename, and that a bare rename would have produced an alert that could never *stop* firing — looking correct on the day only because an idle fleet reads 0 either way. `test_wp55_metrics_exporter.py` pins each name and each unit.

**Values are read from the database at scrape time, not accumulated in process.** An in-process counter resets whenever the API restarts, which `rate()` treats as a counter reset but which also makes the API's uptime part of the measurement. A count read from `render_jobs` is the same number before and after a restart, and is the number an operator gets by querying the table.

**A failed query omits the series rather than reporting zero.** A metric reading 0 because the query broke is indistinguishable from a metric reading 0 because the DLQ is empty — the exact substitution this line of work exists to remove. There is a test for it.

### 3.1 The brief's acceptance test, and why it could not be met as written

> *"render_jobs already holds 35 rows, so JobFailureRateHigh should light up on REAL data the moment the metric exists."*

**It does not, and it should not.** The rule is

```promql
(sum(rate(ivgs_pipeline_jobs_failed_total[5m])) / clamp_min(sum(rate(ivgs_pipeline_jobs_total[5m])), 0.001)) * 100 > 10
```

`rate()` measures change over five minutes. Those 35 rows are historical and static, so both rates are 0 and the expression reads **0%**. The metric is produced, the rule evaluates against real data, and the value is correctly zero.

**Changing it to fire would be wrong**, and wrong in this project's most familiar way. A cumulative `failed/total` would read 54.3% and fire *forever*, because the past never gets better — an alert that cannot stop firing, which WP-54 established is the mirror image of one that cannot start. A page-on-call rule for "job failure rate high" must mean *jobs are failing now*.

So the demonstration used the real data at the honest angle: a probe evaluating `(failed/total)*100 > 10` fired at **54.3%**, proving the metric carries the failure information and the arithmetic works. The live rule stays rate-based and will fire the first time jobs actually fail in a five-minute window.

That 54.3% all-time failure rate over 35 jobs is worth someone's attention on its own merits. It is a finding, not an alert — **D-2**.

### 3.2 Worker liveness — three existing mechanisms, all rejected on measurement

`WorkerDown` must say **which** worker died. Three things that look like they already do this were tried:

1. **`worker_heartbeats`**, the table the schema was designed around: **0 rows, nothing writes it.** Its supposed supervisor, `pipeline_orchestrator.supervise_worker_heartbeats`, does not touch that table either — it polls the GPU scheduler's `/fleet`, whose registry is itself unreliable (P2.46).
2. **`gpu_utils.start_heartbeat_loop`**, started from `worker_ready` — but only when `register_node()` returns a node id, which it does not for a worker with no GPU identity. node-01's `default-worker` and `composition-worker` have **never** heartbeated, and it reports into the same empty registry.
3. **Celery pidbox broadcast** (`inspect ping`). Works from inside a worker container — all five answer. Does **not** work from the API: measured from `ivgs-fastapi` with the workers' exact `broker_transport_options`, `control.ping()` returned **1 of 5**, repeatedly, at 2 s and 6 s timeouts. A critical alert built on that would have reported four healthy workers as dead.

So the worker asserts its own liveness to Redis (`ivgs-workers/utils/liveness.py`), unconditionally — no GPU identity, no scheduler, no broadcast — and the exporter reads it.

**It has to be a last-seen timestamp, not an up/down flag.** `time() - ts > 300` only fires while the series still *exists* and is stale. If a dead worker's series simply vanished, Prometheus would drop it after ~5 minutes of staleness and the alert would never fire: the death would erase the evidence of the death. Shutdown deliberately does **not** delete the record, so a worker stopped and not restarted trips `WorkerDown` five minutes later instead of disappearing quietly.

### 3.3 A defect caught in this package's own first deploy

The first deployed cut labelled node-01's workers `node="2807c417948c"` and `node="12f7e72c557b"` — container IDs. `WorkerConfig.node_hostname` falls back to the container hostname when `IVGS_NODE_NAME` is unset, and it is unset on node-01.

That is precisely the defect `config.py:282` documents for the GPU scheduler registry — *"21 registered 'nodes', 3 alive, on a fleet of three GPUs"* — reappearing in a brand-new metric on its first day. Fixed before commit: the node is taken from the Celery hostname after the `@` and normalised to `node-0N`, so it joins with every other `node` label in Prometheus. Rebuilt and redeployed; the beacon now records `node-01` for both.

---

## 4. Task 2 — per-role VRAM (WP-54 D-2, RULED)

`GPUVRAMHigh` fired continuously on node-02 and was **right to**. Measured: node-02 at **90.4 % used, 8.55 GiB free, flat over an hour** (`min_over_time` equals current), because vLLM preallocates its KV cache. node-03 reads 21.7 %, node-04 28.5 %. One threshold cannot mean the same thing on three roles.

**No threshold was raised and no rule was deleted.** `role` labels were added to the GPU scrape targets, and the one rule became three:

| Rule | Scope | Condition | Why |
|---|---|---|---|
| `GPUVRAMHigh` *(same name, same 90 %)* | `role="image"` | >90 % for **10 m** (was 5 m) | node-04's steady state is 28.5 %, so 90 % is a real signal there. 10 m because image generation legitimately spikes for the length of a batch, and a rule that pages on a normal batch gets muted |
| `GPUVRAMSaturatedVideoNode` *(new)* | `role="video"` | >95 % for **30 m** | CogVideoX and Wan-Animate are co-resident on node-03; high VRAM during a render is expected. **Duration**, not level, is what separates a long render from a stuck one — 30 m is longer than any single clip this pipeline produces |
| `GPULLMNodeFreeVRAMLow` *(new)* | `role="llm"` | **free** < 4 GiB for 15 m | A level threshold measures the allocator, not the health: node-02 reads 90.4 % idle and would read the same under load, so "used %" carries almost no information. **Headroom** does |

**The 4 GiB floor was chosen against measurement, not intuition.** node-02's free VRAM is 8.55 GiB and flat, so the rule sits comfortably below its steady state — healthy today, and demonstrated capable of firing — while still being a real floor: a 96 GB card with under 4 GiB free cannot load anything.

**node-02 did not lose coverage.** It moved from a rule that told it something it already knew to one that would tell it something it does not.

---

## 5. Task 3 — the import repairs, verified on the fleet

Dispatched `process_dlq` into the live default queue, the same way WP-54 proved the defect:

```
BEFORE (v5.13.0): ModuleNotFoundError("No module named 'ivgs_workers'")   line 166
AFTER  (v5.13.0): ModuleNotFoundError("No module named 'ivgs_api'")       line 174
```

**The nine repairs work.** The failure moved eight lines further into the function and changed cause: the `ivgs_workers.*` imports resolve, and execution now reaches `_dlq_table()`, which imports `ivgs_api.app.models`. That is **P2.60**, explicitly not fixed by WP-54, and WP-54's operator block predicted this exact next failure.

**`process_dlq` still does not complete**, and DLQ replay — one of WP-45's live operator-facing bugs — is still broken end to end. It is now blocked on one named, ledgered defect instead of two. **D-3.**

**Which repairs a live dispatch cannot exercise, and why.** Only `process_dlq`'s two imports (`services.dlq_service`, `shared.database.async_session_factory`) are reached by this dispatch. The other seven sit in `supervise_heartbeats`, `run_orphan_cleanup`, `run_retention_migration`, `verify_latest_backup` and `seed_fallback_policies`. Each of those tasks is registered and dispatchable, but each performs real work against live data on success — orphan cleanup deletes assets, retention migration moves storage tiers — and **"change no live data" forbids dispatching them to find out.** They are verified as far as import resolution goes (all targets import inside the running container) and no further. Reported rather than claimed.

---

## 6. Task 4 — CI runs real tests, and is red

WP-54 pointed the integration step from the long-deleted `tests/` at `tests_system/`. WP-55 **measured** what a GitHub runner can actually execute there rather than assuming: most of that tree talks to the live fleet — the API on 8001, the scheduler on 8002, SeaweedFS, Prometheus — none of which exists on a runner. Pointing the step at the whole tree would produce 30 connection errors that say nothing about the commit.

The step now names the four paths that need only the checkout, and **it runs them**, measured with every service unreachable:

```
27 passed, 2 skipped, 4 failed
```

The 2 skips are the alert gate's live half, which says so in its skip reason.

**The 4 failures are real and the step stays red.** They are `test_scanner_detects_pip_packages`: `match_glob` in `scripts/compliance_scanner.py` cannot match `"requirements*.txt"`, so **§F.2 Rule 2 has never been enforced** and a prohibited pip package would pass the compliance gate today. Ledger **P2.49**, raised by WP-52, one line to fix, blast radius already measured as zero. The brief is explicit that a step going red when pointed at real tests is a finding, not a reason to point it back at nothing. **D-1.**

---

## 7. Task 5 — two things not fixed

**(a) `FallbackPolicyModel` — RULED, ledger P2.66.** Defined nowhere in the repository, and nothing anywhere references `FallbackChainService`. That is not a broken import in a working subsystem; it is a subsystem specified, partly written, and never wired up, running on `DEFAULT_FALLBACK_POLICIES` since it was authored. **The import is left broken** and the ruling is recorded at the site: repairing it would create the appearance of a database-backed policy system with no policy table, no writer and no caller behind it — worse than an honest gap, because the next reader would believe policies load.

**(b) The five WP-54 recorded rather than repaired** were each checked and still carry their banner and **P2.60**: `retry_engine.py:388` and `:442`, `dlq_service.py:725`, `motion_graphics.py:531`, `fallback_chain.py:247`. None was repaired in this package.

---

## 8. Verification

| Tree | Baseline | This package |
|---|---|---|
| `ivgs-api` | 843 / 0 | **850 / 0** (+7, the exporter contract tests) |
| `ivgs-workers` | 766 / 18 / 48 skip / 15 err | **766 / 18 / 48 / 15** |
| `ivgs-scheduler` | 22 / 21 | **22 / 21** |
| `ivgs-backup-worker` | 4 / 0 | **4 / 0** |
| `tests_system` | 35 / 16 / 15 skip / 30 err | **35 / 16 / 15 / 30** |

Baseline updated in the same commit as the change that moved it: `ivgs-api` 843 → 850, total 1670 → 1677.

### 8.1 The WP-54 gate did its job unprompted

After the exporter shipped, `test_no_exemption_has_quietly_become_available` went **red on its own**, naming all four exemptions this package had just satisfied and refusing to pass until they were retired. Four removed; `StorageQuotaAlert` remains with its reason **changed** — from *"never built"* to *"built, no data yet"*, which is a different fact and will retire itself the first time a quota row exists.

That is a guard behaving exactly as designed, one package after it was written, without being asked.

### 8.2 Observed live, with output

* `/api/v1/metrics` serving on the deployed image; Prometheus target `ivgs-fastapi:8001` **UP** (**P2.62 closed**).
* Six of seven metric families carrying live series; the seventh empty because `storage_quotas` has 0 rows.
* Worker beacon writing `node-01` for both node-01 workers after the label fix.
* All 14 rules `health: ok`; per-rule base-expression values measured and tabulated.
* Eight capability probes firing, reaching Alertmanager, and delivered to the API webhook; then removed and the rule count verified back at 14.
* `process_dlq` dispatched live: failure moved from line 166/`ivgs_workers` to line 174/`ivgs_api`.
* `promtool check config` / `check rules`: SUCCESS at every step. Every rule change applied by `POST /-/reload`; **nothing was restarted**.
* Prometheus targets 11 up / 5 down. All five downs explained: node-05 ×2 (out of service), node-06 nvidia (unprovisioned), `postgres-exporter` and `redis-exporter` (never deployed — P2.62's siblings, unchanged).

### 8.3 Not observed, and not claimed

* **Nodes 02, 03 and 04 still run `v5.13.0-silent-alarms`.** The worker liveness beacon is deployed on node-01 only, so `ivgs_worker_last_heartbeat_timestamp` currently carries **2 series, not 5**. `WorkerDown` covers node-01's two workers today and will cover all five after §9.2. This is the single most important limitation in this report.
* node-05 and node-06 were not contacted in any way.
* Seven of the nine import repairs are verified only as far as import resolution — §5.
* `StorageQuotaAlert` is **not** proven capable of firing.
* The 54.3 % historical job failure rate was not investigated. It is a finding, not a conclusion.

---

## 9. Operator blocks

### 9.1 The artifact is already staged

```
/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.14.0-exporters.tar.zst   313M
sha256 (first 16): 4fb82e3a87173d5f
```

node-01 is already deployed and verified. The API image is node-01-only and needs no artifact.

### 9.2 Nodes 02 and 04 — service `celery-worker`

One node at a time. **node-05 and node-06 are out of bounds.**

```bash
# node-02 (192.168.1.91), then node-04 (192.168.1.93) with its own compose file
cd /opt/ivgs && \
A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.14.0-exporters.tar.zst && \
sha256sum "$A" | cut -c1-16 && \
zstd -dc "$A" | sudo docker load && \
sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.14.0-exporters/' ivgs-infra/.env && \
sudo docker compose -f ivgs-infra/docker-compose.node02.yml --env-file ivgs-infra/.env \
  up -d --pull never --no-deps celery-worker && \
sleep 15 && sudo docker inspect ivgs-celery-worker --format '{{.Config.Image}}'
```

The printed sha must be `4fb82e3a87173d5f`. node-04's `celery-worker` has `depends_on: comfyui`; `--no-deps` is what keeps the recreate off the engine.

### 9.3 node-03 — service `cogvideox-worker`, NOT `celery-worker`

```bash
# node-03 (192.168.1.92)
cd /opt/ivgs && \
A=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.14.0-exporters.tar.zst && \
sha256sum "$A" | cut -c1-16 && \
zstd -dc "$A" | sudo docker load && \
sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.14.0-exporters/' ivgs-infra/.env && \
sudo docker compose -f ivgs-infra/docker-compose.node03.yml --env-file ivgs-infra/.env \
  up -d --pull never --no-deps cogvideox-worker && \
sleep 15 && sudo docker inspect ivgs-cogvideox-worker-node03 --format '{{.Config.Image}}'
```

**Do not name `celery-worker` here.** node-03 declares one under `profiles: ["standby"]` that is not running; starting it puts a second worker on the same queues and leaves the real one on the old image (WP-44 S6.3).

### 9.4 Gate the whole rollout on the metric, from node-01

```bash
# node-01, after each node
curl -s http://192.168.1.90:8001/api/v1/metrics | grep ivgs_worker_last_heartbeat_timestamp
```

Expect **5 series** when 02, 03 and 04 are all done — `default-worker@node01`, `composition-worker@node01`, `celery-worker@node02`, `cogvideox-worker@node03`, `image-worker@node04` — each labelled `node-0N` and none labelled with a hex container id. Anything less means a node did not take the image.

### 9.5 Nothing to do for Prometheus

All rule and scrape changes are live on node-01, applied by `POST /-/reload` after `promtool check`. Nothing was restarted.

---

## 10. Ledger

**P2.66 — the fallback subsystem was never wired up.** `FallbackPolicyModel` exists nowhere in the repository; nothing references `FallbackChainService`; `load_policies()` has always fallen through to `DEFAULT_FALLBACK_POLICIES` inside a `try/except`. Ruled: **leave the import broken**, recorded at the site. The repair is to finish the design or delete the subsystem — an operator decision, not an edit.

**P2.62 — CLOSED.** `ivgs-api` now serves `/api/v1/metrics` and its Prometheus target reads UP.

**P2.64 — reduced from five rules to one.** `WorkerDown`, `DLQHighCount`, `JobFailureRateHigh` and `RenderQueueBacklog` have metrics and are demonstrated capable. `StorageQuotaAlert` remains, with its reason changed from "never built" to "built, no data yet".

**P2.49 — now blocking CI**, unchanged otherwise. Raised by WP-52; the compliance scanner has never enforced §F.2 Rule 2. See D-1.

**P2.60 — unchanged**, five sites, each still carrying its banner. Now also the blocker for DLQ replay (§5).

---

## 11. Decisions needed

**D-1 — CI is red, and the fix is one line.** `P2.49`: `match_glob` cannot match `"requirements*.txt"`, so a prohibited pip package would pass the compliance gate today. WP-52 measured the blast radius as zero — no tracked requirements file carries one. I left it red because the brief said to ledger it rather than point CI back at nothing, but a permanently-red gate trains people to ignore CI. **One line, or one package?**

**D-2 — 19 of 35 render jobs have failed: a 54.3 % all-time failure rate.** Surfaced by building the metric, not investigated. `JobFailureRateHigh` will not fire on it and correctly so (§3.1), but a job pipeline failing more often than it succeeds is worth someone looking at directly.

**D-3 — DLQ replay is still broken, now on one defect instead of two.** `process_dlq` reaches `_dlq_table()` and dies on `ivgs_api.app.models` (P2.60). The repair is to move `DeadLetterMessage`, `TaskRetry` and `Asset` into `shared/models/` — where `model_store` already lives — or to rewrite those call sites against the API over HTTP as `pipeline_orchestrator.py` already does. This was a live operator-facing bug in WP-45 and is still one.

**D-4 — `WorkerDown` covers 2 of 5 workers until §9.2 and §9.3 run.** The metric is per-worker and correct, but the beacon only exists on node-01's image. Until nodes 02/03/04 take `v5.14.0-exporters`, a death on those three is still invisible.

---

## 12. Commits — HELD, not pushed

```
2dc2074  docs(wp-55): the deploy path, node-03's service name, CI, and one ruling
13af94e  feat(wp-55): the three critical alerts get metrics, and VRAM alerting gets a role
```

plus the documentation commit carrying this report.

**`ivgs-infra/.env` is NOT committed** — it is gitignored (`.gitignore:32`) and carries secrets. Its `IVGS_API_TAG` / `IVGS_WORKERS_TAG` were set to `v5.14.0-exporters` on node-01 as part of the deploy, and the operator blocks in §9 set the same pins on each node.

### Push block — count-gated

`origin/main..HEAD` also carries one **pre-existing** commit that is not mine — `423e489 chore(wp-45): bank the GPU registry state before the dead-node prune`, committed before this package started. The gate expects **4 commits, 3 of them WP-55**, and names the fourth so it cannot be a surprise.

```bash
# node-01
cd /opt/ivgs && git fetch origin && \
AHEAD=$(git rev-list --count origin/main..HEAD) && \
WP55=$(git log --oneline origin/main..HEAD | grep -c 'wp-55') && \
OTHER=$(git log --oneline origin/main..HEAD | grep -v 'wp-55' | cat) && \
echo "ahead=$AHEAD wp55=$WP55" && echo "non-WP-55: $OTHER" && \
if [ "$AHEAD" -eq 4 ] && [ "$WP55" -eq 3 ] && \
   [ "$(echo "$OTHER" | grep -c 'wp-45): bank the GPU registry state')" -eq 1 ]; then \
  git log --oneline origin/main..HEAD && \
  git push origin main && echo "PUSHED"; \
else \
  echo "REFUSING: expected 4 ahead, 3 WP-55 + the WP-45 registry-bank commit; got ahead=$AHEAD wp55=$WP55"; \
fi
```

Nothing has been pushed.
