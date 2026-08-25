# WP-53-CORRECTNESS — four defects the baseline found, node-06, and the dropped seam field

**Date:** 2026-08-25 · **Node:** node-01 only · **Status:** code complete, committed, HELD. **Deploy NOT performed — see §7.**

| | |
|---|---|
| **Commits** | 6, held on `main`, nothing pushed |
| **Zero new failures** | confirmed against `TEST-BASELINE_2026-08-25.md`, all five trees |
| **Baseline rows moved** | updated in the same commit as each fix, as required |
| **Images built / deployed** | **none — blocked, §7** |
| **Nodes visited** | none. node-06 probed from node-01 only |
| **node-05** | not deployed to, not read from, not scheduled. Its Prometheus targets left down, correctly |
| **Live data changed** | none. Migration 0029 applied (additive, nullable, 18 rows all NULL) |

---

## 1. Headline

| Tree | Before (WP-52 baseline) | After |
|---|---|---|
| `ivgs-api` | 833 passed / 0 failed | **843 passed / 0 failed** |
| `ivgs-workers` | 754 / 22 failed / 48 skip / 15 err | **766 / 18 failed** / 48 skip / 15 err |
| `ivgs-scheduler` | 22 / 21 | 22 / 21 *(untouched)* |
| `ivgs-backup-worker` | 4 / 0 | 4 / 0 *(untouched)* |
| `tests_system` | 30 / 16 / 15 skip / 30 err | 30 / 16 / 15 skip / 30 err *(unchanged)* |

**Zero new failures anywhere.** Four ledger entries closed — **P2.50, P2.54, P2.55** — plus the P2.40 half that could honestly be closed. 22 tests added across the two trees.

Prometheus: **6 up / 10 down → 10 up / 6 down**, and all six remaining downs are explained rather than tolerated.

---

## 2. Task 0 — the baseline's arithmetic

§0 said the scheduler had **21** failed. §4's cause table summed to **22**. Re-ran the tree before touching anything else.

**§0 was right.** `test_circuit_breaker.py` collects 10, passes 1, fails **9** — eight on `zremrangebyscore` and one, `test_zero_requests_returns_zero_rate`, on `zcount`. The §4 row read **9** for *"all but `test_zero_requests_returns_zero_rate`"* and the row below then counted that same test again. It is one of the nine, not a tenth.

Corrected to **8**, and the prose made unambiguous — *"all but X"* could be read as all TESTS in the file or all FAILURES in it, and the file has ten of one and nine of the other. The table sums 6 + 1 + 8 + 1 + 4 + 1 = **21**.

Ledger totals it feeds are unchanged (P2.51 = 7 tests, P2.52 = 14), which is exactly why the error would have survived into canon: nothing downstream of the number was wrong. **Every other table in the document was re-checked at the same time** — `ivgs-workers` (22 = 10+2+2+1+2+1+1+1+1+1), `tests_system` (16 failures, 30 errors) and the §0 totals all reconcile. This was the only arithmetic defect. Recorded under a new **Errata** section rather than silently amended.

---

## 3. Task 1 — P2.50, the DLQ hand-off

`services/fallback_chain.py:459` imported `ivgs_workers.services.dlq_service`. No `ivgs_workers` package exists — the directory is `ivgs-workers`, a hyphen, which is not an importable module name. Fixed to `services.dlq_service` and **moved to module scope**: an import on a rarely-taken path is one the taken paths never exercise, and this one sat on the line after *"All levels exhausted — route to DLQ"*.

### 3.1 Correcting WP-52's own ledger entry

P2.50 as written said an exhausted chain *"never reaches the DLQ"* in production. Measured today: **nothing outside this module and its tests references `FallbackChainService` or `execute_fallback_chain` at all.** The chain is not wired into a live path. The import was broken; the blast radius was overstated. Correcting it here rather than quietly narrowing it.

### 3.2 The audit — counted, not estimated

