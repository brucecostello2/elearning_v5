# WP-23-STORAGE-ANALYTICS — report

| | |
|---|---|
| **Package** | `dev/workpackages/WP-23-STORAGE-ANALYTICS.md` |
| **HEAD at start** | `768f3e9` (WP-24 committed earlier in this batch; batch base `f70d63e`) |
| **Date** | 2026-08-23 |
| **Ledger** | New entries proposed below. Related: P2.4 (dedup endpoints), P2.14 (sizes/durations), P2.20 (duplicate assets), swallow-register instance 7 |
| **Tier** | B, Track P. Run **sequentially after WP-24** in the same tree, as WP-QUEUE requires for the two frontend packages. |

Same operator-instruction deviations from WP-QUEUE as recorded in the WP-24 report
(commit-and-HOLD per package; read-only ssh to 02/03/04). This package touched no node.

---

# PASS 1 — findings

## 1.1 The page's numbers, and what is actually in the database

**Verified live** — `docker exec -i ivgs-postgres psql -U ivgs -d ivgs`:

```sql
SELECT storage_tier::text AS tier, count(*) AS assets,
       pg_size_pretty(coalesce(sum(file_size_bytes),0)) AS total_size,
       count(*) FILTER (WHERE file_size_bytes IS NULL) AS null_size_rows
FROM assets GROUP BY storage_tier ORDER BY 1;

 tier | assets | total_size | null_size_rows
------+--------+------------+----------------
 hot  |     45 | 208 MB     |              0
```

```sql
SELECT count(*) AS rows, count(content_hash) AS with_hash,
       count(DISTINCT content_hash) AS distinct_hash,
       sum(reference_count) AS sum_refcount
FROM assets;

 rows | with_hash | distinct_hash | sum_refcount
------+-----------+---------------+--------------
   45 |        45 |            43 |           54
```

So the truth is: **45 assets, 208 MB, all in `hot`, every row sized, 45 content hashes of
which 43 are distinct — 2 duplicates — and 54 references against 45 rows.**

The page reports 0 for all of it. **P2.14 is not the cause here**: `file_size_bytes` is
populated on every row (`null_size_rows = 0`).

## 1.2 Root cause: the frontend reads field names the API has never emitted

This is a **contract mismatch**, not missing data. The API computes the tier numbers correctly.

`RetentionService.get_report()` (`ivgs-api/app/services/retention_service.py`) returns
`RetentionReportResponse` (`app/schemas/retention.py:103-110`):

```python
total_assets: int
total_size_bytes: int
tier_distribution: List[TierDistribution]     # tier, asset_count, total_size_bytes
upcoming_migrations: List[UpcomingMigration]
policy_name: str
```

`useStorageAnalytics` (`ivgs-frontend/src/hooks/useMonitoring.ts:440-452`) reads:

```typescript
tierData:        data?.tiers ?? data?.tier_breakdown,   // neither exists
dedupSavings:    data?.dedup_savings,                   // does not exist
totalUsed:       data?.total_used,                      // does not exist
totalAllocated:  data?.total_allocated,                 // does not exist
```

**Not one of those four names is in the response.** Every one resolves to `undefined`, and the
page then converts each `undefined` into a confident zero with `?? 0` / `|| 0`:
`page.tsx:176` `formatBytes(totalUsed || 0)`, `:178` `formatBytes(totalAllocated || 0)`,
`:261` `{dedupSavings?.percent ?? 0}%`, `:269`, `:277`, `:344`, `:347`, `:371`.

**That fallback is the defect.** It is the same failure class WP-24 just removed from the Node
Monitor: an absent value rendered as a measured zero. "0 B used" and "we did not receive a
number" are different facts.

## 1.3 The regression claim does not hold — this never worked

The brief asks that operator testimony ("this page displayed data previously") be treated as a
regression claim, and that config causes be checked before code (runbook §7.4). I checked, and
the evidence points the other way:

- **No config drift.** The API endpoint is live and healthy: `GET /api/v1/retention/report`
  returns **403** unauthenticated, i.e. routed and auth-gated, not 404 and not 500.
