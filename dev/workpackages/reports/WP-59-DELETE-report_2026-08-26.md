# WP-59-DELETE — a project is eighteen categories, and two of the mechanisms meant to catch what deletion misses were stubs

**node-01, 2026-08-26.** Six commits, HELD, not pushed. Deployed to node-01 as
`v5.18.0-delete` across api / frontend / workers / backup-worker. Migration
0033 applied to both `ivgs` and `ivgs_reconciliation_test`.

---

## 0. The one page worth reading first

The deletion was built and it works — a watched, live deletion of a throwaway
project destroyed every mapped row, purged exactly the one object nothing else
pointed at, cleared five Redis keys, and left a library asset and a
cross-project object intact with their surviving references still resolving.
Screenshots excepted (§12), every acceptance criterion is met and quoted below.

**What the package found on the way is the part worth the operator's attention,
because three separate mechanisms this system relies on to notice things were
not running at all.**

| Finding | Status before | Evidence |
|---|---|---|
| The scheduled **tier migration** is a Phase-5 STUB returning `{'status':'ok'}` | WP-57 D-1 attributed the three-month standstill to a swallowed `UndefinedColumn` in the real service. The real service has **never executed once**. | `celery_taskmeta` holds `"Retention migration — stub (Phase 8)"` under the 04:00 dispatches of 2026-08-24 and 2026-08-25 |
| The scheduled **orphan cleanup** is also a stub | And the real `OrphanCleanupService` behind it queries `assets.storage_path` and `assets.status`, **neither of which exists**, and scans a filer namespace that is **empty**. It is inert three times over. | §3.3 |
| The configured **retention policy** has never governed anything | All three `retention_policies` rows have NULL in both terminal columns; the Pydantic model required them; the load raised into a bare `except` and fell back to hardcoded defaults, silently, since 2026-05-23. | §7.2 |

All three are the same shape as the 75-day backup gap and the four dashboards
WP-57 corrected: **a mechanism reporting health it did not have.** Task 2 named
`orphan_cleanup.py` as the backstop for anything the binary purge misses. It
could not have been one, and saying so is more useful than building on it.

A fourth, smaller, and the most dangerous single thing in the package: **every
database dump this system has ever taken begins `DROP DATABASE IF EXISTS
ivgs;`**. `pg_dump` is run with `--clean --if-exists --create`, so a restore
"into a new database" on the live cluster destroys production regardless of
what `-d` says — the `\connect ivgs` inside the file overrides it. That is why
Task 10's rehearsal runs in a separate cluster and gates its own filter (§10).

---

## 1. Per-task verdicts

| Task | Verdict |
|---|---|
| 1 — enumerate what a project is | **DONE.** 18 categories, built from `pg_constraint` on the live database. A test walks the cascade closure and fails on anything the map misses; it found one on its first run. |
| 2 — the deletion service, ordered so failure cannot lie | **DONE.** Audit-first, DELETING, rows, binaries, Redis. Idempotent and resumable from the audit manifest. **The orphan backstop it names does not work and this report says so.** |
| 3 — running work cancelled for real | **DONE.** Refusal observed; revoke observed reaching the broker and all five live workers; deletion then proceeded. Reservations read from the scheduler's own registry. |
| 4 — shared bytes and the library untouchable | **DONE.** Proven live, twice, with the guard shown to be dynamic rather than sticky. |
| 5 — what deletion means for backups | **DONE.** The dialog makes no backup promise; §9 states what recovery would actually involve. |
| 6 — the API is not a second, weaker door | **DONE.** `confirm_name` required, admin-gated, rate-limited as a job trigger, 200 with the destruction. |
| 7 — tier migration | **REPAIRED AND SHIPPED DISABLED.** Six defects, not two. Dry-run output below. First live pass left for the operator. |
| 8 — physical base backup | **DONE.** `pg_basebackup` weekly, `restore.sh --pit` performs PITR into a staged cluster. Window argued; **one decision open (D-1).** |
| 9 — mount propagation | **DONE.** fstype guard in six scripts, `rslave` on both binds, verified live after a postgres recreate. |
| 10 — restore rehearsal | **DONE.** Rehearsed, timed, torn down. Runbook written. |

---

## 2. TASK 1 — what a project actually is, measured

`PROJECT_CATEGORIES` (`ivgs-api/app/services/project_deletion.py`) is the map.
It is the source of **both** the dialog's category list and the destruction, so
the two cannot drift apart. The `cascade` column below is a transcription of
`pg_constraint.confdeltype` read off the running database, not a statement of
intent.

### 2.1 The map

| # | Category | Reached by | On delete |
|---|---|---|---|
| 1 | `storyboard_scenes` | `storyboard_scenes_project_id_fkey` | CASCADE |
| 2 | `transcripts` | `transcripts_project_id_fkey` | CASCADE |
| 3 | `prompts` | `prompts_project_id_fkey` | CASCADE |
| 4 | `prompt_tag_associations` | `prompt_tag_associations_prompt_id_fkey`, via `prompts` | CASCADE |
| 5 | `render_jobs` | `render_jobs_project_id_fkey` | CASCADE |
| 6 | `pipeline_checkpoints` | via `render_jobs` | CASCADE |
| 7 | `composition_manifests` | via `render_jobs` | CASCADE |
| 8 | `render_segments` | via `render_jobs` | CASCADE |
| 9 | `task_retries` | via `render_jobs` | CASCADE |
| 10 | `gpu_reservations` | via `render_jobs` | CASCADE |
| 11 | `language_variants` | `language_variants_project_id_fkey` | CASCADE |
| 12 | `project_model_selections` | `project_model_selections_project_id_fkey` | CASCADE |
| 13 | `assets` | `assets_project_id_fkey` | CASCADE |
| 14 | `asset_quality_scores` | via `assets` and via `render_jobs` | CASCADE |
| 15 | `dead_letter_messages` | **nothing** | **ORPHAN — explicit DELETE** |
| 16 | `storage_quotas` | **nothing** | **ORPHAN — explicit DELETE** |
| 17 | SeaweedFS objects | not a row | purge step, guarded |
| 18 | Redis scratch keys | not a row | purge step |

**Rows that are SET NULL rather than deleted, and are therefore left behind
deliberately:** `worker_heartbeats.current_job_id`, and
`projects.hero_image_asset_id` / `talking_head_asset_id` (which go with the
project row anyway). `library_assets`, `actors`, `presets`, `models` and
`prompt_tags` are **never touched** — they are shared vocabulary, not project
material.

### 2.2 The two that nothing reaches

`dead_letter_messages` **has no foreign key to anything at all** — it appears
nowhere in `pg_constraint` as a child. The job id lives inside `task_args` /
`task_kwargs` JSONB in three different shapes (WP-45 §4.2 measured all three),
so the only reliable predicate is a text search for the id. Without the
explicit DELETE those rows survive the project as unreplayable litter.

`storage_quotas.entity_id` is a bare UUID with no FK, because the table is
polymorphic over `entity_type` and a polymorphic column cannot carry one.

### 2.3 The one the map missed, and how it was caught

`test_wp59_deletion.py::TestCategoryMap::test_every_project_fk_table_is_in_the_map`
reads `pg_constraint` from the live test schema, walks the `ON DELETE CASCADE`
closure **outward** from `projects`, and fails by name on any table the map
does not cover. Its first run:

```
AssertionError: tables reachable by ON DELETE CASCADE from projects that no
deletion category names: ['prompt_tag_associations']. Each one is material a
deletion destroys without telling anybody.
```

That is category 4 above. It was written by hand into no list and would have
been destroyed silently. **This test is the thing that stops the map going
stale as the schema grows**, and it is worth more than the map itself.

### 2.4 A storage fact the map depends on: the filer namespace is EMPTY

Measured 2026-08-26:

```
GET http://192.168.1.90:8888/          -> {"Entries":null,"EmptyFolder":true}
GET http://192.168.1.90:8888/ivgs/     -> HTTP 404
GET .../ivgs/images/ /videos/ /audio/ /final/  -> HTTP 404, all four
master /vol/status  -> 7 volumes, 212 files at package start
```

Every asset is a **volume object addressed by fid**. `assets.seaweedfs_path` is
a label the uploader writes into the row; nothing writes to the filer at that
path. The purge therefore deletes by **fid**, and deletes the path too only so
the code stays correct if the filer is ever populated. This is also why
`orphan_cleanup`'s Type-1 scan (list filer directories) can never see anything,
and why `retention_migration`'s "move" (POST to a filer path) addressed nothing.

---

## 3. TASK 2 — the order, and the backstop that is not one

### 3.1 The order, and what each step buys