AST walk over all production code in five services:

* **14 sites remain** that import a package which does not exist, in 6 files (15 before this commit). Nine name `ivgs_workers.*` — all eight in `tasks/periodic_tasks.py`, plus the one fixed. Five name `ivgs_api.app.models`, one `ivgs_api.app.database`. **Every one is deferred into a function body.**
* **191 function-body imports overall**; 28 unresolvable from their own service's runtime path. Fourteen of those are `torch`/`diffusers`/`whisperx`/`TTS`/`kokoro`/`temporalio` in the GPU-node server modules — absent from node-01 by design, not defects. The other fourteen are the phantom packages above.

### 3.3 Why the other 14 were NOT fixed

**They are not the same fix**, and renaming them would have produced code that looks fixed and still raises — the trap WP-52 Task 4 stepped around.

* `ivgs_api.app.models` **cannot be renamed.** Checked inside the running worker container: `app.models` fails too. The worker image ships **no ORM models at all** — `DeadLetterMessage`, `TaskRetry`, `Asset` and `FallbackPolicyModel` have no importable home there. Ledger **P2.60**.
* `ivgs_workers.config.get_db_session_factory` names a **function that does not exist** in `config.py` under any spelling. Ledger **P2.61**.

And the context that reframes both: `tasks/periodic_tasks.py`'s `get_beat_schedule()` **is never registered.** `celery_app.py` uses `CELERY_BEAT_SCHEDULE`, and the live DLQ processor is the HTTP-based `tasks.pipeline_orchestrator.process_dead_letter_queue`. Read from the running beat container. So `periodic_tasks.py` + `services/dlq_service.py` are a parallel, unreachable implementation of subsystems that are served elsewhere. That is a design question, not an import fix.

**Acceptance.** `test_all_levels_fail_routes_to_dlq` passes, and a new test proves the DLQ receives the **message**: queue, task name, both replay kwargs, exception type and message, `retry_count_exhausted`, and `FailureCategory.EXTERNAL` **by identity** against the real enum — which only imports if the module path is right. The old test asserted `assert_called_once()` and could not tell a correct hand-off from one that named the wrong queue.

---

## 4. Task 2 — P2.54, `media_type`

`models/task_result.py:240` declared `media_type: str = "image"`. `stage3_images.py:372` branches on `scene.media_type == MediaType.VIDEO_CLIP.value`, so a Stage 2 output of `"video"` — which is what the LLM writes, because the prompt asks in prose — fell to the else-branch and the scene rendered as a still. No exception, no warning, no failed job.

Coerced to `MediaType` through a **closed synonym table** (`video`/`video_clip`, `animated`/`animation`, `image`/`still`). Not a normaliser: no stripping beyond case, no `startswith`, no fuzzy match. Anything outside enum-plus-table is **rejected**. An open-ended normaliser is inference, and inference is what produced the defect. `duration_seconds` gains `gt=0`.

`use_enum_values` is deliberate: the field **validates** against the enum and **stores** the plain string, so the `temporal_pipeline.payloads` mirror declaring `media_type: str`, the `Counter` in `client.py:94`, the `== "image"` in `stage8_final_render.py:419` and anything interpolating the value into a path all see what they saw before. `validate_default` too, or `StoryboardScene()` stored the enum member while `StoryboardScene(media_type="image")` stored the string — one field, two types.

**Rejection is raised ahead of the constructor** in `_validate_storyboard_json`, not left to it. The `try/except` there skips a scene it cannot build and carries on, which for an out-of-taxonomy media type is wrong twice: it loses content the operator asked for, and it converts the model's new loud rejection straight back into a quiet one. The error names the offending value and the alternatives.

**Checked against live data before changing the receiver**, read-only: all **58** `storyboard_scenes` rows across 7 projects carry `image`/`video_clip`/`animation` and nothing else. No existing job becomes unreplayable.

