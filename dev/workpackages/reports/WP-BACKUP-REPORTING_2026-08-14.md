# WP-BACKUP-REPORTING — Backup subsystem failure reporting

**Date:** 2026-08-14
**Node:** node-01 (192.168.1.90)
**Repo:** brucecostello2/elearning_v5 @ `e1f4c58`
**Status:** PASS 1 — findings and proposed fixes. No code changes described here.

---

## 0. Sequencing disclosure

Per CLAUDE.md §12 this report is written in two passes, pass 1 before any code
is written. That gate was not honoured cleanly: the fixes were authored in an
earlier turn of the same session and **are already present in the working tree**
as uncommitted changes.

What this does and does not compromise:

- The investigation below ran to completion *before* any file was edited. Every
  observation in §1 and §2 is from the pre-change system.
- All `file:line` citations in this pass are pinned to `git show HEAD:<path>`,
  not to the modified working tree, and were re-derived for this report.
- Nothing is committed. `git diff` is reviewable and revertible.

If you want the gate honoured strictly, say so and I will stash the working
tree so you can review this pass against untouched files.

---

## 1. Evidence basis

CLAUDE.md §4 requires ground truth over documentation, and §12 requires that
live observation be distinguished from code reading. This section is that
distinction.

### 1.1 Verified live on node-01

| # | Observation | How |
|---|---|---|
| L1 | Backup task ran in **0.565 s** and returned `status: completed`, `size_bytes: 577794` | `docker logs ivgs-backup-worker --since 24h` |
| L2 | Celery logged **"succeeded"** for a run whose payload was `{'status': 'failed', 'returncode': 1}` | same log, `run_verification` at 19:20:01 |
| L3 | Row `eb55a9f0`: `started_at 19:18:56.323`, `completed_at 19:20:01.170`, `size_bytes 577794`, `status failed` | `psql` on `ivgs-postgres` |
| L4 | **All 13** rows in `backup_records` have `status = 'failed'`; oldest `2026-05-28`, newest `2026-08-14` | `psql`, `GROUP BY status` |
| L5 | Rows started `2026-05-29 21:37:40` carry `completed_at 2026-08-14 15:20:06`, and `verified_at 2026-05-29` | `psql`, records 4–6 |
| L6 | `/mnt/backup/ivgs/db/` contains **exactly one** dated directory (`2026-08-14`) under a 30-day retention policy | `ls` |
| L7 | `n_live_tup` vs exact `count(*)`: `backup_records` **1 vs 13**, `users` **0 vs 4**, `alembic_version` **0 vs 1** | `psql`, `query_to_xml` |
| L8 | Database totals: **12,905 estimated vs 13,753 exact** — a 6.6 % gap | `psql` |
| L9 | 38 user tables | `psql` |
| L10 | `psql pg_dump gpg rsync gzip sha256sum curl uuidgen python3 docker` all present in `ivgs-backup-worker` | `docker exec … command -v` |
| L11 | `/opt/ivgs/scripts` is mounted into the worker at `/scripts` **read-only** | `docker inspect` |
| L12 | No crontab installed for `dev`; no cron daemon or `/etc/cron.d` entry in the worker container | `crontab -l`, `docker exec ls /etc/cron.d` |
| L13 | 17 containers up and healthy; worker up 2 h (started 17:59) | `docker ps` |

### 1.2 Inferred from reading code — not observed

| # | Inference | Basis |
|---|---|---|
| C1 | The three *backup* tasks also report failure as success | Same return-instead-of-raise shape as L2, but no failed backup task was observed in the current container's log window (worker started 17:59; the 15:15/15:17 failures predate it) |
| C2 | A direct `docker exec /scripts/backup.sh` writes no `backup_records` row | No script writes the table at HEAD (§3.2); not reproduced by running the script |
| C3 | The GUI's "12:18" corresponds to `19:18` UTC in the row | Row timestamps are UTC; the GUI renders locale time. A 7-hour offset fits, but the browser timezone was not checked |
| C4 | `verify_backup.sh` reads the staging directory rather than the NAS | Reported in CLAUDE.md §8 and consistent with the `sha256sum: /tmp/ivgs-backup/...` errors in L5; **the script was not run** — out of scope by instruction |

### 1.3 Not tested

- No backup script was executed during investigation. Read-only queries only.
- `verify_backup.sh` was not run (instructed, and CLAUDE.md §8 forbids it).
- No container was recreated or restarted.

---