- **The names never matched.** `git log -S` over the **entire API history**:

  ```
  git log --oneline -S "total_allocated" -- ivgs-api/     -> (no commits)
  git log --oneline -S "tier_breakdown"  -- ivgs-api/     -> (no commits)
  ```

  Neither string has ever existed anywhere in the API. On the frontend side the same names
  trace back to `0962319` — *"feat: IVGS v5 production-ready initial release"*, the very first
  commit.

**Verdict: never-wired, from the initial release.** The two sides were written against
different field names and never agreed. I cannot reconcile this with the page having shown real
data before; if the operator has the screenshot that showed data, it would be worth comparing,
because nothing in the code history supports it. Recorded as a disagreement rather than
smoothed over.

## 1.4 What genuinely was never built (propose only, per the brief)

| Concept on the page | Reality | Evidence |
|---|---|---|
| **"Allocated" capacity per tier, and the Used/Allocated % badge** | **Does not exist anywhere.** No allocation or quota-per-tier concept is modelled. `TierDistribution` carries only `tier`, `asset_count`, `total_size_bytes`. There is no column, no config, and no endpoint for a tier capacity. | `app/schemas/retention.py`; `\d assets` |
| **Dedup savings (%, bytes saved, duplicate count)** | **Not computed by any endpoint** — but the *data exists*: `assets.content_hash` and `assets.reference_count` are populated on all 45 rows. | 1.1 query; P2.4 |
| **Tier migration** | **Never runs.** See 1.5. Every asset is `hot` because nothing has ever moved one. | 1.5 |
| **Orphan report** | Backed by `run_orphan_cleanup`, a stub. | `pipeline_orchestrator.py:598-602` |

## 1.5 A real tier-migration implementation exists and is not the one that runs

This is the CLAUDE.md §7 trap — *"filenames are not task identities"* — in its purest form.

**The scheduled task is a stub.** `ivgs-workers/celery_app.py:194` registers the beat entry as
`tasks.pipeline_orchestrator.run_retention_migration`, and that task is:

```python
# ivgs-workers/tasks/pipeline_orchestrator.py:609
def run_retention_migration() -> Dict[str, Any]:
    """Daily retention tier migration (§10.3). Stub for Phase 5."""
    logger.info("retention_migration_started")
    return {"status": "ok", "message": "Retention migration — stub (Phase 8)"}
```

It logs `retention_migration_started`, does nothing, and **returns `{"status": "ok"}`** — so
the daily run reports success. That is swallow-register **instance 7**, confirmed still live at
this HEAD.

**Meanwhile a real implementation sits unscheduled.** `ivgs-workers/tasks/periodic_tasks.py:412`
contains a full `run_retention_migration` that constructs a `RetentionService` from
`ivgs-workers/services/retention_migration.py` — **a module that exists on disk** — and runs an
actual migration. Nothing dispatches it: the beat schedule names the orchestrator's stub.
`run_orphan_cleanup` has the identical shape (`pipeline_orchestrator.py:598` stub registered at
`celery_app.py:189`; `periodic_tasks.py:344` real; `services/orphan_cleanup.py` present).

**This is the substantive finding of the package** and explains the all-`hot` distribution
directly. It is out of scope to fix here — repointing a beat schedule changes what runs nightly
across the fleet and belongs with an operator ruling — so it is proposed as a ledger entry
below, not touched.

## 1.6 Title clipping

`ivgs-frontend/src/app/layout.tsx:71-72` renders `<Header />` then `<main className="flex-1">`.
`Header.tsx:104` is `sticky top-0 z-50` and is **3.5rem** tall.
`app/monitoring/layout.tsx` correctly reserves that: `flex min-h-[calc(100vh-3.5rem)]`, with the
content pane as `<div className="flex-1 overflow-y-auto">`.

