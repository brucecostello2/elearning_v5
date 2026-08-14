# ADR-005: Temporal as the Durable Execution Engine

**Date:** 2026-08-14
**Status:** Accepted
**Deciders:** Bruce Costello (merge authority / review board)
**Related:** AD-05 Orchestration Migration (accepted 2026-08-14); Master Sequence Plan v0.4 (M3); `OUTSTANDING_WORK.md` v4.0 (P0.1, P1.1–P1.3, P2.1–P2.3)

---

## Context

The pipeline coordination layer is hand-rolled: a stage-transition lookup table, event-driven completion callbacks, Redis counters for the media fan-out join, a Beat watchdog to drain stranded joins, a checkpoint system, and bespoke retry/DLQ machinery.

A code audit of `e613e844` (2026-08-14) found four live correctness defects (duplicate GPU execution from a visibility timeout below two tasks' hard limits; a join that advances on incomplete media when Redis errors; a checkpoint subsystem that never writes; GPU reservation releases that raise `TypeError`), plus ~1,957 lines of orphaned operational machinery and zero test coverage on the 1,397-line live orchestrator.

The defects are fixable individually. Three underlying limits are not:

1. **No liveness signal.** Redis-as-broker offers only a pre-guessed visibility timeout. Any workload exceeding the guess reintroduces duplicate execution — a permanent tuning exercise against durations not yet run.
2. **At-least-once delivery, hand-guarded.** Every fan-out needs its own idempotency guard, written correctly, forever.
3. **Per-stage crash recovery.** Checkpointing is eight designs kept in sync; the current one decayed to a silent no-op undetected for months.

Remaining milestones push hard on all three: M4 adds five nodes; M5 multiplies runtimes tenfold and adds two new fan-outs (segment render, parallel talking-head), neither of which is written yet.

**The comparison is not "adopt an engine vs. do nothing."** The alternative is finishing the bespoke layer — wiring three orphaned services into eight stage tasks, building checkpoint write and resume semantics, join idempotency, orchestrator tests, plus the two unwritten fan-outs. That is ~9–13 sessions for a structurally weaker result maintained by one operator. A migration is ~8–14 sessions and deletes ~5,200 lines net.

## Decision

**Adopt Temporal**, self-hosted (MIT licence, satisfying the §1.4 zero-cloud mandate), on a **dedicated node**.

Deciding factors:

- **Durable execution by default.** Crash recovery is the engine's normal behaviour, not a subsystem to build and maintain.
- **Activity heartbeats replace guessed timeouts.** A long render is *long*, not suspicious; a hung one fails fast. This removes limit (1) as a category.
- **Signals map exactly to the two human gates.** The workflow blocks at `wait_condition` for days without a state machine to guard — removing the lenient `approve_storyboard` guard the e2e currently depends on.
- **Child workflows map exactly to the two unwritten fan-outs.** The most complex durable-execution code in IVGS does not exist yet; writing it as child workflows is materially less code than hand-rolling it.
- **The Web UI is a deciding feature, not a bonus.** M5's central problem is observing a multi-hour run. Execution history and run inspection are what make long-video debugging affordable — currently log files are the only evidence.

## Alternatives considered

| Option | Why not |
|---|---|
| **DBOS Transact** | Genuinely attractive: a Python library, no new containers, durable state in the existing Postgres — the option that respects node-01's 16 GB. Rejected only because dedicated compute became available, removing the constraint that favoured it. Youngest ecosystem of those considered. **Remains the designated fallback** if the dedicated node becomes unavailable; that would reopen AD-05 §3. |
| **Hatchet** | Postgres-backed durable workflows with concurrency keys. Comparable shape to Temporal but a larger migration (it can replace Celery itself) and a smaller operational track record. |
| **Prefect** | Good for scheduled ops flows with retries and a UI; weaker for per-request, GUI-triggered, event-driven jobs — which is the majority of IVGS's work. |
| **Celery Canvas (chord/group)** | Zero new infrastructure, and superficially the cheap middle path. Rejected on direct evidence from this codebase: `media_join_watchdog` exists precisely because chord-style joins strand on hard worker crashes. Adopting Canvas keeps the sweeper pattern and all three underlying limits. |
| **Airflow / Dagster** | Batch DAG schedulers; poor fit for GUI-triggered per-job pipelines with multi-day human gates. |
| **Argo / Flyte** | Require Kubernetes. Out of scope for a Docker Compose fleet. |
| **AWS Step Functions et al.** | Cloud-managed; violates the §1.4 self-hosted mandate outright. |
| **Do nothing / fix in place** | See Context — this is the ~9–13 session bespoke path with an unbounded discovery tail. |

## Rejected interim: RabbitMQ broker swap

Replacing Redis with RabbitMQ as the Celery broker would give a real liveness signal (the connection itself), closing the duplicate-execution class without a full migration. It was recommended during analysis and is **withdrawn**: once the migration is committed it is throwaway work, and pre-migration testing stays short enough that a config change to the visibility timeout suffices (ledger P0.1).

Redis is **retained** as cache and heartbeat store. It ceases to be the pipeline broker.

## Consequences

**Positive.** Four defect classes eliminated structurally rather than instance by instance. ~5,541 lines of coordination code replaced by an estimated 600–900. Resume-from-failure becomes the default, collapsing the M5 test-iteration loop for *every* bug class, not just orchestration ones. Pipeline state becomes truthful by construction, closing ORCH-5. Run inspection replaces log archaeology.

**Negative.** A new server component that must be up for any job to progress. Determinism constraints require moving I/O out of coordination code — a refactor, not an annotation. Versioning discipline (`workflow.patched()`, replay tests in CI) is mandatory from the first workflow, because multi-hour renders and multi-day gates mean workflows are *always* in flight during a deploy. A new class of replay-only bugs, unfamiliar to a single operator. Event history requires a retention policy.

**Accepted risk.** Trading a failure class that is understood for one that is not. Judged worthwhile because the new class is *loud* — failing at startup or visibly in a UI — where the current class logs a warning and silently drops footage.

**Neutral.** `ivgs-scheduler` is unaffected; VRAM-aware admission control remains domain logic called from an activity. Queue routing (spec Table 6-7) and AD-02 node specialization are preserved unchanged.

## Compliance

Temporal is MIT-licensed and self-hosted, satisfying §1.4 (100% self-hosted, zero cloud AI dependencies). It introduces no prohibited packages, environment variables, or endpoints, so the §1.4 CI compliance scans are unaffected. The architectural change itself is covered by AD-05 under the §18 change-control process.
