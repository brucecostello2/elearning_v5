# Design decision — who creates `storage_quotas` rows

| | |
|---|---|
| **Status** | **DRAFT — recorded, not built.** WP-45 Task 6(g) says RECORD the decision and *do not build unprompted*. Nothing in this document has been implemented. |
| **Raised by** | WP-40 §9.7, re-raised as WP-45 Task 6(g) |
| **Date** | 2026-08-25 |
| **Owner** | Operator |

---

## 1. What is true today

`storage_quotas` has **0 rows** (measured 2026-08-25 on node-01's Postgres), and
**nothing creates one.** The table, the ORM model and two routes all exist:

| Piece | Where | State |
|---|---|---|
| Table | migration `0012_storage_quotas` | created, empty |
| Model | `ivgs-api/app/models/storage_quota.py` | complete |
| `GET /api/v1/quotas/{entity_type}/{entity_id}` | `app/api/v1/quotas.py:33` | works, 404s on every entity |
| `PUT /api/v1/quotas/{entity_type}/{entity_id}` | `app/api/v1/quotas.py:78` | works, and is the **only** writer in the codebase |

So a quota exists exactly when an admin has PUT one by hand, and no admin has.
The Storage → Quotas panel consequently shows "No quota data", which WP-40 made
honest rather than hiding.

Columns: `entity_type` (`project` | `user`), `entity_id`, `max_bytes`,
`current_bytes`, `tier` (nullable), `alert_threshold_pct` (default 80).

## 2. The two questions, which are separate

They have been discussed as one and they are not.

**Q1 — who creates the row, and when?**
**Q2 — who keeps `current_bytes` true?**

A row with a `max_bytes` nobody enforces is decoration. A `current_bytes` nobody
updates is worse: it is a number on a dashboard that was true once.

## 3. Options for Q1 (row creation)

| Option | Mechanism | Implication |
|---|---|---|
| **A. Admin-only, as now** | The `PUT` route is the only writer | Honest and already built. Quotas apply to whoever an admin has thought about; everyone else is unlimited. Zero new code. |
| **B. On project creation** | `ProjectService.create_project` inserts a row from a configured default | Every project is covered from birth. Needs a default `max_bytes` that is a policy decision, and a migration/backfill for the 16 existing projects. |
| **C. On user creation** | `UserService` inserts a `user` row | Matches the frontend, which polls `/quotas/user/{id}` — the 404s WP-40 §4 reduced. Per-user is the fairer unit when several operators share a fleet. |
| **D. Lazily, on first read** | `GET` creates from a default when absent | Never 404s. But a GET that writes is a surprising contract, and it hides the fact that nobody has set a policy. |

## 4. Options for Q2 (`current_bytes`)

| Option | Mechanism | Implication |
|---|---|---|
| **W. Derive, never store** | Compute `SUM(assets.file_size_bytes)` per entity on read | Cannot drift. This is the same ruling WP-43 D-1 made for per-language progress, and WP-45 implemented that way. One aggregate over an indexed FK; cheap at this fleet's size. `current_bytes` becomes a cache at most. |
| **X. Increment on upload** | `AssetService.upload_asset` adds, `delete_asset` subtracts | Drifts the first time a path misses. The scheduler's own `pq:depths` counter is the cautionary tale — WP-45 Task 4 found it reporting `urgent: 28` against 20 real entries and `normal: -6`, a **negative** count of a thing that cannot be negative. |
| **Y. Periodic sweep** | A Celery beat task recomputes | Correct between runs, wrong within them, and adds a scheduled job to maintain. |

## 5. Recommendation

**A + W.** Keep admin-set quotas, and derive usage.

The reasoning is the same one this work package has been applying all week: the
system already has more places where a number is written than places where a
number is checked, and every one of those has drifted. `current_bytes` as a
stored counter is `pq:depths` again, with a bigger blast radius — the difference
between "the dashboard is wrong" and "an upload was refused against a quota that
was never really full".

Deriving costs one `SUM` over `assets.file_size_bytes` grouped by
`project_id`, on a table with an indexed FK and a few dozen rows per project.
If that ever becomes expensive, the fix is a materialised view with a stated
refresh interval — an explicit cache with a known staleness — not an
incrementing counter with an unknown one.

**A over B/C/D** because enforcement does not exist yet either. Creating rows
before anything reads them for a decision would add provisioning to maintain in
exchange for nothing. When enforcement is built, C (per user) is the better
unit and creation should move there.

## 6. What is NOT decided here

* Whether quotas are **enforced** at all. Nothing currently refuses an upload
  for quota reasons, and WP-45 did not add that.
* The default `max_bytes`, which is a capacity question for the operator, not an
  API question.
* Whether `tier` participates. The column allows a per-tier quota; every
  discussion so far has assumed a single total.

## 7. Decision

> _Operator ruling to be recorded here._
