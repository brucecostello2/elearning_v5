# WP-BACKUP-SCHEDULE — Where backup scheduling should live

**Date:** 2026-08-14
**Node:** node-01 (192.168.1.90)
**Repo:** brucecostello2/elearning_v5 @ `e1f4c58`
**Status:** PASS 1 + PASS 2 (appended below). Option B implemented and deployed;
database half of the exit gate proven, asset half blocked on decision D1.
**Origin:** §4.1 of `WP-BACKUP-REPORTING_2026-08-14.md`

**Exit gate (operator):** a database backup and an asset backup both run
unattended and appear in the GUI as completed.

---

## 1. Operator context, and where it was incomplete

The cron entries for `backup.sh` and `asset_backup.sh` were removed earlier
today on the reasoning that both should run from the worker. The operator has
already identified the gap: the worker has no beat schedule for either.

Two further corrections, both from live evidence:

1. **Removing the cron entries did not cause the 75-day gap.** The entries were
   present and firing nightly; they were failing on a one-word configuration
   error (§2.2). The gap predates the removal by months.
2. **`asset_backup.sh` failing from cron was never a lock-dir or NFS problem.**
   It failed on a disk-space check against the old, nearly-full target (§2.3).

---

## 2. Findings

### 2.1 Current schedule state — verified live

Root's crontab (`sudo crontab -l`) retains the section headers with the entries
removed beneath them:

```
# 02:00 — Full database backup
                                     <- entry removed
# 03:00 — Asset backup
                                     <- entry removed
# 04:00 — Config backup
0 4 * * * /opt/ivgs/scripts/config_backup.sh   >> /var/log/ivgs/config_backup-cron.log 2>&1
# 05:00 — Verify yesterday's database backup
0 5 * * * /opt/ivgs/scripts/verify_backup.sh $(date -d "yesterday" +\%Y-\%m-\%d) >> …
```

`MAILTO=""` — cron output is discarded by design.
`BASH_ENV=/etc/ivgs/cron-backup-env` supplies `POSTGRES_HOST`, `POSTGRES_PORT`,
`POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `WAL_ARCHIVE_DIR`,
`WAL_RETENTION_DAYS`, `BACKUP_GPG_RECIPIENT`, `PROMETHEUS_PUSHGATEWAY`.

Log mtimes confirm both removed jobs ran this morning before removal:
`backup-cron.log` 02:00, `asset_backup-cron.log` 03:00, `config_backup-cron.log`
04:00, `verify_backup-cron.log` 05:00.

**`verify_backup.sh` is still scheduled daily at 05:00.** That is the script
CLAUDE.md §8 says must not be run, and it has been running unattended every day.
Today's 05:00 run: `Backup directory not found: /mnt/backup/ivgs/db/2026-08-13`,
then `Backup verification FAILED  triggering BackupFailed alert`.

### 2.2 Root cause of the 75-day database gap — verified live

`backup-cron.log` shows the same failure on consecutive days:

```
{"timestamp":"2026-08-13T02:00:01.125Z","level":"ERROR",… "message":"Cannot connect to PostgreSQL",
 "extra":{"host":"localhost","port":5432}}
{"timestamp":"2026-08-13T02:00:01.129Z","level":"ERROR",… "message":"Backup failed with exit code 4"}
{"timestamp":"2026-08-14T02:00:01.099Z","level":"INFO", … "=== IVGS v5 Daily Database Backup Starting ==="}
{"timestamp":"2026-08-14T02:00:01.138Z","level":"ERROR",… "message":"Cannot connect to PostgreSQL",
 "extra":{"host":"localhost","port":5432}}
{"timestamp":"2026-08-14T02:00:01.143Z","level":"ERROR",… "message":"Backup failed with exit code 4"}
```

The cause, measured now:

| Check | Result |
|---|---|
| `grep '^export POSTGRES_HOST=' /etc/ivgs/cron-backup-env` | `localhost` |
| `docker port ivgs-postgres` | `5432/tcp -> 192.168.1.90:5432` |
| `pg_isready -h localhost -p 5432` | `no response`, **exit 2** |
| `pg_isready -h 192.168.1.90 -p 5432` | `accepting connections`, **exit 0** |

Postgres publishes on the LAN address only, not on loopback. `POSTGRES_HOST=localhost`
therefore fails `pg_isready` in `preflight_checks`, and `backup.sh` exits 4 before
producing anything — no dump, no NAS directory, no row. **One word in one env
file is the whole 75-day gap.**

This is consistent with `/mnt/backup/ivgs/db/` holding exactly one dated
directory (L6 of the reporting package): every cron run since the misconfiguration
died in pre-flight, and today's single directory came from the 19:18 worker run.

### 2.3 Why `asset_backup.sh` failed from cron — verified live

```
{"timestamp":"2026-08-14T03:00:01.262Z","level":"ERROR","service":"asset-backup",
 "message":"Insufficient NAS disk space","extra":{"available_mb":580,"required_mb":5120}}