A guard test asserts every `MediaType` member has a synonym-table entry — otherwise a new member would be rejected by its own name, a failure mode the rejection path itself introduces.

---

## 5. Task 3 — P2.55, the JSON extractor

`stage2_storyboard.py` searched for `[` before `{`, so a preambled `{"scenes": [...]}` returned the inner **array** and the wrapper was discarded.

Fixed by taking whichever delimiter **opens first** — the outermost structure — not by inverting the bias to `{` before `[`, which would have broken a bare top-level array with a preamble. There is a test for that case specifically.

The three extraction tests each asserted `"scenes" in result`, which a bare list also satisfies, so two passed and one failed and a shared defect read as one broken test. They are now parametrised over all three paths and compare against the payload itself.

### Did any stored storyboard lose fields? **No.**

The structural reason is the strong one: `_extract_json_from_response` is reached **only** on the `VLLMInvalidResponseError` recovery path, and its sole consumer is `_validate_storyboard_json`, which reads `scenes` and no other wrapper key. There was nothing on the wrapper for it to lose.

**The log evidence is weak and should not be leaned on:** zero `storyboard_json_parse_failed` events, but `ivgs-celery-default` restarted at 15:43 the same day, so the window is about three hours. Stated plainly rather than presented as corroboration. **No data changed.**

---

## 6. Task 4 — node-06

Measured from node-01 before changing anything: node-06 answers ICMP (0% loss) and serves node-exporter on **:9100**; **9400, 9401 and 9430 are all closed**. It is up and has never been provisioned. `nvidia-smi` reports **NVIDIA GeForce RTX 5080, 16303 MiB, driver 580.173.02**.

### 6.1 The correction already existed, and had for weeks

`dev/workpackages/WP-29-FLEET-ERRATA.md:28` records:

> `| node-06 | RTX 6000 Blackwell 96 GB | NVIDIA GeForce RTX 5080, 16303 MiB | WP-28 |`

The same figure, to the mebibyte, filed as an erratum by WP-29 and **never applied**. WP-24, WP-48 and WP-52 all went on quoting 96 GB afterwards. The card *was* swapped; what it was swapped to is a consumer 5080, **six times smaller** than anything written down. This is the more useful finding than the number itself: the errata mechanism produced the right answer and nothing consumed it.

### 6.2 Eight places, asserting five different sets of hardware

| Site | Claimed | Now |
|---|---|---|
| `nodes.py` `NODE_TOPOLOGY` | RTX 6000 Blackwell / 98304 / `verified False` | GeForce RTX 5080 / 16303 / `verified True` |
| `gpu_requirements.yaml` | "Intel Arc B70 Pro" / 32 GB / Battlemage | measured; **and its node-05 row held node-06's actual card** — the two rows had been transposed |
| frontend `GPU_LABELS` | **all five GPU rows wrong**: A6000 48 GB ×2, RTX 4090 24 GB ×2, Intel Arc A770 16 GB | measured values |
| `prometheus.yml` node-exporter | `gpu: intel-b70-pro` | `nvidia-rtx-5080` |
| `smoke/test_gpu_nodes.py` | docstrings + `_EXPORTER_PORT` 9401 | 9400 |
| `dev/CLAUDE.md` §2, `README.md` ×2, Master Sequence Plan | OFFLINE / RTX 6000 96 GB | measured, with the design consequence flagged |

Not one of the cards the frontend named is in this fleet. Its comment said *"per §3.2"*, which is how a set of invented values acquires a citation.

**`intel-gpu-exporter` job removed.** It scraped `node-06:9401` for an Intel card that is not there; Prometheus has reported it down for its whole life and no configuration change could have fixed it. node-06 now appears in the nvidia job on :9400, down until provisioning, so the target goes green the moment the operator acts. Coverage moved; it was not dropped.

### 6.3 node-01's dead targets — the premise was half right

Container DNS fixed **two of five**, verified live after `POST /-/reload`:

| Target | Was | Now |
|---|---|---|
| `ivgs-scheduler:8001` | DOWN (`context deadline exceeded`) | **UP** |
| `ivgs-node-exporter:9100` | DOWN | **UP** |

**No ufw call was needed**, contrary to the order's expectation. `ivgs-node-exporter` is on `ivgs-infra_ivgs-net`, not host networking, and runs with `--path.procfs=/host/proc --path.sysfs=/host/sys --path.rootfs=/rootfs` against host mounts — so container DNS reaches it and the metrics are the host's. Verified by scraping it from a peer container: 200, 108 KB.

This one matters beyond tidiness: `app/core/node_health.py` reads `up{job="node-exporter"}`, so **node-01 had been rendering as `unknown` in the Node Monitor** — the healthiest machine in the fleet, unable to observe itself. `up{node="node-01"}` is now 1.

**The other three are not networking problems and were left, annotated:**

* **`ivgs-api` serves no Prometheus endpoint at all.** No `prometheus_client` import, no `/metrics` route (compare `ivgs-scheduler/main.py:883`, which has one). Probed `/metrics`, `/api/metrics`, `/api/v1/metrics` on the live container — all 404. The published port is 8001, not the 8000 configured.
* **No `postgres-exporter` or `redis-exporter` container exists on this host.** `docker ps -a` has neither; they were never deployed.

Pointing those at container names would turn a timeout into a 404 and make them **look** addressed. Ledger **P2.62**.

### 6.4 Found while in the file: a critical alert that could never fire

`GPUOvertemperature` — severity critical, action *"page on-call"* — matched `nvidia_gpu_temperature_celsius` **OR** `intel_gpu_temperature_celsius`. **Neither series exists.** Queried against live Prometheus: the only GPU temperature series is `nvidia_smi_temperature_gpu`; `intel_*` returns nothing at all; `DCGM_FI_DEV_GPU_TEMP` is a stale name in the label index with zero live series.

GPU overtemperature has therefore never been alertable, and an alert matching nothing is indistinguishable from an alert whose condition is not met. Corrected. Safe to enable: the three live GPUs read **29–35 °C**. `promtool check config`: both files valid. Rule health: `ok`, state `inactive`.

**Also found, NOT fixed:** five `dashboard:` annotations in `alert_rules.yml` are junk image URLs — a YouTube thumbnail, Grafana and Citrix marketing screenshots, a Google user-content blob, a CoreWeave docs image — two with a dangling `$labels.node }}` fragment. These are operator-facing. I did not invent replacement URLs because I do not know the real dashboard UIDs and a guessed link is worse than an obviously broken one. Ledger **P2.63**.

---

## 7. Task 5 — the export seam

MBCP amended the bundle on 2026-08-21 (WP-E32-R) to carry `request_constraints`. IVGS's `ExportBundleIn` had no such field and carried `extra="ignore"`, so every bundle since has been accepted with a 201 and the field binned in silence.

### 7.1 Verified against MBCP's code, not the work order — and it changed the fix

The read-only clone at `/opt/MBCP` was pinned at `ea7f91e` (2026-08-05), **sixteen days before the amendment**, and contained no `request_constraints` anywhere. A first `git fetch` appeared to fail on the network; it was the credential prompt hanging. Re-run with `GIT_TERMINAL_PROMPT=0` and read at `origin/main` = `156ddb4`. The clone's working tree and HEAD are untouched — no commits there, per CLAUDE.md §11.

Two corrections to the order's premise, both material:

* It cites `export.py:70`. The declaration is at **line 82**.
* It says MBCP *"populates it on every export"*. **It does not.** `mbcp_core.request_constraints()` returns `None` for any model with no declared rule — MBCP's own tests pin that for FLUX.1-dev and for unregistered names — and the field is declared `dict | None = None`. **Most exports carry an explicit `null`.**

