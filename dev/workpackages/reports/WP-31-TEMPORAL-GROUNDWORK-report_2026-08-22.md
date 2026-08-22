# WP-31-TEMPORAL-GROUNDWORK — report

| | |
|---|---|
| **Work package** | `dev/workpackages/WP-31-TEMPORAL-GROUNDWORK.md` |
| **Date** | 2026-08-22 |
| **Profile** | Tier B, **unattended** — single overnight session, no operator available |
| **Repo basis** | `brucecostello2/elearning_v5` @ **`8092cd8`** (node-01) |
| **Nodes touched** | node-01 (repo work + read-only inspection), node-07 = 192.168.1.96 (Temporal cluster) |
| **Outcome** | **All three lanes complete.** Nothing blocked. |
| **Addendum** | **Rulings round, same day.** Operator ruled D-1…D-6; D-4 measured against the live fleet. See "Rulings applied" below. |
| **Commits** | Authored and **HELD**. Operator pushes. |

## Access note

The brief specifies `root@192.168.1.96`. The session was handed
`dev@192.168.1.96` with passwordless sudo, and that was used throughout.
Node hostname confirmed as **`temporal`**. No root login was attempted.

---

## Executive summary

| Lane | Result |
|---|---|
| **A** — AD-05 review dossier | **Complete.** All Draft 1 factual claims verified against HEAD. 9 exact, 11 drifted, **4 materially wrong**, **0 left unverified** (the last, D1's two-node premise, was measured in the rulings round). Amendment (Draft 2) and approval checklist written. |
| **B** — Temporal dev cluster on node-07 | **Complete.** Greenfield → running 4-container stack, every image pinned. Smoke workflow verified via CLI. Persistence proven across a full restart. Two real config bugs found and fixed. |
| **C** — shadow-workflow spike | **Complete.** DAG-driven 8-stage workflow, signal gates, 6-scene fan-out. **Resume demonstration succeeded**: 13 activities, 13 completions, each exactly once, across a `SIGKILL`. Bounded retries surfaced, not swallowed. |

**The headline.** A worker was killed mid-fan-out. The workflow completed
without re-running any activity whose completion had reached the server, and
without restarting from stage 1. This is the property AD-05 §12 test 5 asks
for and the reason the migration is proposed. It works.

**The most important finding is not that it works — it is what it costs.**
Two scene activities whose bodies had finished, but whose completion had not
yet been reported when the worker died, **executed a second time.** That is
correct at-least-once activity semantics, and it means every writing activity
must be idempotent. Draft 1 does not say this. Draft 2 §6 now makes it binding,
and it is item A-5 on the approval checklist.

---

## Deliverables

| Path | What |
|---|---|
| `docs/IVGS_v5_Addendum_AD-05_Draft2_Amendment.md` | Lane A (a) — amendment draft; discrepancies, DAG design, idempotency requirement, census + boundary tables as Appendices B and C |
| `docs/AD-05_Operator_Approval_Checklist.md` | Lane A (b) — one-page approval checklist, 7 approvals + 4 open rulings, each with a plain-English risk statement |
| `configs/temporal/docker-compose.yml` | Lane B — pinned compose stack (tracked; `.env` is not) |
| `configs/temporal/dynamicconfig/development-sql.yaml` | Lane B — dynamic config |
| `configs/temporal/.env.example`, `.gitignore` | Lane B — secret handling |
| `dev/spikes/temporal/` (12 files) | Lane C — the spike, marked throwaway in its README |
| this file | report |

Draft 1 (`docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md`) is
**unedited**, as required — the amendment sits alongside it.

---

# Lane A — AD-05 code-grounded review dossier

Every checkable claim in Draft 1 was re-run against HEAD. Full detail, with
corrected file:line for each, is in Draft 2 §3 and §4. Summary:

### Confirmed exactly, line numbers included — *verified live*

`config.py:214-215` (`broker_visibility_timeout = 3600`) ·
`video_generation_task.py:445` (`time_limit = 3900`) ·
`checkpoints.py:79,106,137,175` (**all four**, and the only POST is
`resume_pipeline`) · `gpu_utils.py:211` (one-parameter release) ·
`gpu_utils.py:126` (acquire) · orphaned lines **1,957** exactly
(461+754+742) · **14** `from ivgs_workers…` occurrences, and **no
`ivgs_workers` package exists** · **859** lines of tests over the three inert
modules (236+379+244) · zero tests on the live orchestrator.

### Three material corrections

**1. "`periodic_tasks.py` … cannot run" — WITHDRAWN.** It is in the Celery
include list (`celery_app.py:330`); its module-level imports are clean
(`periodic_tasks.py:29-38`); the broken `ivgs_workers` imports are **lazy**;
and `poll_model_node_availability` is beat-scheduled **every 30 seconds**
(`celery_app.py:208-212`) using only safe imports. All **eight** beat entries
resolve to registered task names. *Consequence:* deleting `periodic_tasks.py`
at cutover would remove a live 30-second poll. Now an explicit migration item
and checklist line A-7.

**2. "the 14 `send_task` call sites" — undercount; it is 23.** Enumerated in
Draft 2 §4.3. Only 10 are in the orchestrator modules; **13 sit inside the
eight stage bodies** that §8 declares untouchable. §8 is amended to permit
exactly those 23 edits and nothing else. This is checklist item A-4 — the
scope boundary as written was self-contradictory.

**3. §8 line-count table has drifted.** `pipeline_orchestrator_v2.py`
1,397 → **1,502**; `celery_app.py` 648 → **642**; total 5,541 → **5,640**.
Draft 1's arithmetic was internally correct; the code grew over 36 commits.

### D4 — a standing contradiction resolved, partially

`CLAUDE.md` §7 records the `release_gpu_reservation` signature drift as
"UNVERIFIED and contradictory" against `OUTSTANDING_WORK.md:293`.

**It reproduces in source at HEAD.** `release_gpu_reservation(reservation_id)`
takes one parameter (`gpu_utils.py:211`); three call sites pass two —
`video_generation_task.py:540`, `talking_head_task.py:699`, and
`talking_head_task.py:884`. Draft 1's third reference (`:543`) is wrong. A
**fourth** site Draft 1 omits, `celery_app.py:601`, passes one and is correct.
Acquire sites number **seven**, not eight.

> **Scope of this resolution — read carefully.** This was established by
> *reading* the signature and all four call sites. **No call site was
> executed.** Whether the *deployed image* matches HEAD is a different
> question and is **not** resolved here. `CLAUDE.md`'s instruction not to act
> on either claim as fact still stands for the deployed-image question.

### D1's two-node premise — MEASURED, and it is false as deployed

Originally recorded here as unverifiable. It was measured in the rulings round
(D-4) and is now a **fourth material correction**. Full write-up: Draft 2 §4.5.

`celery inspect active_queues` against the live broker, five workers online:

```
celery-worker@node02      gpu_llm
cogvideox-worker@node03   gpu_video
image-worker@node04       gpu_image, gpu_tts, gpu_talking_head
default-worker@node01     default, notifications, cleanup
composition-worker@node01 composition
```

**Only node-03 consumes `gpu_video`. Node-02 does not.** Node-02 defines such
a worker (`docker-compose.node02.yml:126`) but it carries
`profiles: ["standby"]` (`:95`) and is not started; node-03's `gpu_llm` worker
is the standby half (`docker-compose.node03.yml:160`). It is an
**active/standby pair, not two concurrent consumers.**

The redelivery defect survives unchanged — `visibility_timeout 3600` under
`time_limit 3900` with `acks_late` still means a long video task is
redelivered and runs twice. What does not survive is D1's *concurrency*
claim: with one active consumer at `--concurrency=1` the duplicate serialises
behind the original instead of racing it on a second GPU. **D1's severity is
lower than Draft 1 states.**

Confirmed a third way, on the nodes themselves (read-only, `root@`):

```
node-02  ivgs-celery-node02            Up (healthy)   --queues=gpu_llm   --concurrency=2
         ivgs-cogvideox-worker         Exited (0) 2 months ago      <- the gpu_video worker
node-03  ivgs-cogvideox-worker-node03  Up (healthy)   --queues=gpu_video --concurrency=1
         ivgs-celery-node03            Exited (0) 2 months ago      <- the gpu_llm worker
```

The premise becomes true the moment anyone starts node-02's `standby` profile.
Latent, not retired.

### Other findings recorded for the register

- **`save_checkpoint` has 15 call sites, not 5.** `CLAUDE.md` §7 says "all 5
  call sites"; the actual count across 9 stage files is **15**, and **not one**
  captures the return value. `CLAUDE.md`'s line references (`:442,450`) are
  correct — those are the two `return False` statements.
- **P2.3's four mismatched files confirmed**: `stage5_voiceover.py` →
  `tasks.stage4_voiceover.*` (also the wrong stage number),
  `stage7_prototype_draft.py` → `tasks.prototype_draft_task.*`,
  `stage8_final_render.py` → `tasks.final_render_task.*`,
  `periodic_tasks.py` → `ivgs_workers.tasks.periodic_tasks.*`.
- **`run_backup_verification` stub confirmed** returning `{'status': 'ok'}` on
  a daily schedule (`pipeline_orchestrator.py:616-622`) — matches the
  swallowed-failures register. No new instances were added by this package.

### Census and boundary tables

Delivered as **Draft 2 Appendix B** (40-row Celery touchpoint census, each with
file:line and its Temporal replacement) and **Appendix C** (activity-boundary
table, stages 1–8: real registered name, queue, today's retry/timeout
constants, proposed activity signature, timeouts/heartbeat, idempotency key).

**Method note.** Every line reference in both appendices was produced by
grepping HEAD in this session, not copied from Draft 1. Where Draft 1 and the
repo disagreed, the repo won and the disagreement is recorded.

---

# Lane B — Temporal dev cluster on node-07

## Precheck — *verified live*

| Property | Value |
|---|---|
| Hostname | **`temporal`** |
| Reachable | yes, `dev@192.168.1.96`, passwordless sudo confirmed |
| OS | Ubuntu **24.04.4 LTS**, kernel 6.8.0-137-generic |
| RAM | 7.7 GiB total, 7.1 GiB available |
| Disk | 48 GB root, 38 GB available (16% used) |
| Docker | **absent** — greenfield, as the brief anticipated |

## Installed — *verified live*

| Component | Version |
|---|---|
| Docker Engine | **29.7.2** (build a7dcaa6), overlayfs |
| Docker Compose plugin | **v5.5.0** |
| Python | 3.12.3 (system) |
| `temporalio` Python SDK | **1.31.0** (pinned, in a venv) |

## Pinned images — no `latest` anywhere (WP-09 lesson)

| Service | Image | Digest-pinned tag |
|---|---|---|
| `temporal` | `temporalio/auto-setup` | **1.29.7** |
| `temporal-ui` | `temporalio/ui` | **2.53.3** |
| `temporal-admin-tools` | `temporalio/admin-tools` | **1.29.7-tctl-1.18.4-cli-1.7.2** |
| `temporal-postgresql` | `postgres` | **17.11-alpine** |

Postgres 17 matches production's major version (`CLAUDE.md` §4 records
`postgres:17.2` in production). This is a **separate** database on node-07;
**no pipeline database was accessed at any point.**

