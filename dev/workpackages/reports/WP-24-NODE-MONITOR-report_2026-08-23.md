# WP-24-NODE-MONITOR — report

| | |
|---|---|
| **Package** | `dev/workpackages/WP-24-NODE-MONITOR.md` |
| **HEAD at start** | `f70d63e17459f491334aab0c057dc5f06887891c` (tree clean, `HEAD == origin/main`) |
| **Date** | 2026-08-23 |
| **Ledger** | P2.22 (`/api/v1/nodes` hardcodes `status="online"`), P2.6 / P2.6a / P2.6b (GPU telemetry, exporter crashloop, empty heartbeat registry), P2.39 |
| **Tier** | B, Track P. Run alone in this tree; WP-23 (the other frontend package) runs after it, sequentially, per WP-QUEUE. |
| **Fleet** | `v5.6.0-m2` on all four nodes (`reports/WP-34-DEPLOY-BATCH-report_2026-08-23.md`) |

**Deviations from WP-QUEUE common rules, by explicit operator instruction (overnight batch).**
Rule 1 ("no commit") is overridden: this batch is *commit-and-HOLD per package, explicit-path
commits, no push*. Rule 5 ("no commands on any node other than node-01") is relaxed to
**read-only `ssh root@` on nodes 02/03/04** for measurement only. Nothing was written on any
node by this package. Both are recorded here so the exceptions are visible rather than assumed.

---

# PASS 1 — findings

## 1.1 The stub, re-verified at HEAD

The brief cites `nodes.py:82`, audited at `e613e844`. At `f70d63e` the file is
`ivgs-api/app/api/v1/nodes.py`, 122 lines, and the stub is at **two** sites, not one:

| Site | Line | Code |
|---|---|---|
| `list_nodes` | **`nodes.py:83`** | `"status": "online",  # Stub — real status from GPU scheduler in Phase 8` |
| `get_node` (detail) | **`nodes.py:111`** | `"status": "online",` — no comment, easy to miss |

Both return `used_vram_mb: 0`, `gpu_utilization_pct: 0.0`, `temperature_c: 0.0` unconditionally
(`nodes.py:85-87`, `:112-115`), and the detail route adds `power_draw_w: 0.0` (`:116`).
`NODE_TOPOLOGY` (`nodes.py:23-66`) is a hardcoded dict of six nodes.

**The zeros are the more dangerous half of this defect.** A wrong status is one word; six GPU
cards reporting "VRAM 0.0 / Util 0% / Temp 0 C" reads as *measured idle hardware*. It is not a
reading at all — no code path has ever written those fields.

The frontend faithfully renders the lie and adds one of its own:
`ivgs-frontend/src/app/nodes/page.tsx:92-99` computes the counter as
`nodes.filter(n => n.status === "online").length`, so "6 online | 0 offline" is arithmetic over
six hardcoded strings. `NodeCard.tsx:44-47` divides `used_vram_mb / total_vram_mb` and draws a
0%-width bar; `:112` gates the VRAM block on `total_vram_mb > 0`, which is topology, not
telemetry — so a card shows a VRAM *bar* for a node it has never measured.

## 1.2 Data path — what exists, measured

**Verified live** (all of this section):

| Source | Endpoint | State |
|---|---|---|
| GPU scheduler heartbeat registry | `http://192.168.1.90:8002/fleet` | **HTTP 200, and empty**: `total_nodes:0, alive_nodes:0, total_vram_mb:0, nodes:[]`, with `queue_depth.urgent:23` stranded |
| Scheduler routes | `/openapi.json` | `/register`, `/heartbeat`, `/schedule`, `/drain/{node_id}`, `/fleet`, `/reservations/{id}`, `/health`, `/metrics` |
| Prometheus | `http://prometheus:9090` from inside `ivgs-fastapi` | **reachable, HTTP 200** |

The scheduler **has** `/register` and `/heartbeat` and **nothing calls them** — that is P2.6b,
and it is why `/fleet` is empty. Fleet-wide heartbeat registration is explicitly out of this
brief's scope (M4). So the registry is not a usable source today.

**Prometheus `up`, read live:**

| job | node-01 | node-02 | node-03 | node-04 | node-05 | node-06 |
|---|---|---|---|---|---|---|
| `node-exporter` | **0** | **1** | **1** | **1** | 0 | 0 |
| `nvidia-gpu-exporter` | (no target) | 0 | 0 | 0 | 0 | — |