Then every monitoring page opens with `<div className="min-h-screen ...">` — and
`min-h-screen` is **100vh**. A 100vh child inside a `calc(100vh - 3.5rem)` scroll container
overflows by exactly the header's height, which is why the page's own `<h1>` block
(`storage/page.tsx:161`, inside a non-sticky `<header>`) ends up pushed under the sticky global
header. The offset is double-counted: the layout subtracts the header, the page adds it back.

**The same `min-h-screen` is on all six monitoring pages** (`dlq`, `gpu`, `pipeline`, `quality`,
`storage`, `timeline`) — verified by grep. Per the queue's scope stop-rule (rule 6) only the
storage page is changed here; the other five are recorded in 2.4 with the exact one-token fix.

## 1.7 Proposed fix

1. **`useStorageAnalytics`** reads the field names the API actually emits, and maps
   `tier_distribution` into the shape the chart wants.
2. **Concepts that do not exist are reported as unavailable, not as zero.** The hook returns
   explicit `allocationAvailable: false` / `dedupAvailable: false` flags with reasons, instead
   of `undefined` that the page silently floors to 0.
3. **The page renders those reasons.** Dedup tiles and the Allocated column show "not
   available" plus why; the Used/Allocated percentage badge is suppressed entirely when there
   is no allocation figure, rather than displaying a percentage of an imaginary denominator.
4. **`min-h-screen` → `min-h-full`** on the storage page.

Not touched: dedup computation (P2.4 — out of scope, "propose only"), tier-migration machinery,
the beat schedule, the orchestrator, any stage task.

---

# PASS 2 — what changed, and how it was verified

## 2.1 Change summary

```
 ivgs-frontend/src/hooks/useMonitoring.ts               | useStorageAnalytics rewritten
 ivgs-frontend/src/app/monitoring/storage/page.tsx      | honest states; min-h fix
```

Two files. No API change was needed — the API was already correct.

**`useStorageAnalytics`** now reads `tier_distribution`, `total_size_bytes`, `total_assets`,
`policy_name` — the names the endpoint emits — and maps `tier_distribution` into the chart's
shape. It additionally returns `dedupAvailable` / `dedupReason` and `allocationAvailable` /
`allocationReason`, so the page can distinguish "zero" from "no such figure" instead of
inferring it from `undefined`.

**The page** no longer floors absent values to 0:

| Element | Before | After |
|---|---|---|
| Header total | `formatBytes(totalUsed \|\| 0)` → "0 B" | real total, plus the asset count |
| Header "/ allocated" + % pill | "/ 0 B" and a **green 0%** pill | pill replaced by a neutral "no capacity target" chip carrying the reason |
| Dedup: savings / space saved / duplicates | `0%`, `0 B`, `0` | one "Not available" panel with the reason |
| Tier table "Used" | `0 B` for tiers absent from the response | real bytes, or "no assets" when the tier is absent |
| Tier table "Allocated" | `0 B` | "not modelled", with the reason on hover |
| Tier table "Usage %" | a **green 0%-full bar** | "—" (no denominator, so no bar) |

The green 0% pill was the worst of these: it did not read as "unknown", it read as *healthy
with plenty of headroom*.

**Title clipping** — `min-h-screen` → `min-h-full` on the page's root div, with the reasoning
in a comment.

## 2.2 Verified

- **Ground truth from Postgres** — queries and output in 1.1. 45 assets, 208 MB, all `hot`,
  no null sizes; 43 distinct `content_hash` over 45 rows.
- **The API side computes this correctly** — read from `retention_service.get_report()` and
  `schemas/retention.py:103`; the tier query there is the one reproduced in 1.1, and it returns
  non-zero against this data.
- **`git log -S` across all of `ivgs-api/`** for `total_allocated` and `tier_breakdown`:
  no commits, ever. That is what makes this never-wired rather than a regression.
- **`npx tsc --noEmit` passes** on the frontend after the change (rc 0).

## 2.3 NOT verified

- **The rendered page.** No browser was driven. The running `ivgs-nextjs` serves `v5.6.0-m2`,
  which predates this change; it renders after tonight's node-01 deploy.