## Two real bugs found and fixed — *verified live*

**B-1. auto-setup never created its database.** The stack came up and looped:

```
ERROR  sql handle: unable to refresh database connection pool
       {"error": "pq: database \"temporal\" does not exist"}
ERROR  Unable to setup SQL schema.  {"error": "no usable database connection found"}
```

Root cause, read from the image's own script rather than guessed
(`/etc/temporal/auto-setup.sh:207`):

```bash
# Create database only if its name is different from the user name.
if [[ ${DBNAME} != "${POSTGRES_USER}" && ${SKIP_DB_CREATE} != true ]]; then
```

`DBNAME` defaults to `temporal` and `POSTGRES_USER` was `temporal`, so
auto-setup **skipped** creating the database, assuming the Postgres image had
done it at initdb — but the Postgres container had `POSTGRES_DB=postgres`.
Neither side created it.

*Fix:* `POSTGRES_DB: temporal` on the Postgres service, with the reason
recorded in a comment in the compose file. Because initdb only runs on an
empty data directory, the volume was dropped (`down -v`) and recreated — safe,
the cluster held nothing.

**B-2. the healthcheck could never pass.** The server binds to the container
IP, not loopback — measured inside the container:

```
tcp  0  0  172.18.0.3:7233  0.0.0.0:*  LISTEN  1/temporal-server
```