The scrape *errors* carry more signal than the `up` value, and the distinction is the whole
basis of the fix:

- node-05, node-06 → `dial tcp 192.168.1.94/.95:9100: connect: no route to host` — **genuinely down**
- node-02/03/04 `:9400` → `connect: connection refused` — **host up, nothing listening**
- node-01 (every one of its targets) → `context deadline exceeded` — **a timeout, not a refusal**

## 1.3 node-01 is not down; its own firewall hides it from its own Prometheus

`ufw` on node-01 is active and admits `192.168.1.0/24` to the host. The Prometheus container
sits on the `172.x` compose bridge, so its scrape of `node-01:9100` is dropped, not refused —
hence the timeout. Reproduced from inside `ivgs-fastapi`:

```
node-01:9100        rc=28 (timeout)      <- self, via the host's published port
192.168.1.90:9100   rc=28 (timeout)      <- same, by IP
node-02:9100        http=200
node-03:9100        http=200
node-04:9100        http=200
node-05:9100        rc=7                 <- genuinely unreachable
node-06:9100        rc=7                 <- genuinely unreachable
```

**This is the same firewall shape WP-34 hit on node-02** (a container cannot reach its own
host's published port; cross-node is fine because it is SNAT'd to a `192.168.1.x` source).
It means *any* probe that leaves the API container — Prometheus `up`, a direct TCP dial, ICMP —
has an identical blind spot on **node-01 only**. A naive `up`-based status would report the
healthiest node in the fleet as offline: a new lie, pointing the other way.

## 1.4 GPU telemetry does not exist anywhere on this fleet today

**P2.6a, root cause captured** — `docker logs ivgs-nvidia-gpu-exporter` on node-03:

```
panic: descriptor Desc{fqName: "nvidia_smi_power_smoothing_window_multiplier [ms]", ...}
  is invalid: "nvidia_smi_power_smoothing_window_multiplier [ms]" is not a valid metric name
    ... prometheus.MustRegister ... main.main()
exit code 2, finished 2026-06-02T13:30:45Z
```

`utkuozdemir/nvidia_gpu_exporter:1.2.1` auto-discovers every field `nvidia-smi --help-query-gpu`
advertises. The current driver advertises `power_smoothing.window_multiplier [ms]`, whose name
contains a space and brackets, so the derived metric name is invalid and `MustRegister` panics
**at startup**. It is not a crash*loop* any more — it is simply dead, and has been for 82 days.

Per-node state, measured:

| Node | Exporter in compose? | Container | Result |
|---|---|---|---|
| node-01 | no target at all | none | no GPU (correct — CPU hub) |
| node-02 | yes (`docker-compose.node02.yml:244`) | **none exists** | `:9400` connection refused |
| node-03 | yes | exists, **Exited(2) since 2026-06-02** | `:9400` connection refused |
| node-04 | **REMOVED** — `docker-compose.node04.yml:13`: *"nvidia-gpu-exporter REMOVED (utkuozdemir 1.2.1 invalid-metric-name crashloop…)"* | none | `:9400` connection refused |

**So there is no node, including node-04, from which VRAM/util/temp can be read today without
first deploying something to that node.** Tonight's instruction forbids deploying to 02/03/04.
See D-3.

## 1.5 The topology dict is wrong about the hardware

Measured via `nvidia-smi` (read-only ssh):

| Node | `NODE_TOPOLOGY` claims | Measured 2026-08-23 |
|---|---|---|
| node-02 | RTX 6000 Blackwell, 98304 MB | **RTX PRO 6000 Blackwell Workstation Edition, 97887 MiB**, 88490 used, 0%, 30 C |
| node-03 | RTX 6000 Blackwell, 98304 MB | **RTX PRO 6000 Blackwell Workstation Edition, 97887 MiB**, 20710 used, 0%, 29 C |
| node-04 | **RTX 5000 Pro Blackwell, 49152 MB** | **RTX PRO 6000 Blackwell Workstation Edition, 97887 MiB**, 38316 used, 0%, 32 C |

node-04 is declared at **half its real VRAM and the wrong card**. Any scheduler or operator
reading capacity off this page would size a job against 48 GB on a 96 GB card. node-05 and
node-06 are offline and their entries are unverifiable claims — node-06's in particular is
stale, since CLAUDE.md §2 records its card was swapped to an RTX 6000 96 GB.

## 1.6 Proposed fix

**In `ivgs-api/app/api/v1/nodes.py`:**

