# Runbook — BackupFailed / BackupStale

Referenced by the `runbook:` annotation on both alerts in
`ivgs-infra/configs/prometheus/alert_rules.yml`. Until 2026-08-14 that
annotation pointed at a file that did not exist.

**Node:** node-01 (192.168.1.90) unless stated otherwise.

---

## Which alert fired?

The two are deliberately different questions. Answer this first — it changes
everything below.

| Alert | Means | Expression |
|---|---|---|
| **BackupFailed** | A backup **ran and failed** | `ivgs_backup_last_status == 0` |
| **BackupStale** | A backup **did not run at all** for >26 h | `time() - ivgs_backup_last_timestamp > 93600` |

`BackupStale` inhibits `BackupFailed` for the same `backup_type` — if a backup
is not running, a stale failure status is noise on top of the larger fact.

---

## First: is it real?

Both alerts are driven by the **pushgateway**, whose values persist until
overwritten. Check the database row, which is the authoritative record and is
written by every invocation path (cron, `docker exec`, worker, beat):

```
# RUN ON: node-01
docker exec ivgs-postgres psql -U ivgs -d ivgs -c \
  "select backup_type,status,started_at,completed_at,verified_at
   from backup_records order by started_at desc limit 10;"
```

A `completed` or `verified` row inside the last day means the backup itself is
fine and the alert is about the metric, not the backup.

Then check the artifact — **exit 0 is not proof**:

```
ls -la /mnt/backup/ivgs/db/$(date +%Y-%m-%d)/
cd /mnt/backup/ivgs/db/$(date +%Y-%m-%d) && sha256sum -c ivgs_backup.sha256
```

---

## BackupStale — the backup is not running

Which scheduler owns the job? **There are two, deliberately** — see
`docs/deployment/runbook.md` §5.1.

| Job | Scheduled by | Check |
|---|---|---|
| Database, 02:00 | **Celery beat**, in the backup worker | `docker exec ivgs-backup-worker python -c "from celery_app import celery_app; print(celery_app.conf.beat_schedule)"` |
| Assets, 03:00 | **host cron** | `sudo crontab -l` |
| Config, 04:00 | **host cron** | `sudo crontab -l` |

```
docker logs ivgs-backup-worker --since 24h | grep -E "beat|run_full_database_backup"
sudo tail -20 /var/log/ivgs/asset_backup-cron.log
```

**Known cause, 2026-05-29 → 2026-08-14.** `POSTGRES_HOST=localhost` in
`/etc/ivgs/cron-backup-env`, while Postgres publishes on `192.168.1.90:5432`
only. `pg_isready` failed in pre-flight, `backup.sh` exited 4 before producing
anything, and 75 days passed with no database backup. If this recurs:

```
sudo grep '^export POSTGRES_HOST=' /etc/ivgs/cron-backup-env   # expect 192.168.1.90
pg_isready -h 192.168.1.90 -p 5432
```

---

## BackupFailed — a backup ran and failed

```
sudo tail -40 /var/log/ivgs/backup.*.log
docker logs ivgs-backup-worker --since 24h | grep -A5 BackupTaskError
```

The Celery task **raises** on failure as of `55ead2a`, so a failed backup is
task state FAILURE. If Celery says SUCCESS, the task is not the one that failed.

| Exit code | Meaning | Action |
|---|---|---|
| 1 | Missing env var / GPG key absent | Check `BACKUP_GPG_RECIPIENT` and the keyring |
| 2 | Lock held by another run | `ls -l /var/run/ivgs/*.lock`; a stale lock from a killed run is removed automatically only if the PID is dead |
| 3 | Insufficient disk space | `df -h /mnt/backup/ivgs` |
| 4 | Cannot reach Postgres | See the `POSTGRES_HOST` note above |
| 5 | GPG encryption produced no output | `gpg --list-keys "$BACKUP_GPG_RECIPIENT"` |
| 6 | NAS unavailable / rsync failed | `mountpoint /mnt/backup/ivgs` — see the mount trap below |
| 7 | Retention cleanup failed | Non-fatal to the dump itself |

---

## Verification failures

`verify_backup.sh` is safe to run and is scheduled at 05:00.

```
sudo /opt/ivgs/scripts/verify_backup.sh $(date +%Y-%m-%d)
```

A failed verification **does not** mean the backup failed. It writes
`error_message` on the row and leaves `status` and `completed_at` alone; the
Celery task raises. Check whether the dump is actually bad before treating it
as data loss — the historical failures through 2026-08-14 were all caused by
the checksum file recording an absolute *staging* path, with the dumps intact.

---

## Two traps that make this alert lie

**1. A remount orphans containers.** A bind mount does not follow a remount of
its source. On 2026-08-14 the `.9`→`.7` migration left `ivgs-postgres` holding a
dead handle: WAL archiving reported `archived_count = 0` / `failed_count = 24`
while `/mnt/backup/ivgs/wal/` looked populated from the host. After any remount
of `/mnt/backup/ivgs`, recreate every container that bind-mounts it:

```
docker exec ivgs-postgres sh -c 'ls /mnt/wal-archive >/dev/null && echo OK || echo BROKEN'
docker exec ivgs-postgres psql -U ivgs -d ivgs -c "select * from pg_stat_archiver;"
```

**2. Pre-flight tests a directory, not a mountpoint.** `/etc/fstab` uses
`nofail`, so a boot with the NAS unreachable leaves an empty local directory
that passes the `-d` check — backups then land on the local disk and report
success. Confirm with `mountpoint /mnt/backup/ivgs`.

---

## Escalation

If the dump is genuinely lost, `RECOVERY.md` covers restore. Note the
outstanding gap: **no IVGS restore drill has been run against `.7`**, and the
GPG private key still sits in `_keys/` on the backup share alongside the
ciphertext it protects.
