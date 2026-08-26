# Recovery promise — what this system can and cannot restore

**Written 2026-08-26 by WP-57 Task 6, from measurement. REWRITTEN the same day
by WP-59 Task 8, after the operator ruled D-2: implement PITR.** It exists
because `scripts/restore.sh` advertised a `--pit` flag and the WAL archive
looked healthy, so the recovery promise had to be inferred from two artefacts
that disagreed with each other. Inferring it during an incident is the wrong
time.

---

## The short answer

Two recovery capabilities, and they are different from each other. Know which
one you want before you start.

| | Logical restore | Point-in-time recovery |
|---|---|---|
| **Recovers to** | the instant last night's dump began | any instant covered by the WAL archive |
| **From** | `pg_dump` (`scripts/backup.sh`), nightly 02:00, kept 30 days | `pg_basebackup` (`scripts/basebackup.sh`), Sunday 01:00, kept 35 days + the WAL archive |
| **Command** | `sudo scripts/restore.sh <YYYY-MM-DD>` | `sudo scripts/restore.sh <YYYY-MM-DD> --pit <YYYY-MM-DD-HH:MM>` |
| **Touches the live cluster** | **YES** — it drops and recreates `ivgs` | **NO** — it stages a separate cluster |
| **Portable across major versions** | yes | no — bound to `postgres:17.2`'s on-disk format |
| **Rehearsed?** | **yes**, `scripts/restore_rehearsal.sh`, see `restore-rehearsal.md` | preconditions rehearsed; a full replay needs a base backup to exist first |

**Keep both.** They answer different questions and losing either loses a
capability. A logical dump can be restored onto any cluster, any version, and
can be loaded selectively; a base backup can only be restored onto the same
major version, but it is the only thing archived WAL can be replayed onto.

---

## What changed, and why it could not have worked before

WP-57 established, by measurement, that PITR was impossible here:

| | |
|---|---|
| What was backed up | `pg_dump --format=plain` — a **logical** dump |
| What PITR needs | a **physical** base backup |
| Did one exist? | **No.** `pg_basebackup` appeared nowhere in the repository. |
| Was WAL archived? | **Yes, and it worked.** Live, current, faithfully pruned. |
| Could it be replayed? | **No.** Not onto a logical dump. |

This was never a configuration gap that a flag closes. WAL records **physical
block changes** keyed to LSNs inside one specific data directory. `pg_dump`
emits SQL; restoring it builds a **new cluster** with a different physical
layout and an unrelated LSN timeline. There was no base to roll forward from,
so `recovery_target_time` had nothing to seek within.

`scripts/basebackup.sh` is the missing half. It takes a byte-level copy of the
data directory, weekly, and records the LSN the copy started at. Segments
archived from that LSN forward replay onto it.

---

## The window — argued, not inherited

**This is the section to read before promising anyone a recovery point.**

A PITR promise is only as deep as the *shorter* of two windows:

1. how far back a **base backup** still exists, and
2. how far back the **WAL archive** still holds an unbroken run of segments.

The rule is: **WAL retention must cover at least the interval back to the
oldest base backup it must replay onto**, or the promise is false the day it is
written. If a base survives from 30 days ago but WAL only goes back 7, that
base is unusable — there is nothing to bridge days 8 through 30.

### The numbers, as configured

| Setting | Value | Where |
|---|---|---|
| Base backup cadence | weekly, Sunday 01:00 UTC | `ivgs-backup-worker/celery_app.py` |
| Base backup retention | **35 days** | `BACKUP_RETENTION_BASEBACKUP_DAYS`, default in `scripts/basebackup.sh` |
| WAL retention | **7 days** | `BACKUP_RETENTION_WAL_DAYS`, `ivgs-infra/.env` |
| Logical dump retention | 30 days | `BACKUP_RETENTION_DB_DAYS` |

### What that actually promises

**The PITR window is 7 days, not 35.** WAL retention is the binding
constraint, and it should be read that way rather than being quietly assumed to
be the base retention.

Working it through: a weekly base and 7-day WAL means that at the *worst* point
in the cycle — the moment just before a new base is taken — the newest base is
7 days old and the archive reaches back exactly 7 days. The two just meet.
There is no margin, and a base backup that is skipped for any reason opens a
hole immediately: the newest base becomes 14 days old while the WAL still only
reaches back 7, and days 8–14 become unrecoverable *even though a base and an
archive both exist*. That is why `BaseBackupStale` pages at 8 days — the alert
is not about tidiness, it is the tripwire on this exact gap.

**Recommendation, for the operator's decision (WP-59 D-2):** raise
`BACKUP_RETENTION_WAL_DAYS` from 7 to **10**. That gives three days of slack
over the weekly cadence, so one missed base does not open a hole, and the cost
is trivial: the archive currently holds 207 segments at 16 MB each — about 3.3
GB for 7 days — on a NAS that is 1% full of 20 T. It is not raised here because
retention is a policy number and this package's remit was to argue it, not to
change it unasked.