1. `status` derives from a real check, with the basis named in the payload:
   - **node-01 = `online`, basis `self`** — this API process runs on node-01; if it answers, node-01 is up. Not a probe, a tautology, and labelled as one (see D-2).
   - **all others** from Prometheus `up{job="node-exporter"}` plus scrape freshness → `online` / `offline`, basis `node-exporter-scrape`.
   - **Prometheus unreachable or the query fails → `unknown`, basis `probe-unavailable`.** Never `offline` on a failed probe: "we could not tell" and "it is down" are different facts, and collapsing them is the defect this package exists to remove.
2. GPU metric fields become **nullable** and are populated only from a real reading. With the exporter dead fleet-wide they are `null` today. No field is ever `0` unless `0` was measured.
3. Each node carries a `telemetry` block: `{available, source, reason, as_of}` so the UI can say *why* there is no data.
4. `total_vram_mb` stays declared topology but is corrected to measured values, and is labelled `vram_total_mb_declared` so it is never mistaken for a reading.

**In the frontend:** nullable metrics + `unknown` status in `types/api.ts`; `NodeCard` renders
"no data" with the reason instead of zeros, and draws the VRAM bar only when a real reading
exists; the page counter derives from real statuses and reports `unknown` separately.

**Not touched:** the scheduler, the heartbeat registration work (M4), any node's configuration.

## 1.7 Decisions recorded (operator unattended — not blocked on)

- **D-1 — node-07 (.96) does NOT appear on the Node Monitor.** Measured: `.96` answers ICMP (0% loss) but refuses my SSH key, so it is up and not administrable from here. Per `WP-31-TEMPORAL-GROUNDWORK.md:5,8` it hosts the **Temporal cluster only**, with its own Postgres, and is not a pipeline node — no queue, no GPU, no stage service. Adding it would put a host with no pipeline role into the "N online" denominator and misstate fleet capacity. `WP-QUEUE.md:46` also lists the node-07/host-capacity decision as operator-only. **It is excluded, and the exclusion is deliberate rather than an oversight** — it belongs in a Temporal/infra view under M3, not here. Reversible in one dict entry if the operator disagrees.
- **D-2 — reachability source is Prometheus `up{job="node-exporter"}`, not ICMP.** Prometheus already scrapes all six nodes every scrape interval, is already deployed, and is reachable from the API container (verified, HTTP 200). ICMP would need `CAP_NET_RAW` in the API container; a direct TCP fan-out would add up to six dials to an endpoint polled every 10 s and would duplicate what Prometheus already does — **and it would share the identical node-01 blind spot**, so it buys nothing. Stated limitation, in the payload: *online here means this node's node-exporter answered Prometheus recently*, which is a proxy for the host, not the host itself.
- **D-3 — the exit gate's node-04 GPU clause is NOT met, and cannot be met tonight.** No exporter exists on node-04 (removed from its compose), none runs on node-02, and node-03's is dead. Fixing it requires editing a node's compose and recreating a container **on that node**, which tonight's instruction forbids (02/03/04 are not deployed). An operator deploy block is supplied in Pass 2 §2.5, with the `--query-gpu-fields` fix that addresses the panic in 1.4 without changing the image. Until it runs, every GPU field reads "no data — GPU exporter not running on this node", which is true.
- **D-4 — node-01's ufw is NOT changed.** Fixing Prometheus's view of node-01 would mean opening the host firewall to the docker bridge. The operator ruled against exactly that change on node-02 on 2026-08-23 (P1.4p, ruling 1). The same reasoning is applied here rather than quietly doing the opposite on a different node: node-01's status uses the `self` basis instead. Recorded so the asymmetry is visible.
- **D-5 — node-05/node-06 topology entries are left as declared,** flagged `unverified`. They are offline; correcting hardware claims for machines that cannot be measured would be substituting one unverified claim for another. CLAUDE.md §2 says node-06's card was swapped to an RTX 6000 96 GB, which contradicts the dict — recorded, not silently "fixed".

---

# PASS 2 — what changed, and how it was verified

## 2.1 Change summary

```
 ivgs-api/app/core/node_health.py           | NEW  (~250 lines)
 ivgs-api/app/api/v1/nodes.py               | stub removed, topology corrected
 ivgs-api/tests/test_wp24_node_honesty.py   | NEW  12 tests
 ivgs-api/tests/test_api_nodes.py           | docstring only - no assertion changed
 ivgs-frontend/src/types/api.ts             | nullable metrics, unknown status, telemetry
 ivgs-frontend/src/components/NodeCard.tsx  | honest empty states
 ivgs-frontend/src/app/nodes/page.tsx       | counters derive from real statuses
```