```

The check is `asset_backup.sh:239`, `df -BM "${BACKUP_NAS_DIR}"`, field 4, against
`MIN_DISK_SPACE_MB=5120`.

Measured now on the `.7` NFS target:

```
Filesystem                  1M-blocks   Used Available Use% Mounted on
192.168.1.7:/mnt/store/ivgs 22373536M 46787M 22326749M   1% /mnt/backup/ivgs
```

22,326,749 MB available. The awk field extraction was re-run and yields field 4
correctly, so the check itself is sound.

The 580 MB reading is therefore not the current target. `/etc/fstab` still
carries the stale comment `# Backup NAS (SMB share at //192.168.1.9/elearning`
above the active NFS line, and CLAUDE.md §2 records `.9` as the retired,
now-forbidden CIFS NAS. The 03:00 run measured the old, nearly-full `.9` share
before today's migration to `.7`.

**The operator's expectation that `asset_backup.sh` would now succeed is
consistent with all available evidence, but is NOT verified — the script was not
run.** 45 GB of assets are already present on the new target.

#### 2.3.1 The lock-dir fix and the cron path — reconciliation

The operator attributes the expected recovery to the lock-dir fix. That fix is
real and verified:

```
/etc/tmpfiles.d/ivgs.conf   (created 2026-08-14 17:58)
d /var/run/ivgs 0755 999 999 -
```

`/run/ivgs` is now present, mode 0755, owned by uid 999 — and uid 999 on this
host resolves to `node_exporter`, the same numeric uid that is `ivgs` inside the
containers. That satisfies CLAUDE.md §8.

But it does not explain the cron failures, and the distinction matters:

| Path | Runs as | Was the lock dir a blocker? |
|---|---|---|
| Worker / API (`docker exec`, Celery) | uid 999 in-container | **Yes.** The 15:15 and 15:17 rows carry `/var/run/ivgs/backup.lock: Permission denied` and `/var/run/ivgs/asset-backup.lock: Permission denied` |
| Host cron | **root** | **No.** root writes the lock file regardless of ownership; `backup-cron.log` and `asset_backup-cron.log` show exit 4 and exit 3 respectively, never a lock error |

So two independent faults were in play, each blocking a different path:

- the missing lock dir blocked the **worker** path (fixed 17:58);
- `POSTGRES_HOST=localhost` (§2.2) and the full `.9` target (§2.3) blocked the
  **cron** path — and `POSTGRES_HOST` is **still broken now**.

The conclusion "asset_backup.sh would now succeed from cron" is probably right,
but the operative fix for it was the `.7` NFS migration, not the lock dir.
`backup.sh` from cron will still fail tonight if P3 is not applied, lock dir or
no lock dir.

### 2.4 Celery beat cannot currently reach the backup worker — verified live