**Why base retention is 35 and not 7.** It is deliberately much longer than the
WAL window. A base older than the WAL window cannot be used for PITR, but it is
still a complete physical copy of the cluster and can be restored *to its own
instant* — which is a real, if coarse, recovery of last resort when the archive
itself is damaged. Five weeks of those costs almost nothing and removes a class
of total loss.

**Why `--wal-method=none`.** The base backup deliberately does NOT bundle a
copy of the WAL it needs. Bundling would double the storage of every segment,
and — worse — invites a restore that replays only the bundled WAL and stops,
which is a restore to the base's own instant rather than a point-in-time
recovery. The archive is the single source of WAL. That is the design.

---

## Doing a point-in-time recovery

```bash
# node-01. Check first: this reports what it WOULD do and writes nothing.
sudo scripts/restore.sh <YYYY-MM-DD> --pit <YYYY-MM-DD-HH:MM> --dry-run
```

`--pit` refuses, naming the reason, when any of four preconditions fails:

1. **no base backup directory** — take one: `scripts/basebackup.sh`
2. **no base at or before the target instant** — recovery replays *forward*;
   a base taken after the target cannot reach it. It lists the bases present.
3. **the WAL archive is missing, empty, or not on the NAS** — the last of
   these is the WP-57 D-3 shadowed-mount case, and replaying from a shadowed
   local tree would replay a *partial* history and stop early without an error.
4. **the WAL archive has a gap** — it names the two segments either side.
   Replay would stop at the gap and report success at an earlier instant than
   you asked for, which is the most dangerous possible outcome.

When the preconditions hold, it unpacks the base into a **staging directory**
and writes `recovery.signal` plus the two recovery GUCs into
`postgresql.auto.conf`. It then prints the commands to start that cluster on
port **5433**, alongside the live one.

**It never touches the running cluster, and it never will.** An in-place PITR
of a live database is a one-way door pressed under stress. The recovered
cluster comes up with `recovery_target_action = 'pause'`, so it stops at the
target and waits — connect to it, look at what you actually recovered, and only
then `pg_wal_replay_resume()`. Promoting automatically would end the timeline
and foreclose a second attempt at a different instant.

Cutting the application over to the recovered cluster is a separate, deliberate
act. This runbook does not automate it.

---

## Recovery from a logical dump (the everyday case)

```bash
# node-01. Restores the most recent verified dump. Rehearsed - see
# docs/runbooks/restore-rehearsal.md for the proof and the timings.
sudo scripts/restore.sh <YYYY-MM-DD>
```

Recovery point = the instant that dump began. Expect to lose everything after it.

**Know what the dump contains before you point psql at anything.** Every dump
this system takes is written with `pg_dump --clean --if-exists --create`, so
line 22 of the plaintext is:

```sql
DROP DATABASE IF EXISTS ivgs;
```

followed by `CREATE DATABASE ivgs` and `\connect ivgs`. **Feeding that file to
`psql` destroys the live database no matter what `-d` names on the command
line** — the `\connect` overrides it. `restore.sh` is built around that and is
safe; an improvised `psql < dump.sql` is not. If you need the dump restored
*beside* the live database rather than over it, use
`scripts/restore_rehearsal.sh`, which filters the cluster-level statements out
and gates the filter before running anything.

---

## Mount safety — why every backup path now checks the filesystem type

Two processes were caught writing to the **local disk shadowed underneath the
NFS mountpoint** on 2026-08-25/26: `ivgs-backup-worker` (two nights of failed
dumps) and postgres' `archive_command` (1.9 GB of WAL archived to the wrong
place). See `backup-failed.md` for the incident. WP-59 Task 9 closed it two
ways, and both are needed:

* **`scripts/lib/nfs_guard.sh`** — every process that writes under
  `/mnt/backup` asserts `stat -f` reports `nfs`/`nfs4` before it writes, and
  refuses with a recorded failure otherwise. A path check (`[ -d ... ]`) cannot
  see this: a shadowed local directory *is* a directory.
* **`propagation: rslave`** on the `/mnt/backup` and `/mnt/backup/ivgs/wal`
  binds, so a later NFS mount or remount on the host reaches containers that
  are already running instead of leaving them holding a stale inode.

`wal_archive.sh` runs the guard **before** its `mkdir -p`, which is the whole
point of the ordering: `mkdir -p` under an absent mount is what *created* the
shadowed tree. Refusing returns non-zero to `archive_command`, so PostgreSQL
keeps the segment in `pg_wal` and retries — the WAL is held on the primary,
not lost, and `pg_wal` growing is the visible pressure an operator should see
instead of a silent split archive.

---

## Preconditions, verified live 2026-08-26

| Check | Value |
|---|---|
| `wal_level` | `replica` — sufficient for physical base + PITR |
| `max_wal_senders` | 10 |
| role `ivgs` | `rolreplication = t`, `rolsuper = t` |
| `pg_basebackup` in `ivgs-backup-worker` | 17.10 (client) against 17.2 (server) |
| WAL archive | 207 segments, `000000010000000100000003` … `0000000100000001000000D1`, **no gaps** |
| NAS | 20 T, 59 G used (1%) — capacity is not a constraint |

The gap check above is not a claim; `restore.sh --pit` performs it on every run
and refuses on a gap.