That second point nearly shipped a worse defect than the one being fixed. My first cut typed the field `dict` with a `default_factory`, which would have **422'd every bundle carrying an explicit null** — a silently-dropped field traded for a rejected export. There is now a test named for exactly that.

`None` and `{}` are kept distinct, in MBCP's words: *"An empty block would be the claim 'we checked'; a missing one is the truth 'we have declared nothing'."* IVGS stores NULL for a null and never substitutes an empty object, on create or on re-cert.

### 7.2 (a) A column, not a `default_params` key

Four MBCP-sourced facts already ride in `models.default_params`, so a fifth key would have needed no migration. It would also have been wrong, twice:

1. `default_params` are **defaults** a caller may override; these are **constraints** a caller must satisfy. One careless read across that line *is* the failure MBCP documented — a consumer reads `quality_summary.performance.resolution` (a MEASURED 1920×1080 for Wan2.2-T2V), builds a request from it, and reproduces a 135/134 sampler failure holding MBCP's certificate. WP-47's scenario, named by the sender in advance.
2. The block **contains a nested `default_params`** of legal defaults. The two would collide by name.

Migration **0029**, JSONB, nullable, opaque. Carried, stored, surfaceable, **not interpreted** — WP-53's stated scope. The real block leads with an honesty label: `kind: "declared"`, `declared_by`, `declared_on`, then optional `geometry`, `frame_count_rule`, `value_rules`, `default_params`.

### 7.3 (b) `extra="allow"` + a record, argued

**`extra="forbid"` is wrong here, for a reason specific to this seam.** AD-04 seam 1 is an MBCP-initiated **PUSH** and IVGS is a receiver (CLAUDE.md §11.1). MBCP amends the bundle unilaterally and has done so at least twice. Under `forbid`, the next amendment would 422 **every** certification export until someone on this side shipped a schema change — a silent drop traded for a **total ingest outage the sender cannot clear**. For a receiver that does not control the contract, availability of the seam beats strictness at its edges.

`allow` + a recording path is what *"must produce a record, not silence"* actually asks for. An unknown field now costs a WARNING naming the fields and a **durable** record on the row (`default_params._unknown_export_fields`), and the bundle still lands. Logged **before** the replay branch can return, so a re-send of a drifted bundle still says so. A test pins the `forbid` decision so a future change has to argue with the reasoning rather than discover the outage.

**Acceptance:** a bundle carrying `request_constraints` round-trips to the store row (verbatim, including the nested key, and not into `default_params`); an unknown field produces a log line naming it. 19 tests in that module, all passing.

### 7.4 Migration applied

`ivgs_reconciliation_test` and **live `ivgs`**, 0028 → 0029. Additive and nullable: 18 existing model rows, all NULL, **no data changed**. Verified the **running** image is unaffected — it queries `models` fine (18 rows) and `/health` is 200 — because the deployed ORM does not name the new column. The DB being ahead of the image is the safe direction for an additive column, and it means the eventual deploy cannot 500 on a missing column.

---

## 8. The deploy — NOT performed, and why

The order asked for a node-01 deploy under WP-34 rules, versioned as one coherent set (`v5.12.0-correctness`). **I could not complete it, and I did not do half of it.**

**node-01 holds no container-registry credentials.** There is no `~/.docker/config.json`. `ghcr.io/v2/` answers 401 unauthenticated, and no push is possible. I did not go looking for a token to repurpose.

I could have built locally and recreated the node-01 containers against a tag that exists only on this machine. I chose not to, for two reasons:

1. Nodes 02/03/04 need the same worker image, and their rebuild is an operator job by this order's own rules. A tag that cannot leave node-01 cannot be pasted into those blocks, so the fleet would be split across two meanings of `v5.12.0-correctness`.
2. That is precisely the class of confusion CLAUDE.md §6 is written about — *"Never read a tag variable out of a container and believe it."* Creating an unreproducible tag to satisfy a checkbox would make the next package's ground-truth check harder, not easier.