Beat has no backup entries at all. `ivgs-workers/celery_app.py:182-221` schedules
heartbeat supervision, DLQ processing, orphan cleanup, retention migration,
GPU metrics, model polling, the media-join watchdog — and `backup-verification`
at 05:00, which is a stub (§4).

More importantly, **the two Celery apps do not share a Redis keyspace**:

| App | `global_keyprefix` |
|---|---|
| `ivgs-backup-worker/celery_app.py:127` | `"ivgs_backup_"` |
| `ivgs-api` dispatcher, `backup.py:63` | `"ivgs_backup_"` (set deliberately to match) |
| `ivgs-workers/celery_app.py:252-262` | **none** |

`ivgs-celery-beat` runs the `ivgs-workers` app. A beat entry added there would
publish into the unprefixed keyspace and the backup worker, consuming under
`ivgs_backup_`, would never see it. The API works around this by constructing a
separate producer with the matching prefix (`backup.py:55-68`).

This is the single most important constraint on the design: **"schedule it in
beat" is not a one-line change to the existing beat schedule.**

### 2.5 Nothing delivers the alert that was firing — verified live

The signal existed the whole time. `BackupFailed` is defined at
`ivgs-infra/monitoring/prometheus/alert_rules.yml:143-157`, `expr:
ivgs_backup_last_status == 0`, instant, severity critical. The scripts push that
gauge from their EXIT trap, so every failed 02:00 run pushed a 0.

Prometheus is firing it right now:

```
"alertname":"BackupFailed", "job":"ivgs_backup_verify", "state":"firing",
"activeAt":"2026-08-14T19:20:02.537333912Z"
```

But:

- `docker ps -a | grep -i alert` → **no Alertmanager container**
- `prometheus.yml` has **no `alerting:` block**

The alert fires into Prometheus and is delivered to nobody.

**Three independent notification paths all failed simultaneously**, which is the
real answer to "how did 75 days pass unnoticed":

| Path | Why it was silent |
|---|---|
| Celery task state | Tasks returned `{'status':'failed'}`; Celery logged success — WP-BACKUP-REPORTING §3.1 |
| GUI `backup_records` | Cron runs wrote no row — WP-BACKUP-REPORTING §3.2 |
| Prometheus `BackupFailed` | Fires correctly; no Alertmanager exists to deliver it |

The first two are fixed pending deploy. **The third is untouched, and no
scheduling choice in this package fixes it.**

### 2.6 A silent-redirect hazard in pre-flight — verified live

`/etc/fstab` mounts the target with `nofail`, so a boot with `.7` unreachable
proceeds with `/mnt/backup/ivgs` unmounted. Pre-flight tests
`[ ! -d "${BACKUP_NAS_DIR}" ]` (`backup.sh`, and `asset_backup.sh:233`) — a
**directory** test, which an empty local mountpoint passes. Backups would then be
written to the local root filesystem (261 GB free) and reported as successful.

`mountpoint /mnt/backup/ivgs` currently returns `is a mountpoint`, so this is
latent, not active. It is the same class of defect as §4: a check that cannot
distinguish "fine" from "silently wrong".

---

## 3. Where scheduling should live

| Option | For | Against |
|---|---|---|
| **A. Host cron** (status quo ante) | Host has every required tool, the GPG backup key in root's keyring, and a working env file. No broker dependency — survives Redis/beat/worker outage, which matters for DR tooling. With the row-ownership fix, cron runs now appear in the GUI. | Failure signal is a log file with `MAILTO=""` plus a Prometheus alert nobody receives. This is exactly the configuration that failed silently for 75 days. |
| **B. Celery beat in the backup worker** | Matches operator intent. After the defect-1 fix a failure is a real Celery FAILURE state. The worker container is the only environment with a *demonstrated* good run (0.565 s at 19:18). Single control plane. | Adds Redis + beat as dependencies of the backup path. Beat is a single point of failure. Requires new wiring (§3.1). |
| **C. Beat in `ivgs-celery-beat`** | Would reuse the existing beat process. | **Not viable without rework** — keyspace mismatch, §2.4. Changing that app's prefix would break every other task it schedules. |
| **D. Both cron and beat** | Redundancy. | Double runs. The loser hits the lock file and exits 2, which post-fix records a *failed* row — manufacturing exactly the false failures this work set out to remove. |

