# IVGS Work-Package Queue and Common Rules

| | |
|---|---|
| **Prepared** | 2026-08-14, from Agent Development Plan v1.0 + OUTSTANDING_WORK.md v4.1 + runbook 2.1 |
| **Location** | `/opt/ivgs/dev/workpackages/` — package briefs live here; reports in `reports/` |
| **Operator** | Bruce Costello — sole merge authority. Agents author and propose only. |

## How a session starts

1. Start from `/opt/ivgs/dev` so `CLAUDE.md` auto-loads. Read it in full if it did not.
2. Run the runbook §1 session-start gate. Record the actual HEAD SHA in your report.
   All `file:line` references in these briefs were audited at `e613e844`; the repo has
   moved (`b09b70f`+). **Re-verify every reference before relying on it.**
3. Determine the current package (next section). Read its brief in full, plus the
   ledger items it names in `OUTSTANDING_WORK.md`.

## Sequencing — self-managing

**Track S (sequential — the critical path).** Order is fixed:

| # | Package | Gate before proceeding |
|---|---|---|
| 1 | `WP-15-DOCS-APPLY` | Exit gate met, report written |
| 2 | `WP-00-DETECTOR` | Exit gate met, report written |
| 3 | `WP-02-ORCH6` | **HARD STOP at pass 1** — operator reviews findings before any code |
| 4 | `WP-03-STAGE8-VALIDATION` | Visual QA is operator-only; agent half must be complete |
| 5 | `WP-04-FRAME-ALIGN` | **Blocked until operator supplies the AD-03 Q5 fps value** |
| 6 | `WP-05-VISIBILITY-TIMEOUT` | Exit gate met |
| 7 | `WP-06-MEDIA-JOIN` | Exit gate met |
| 8 | `WP-07-CHECKPOINTS` | Exit gate met |
| 9 | `WP-08-GPU-RESERVATIONS` | Contradiction resolution step first — see the brief |

**A package is CLOSED when its report exists in `reports/` and records the exit gate
as met with evidence.** At session start, list `reports/`: the first Track-S package
with no report is the current package. Never skip ahead; never run two Track-S
packages in one working tree at once — they all touch the orchestrator or a stage task.

**Track P (parallel-safe — any order, any time).** `WP-09` … `WP-14`, `WP-18`, `WP-19`,
`WP-23` (storage analytics page), `WP-24` (node monitor). Disjoint file sets; safe while
Track S is blocked on the operator. If run concurrently with other work, use
`git worktree add` and say so in the report. WP-23 and WP-24 both touch the frontend —
run them sequentially or in separate worktrees, never together in one tree.

**Not in this queue** (operator-only or out of agent scope): overnight-backup verdict,
visual QA of `final_1080p_9007b2cf.mp4`, node-07/host-capacity decision, S-1 token
rotation (WP-16), and every M3/AD-05 migration package.

## Common rules — binding on every package

1. **No commit, push, merge, or deploy.** Leave changes unstaged in the working tree;
   the report lists every touched file. The operator commits.
2. **Two passes.** Pass 1: findings + proposed fix with `file:line` evidence — written
   into the report BEFORE any code is edited. Pass 2: what changed, how verified, what
   remains open. Tier C packages STOP after pass 1 until the operator approves.
3. **Evidence discipline.** Separate **verified live** from **inferred from reading
   code**, in labelled report sections. An exit code of 0 is not proof — check the
   artifact. Cite `file:line` for every behavioural claim.
4. **Ground truth.** Verify against committed code and running containers — never
   against these briefs, the ledger, or any summary. Where a brief and the repo
   disagree, the repo is right; record the discrepancy in the report.
5. **Never:** `git clean`, `git rm`, any destructive git operation; touch
   `ivgs-infra/.env.node01`; print secrets; modify the eight stage task bodies except
   where a brief explicitly scopes it; run commands on any node other than node-01.
6. **Scope stop-rule.** If the fix genuinely requires edits outside the brief's stated
   file set, STOP, record why in the report, and wait. Do not widen scope to seem
   thorough; do not narrow it to seem fast.
7. **Swallow-failure ledger.** Any new instance of "error path returns a sentinel no
   caller checks" found during any package is appended to
   `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` in the same session.

## Report protocol

- Path: `/opt/ivgs/dev/workpackages/reports/`
- **Name: `WP-<ID>-<NAME>-report_<YYYY-MM-DD>.md`** (e.g. `WP-15-DOCS-APPLY-report_2026-08-15.md`)
- Structure: header (package, HEAD SHA, date) → Pass 1 (findings, evidence basis
  split live/inferred, proposed fix, decisions requested) → Pass 2 (change summary
  with diff stat, verification observed vs not, open items) → exit-gate verdict.
- Plain ASCII throughout.

## Suggested operator kickoff prompt

> Read /opt/ivgs/dev/workpackages/WP-QUEUE.md and determine the current Track S
> package by scanning reports/. Execute it under the queue's common rules. Stop
> where the brief says stop.

For a Track P package, name it explicitly instead.
