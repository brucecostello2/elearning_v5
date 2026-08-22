# WP-31-TEMPORAL-GROUNDWORK — AD-05 review dossier, Temporal dev cluster, resume spike

| | |
|---|---|
| **Ledger** | M3.1 preparation (AD-05 review-board gate) + M3.2 completion (Temporal on node-07). Does NOT open M3.3 — no migration code is authorized by this package. |
| **Tier** | B (observable) — designed for a single long UNATTENDED session |
| **Report** | `reports/WP-31-TEMPORAL-GROUNDWORK-report_<YYYY-MM-DD>.md` |
| **Nodes** | node-01 (repo work) and node-07 = 192.168.1.96 (Temporal cluster ONLY) |

## Unattended profile — binding

This package runs overnight with no operator available. Therefore:

1. **Never block on a decision.** Where the operator's ruling would normally be
   required, record the question and the options in the report under
   "DECISIONS REQUESTED", pick nothing, and continue with the other lanes.
2. **Never retry a failing external dependency more than 3 times.** Record and move on.
3. Commit-and-HOLD as always; the operator pushes. Report mandate as always.
4. If node-07 (192.168.1.96) is unreachable over SSH, record that in the report
   and complete Lanes A and C anyway. Do not attempt to fix network or keys.

## Hard boundaries — binding

- **NO migration code.** The M3.1 gate (Master Plan v0.4, review-board approval
  before any code) remains closed. Nothing in this package modifies
  `ivgs-api/`, `ivgs-workers/`, `ivgs-scheduler/`, `shared/`, or any compose
  file for nodes 01–06.
- Software may be installed on **node-07 only**. No other node is touched
  beyond read-only commands on node-01.
- Spike code lives in `dev/spikes/temporal/` only, is imported by nothing in
  production paths, and its README states it is throwaway evidence.
- No pipeline database access. The cluster gets its own Postgres on node-07.
- WP-IVGS-0 may be running in the same repo concurrently. Your file set is
  disjoint by design (docs/, dev/spikes/, node-07). If `git status` shows
  changes in files you did not touch, do not stage them — commit only your own
  paths, explicitly listed.

## Lane A — AD-05 code-grounded review dossier (the meat)

Purpose: turn AD-05 from an authored draft into an approvable design. The
operator's review-board approval is the gate for all migration work; this lane
produces everything needed to grant it.

1. Read `docs/IVGS_v5_Addendum_AD-05_Orchestration_Migration.md` in full,
   including the design-input line added 2026-08-22 (storyboard compiled to an
   explicit dependency DAG — per-scene depends_on / parallel groups — rather
   than a hardcoded stage sequence).
2. **Verify every factual claim in AD-05 against HEAD.** Celery config values,
   task names, fan-out sites, state writes, line counts of code proposed for
   deletion. Where AD-05 and the repo disagree, the repo is right — record every
   discrepancy with file:line.
3. **Celery touchpoint census.** Every place the orchestration layer touches
   Celery/Redis semantics: broker config, `acks_late`, visibility timeout,
   `STAGE_TASK_MAP` dispatch, group/chord fan-outs, watchdogs, checkpoint
   stubs, retry/DLQ dead weight. Output: one table, file:line, with the AD-05
   workflow/activity construct that replaces each row (or "deleted, replaced by
   Temporal primitive X").
4. **Activity-boundary table per stage (1–8).** Real task signatures at HEAD →
   proposed activity signature, idempotency notes, timeout/heartbeat
   parameters, which node's worker queue serves it.
5. **DAG design section.** How the storyboard (today: flat scene list; P2.32
   notes the contract carries no dependency fields yet) compiles to the
   workflow's execution graph now, and how per-scene depends_on / parallel
   groups slot in when the AD-07 v2.x extension lands. The design must not
   require the v2.x fields to exist yet.
6. **Deliverables:** (a) an AD-05 amendment draft (new version number, change
   log, discrepancies corrected) committed alongside the original; (b) a
   one-page operator approval checklist — the specific things the operator is
   being asked to approve, each with a plain-English risk statement; (c) the
   census + boundary tables in the report or an appendix file.

## Lane B — Temporal dev cluster on node-07

1. Precheck: `ssh root@192.168.1.96 hostname` — expect success; record the
   hostname. Verify Ubuntu version, disk, RAM, and that Docker is present
   (install docker-ce if absent — this node is greenfield; record versions).
2. Deploy Temporal server via docker compose with **Postgres persistence**
   (its own Postgres container, its own volumes on node-07), Temporal UI, and
   admin-tools. **Pin every image by explicit version tag — no `latest`**
   (the WP-09 lesson). Record every pinned version in the report.
3. Compose file and any config live on node-07 under `/opt/temporal/` AND a
   copy is committed to the repo under `configs/temporal/` (tracked, no
   secrets — generate any passwords on node-07, reference them via an
   untracked `.env` there, and say so in the report).
4. Smoke test: Python SDK hello-world workflow executed against the cluster
   from node-07; verify completion via `temporal workflow show` (CLI), not
   just client output. Confirm the UI serves on the LAN and note the URL.
5. Survivability: `docker compose restart` the whole stack; confirm the
   completed workflow's history is still queryable afterwards (persistence
   proof, not assumption).

## Lane C — shadow-workflow spike (review-board evidence)

In `dev/spikes/temporal/`, Python SDK, against the Lane-B cluster:

1. A workflow modeling the 8-stage pipeline as **stub activities** (sleep +
   log; zero IVGS imports), including: one per-scene fan-out (6 parallel stub
   scenes), one human-approval gate implemented as a **signal**, and stage
   ordering derived from a small in-code DAG structure rather than a
   hardcoded call sequence (evidence for the design-input line).
2. **The resume demonstration — the headline.** Start a run, kill the worker
   process mid-stage-5 fan-out, restart the worker, and show the workflow
   completes without re-executing the activities that already finished.
   Capture the event-history extract proving which activities ran once.
   This is the property the entire migration exists to buy; the review board
   should see it working before approving.
3. A deliberately failing activity with a retry policy — show bounded retries
   and the failure surfacing in workflow state (no swallowed failure).
4. README: what the spike proves, how to re-run each demonstration, and a
   statement that this code is evidence, not foundation.

## Exit gate

Lane A dossier committed (amendment draft + approval checklist + census);
Lane B cluster up with pinned versions, smoke workflow verified via CLI, and
persistence proven across a restart; Lane C resume demonstration captured with
event-history evidence. All commits HELD. Report saved with lanes separated
and every "verified live" claim distinguished from "inferred". If any lane was
blocked, the report says exactly where and why, and the other lanes are complete.