### 3.1 Recommendation — Option B, with prerequisites

Run `celery beat` against the **backup worker's own app**, inside or alongside
`ivgs-backup-worker`. That app already has the correct `global_keyprefix`, queue,
and routes (`ivgs-backup-worker/celery_app.py:83-100`), so no keyspace surgery is
needed.

Reasoning: the differentiator is not GUI visibility — the row-ownership fix gives
cron and beat identical GUI behaviour. It is that a beat-dispatched failure
produces a machine-readable Celery FAILURE, whereas cron produces a discarded
log line. Given that the alert-delivery path is broken (§2.5), the plane with the
*most* remaining signal should win.

Prerequisites, in order:

| P | Change | Why |
|---|---|---|
| P1 | Make `backup_id` optional in the three worker tasks (`backup_id: str \| None = None`). When absent, skip the pre-update and let the script's `ensure_backup_id` + `INSERT` own the row entirely. | Beat schedules static args and cannot mint a UUID per firing. The row-ownership fix from WP-BACKUP-REPORTING is what makes this possible. |
| P2 | Add beat entries to `ivgs-backup-worker/celery_app.py` — full database 02:00, assets 03:00, config 04:00 — and run the beat process. | The schedule itself. |
| P3 | Fix `POSTGRES_HOST` in `/etc/ivgs/cron-backup-env` → `192.168.1.90`. | Needed **regardless of plane** — see §3.2. |
| P4 | Remove or disable the 05:00 `verify_backup.sh` cron entry. | It runs the forbidden script daily and is failing every night. Re-enable under the separate verification WP. |
| P5 | Retire `configs/cron/backup_cron`, or rename it to what it is (a verification procedure, not a crontab). | It is documentation masquerading as config, and it misled this investigation once already. |

Option A remains defensible for the database backup alone if broker independence
is judged more valuable than the Celery failure signal. **Option D should not be
adopted.**

### 3.2 P3 is urgent independently of the plane — and lands tonight

`config_backup.sh` still runs from host cron at 04:00. Under the
WP-BACKUP-REPORTING change it now sources `scripts/lib/backup_record.sh`, whose
`POSTGRES_*` defaults are overridden by `BASH_ENV` to the broken
`POSTGRES_HOST=localhost`.

**Tonight at 04:00, `config_backup.sh` will archive successfully but fail to
write its `backup_records` row**, log `backup_record: could not open
backup_records row` to stderr, and emit `record_write=failed`. Not fatal — the
failure policy is working as designed — but the row the operator expects will not
appear, and the cause will be P3, not the change.

Fixing `POSTGRES_HOST` before 04:00 avoids that entirely.

---

## 4. Fifth instance of the swallow-failure pattern

Recorded here and in `WP-00-SWALLOWED-FAILURES_2026-08-14.md`.

```
ivgs-workers/tasks/pipeline_orchestrator.py:620-623
    """Daily backup verification. Stub for Phase 5."""
    logger.info("backup_verification_started")
    return {"status": "ok", "message": "Backup verification — stub (Phase 10)"}
```

Scheduled daily at 05:00 by `ivgs-workers/celery_app.py:202-205`. It reports
`status: "ok"` having performed no verification, and Celery records SUCCESS. A
dashboard keyed on this task shows a green daily verification that has never
verified anything. Worse than the other four instances: those swallow a real
failure, this one manufactures a success.

---

## 5. Proposed exit-gate procedure

The gate is *observed*, not inferred. Nothing below is claimed until run.