Three stores, no distributed transaction, so it cannot be atomic. What is
guaranteed is that every reachable intermediate state is honestly labelled.

| Step | What it does | What a crash here leaves |
|---|---|---|
| 1 | Refuse on non-terminal jobs; verify reservations against the scheduler registry | nothing changed |
| 2 | **Audit row written and COMMITTED**, with the per-category counts and the binary manifest | an audit row for a deletion that did not happen — visibly `purge_state: pending` |
| 3 | `state = DELETING`, COMMITTED | a project visibly mid-delete; terminal, no pipeline can start |
| 4 | (manifest already captured in step 2) | — |
| 5 | Rows, in ONE transaction | either all rows or none |
| 6 | Binaries, idempotent | orphaned objects — by construction, never a live row pointing at nothing |
| 7 | Redis scratch | inert leftover keys |

`audit_log` has **no foreign key to `projects`** (verified on the live schema),
so the audit row outlives the project by construction rather than by luck.

**Resumability is real, not asserted.** After step 5 the project row is gone, so
nothing in the database can say what objects it owned — except the audit row's
`binary_manifest`, written in step 2 for exactly this reason.
`resume_pending_deletions` re-reads it and finishes the purge.
`test_interrupted_purge_is_resumed_from_the_audit_row` simulates the crash by
writing the audit row and deleting the project rows, then calls delete and
asserts the stranded object is purged and `purge_state` reaches `complete`.

A second delete of a *finished* one converges on `ALREADY_DELETED` naming the
audit id — different from "no such project", because the system does in fact
remember destroying it. Observed live:

```
HTTP 404  ALREADY_DELETED - This project was already deleted (audit record
b2799e47-d64d-4915-ae11-44245d265145, completed 2026-08-26T02:00:51). Nothing
further to do.
```

### 3.2 An object the purge cannot confirm is NOT counted as deleted

`files_deleted` counts confirmed deletions only. An unconfirmed one goes into
`files_failed`, into the audit row, and onto the dialog's final panel, and
`purge_state` becomes `files_incomplete`. Reporting "3 files deleted" over three
objects still on disk is precisely the class of defect this package exists to
close, and it would have been trivially easy to write.

### 3.3 The orphan backstop — VERIFIED, and it would NOT have swept this shape

Task 2 requires this to be verified rather than assumed. It was, and the answer
is no, for **three independent reasons**, any one of which is sufficient.

**(a) The scheduled task is a stub.** Celery beat dispatches
`tasks.pipeline_orchestrator.run_orphan_cleanup`, which logs one line and
returns a fixed dict. Its own result payload, from the live result backend:

```
name    tasks.pipeline_orchestrator.run_orphan_cleanup
status  SUCCESS
2026-08-25 03:00:00   "Orphan cleanup — stub (Phase 8)"
2026-08-24 20:33:35   "Orphan cleanup — stub (Phase 8)"
```

The real task is `ivgs_workers.tasks.periodic_tasks.run_orphan_cleanup`, whose
schedule lives in `get_beat_schedule()` — which is not wired.
`ivgs-workers/tasks/__init__.py:25` says so in as many words: *"Dormant:
tasks.periodic_tasks (not wired; H.1 consolidation item)"*.

**(b) Every one of its three scans names a column that does not exist.**

```
SELECT id, storage_path FROM assets                        -> ERROR: column "storage_path" does not exist
SELECT id, storage_path FROM assets WHERE reference_count=0 -> ERROR: column "storage_path" does not exist
SELECT 1 FROM assets WHERE storage_path = '/x'             -> ERROR: column "storage_path" does not exist
SELECT status FROM assets                                  -> ERROR: column "status" does not exist
```

`assets` has `seaweedfs_path` and `seaweedfs_fid`, and no `status` column at
all — so `_mark_db_record_orphaned` and `_quarantine_asset`, which both write
`status`, would fail too. The failures are not per-scan: the `SELECT` in
`_scan_type2_db_without_seaweedfs` sits outside any local try, so the exception
aborts `run_cleanup` at scan 2 and scans 2, 3 and the quarantine expiry never
run.

**(c) Its Type-1 scan lists filer directories, and the filer namespace is
empty** — §2.4. It would find nothing to cross-reference even with the columns
fixed.

**It is left pointing at its stub, deliberately, and this is a decision for the
operator (D-2).** `OrphanCleanupService` QUARANTINES and then permanently
DELETES binaries and has **no shared-object guard**. Switching it on today
would let it delete a library asset's bytes out from under every project
referencing them — the exact thing Task 4 exists to prevent. Repairing it is a
package of its own, and it should inherit `binary_manifest`'s guard rather than
grow a second copy.

**What this means for WP-59's own guarantee:** the deletion does not rely on the
backstop. It captures the manifest before destroying the rows and reports any
object it could not confirm deleted. The backstop would have been belt to that
braces; it is currently neither.

---

## 4. TASK 3 — running work is cancelled for real

Acceptance: *attempt deletion of a project with a running job; observe refusal;
cancel via the GUI; observe the revoke reach the broker (the WP-45 assertion
standard); deletion then proceeds.* All four, live, on the deployed build.

### 4.1 The refusal

```
DELETE /projects/702b0dd6.../               (no confirm_name)   HTTP 422
  {"detail":[{"type":"missing","loc":["query","confirm_name"],"msg":"Field required"}]}

DELETE /projects/702b0dd6...?confirm_name=wrong                 HTTP 409
  CONFIRMATION_MISMATCH - The confirmation name does not match this project's name.

DELETE /projects/702b0dd6...?confirm_name=WP59-THROWAWAY-victim HTTP 409
  JOBS_NOT_TERMINAL - 1 job(s) are still pending or running. Cancel them before
                      deleting this project.
      f8e470bf-11eb-41df-878d-93194080aa10 image_generation running

project still intact: WP59-THROWAWAY-victim | DRAFT
```

### 4.2 The revoke, reaching the broker

The route is WP-45's `POST /jobs/{id}/cancel`, called by the dialog. It is not
reimplemented: a second revoke path would be a second thing that can be wrong
about whether the GPU stopped.

```
BEFORE  celery inspect revoked
  -> image-worker@node04:      - empty -
  -> celery-worker@node02:     - empty -
  -> cogvideox-worker@node03:  - empty -

POST /jobs/f8e470bf.../cancel        HTTP 200
  status: failed    error_message: Cancelled by user

AFTER   celery inspect revoked
  -> default-worker@node01:     * cebe542d-bd9d-4757-90b7-6bcd8a684083
  -> composition-worker@node01: * cebe542d-bd9d-4757-90b7-6bcd8a684083
  -> celery-worker@node02:      * cebe542d-bd9d-4757-90b7-6bcd8a684083
  -> image-worker@node04:       * cebe542d-bd9d-4757-90b7-6bcd8a684083
  -> cogvideox-worker@node03:   * cebe542d-bd9d-4757-90b7-6bcd8a684083
  5 nodes online.
```

**The revoke reached the broker and all five live workers hold it.** That is the
WP-45 standard — not the 200, the broadcast. The task dispatched for this was
`celery_app.debug_task` with a one-hour countdown, deliberately: it is the
workers' own no-op ping, so the revoke is real without sending GPU work to
nodes 02/03/04, and a countdown leaves it sitting in the broker, which is the
state a Cancel button is actually for.

`failed` is the terminal state a cancel produces — `job_status` is a four-value
enum with no `cancelled` member, and `JobService.cancel_job` writes `failed`
with `error_message = "Cancelled by user"`.

### 4.3 GPU reservations, read from the registry that holds them

The scheduler's reservation registry is in **Redis db 1**
(`ivgs-scheduler/main.py:110`, `docker-compose.node01.yml`), while the API is
bound to db 0 — so the API could not see it at all. `SCHEDULER_REDIS_URL` is
now passed to the API container and the deletion reads:

* `sched:job_reservation:{job_id}` — the job→reservation map, and
* `sched:reservations:index` — the durable id set, cleaned only lazily
  (`scheduler.py:522`), so a reservation hash that outlived its job map is
  visible only here.

Both, because either alone has a hole. Live during the acceptance run the
registry was reachable and empty (`gpu_reservations_held: []`,
`scheduler_registry_error: null`).

**A registry that cannot be READ also refuses.** "I could not check" and "I
checked and there is nothing" are different facts — the WP-45 dedup-probe
lesson. `test_unreadable_scheduler_registry_refuses` exercises the real code
path with no stub and asserts the project survives.

### 4.4 Deletion then proceeds

```
preview after the cancel:
  deletable      True
  blocking_jobs  []
  reservations   []
```

---

## 5. TASK 4 — shared bytes and the library are untouchable

### 5.1 The sharing mechanism, established by reading the code