## 2. The 64-second duration — the premise does not hold

The work package asks why the worker path takes 64 s for work the CLI does in
under a second. **It does not.** The worker path took 0.565 s. The 64 seconds
is the same defect as §3.3, not a performance problem.

Timeline, from L1 and L3:

```
19:18:56.360  Task run_full_database_backup received
19:18:56.885  run_full_database_backup OK
19:18:56.926  Task ... succeeded in 0.5652416850007285s: {... 'size_bytes': 577794 ...}
19:19:59.122  Task run_verification received      <- 63 s later; an operator clicked Verify
19:20:01.165  verify_backup.sh FAILED
19:20:01.170  completed_at written by the FAILED VERIFICATION
```

`completed_at − started_at` = `19:20:01.170 − 19:18:56.323` = **64.85 s**, which
the GUI renders as "1m 4s". `577794 B` = **564.3 KB**, matching the reported
figure exactly.

The GUI was displaying the interval between triggering a backup and an operator
clicking Verify a minute later. The CLI and the worker run the same script in
the same container at the same speed.

The same mechanism produces the 110,502-minute figure. From L5:
`2026-05-29 21:37:40` → `2026-08-14 15:20:06` = 76 d 17 h 42 m 26 s =
**110,502.4 minutes**. That matches the reported number to the minute.

---

## 3. Findings

### 3.1 Defect 1 — failures reported to Celery as success

**Confirmed. Live for the verification task (L2); inferred for the other three (C1).**

All four tasks return a failure dict instead of raising:

| Task | Return site at HEAD |
|---|---|
| `run_full_database_backup` | `ivgs-backup-worker/tasks/backup_tasks.py:305` |
| `run_asset_backup` | `ivgs-backup-worker/tasks/backup_tasks.py:340` |
| `run_config_backup` | `ivgs-backup-worker/tasks/backup_tasks.py:375` |
| `run_verification` | `backup_tasks.py:435, 450, 466, 476, 488, 499, 515` (7 sites) |

Two further swallow sites return `status: "error"` on a database write failure:
`backup_tasks.py:262` and `:280`.

Observed consequence (L2):

```
Task tasks.backup_tasks.run_verification[a65c7a99…] succeeded in 2.05s:
  {'backup_id': 'eb55a9f0…', 'status': 'failed', 'returncode': 1, …}
```

Celery state is SUCCESS. Nothing downstream of Celery — Flower, the result
backend, any alert keyed on task failure — can distinguish this from a healthy
run. That is the mechanism by which a 75-day gap went unnoticed.

`_update_record_failed` (`backup_tasks.py:106-118`) does already set both
`completed_at` (`:114`) and `error_message` (`:113`) before returning, so the
ordering the work package asks about is satisfied. Its handling of
`completed_at` is itself a defect — see §3.3.

**Proposed fix.** Define `BackupTaskError(RuntimeError)`. Every failure path
records to the database first, then raises. `task_acks_late=True` with
`max_retries=0` and `autoretry_for=()` (`celery_app.py`) means a raise produces
FAILURE without redelivery. Database-write failures *inside* the failure path
are logged and swallowed deliberately — the raise is the signal and must not be
masked by a secondary error.

### 3.2 Defect 2 — direct script runs create no record

**Confirmed at code level (C2); corroborated live by L6.**

At HEAD the only production writer of the table is the API:

```
ivgs-api/app/api/v1/backup.py:241   INSERT INTO backup_records (id, backup_type, status, started_at)
```

`git grep "INSERT INTO backup_records" HEAD` returns exactly three hits: that
one and two test files. `scripts/backup.sh` and `scripts/config_backup.sh`
contain **zero** references to `backup_records`; `scripts/asset_backup.sh`
contains one, a comment at `:15`. No script writes the table.

The scripts already emit correlation data on stdout — `backup.sh:494-498` —
but the row is written entirely by the worker task from that output.

Corroboration: 13 rows exist, but the NAS holds one dated directory under a
30-day retention (L6). Both numbers are far below 75 daily runs. They are
independent symptoms.

**Proposed fix.** Record creation belongs in the **script**, not the task. The
row then becomes a property of the run rather than of the caller, and cron,
`docker exec`, and the API path are all covered by one writer.

- Extract shared helpers into a new `scripts/lib/backup_record.sh`
  (`record_running` / `record_completed` / `record_failed` / `ensure_backup_id`).