1. Apply P3; confirm `pg_isready -h $POSTGRES_HOST` from a cron-equivalent shell.
2. Deploy WP-BACKUP-REPORTING: rebuild the backup-worker image, recreate with
   `--no-deps` (CLAUDE.md §6), rebuild the frontend.
3. Apply P1 + P2; start beat.
4. Wait for one unattended 02:00 and 03:00 cycle — **do not trigger manually**;
   a manual trigger tests the API path, not the schedule.
5. Confirm, in this order:
   - `/mnt/backup/ivgs/db/<date>/` and `/mnt/backup/ivgs/assets/<date>/` contain
     the expected artifacts, with non-zero size and a matching checksum file
   - `backup_records` has one `full_database` and one `asset_backup` row for the
     date, both `status = 'completed'`
   - the GUI at `/admin/backups` shows both as completed with a plausible
     duration
   - the Celery task states are SUCCESS
   - `ivgs_backup_last_status{backup_type="database"}` is 1 in the pushgateway
6. Then, as a negative test, break one input deliberately (revert `POSTGRES_HOST`)
   and confirm the run appears as **failed** in the GUI and FAILURE in Celery.
   A gate that only proves the success path is half a gate.

Step 6 matters most: the whole failure of this subsystem was that the unhappy
path was invisible.

---

## 6. Open questions for the operator

| # | Question | Recommendation |
|---|---|---|
| Q1 | Option A, B, or D? | **B**, per §3.1 |
| Q2 | Apply P3 before 04:00 tonight? | Yes — §3.2 |
| Q3 | Disable the 05:00 `verify_backup.sh` cron entry now? | Yes — it runs a forbidden script and fails nightly |
| Q4 | Alertmanager / alert delivery — this WP, or its own? | **Its own WP, and higher priority than this one.** Neither plane produces a delivered alert without it |
| Q5 | Harden pre-flight to test `mountpoint` rather than `-d`? | Yes, but as part of the verification WP, not here |

---

*End of pass 1. No code written. Pass 2 to follow once Q1–Q5 are answered.*

---
---

# PASS 2 — Option B implemented, database half proven, asset half blocked

**Appended:** 2026-08-14
**Operator decision:** Q1 = Option B. Q2 = apply P3. Q3 = 05:00 verify disabled (operator did this). Q4 = alerting promoted to its own WP.

## 7. What was done

### 7.1 P3 — `POSTGRES_HOST` (the root cause)

`/etc/ivgs/cron-backup-env`: `export POSTGRES_HOST=localhost` →
`192.168.1.90`. Backup taken first at
`/etc/ivgs/cron-backup-env.bak-20260814-2040`. Only that line changed; the file
holds a password and was never printed.

**Verified live**, in a reconstructed cron environment
(`env -i BASH_ENV=/etc/ivgs/cron-backup-env … bash`):

```
POSTGRES_HOST as cron sees it: 192.168.1.90
192.168.1.90:5432 - accepting connections     pg_isready exit=0
select count(*) from backup_records  ->  13   exit=0
```

The second check matters more than the first: it is the exact credential path
`scripts/lib/backup_record.sh` uses, so tonight's 04:00 `config_backup.sh` will
write its row. Before the fix it would have logged `could not open
backup_records row` and emitted `record_write=failed`.

Crontab state confirmed before touching anything: `backup.sh` (02:00) and
`asset_backup.sh` (03:00) are gone, `verify_backup.sh` (05:00) is
`#DISABLED-2026-08-14`, `config_backup.sh` (04:00) is **still active** — so the
04:00 deadline was real.

### 7.2 P1 — `backup_id` optional

`ivgs-backup-worker/tasks/backup_tasks.py`. The three backup tasks take
`backup_id: Optional[str] = None`. Two conventions:

