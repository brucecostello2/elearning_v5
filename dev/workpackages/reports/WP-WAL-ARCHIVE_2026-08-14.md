# WP-WAL-ARCHIVE — Stale bind mount broke WAL archiving; container audit

**Date:** 2026-08-14
**Node:** node-01 (192.168.1.90)
**Status:** CLOSED. Both items verified live.
**Origin:** runbook §5 warning raised at the close of the previous session

---

## 1. Item 1 — WAL archiving restored

### 1.1 The fault (recorded before the fix)

`archive_mode = on`, `archive_command = /scripts/wal_archive.sh %p %f` — so
Postgres invokes the script directly, per WAL segment. **It needs no cron entry
and never did**; that open unassigned item is closed as "by design".

But it had archived nothing since 16:41. Verified before the operator's
recreate:

```
archived_count     0
failed_count       24        (30 by 21:15)
last_archived_wal  (null)
last_failed_wal    0000000100000000000000EE
stats_reset        2026-08-14 16:41:08
```

Inside `ivgs-postgres`, `/mnt/wal-archive` returned **`Host is down`** while the
same path listed 45 files normally from the host.

**Cause.** The container started 16:48 holding a bind mount of
`/mnt/backup/ivgs/wal` captured before the `.9`→`.7` remount. A bind mount does
not follow a remount of its source, so the container kept pointing at the dead
CIFS handle. The archive target did not follow the migration for Postgres even
though it did for every host-side script.

### 1.2 Closure — verified live

Operator recreated the container at 21:16:45. Confirmed after:

| Check | Result |
|---|---|
| Mount inside container | write test **RW OK** |
| `archived_count` | **0 → 3**, then 4 |
| `last_archived_wal` | `…F0`, then `…F1` |
| `last_archived_time` | `21:17:05`, then `21:20:40` — fresh |
| `last_failed_time` | `21:15:47` — **predates the recreate**; no failures since |

Not trusting the counter alone, a `pg_switch_wal()` was forced and the artifact
checked on the NAS:

```
-rw------- 16777216  21:20:40  0000000100000000000000F1
```

Full 16 MB segment, timestamp matching `last_archived_time` exactly. The
`ED…EE…EF…F0…F1` sequence is contiguous, so there is no filename gap in the
archive across the break window.

**Not verified:** the *content* validity of `…EE`, which carries a 21:01
timestamp that predates the recreate and whose provenance is not established.
The sequence is complete; whether that one segment is usable for PITR was not
tested and would only matter in a recovery to that exact point.

---

## 2. Item 2 — Container audit: no other victims

Six running containers bind-mount `/mnt/backup` or `/mnt/ivgs-shared`:

| Container | Mount | Started | Live test |
|---|---|---|---|
| ivgs-postgres | `/mnt/backup/ivgs/wal` | 21:16 | RW OK |
| ivgs-backup-worker | `/mnt/backup` | 20:57 | RW OK |
| ivgs-fastapi | `/mnt/ivgs-shared` | 16:48 | RW OK |
| ivgs-celery-composition | `/mnt/ivgs-shared` | 16:48 | RW OK |
| ivgs-celery-default | `/mnt/ivgs-shared` | 16:48 | RW OK |
| ivgs-seaweedfs-volume | `/mnt/ivgs-shared` | 16:48 | RW OK |

**Nothing needed recreating.** The four containers of the same 16:48 vintage as
the broken Postgres are unaffected for a structural reason:

```
mountpoint /mnt/ivgs-shared  ->  is not a mountpoint
```

`/mnt/ivgs-shared` is a plain directory on `/`, not a separate mount, so a
remount could not orphan it. Only `/mnt/backup/ivgs` is NFS, and the only two
containers touching it have both been recreated since the migration.

Tested by direct read/write inside each container rather than by comparing
start times against the remount — a timestamp comparison would have flagged
four false positives here.

### 2.1 Recommendation not actioned

Both NFS-touching binds use plain `rw`, i.e. default `rprivate` propagation, so
**a future remount will orphan them again in exactly the same way**. `:rslave`
would let remounts propagate into the containers.

Not applied: it requires recreating `ivgs-postgres` a second time within the
hour, on a 16 GB node the Proxmox host OOM-killed twice today, to fix a
hypothetical rather than an active fault. Recorded for the operator instead,
along with the detection command:

```
docker exec ivgs-postgres sh -c 'ls /mnt/wal-archive >/dev/null && echo OK || echo BROKEN'
```

This is now in `docs/runbooks/backup-failed.md` under "Two traps that make this
alert lie", so the next remount has a written check.

---

## 3. Evidence discipline

**Verified live:** every row of both tables above; the archiver counters before
and after; the forced `pg_switch_wal` and its resulting NAS artifact;
`mountpoint /mnt/ivgs-shared`; the per-container read/write tests.

**Inferred:** the stale-bind-mount mechanism. It is the only explanation
consistent with "host path healthy, container path `Host is down`, container
older than the remount", and the recreate fixed it — but the remount instant
was not captured, so the causal chain is reconstructed, not observed.

**Not tested:** `:rslave` propagation behaviour on this host; the content
validity of segment `…EE`.

*Closed.*