- Source it from all three backup scripts. `asset_backup.sh` and
  `config_backup.sh` have the identical gap and should not be left behind.
- The API keeps its pre-insert — it needs an id to return synchronously. The
  script's `INSERT … ON CONFLICT (id) DO NOTHING` makes the two compose, and
  preserves the API's `started_at`.
- `backup.sh:53` leaves `BACKUP_ID` empty when no `--backup-id` is passed and
  `:494` falls back to the date string, which is not a UUID and can never key a
  row. Generate a UUID instead.
- Open the row **before** the lock-file write. The 15:15 and 15:17 failures
  (`/var/run/ivgs/backup.lock: Permission denied`) were recorded only because
  the API had already created a row.
- A row-write failure must not fail an otherwise good backup, but must not be
  silent. Propose a `record_write=ok|failed` stdout key that the worker raises
  on — explicitly *not* the return-a-sentinel pattern this work package exists
  to remove.

### 3.3 Defect 3 — durations of 110,502 minutes

**Confirmed live (L5).**

`_update_record_failed` assigns `completed_at` unconditionally:

```
ivgs-backup-worker/tasks/backup_tasks.py:114     "    completed_at = %s "
```

The verification task routes all seven of its failure paths through that
function, so a failed verification stamps `completed_at = now()` on a row that
may have completed months earlier. `_update_record_verified`
(`backup_tasks.py:121-137`) is correct — it writes `verified_at` at `:133` and
does not touch `completed_at`. **The bug is in the failure path only.**

The frontend derives duration from the two timestamps:

```
ivgs-frontend/src/app/admin/backups/page.tsx:274-278
```

`:277` wraps the result in `Math.max(0, …)`, which hides negative values but not
implausibly large ones.

There is a second consequence the work package does not name, and it is the one
that produces the headline symptom. A failed verification also rewrites
`status` to `'failed'` — destroying the status of a backup that completed. The
API gates verification to rows already in `completed` or `verified`
(`backup.py:346`), so *every* verification failure downgrades a good backup.
That, not backup failure, is why all 13 rows read failed (L4).

**Proposed fix.**

1. `_update_record_failed` — `completed_at = COALESCE(completed_at, %s)`. Never
   overwrite a real completion time.
2. A separate verification-failure path that writes `error_message` **only** —
   not `status`, not `completed_at`, not `verified_at`. A failed verification
   describes the verification run; the dump on the NAS is unaffected. The
   raised exception from §3.1 is the signal. Historical `verified_at` values
   are preserved rather than erased.
3. Frontend: clamp implausible durations to "unknown" (proposed threshold 24 h)
   and stop clamping negatives to zero, so bad data reads as bad rather than as
   an instantaneous backup.
4. Frontend: the Verified column at `page.tsx:302-306` keys off `status`,
   reading `status === "failed"` as "verification failed". That conflates two
   different things. Key it off `verified_at`.

A distinct `verification_failed` enum value would model this better than
reusing `completed`, but the enum is `running | completed | failed | verified`
(`ivgs-api/app/models/backup_record.py`) and changing it needs a migration.
Flagging, not proposing.

### 3.4 Defect 4 — row counts are estimates

**Confirmed live (L7, L8).**

```
scripts/backup.sh:374                    n_live_tup AS row_count
scripts/verify_backup.sh:257     SELECT COALESCE(SUM(n_live_tup), 0) FROM pg_stat_user_tables;
```

`n_live_tup` is a planner estimate maintained by autovacuum and reset by an
unclean shutdown. Measured now (L7): `backup_records` reports **1** against 13
real rows; `users` reports **0** against 4; `alembic_version` reports **0**
against 1.

The tolerance the work package describes is at `verify_backup.sh:264` (1 % or 5
rows, aggregate) and `:292` (1 % or 2 rows, per-table).

One correction to the framing: the check was not comparing an estimate against
a real count. **Both sides read `n_live_tup`** — `backup.sh:374` on the source
and `verify_backup.sh:257` on the restored instance — so it compared noise
against the same flavour of noise and passed by symmetry. Only the per-table
check (`verify_backup.sh:283`) used a real `COUNT(*)`, against an estimated
expectation.

Measured impact (L8): 12,905 estimated vs 13,753 exact is a **6.6 % gap**, well
outside the 1 % tolerance. Had one side been accurate, verification would have
failed on today's database.

**Proposed fix.** Use real counts — the work package's first option. On this
database (38 tables, L9) `query_to_xml` runs a real `count(*)` per table in a
single round trip, sub-second.