so a healthcheck addressing `127.0.0.1:7233` was refused indefinitely, and the
UI and admin-tools never started (`dependency failed to start: container
temporal is unhealthy`). *Fix:* `BIND_ON_IP: 0.0.0.0`, also commented in place.

Both fixes are in the committed compose file, so the next person does not
rediscover them.

## Result — *verified live*

```
temporal                temporalio/auto-setup:1.29.7                        Up (healthy)
temporal-admin-tools    temporalio/admin-tools:1.29.7-tctl-1.18.4-cli-1.7.2 Up
temporal-ui             temporalio/ui:2.53.3                                Up
temporal-postgresql     postgres:17.11-alpine                               Up (healthy)
```

Both databases created by auto-setup: `temporal` and `temporal_visibility`.
Default namespace registered; search attributes added.

**LAN reachability, tested from node-01:**

| Endpoint | Result |
|---|---|
| gRPC `192.168.1.96:7233` | **open** |
| Web UI `http://192.168.1.96:8080` | **HTTP 200**; `/api/v1/namespaces` returns JSON |

Postgres is bound to `127.0.0.1:5432` on node-07 only — the event store is not
exposed to the LAN.

## Smoke test — verified by CLI, not client output

`smoke_hello.py` executed a hello-world workflow. Per the brief, verification
is the CLI:

```
$ temporal workflow show --workflow-id ivgs-smoke-hello-2026-08-22
    1  WorkflowExecutionStarted     5  ActivityTaskScheduled
    2  WorkflowTaskScheduled        6  ActivityTaskStarted
    3  WorkflowTaskStarted          7  ActivityTaskCompleted
    4  WorkflowTaskCompleted       ...
   11  WorkflowExecutionCompleted
Results:
  Status  COMPLETED
  Result  "Hello, IVGS! -- from Temporal on node-07"
```

## Persistence across restart — proven, not assumed

`docker compose restart` on the **whole** stack. All four containers came back
with fresh uptimes (`Up 10 seconds`), `temporal` healthy again in 20 s. The
pre-restart workflow's **complete 11-event history and result were still
queryable**, byte-identical to before.

> This is the O-1 evidence: local Postgres on node-07 holds history across a
> full stack restart. Node-01's Postgres was never involved.

---

# Lane C — shadow-workflow spike

Location: `dev/spikes/temporal/`. **Zero IVGS imports**, imported by nothing,
README states it is throwaway evidence.

## What was built

- `pipeline_dag.py` — the 8 stages + 2 gates as `DagNode`s with `depends_on`,
  and a pure `topological_waves()` that compiles them into ordered parallel
  groups and **raises on a cycle rather than deadlocking at await time**.
  Compiles to 10 waves. Runs standalone, no cluster needed.
- `workflow.py` — walks the waves. **The workflow body names no stage.**
  `gate` → `workflow.wait_condition` on a signal; `fanout` → `asyncio.gather`
  over per-scene activities with `return_exceptions=True` (preserving the
  deliberate partial-advance behaviour of commit `35d9226`); `activity` → one
  activity. Signals: `storyboard_approved`, `draft_approved`, `cancel_job`.
  Query: `state`.
- `activities.py` — stub activities that sleep and heartbeat, and append an
  `fsync`'d JSONL execution ledger recording every body execution with pid and
  attempt. The ledger is independent of anything Temporal reports.

## Demonstration 2 — resume — **the headline**, *verified live*

`ivgs-resume-demo-run2`, 2026-08-22. Worker A `SIGKILL`ed mid-fan-out, 8 s
after the second scene completed so the kill lands mid-activity.

**Durable event history (`resume_evidence.py`, read from the server):**

```
  13  EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
  13  EVENT_TYPE_ACTIVITY_TASK_STARTED
  13  EVENT_TYPE_ACTIVITY_TASK_COMPLETED
   2  EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED
   1  EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED

signals received: ['storyboard_approved', 'draft_approved']

activity SCHEDULES total          : 13
schedules completed exactly once  : 13
schedules completed more than once: 0
```

**Body-execution ledger (`analyze_ledger.py`, written by the activities):**

