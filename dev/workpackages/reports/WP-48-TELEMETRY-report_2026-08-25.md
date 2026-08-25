# WP-48-TELEMETRY — report

| | |
|---|---|
| **Date** | 2026-08-25 |
| **Built from** | `5fbfe45` — clean tracked tree, `HEAD == origin/main` (`git rev-list --left-right --count` → `0  0`) |
| **Tag** | **`v5.9.0-telemetry`** — `ivgs-api` and `ivgs-frontend` only. Workers stay `v5.8.0-animation`; no engine touched anywhere. |
| **Nodes touched** | node-01 (api + frontend + a log source), node-02, node-03, node-04, node-05. node-06 offline, skipped. |
| **Outcome** | **All five exit gates met and verified live.** Four GPU nodes serve `nvidia_smi_*` from one tracked overlay, all four Prometheus targets UP, all four cards show VRAM/util/temp **and Power**. Per-node logs are real on all five online nodes. Task 4 verdict below. |
| **Repo state** | **Commit-and-HOLD.** Committed on `main`, **not pushed**. |

**Authorisation.** `dev/CLAUDE.md` §1 says Claude does not deploy and does not run commands
on nodes other than node-01 unless explicitly handed over. This package carries that
hand-over in its own text (Task 1: *"deployed to nodes 02, 03, 04, 05"*), on the WP-34 /
WP-DEPLOY-R2-R5 precedent. Recorded so the exception is visible rather than assumed.
Task 4 was executed **read-only** on both systems.

---

## S0. Verdicts

| Task | Verdict | One line |
|---|---|---|
| **1 — one tracked overlay, everywhere** | **PASS** | `ivgs-infra/docker-compose.telemetry.yml`, own compose project, on nodes 02/03/04/05. Four targets UP. Three untracked per-node files retired. **Closes ledger P2.6a.** |
| **2 — the Power column** | **PASS** | Root cause was neither the exporter nor Prometheus: `power_draw_w` was served only by the *detail* route while the card polls the *list* route. One field moved; Power is a real number on all four cards. |
| **3 — node logs** | **PASS, with its design stated** | The advertised endpoint never existed; the one that did could never have worked. Replaced with a per-node read-only log source + two API routes + a real panel. Polled tail, **not** a stream — said so on the panel. |
| **4 — AD-04 conformance** | **CONFORMS to the SSOT** — and the *rule as stated in the work order* does not. See S6. Ledgered **P2.41** for an operator ruling. Nothing implemented. |
| **5 — riders** | **PASS (operational docs), spec docs ledgered** | node-05 corrected everywhere it is operationally load-bearing; node-07 row added. AD-02 + functional spec left to change control → **P2.43**. |

