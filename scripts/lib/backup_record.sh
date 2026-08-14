# =============================================================================
# IVGS v5 — backup_records row ownership (shared by the backup scripts)
# =============================================================================
# Sourced by backup.sh, asset_backup.sh and config_backup.sh.  Not executable
# on its own.
#
# Why the script owns the row, not the Celery task
# ------------------------------------------------
# The row used to be written exclusively by ivgs-backup-worker's task bodies.
# That made the GUI blind to any run the worker did not start: a cron
# invocation, or a direct `docker exec ivgs-backup-worker /scripts/backup.sh`,
# produced a real encrypted dump on the NAS with no backup_records row behind
# it.  On 2026-08-14 the table held 13 rows for a system nominally backing up
# daily, and /mnt/backup/ivgs/db/ held exactly one dated directory.
#
# Moving the write here makes the row a property of the run rather than of the
# caller.  Every path is covered, and the coupling is one-way: the script needs
# no knowledge of who invoked it.
#
# When the API pre-creates a row it passes --backup-id, and record_running's
# INSERT no-ops through ON CONFLICT so the API's started_at survives.
#
# Failure policy
# --------------
# A row-write failure must not fail an otherwise good backup — the encrypted
# dump on the NAS is worth more than its bookkeeping — but it must not be
# silent either.  RECORD_WRITE flips to "failed" and the reason goes to stderr;
# callers emit record_write= on stdout and the worker raises on it.  This is
# deliberately NOT the "return a failure value and hope someone checks it"
# pattern that this change exists to remove.
#
# Contract for the sourcing script
# --------------------------------
#   BACKUP_ID           must be set to a UUID before any call
#   BACKUP_RECORD_TYPE  one of the backup_type enum values:
#                       full_database | wal_archive | asset_backup |
#                       config_backup | vm_snapshot
#   POSTGRES_*          read from the environment; defaults below match the
#                       other IVGS scripts
# =============================================================================

BACKUP_RECORD_HOST="${POSTGRES_HOST:-localhost}"
BACKUP_RECORD_PORT="${POSTGRES_PORT:-5432}"
BACKUP_RECORD_USER="${POSTGRES_USER:-ivgs}"
BACKUP_RECORD_DB="${POSTGRES_DB:-ivgs}"

# "ok" until proven otherwise.
RECORD_WRITE="ok"

# Self-contained logging: the three sourcing scripts do not agree on a logging
# API (backup.sh and asset_backup.sh have log_error, config_backup.sh has
# log_entry), so this library depends on neither.
_record_warn() {
    echo "backup_record: $1 (backup_id=${BACKUP_ID:-unset})" >&2
}

_psql_record() {
    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
        -h "${BACKUP_RECORD_HOST}" -p "${BACKUP_RECORD_PORT}" \
        -U "${BACKUP_RECORD_USER}" -d "${BACKUP_RECORD_DB}" \
        -v ON_ERROR_STOP=1 -q -t -A -c "$1" >/dev/null 2>&1
}

# Open the row.  Call as early as the script can manage — before the lock file,
# before disk and mount checks — so that a run which dies in pre-flight is
# still visible.  The lock-file "Permission denied" failures of 2026-08-14 were
# recorded only on the API path, because only the API had a row by then.
record_running() {
    local rc=0
    _psql_record "INSERT INTO backup_records
                      (id, backup_type, status, started_at)
                  VALUES ('${BACKUP_ID}'::uuid,
                          '${BACKUP_RECORD_TYPE}', 'running', now())
                  ON CONFLICT (id) DO NOTHING;" || rc=$?
    if [ "${rc}" -ne 0 ]; then
        RECORD_WRITE="failed"
        _record_warn "could not open backup_records row (status=running)"
    fi
}

# Close the row on success.
record_completed() {
    local size="$1"
    local path="$2"
    local rc=0
    _psql_record "UPDATE backup_records
                  SET status = 'completed',
                      size_bytes = ${size},
                      backup_path = '${path}',
                      completed_at = now()
                  WHERE id = '${BACKUP_ID}'::uuid;" || rc=$?
    if [ "${rc}" -ne 0 ]; then
        RECORD_WRITE="failed"
        _record_warn "could not close backup_records row (status=completed)"
    fi
}

# Close the row on failure.  Call from the EXIT trap.
#
# completed_at is COALESCEd, never assigned: a row that already carries a real
# completion time must keep it.  Overwriting it with now() on rows started
# months earlier is what produced the 110,502-minute durations in the GUI,
# which derives duration as completed_at - started_at.
record_failed() {
    local exit_code="$1"
    local logref="${2:-/var/log/ivgs/backup.log}"
    _psql_record "UPDATE backup_records
                  SET status = 'failed',
                      error_message = left(
                          'exited ${exit_code}; see ${logref}', 2000),
                      completed_at = COALESCE(completed_at, now())
                  WHERE id = '${BACKUP_ID}'::uuid;" || true
}

# Assign a UUID when the caller did not supply one, so cron and direct
# `docker exec` runs key a row exactly as API-triggered runs do.  The previous
# fallback was the date string, which is not a UUID and could never key a row.
ensure_backup_id() {
    if [ -z "${BACKUP_ID:-}" ]; then
        BACKUP_ID="$(uuidgen 2>/dev/null \
            || cat /proc/sys/kernel/random/uuid 2>/dev/null \
            || echo "")"
    fi
}