**Content-hash dedup is PROJECT-SCOPED at both ends.** The worker probe passes
`project_id` at all four call sites (`stage3_images.py:493`,
`stage5_voiceover.py:449`, `video_generation_task.py:348`,
`animation_generation_task.py:507`), and the upload's dedup query is

```python
and_(or_(*dedup_conditions), Asset.project_id == project_id,
     Asset.storage_tier != "deleted")            # asset_service.py:298-303
```

So dedup **never** produces a row in another project. Within a project it
produces ONE row with `reference_count` incremented. Confirmed live:

| upload | result |
|---|---|
| `shared.png` → victim | new row `bdd4405a`, fid `3,d68e809d7a`, dedup **false**, refs 1 |
| `shared.png` → victim **again** | **same row** `bdd4405a`, same fid, dedup **true**, refs **2** |
| `shared.png` → **survivor** (identical bytes) | **new** row `3c6b62cc`, **new** fid `4,d7bf81f0f0`, dedup false, refs 1 |

**The cross-project sharing that does exist is AD-09.4.2 reference-don't-copy.**
`LibraryService.reference_into_project` (`library_service.py:370-371`) creates
an `assets` row carrying the library object's `seaweedfs_fid` and
`seaweedfs_path` **verbatim**. Two projects referencing one logo hold two rows
pointing at one object. Confirmed live: both referencing rows carry fid
`7,d5556ce175`.

### 5.2 The guard, and the proof it is selective

One rule, enforced per object rather than inferred, decided while the rows still
exist and carried into the purge unchanged: **purge an object only if no
surviving `assets` row and no `library_assets` row names its fid or its path.**

The acceptance scenario had four objects:

| fid | what it is | expected |
|---|---|---|
| `7,d5556ce175` | library asset, referenced into both projects | **preserved** |
| `3,d68e809d7a` | victim's object, also pointed at by a survivor row | **preserved** |
| `6,d81f800973` | victim's alone | **purged** |
| `4,d7bf81f0f0` | survivor's own | untouched |

Deleting the victim:

```
files_deleted    1
files_preserved  2
preserved_reasons:
  7,d5556ce175  /ivgs/library/logos/logo.png                  library_asset
  3,d68e809d7a  /ivgs/images/702b0dd6-.../shared.png          referenced_by_another_project
```

Bytes, fetched from the volume server afterwards:

```
7,d5556ce175  LIBRARY            HTTP 200  4096 bytes
3,d68e809d7a  CROSS-PROJECT      HTTP 200  8192 bytes
6,d81f800973  VICTIM-ONLY        HTTP 404  0
4,d7bf81f0f0  SURVIVOR-OWN       HTTP 200  8192 bytes
```

SeaweedFS's own accounting agrees: volume 6 `DeleteCount 1`,
`DeletedByteCount 6027`; every other volume 0.

The `library_assets` row is untouched (`superseded_by` still NULL), and the
surviving references still **resolve to bytes** through the API, not merely
exist as rows:

```
GET /assets/adecc9fb.../download  (library ref)     HTTP 200  4096
GET /assets/fcb6af3d.../download  (shared object)   HTTP 200  8192
GET /assets/3c6b62cc.../download  (own upload)      HTTP 200  8192
```

### 5.3 And the guard is DYNAMIC, not sticky

Deleting the *second* throwaway project afterwards:

```
files_deleted    2
files_preserved  1
  preserved 7,d5556ce175 -> library_asset

7,d5556ce175  LIBRARY            HTTP 200   <- still preserved: the library row holds it
3,d68e809d7a  WAS-CROSS-PROJECT  HTTP 404   <- now purged: nothing points at it any more
4,d7bf81f0f0  SURVIVOR-OWN       HTTP 404
```

The same object was preserved by one deletion and purged by the next, correctly
both times. A guard that had cached "this fid is shared" would have leaked it
forever.

---

## 6. TASK 5 — what deletion means for backups, stated honestly

**The dialog makes no backup promise, and that is deliberate.** Its final panel
says:

> This is permanent. It cannot be undone from this interface, and there is no
> "restore project" action anywhere in the application.

It does **not** say "it's in the backups", because on the day that sentence
matters it would be a promise nobody could keep.

### 6.1 Where a deleted project does still exist

| Artefact | Retention | Contains the deleted project? |
|---|---|---|
| Nightly `pg_dump` | 30 days (`BACKUP_RETENTION_DB_DAYS`) | Yes, if the dump predates the deletion |
| Weekly `pg_basebackup` (new, Task 8) | 35 days | Yes, same condition |
| WAL archive | 7 days | Yes — the rows exist at any instant before the delete |
| Nightly asset snapshot (SeaweedFS volumes) | per `BACKUP_RETENTION_ASSETS_DAYS` | Yes — the volume file, including the deleted object |
| **Indefinite monthly snapshots** (WP-58) | forever | Yes |

### 6.2 What recovering ONE project would actually involve

**It is not a supported operation and this package did not build one.** Stated
so the operator knows the shape of the ask before agreeing to it:

1. **Restore the whole database elsewhere.** `restore_rehearsal.sh` already does
   exactly this into a scratch cluster — about 1.5 seconds today.
2. **Extract that project's rows in dependency order** across the 16 database
   categories in §2.1, rewriting nothing: the ids are UUIDs, so they can be
   re-inserted as they were, provided the target rows do not already exist.
   `users`, `models`, `presets` and `library_assets` must be present first, and
   `projects.created_by` is `NOT NULL`.
3. **Recover the binaries.** This is the hard part. The asset backup snapshots
   whole SeaweedFS **volumes**; there is no per-object extraction. You would
   restore the volume files into a scratch SeaweedFS cluster, fetch each fid
   from the manifest in the deletion's audit row, and re-upload them — which
   assigns **new fids**, so every restored `assets` row needs its
   `seaweedfs_fid` rewritten.
4. **Reconcile.** `reference_count`, `library_asset_id` and any object that was
   *preserved* (and so is still live) must not be duplicated.

The audit row is what makes step 3 possible at all: it carries the full
`(fid, path, size, asset_types)` manifest, written before destruction.

**Estimate: a day of careful work by someone who has done a restore before, and
it has never been done.** Which is the honest reason the GUI does not offer it.

---

## 7. TASK 7 — tier migration: six defects, and a stub in front of them

### 7.1 The scheduled task was never the real one

WP-57 §3.1 concluded the real service ran nightly and swallowed
`UndefinedColumn` per tier. **It has never executed once.** Beat dispatches the
Phase-5 stub in `pipeline_orchestrator.py:680`:

```
name    tasks.pipeline_orchestrator.run_retention_migration
status  SUCCESS
2026-08-25 04:00:00.063   "Retention migration — stub (Phase 8)"
2026-08-24 20:33:35.711   "Retention migration — stub (Phase 8)"
```

WP-57's column finding is correct and is fixed; its attribution is corrected
here. **Both halves had to be repaired for either to matter** — fixing the
column alone would have left the stub on the schedule, and pointing the schedule
at the real task alone would have started raising `UndefinedColumn` nightly.

### 7.2 Six defects, all verified against the live schema

| # | Defect | Consequence |
|---|---|---|
| 1 | scan selects `storage_path` | `assets` has `seaweedfs_path`; every scan raises (WP-57 D-1) |
| 2 | `StorageTier.ARCHIVE = "archive"` | enum label is `archived` (WP-57 D-1) |
| 3 | `StorageTier.DELETE = "delete"` | enum label is `deleted` — **same defect, one hop down, not named by WP-57** |
| 4 | `_transition_tier` writes `updated_at` | `assets` has no such column |
| 5 | `_delete_asset` writes `status = 'deleted'` | `assets` has no such column |
| 6 | `RetentionPolicy` requires `archive_days` / `delete_after_days` | **all three live policy rows have NULL in both**, so the load raises into a bare `except` and the hardcoded defaults are used instead |

**Defect 6 is the one to read twice.** The operator's configured retention
policy has governed nothing since the table was seeded on 2026-05-23:

```
 name       | hot | warm | cold | archive_days | delete_after_days | applies_to | default
 standard   |  30 |   90 |  365 |        NULL  |             NULL  | all        | t
 long-term  |  90 |  180 |  730 |        NULL  |             NULL  | all        | f
 compliance | 365 |  730 | 3650 |        NULL  |             NULL  | all        | f
```

Third instance of this shape in three packages — WP-58's four
`BACKUP_RETENTION_*`, WP-57's three `RATE_LIMIT_*`, and now this. A setting that
looks live and is decorative, invisible until someone tries to change a value.