**Five new ledger entries** — P2.40 (node-01's own Prometheus targets have all been down),
P2.41 (the AD-04 doctrine conflict), P2.42 (node-02's `vllm.service`), P2.43 (node-05 in the
specs), P2.44 (`wp42probe`). **P2.6(a) closed.**

---

## S1. Task 1 — one tracked overlay, deployed to four nodes

### 1.1 What replaced what

Three nodes had each independently grown an untracked `docker-compose.gpuexp.yml`. They were
**not the same file**: node-04's (835 B, 23 Aug) declared `networks: [ivgs-net]` and named its
container `ivgs-nvidia-gpu-exporter` inside the `ivgs-infra` project; node-02's and node-03's
(512 B, both written today) had no networks key and named it `ivgs-gpu-exporter` in a project
called `gpuexp`. Same intent, three configurations, none in version control.

**One file now:** `ivgs-infra/docker-compose.telemetry.yml`. Two properties in it are load-bearing:

* **`name: ivgs-telemetry`** — its own compose project, pinned in the file rather than trusted
  to a `-p` flag on the command line. `docker compose -f docker-compose.telemetry.yml up -d`
  on any node reaches exactly its two services and *cannot* recreate an engine. That is WP-34's
  additive rule expressed as configuration.
* **no `networks:` key** — deliberately, after node-02 (S2). The default project bridge is the
  one network that is always recreated together with the project.

The `--query-field-names` list is unchanged in substance from the working node-04 file and
**includes `power.draw`**. Auto-discovery is what panics on this driver; the restriction is the fix.

### 1.2 Per-node before / after

| Node | BEFORE | Action | AFTER |
|---|---|---|---|
| **node-02** (.91) | Container up, logging `Listening on [::]:9835`. `curl` on host 9400 → **empty**; `ss` → nothing listening; Prometheus → `connection refused`. | Backed up `gpuexp.yml`; `down` the orphaned `gpuexp` project; `up` the tracked overlay. | `0.0.0.0:9400` listening; 11 `nvidia_smi_*` series; target **UP**. |
| **node-03** (.92) | Working (operator's overlay today). 11 series. | Backed up; migrated to the tracked file. | 11 series; target **UP**; no gap in Prometheus. |
| **node-04** (.93) | Working, but inside the `ivgs-infra` project with the node-04 stack. 11 series. | Removed **only** that service (`compose rm -sf nvidia-gpu-exporter`); neutered the untracked file to `services: {}` so the label-derived invocation still resolves; `up` the tracked file. | 11 series; target **UP**; container renamed to the fleet-standard `ivgs-gpu-exporter`. |
| **node-05** (.94) | **No exporter, no containers at all, no `/opt/ivgs`.** | Created the path, shipped both files with a SHA gate, pulled images, `up`. | 11 series; target **UP**. |

**Engines provably not recreated.** Container IDs captured immediately before and after on
each node are byte-identical:

    node-02  ivgs-vllm-primary 6677d154b11f  ivgs-celery-node02 ec4bf927ac14  ivgs-node-exporter 0481646b82f7
    node-03  cogvideox-server bdd8a439fe12  cogvideox-worker 6ac707e8850c  wan-animate 776bb07a9f7e  node-exporter 8c14bdb4e814
    node-04  comfyui 432bec40fc0a  coqui 0067286d78d9  kokoro e720f215c865  whisperx a8905e7ef1ef
             latentsync 74e9916c9171  celery-node04 c326eab3def1  node-exporter ca673a7ec78b

**Files were shipped under a SHA gate** (`dev/CLAUDE.md` §5), identical on all four nodes:

    b01e21df…b20a8b  docker-compose.telemetry.yml
    b4c51a66…14395   configs/node-logs/nginx.conf

### 1.3 Exit gate — measured after deploy

    $ curl -s localhost:9090/api/v1/targets  | (job=nvidia-gpu-exporter)
      http://node-02:9400/metrics  up
      http://node-03:9400/metrics  up
      http://node-04:9400/metrics  up
      http://node-05:9400/metrics  up
      http://node-06:9401/metrics  down   (offline, expected)

    $ curl -s 'localhost:9090/api/v1/query?query=nvidia_smi_power_draw_watts'
      node-02 16.3 W   node-03 16.19 W   node-04 18.72 W   node-05 15.92 W

The Node Monitor half of the gate is in S3.3.

---

## S2. node-02 — the actual failure, which was not the one on the ticket

The brief framed node-02 as a publish/binding problem and suggested a daemon default bind IP.
It is neither. Measured on the box:

    $ docker inspect ivgs-gpu-exporter -f '{{json .HostConfig.PortBindings}}'
      {"9835/tcp":[{"HostIp":"0.0.0.0","HostPort":"9400"}]}      <- the publish IS declared

    $ docker inspect ivgs-gpu-exporter -f '{{json .NetworkSettings.Networks}}'
      {}                                                         <- and the container has NO network

    $ ss -lntp | grep 9400          -> nothing
    $ iptables -t nat -S DOCKER | grep 9400  -> nothing
    $ cat /etc/docker/daemon.json   -> only the nvidia runtime block; no "ip" default

`gpuexp_default` existed and had been created at **03:50:22**, *after* the container. The
network was removed and recreated underneath a running container, which left the container
with no endpoint — so docker never started a `docker-proxy`, never wrote a DNAT rule, and the
declared port binding was simply never realised. There was nothing to bind to.

**This is why the tracked overlay declares no network.** The default project bridge is
recreated with the project, so a `down`/`up` cannot leave this state behind.

**The lesson worth keeping:** *"the process is up and says it is listening"* and *"the port is
published"* are independent facts, and `docker ps` showing a container as `Up` with an empty
Ports column is the visible symptom of the second one being false.

### 2.1 Where `ivgs-dcgm-exporter` came from — traced

`/root/.bash_history` on node-02:

    378  docker run -d --rm --gpus all --cap-add SYS_ADMIN -p 9400:9400 --name dcgm-test \
           nvcr.io/nvidia/k8s/dcgm-exporter:4.5.3-4.8.2-distroless
    387  … :4.5.3-4.8.2-ubuntu22.04
    396  … :4.2.3-4.1.3-ubuntu22.04
    423  docker pull "nvcr.io/${REPO}@${DIGEST}" && docker run … && curl -s localhost:9400/metrics \
           | grep -E '^DCGM_FI_DEV_(GPU_UTIL|FB_USED|POWER_USAGE|GPU_TEMP)[ {]'
    449    dcgm-exporter:
    450      image: nvcr.io/nvidia/k8s/dcgm-exporter@sha256:a7ad6547…
    451      container_name: ivgs-dcgm-exporter
    476  Description=IVGS node-02 container stack (vLLM + dcgm + node-exporter)
    495  docker compose up -d dcgm-exporter node-exporter

A hand-run search for a Blackwell-capable exporter, pinned by digest, written into a compose
block and a systemd unit. It served `DCGM_FI_DEV_*` metric names — **which nothing in this repo
reads**; `node_health.py:76-81` queries `nvidia_smi_*` exclusively. So it held port 9400 for
hours while being invisible to the page it was meant to feed.

**Remnants, and what was done:**

| Remnant | State | Action |
|---|---|---|
| `ivgs-dcgm-exporter` container | already removed by the operator | — |
| dangling image `nvcr.io/nvidia/k8s/dcgm-exporter@sha256:a7ad6547…`, 928 MB (240 MB on disk) | present, no container referencing it | **removed** (`docker rmi`, untagged + deleted) |
| compose block, unit file, any `*dcgm*` path under `/opt /root /etc` | **none found** | — |
| `/etc/systemd/system/vllm.service` Description string | still names dcgm; unit `disabled` + `inactive` | **left alone**, ledgered **P2.42** — editing a systemd unit is outside an additive-exporter package, and there is a second, worse problem in it (see P2.42). |

---

## S3. Task 2 — the Power column

### 3.1 The chain, traced end to end

| Link | What is there | Verdict |
|---|---|---|
| exporter emits | `nvidia_smi_power_draw_watts{uuid=…}` — `power.draw` is renamed by the exporter | ✅ correct, and node-04 was serving it |
| Prometheus stores | `node-03 16.2`, `node-04 18.87` at the time of the check, before any change | ✅ present |
| API queries | `node_health.py:80` → `"power_draw_w": 'nvidia_smi_power_draw_watts'` | ✅ correct, and already being queried |
| API **serves** | `nodes.py:128-130` — `payload["power_draw_w"] = …` **inside `if detail:`** | ❌ **the defect** |
| page reads | `NodeCard.tsx:50` `typeof node.power_draw_w === "number"`, from `useNodes()` → `GET /api/v1/nodes` | ✅ correct — reading a field the list route did not send |

So every component was right and the fault was one field on the wrong side of an `if`. The
list route is what the card polls every 10 s; the detail route it was gated behind is called
only by `GET /nodes/{id}`, which nothing in the UI calls. Power read `no data` on a healthy
node for as long as this has stood.

**Note this is not a driver limitation.** The work order allowed for the card having to say
"N/A" if the driver genuinely reports nothing. It does not: all four cards report real watts.

### 3.2 The fix, and one thing added beyond it

`power_draw_w` moved out of the `detail` block and sits beside `used_vram_mb`,
`gpu_utilization_pct` and `temperature_c` — it is a measurement like the other three.
`NodeStatus.power_draw_w` in `types/api.ts` changed from optional to required to match.

Beyond the literal ask, `NodeCard.tsx` now distinguishes **two different absences**, because
the work order's own N/A question exposed that the card could not tell them apart:

* `telemetry.available === false` → nothing is measuring this node → **"no data"**
* `telemetry.available === true` but this field is null → the exporter is scraped and healthy
  and returned everything else → **"n/a"**, with a tooltip naming the driver

"no data" sends someone to debug an exporter. On a working exporter that is the wrong place,
and it is the same class of defect as WP-24's rendering-null-as-0 — a truthful number that
points at the wrong conclusion.

### 3.3 Exit gate — `GET /api/v1/nodes` on the deployed image, live

    node-01  online   vram=None      util=None  temp=None  POWER=None
    node-02  online   vram=88494.0   util=0.0   temp=31.0  POWER=16.32
    node-03  online   vram=41195.0   util=0.0   temp=29.0  POWER=16.29
    node-04  online   vram=11345.0   util=0.0   temp=33.0  POWER=19.31
    node-05  online   vram=2.0       util=0.0   temp=36.0  POWER=15.93
    node-06  offline  vram=None      util=None  temp=None  POWER=None

node-01 has no GPU; node-06 is off. Both correctly null rather than zero. **Task 1's card-side
gate and Task 2's gate are both met by this one response.**

---

## S4. Task 3 — node logs

### 4.1 Does the advertised endpoint exist? No. Nor could the one that did have worked.

The modal printed, verbatim:

    Live log streaming via WebSocket — connect to
    ws://node-01:8000/api/v1/nodes/{hostname}/logs/stream
    [Log output will appear here in real-time]

**`/api/v1/nodes/{id}/logs/stream` has never been a registered route on this app.** A
*different* one existed — `WS /api/v1/ws/nodes/{node_id}/logs` in `ws_logs.py` — and it could
not have produced a line either. It ran:

    cmd = f"ssh {host} '{docker_cmd} {tail}'"
    process = await asyncio.create_subprocess_shell(cmd, …)

from inside `ivgs-fastapi`. Measured 2026-08-25 in the running container:

    $ docker exec ivgs-fastapi sh -c 'command -v ssh; command -v docker'
    (both empty)

No `ssh` binary, no key, no `docker` CLI. The subprocess exits immediately, `readline()`
returns empty, the loop breaks, the socket closes having sent nothing — **and nothing raises**.
That is the WP-00 swallow shape exactly: a failure that renders as silence. The `<a download>`
to `/api/v1/nodes/{host}/logs/download` was equally fictional, and could not have carried the
Bearer token this API requires even if the route had existed.

**Both are removed** — route and advertisement — rather than left in place, and
`test_wp48_telemetry.py::TestTheDeadWebsocketRouteIsGone` pins the removal.

### 4.2 The design, and why this one

node-01 has **no SSH into the fleet as the service user** and the API container has no shell
access to anything. What node-01 *does* have is LAN reach to each node's published ports —
Prometheus already scrapes all of them. So the log source lives on the node, following the
exporter pattern, and is added to the same tracked overlay: one deploy per node, not two.

`ivgs-node-logs` is **nginx over that node's Docker socket with a positive two-route
allowlist** (`ivgs-infra/configs/node-logs/nginx.conf`):

    GET /containers/json           -> the container list
    GET /containers/<id>/logs      -> that container's logs
    everything else                -> 403

**The alternative I rejected, and why it matters.** The obvious implementation is to publish
the Docker socket, or `tecnativa/docker-socket-proxy` with `CONTAINERS=1`. Both grant
`GET /containers/<id>/json` — the inspect route, whose response contains `Config.Env`, i.e.
**every token and password each container was started with**. Trading that for a log pane is a
bad deal. The allowlist refuses inspect specifically, along with `/exec`, `/images`,
`/volumes`, `/info`, `/version`, and every method other than GET/HEAD. Verified on every node:

    list=200   inspect=403   info=403   POST /containers/json=403

**What it still is.** A LAN-reachable, unauthenticated read of container **names, images,
states and log text** on ports 9430. Log text can itself contain secrets if a service prints
one. This is an addition to the fleet's exposure and it is stated here rather than buried:
it sits behind the same perimeter as vLLM on `:8000`, ComfyUI on `:8188` and the exporters on
`:9400`, all already open. Narrowing it further (mTLS, a shared token, or a ufw allow-from
node-01 only) is a reasonable follow-up and needs an operator decision, not a silent choice.

**node-01 is the exception, again.** ufw admits only `192.168.1.0/24` to the host and the
compose bridge is `172.x`, so `ivgs-fastapi` cannot reach node-01's own published ports — the
same blind spot `node_health.py` documents for the reachability probe. node-01's source
therefore publishes **no host port**: `docker-compose.telemetry.node01.yml` attaches it to
`ivgs-infra_ivgs-net` and the API addresses it as `http://ivgs-node-logs:9430`. (This is also
the fix pattern P2.40 needs for the five dead node-01 scrape targets.)

### 4.3 What it is, honestly: a polled tail

`GET /api/v1/nodes/{id}/logs?container=&tail=` returns the last N lines. The panel re-fetches
every 3 s. **It is not a stream**, and the panel says so on its own status line — *"polled tail
— last 300 lines every 3s from http://…"*. Calling a poll "live streaming" is how the original
placeholder survived: nobody could tell an empty stream from a quiet container.

Implementation notes worth keeping:

* **Docker's multiplexed framing is decoded, not assumed.** A container without a TTY returns
  8-byte frame headers (`\x02\x00\x00\x00 …`); with a TTY, raw bytes. Both occur in this fleet.
  Guessing wrong does not fail loudly — it renders header bytes as mojibake — so the format is
  detected and both paths are unit-tested.
* **Log level is inferred and nullable.** Docker carries no level field. A line that names no
  level reports `level: null` and appears only under "All levels". Defaulting it to `info`
  would make the filter quietly lie about what it is hiding.
* **ANSI colour is stripped** (ComfyUI, uvicorn and vLLM all colour their output).
* **The container reference is validated before it reaches a URL path** — `../info` is refused
  in the API, never sent. Unit-tested to assert the request is not made at all.

### 4.4 Exit gate — live, per node

    node          containers                       logs (tail=4)
    node-01       available=True   n=20            4 lines   celery ForkPoolWorker warnings + task INFO
    node-02       available=True   n=7             4 lines   vLLM APIServer GET /health 200
    node-03       available=True   n=8             4 lines   cogvideox GET /health 200
    node-04       available=True   n=11            3 lines   ComfyUI "[INFO] To see the GUI go to: …"
    node-05       available=True   n=2             2 lines   gpu-exporter "Listening on [::]:9835"
    node-06       available=False  n=0             0 lines   "no log source answered at http://192.168.1.95:9430:
                                                              ConnectError. Either ivgs-node-logs is not deployed
                                                              on this node, or the node is unreachable."

**Real lines from every online node, including node-01. node-06 says why it cannot, which is
the other half of the requirement.**

---

## S5. What changed

| File | Change |
|---|---|
| `ivgs-infra/docker-compose.telemetry.yml` | **new, tracked.** GPU exporter + node-logs; project `ivgs-telemetry`. Deployed to nodes 02/03/04/05. |
| `ivgs-infra/docker-compose.telemetry.node01.yml` | **new, tracked.** node-01's log source only, on `ivgs-net`, no host port. |
| `ivgs-infra/configs/node-logs/nginx.conf` | **new, tracked.** The two-route allowlist. `nginx -t` clean. |
| `ivgs-api/app/core/node_logs.py` | **new.** Log source client: addressing, demux, ANSI strip, level inference, honest unavailability. |
| `ivgs-api/app/api/v1/nodes.py` | Task 2 (`power_draw_w` onto the list payload); `GET /{id}/containers`; `GET /{id}/logs`; node-05 topology corrected. |
| `ivgs-api/app/api/v1/ws_logs.py` | Dead ssh-based node-log WS route removed with the reason recorded in place. Job-status WS untouched. |
| `ivgs-frontend/src/components/monitoring/NodeLogPanel.tsx` | **new.** Container picker, polled tail, working level filter + search, working Download (Blob, not a fictional route), follow toggle, honest unavailable state. |
| `ivgs-frontend/src/app/nodes/page.tsx` | Placeholder paragraphs and the fake `<a download>` replaced by the panel. |
| `ivgs-frontend/src/components/NodeCard.tsx` | "no data" vs "n/a" (S3.2). |
| `ivgs-frontend/src/types/api.ts` | `power_draw_w` required; `NodeContainer(s)` / `NodeLog*` types. |
| `ivgs-infra/{configs,monitoring}/prometheus/prometheus.yml` | node-05 labels: `rtx-5080` → `rtx-pro-5000-blackwell`. |
| `dev/CLAUDE.md`, `README.md` | node-05 corrected; node-07 Temporal row added (§2 had none). |
| `OUTSTANDING_WORK.md` | P2.6(a) closed; P2.40–P2.44 added. |
| `ivgs-api/tests/test_wp48_telemetry.py` | **new,** 18 tests. |
| `ivgs-api/tests/test_wp24_node_honesty.py` | node-05 is measured now — assertion narrowed to node-06, with the reason. |
| `ivgs-api/tests/test_ws_node_logs.py` | 8 mocked-subprocess tests over the removed route → 3 removal pins + the account of why they could not catch it (§7.1). |
| `ivgs-api/tests/test_ws_connection.py` | 3 node-log tests removed; 2 auth tests retargeted off a route that no longer exists (they were passing on a 404). |
| `ivgs-api/tests/test_ws_edge_cases.py` | 4 node-log tests replaced by the same properties asserted on the HTTP route. |
| `ivgs-api/tests/test_node_topology.py` | **incidental fix** — two tests red since WP-24 (§7.2). |

---

## S6. Task 4 — AD-04 conformance: who initiates the metadata transfer?

**Read-only on both systems.** One access limitation, stated up front: **there is no SSH
credential from node-01 to 192.168.1.51**, so `/opt/mbcp` on the MBCP host could not be read
directly. The MBCP side was read from `/opt/MBCP`, the read-only reference clone
(`dev/CLAUDE.md` §11) at `ea7f91e`. Everything cited below is corroborated by IVGS-side
runtime evidence that only a real POST could have produced (§6.3).

### 6.1 What the SSOT specifies — quoted exactly

`MBCP_Master_Functional_Specification_SSOT_v3.3.md`, §12.4:

> **`connected`** → `AD01Export`: transmits to the live AD-01 ingest endpoint.

§12.6 **AD-01 Integration [EXTERNAL — Phase 4]**:

> In `connected` mode, `AD01Export` posts the package to `MBCP_AD01_URL` authenticated by
> `MBCP_AD01_TOKEN`. On the IVGS side, AD-01 ingests the package as a `CANDIDATE`
> registration whose attestation is the MBCP certification, and a new IVGS-side fetch client
> (in `ivgs-models`) retrieves the weight bundle from the serving plane.

§2.2 (line 82):

> IVGS's **AD-01 Model Store** consumes MBCP's **certification attestation** (AD-01.7.2) and
> **fetches** the weight bundle via a new IVGS-side client (in `ivgs-models`) …

`IVGS_v5_Addendum_AD-04-v3…md` §3.14, **Seam 1 — Certification export (Management)**:

> `AD01Export` (**Phase 4**): POSTs the bundle to AD-01 — certification ID →
> `model_approvals.vetting_reference`, scorecard → `model_approvals.checklist`, measured VRAM
> → `models.vram_gb`, weight bundle → `models.weights_ref`/`weights_checksum`.

And §3.14, **Seam 2**:

> The **IVGS-side consumer** — the new fetch mechanism in `ivgs-models` (§3.7a) — is the
> stubbed half … at Phase 4 AD-01's tooling **pulls** certified bundles and verifies checksums.

**The "pull-only" sentence itself.** `IVGS_v5_Addendum_AD-04_v3.1_Amendment.md`, under
*"Closed by implementation"*, decision **#2 — Weight-serving transport**:

> **HTTP** — `ivgs-models/mbcp_fetch.py` against `{serving_url}/weights/{model}/manifest`, with
> checksum verification. **Direction is pull: IVGS pulls, MBCP does not push.** Not yet
> exercised end-to-end (ledger P2.10).

**The SSOT is neither silent nor ambiguous.** It specifies **two seams with opposite
directions**: metadata/attestation is **POSTed by MBCP**; weights are **pulled by IVGS**. The
"MBCP does not push" sentence is a property of decision #2 — the *weight* transport — and is
not stated anywhere as a general rule.

### 6.2 What is implemented

**MBCP side** (`/opt/MBCP` @ `ea7f91e`) — two initiators, both MBCP's:

1. **Operator action.** `mbcp_api/api/v1/certifications.py:570` —
   `@router.post("/exports", …, dependencies=[Depends(require_admin)])`, assembling the bundle
   and at `:641-643` calling `get_exporter(...)` → `await exporter.export(bundle)`. AD-04 v3.1
   states the same: *"Certify ≠ export. Export is a distinct admin action, `POST /api/v1/exports
   {certification_id}`."* This is the `serving-management-api-1` container that holds
   `MBCP_AD01_TOKEN`.
2. **A scheduled autonomous re-send.** `mbcp_worker/export_drain.py:87` —
   `drain_pending_exports` re-sends un-transmitted `pending_exports` rows, dispatched by the
   DB-backed Beat as a *"fixed periodic maintenance entry"*. This is the second token holder,
   `serving-ingest-worker-1`.

Both reach `mbcp_core/export/ad01.py:62-71`:

    resp = await client.post(
        f"{self._base_url}/ad01/v1/certified-models",
        json=bundle.model_dump(mode="json"),
        headers={"X-Service-Token": self._token,
                 "Idempotency-Key": bundle.idempotency_key},
    )

**IVGS side** — a pure receiver, and nothing else:

* `ivgs-api/app/api/ad01_ingest.py:71-80` — `POST /ad01/v1/certified-models`, root-mounted
  (`ivgs-api/main.py:83`) so the path matches MBCP's client exactly.
* `app/core/rbac.py:26-47` `require_mbcp_ingest` — constant-time compare of `X-Service-Token`
  against `IVGS_MBCP_INGEST_TOKEN`. *"Machine-to-machine — the caller is the external
  certifier."*
* **There is no IVGS-side puller of model metadata.** Grepping `ivgs-api`, `ivgs-models`,
  `ivgs-workers`, `ivgs-scheduler` and `shared` for any client of MBCP's `/certifications` or
  `/exports` returns nothing. IVGS holds `MBCP_SERVING_TOKEN` for the **weight** path
  (`ivgs-models/mbcp_fetch.py`, never exercised — P2.10) and that is the only direction IVGS
  initiates.

The token topology in the brief is itself the confirmation: **IVGS holds a *receiver* secret;
MBCP holds *sender* secrets in two containers.** A pull architecture would have those reversed.

### 6.3 The July 10 ingest — mechanism confirmed from IVGS's own data

    $ select count(*), min(attested_at), max(attested_at) from model_approvals
      where attested_at::date='2026-07-10';
       24 | 2026-07-10 01:01:05 | 2026-07-10 03:13:02

Eleven models and eighteen attestations land inside **0.8 s** at `02:22:24` — a burst, not
eleven human actions; the shape of `drain_pending_exports` flushing a batch (default 25) after
`MBCP_AD01_MODE` flipped to `connected`, or a scripted loop over `POST /exports`. Either way,
MBCP-initiated.

`model_approvals.attested_by` is `bruce` — written by `ad01_ingest.py:176` from
`bundle.certified_by`, i.e. the MBCP-side certifier carried across in the payload, not an IVGS
user. And `model_approvals.checklist` holds MBCP-authored content IVGS has no other route to:

    {"quality": {"note": "No human-eval aggregate yet; not fabricated (INV-9).",
                 "status": "pending_human_eval", …},
     "provenance": {"cuda_version": "13.0", "gpu_driver_version": "580.159.03",
                    "engine_image_digest": "sha256:f5156c2ef9d2…", …}}

`INV-9` is an MBCP invariant. `engine_image_digest` is measured on MBCP's benchmark hardware.
No IVGS code path could have produced these rows.

### 6.4 Verdict

> **The metadata path CONFORMS to the SSOT.** The SSOT specifies that MBCP POSTs the
> certification package to AD-01 (§12.4, §12.6) and that IVGS pulls only the weight bundle;
> the implementation does exactly that, on both sides.
>
> **What does not conform is the rule as stated in the work order** — *"PULL-ONLY: IVGS
> initiates all transfers from MBCP; MBCP never pushes."* That sentence is true of Seam 2
> (weights) and false of Seam 1 (metadata), and no spec text states it as a general rule. Its
> source is AD-04 v3.1's closed decision **#2**, which is titled *"Weight-serving transport"*.

So this is not case (a), (b) or (c) as posed: it is **a doctrine/spec conflict, with the code
on the SSOT's side.** Ledgered **P2.41** for an operator ruling, with both options costed:

| Option | What it means |
|---|---|
| **(i) Narrow the doctrine** — recommended | State the pull-only rule as Seam-2-scoped in the fleet docs and in `dev/CLAUDE.md`. No code changes on either side. The architecture is already coherent: weights are large and content-addressed (pull), attestations are small, event-driven and idempotent (push). |
| **(ii) Enforce pull everywhere** | An **MBCP-owned, change-controlled** amendment to SSOT §12.4/§12.6 — and SSOT §787 explicitly **freezes** the AD-01 export-factory seam, so this is a spec-level decision, not an implementation edit. Then: a new IVGS-side scheduled puller against MBCP's `/certifications`, plus demotion of `ad01_ingest.py` to a disabled receiver. Note MBCP's `pending_exports` drain, poison-row parking and per-cert idempotency all exist to make *push* honest; a pull design re-solves that from scratch. |

**Nothing is implemented for either option.** Both systems were read-only for this task.

---

## S7. Tests

**Targeted — the package's own gates.** `TEST_DATABASE_URL` → `ivgs_reconciliation_test`
(bare `pytest` refuses to start against the live DB; that guard is correct and is why it is
set explicitly):

    tests/test_wp48_telemetry.py ..................        [ 60%]
    tests/test_wp24_node_honesty.py ............           [100%]
    30 passed in 0.87s

The 18 new tests are hermetic — `httpx.get` and `node_health._query` are monkeypatched, so no
node, Prometheus or Docker socket is contacted. Each pins a defect that shipped:

* Power is on the **list** payload, not detail-only — the Task 2 defect, stated as an assertion.
* Power is `None`, never `0`, when unmeasured.
* `GPU_QUERIES["power_draw_w"]` is the metric name the exporter actually emits.
* node-05 declares the card that is in it (48935 MiB, `topology_verified` True).
* An unreachable log source names the URL and says "not deployed / unreachable" — never an
  empty line list.
* `../info` as a container ref **never reaches the wire** (asserted on the mock's call list).
* Docker multiplexed frames demux; raw TTY output passes through; empty payload is empty.
* ANSI stripped, level inferred; a line that names no level reports `null`, not `info`.
* `stream_node_logs` no longer exists, `stream_job_status` still does, and no route in
  `ws_logs.router` advertises a node-log path.

**Frontend:** `npx tsc --noEmit` → **rc=0, no errors.** (`npm run lint` is not usable here — it
drops into next.js's interactive ESLint setup prompt; ESLint has never been configured in this
checkout. Environment note, pre-existing, not introduced here. `lint-frontend` runs in CI.)

### 7.1 The 15 tests this package broke, and what was done about them

Removing the ssh-based WebSocket route broke **15 existing tests** across three files. They
are not collateral — they are the reason the defect survived:

| File | Tests | What they did |
|---|---|---|
| `test_ws_node_logs.py` | 8 | Streaming, service filter, tail, process cleanup, SSH-failure handling. **All eight patched `asyncio.create_subprocess_shell`** — so they mocked away the only thing that was broken. |
| `test_ws_connection.py` | 3 | Valid node, invalid node, disconnect cleanup. Same mock. |
| `test_ws_edge_cases.py` | 4 | Message envelope, unknown-node error, all-valid-node-ids, invalid-node-ids. Same mock. |

**None of them could have caught it.** A handler whose subprocess is mocked passes whether or
not `ssh` exists on the box. This is ledger P2.22's warning — a test that freezes a stub —
and WP-00's swallow shape, in the same place.

**What was done, and it is not deletion-and-move-on:**

* `test_ws_node_logs.py` is **kept as a file**, rewritten to three tests that pin the removal:
  the route is gone, `stream_job_status` is not, and the HTTP replacement names an unknown
  node instead of returning an empty list. Its docstring carries the full account so the next
  person who wants to re-add a node-log WebSocket reads why this one could not work.
* The 3 + 4 in the other two files are replaced by removal pins and, where the test was
  reaching for a real property, by an assertion of that property on the route that now serves
  logs.
* **Two auth tests were passing for the wrong reason and were retargeted.**
  `test_ws_connect_no_auth_rejected` and `test_ws_connect_invalid_token_rejected` pointed at
  the node-log route; once it was removed they still passed, because TestClient raises for a
  404 exactly as it does for a 1008 close. They asserted nothing about authentication. Both
  now point at `/ws/jobs/{id}/status`, which exists. `test_ws_node_logs_no_auth` became an
  assertion that the HTTP log route requires a token.

### 7.2 Two tests that were already red, and had been since WP-24

Found while classifying the above, in `test_node_topology.py` — **not caused by this package**
(`git diff` on that file was empty when they failed):

* `RTX6000 = "NVIDIA RTX 6000 Blackwell"` / `VRAM_96 = 98304`, while WP-24 measured
  `"NVIDIA RTX PRO 6000 Blackwell Workstation Edition"` / `97887` on nodes 02/03 and recorded
  it at `nodes.py:48,57`. The constants were never updated.
* `assert "cogvideox" in n["services"]` for node-03 — exact list membership against
  `["cogvideox-server", "cogvideox-worker"]`, so it has been false since those entries were named.

Both fixed here, using values already measured and recorded in the repo. The 96 GB test was
also **split**: node-02/03 are measured, node-06 is DECLARED and cannot be measured while it
is off, so pinning all three to one pair of constants asserted a measurement nobody has taken.
node-06 now has its own `*_DECLARED` pair plus `topology_verified is False`, and the
divergence between the two pairs is the point rather than a bug. Flagged as an incidental fix
outside WP-48's scope; it is two stale constants against ground truth the repo already holds,
and leaving the suite red is worse.

### 7.3 Full Python suite — before and after, and the environment condition

Budgeted at two full runs; both used. (A third invocation happened and is disclosed: the shell
had been left in `ivgs-api/`, so it collected 708 items — the api subset, not the suite — and
is not counted as a full run. Its 3 failures are the same three the real runs show.)

| Run | Result |
|---|---|
| **Before** the test repairs | `86 failed, 1340 passed, 53 skipped, 77 errors in 212.79s` |
| **After** | `69 failed, 1347 passed, 53 skipped, 77 errors in 211.63s` |

**Exactly 17 tests moved from red to green and NOTHING moved the other way.** Set-differenced
by node id:

    fixed  (in run 1, absent from run 2):  the 15 above + the 2 stale topology tests
    new    (absent from run 1, in run 2):  (none)

**No failure or error in either run is in this package's code.** Grepping the final run's
FAILED/ERROR lines for `wp48`, `node_log`, `telemetry`, `node_health`, `test_api_nodes`,
`node_topology` and `ws_` returns **0 matches**.

**The remaining 69 + 77 are the environment condition WP-46 recorded** and is unchanged here:
`tests_system/integration/*` and `tests_system/e2e/*` error at fixture setup on
`passlib.handlers.bcrypt: module 'bcrypt' has no attribute '__about__'` (a passlib/bcrypt
version mismatch in the venv that takes down every fixture needing a user), and a further
group fails on `Database connection check failed: [Errno 111] Connect call failed
('127.0.0.1', 5432)` — the suite reaching for a loopback Postgres that is published on
`192.168.1.90`. Largest single group is `tests_system/test_compliance_scanner.py` (19).
None of it is new, and it still deserves its own package.

---

## S8. Deploy evidence

### 8.1 node-01 — `v5.9.0-telemetry`

Both images built from the repository root, `docker build` rc=0, present in the local store
afterwards (checked against `docker images`, not trusted from the exit code):

| Image | Id | Size |
|---|---|---|
| `ghcr.io/brucecostello2/ivgs-api:v5.9.0-telemetry` | `857838f22930` | 490 MB |
| `ghcr.io/brucecostello2/ivgs-frontend:v5.9.0-telemetry` | `dc094e79fac4` | 259 MB |

**Content gates — every one a `grep` INSIDE the image.** The API image lays the app out at
`/app/app/…`, not `/app/…` (the WP-34 S2 lesson; a gate on the short path returns 0 for every
marker and looks exactly like a missing fix):

| Gate | Path | Result |
|---|---|---|
| `node_logs.py` present | `/app/app/core/node_logs.py` | yes |
| power on the LIST payload | `/app/app/api/v1/nodes.py` | 1 |
| detail-only `payload["power_draw_w"]` gone | `/app/app/api/v1/nodes.py` | 0 |
| `GET /{node_id}/containers` | `/app/app/api/v1/nodes.py` | 1 |
| `GET /{node_id}/logs` | `/app/app/api/v1/nodes.py` | 1 |
| node-05 `48935` | `/app/app/api/v1/nodes.py` | 2 |
| `async def stream_node_logs` | `/app/app/api/v1/ws_logs.py` | **0** (removed) |
| `websocket("/ws/nodes…` decorator | `/app/app/api/v1/ws_logs.py` | **0** (removed) |
| `async def stream_job_status` | `/app/app/api/v1/ws_logs.py` | 1 (kept) |

Frontend is a Next.js **standalone** build — compiled, minified JS, not `.tsx` — so its gates
run against `/app/.next`:

| Gate | Result |
|---|---|
| any file containing `logs/stream` | **none** — the fake ws:// promise is gone from the bundle |
| `polled tail` present | `/app/.next/server/app/nodes/page.js` **and** `/app/.next/static/chunks/app/nodes/page-1aa35e…js` |
| `/containers` endpoint present | `page-1aa35e…js` |

**Deploy.** `.env` backed up (`ivgs-infra/.env.bak-wp48-20260825-044902`) before the two tag
bumps; `IVGS_WORKERS_TAG` deliberately untouched at `v5.8.0-animation`.

The compose invocation was **derived from container labels**, not guessed (`dev/CLAUDE.md` §6)
— and that mattered: the service names are `fastapi-backend` / `nextjs-frontend`, not
`ivgs-api` / `ivgs-frontend`. The first attempt using the container names failed with
`no such service: ivgs-api`, which is the check working.

    docker compose --env-file .env \
      -f docker-compose.node01.yml -f docker-compose.override.node01.yml -f docker-compose.monitoring.yml \
      up -d --no-deps --force-recreate fastapi-backend nextjs-frontend

`--no-deps` per §6. **Running images confirmed from `docker ps`, not from `docker exec env`**
(§6: never read a tag variable out of a container and believe it):

    ivgs-fastapi   ghcr.io/brucecostello2/ivgs-api:v5.9.0-telemetry        Up (healthy)
    ivgs-nextjs    ghcr.io/brucecostello2/ivgs-frontend:v5.9.0-telemetry   Up (healthy)

**Nothing else recreated** — container IDs identical before and after across all twelve
services that had to be left alone:

    postgres ed32ab8a79a4 · redis 8431e02f4b78 · seaweedfs master/volume/filer 4d9621bb6047 / 389be3b79def / 2af3e52ae41c
    celery default/composition/beat 10bb5f7d6fdf / a17f7b90d784 / 80eb09dd274d
    scheduler dfc6cba52442 · prometheus a626fc743cf0 · grafana 94d6429f9c0c · nginx 5045e8dd57f4

**Serving the new bundle**, verified through the live nginx rather than only inside the image:

    GET https://node-01/nodes                                        -> 200
    GET https://node-01/_next/static/chunks/app/nodes/page-1aa35e….js -> 200, contains "polled tail — last"

### 8.2 Nodes 02–05 — the telemetry overlay

Additive only: `ivgs-gpu-exporter` and `ivgs-node-logs`, in the `ivgs-telemetry` project. No
engine, worker or exporter belonging to any other project was recreated (S1.2). Backups taken
before touching anything: `docker-compose.gpuexp.yml.bak-wp48-<ts>` on each of nodes 02/03/04;
node-05 had no prior file. node-04's superseded file was reduced to `services: {}` with a
pointer to its backup rather than deleted — its containers' `project.config_files` label names
it, so deleting it would break the label-derived compose invocation for the whole node-04 stack.

Verified after deploy, on the node: `compose ps` both services Up, `node-logs` **healthy**;
`ss -lnt` showing 9400 and 9430; `curl` returning the four metrics; the allowlist gates
(`list=200 inspect=403 info=403 post=403`).

### 8.3 What this package did NOT touch

Workers on every node; vLLM; CogVideoX; the Wan-Animate server; ComfyUI; Coqui, Kokoro,
WhisperX, LatentSync; Postgres, Redis, SeaweedFS, the scheduler, Prometheus, Grafana, nginx,
alertmanager, pushgateway; every `.env` on nodes 02–05; every systemd unit anywhere.

---

## S9. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| **D-1** | **AD-04 direction doctrine (P2.41).** The metadata seam is a push, by SSOT §12.4/§12.6, and the implementation matches. The "pull-only" rule as written contradicts it. | **Narrow the doctrine to Seam 2 (weights)** and say so in the fleet docs. Option (ii) requires an MBCP-owned amendment to a seam SSOT §787 explicitly freezes. |
| **D-2** | **`ivgs-node-logs` exposure (S4.2).** Ports 9430 are LAN-reachable and unauthenticated: container names/images/states and log text, read-only, GET-only, inspect refused. | Accept as-is for now (it sits behind the same perimeter as vLLM :8000 / ComfyUI :8188 / exporters :9400), **or** ufw allow-from 192.168.1.90 only. Say which; I did not choose a firewall policy unasked. |
| **D-3** | **node-01's five dead scrape targets (P2.40).** No host, API, Postgres or Redis metrics for the hub, and Grafana's overview dashboard is reading nothing. | Re-point four of the five at container DNS on `ivgs-net` — no firewall change needed, the pattern is already proven by this package's node-01 log source. `node-exporter` is the one that needs a ufw call. |
| **D-4** | **node-05's role.** The work order says *quality-services stack*; AD-02 says *image fallback + Ollama*; the node runs neither and has no `/opt/ivgs` checkout. | Settle the role, then amend AD-02 + the functional spec under change control (P2.43). |
| **D-5** | **Task-3 scope.** I shipped a polled tail and **removed** the WebSocket route rather than reimplementing it, on the "minimal honest version" instruction. | Confirm. A follow-up can stream over the same source (`follow=1` already passes through the nginx allowlist with `proxy_buffering off`) if live-tail is wanted. |

---

## S10. Push block — ALL held commits, count-gated

**Nothing has been pushed.** This repo is on commit-and-HOLD; the operator batches.

Run this on node-01. It refuses to push unless the count of unpushed commits is **exactly**
what this report accounts for, so a commit that arrived from elsewhere between writing and
running this cannot ride along unnoticed:

    cd /opt/ivgs
    EXPECTED=5              # the five WP-48 commits listed below; re-verify before running
    AHEAD=$(git rev-list --count origin/main..HEAD)
    BEHIND=$(git rev-list --count HEAD..origin/main)
    if [ "$AHEAD" != "$EXPECTED" ]; then
      echo "REFUSING: $AHEAD commits ahead, expected $EXPECTED. Review before pushing:"
      git log --oneline origin/main..HEAD
    elif [ "$BEHIND" != "0" ]; then
      echo "REFUSING: $BEHIND commits behind origin/main. Rebase or merge first."
    elif [ -n "$(git status --porcelain --untracked-files=no)" ]; then
      echo "REFUSING: tracked working tree is dirty."
      git status --short
    else
      git log --oneline origin/main..HEAD
      echo "--- gate passed: $AHEAD commits, tree clean, up to date with origin ---"
      git push origin main
    fi

**Held commits — five, and they are the whole of what is held.** At the start of this session
`HEAD == origin/main` at `5fbfe45` (`git rev-list --left-right --count HEAD...origin/main` →
`0  0`), so nothing was already waiting behind these:

    66c98a0  feat(wp-48): one tracked exporter overlay, and a log source that is not a promise
    6128260  fix(wp-48): Power was on the wrong route, and the log stream was on no route
    a5dcc42  feat(wp-48): the log pane shows logs, and "no data" stops meaning two things
    3d74b7b  test(wp-48): the tests that could not have caught it, and two red since WP-24
    <head>   docs(wp-48): the report, node-05's real card, and an AD-04 verdict with the quote
             ^ this commit -- it carries this file, so its own hash cannot be printed in it.
               `git log --oneline -1` at push time is the value.

`git rev-list --count origin/main..HEAD` → **5**, tracked tree clean. If that number is not 5
when the block runs, something arrived from elsewhere — the gate will refuse and print the
log rather than push it along with these.

---

## S11. Standing caveats on this report

* **Task 4 was read from the reference clone.** No SSH credential from node-01 reaches
  192.168.1.51, so `/opt/mbcp` on the MBCP host was not read; `/opt/MBCP` @ `ea7f91e` was.
  The July-10 evidence in §6.3 is IVGS-side runtime data and is independent of that clone.
* **The Node Monitor cards were verified through their data contract, not with a browser.**
  The card's Power cell reads `node.power_draw_w` from `GET /api/v1/nodes` (`NodeCard.tsx:50`),
  that response now carries a number for all four GPU nodes (§3.3), and the compiled bundle
  serving those cards is live (§8.1). There is no Playwright in this checkout (ledger P2.25a),
  so no screenshot was taken. Stated rather than implied.
* **`ivgs-node-logs` runs its nginx worker as root** to connect to the docker socket
  (`root:docker 0660`; an `nginx`-user worker gets EACCES). Its reachable surface is the two
  locations in the allowlist. The `:ro` on the socket mount is signalling — a read-only bind
  mount does not constrain Docker API semantics; **the route allowlist is what makes it
  read-only**, and that is where any change must be reviewed.
* **Log level is inferred from line text**, not read from a level field docker does not carry.
  The panel's filter is therefore best-effort by construction, and a line that names no level
  is excluded from every level filter rather than silently counted as `info`.