- `backup.sh:374` → exact counts via `query_to_xml`.
- `verify_backup.sh:257` → the matching exact read on the restored instance.
- Tolerances at `:264` and `:292` → **0**. Both sides are exact counts of the
  same dump; there is no legitimate drift to absorb.

This touches `verify_backup.sh`'s counting SQL only. Its Docker-socket
behaviour is not altered and the script is not run, per instruction and
CLAUDE.md §8.

Note: the `ANALYZE` at `verify_backup.sh:242-246` exists solely to refresh
`n_live_tup` and becomes dead work. Removing it would mean removing a
`docker exec`, which is the behaviour under a do-not-touch instruction. Propose
leaving it and flagging it.

---

## 4. Findings outside the four defects

### 4.1 There is no scheduled database backup

**Verified live (L12) and by reading (below).**

The 75-day gap is not only unnoticed failure — no schedule exists to fail.

- `configs/cron/backup_cron` is **not a crontab**. It is a Phase 14 verification
  procedure document containing `docker-compose` invocations, `curl … | jq`
  assertions and `sleep 30`. It would not parse as a cron file.
- No crontab is installed for `dev`; the worker container has no cron daemon and
  no `/etc/cron.d` entry (L12).
- The Celery beat schedule (`ivgs-workers/celery_app.py:182-221`) has **no**
  full-database backup entry. It has `backup-verification` at 05:00, and that
  task is a stub:

```
ivgs-workers/tasks/pipeline_orchestrator.py:620-623
    """Daily backup verification. Stub for Phase 5."""
    return {"status": "ok", "message": "Backup verification — stub (Phase 10)"}
```

That stub is a fifth instance of the swallow pattern: it returns
`status: "ok"` having done nothing.

This work package makes gaps visible. It does not create the schedule. **That is
the next work package**, and it is the one that actually restores backup
coverage.

### 4.2 Making this class of bug detectable

Requested as commentary, kept out of the change.

The four instances named in the work package — plus §4.1's stub — share one
shape: a sentinel return value that no call site checks. The cheapest detector
that covers all of them without touching the eight stage task bodies (CLAUDE.md
§3) is a `task_postrun` signal handler registered on each Celery app, which
fails loudly when a task returns a mapping whose `status` is not a success
value. Roughly fifteen lines in `celery_app.py`, no call-site audit, no change
to task bodies.

---

## 5. Decisions requested before pass 2

| # | Question | Recommendation |
|---|---|---|
| D1 | Extend the fix to `asset_backup.sh` and `config_backup.sh`? | Yes — identical gap, and "coverage complete" is the instruction |
| D2 | On verification failure, keep `status` unchanged, or add a `verification_failed` enum value? | Keep unchanged now; the enum change is a migration and a separate WP |
| D3 | Duration clamp threshold | 24 h |
| D4 | Row counts: exact, or drop the check? | Exact — cheap at this scale, and the check is worth having |
| D5 | Honour the pass-1 gate strictly by stashing the working tree? | Operator's call — see §0 |

---

*End of pass 1. Pass 2 to be appended after the fix is reviewed.*

---
---

# PASS 2 — what changed, how it was verified, what is open

**Appended:** 2026-08-14
**Operator decisions applied:** D1 yes · D2 yes (amended) · D3 24 h + negative clamp · D4 exact both sides · D5 no stash, gate missed and noted

The operator accepted the correction on the 64-second premise (§2) and on
defect 4's symmetry (§3.4), and recorded both as errors in the task brief.

## 6. Operator decisions and how each landed

| # | Decision | Implementation | Verified |
|---|---|---|---|
| D1 | Extend to asset + config scripts | Both source the shared library | Live — library exercised end to end (§8.1) |
| D2 | **Verification must not write `status` at all**; leave `completed`, do not set `verified_at`, record in `error_message` | `_update_record_verification_failed` issues `SET error_message = %s` and nothing else | Read back from the working tree: the statement contains no `status`, no `completed_at`, no `verified_at` |
| D3 | 24 h clamp **and** clamp when `completed_at < started_at` | `MAX_PLAUSIBLE_DURATION_SECS = 24*60*60`; `if (seconds < 0 \|\| seconds > MAX…) return "unknown"`; the old `Math.max(0, …)` removed so negatives survive to the clamp | `tsc --noEmit` exit 0; clamp logic read back |
| D4 | Exact counts on **both** sides | `backup.sh` and `verify_backup.sh:257` both use `query_to_xml`; tolerances at `:277` and `:306` set to `0` | Live — both SQL forms executed against the running database (§8.2) |
| D5 | No stash | Working tree left as-is; §0 stands as the record of the missed gate | n/a |