- **given** (API path) — task updates that row as a backstop, unchanged;
- **omitted** (beat path) — task writes nothing to `backup_records`; the script
  mints its own UUID and owns the row end to end. The task reads the id back off
  the script's stdout (`effective_id`) so the Celery result still identifies the
  row.

`_run_backup_script` omits `--backup-id` entirely when None. This is only
possible because of the row-ownership change in WP-BACKUP-REPORTING.

### 7.3 P2 — beat in the backup worker's own app

`ivgs-backup-worker/celery_app.py` gains `BEAT_SCHEDULE` and
`beat_schedule_filename=/tmp/ivgs-backup-celerybeat-schedule`.
`ivgs-backup-worker/Dockerfile` CMD gains `--beat`.

Embedded beat rather than a second container: this service runs exactly one
replica, so the usual objection (beat cannot scale past one process) is the
requirement here — a second scheduler would double-fire every backup. It also
keeps the scheduler in the only container whose app carries the
`ivgs_backup_` keyprefix the worker consumes under.

`config_backup` is deliberately **not** in beat. It still runs from host cron at
04:00, and scheduling it in both planes would double-fire, with the loser hitting
the lock file and recording a spurious failure. Single plane *per job*, not a
single plane overall.

## 8. Verification — observed

| # | Observation | Result |
|---|---|---|
| S1 | `docker exec ivgs-backup-worker grep -c BackupTaskError /app/tasks/backup_tasks.py` | **17** — the operator's gate, passed after each of three rebuilds |
| S2 | Postgres during three `--force-recreate --no-deps` cycles | `Up 4 hours (healthy)` throughout — `--no-deps` held |
| S3 | Beat schedule read from the **running** process | `full-database-backup \| run_full_database_backup \| <crontab: 0 2 * * *> \| queue=backup` |
| S4 | Beat state file | `/tmp/ivgs-backup-celerybeat-schedule`, 16384 bytes, owned `ivgs` |
| S5 | **Beat actually fires** — temporary 12-second schedule in a throwaway module, shipped 02:00 entry untouched | `Scheduler: Sending due task proof-db-backup` ×2 |
| S6 | **Worker consumed them and the script owned the row** | `succeeded in 0.617s: {'backup_id': 'a12e15bb…', 'status': 'completed', 'size_bytes': 600900}` — beat passed no id; that UUID was minted by `backup.sh` |
| S7 | Rows for the beat-dispatched runs | `completed`, durations 0.51 s and 0.51 s |

S5–S6 are the database half of the exit gate, proven rather than argued. The
throwaway module and its state file were deleted afterwards.

Compose invocation was derived from labels per CLAUDE.md §6, not guessed:

```
com.docker.compose.project.config_files =
  /opt/ivgs/ivgs-infra/docker-compose.node01.yml,
  /opt/ivgs/ivgs-infra/docker-compose.override.node01.yml,
  /opt/ivgs/ivgs-infra/docker-compose.monitoring.yml
```

## 9. Exit gate — half met

> a database backup and an asset backup both run unattended and appear in the
> GUI as completed

| Half | State |
|---|---|
| Database | **Met in mechanism** (S5–S7). Unattended firing at 02:00 not yet observed — that needs the clock |
| Asset | **Blocked.** See §D1 |

### D1 — asset backup cannot run inside the worker container

`asset_backup.sh` reads four host paths. **Verified live — all four are missing
inside `ivgs-backup-worker`:**

```
/var/lib/docker/volumes/ivgs-infra_seaweedfs-volume-data/_data   MISSING   (7.1 G on host)
/var/lib/docker/volumes/ivgs-infra_seaweedfs-filer-data/_data    MISSING
/var/lib/docker/volumes/ivgs-infra_seaweedfs-master-data/_data   MISSING
/mnt/ivgs-shared                                                 MISSING   (45 G on host)
```

The container mounts only `/var/log/ivgs`, `docker.sock`, `/var/run/ivgs`,
`/opt/ivgs/scripts`, `/mnt/backup` and the GPG keyring. From host cron the script
ran as root with native access; from the worker it has none.