**`app/core/node_health.py`** — new. Queries Prometheus, returns one of
`online` / `offline` / `unknown` per node with `status_basis` and `status_reason`, plus
nullable GPU metrics and a `telemetry` block explaining their presence or absence.
`collect_fleet_health()` never raises: it degrades to `unknown`, which is a truthful answer.

**`app/api/v1/nodes.py`** — both stub sites (`:83` list, `:111` detail) removed; both routes
now share `_node_payload()`. Declared topology and observed telemetry are separate fields, so
`total_vram_mb` (a claim) can never be mistaken for `used_vram_mb` (a reading). Hardware
corrected per 1.5. Added `GET /api/v1/nodes/health-notes`, registered **before** `/{node_id}`
so the literal path wins the match.

**Frontend** — `used_vram_mb` / `gpu_utilization_pct` / `temperature_c` are `number | null`;
`NodeCard` renders "no data" per cell and shows the reason; the VRAM bar is gated on a real
reading rather than on `total_vram_mb > 0`, and with no reading it draws a **dashed rail**
rather than a 0%-full bar — an empty bar reads as "measured and idle", which is the same lie
in a different medium. `unknown` renders **grey, not red**: colouring it like offline would
have re-created the collapse in CSS after removing it from the JSON.

## 2.2 Verified live

`collect_fleet_health` executed **inside the running `ivgs-fastapi` container** against the
real Prometheus:

```
node-01  online   basis=self                  reason: this API process runs on node-01
node-02  online   basis=node-exporter-scrape  reason: node-exporter answered the last scrape
node-03  online   basis=node-exporter-scrape
node-04  online   basis=node-exporter-scrape
node-05  offline  basis=node-exporter-scrape  reason: node-exporter did not answer
node-06  offline  basis=node-exporter-scrape

online: [node-01..04]   offline: [node-05, node-06]   unknown: []
GPU metrics: all None on every node
```

**node-05 and node-06 report offline against the live fleet.** That is the headline exit-gate
clause, and it is met.

Degraded path, same container, `IVGS_PROMETHEUS_URL` pointed at a dead port:

```
online: [node-01]   offline: []   unknown: [node-02..06]
```

Nothing was reported `offline` on a failed probe.

**Latency, measured** — both the healthy and the dead-Prometheus path complete in **0.372 s**.
The first draft took up to 20 s when Prometheus was unreachable (5 queries x 4 s), which would
have been a self-inflicted defect on an endpoint the UI polls every 10 s. Fixed by
short-circuiting the four GPU queries once the reachability query has already failed, and
dropping the per-query timeout to 2 s.

## 2.3 Tests

`ivgs-api/tests/test_wp24_node_honesty.py` — **12 passed in 0.75 s**, hermetic
(`node_health._query` monkeypatched; no Prometheus contacted, no DB).

They pin properties, not readings, per P2.22's warning. Coverage: down nodes report offline;
a failed probe is `unknown` and never `offline`; a node with no scrape target is `unknown`;
the self node stays online when probing fails; every status carries a basis and a reason;
absent telemetry is `None` and never `0`; present telemetry converts bytes→MB and ratio→percent;
**a genuine `0.0` reading survives as `0.0`** (the fix must not overcorrect into hiding real
zeros); the wire payload never emits `0` for an unmeasured metric; node-04's corrected hardware;
offline nodes flagged `topology_verified: False`; node-07 absent.

**The tests were shown to discriminate.** Replaying the pre-fix payload (`nodes.py:83-87` at
`4d61cab`) through the same assertions fails 4 of them:

```
FAIL: node-04.used_vram_mb is 0; ... must be null, not a number
FAIL: node-04.gpu_utilization_pct is 0.0; ...
FAIL: node-04.temperature_c is 0.0; ...
FAIL: down-node test: node-05 would have to be offline
```

`test_api_nodes.py` was read and **kept**: it asserts shape, ids, auth and 404 only, and never
froze the stub's values. Only its docstring changed.

## 2.4 Not verified

- **The rendered page.** The running `ivgs-fastapi` still serves `v5.6.0-m2`, which carries the
  old `nodes.py`. The new code is verified by unit test and by executing the new module inside
  the running container against real Prometheus — but nobody has looked at the page. It renders
  after tonight's node-01 deploy; see the batch summary.