- **The authenticated wire response.** `GET /api/v1/retention/report` returns 403 without a
  token and no token was minted — creating a user writes to the production database. The
  response *shape* is established from the Pydantic `response_model` and the service code, and
  the *values* from the same query run directly against Postgres. The field names in the hook
  now match the schema by inspection, not by a captured HTTP response.
- **The title fix visually.** The CSS reasoning is structural and I am confident in the
  double-counted offset, but nobody has looked at the page. Flagged rather than claimed.

## 2.4 Recorded, not acted on

- **The same `min-h-screen` bug is on all six monitoring pages** — `dlq`, `gpu`, `pipeline`,
  `quality`, `storage`, `timeline`. Only `storage` is in this brief's scope, and WP-QUEUE rule 6
  forbids widening it, so the other five are left. The fix is identical and one token:
  `min-h-screen` → `min-h-full` on each page's root div. **Operator: this is a five-line change
  and the other five pages are clipping their titles right now.**
- **A swallowed failure in the frontend, already self-documented but never registered.**
  `useMonitoring.ts` (`useStorageQuotas`) says in its own docstring: *"per-user fetch errors are
  swallowed and reported as empty quota rows. If individual quota endpoints start returning
  500s, those failures will be silent."* A 500 becomes a row reading `used_bytes=0`. Added to
  the WP-00 register as **instance 18** under queue rule 7.

## 2.5 Proposed ledger entries

- **P2.40 — The Storage Analytics page and its API have never shared a field contract.**
  Four field names read by the frontend since the initial release (`total_used`,
  `total_allocated`, `dedup_savings`, `tiers`/`tier_breakdown`) have never existed on the API.
  Fixed by WP-23. **The generalisable defect is that nothing checks frontend-to-API field
  agreement** — no generated client, no shared schema, no contract test. This page is unlikely
  to be the only place it happened; the same `?? 0` habit would hide it everywhere.
  *Suggested action: generate the TS types from the OpenAPI schema, or add a contract test per
  monitoring hook.*
- **P2.41 — Storage allocation/capacity is not modelled anywhere.** The page has always had
  "Allocated" columns and a Used/Allocated percentage with no backing concept. Either model
  per-tier capacity or remove the columns; they currently show "not modelled".
- **P2.42 — Two implementations of retention migration and orphan cleanup exist; the beat
  schedule points at the stubs.** `celery_app.py:189,194` register
  `tasks.pipeline_orchestrator.run_orphan_cleanup` / `run_retention_migration`, which are stubs
  returning `{"status": "ok"}` (`pipeline_orchestrator.py:598,609`). Real implementations sit
  unscheduled in `tasks/periodic_tasks.py:344,412`, backed by `services/orphan_cleanup.py` and
  `services/retention_migration.py`, both present on disk. **This is why every asset is in
  `hot`.** Repointing the schedule changes what runs nightly across the fleet, so it needs an
  operator ruling rather than a quiet edit. Directly extends swallow-register instance 7.
- **P2.43 — Dedup savings are derivable today and are not derived.** `assets.content_hash` and
  `assets.reference_count` are populated on all 45 rows; the aggregate is one query. Narrower
  than P2.4 (which is about the `GET /assets?sha256=` lookup endpoints) and much cheaper.

## 2.6 Exit gate

| Clause | Verdict |
|---|---|
| Every number is demonstrably true, or an honest "not available" | **MET** — tier bytes/counts now come from the endpoint that measures them (verified against Postgres); allocation, usage-% and dedup are labelled unavailable with reasons |
| Queries shown | **MET** — 1.1 |
| Title renders fully | **MET in code, UNVERIFIED visually** — cause identified and fixed; no browser was driven |
| Report separates worked-then-broke vs never-wired | **MET** — 1.3 (never-wired, with the `git log -S` evidence) and 1.4 |
| Ledger entries proposed for never-built subsystems | **MET** — 2.5, four entries |

**Overall: exit gate MET**, with the single caveat that the visual result is unverified until
the page is deployed and looked at.