**This is a gap in my own pass-1 analysis.** §3.1 recommended Option B for both
jobs without checking the worker's mounts against the asset script's sources. The
operator chose Option B on that recommendation.

A beat entry for `run_asset_backup` was therefore **not shipped** — it would fail
every night at 03:00, manufacturing exactly the false failures this work exists
to remove. The omission is documented in `celery_app.py` at the schedule.

Permissions were checked so the options are concrete: the three `_data`
directories are `drwxr-xr-x root:root` with `-rw-r--r--` contents, and
`/mnt/ivgs-shared` is owned by uid 999. **Read-only bind mounts would be
readable by the container.**

| Option | For | Against |
|---|---|---|
| **D1-a** — add the four paths as `:ro` mounts to `backup-worker`, then add the 03:00 beat entry | Single plane for both jobs, as intended. Verified readable | Bind-mounts Docker's internal volume tree into a container. That container already has `docker.sock` (root-on-host), so marginal risk is small — but it is still a security decision, and mine to propose, not to take |
| **D1-b** — restore the 03:00 `asset_backup.sh` host cron entry | No container changes. Runs as root where the data natively is. No double-fire risk: db is beat-only, assets are cron-only | Two planes. Reverses an operator decision from this morning, so it needs the operator's word |

**Recommendation: D1-b.** The constraint is real and physical — the asset data
lives on the host, and the backup should run where the data is. D1-a moves 52 GB
of source paths into a container purely to satisfy a scheduling preference.
"Single plane per job" already holds under D1-b, and the double-fire hazard that
motivated single-plane does not apply to two different jobs.

Either way the exit gate needs one more operator decision before it can close.

## 10. Open items

| # | Item | Owner |
|---|---|---|
| S-O1 | **Decide D1-a or D1-b.** The asset half of the exit gate is blocked on it | operator |
| S-O2 | Observe the unattended 02:00 firing and confirm the row | tomorrow |
| S-O3 | Nothing is committed. `scripts/lib/` is staged; everything else is unstaged | operator |
| S-O4 | Four doc files changed at 19:22 and 20:25 by someone else. Do not sweep them into this commit | operator |
| S-O5 | New defect found while verifying (see §11) | open |
| S-O6 | `configs/cron/backup_cron` is still a verification procedure masquerading as a crontab (P5, unactioned) | open |

## 11. New defect found during verification

`sha256sum -c` against the NAS copy **fails**, and the reason is not corruption:

```
stored:       81081b19abf8348d0b538db4d801e3cce988f89b15415101f6fda6abe687dda4
path in file: /tmp/ivgs-backup/2026-08-14/ivgs_backup.sql.gz.gpg   <- staging path
actual:       81081b19abf8348d0b538db4d801e3cce988f89b15415101f6fda6abe687dda4
RESULT: hash MATCHES - only the recorded path is wrong
```

`backup.sh`'s `compute_checksum` writes `sha256sum "${ENCRYPTED_FILE}"`, an
absolute path into the *staging* directory. Rsynced to the NAS, the file names a
path that does not exist there, so the checksum cannot be verified in place.

**The dumps are intact.** Only the recorded path is wrong, and the worker's
durability check reads `split()[0]` so it is unaffected.

This is very likely the true root of the historical verification failures — the
May rows carry exactly `sha256sum: /tmp/ivgs-backup/2026-05-29/…: No such file
or directory` — and of C4 in the reporting package ("verify_backup.sh reads the
staging directory"). It may be `backup.sh` writing a staging path rather than
`verify_backup.sh` looking in the wrong place.

Not fixed: outside both this package's scope and the ordered step list. The
one-line shape of a fix is a `cd` to the staging directory and a relative
filename, so the checksum file is portable. **Recommend this leads the
verification work package**, since it may resolve it outright.

*End of pass 2.*
