# Recovery promise — what this system can and cannot restore

**Written 2026-08-26 by WP-57 Task 6, from measurement.** It exists because
`scripts/restore.sh` advertised a `--pit` flag and the WAL archive looked
healthy, so the recovery promise had to be inferred from two artefacts that
disagreed with each other. Inferring it during an incident is the wrong time.

---

## The short answer

**Point-in-time recovery does not exist on this system.** Recovery is
**checkpoint-only**: you restore the most recent nightly dump, and everything
written after that dump was taken is gone.

---

## Why, precisely

| | |
|---|---|
| What is backed up | `pg_dump --format=plain` — a **logical** dump (`scripts/backup.sh:310`) |
| What PITR needs | A **physical** base backup (`pg_basebackup`) |
| Does one exist? | **No.** `pg_basebackup` appears nowhere in this repository. |
| Is WAL archived? | **Yes, and it works.** 99 segments / 740 MB, `pg_stat_archiver.last_archived_time` minutes old when measured 2026-08-26. |
| Can that WAL be replayed? | **No.** Not onto a logical dump. |

This is not a configuration gap that a flag closes. WAL records **physical block
changes** keyed to LSNs inside one specific data directory. `pg_dump` emits SQL;
restoring it builds a **new cluster** with different physical layout and an
unrelated LSN timeline. There is no base to roll forward from, so
`recovery_target_time` has nothing to seek within.

## What this means for the retention windows

WP-58 recorded that WAL is kept 7 days while dumps are kept 30, and called the
pair inconsistent for PITR. That inconsistency is **moot while PITR does not
exist**: the WAL window governs nothing, because no window of WAL is replayable.

`BACKUP_RETENTION_WAL_DAYS` is therefore currently a **cost control on 740 MB of
segments that serve no recovery purpose** — not a recovery parameter. Do not
reason about it as one until a physical base backup exists.

## What you actually do in an incident

```bash
# node-01. Restores the most recent verified dump. There is no --pit.
sudo scripts/restore.sh <YYYY-MM-DD>
```

Recovery point = the instant that dump began. Expect to lose everything after it.
`--pit` now **refuses with a reason** (exit 5) rather than writing a recovery.conf
for a base backup that does not exist.

## Before you trust any of this — two live defects, 2026-08-26

1. **The database backup has been FAILING since 2026-08-24.** Two consecutive
   nights, exit 6, `NAS backup directory not available: /mnt/backup/ivgs/db`.
   The most recent restorable dump is **2026-08-23**.
2. **The cause is a stale mount inside `ivgs-backup-worker`.** Its `/proc/mounts`
   shows `/mnt/backup` as local **ext4**, not the NFS export. The container was
   started before (or across) the NFS mount, so it sees the **local directory
   shadowed underneath the mountpoint** — frozen at 2026-07-25, holding **45 GB
   of orphaned July snapshots on the root volume** that no prune can reach.

   ```
   host      /mnt/backup/ivgs/assets : 2026-08-14 … 2026-08-25   (11, on the NAS)
   container /mnt/backup/ivgs/assets : 2026-07-12 … 2026-07-25   (8, local disk)
   ```

   This is the same class `backup-failed.md` already records for postgres' WAL
   handle after a remount. **Recreating the container is what re-binds it**; a
   durable fix needs `rshared` mount propagation so a later NFS mount reaches
   containers that are already running.

Until (1) is cleared, the checkpoint-only promise above is not 23 days deep —
it is "2026-08-23 or nothing".

## The open decision

**WP-57 D-2.** Either introduce `pg_basebackup` so the archived WAL becomes
replayable and this document is rewritten around a real recovery window, or
accept checkpoint-only and stop archiving WAL. What must not continue is the
present state: an archive that is faithfully maintained, pruned on a schedule,
and cannot be restored from — which is precisely the shape of the 75-day backup
gap, where the mechanism reported health it did not have.

A physical base backup was **not** introduced by WP-57, deliberately: the package
forbids running a restore, and shipping an unrehearsed second recovery mechanism
would create a second thing nobody has proven — the same failure, one layer up.
Restore rehearsal is an operator decision to schedule, not an action to take here.