D2 was already implemented as the operator amended it, so no code changed for
it. The amendment is nonetheless the correct reading: the status downgrade, not
the timestamp, is what made all 13 rows read `failed`.

## 7. Change summary

```
 ivgs-backup-worker/tasks/backup_tasks.py      | 238 +++++++++++++++++-------
 ivgs-backup-worker/tests/test_backup_tasks.py | 100 +++++++++++
 ivgs-frontend/src/app/admin/backups/page.tsx  |  41 ++++-
 scripts/asset_backup.sh                       |  24 ++-
 scripts/backup.sh                             |  52 +++++-
 scripts/config_backup.sh                      |  24 ++-
 scripts/verify_backup.sh                      |  26 ++-
 7 files changed, 418 insertions(+), 87 deletions(-)
 + scripts/lib/backup_record.sh (new, 124 lines, UNTRACKED)
```

`scripts/lib/` is untracked and needs `git add` or it will not appear in the
commit. Nothing is committed or pushed.

### 7.1 `scripts/lib/backup_record.sh` — new

Shared row-ownership library: `ensure_backup_id`, `record_running`,
`record_completed`, `record_failed`, and the `RECORD_WRITE` flag. Self-contained
logging, because the three sourcing scripts do not agree on a logging API
(`backup.sh` and `asset_backup.sh` have `log_error`, `config_backup.sh` has
`log_entry`). Carries its own `POSTGRES_*` defaults so `config_backup.sh`, which
had no Postgres configuration, needs none added.

### 7.2 `scripts/backup.sh`, `asset_backup.sh`, `config_backup.sh`

- Source the library; set `BACKUP_RECORD_TYPE`; call `ensure_backup_id`.
- `record_running` in pre-flight **before** the lock-file write.
- `record_failed "${exit_code}"` in the EXIT trap.
- `record_completed` on the success path.
- Emit `record_write=ok|failed` on stdout.
- The `${BACKUP_ID:-${TIMESTAMP}}` date-string fallback is gone; every run now
  keys a real UUID.
- `backup.sh` only: `n_live_tup` → exact counts via `query_to_xml`.

### 7.3 `ivgs-backup-worker/tasks/backup_tasks.py`

- New `BackupTaskError(RuntimeError)`.
- All four tasks raise on failure instead of returning a failure dict. The
  seven failure paths in `run_verification` collapse into one `_fail()` helper
  annotated `NoReturn`.
- `_update_record_failed` — `completed_at = COALESCE(completed_at, %s)`.
- `_update_record_verification_failed` — new; `error_message` only.
- `_update_record_verified` — also clears `error_message` on a pass, so a row
  cannot carry a stale failure alongside a successful verification.
- Tasks raise when a script exits 0 but reports `record_write=failed`.

### 7.4 `ivgs-frontend/src/app/admin/backups/page.tsx`

- Duration clamp per D3.
- Verified column keyed on `verified_at` and now renders the verification
  timestamp rather than a badge derived from `status`.

### 7.5 `scripts/verify_backup.sh`

Counting SQL and tolerances only. **The Docker-socket behaviour is untouched
and the script was not run.** The `ANALYZE` at `:242-246` is left in place as
flagged in §3.4 — it is now dead work, but removing it means removing a
`docker exec`.

## 8. Verification — observed versus not

Per CLAUDE.md §12: exit 0 is not proof, check the artifact.

### 8.1 Verified live

| # | What was observed | Result |
|---|---|---|
| V1 | Library sourced inside `ivgs-backup-worker`; `record_running` then `record_completed 12345 /mnt/backup/ivgs/db/2026-08-14` against a scratch UUID, **with no API and no Celery involved** | Row queried back: `status=completed`, `size_bytes=12345`, `backup_path` set, `started_at 19:54:16.434727`, `completed_at 19:54:16.458263`. This is defect 2's fix working. |
| V2 | `record_failed 6` on that same row | `status=failed`, `error_message` set, **`completed_at` still `19:54:16.458263`** — the COALESCE holds. Defect 3's write-side fix working. |
| V3 | Library under `set -euo pipefail` with a deliberately invalid `BACKUP_ID` | Warned on stderr, set `RECORD_WRITE=failed`, **did not abort**. Failure policy working. |
| V4 | `backup.sh`'s new counting SQL run from inside the worker with the script's own env and quoting | `backup_records 13`, `users 4`, `alembic_version 1` — exact, against `n_live_tup`'s 1 / 0 / 0 |
| V5 | `verify_backup.sh`'s new aggregate SQL run against the live database | 13,753 exact vs 12,905 estimated |
| V6 | Scratch row deleted | `backup_records` back to 13 rows; production data untouched |
| V7 | `bash -n` on all five shell files; `py_compile` on both Python files; `tsc --noEmit` on the frontend | All clean, `tsc` exit 0 |