**NULL now means "do not progress past this tier", and the old code read it as
ZERO.** `get_tier_duration_days` used `mapping.get(tier, 0)`, and `0` satisfies
`time_in_tier >= duration` for every asset that has ever existed. An
unconfigured `delete_after_days` would have **deleted the entire fleet** on the
first run that reached it. Pinned in
`test_null_terminal_days_load_and_do_not_progress`.

### 7.3 And the physical move was never a move

`_transition_tier` POSTed to a filer path with `X-Seaweedfs-Collection` headers.
That addressed nothing (§2.4 — the filer namespace is empty), and SeaweedFS
assigns a volume's collection at `/dir/assign` time; there is no filer header
that relocates an existing object between collections. Genuinely moving bytes
means re-uploading them into a volume of the target collection and rewriting the
fid — a real feature, not something to smuggle in under a header.

**The tier column now moves and the placement is recorded as
`physical_move=not_performed`.** A tier saying `cold` over bytes still on the
hot volume is a smaller lie than a log line claiming the bytes moved, and it is
the one the operator can see.

`_delete_asset` tombstones with `storage_tier = 'deleted'` — which the rest of
the system already reads as "not a live asset" (`find_by_hash` and the upload
dedup both exclude it) — and does **not** remove bytes, because byte removal
needs Task 4's shared-object guard, which this service does not have.

### 7.4 The swallow

The per-tier `except` is kept — one bad tier should not strand the other three,
which is genuine value — but the report now carries `status`, the task **raises**
on it, and Celery records FAILURE. It used to append to `report.errors`, which
nothing read, and return `{'status': 'ok'}`.

### 7.5 Dry run — live, on the deployed worker, writing nothing

```
===== WP-59 Task 7 dry run, 2026-08-26, ivgs-workers:v5.18.0-delete =====
  dry_run                True
  status                 ok
  policy_source          database          <- was hardcoded_defaults, silently
  policy_load_error      None
  assets_scanned         161
  transitions_performed  44
  assets_deleted         0
  capped                 False
  policy_gaps            {}
  would_move             {'hot->warm': {'assets': 44, 'bytes': 187295751}}
  errors                 []
  duration_seconds       0.038
```

**44 assets, 187,295,751 bytes (178 MB), hot → warm. Nothing archived, nothing
deleted** — `standard` sets `archive_days` NULL, so `cold` is terminal under the
configured policy, and `delete` is unreachable from it. `policy_gaps` is empty
only because no asset has reached `cold` yet; the cold→archived hop scans zero
rows.

Verified afterwards, nothing was written:

```
 storage_tier | count | min(tier_transition_at)
 hot          |   161 | (null)
```

And `retention-migration` is **absent from the deployed beat schedule**:

```
  backup-verification      tasks.pipeline_orchestrator.run_backup_verification
  dlq-processor            tasks.pipeline_orchestrator.process_dead_letter_queue
  gpu-fleet-metrics        tasks.pipeline_orchestrator.collect_gpu_fleet_metrics
  heartbeat-supervision    tasks.pipeline_orchestrator.supervise_worker_heartbeats
  media-join-watchdog      tasks.pipeline_orchestrator_v2.media_join_watchdog
  model-availability-poll  ivgs_workers.tasks.periodic_tasks.poll_model_node_availability
  orphan-cleanup           tasks.pipeline_orchestrator.run_orphan_cleanup
```

### 7.6 OPERATOR BLOCK — tier migration, first live pass

**Run the three steps in order and read the output of each before the next.**
Nothing here is automatic; step 3 is a separate, deliberate edit.

```bash
# ── node-01 ────────────────────────────────────────────────────────────────
# STEP 1 — DRY RUN. Writes nothing. Confirm the numbers match the report.
cd /opt/ivgs
docker exec ivgs-celery-default python - <<'PY' 2>&1 | sed -n '/=====/,$p'
import asyncio
from services.retention_migration import RetentionService
from shared.database import async_session_factory
svc = RetentionService(db_session_factory=async_session_factory, dry_run=True)
loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
r = loop.run_until_complete(svc.run_migration()); loop.run_until_complete(svc.close())
d = r.model_dump(mode="json")
print("===== dry run =====")
for k in ("dry_run","status","policy_source","policy_load_error","assets_scanned",
          "transitions_performed","assets_deleted","capped","policy_gaps",
          "would_move","errors"):
    print(f"  {k:22} {d[k]}")
PY
```

```bash
# ── node-01 ────────────────────────────────────────────────────────────────
# STEP 2 — CAPPED LIVE PASS. Moves AT MOST 5 assets, hot -> warm only.
# Nothing is archived or deleted: the configured policy sets archive_days NULL.
# NO BYTES MOVE - only the tier column and tier_transition_at. See report S7.3.
cd /opt/ivgs
echo "--- before ---"
docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
  "SELECT storage_tier, count(*) FROM assets GROUP BY 1 ORDER BY 1;"

docker exec ivgs-celery-default python - <<'PY' 2>&1 | sed -n '/=====/,$p'
import asyncio
from services.retention_migration import RetentionService
from shared.database import async_session_factory
svc = RetentionService(db_session_factory=async_session_factory,
                       dry_run=False, max_transitions=5)
loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
r = loop.run_until_complete(svc.run_migration()); loop.run_until_complete(svc.close())
d = r.model_dump(mode="json")
print("===== capped live pass =====")
for k in ("dry_run","status","policy_source","assets_scanned",
          "transitions_performed","assets_deleted","capped","errors"):
    print(f"  {k:22} {d[k]}")
PY

echo "--- after: expect 5 rows moved to warm, tier_transition_at stamped ---"
docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
  "SELECT storage_tier, count(*), max(tier_transition_at) FROM assets GROUP BY 1 ORDER BY 1;"
echo "--- the 5 moved rows are still downloadable (the bytes did not move) ---"
docker exec ivgs-postgres psql -U ivgs -d ivgs -Atc \
  "SELECT seaweedfs_fid FROM assets WHERE storage_tier='warm' LIMIT 5;" \
  | while read f; do printf '  %-16s HTTP %s\n' "$f" \
      "$(curl -s -o /dev/null -w '%{http_code}' http://192.168.1.90:8080/$f)"; done
```

```bash
# ── node-01 ────────────────────────────────────────────────────────────────
# STEP 3 — ENABLE THE SCHEDULE. Only after steps 1 and 2 both behaved.
# Uncommenting this gives a nightly DRY RUN, not a nightly migration: the task
# defaults to dry_run. Turning that off is a separate edit, on purpose.
cd /opt/ivgs
sed -i 's|^    # "retention-migration": {|    "retention-migration": {|; \
        s|^    #     "task": "ivgs_workers.tasks.periodic_tasks.run_retention_migration",|        "task": "ivgs_workers.tasks.periodic_tasks.run_retention_migration",|; \
        s|^    #     "schedule": crontab(hour=4, minute=0),|        "schedule": crontab(hour=4, minute=0),|; \
        s|^    #     "options": {"queue": "default", "priority": 2},|        "options": {"queue": "default", "priority": 2},|; \
        s|^    # },|    },|' ivgs-workers/celery_app.py
git diff --stat ivgs-workers/celery_app.py
echo "REBUILD AND REDEPLOY the workers image before this takes effect."
```

---

## 8. TASK 8 — point-in-time recovery exists now

### 8.1 What was missing, and what was added

The WAL archive was live, current and faithfully pruned, and **could not be
replayed** because there was no physical base to replay it onto. Not a
configuration gap: WAL records physical block changes keyed to LSNs in one data
directory, and `pg_dump` builds a new cluster with an unrelated timeline.

`scripts/basebackup.sh` — weekly `pg_basebackup --format=tar --gzip
--checkpoint=fast --wal-method=none` to `/mnt/backup/ivgs/basebackup/`, through
the same pattern as the other three backup jobs: the script owns its
`backup_records` row, failure raises `BackupTaskError`, and it pushes the same
`ivgs_backup_last_*` gauges the alert family reads. New `backup_type` enum value
`physical_base_backup` (migration 0033).

**`--wal-method=none` deliberately.** Bundling WAL would double the storage of
every segment and invite a restore that replays only the bundled WAL and stops
— a restore to the base's own instant, not a point-in-time recovery.

### 8.2 Preconditions, verified live

```
wal_level                 replica         (sufficient for physical base + PITR)
max_wal_senders           10
role ivgs                 rolreplication=t, rolsuper=t
pg_basebackup in worker   17.10 (client) against 17.2 (server)
WAL archive               208 segments, 04..D3, NO GAPS
NAS                       20 T, 59 G used (1%)
```

### 8.3 Dry run, and the guard refusal

