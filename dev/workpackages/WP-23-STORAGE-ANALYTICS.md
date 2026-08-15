# WP-23-STORAGE-ANALYTICS — Storage Analytics page shows all zeros; title clipped

| | |
|---|---|
| **Ledger** | New item — propose the entry in the report. Related: P2.4 (dedup endpoints 404), P2.14 (sizes/durations not persisted), swallow register instance 7 (`run_retention_migration` is a stub) |
| **Tier** | B (observable) · **Track P** (parallel-safe — API/frontend only; do NOT run in the same working tree as WP-24, both touch the frontend; use a worktree if concurrent) |
| **Report** | `reports/WP-23-STORAGE-ANALYTICS-report_<YYYY-MM-DD>.md` |

## Symptom (operator-reported, 2026-08-15, screenshot on file)

`/monitoring/storage` (spec §8.2.6) shows zero everywhere: dedup savings 0%,
space saved 0 B, duplicate assets 0, and every tier (Hot/Warm/Cold/Archive)
0 B used / 0 allocated / 0 assets. This cannot be true — SeaweedFS holds tens
of GB of generated assets and the ledger records duplicate assets accumulating
(P2.20). Additionally the page's own H1 title is clipped under the fixed top
nav bar.

**Operator testimony: this page displayed data previously.** Treat that as a
regression claim. Per runbook §7.4, config causes outrank code causes here —
check environment/config drift before assuming broken code. The 2026-06-05
incident (env-name mismatch sprung by a recreate) is the precedent.

## Investigate (pass 1 — before any fix)

1. Which API endpoints does the page call? (browser network tab or read the
   frontend page source). For each: does it 404, 500, or return real zeros?
2. If real zeros: trace each to its source. Known suspects — dedup absent
   (`GET /assets?sha256=` 404s, P2.4); `assets.file_size_bytes` /
   `duration_seconds` population; tier data depending on `storage_tier` values
   nothing ever migrates (`run_retention_migration` is a stub — register
   instance 7); orphan report depending on `run_orphan_cleanup` (also a stub).
3. If the page previously worked: find what changed — git log on the relevant
   API/frontend files, container recreate history, env variables in the running
   containers (`docker exec <c> env`, not the .env file).
4. The title clipping: identify the CSS cause (fixed-header offset).

## Fix (pass 2, after findings)

**In scope:** the title-clipping CSS; any cheap honest fix (e.g. an endpoint
returning zeros instead of erroring should surface its true state; a query
reading the wrong column); honest empty-states ("no data — tier migration not
yet enabled") instead of confident zeros.
**Out of scope — propose only:** building dedup (P2.4), tier-migration
machinery, or anything touching the orchestrator/stage tasks. If the root cause
is "the subsystem was never built," say so plainly and propose the ledger entry;
do not build it here.

## Exit gate

Every number on the page is either demonstrably true (verified against Postgres/
SeaweedFS directly — show the queries) or replaced by an honest "not available"
state. The title renders fully. Report separates: worked-then-broke (with the
breaking change identified) vs never-wired (with ledger entries proposed).