```
activity          starts  completes  pids            verdict
s1_transcript          1          1  [46636]         ran exactly once
s2_storyboard          1          1  [46636]         ran exactly once
scene-1                1          1  [46636]         ran exactly once
scene-5                1          1  [46636]         ran exactly once
scene-0                1          1  [46921]         ran exactly once
scene-2                1          1  [46921]         ran exactly once
scene-3                2          1  [46636, 46921]  body ran twice (killed inside the ack window)
scene-4                2          1  [46636, 46921]  body ran twice (killed inside the ack window)
s4_manifest            1          1  [46921]         ran exactly once
s5_voiceover           1          1  [46921]         ran exactly once
s6_talking_head        1          1  [46921]         ran exactly once
s7_draft               1          1  [46921]         ran exactly once
s8_final               1          1  [46921]         ran exactly once
```

**Event-history extract, showing the fan-out and the worker death:**

```
   17  22:30:28Z  WorkflowExecutionSignaled   <- gate 1 released
   21  22:30:28Z  ActivityTaskScheduled       <- six scenes scheduled
   22  22:30:28Z  ActivityTaskScheduled          in ONE workflow task:
   23  22:30:28Z  ActivityTaskScheduled          this is the gather
   24  22:30:28Z  ActivityTaskScheduled
   25  22:30:28Z  ActivityTaskScheduled
   26  22:30:28Z  ActivityTaskScheduled
   27  22:30:28Z  ActivityTaskStarted
   28  22:30:48Z  ActivityTaskCompleted       <- worker A
   30  22:30:28Z  ActivityTaskStarted
   31  22:30:48Z  ActivityTaskCompleted       <- worker A
                                              *** SIGKILL ~22:30:56 ***
   34  22:30:59Z  ActivityTaskStarted         <- worker B picks up
   35  22:31:19Z  ActivityTaskCompleted
   ...
   78  22:31:57Z  WorkflowExecutionSignaled   <- gate 2 released
   88  22:32:00Z  WorkflowExecutionCompleted
```

**What this proves.** Stages 1 and 2 completed on worker A (pid 46636) and were
**never re-run** after the restart — the pipeline did not go back to stage 1.
The six-scene fan-out was scheduled in a single workflow task. Both gates
released via signal. Final workflow state: all 10 DAG nodes completed, all 6
scenes present, `finished: true`.

**What it also proves, and this matters more.** The ledger records **15** body
executions where the history records **13** completions. Scenes 3 and 4 were
in flight when the worker died; their bodies ran again. Temporal guarantees the
**workflow** advances exactly once; **activities execute at least once**.

This was not designed into the demonstration — it was observed, and the
tooling was then rebuilt to report it honestly rather than hide it. It is
written up as a binding requirement in Draft 2 §6 and as checklist item A-5.

## Demonstration 3 — bounded retries, failure surfaced — *verified live*

```
{"event": "start",  "key": "flaky", "attempt": 1}   ts 1787438096.604
{"event": "failed", "key": "flaky", "attempt": 1}   ts 1787438097.106
{"event": "start",  "key": "flaky", "attempt": 2}   ts 1787438098.119   (+1.0 s)
{"event": "failed", "key": "flaky", "attempt": 2}   ts 1787438098.621
{"event": "start",  "key": "flaky", "attempt": 3}   ts 1787438100.637   (+2.0 s)
{"event": "failed", "key": "flaky", "attempt": 3}   ts 1787438101.139
```

Exactly 3 attempts (`maximum_attempts=3`), backoff 1 s → 2 s
(`backoff_coefficient=2.0`) visible in the timestamps. The failure surfaced in
queryable workflow state:

```
"failure": "flaky_stage exhausted retries: StubTransientError: deliberate stub failure on attempt 3"
```

**Not swallowed** — readable by query and visible in the UI, which is the
contrast with the swallowed-failure register.

## Two spike bugs worth recording

1. **`handle.query("state")` returns an undecoded `dict`.** Querying by name
   string gives the SDK no result type, so `.__dict__` raises. The gate-detection
   loops in the first demo run therefore never matched and fell through to their
   **timeouts** — the run only *appeared* to work. Fixed by querying through the
   method reference. **The first run's timings are not trustworthy for gate
   latency;** run 2 is the canonical one.
2. **`resume_evidence.py` printed a false `PASS` over an empty table.**
   `ev.event_type` is a plain `int`, not an enum with `.name`, so every match
   failed, zero activities were counted, and "no activity completed twice"
   was trivially true. Fixed with `EventType.Name(...)`. Recorded because a
   false PASS is worse than a failure, and this one would have been quoted at
   the review board.