Everything a deploy needs is done and verified: code committed, migration applied to both databases, tests green. The block below is complete and gated. **Decision D-3.**

### 8.1 Operator block — build, push, deploy node-01

```bash
# node-01
cd /opt/ivgs && \
echo "$GHCR_PAT" | docker login ghcr.io -u brucecostello2 --password-stdin && \
docker build -t ghcr.io/brucecostello2/ivgs-api:v5.12.0-correctness     -f ivgs-api/Dockerfile     . && \
docker build -t ghcr.io/brucecostello2/ivgs-workers:v5.12.0-correctness -f ivgs-workers/Dockerfile . && \
docker push ghcr.io/brucecostello2/ivgs-api:v5.12.0-correctness && \
docker push ghcr.io/brucecostello2/ivgs-workers:v5.12.0-correctness && \
sed -i 's/^IVGS_API_TAG=.*/IVGS_API_TAG=v5.12.0-correctness/;s/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.12.0-correctness/' ivgs-infra/.env && \
grep -E '^IVGS_(API|WORKERS)_TAG=' ivgs-infra/.env && \
docker compose \
  -f ivgs-infra/docker-compose.node01.yml \
  -f ivgs-infra/docker-compose.override.node01.yml \
  -f ivgs-infra/docker-compose.monitoring.yml \
  --env-file ivgs-infra/.env \
  up -d --no-deps fastapi celery-default celery-composition celery-beat && \
sleep 15 && \
for c in ivgs-fastapi ivgs-celery-default ivgs-celery-composition ivgs-celery-beat; do \
  echo "$c -> $(docker inspect $c --format '{{.Config.Image}}')"; done && \
curl -s -o /dev/null -w "health:%{http_code}\n" http://192.168.1.90:8001/api/v1/health
```

Migration 0029 is **already applied** to `ivgs`; do not re-run it. `--no-deps` is mandatory or Postgres restarts (CLAUDE.md §6). Verify the image with `docker inspect`, never with `docker exec env` — the service-level `env_file` injects stale `IVGS_*_TAG` values.

### 8.2 Operator block — nodes 02/03/04 worker rebuild

Run **after** the push above succeeds. One node at a time.

```bash
# node-02  (then repeat on node-03 = 192.168.1.92, node-04 = 192.168.1.93)
cd /opt/ivgs && \
sed -i 's/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.12.0-correctness/' ivgs-infra/.env && \
docker compose -f ivgs-infra/docker-compose.node02.yml --env-file ivgs-infra/.env pull celery-worker && \
docker compose -f ivgs-infra/docker-compose.node02.yml --env-file ivgs-infra/.env up -d --no-deps celery-worker && \
sleep 10 && docker inspect ivgs-celery-worker --format '{{.Config.Image}}'
```

**node-05 is OUT OF SERVICE — do not run this there.** node-04's `celery-worker` has a `depends_on: comfyui`; `--no-deps` is what keeps the recreate off the engine.

### 8.3 Operator block — provision node-06 telemetry

node-06 has **no `/opt/ivgs`**. It needs the repo (or at least `ivgs-infra/docker-compose.telemetry.yml`) before this runs. Nothing in WP-53 touched node-06.

```bash
# node-06 (192.168.1.95) — after /opt/ivgs exists there
cd /opt/ivgs && \
docker compose -f ivgs-infra/docker-compose.telemetry.yml up -d && \
sleep 10 && \
curl -s -o /dev/null -w "gpu-exporter:%{http_code}\n" http://127.0.0.1:9400/metrics && \
curl -s -o /dev/null -w "node-logs:%{http_code}\n"    http://127.0.0.1:9430/containers/json?limit=1
```

Then from **node-01**, confirm the target Prometheus is already configured for goes green:

```bash
# node-01
curl -s 'http://127.0.0.1:9090/api/v1/targets?state=any' \
  | grep -o '"scrapeUrl":"[^"]*node-06:9400[^"]*"[^}]*"health":"[a-z]*"'
```

