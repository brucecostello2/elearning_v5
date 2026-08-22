# WP-31 Lane C — Temporal shadow-workflow spike

> **This code is EVIDENCE, NOT FOUNDATION.**
>
> It exists to show the AD-05 review board that a property works before they
> are asked to approve a migration that depends on it. It is throwaway. It
> imports nothing from IVGS, it is imported by nothing in IVGS, and no part of
> it should be promoted into the migration. When AD-05 is approved and real
> workflow code is written, **delete this directory.**
>
> The M3.1 review-board gate is closed. WP-31 wrote no migration code.

## What this proves

| # | Claim | Where it is demonstrated | AD-05 |
|---|---|---|---|
| 1 | Stage order can be **derived from a DAG**, not hardcoded | `pipeline_dag.py`, walked by `workflow.py` | §5.1 design input |
| 2 | The per-scene fan-out needs **no counter, no join key, no watchdog** | `workflow.py::_fan_out_scenes` | §5.2, defect D2 |
| 3 | Human gates are **signals** that block indefinitely | `workflow.py::_await_gate` | §5.3 |
| 4 | **A killed worker resumes without re-running completed activities** | `demo_resume.sh` | §12 test 5 — the headline |
| 5 | Retries are **bounded and the failure surfaces**, never swallowed | `demo_retry.sh` | §9 |

## Cluster

Runs against the WP-31 Lane B dev cluster on **node-07 (192.168.1.96)**.
Compose file: `configs/temporal/docker-compose.yml`, deployed at
`/opt/temporal/`. UI: <http://192.168.1.96:8080>. gRPC: `192.168.1.96:7233`.

## Setup (on node-07)

```bash
cd /home/dev/spikes/temporal
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # temporalio==1.31.0
```

## Re-running each demonstration

### Lane B smoke test — cluster and SDK talk to each other

```bash
.venv/bin/python3 smoke_hello.py ivgs-smoke-hello-$(date +%F)
# verify from the CLI, not from the script's stdout:
sudo docker exec temporal-admin-tools temporal workflow show \
    --address temporal:7233 --workflow-id ivgs-smoke-hello-$(date +%F)
```

### Demonstration 1 — the DAG

```bash
python3 pipeline_dag.py     # prints the compiled parallel groups; needs no cluster
```

### Demonstration 2 — resume (THE HEADLINE)

```bash
./demo_resume.sh my-run-id
```

Starts a worker, starts the workflow, signals gate 1, waits until
`KILL_AFTER_SCENES` (default 2) scenes have **completed**, waits a further
`KILL_DELAY_S` (default 8 s) so the `SIGKILL` lands **mid-activity** rather
than on a completion boundary, kills the worker, restarts it, signals gate 2,
and prints the ledger analysis before and after.

Then read the durable history:

```bash
.venv/bin/python3 resume_evidence.py my-run-id
```

**Two independent sources of truth, deliberately:**

- `analyze_ledger.py` reads a JSONL file the **activity bodies** write and
  `fsync` themselves. It says what actually executed.
- `resume_evidence.py` reads the **event history** from the server. It says
  what was durably recorded.

The gap between them is the point (see below).

### Demonstration 3 — bounded retries, failure surfaced

```bash
./demo_retry.sh my-retry-id
```

## The result that matters most

From the 2026-08-22 run (`ivgs-resume-demo-run2`):

- The durable history holds **13 activity schedules and 13 completions — every
  one exactly once.** The workflow ran to completion across a worker death.
- Stages 1 and 2, and scenes 1 and 5, completed on worker A (pid 46636) and
  were **never re-run** after the restart. The pipeline did not go back to
  stage 1.
- The ledger recorded **15 body executions, not 13.** Scenes 3 and 4 were
  in flight when the worker was killed, and their bodies ran a second time.

**That gap is not a bug and it is not noise.** Temporal guarantees the
*workflow* advances exactly once; *activities* execute at least once. An
activity killed after finishing its work but before its completion is reported
will run again. It is a small window and it is unavoidable.

The operational consequence — **every writing activity must be idempotent on
`(job_id, stage, scene_index)`** — is written up as a binding requirement in
AD-05 Draft 2 §6. If the spike had been built to hide this, the review board
would have approved the migration without being told about it.

## Files

| File | What it is |
|---|---|
| `pipeline_dag.py` | The DAG and `topological_waves()`. Pure; runs standalone. |
| `shared_types.py` | Payload dataclasses shared by workflow and activities. |
| `activities.py` | Stub activities. Sleep, heartbeat, write the ledger. |
| `workflow.py` | The shadow workflow: DAG walker, fan-out, gates, queries. |
| `worker.py` | The worker process. This is the one `demo_resume.sh` kills. |
| `run_demo.py` | Driver: start / signal / state / result. |
| `analyze_ledger.py` | Body-execution view of the resume evidence. |
| `resume_evidence.py` | Durable-history view of the resume evidence. |
| `smoke_hello.py` | Lane B hello-world smoke test. |
| `demo_resume.sh` | Demonstration 2. |
| `demo_retry.sh` | Demonstration 3. |

## Two bugs this spike hit, recorded so they are not re-hit

1. **`handle.query("state")` returns an undecoded `dict`.** Querying by name
   string gives the SDK no result type. Query through the method reference —
   `handle.query(VideoPipelineShadowWorkflow.state)` — to get the dataclass
   back. Cost a full demo run: the gate-detection loops silently fell through
   to their timeouts and the demo only *appeared* to work.
2. **`ev.event_type` is a plain `int`, not an enum with `.name`.** Use
   `EventType.Name(ev.event_type)`. Before the fix, `resume_evidence.py`
   matched nothing and printed a confident `PASS` over an empty table — a
   false pass, which is worse than a failure.
