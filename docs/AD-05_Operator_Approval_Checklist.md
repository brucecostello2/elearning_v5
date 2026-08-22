# AD-05 — Operator approval checklist

**One page. Produced by WP-31 Lane A, 2026-08-22, against `8092cd8`.**

This is the §18 review-board gate. Approving AD-05 authorises migration code
to be written; it does not authorise cutover (§12 gates that separately).

Read alongside `IVGS_v5_Addendum_AD-05_Draft2_Amendment.md`. Each item is a
**separate** decision — approving one does not commit you to the next.

---

## A. What you are being asked to approve

| # | Approve this | Plain-English risk if you approve | Plain-English risk if you don't |
|---|---|---|---|
| **A-1** | **Temporal replaces the Celery coordination layer.** Engine choice per ADR-005. | You take on a new server to operate, a new failure mode (workflow determinism), and 8–14 sessions of work. If it stalls half-done you have two orchestrators — the exact P2.3 situation, one level up. | You finish the bespoke layer instead: ~9–13 sessions of unbounded discovery work, ending with weaker machinery that one person maintains. D1–D4 stay a recurring class, not a fixed list. |
| **A-2** | **Temporal runs on node-07, persisting to its own Postgres on node-07.** (Draft 1 O-1.) | One more machine to keep alive. If node-07 dies, no renders start — but nothing already-running is lost, because history is durable. | Persisting to node-01's Postgres extends the P1.9 SPOF onto the 16 GB node that already runs ~13 services. |
| **A-3** | **Sequencing moves into workflow code, expressed as a DAG.** (Draft 2 §5.) | The workflow becomes the single place stage order is decided. A mistake there affects every job. | `STAGE_TASK_MAP` stays: a stringly-typed lookup where a typo is a runtime-only error no static check catches. P2.3's defect class stays open forever. |
| **A-4** | **The migration may edit stage files at exactly 23 `send_task` sites** — and nowhere else. (Draft 2 §4.3, amended §8.) | The §8 "don't touch stage bodies" rule now has an exception, and exceptions get widened. | §8 as written forbids the edits the migration *requires*. A migration session hits site #11, reads the stop-rule, and either stops wrongly or widens scope silently. |
| **A-5** | **Every writing activity must be made idempotent on `(job_id, stage, scene_index)`.** (Draft 2 §6.) | Real work on all 8 stages, over and above the wrappers. Not free. | **Measured on node-07 2026-08-22:** a killed worker re-ran two scene activities. Without idempotency that is duplicate renders and duplicate uploads, silently, on every worker restart. |
| **A-6** | **Versioning (`workflow.patched()`) and a CI replay test from the first workflow written.** (Draft 1 §7.2.) | Discipline overhead on every workflow change, starting immediately. | Multi-hour renders plus multi-day gates mean in-flight workflows during every deploy. Retrofitting versioning after in-flight jobs exist is the documented failure mode. |
| **A-7** | **Periodic tasks move to Temporal Schedules; Celery Beat is removed.** (Draft 1 O-5.) | Beat's schedules must be re-created; one of them (`poll_model_node_availability`, every 30 s) is **live today** and must be re-homed before `periodic_tasks.py` is deleted. | Celery survives as a second orchestrator, which is the half-migration risk you are trying to avoid. |

---

## B. Preconditions you are confirming are understood

These are Draft 1 §11.1. **Approval does not waive them.**

- [ ] **M1 closed** — ORCH-6 done, Stage 8 validated, reference output banked.
      Without the reference output there is nothing to verify the migration against.
- [ ] **M2 closed** — D1–D4 fixed. You migrate *from* a working system, not onto a broken one.
- [ ] **Node-07 reachable from all fleet nodes.** WP-31 verified node-01 → node-07
      (gRPC 7233 and UI 8080). **Nodes 02, 03, 04 were NOT tested** — outside WP-31's boundary.
- [ ] **Cutover happens in a quiet window** with no in-flight jobs (§11.3).

---

## C. Decisions still open — you must rule, or explicitly defer

| # | Question | Recommendation | Consequence of deferring |
|---|---|---|---|
| **D-1** (O-3) | Is GPU reservation failure **fatal**, or does it fail open as today? | **Fatal with retry**, once P2.6 makes the registry real. Failing open silently is why `total_nodes:0` went unnoticed for months. | The migration carries the current silent-fail-open behaviour into the new architecture, and it will be just as invisible there. |
| **D-2** (O-4) | Event-history **retention period**. | 30 days is ample. A 6-scene shadow run produced **71 events / ~10.4 KB** — kilobytes per job, not megabytes. Cheap either way. | Defaults apply. Low risk now; revisit before M5's long runs. |
| **D-3** | Is the **estimate** (8–14 sessions, 600–900 replacement lines) accepted as the basis for approval? | Treat as an estimate. WP-31 measured nothing that confirms or refutes it. | You approve a plan whose cost is unmeasured. Stating that explicitly is better than implying it was verified. |
| **D-4** | Does D1's premise — **`gpu_video` consumed by node-02 *and* node-03** — hold? | **Verify before relying on it.** WP-31's boundary permitted node-01 read-only and node-07 only; this is unverified. | D1's *concurrent duplicate execution* consequence rests on an unchecked premise. The queue name and time limits are confirmed; the two-node claim is not. |

---

## D. What WP-31 already de-risked (no approval needed — evidence, not proposals)

Verified live on node-07, 2026-08-22. Details in
`dev/workpackages/reports/WP-31-TEMPORAL-GROUNDWORK-report_2026-08-22.md`.

- Temporal cluster stands up on a greenfield Ubuntu 24.04 node, all images
  pinned, with its own Postgres. **Working.**
- History survives a full `docker compose restart`. **Proven, not assumed.**
- An 8-stage pipeline shape, two signal gates and a 6-scene fan-out all run
  from a DAG structure, with no hardcoded stage sequence. **Working.**
- **A killed worker resumes without re-running completed activities.** 13
  activity schedules, 13 completions, each exactly once. **This is the property
  the entire migration exists to buy, and it works.**
- Bounded retries with the failure surfaced in queryable workflow state, not
  swallowed. **Working.**

---

## E. Sign-off

| | |
|---|---|
| Approve A-1 … A-7 (list any withheld) | ______________________ |
| Rule on D-1 … D-4 | ______________________ |
| Approved by | ______________________ |
| Date | ______________________ |

**Until this is signed, no migration code may be written.** WP-31 wrote none:
its spike lives in `dev/spikes/temporal/`, imports nothing from IVGS, and is
marked throwaway in its own README.
