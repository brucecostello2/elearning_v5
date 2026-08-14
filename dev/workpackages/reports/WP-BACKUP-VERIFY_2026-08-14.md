# WP-BACKUP-VERIFY — Portable checksum, NAS-side compare, no 2 GB tmpfs

**Date:** 2026-08-14
**Node:** node-01 (192.168.1.90)
**Commit:** `55ea53e` (pushed)
**Status:** CLOSED. Gated both ways before the 05:00 cron entry was re-enabled.
**Origin:** §11 of `WP-BACKUP-SCHEDULE_2026-08-14.md`, confirmed independently
by the operator at 19:11

---

## 1. Findings

### 1.1 The producer wrote an unusable checksum — verified live

`backup.sh` computed `sha256sum "${ENCRYPTED_FILE}"`, recording the **absolute
staging path**:

```
5954...657dd  /tmp/ivgs-backup/2026-08-14/ivgs_backup.sql.gz.gpg
```

rsync carries that file to the NAS, where the recorded path does not exist. So
`sha256sum --check` on the NAS copy failed with *No such file or directory* on
a byte-perfect dump. Measured before the fix: the recorded hash matched the NAS
file exactly — **only the path was wrong**.

This is the true source of the historical verification failures, including the
`2026-05-29` rows whose `error_message` reads
`sha256sum: /tmp/ivgs-backup/2026-05-29/...: No such file or directory`.

### 1.2 The verifier was not, in fact, reading staging

The brief called for making `verify_backup.sh` read the NAS instead of staging.
On inspection it already did: `BACKUP_NAS_DIR` defaults to
`/mnt/backup/ivgs/db`, `BACKUP_DIR` is the NAS path, and `verify_checksum`
already wrapped its check in `cd "${BACKUP_DIR}"`.

The `cd` was correct in intent and defeated by the producer's absolute path.
**The bug was entirely in the producer**, as the operator had concluded
independently. The verifier change below is hardening, not the fix.

### 1.3 A missing checksum file was a silent pass

`verify_checksum` returned 0 with a warning when the checksum file was absent.
Verification whose only integrity check can be skipped into success is not
verification.

### 1.4 The 2 GB tmpfs — a real host risk

`--tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=2g`, i.e. up to 2 GB of
host RAM, spawned unattended at 05:00 as a sibling container through the mounted
Docker socket with nothing bounding it. node-01 was reduced to 16 GB the same
day and the Proxmox host OOM-killed the VM twice.

---

## 2. Changes

| File | Change |
|---|---|
| `scripts/backup.sh` | `compute_checksum` writes a **bare filename** computed from inside the target directory, so the checksum verifies from staging or NAS alike |
| `scripts/verify_backup.sh` | Compares hashes directly instead of `sha256sum --check`, which would resolve whatever path the file records. Works on both new bare-filename files and the older absolute-path files still on the NAS |
| `scripts/verify_backup.sh` | Missing checksum file is now a hard failure |
| `scripts/verify_backup.sh` | PGDATA on disk (`/var/tmp/ivgs-verify-pgdata-$$`) instead of tmpfs; container capped at `--memory=512m --memory-swap=512m --shm-size=128m`; EXIT trap removes the directory |

Disk was chosen over shrinking the tmpfs because `/` has ~261 GB free and the
dump is under 1 MB — there was never a reason for this to be in RAM.

---

## 3. Verification — observed

Run as root from a reconstructed cron environment (`env -i BASH_ENV=…`), i.e.
the way the 05:00 entry will invoke it.

| # | Test | Result |
|---|---|---|
| V1 | New checksum format after a fresh backup | `5954…657dd  ivgs_backup.sql.gz.gpg` — bare filename |
| V2 | **Known-good backup** | **PASSED, exit 0, 4 s** |
| V3 | Row counts inside V2 | matched **exactly**, tolerance 0 — both sides now exact counts |
| V4 | Verification block persisted to the NAS | `{"status": "passed", "timestamp": "2026-08-14T21:24:39Z", "duration_seconds": 4}` |
| V5 | **Byte-corrupted copy** (256 random bytes at offset 50000) | **FAILED, exit 1**, caught at the checksum before any restore |
| V6 | Cleanup after both runs | no temp container, no PGDATA directory, **no tmpfs mount** |
| V7 | Host memory across both runs | ~13 GB available throughout, unchanged |

V5 ran against an isolated copy under `/var/tmp` with `BACKUP_NAS_DIR`
overridden. **The NAS backup was never modified.**

V2 is the first successful end-to-end verification this system has recorded.

### 3.1 Not verified

- The 05:00 cron entry has not yet fired on its own schedule.
- Only one corruption mode was tested (payload bytes). Truncation, a corrupted
  GPG header, and a valid-but-stale dump were not exercised.
- V5 short-circuits at the checksum, so the corrupted-restore path — how the
  script behaves when a *checksum-valid* dump fails to restore — remains
  untested.

---

## 4. Cron re-enabled

The 05:00 entry was restored only after V2 and V5 both passed:

```
0 5 * * * /opt/ivgs/scripts/verify_backup.sh $(date -d "yesterday" +\%Y-\%m-\%d) >> /var/log/ivgs/verify_backup-cron.log 2>&1
```

It verifies *yesterday's* backup, which is the original design and is left
unchanged.

`CLAUDE.md` §8 and `docs/deployment/runbook.md` §5 both said "do not run
verify_backup.sh". Both are corrected, and both now record what changed and
that the script still spawns a sibling container via the Docker socket — that
part is unaltered, per instruction.

---

## 5. Follow-on defect found during this work

Fixed under WP-ALERTING rather than here, because it is an alerting fault:
`verify_backup.sh` pushed `ivgs_backup_last_status=0` on failure but never
pushed 1 on success, so a single failed verification pinned `BackupFailed`
firing permanently. See `WP-ALERTING_2026-08-14.md` pass 2.

*Closed.*