---

# Rulings applied

All six decisions were ruled by the operator on 2026-08-22 and are applied in
this commit. Nothing is outstanding.

| # | Ruling | Applied where |
|---|---|---|
| **D-1** | **(a) fatal-with-retry**, explicitly **contingent on ledger P2.6 making the heartbeat registry real by implementation time** — if P2.6 has not landed, the decision reopens rather than shipping fatal against an empty registry | Draft 2 §7 (O-3); checklist item **A-8**, marked pre-ruled |
| **D-2** | **90 days** event-history retention, applied as configuration **at M3.3 — nothing applied now** | Draft 2 §7 (O-4); checklist C. **The node-07 cluster was deliberately left at its default; no retention config was touched.** |
| **D-3** | `dev/spikes/` **is** an accepted repo path | `dev/CLAUDE.md` §12, one paragraph after the `dev/workorders/` ruling |
| **D-4** | **Measured: NO.** Only node-03 consumes `gpu_video` | Draft 2 §4.5 (rewritten, now a 4th material correction); checklist C-1; Lane A above |
| **D-5** | Leave the node-07 cluster running | No action — `restart: unless-stopped`; verified still healthy |
| **D-6** | §8 amendment wording **accepted as drafted** | Draft 2 §4.3; checklist item **A-4**, marked pre-ruled |

## What D-4 changed, and what it did not

D-4 is the only ruling that altered a factual claim rather than settling a
preference, so it is called out separately.

**Changed.** D1's headline consequence — "the duplicate can execute
concurrently on the other node" — is **false in the deployed fleet.**
`gpu_video` has a single active consumer, `cogvideox-worker@node03`, at
`--concurrency=1`. Node-02's `gpu_video` worker exists but has been stopped
for two months. **D1's severity is downgraded**, and Draft 2 and the checklist
now say so.

**Not changed.** The defect itself. `broker_visibility_timeout = 3600`
(`config.py:214-215`) still sits below `time_limit = 3900`
(`video_generation_task.py:445`) with `task_acks_late = True`
(`celery_app.py:288`). A video task exceeding 3600 s **is** redelivered and
**does** execute twice. Only the blast radius shrank: serialised behind the
original on one worker, not racing it on a second GPU.

**The honest reading for the board.** This is not "D1 was overstated, so the
case is weaker." The premise is one `--profile standby` away from being
exactly true. It is §2.2(1)'s argument in miniature — correctness resting on a
guessed timeout plus a deployment detail nobody re-checks. **If D1 is weighted
lower, §2.2's structural argument should be weighted correspondingly higher.**

## Access correction

The rulings round initially failed to reach node-02 and node-03: `dev@` is
rejected by publickey there. The operator corrected the handover — **nodes
02–06 use `root@`; only node-07 uses `dev@`.** With `root@` both nodes were
reachable and were inspected read-only (`docker ps`, `docker inspect`; no
state changed). The earlier broker-based measurement and the later on-node
measurement agree exactly.

**Still untested:** reachability from nodes 02–06 *to node-07* on 7233. The
broker route answers what workers consume; it says nothing about whether those
nodes can reach the Temporal cluster. Flagged in the checklist preconditions
as a pre-§11.2-step-1 check.

# Verified live vs inferred

**Verified live** — observed on a running system this session:

- **D1's two-node `gpu_video` premise (rulings round).** Measured three ways:
  repo compose profiles, `celery inspect active_queues` against the live
  broker (5 workers online), and the running container commands read on
  node-02 and node-03 themselves. All three agree: **only node-03 consumes
  `gpu_video`.**

- node-07 hostname, OS, RAM, disk, absence of Docker; installed Docker/Compose versions
- All four container images pulled at their pinned tags and running healthy
- auto-setup's database-creation skip, read from `/etc/temporal/auto-setup.sh:207` **inside the image**
- The server binding to the container IP, read from `netstat` inside the container
- Both databases created; default namespace registered
- gRPC 7233 and UI 8080 reachable **from node-01**
- Hello-world workflow executed and confirmed via `temporal workflow show`
- Full-stack `restart`; history intact afterwards
- DAG compiling to 10 waves; the shadow workflow running end to end
- The resume demonstration: ledger, event history, and CLI extract, all three
- The retry demonstration: 3 attempts, backoff intervals, failure in workflow state
- Every Lane A file:line — each grepped against HEAD in this session