No `prometheus.yml` change is needed — node-06:9400 is already registered and waiting.

**No ufw call is required for node-01's node-exporter.** The order anticipated one; measurement says otherwise (§6.3). None is provided, deliberately, rather than shipping a command that does nothing.

---

## 9. Ledger — new entries

**P2.60 — the worker image ships no ORM models.** Five deferred imports of `ivgs_api.app.models` (`dlq_service.py:725`, `fallback_chain.py:247`, `motion_graphics.py:531`, `retry_engine.py:388,433`) plus one of `ivgs_api.app.database`. Checked inside the running container: `app.models` fails too, so this is not a rename — `DeadLetterMessage`, `TaskRetry`, `Asset` and `FallbackPolicyModel` have no importable home in `ivgs-workers`. Repair is a design call: move the model definitions into `shared/`, or rewrite those five call sites against the API over HTTP as `pipeline_orchestrator.py` already does. Note `fallback_chain.load_policies` swallows its failure in a `try/except` and falls back to `DEFAULT_FALLBACK_POLICIES`, so DB-held policies have never loaded — a swallow-register candidate.

**P2.61 — `ivgs_workers.config.get_db_session_factory` does not exist.** Eight deferred imports in `tasks/periodic_tasks.py` name `ivgs_workers.*`; five of those want a function `config.py` has under no spelling. Compounding it: that module's `get_beat_schedule()` is **never registered** — `celery_app.py` uses `CELERY_BEAT_SCHEDULE` and the live DLQ processor is `tasks.pipeline_orchestrator.process_dead_letter_queue`. `periodic_tasks.py` and `services/dlq_service.py` are a parallel, unreachable implementation of subsystems served elsewhere. Decide whether they are the future or the past before repairing their imports.

**P2.62 — three node-01 Prometheus targets are dead for non-network reasons.** `ivgs-api` exposes no `/metrics` at all (no `prometheus_client`, three paths probed, all 404) — the fix is code. `postgres-exporter` and `redis-exporter` have no container on this host — the fix is deployment. All three left configured and annotated so the gap stays visible.

**P2.63 — five `dashboard:` annotations in `alert_rules.yml` are junk image URLs.** A YouTube thumbnail, Grafana/Citrix marketing screenshots, a Google user-content blob, a CoreWeave docs image; two carry a dangling `$labels.node }}` from a mangled template. Operator-facing, on critical alerts. Not fixed: real dashboard UIDs unknown here, and a guessed link is worse than an obviously broken one.

**Closed by this package:** **P2.50** (§3), **P2.54** (§4), **P2.55** (§5), and the repairable half of **P2.40** (§6.3).

---

## 10. Decisions needed

**D-1 — node-06's role does not survive its hardware.** AD-02 gave it an on-demand fp8-70B LLM-failover leg **and** a second-CUDA-video-node role (CogVideoX 5B / Wan2.1), both sized against 96 GB. The card is 16 GB. I corrected every measured fact and **deliberately left the role string saying "failover"** in `NODE_TOPOLOGY`, so the contradiction stays visible instead of being quietly rewritten. This is an AD-02 re-ruling, and it is yours.

**D-2 — node-04 is a 96 GB card declared as 48 GB.** Live Prometheus reports `NVIDIA RTX PRO 6000 Blackwell Workstation Edition` / **97887 MiB** for node-04, while `NODE_TOPOLOGY` declares `RTX 5000 Pro Blackwell` / 49152. `dev/CLAUDE.md` §2 is the only document that had it right. **Not corrected here**: node-04 is live and serving, and `total_vram_mb` feeds admission decisions — changing a live GPU node's declared capacity is a scheduling change, not a documentation fix. The frontend labels now show the measured 96 GB and say so, with the contradiction named in a comment.