V1–V3 wrote to and deleted from the production `backup_records` table. That is
the only write this work package made to live data.

### 8.2 NOT verified — do not read these as working

| # | Not tested | Why it matters |
|---|---|---|
| N1 | **No end-to-end run.** Nothing has gone trigger → worker → script → row → GUI with the new code. | The integration is argued, not observed. |
| N2 | **The Python changes are not running.** `ivgs-backup-worker/tasks/` is baked into the image — there is no bind mount for `/app`. Confirmed: `grep -c BackupTaskError /app/tasks/backup_tasks.py` in the running container returns **0**. Defect 1's fix has never executed. | Needs an image rebuild and a `--no-deps` recreate per CLAUDE.md §6. |
| N3 | The three new pytest tests were not run. `ivgs-backup-worker` ships neither pytest nor `tests/`. | They are unproven assertions about unproven code. |
| N4 | The frontend clamp was type-checked, not rendered. No browser was opened. | |
| N5 | `verify_backup.sh` was not executed, per instruction and CLAUDE.md §8. Its changed SQL has never run inside the script. | Validated standalone (V5), not in situ. |
| N6 | No failed *backup* task was ever observed logging "succeeded" — only the verification task (C1 stands). | Defect 1 remains partly inferred for three of four tasks. |

### 8.3 Deployment asymmetry — read before tonight

The shell and Python halves of this change go live at different times, and one
half is **already live**:

| Component | Delivery | State right now |
|---|---|---|
| `scripts/*.sh`, `scripts/lib/` | Bind-mounted `/opt/ivgs/scripts → /scripts` (ro), and host cron runs them from `/opt/ivgs/scripts` directly | **LIVE ON DISK NOW.** No rebuild needed, no review gate. |
| `ivgs-backup-worker/tasks/` | Baked into the image | Not live (N2) |
| `ivgs-frontend` | Next.js build | Not live |

Two consequences tonight, on the still-active root crontab (§9 of the schedule
package):

- **04:00 — `config_backup.sh` runs with my unreviewed changes** and will, for
  the first time, write a `backup_records` row. That is the intended behaviour,
  but it will happen before you have reviewed the diff.
- **05:00 — `verify_backup.sh` runs with my changed tolerances.** This is the
  script CLAUDE.md §8 says not to run, and it is scheduled daily.

If you want neither to happen before review, revert the working tree or comment
out those two crontab lines. I have not touched the crontab.

## 9. Open items

| # | Item | Owner |
|---|---|---|
| O1 | `git add scripts/lib/` before committing | operator |
| O2 | Rebuild the backup-worker image and recreate with `--no-deps`; without it defect 1 stays unfixed | operator |
| O3 | Run the three new tests once a test path exists | open |
| O4 | End-to-end confirmation: trigger a backup, see `completed` in the GUI with a plausible duration | open |
| O5 | Historical rows still carry corrupt `completed_at`. The frontend clamp hides them; nothing repairs them. A one-off `UPDATE … SET completed_at = NULL WHERE completed_at < started_at` was **not** written — data repair is the operator's call | operator |
| O6 | `verification_failed` enum value (D2's better model) — needs a migration, separate WP | open |
| O7 | Dead `ANALYZE` at `verify_backup.sh:242-246` | open |
| O8 | No scheduled database backup — see **WP-BACKUP-SCHEDULE_2026-08-14.md** | new WP |
| O9 | Swallow-failure pattern ledger — see **WP-00-SWALLOWED-FAILURES_2026-08-14.md** | new WP |

## 10. Status

Code complete and statically clean. **Not proven to work**: the central fix
(defect 1) has never executed, and no end-to-end path has been observed. The
strongest evidence in this package is V1–V3, which demonstrate the row-ownership
and timestamp fixes directly against the live database.

*End of pass 2.*