```
$ docker exec ivgs-backup-worker /scripts/basebackup.sh --dry-run
dry_run=true
would_write_to=/mnt/backup/ivgs/basebackup/2026-08-26
cluster_size_mb=146
start_lsn=1/D27E6F38
record_write=skipped

$ sudo ls /mnt/backup/ivgs/ | grep -c basebackup
0                      <- a dry run writes NOTHING, not even the directory

$ docker exec -e BACKUP_BASEBACKUP_NAS_DIR=/tmp/notnas/basebackup \
      ivgs-backup-worker /scripts/basebackup.sh --dry-run ; echo $?
NFS GUARD: physical base backup directory does not exist: /tmp/notnas
NFS GUARD: refusing to create it. ...
basebackup: Base backup destination parent is not an NFS mount: /tmp/notnas
6
```

**No base backup has been taken.** The first run is the operator's — §8.6.

### 8.4 `restore.sh --pit` performs PITR, and refuses clearly when it cannot

Four preconditions, each named separately, because "PITR failed" is not a useful
sentence at 3 a.m. All four exercised against a temporary tree (nothing under
`/mnt/backup` was written):

```
(1) no base backup directory
    Point-in-time recovery is NOT POSSIBLE: no base backup directory.
      Looked in: /nonexistent/basebackup
      Take one with: scripts/basebackup.sh  (dry run first: --dry-run)
      Until a base exists, the honest recovery promise is checkpoint-only.

(2) no base at or before the target
    Point-in-time recovery is NOT POSSIBLE: no base backup was taken at or
      before 2026-08-15-01:00. Recovery replays WAL FORWARD from a base.
      Bases present: 2026-08-20

(3) WAL archive not on the NAS
    Point-in-time recovery is NOT POSSIBLE: the WAL archive at ... is not on
      the NAS. Replaying from a shadowed local directory would replay a
      partial history and stop early without an error (WP-57 D-3).

(4) a gap in the segment run  [one segment removed from a copy of the real names]
    Point-in-time recovery is NOT SAFE: the WAL archive has gaps.
      00000001000000010000009F -> 0000000100000001000000A1
      Replay would stop at the first gap and report success at an earlier
      instant than requested. Refusing.

SUCCESS PATH (dry run, real 207-name archive, base dated before target)
    [INFO] Base backup selected
    [INFO] WAL archive verified          (segments 207, gaps 0)
    [DRY RUN] Would stage a recovery cluster ... and replay 207 segments
    pitr_wal_segments=207
```

Precondition 4 is the one that matters most: replay stops at a gap and reports
**success** at an earlier instant than requested. That is worse than a failure.

**It stages a separate cluster and never touches the live one.** It unpacks the
base into a staging directory, writes `recovery.signal` and the recovery GUCs
into `postgresql.auto.conf` (PG12+; the old code wrote a `recovery.conf`, which
17.2 ignores — a second reason the old instructions could not have worked), and
prints the commands to bring it up on port 5433 with
`recovery_target_action = 'pause'` so the operator can look before promoting.

### 8.5 The window — argued, and the promise stated

| Setting | Value |
|---|---|
| Base cadence | weekly, Sunday 01:00 UTC |
| Base retention | 35 days |
| **WAL retention** | **7 days** |
| Logical dump retention | 30 days |

**The PITR window is SEVEN days, not thirty-five.** WAL retention is the binding
constraint and must be read that way. With a weekly base and 7-day WAL, at the
worst point in the cycle — just before a new base — the newest base is 7 days
old and the archive reaches back exactly 7 days. **They just meet, with no
margin.** One missed base opens a hole immediately: the newest base becomes 14
days old while the WAL still reaches back 7, and days 8–14 become unrecoverable
*even though a base and an archive both exist*. `BaseBackupStale` at 8 days is
the tripwire on exactly that.

**Recommendation (D-1): raise `BACKUP_RETENTION_WAL_DAYS` from 7 to 10.** Three
days of slack over the weekly cadence. Cost: the archive holds 208 segments at
16 MB — about 3.3 GB for 7 days — on a NAS 1% full of 20 T. Not changed here,
because retention is a policy number and the remit was to argue it.

Base retention is 35 deliberately: a base older than the WAL window cannot serve
PITR, but it is still a complete physical copy restorable *to its own instant* —
a coarse recovery of last resort if the archive itself is damaged.

### 8.6 Alerting

`BackupStale` (26 h) now **excludes** `physical_base_backup`; a new
`BaseBackupStale` fires at 8 days. A 26-hour threshold on a weekly job pages six
days out of seven, which is the same as no alert. `promtool check rules` on the
live config: **SUCCESS, 15 rules** (was 14).

Worth stating why this alert matters most: if the base backup silently stops,
**nothing breaks and nothing looks wrong** — the archive keeps filling, the
nightly dump keeps succeeding, every dashboard stays green — and the ability to
recover to an instant is lost invisibly, discovered during an incident. That is
the 75-day-gap shape.

### 8.7 OPERATOR BLOCK — first physical base backup

```bash
# ── node-01 ────────────────────────────────────────────────────────────────
# STEP 1 — dry run. Writes nothing; names any precondition that fails.
docker exec ivgs-backup-worker /scripts/basebackup.sh --dry-run ; echo "exit=$?"

# STEP 2 — take the first base. ~146 MB of cluster, gzip-compressed to the NAS.
# It reads the whole data directory, so run it when the node is quiet.
docker exec ivgs-backup-worker /scripts/basebackup.sh ; echo "exit=$?"

# STEP 3 — verify the artefact, the row, and the metric.
sudo ls -la /mnt/backup/ivgs/basebackup/*/
docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
  "SELECT backup_type, status, size_bytes, backup_path, started_at, completed_at
   FROM backup_records WHERE backup_type='physical_base_backup'
   ORDER BY started_at DESC LIMIT 3;"
curl -s http://192.168.1.90:9091/metrics | grep physical_base_backup

# STEP 4 — rehearse the PITR path against it. DRY RUN: writes nothing, and the
# live database is never addressed.
sudo /opt/ivgs/scripts/restore.sh 2026-08-23 \
     --pit "$(date -u -d '5 minutes ago' +%Y-%m-%d-%H:%M)" --dry-run
```

---

## 9. TASK 9 — mount propagation, and the fstype pre-flight

### 9.1 Why the path check could not have caught it

`backup.sh` gated the NAS on `[ ! -d "${BACKUP_NAS_DIR}" ]`. **A shadowed local
directory IS a directory.** That check produced exit 6 for the database only
because the shadowed local tree happened not to contain `db/`. It DID contain
`assets/` — which is how 45 GB of July asset snapshots accumulated on the root
volume for months while the surface reported the asset backup working. The loud
failure was luck; the silent one was the design.

### 9.2 The guard

`scripts/lib/nfs_guard.sh` asserts `stat -f` reports `nfs`/`nfs4`, resolved by
the kernel at call time so a mountpoint that exists but is not mounted cannot
fool it. It names the fstype and the `/proc/mounts` entry it resolved to, writes
only to **stderr** (three callers parse their own stdout for `KEY=VALUE` lines),
and **refuses to create a missing directory**.

Sourced by **six** scripts, not the two that were caught: `backup.sh`,
`asset_backup.sh`, `config_backup.sh`, `wal_archive.sh`, `basebackup.sh` and
`restore.sh`.

Gated both ways — a guard that refused everything would be trivially "safe" and
would stop every backup on the node:

```
/mnt/backup/ivgs/db   -> PASS (nfs)
/var/log/ivgs         -> REFUSED, fstype ext2/ext3, mount /dev/mapper/... / ext4
/mnt/backup/ivgs/nope -> REFUSED, does not exist, and NOT created
```

**Order matters in `wal_archive.sh`:** the guard runs **before** `mkdir -p`,
because `mkdir -p` under an absent mount is what *built* the shadowed tree.
Refusing returns non-zero to `archive_command`, so PostgreSQL keeps the segment
in `pg_wal` and retries — the WAL is held on the primary, not lost, and `pg_wal`
growing is visible pressure rather than a silent split archive. The retention
prune is guarded too.

### 9.3 Propagation — the durable half

Both binds were docker's default `rprivate`, so each container captured whatever
inode was at its path **at start time**. That is precisely why a routine
`docker compose up -d` fixed nothing in WP-57 §6.1 and `--force-recreate` was
needed. Now:

```
/mnt/backup            (backup-worker)  ->  propagation: rslave
/mnt/backup/ivgs/wal   (postgres)       ->  propagation: rslave
```

`rslave` rather than `rshared`: the host is the authority (its mounts are
already `shared`, verified with `findmnt`), and these containers have no
business propagating mounts back out. One-way is the smaller privilege.

### 9.4 Verified live, after recreating postgres