**D-3 — the deploy is blocked on registry credentials, §8.** No `~/.docker/config.json` on node-01. I declined to build a tag that could exist only on this machine. Blocks §8.1 and §8.2; §8.3 (node-06) is independent of it.

**D-4 — was fetching `/opt/MBCP` acceptable?** The clone is declared READ-ONLY and I ran `git fetch origin main` on it to verify the seam contract, which moved `origin/main` from `ea7f91e` to `156ddb4`. No commits, no checkout, HEAD and working tree unchanged. It was the difference between implementing a verified contract and a described one — and it caught a bug that would have 422'd most exports (§7.1). If the read-only rule is meant to forbid fetching too, say so and I will note it for future packages.

---

## 11. Verification — observed vs inferred

**Observed live, with output:**

* All five trees re-run; zero new failures against the baseline.
* `ivgs-api` 843 passed / 0 failed. `ivgs-workers` 766 / 18.
* Prometheus target health before and after reload: 6 up/10 down → 10 up/6 down; `up{job="node-exporter", node="node-01"}` = 1.
* `promtool check config` on both edited files: valid. `GPUOvertemperature` rule health `ok`.
* node-06 reachability and open/closed ports, probed from node-01.
* node-04 / node-02 / node-03 GPU names and VRAM from live `nvidia_smi_gpu_info`.
* `ivgs_workers` and `app.models` unimportable **inside** the running worker container.
* Live beat schedule keys read from `ivgs-celery-beat`.
* Migration 0029 applied to both databases; 18 model rows, all NULL; running API unaffected (`/health` 200, 18 rows queried).
* `request_constraints` read at MBCP `origin/main` = `156ddb4`.
* 58 `storyboard_scenes` rows, all in taxonomy — checked before tightening the receiver.

**Not observed, and not claimed:**

* **Nothing was deployed.** The fixes are in the tree and the images still run `v5.11.0-apibatch`. No claim is made about their behaviour in the fleet.
* node-06 was not provisioned and not logged into. Everything about it was measured from node-01 or read from Prometheus.
* node-05 was not deployed to, read from, or scheduled on. Its two down targets are left down.
* The three-hour log window behind §5's "no `storyboard_json_parse_failed` events" is too short to prove much; the structural argument carries that finding, not the logs.
* Whether MBCP's `request_constraints` block will ever contain shapes beyond those in its current source — the field is carried opaquely for that reason.

---

## 12. Commits — HELD, not pushed

```
dd31f7e  feat(wp-53): the export seam carries request_constraints, and reports what it cannot
02504a3  fix(wp-53): node-06 is online, and it is a 5080, not a 6000
84ddb02  fix(wp-53): P2.54 and P2.55, Stage 2 stops inferring and stops discarding
723e74e  fix(wp-53): P2.50, the DLQ hand-off that has never worked
605c817  docs(wp-53): the baseline's scheduler table double-counted one test
```

plus the documentation commit carrying this report.

### Push block — count-gated

Run on **node-01**. Refuses unless exactly **6** commits are ahead of `origin/main` and all six are WP-53, so a stale or partial tree cannot be pushed by accident.

```bash
# node-01
cd /opt/ivgs && git fetch origin && \
AHEAD=$(git rev-list --count origin/main..HEAD) && \
WP53=$(git log --oneline origin/main..HEAD | grep -c 'wp-53') && \
echo "ahead=$AHEAD wp53=$WP53" && \
if [ "$AHEAD" -eq 6 ] && [ "$WP53" -eq 6 ]; then \
  git log --oneline origin/main..HEAD && \
  git push origin main && echo "PUSHED"; \
else \
  echo "REFUSING: expected 6 commits ahead, all WP-53; got ahead=$AHEAD wp53=$WP53"; \
fi
```

Nothing has been pushed. `dev/workpackages/WP-45-gpu-registry-backup-20260825-170853.txt` is WP-45's untracked artefact and was left alone.