**Inferred / not verified** — stated as such:

- **The deployed-image question for D4.** The signature drift is confirmed *in
  source at HEAD*. No call site was executed and no running container was
  inspected. `CLAUDE.md`'s caution about the deployed image still stands.

- **Reachability from nodes 02–06 to node-07.** Only node-01 → node-07 was
  tested. Opening a shell on node-02/03 does not establish this.
- **The 8–14 session / 600–900 line estimates.** Carried forward from Draft 1
  unchanged. Nothing here measures them; Draft 2 says so explicitly.
- **The claim that the 23 in-stage `send_task` sites are *all* the stage-body
  coupling to the coordination layer.** They are all the `send_task` sites.
  Other coupling (shared Redis keys, `IVGSBaseTask` behaviour) was not audited.
- **Production behaviour of anything.** No pipeline code was run, no pipeline
  database was touched, and nothing on nodes 01–06 was modified.

---

# Boundary compliance

| Constraint | Status |
|---|---|
| **No migration code** | Honoured. Nothing in `ivgs-api/`, `ivgs-workers/`, `ivgs-scheduler/`, `shared/`, or any compose file for nodes 01–06 was modified. |
| Software installed on node-07 only | Honoured. node-01 saw read-only inspection plus new files under `docs/`, `configs/temporal/`, `dev/`. In the rulings round node-02 and node-03 were inspected **read-only** (`docker ps`, `docker inspect`) under the operator's explicit D-4 instruction; nothing was installed, started, stopped or changed on either. |
| Spike isolated | Honoured. `dev/spikes/temporal/` imports nothing from IVGS; nothing imports it; README states it is throwaway. |
| No pipeline database access | Honoured. The cluster has its own Postgres on node-07. |
| Disjoint from concurrent WP-IVGS-0 | Honoured. WP-IVGS-0's changes were already committed at `8092cd8` before this session began; the working tree held only this package's own files. **Only explicitly listed paths were staged.** |
| Never block on a decision | Honoured — 6 recorded, none picked by WP-31. All six subsequently **ruled by the operator** and applied; see "Rulings applied". |
| Max 3 retries on a failing dependency | Honoured. The cluster took 3 deploy attempts (initial, B-1 fix, B-2 fix), each a diagnosed root cause, not a blind retry. |
| Commit and HOLD | Honoured. Nothing pushed, in either round. |
| Concurrent-session hygiene (rulings round) | Honoured. Another session committed `cf3d59b`, `17c8b8c`, `d5d8e7d` during the pause; those are untouched and only WP-31 paths plus the operator-directed `dev/CLAUDE.md` line were staged. |

---

# Exit gate

| Requirement | Status |
|---|---|
| Lane A dossier committed (amendment + checklist + census) | **Met** — Draft 2 with Appendices B and C, plus the checklist |
| Lane B cluster up, versions pinned | **Met** — 4 services, all pinned, no `latest` |
| Lane B smoke workflow verified via CLI | **Met** — `temporal workflow show`, not client output |
| Lane B persistence proven across restart | **Met** — full-stack restart, history intact |
| Lane C resume demonstration with event-history evidence | **Met** — 13/13 exactly once, plus the ledger and CLI extract |
| All commits HELD | **Met** |
| Report with lanes separated, live vs inferred distinguished | **Met** |
| If a lane was blocked, say where and why | **No lane was blocked.** |

---

## Operator quick reference — node-07

```bash
ssh dev@192.168.1.96
cd /opt/temporal

sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs -f temporal
sudo docker compose --env-file .env down          # stop, keep data
sudo docker compose --env-file .env down -v       # stop AND DESTROY history

sudo docker exec temporal-admin-tools temporal workflow list --address temporal:7233
```

Web UI: <http://192.168.1.96:8080> · gRPC for fleet workers: `192.168.1.96:7233`

The Postgres password was generated **on node-07** with `openssl rand -hex 24`,
lives only in `/opt/temporal/.env` (mode 0600, untracked), and **is not in the
repo and does not appear in this report**. `configs/temporal/.env.example`
carries the variable names; `configs/temporal/.gitignore` excludes `.env`.

*End of report.*