- **Real, changing GPU numbers.** Not obtainable — see D-3. No exporter runs anywhere.
- **`unknown` end-to-end through the UI.** The state is unit-tested and the CSS branch exists;
  it has not been seen in a browser.

## 2.5 Operator block — bring GPU telemetry back (NOT run by this package)

This is the fix for P2.6a. It restricts the exporter to an explicit field list so the
invalid-metric-name panic in 1.4 cannot occur, **without changing the image**. It requires a
compose edit and a container recreate **on node-04**, which tonight's instruction excludes.

Add to node-04's `docker-compose.node04.yml` (the service was removed at line 13; re-add it):

```yaml
  nvidia-gpu-exporter:
    image: utkuozdemir/nvidia_gpu_exporter:1.2.1
    container_name: ivgs-nvidia-gpu-exporter
    <<: [*common-restart, *common-logging, *gpu-resources]
    ports:
      - "0.0.0.0:9400:9400"
    networks:
      - ivgs-net
    command:
      # P2.6a: without an explicit field list the exporter enumerates every
      # nvidia-smi --help-query-gpu field. This driver advertises
      # "power_smoothing.window_multiplier [ms]", which cannot become a valid
      # Prometheus metric name, and MustRegister panics at startup.
      - "--query-gpu-fields=uuid,name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,clocks.current.graphics"
```

```
# RUN ON: IVGS node-04 (192.168.1.93)
( cd /opt/ivgs/ivgs-infra || exit 1
  cp -a docker-compose.node04.yml "docker-compose.node04.yml.bak-pre-gpuexp-$(date -u +%Y%m%d-%H%M%S)" || exit 1
  docker compose -f /opt/ivgs/ivgs-infra/docker-compose.node04.yml --env-file /opt/ivgs/ivgs-infra/.env config -q || { echo "ABORT: compose invalid"; exit 1; }
  docker compose -f /opt/ivgs/ivgs-infra/docker-compose.node04.yml --env-file /opt/ivgs/ivgs-infra/.env up -d --no-deps nvidia-gpu-exporter
  sleep 5
  docker ps --filter name=ivgs-nvidia-gpu-exporter --format '{{.Names}} {{.Status}}'
  curl -s --max-time 10 http://127.0.0.1:9400/metrics | grep -c '^nvidia_smi_' 
  echo "want: Up, and a non-zero metric count. If it exited, docker logs it - the panic line names the offending field."
) | tr -cd '\11\12\15\40-\176'
```

Verification once it runs (exit-gate clause for node-04), comparing two refreshes:

```
# RUN ON: IVGS node-04 (192.168.1.93)
nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader
sleep 20
nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader
# then compare against two /nodes refreshes; the numbers must track, and must change
```

`--no-deps` is mandatory on node-04 (its `celery-worker` declares `depends_on: [comfyui]`);
the block above names only the exporter, so no engine is recreated.

**Same fix applies to node-02 and node-03**, whose exporter services already exist in compose
— they need the `command:` block added and the container recreated. node-03's must also be
removed first, since a stopped container with the old config is present.

## 2.6 Exit gate

| Clause | Verdict |
|---|---|
| node-05 and node-06 show **offline** | **MET** — verified live against Prometheus |
| node-01 shows online / no-GPU | **MET** — `basis: self`, `gpu_model: null` renders "No GPU (Infrastructure)" |
| "N online" derives from real checks, not the stub | **MET** — and `unknown` is counted separately rather than folded into offline |
| Every remaining "no data" is labelled as such | **MET** — per-cell "no data" plus the reason on the card |
| node-04 shows **real, changing** VRAM/util/temp | **NOT MET** — see D-3. No GPU exporter runs anywhere on the fleet (P2.6a); fixing it needs a node-04 deploy, excluded tonight. Operator block supplied in 2.5. |

**Overall: exit gate PARTIALLY met.** The honesty half — the part that removes the false
assertion — is complete and verified. The telemetry half is blocked on a node-04 deploy that
this batch is not permitted to perform, and the page now says "no data" with the reason
instead of showing zeros, which is the correct behaviour until that block is run.

## 2.7 Swallowed-failure check (queue rule 7)

No new instance found in the files touched. The new code was written against the pattern
deliberately: `_query()` returns `None` on failure (distinct from `[]`, "Prometheus answered
and has no such series"), logs at `warning` with the expression and error, and every caller
branches on it. The `unknown` state exists precisely so a failure is not converted into a
confident value — the inverse of the swallow pattern.