```
/ivgs-backup-worker: /mnt/backup      propagation=rslave
/ivgs-postgres:      /mnt/wal-archive propagation=rslave
docker exec ivgs-backup-worker stat -f -c %T /mnt/backup/ivgs   -> nfs
docker exec ivgs-postgres     stat -f -c %T /mnt/wal-archive    -> nfs

SELECT pg_switch_wal();  -> 1/D30000B8
last_archived_wal 0000000100000001000000D3   at 2026-08-26 01:54:32
NAS: 208 segments, 04..D3, gaps: none
find /mnt/backup -xdev -mindepth 1 -maxdepth 3  ->  /mnt/backup/ivgs   (nothing else)
```

**The forced segment switch archived through the guarded script to the NAS.** The
guard does not break live archiving, and the local shadow tree is empty.

**Neither half alone is enough.** Propagation only helps a mount that arrives
later; the in-process guard is what makes the write itself impossible on the
wrong filesystem. Both, because either alone leaves a hole.

---

## 10. TASK 10 — the restore, rehearsed

### 10.1 The isolation mechanism, stated explicitly

**Not discipline — a separate PostgreSQL cluster.** A throwaway `postgres:17.2`
container with its own `PGDATA` on its own temporary directory, its own
postmaster, **no published port** so nothing outside the docker host can address
it, and `--memory=512m --memory-swap=512m` (node-01 is a 16 GB VM its Proxmox
host has OOM-killed before). The only thing the script does to the live cluster
is four `SELECT count(*)`. No code path in it can write to the live database.

### 10.2 Why that isolation is load-bearing, not belt-and-braces

`backup.sh` runs `pg_dump --clean --if-exists --create`. Line 22 of the
plaintext of **every dump this system has ever taken**:

```sql
DROP DATABASE IF EXISTS ivgs;
CREATE DATABASE ivgs WITH TEMPLATE = template0 ...
\connect ivgs
```

**Feeding that file to `psql` destroys the live database regardless of what `-d`
names on the command line** — the `\connect` overrides it. A rehearsal that
restored "into a new database" on the live cluster, as the task's example
phrasing suggests, would have been the single most destructive thing in this
package.

So the script does three things: runs in a different cluster; **filters**
everything up to and including `\connect` out of the dump; and **gates the
filter** — greps the filtered file for `DROP DATABASE`, `CREATE DATABASE` and
`\connect` and exits 5 if any survived. A comment claiming the filter works
would not be evidence. Afterwards it asserts `current_database()`.

### 10.3 The rehearsal

```
01:42:52  IVGS restore rehearsal — scratch cluster only, live database untouched.
01:42:52  Rehearsing dump: /mnt/backup/ivgs/db/2026-08-23/ivgs_backup.sql.gz.gpg
01:42:52  Decrypted in 0.095s — 5765913 bytes of SQL.
01:42:52  Filter verified: no DROP/CREATE DATABASE and no \connect remain.
01:42:52  Scratch cluster ready in 1.133s.
01:42:52  Restore completed in 0.222s.
01:42:52  Confirmed: objects are in ivgs_restore_rehearsal, in the scratch cluster.

table                        restored         live      delta
------------------------ ------------ ------------ ----------
projects                           15           17         +2
storyboard_scenes                  32           58        +26
assets                             45          160       +115
render_jobs                        17           40        +23

01:42:53  Timings:  decrypt 0.095s | cluster start 1.133s | restore 0.222s
01:42:53  Total recovery time for the data phase: 1.450s
01:42:53  Tearing down the scratch cluster.
```

Every delta is **positive** — live growth since the dump — and none negative,
which would mean the restore produced rows live does not have.

**The dump rehearsed is 2026-08-23, not the previous night's**, because the
nightly failed on the 24th and 25th (WP-57 §6.1, fixed 2026-08-26). The freshest
restorable point was three days older than anyone would have assumed. That is
itself the reason to rehearse.

**These timings are not an RTO.** The database is small — 5.8 MB of SQL, 160
asset rows — and `psql` genuinely takes a fifth of a second. `docs/deployment/runbook.md`'s
4-hour RTO is dominated by decision-making, stopping the fleet and verification.
Timings are recorded in milliseconds because `date +%s` would have logged the
whole rehearsal as "0s", a number that proves nothing and ages badly.

Afterwards: live `projects` = 17, `pg_database` lists only `ivgs`,
`ivgs_reconciliation_test`, `postgres`, `template0`, `template1` — the scratch
database and its container are gone.

`docs/runbooks/restore-rehearsal.md` carries the procedure, how to read a delta,
and a results table to append to, so the trend is visible.

**PITR rehearsal is the operator's step 4 in §8.7** — it needs a base backup to
exist, and none has been taken.

---

## 11. Package acceptance — the live, watched deletion

Two throwaway projects created for the purpose. **No existing project was
touched.**

| Criterion | Result |
|---|---|
| every mapped row gone | ✅ all 9 checked tables 0; no orphaned quality scores |
| binaries gone | ✅ `6,d81f800973` HTTP 404; SeaweedFS `DeleteCount 1`, 6027 bytes |
| Redis clean | ✅ 5 keys before, 0 after |
| audit row present | ✅ `b2799e47`, `PROJECT_DELETE_COMPLETED`, counts + who + when |
| library asset survives | ✅ row intact, object HTTP 200, reference resolves |
| deduped/shared bytes survive | ✅ §5.2, and the guard shown dynamic in §5.3 |
| orphan sweep finds nothing | ✅ 164 live asset rows checked, **0** whose object is missing. **The shipped orphan sweep could not have run — §3.3.** |
| existing projects untouched | ✅ 17 before, 17 after, excluding throwaways |
| tier-migration dry run in the report | ✅ §7.5 |
| first live tier pass left to the operator | ✅ §7.6 |
| restore rehearsal timings | ✅ §10.3 |
| screenshots of each dialog state | ⚠️ **see §12** |

Final state vs before:

| table | before | after |
|---|---|---|
| projects | 17 | 17 |
| assets | 160 | **161** |
| storyboard_scenes | 58 | 58 |
| render_jobs | 40 | 40 |
| library_assets | 0 | 0 |
| asset_quality_scores | 21 | 21 |
| pipeline_checkpoints | 40 | 40 |

**The +1 asset is not this package's.** It is a `talking_head` row on project
`52d52867` created at 01:59:03, one of five appearing on that project during the
session at 23:26, 23:41, 00:00, 01:12 and 01:59 — matching five
`assemble_prototype_draft` runs. Something is re-dispatching a talking-head
render on that project on a loop. Recorded as an observation (D-3), not touched.

