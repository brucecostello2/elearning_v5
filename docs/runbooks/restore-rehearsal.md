# Restore rehearsal — the procedure, so the next one is a paste

**Written 2026-08-26 by WP-59 Task 10, closing WP-57 D-5.** The
checkpoint-only recovery promise was *inferred* from reading `backup.sh` and had
never been demonstrated. Nobody on this system had restored a backup. This
document exists so that the next rehearsal is a paste rather than a design, and
so that the numbers it produces are comparable to the last one's.

---

## Do this

```bash
# node-01. Rehearses the most recent dump. Takes about two seconds today.
cd /opt/ivgs
./scripts/restore_rehearsal.sh
```

```bash
# A specific dump instead of the most recent:
./scripts/restore_rehearsal.sh 2026-08-23

# Leave the scratch cluster up to poke at it (remember to remove it after):
./scripts/restore_rehearsal.sh --keep
docker rm -f ivgs-restore-rehearsal
```

**Cadence: monthly, and after any change to `backup.sh`, `restore.sh` or the
PostgreSQL major version.** A rehearsal that is only run when someone
remembers is the same as no rehearsal — it will not have been run recently on
the day it matters.

---

## The isolation mechanism, stated explicitly

The live database is not touched in any step, and the mechanism is **not
discipline**. It is a **separate PostgreSQL cluster**:

* a throwaway `postgres:17.2` container with its own `PGDATA` on its own
  temporary directory, its own postmaster and its own shared buffers;
* **no published port** — it is reachable only through `docker exec`, so
  nothing outside the docker host can address it at all;
* it is never given the live cluster's socket, data directory or port.

The only thing the script does to the live cluster is four `SELECT count(*)`
statements, for the comparison table. There is no code path in it that can
write to the live database.

It also runs `--memory=512m --memory-swap=512m`, the same ceiling
`verify_backup.sh` uses. node-01 is a 16 GB VM whose Proxmox host has OOM-killed
it before (`dev/CLAUDE.md` §7); a rehearsal must not be able to take the node
down.

### Why that isolation is load-bearing rather than belt-and-braces

`backup.sh` runs `pg_dump ... --clean --if-exists --create`. Line 22 of the
plaintext of **every dump this system has ever taken** is:

```sql
DROP DATABASE IF EXISTS ivgs;
```

followed by `CREATE DATABASE ivgs` and `\connect ivgs`.

**Feeding that file to `psql` destroys the live database regardless of what
`-d` names on the command line** — the `\connect` inside the file overrides it.
A rehearsal that restored "into a new database" on the live cluster would have
been the single most destructive thing anyone could run here.

So the script does three things, not one:

1. runs in a **different cluster**;
2. **filters** everything up to and including `\connect` out of the dump, which
   turns it into "restore these objects into whatever database I am connected
   to";
3. **gates the filter** — it greps the filtered file for `DROP DATABASE`,
   `CREATE DATABASE` and `\connect`, and exits 5 without starting anything if
   any survived. A comment claiming the filter works would not be evidence; the
   grep is.

After the restore it asserts `SELECT current_database()` equals
`ivgs_restore_rehearsal`, because a restore that silently landed somewhere else
is exactly the failure the isolation exists to prevent.

---

## Reading the output

```
table                        restored         live      delta
------------------------ ------------ ------------ ----------
projects                           15           17         +2
storyboard_scenes                  32           58        +26
assets                             45          160       +115
render_jobs                        17           40        +23
```

* **A positive delta is expected.** It is live growth since the dump was taken.
  Confirm the size is plausible for the elapsed time; a project count that
  jumped by 200 in three days is worth a question of its own.
* **A negative delta needs explaining before the rehearsal counts.** It means
  the restore produced rows the live database does not have — a restore of the
  wrong dump, or rows deleted from live since. Either way, stop and find out.
* **`ERR` in a column** means the table does not exist in one of the two. On the
  restored side that is a failed restore; on the live side it is a migration
  applied after the dump was taken. Check `alembic_version` in both.

Add tables to compare with `REHEARSAL_TABLES="projects users assets" ./scripts/restore_rehearsal.sh`.

---

## Recorded results

Keep appending. The point of a table like this is the trend: a restore time
that has grown tenfold is a fact worth knowing before an incident, not during
one.

| Date | Dump rehearsed | SQL size | Decrypt | Cluster start | Restore | Total | Result |
|---|---|---|---|---|---|---|---|
| 2026-08-26 | 2026-08-23 | 5,765,913 B | 0.095 s | 1.133 s | 0.222 s | **1.450 s** | PASS — 15/32/45/17 restored, all deltas positive |

**Note the dump rehearsed is 2026-08-23, not the previous night's.** The
nightly database backup failed on 2026-08-24 and 2026-08-25 (shadowed NFS
mount, WP-57 §6.1, fixed 2026-08-26) so 2026-08-23 was the most recent dump
that existed. That is itself the reason to rehearse: the freshest restorable
point was three days older than anyone would have assumed.

**These timings are not a projection.** The IVGS database is small — 5.8 MB of
SQL, 160 asset rows — and the restore genuinely takes a fifth of a second.
Do not read 1.45 s as the recovery time objective: RTO in `docs/deployment/runbook.md`
is 4 hours and is dominated by decision-making, stopping the fleet, and
verification, not by `psql`.

---

## Rehearsing PITR

Once `scripts/basebackup.sh` has produced at least one base backup, the
point-in-time path is rehearsed the same way — into a staged cluster on port
5433, never the live one:

```bash
# node-01. Reports what it would do; writes nothing.
sudo scripts/restore.sh <YYYY-MM-DD> --pit <YYYY-MM-DD-HH:MM> --dry-run
```

The dry run checks all four preconditions (a base at or before the target, the
WAL archive present, on the NAS, and gap-free) and prints the base it selected
and the segment count. `docs/runbooks/point-in-time-recovery.md` has the full
procedure and the window argument.

**As of 2026-08-26 no base backup has been taken yet** — `basebackup.sh` ships
in this package and its first run is the operator's, in the WP-59 report's
Task 8 block. Until then `--pit` refuses with precondition 1, which is the
correct answer and was verified: see the WP-59 report §Task 8.