The two `PROJECT_DELETE_COMPLETED` audit rows are the only intended residue.
The throwaway library asset created as a test fixture was removed by hand
afterwards (this package's deletion service never writes to `library_assets`),
returning the library to its 0 rows.

---

## 12. Screenshots — what could not be produced, and what is here instead

**node-01 has no browser and no browser-automation library.** Verified:
`playwright`, `selenium` and `pyppeteer` are not installed in `.venv`; no
`chromium`, `chromium-browser`, `google-chrome`, `firefox`, `wkhtmltoimage` or
`cutycapt` on `PATH` or in `/usr/bin`; no snaps. Installing a headless browser
and its ~150 MB of runtime onto a 16 GB node was outside this package's scope
and not authorised, so **no screenshots were taken and none are presented as
such.**

What is below is a faithful text rendering of each dialog state, generated
programmatically from **the real API payloads captured during the acceptance
run** (`preview_blocked.json`, `preview_ready.json`, `delete.json`) laid out
against `DeleteProjectDialog.tsx`. Every count, label, detail sentence, job id
and preserved-object reason is the live value, not a mock-up.

**To take the screenshots yourself:** log into the GUI as an admin, open any
project, press **Delete project**. Stage 1 is immediate; tick every category for
stage 1's enabled state; press Continue for stage 2; type the name for the
enabled Delete button. (Do this against a throwaway project — the flow is real.)

==============================================================================
STAGE 1 — categories, nothing pre-selected, Continue disabled
==============================================================================
  Delete “WP59-THROWAWAY-victim” — what this will destroy

  +----------------------------------------------------------------------+
  | Below is everything this project holds. Read each line and tick
  | it to confirm you are willing to lose it. IF YOU SEE SOMETHING
  | HERE YOU WANT TO KEEP, STOP. Close this dialog, go and save that
  | material somewhere outside this project, and come back
  | afterwards. That is what this list is for — there is no way to
  | get any of it back once the deletion runs.
  +----------------------------------------------------------------------+

  !! This project cannot be deleted while work is still running.
     1 job is still pending or running. Cancelling stops the work on the
     GPU and releases its reservation; deletion becomes available once
     every job has finished or been cancelled.
       [ image_generation  running ]                      ( Cancel job )
         f8e470bf-11eb-41df-878d-93194080aa10

  [ ] Storyboard scenes                              3
      Scene text, visual descriptions, timing and camera direction.
  [ ] Transcripts                                    1
      Uploaded source transcripts and their refined text.
  [ ] Prompts                                        1
      Every prompt version written for this project, active or supersede
  [ ] Prompt tag links                               0
      Which retrieval tags each of this project's prompts carries.
  [ ] Job history                                    1
      Every pipeline run this project has ever had, and why each one end
      image_generation: 1
  [ ] Checkpoints                                    1
      Stage checkpoints. Losing these makes an interrupted run unresumab
  [ ] Composition manifests                          0
      The rendered timeline: what went where, at what offset, at what re
  [ ] Render segments                                0
      Per-segment render records and their output references.
  [ ] Retry records                                  0
      Every retry attempt and the failure that caused it.
  [ ] GPU reservation records                        0
      Database records of GPU reservations taken for this project's jobs
  [ ] Language variants                              1
      Each localised version of this course and its render references.
  [ ] Model selections                               0
      Which AD-01 certified model was chosen for each stage and scene.
  [ ] Media assets (database records)                3
      Every asset row: images, video, audio, talking-head clips, drafts 
      image: 3
  [ ] Quality scores                                 1
      Automated quality and safety verdicts, and any human review notes.
  [ ] Dead-letter messages                           0
      Failed task messages retained for replay that name this project's 
  [ ] Storage quota records                          0
      This project's storage accounting row.
  [ ] Stored files (SeaweedFS)                       1
      The actual bytes: rendered images, video, audio and finished cours
      shared_files_preserved: 2
  [ ] Pipeline scratch state (Redis)                 5
      Media-join counters, job context and failure lists held for this p

  18 categories left to confirm.        ( Keep this project )  ( Continue )
                                                                    ^ DISABLED

==============================================================================
STAGE 1 — after the Cancel, all categories ticked, Continue enabled
==============================================================================
  deletable: True   blocking_jobs: []   reservations: []
  [x] Storyboard scenes                              3
  [x] Transcripts                                    1
  [x] Prompts                                        1
  [x] Prompt tag links                               0
  [x] Job history                                    1
  [x] Checkpoints                                    1
  [x] Composition manifests                          0
  [x] Render segments                                0
  [x] Retry records                                  0
  [x] GPU reservation records                        0
  [x] Language variants                              1
  [x] Model selections                               0
  [x] Media assets (database records)                3
  [x] Quality scores                                 1
  [x] Dead-letter messages                           0
  [x] Storage quota records                          0
  [x] Stored files (SeaweedFS)                       1
  [x] Pipeline scratch state (Redis)                 5

  All categories confirmed.            ( Keep this project )  ( Continue )
                                                                 ^ ENABLED

==============================================================================
STAGE 2 — the final confirmation
==============================================================================
  Permanently delete “WP59-THROWAWAY-victim”?

  +----------------------------------------------------------------------+
  | THIS IS PERMANENT. It cannot be undone from this interface, and there |
  | is no “restore project” action anywhere in the application.            |
  |                                                                      |
  | Once you press Delete, the material listed below is destroyed:       |
  | 12 database records and 5.9 KB of stored files.                    |
  +----------------------------------------------------------------------+

    Storyboard scenes                               3
    Transcripts                                     1
    Prompts                                         1
    Job history                                     1
    Checkpoints                                     1
    Language variants                               1
    Media assets (database records)                 3
    Quality scores                                  1
    Stored files (SeaweedFS)                        1
    Pipeline scratch state (Redis)                  5

  Type the project name exactly to enable deletion:  WP59-THROWAWAY-victim
  [                                                    ]

                        ( Back )  ( Keep this project )  ( Delete permanently )
                                                            ^ DISABLED until exact match

==============================================================================
STAGE 3 — what was actually destroyed (the real response)
==============================================================================
  “WP59-THROWAWAY-victim” has been deleted

    Database records removed                           13
    Stored files deleted                                1
    Stored files preserved (shared or in the library)    2
    Pipeline scratch keys cleared                        5

    An audit record of this deletion — who, when, and the count of every
    category — was written before the deletion began and survives it:
    b2799e47-d64d-4915-ae11-44245d265145

    Files shared with the asset library, or with a project that still
    exists, were deliberately left in place.
      7,d5556ce175     library_asset
      3,d68e809d7a     referenced_by_another_project

                                                    ( Back to projects )
---

## 13. Deployment — node-01 only, WP-34 binding rules

`v5.18.0-delete`, one coherent set across the four images this package touched.
GHCR is off the deploy path; artifacts under the standard name, the save pipe
run as two users.

| Image | Artifact |
|---|---|
| `ivgs-api:v5.18.0-delete` | `brucecostello2_ivgs-api_v5.18.0-delete.tar.zst` |
| `ivgs-frontend:v5.18.0-delete` | `brucecostello2_ivgs-frontend_v5.18.0-delete.tar.zst` |
| `ivgs-workers:v5.18.0-delete` | `brucecostello2_ivgs-workers_v5.18.0-delete.tar.zst` |
| `ivgs-backup-worker:v5.18.0-delete` | `brucecostello2_ivgs-backup-worker_v5.18.0-delete.tar.zst` |

All four registered in `/mnt/ivgs-shared/image-artifacts/MANIFEST.txt` with
sha256. `ivgs-scheduler` is unchanged and stays at `v5.0.0-20260522`.

Running on node-01, verified with `docker ps` (never from a container env var):

```
ivgs-fastapi              ghcr.io/brucecostello2/ivgs-api:v5.18.0-delete            healthy
ivgs-nextjs               ghcr.io/brucecostello2/ivgs-frontend:v5.18.0-delete       healthy
ivgs-celery-default       ghcr.io/brucecostello2/ivgs-workers:v5.18.0-delete        healthy
ivgs-celery-composition   ghcr.io/brucecostello2/ivgs-workers:v5.18.0-delete        healthy
ivgs-celery-beat          ghcr.io/brucecostello2/ivgs-workers:v5.18.0-delete        healthy
ivgs-backup-worker        ghcr.io/brucecostello2/ivgs-backup-worker:v5.18.0-delete  healthy
```

**`ivgs-postgres` was also recreated**, which is a live database restart and is
called out rather than buried: the `/mnt/wal-archive` bind changed from short to
long syntax to carry `propagation: rslave` (Task 9), and compose will not apply
that without recreating the container. Verified afterwards: healthy, 17
projects, WAL archiving to the NAS with an unbroken 208-segment run (§9.4).

Migration **0033** applied to `ivgs` and `ivgs_reconciliation_test`; downgrade
round-trip exercised on the test database.

**Nodes 02/03/04 need nothing from this package.** Nothing in it changes worker
task code that those nodes execute: the tier-migration and orphan-cleanup
repairs run only on node-01's `celery-default`, and the retention schedule ships
disabled. Their images may be left where they are. If the operator wants them
on the same tag for tidiness, the usual paste blocks apply — **and node-03's
service is `cogvideox-worker`, not `celery-worker`**.

---

## 14. Test evidence

Measured on node-01 against the deployed stack, 2026-08-26.

| Tree | Baseline (WP-57/58) | Now | Δ passed | New failures |
|---|---|---|---|---|
| `ivgs-api` | 880 / 0 / 0 / 0 | **904 / 0 / 0 / 0** | +24 | **0** |
| `ivgs-workers` | 799 / 18 / 48 / 15 | **809 / 18 / 48 / 15** | +10 | **0** |
| `ivgs-scheduler` | 22 / 21 / 0 / 0 | 22 / 21 / 0 / 0 | 0 | 0 |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | 4 / 0 / 0 / 0 | 0 | 0 |
| `tests_system` | 56 / 12 / 15 / 30 | **73 / 12 / 15 / 30** | +17 | **0** |
| **Total** | 1761 / 47 / 63 / 45 | **1812 / 47 / 63 / 45** | **+51** | **0** |

**ZERO new failures.** No assertion was weakened, no skip marker added, no
coverage deleted. The baseline document is updated in the same commits.

New tests:

* `ivgs-api/tests/test_wp59_deletion.py` — 22. The category map against
  `pg_constraint`, the non-terminal-job refusal for both `pending` and
  `running`, the terminal-job pass for both `success` and `failed`, the
  unreadable-registry refusal, five confirmation near-misses, the Task 4
  acceptance in one deletion, the audit row before and after, convergence, the
  interrupted-purge resume, and DELETING's absence from every transition set.
* `ivgs-workers/tests/test_wp59_retention.py` — 11 (10 + the nullable-policy
  test added with the second Task 7 finding).
* `tests_system/test_wp59_nfs_guard.py` — 17, driving the real guard script.
* `ivgs-api/tests/test_projects.py` — +3 route tests.

**Two existing tests were CORRECTED, and neither is a relaxation:**

1. `test_retention.py::test_storage_tier_enum_values` asserted
   `StorageTier.ARCHIVE.value == "archive"` and passed, because it checked the
   Python constant against itself rather than against the schema it has to
   write into. It now asserts the database's labels — strictly stronger, and
   the only version that could have caught the defect it was sitting on.
2. `test_service_project.py::TestDeleteProject` no longer calls
   `ProjectService.delete_project` (removed). It now asserts the method stays
   gone.

`tests_system/integration/test_projects_integration.py::test_delete_project` was
updated to the new contract. It sits in the 30-error `admin_headers` group
(**P2.57**) and does not run; leaving it asserting 204 would have been a latent
false statement.

**Environment note, not a retry:** no run in this package was timeout-killed.
The API tree took 4m33s. `SELECT count(*) FROM users` on the test database was 0
before the run (the WP-56 dirty-database check).

---

## 15. Ledger and register entries

**Swallow register — three new instances**, for
`WP-00-SWALLOWED-FAILURES_2026-08-14.md`:

| # | Instance | Status |
|---|---|---|
| 27 | `RetentionService._process_tier_transitions` — per-tier `except` appended to `report.errors`, which nothing read; the task returned `{'status':'ok'}` and Celery recorded SUCCESS | **CLOSED** — `report.status`, the task raises |
| 28 | `RetentionService.load_policies` — bare `except Exception` on a ValidationError meant the operator's configured retention policy was silently replaced by hardcoded defaults on every run since 2026-05-23 | **CLOSED** — logged as an ERROR naming the consequence, and `policy_source` is reported |
| 29 | `OrphanCleanupService.run_cleanup` — one `except Exception` around all three scans appends to `report.errors`, which nothing reads, and the task returns the report as success | **OPEN** — the service is inert for three other reasons first (§3.3); repairing it is D-2 |

**Phantom / inert-mechanism family** (WP-57 called the tier scan the seventh
instance):

| # | Instance | Status |
|---|---|---|
| 8 | `tasks.pipeline_orchestrator.run_retention_migration` — beat dispatches a Phase-5 stub; the real service has never executed | **CLOSED** — schedule points at the real task, shipped disabled |
| 9 | `tasks.pipeline_orchestrator.run_orphan_cleanup` — same, and the real service behind it is inert three times over | **OPEN — D-2** |
| 10 | `retention_policies` rows that have never been read | **CLOSED** |

---

## 16. Decisions needed

### D-1 — raise `BACKUP_RETENTION_WAL_DAYS` from 7 to 10?

**Recommend YES.** The PITR window is the WAL window, and with a weekly base
they exactly meet with no margin: one missed base backup opens an unrecoverable
7-day hole while both a base and an archive still exist. Three days of slack
costs about 1.4 GB on a NAS that is 1% full of 20 T.

Not changed here because retention is a policy number and the remit was to argue
it. One line in `ivgs-infra/.env`; both compose services already interpolate it
from the same value (WP-58 Task 2), so they cannot drift.

### D-2 — repair `OrphanCleanupService`, or delete it?

It is inert three times over (§3.3) and it is named in this package's brief as
the backstop for anything the binary purge misses. It is not one.

| Option | Implication |
|---|---|
| **Repair it** (recommended) | It must inherit `ProjectDeletionService.binary_manifest`'s shared-object guard, not grow a second copy — it QUARANTINES and then permanently DELETES, and without the guard it would delete a library asset's bytes out from under every project referencing them. Its Type-1 scan also has to be rewritten around volume fids, because the filer namespace is empty. That is a package. |
| **Delete it** | Honest, and cheap. Nothing depends on it today. The cost is that WP-59's deletion has no backstop for an object it could not confirm deleted — though it does report each one (`files_failed`) rather than losing it. |
| Leave it | The current state: a scheduled stub in front of an inert service, reporting SUCCESS nightly. This is the option the package exists to argue against. |

**Not switched on under any circumstances until it has the guard.**

### D-3 — something is looping on project `52d52867`

Five `talking_head` assets appeared on "New multiplication pass" during this
session (23:26, 23:41, 00:00, 01:12, 01:59), matching five
`assemble_prototype_draft` runs, with `handle_stage_completion` and
`media_join_watchdog` firing alongside. Nothing in WP-59 touches that project or
those tasks. It looks like a re-dispatch loop and it is accumulating rows and
bytes. **Recorded, not investigated** — out of this package's scope, and worth a
look before it grows.

### D-4 — nodes 02/03/04 image tags

Nothing in this package changes code those nodes execute (§13), so they can stay
where they are. Bring them to `v5.18.0-delete` only if you want one tag across
the fleet.

---

## 17. What was NOT done, and why

* **No restore was run against the live database.** The rehearsal is a separate
  cluster; `restore.sh --pit` stages a separate cluster; neither addresses the
  live one.
* **The tier-migration schedule is not enabled**, and the first live pass was
  not run. §7.6 is the operator's.
* **No base backup was taken.** §8.7 is the operator's.
* **No prune was run against the live backup store.** Every retention test uses
  a pytest `tmp_path` or a temporary tree in the scratchpad.
* **No restore feature was built** (Task 5 forbids it). §6.2 states what one
  would involve.
* **`library_assets` was never written by the deletion service.** The one
  throwaway library row created as a test fixture was removed by hand
  afterwards.
* **`OrphanCleanupService` was not repaired** — D-2.
* **No screenshots** — §12, with the reason and the operator's reproduction
  path.
* **Nothing was deployed to node-05 or node-06**, and nothing was read from
  them.

---

## 18. Push block — COMMITTED AND HELD, NOT PUSHED

Six commits on `main`, count-gated. **The gate is the test baseline**: if the
counts below do not reproduce, do not push.

```bash
# ── node-01 ────────────────────────────────────────────────────────────────
cd /opt/ivgs

# 1. The six commits that must be there, newest first. f767429 (WP-57) is the
#    parent; anything else below 68dcec1 means the history is not what this
#    report describes.
git log --oneline -7
#   <this>  docs(wp-59): report - the deletion works, and three mechanisms ...
#           (its own hash is deliberately not quoted here: the report is the
#            last commit, so quoting it would have been stale the moment it
#            was written)
#   053fc7d fix(wp-59): the configured retention policy has never governed anything
#   bbe0556 test(wp-59): the restore is rehearsed, and the baseline moves to 1812/47
#   2944d7c feat(wp-59): a physical base, so the WAL archive becomes replayable
#   d4b42e1 fix(wp-59): every backup writer asserts nfs4, and the binds propagate
#   97cfee6 fix(wp-59): tier migration - the scheduled task was a stub ...
#   68dcec1 feat(wp-59): a project can be deleted deliberately ...
#   f767429 docs(wp-57): report, and the baseline moved to 880/799   <- parent

# 2. Nothing untracked or modified is being left behind.
git status --short          # expect: empty

# 3. THE COUNT GATE. Re-measure all five trees and compare to the baseline.
PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
unset PGPW PGUSER

# The test database must be at 0033 and clean before believing any number.
docker exec ivgs-postgres psql -U ivgs -d ivgs_reconciliation_test -Atc \
  "SELECT (SELECT * FROM alembic_version) AS rev, (SELECT count(*) FROM users) AS users;"
# expect: 0033|0

.venv/bin/python -m pytest ivgs-api/tests            -q | tail -1   # 904 passed
.venv/bin/python -m pytest ivgs-workers/tests        -q | tail -1   # 809 passed, 18 failed, 48 skipped, 15 errors
.venv/bin/python -m pytest ivgs-scheduler/tests      -q | tail -1   # 22 passed, 21 failed
.venv/bin/python -m pytest ivgs-backup-worker/tests  -q | tail -1   # 4 passed
.venv/bin/python -m pytest --timeout=120 tests_system -q | tail -1  # 73 passed, 12 failed, 15 skipped, 30 errors

# 4. The deployed images are the committed tree.
docker ps --format '{{.Names}}\t{{.Image}}' | grep -E 'fastapi|nextjs|celery|backup-worker'
# all six on v5.18.0-delete

# 5. ONLY IF EVERY COUNT ABOVE MATCHES:
git push origin main
```

**If any count differs, stop.** A timeout-killed run leaves the test database
dirty (`users` non-zero) and the next number is residue, not a regression — see
the baseline §2.
