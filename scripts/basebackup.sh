#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — WEEKLY PHYSICAL BASE BACKUP (pg_basebackup)   WP-59 Task 8
# =============================================================================
# Closes WP-57 D-2. RULED: implement PITR.
#
# WHY THIS EXISTS
# ---------------
# The WAL archive on the NAS has been faithfully maintained for months and
# COULD NOT BE REPLAYED, because there was nothing to replay it onto. WAL
# records physical block changes keyed to LSNs inside one data directory;
# `backup.sh` takes `pg_dump --format=plain`, a LOGICAL dump, and restoring one
# builds a new cluster with a different physical layout and an unrelated
# timeline. `recovery_target_time` had nothing to seek within. The archive was
# a genuine, well-kept, unusable artefact.
#
# `pg_basebackup` is the missing half: a byte-level copy of the data directory
# with the LSN the copy started at. WAL segments archived from that LSN onward
# replay onto it, and point-in-time recovery becomes a real operation rather
# than a documented aspiration.
#
# WHAT THIS IS NOT
# ----------------
# It is NOT a replacement for backup.sh. The two answer different questions:
#
#   pg_dump (nightly, 30 days)   "give me this database back, on any cluster,
#                                 at last night's 02:00"
#   pg_basebackup (weekly)       "give me this cluster back, on this major
#                                 version, at an arbitrary instant covered by
#                                 the WAL archive"
#
# A logical dump is portable across PostgreSQL major versions and selective; a
# base backup is neither, and is bound to postgres:17.2's on-disk format. Both
# are kept. Losing either loses a capability.
#
# Schedule:  Weekly. See ivgs-backup-worker/celery_app.py (WP-59) and the
#            recovery-window argument in docs/runbooks/point-in-time-recovery.md.
# Method:    pg_basebackup --format=tar --gzip --checkpoint=fast --wal-method=none
# Target:    /mnt/backup/ivgs/basebackup/YYYY-MM-DD/
# Retention: BACKUP_RETENTION_BASEBACKUP_DAYS (default 35 — argued in the runbook)
#
# Environment variables:
#   POSTGRES_HOST/PORT/USER/PASSWORD/DB    as the other backup scripts
#   BACKUP_BASEBACKUP_NAS_DIR              default /mnt/backup/ivgs/basebackup
#   BACKUP_RETENTION_BASEBACKUP_DAYS       default 35
#   PROMETHEUS_PUSHGATEWAY                 default http://localhost:9091
#   MIN_BASEBACKUP_DISK_SPACE_MB           default 2048
#
# Exit codes:
#   0 — Success
#   1 — Missing required environment variable / missing tool
#   2 — Lock file exists (another base backup running)
#   3 — Insufficient space on the NAS
#   4 — pg_basebackup failed
#   6 — Destination is not the NAS (NFS guard, WP-57 D-3)
#   7 — Retention cleanup failed
#   8 — Replication privileges are not available
#
# On success, emits KEY=VALUE lines on stdout for the calling task:
#   backup_id= size_bytes= backup_path= start_lsn= record_write=
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
BACKUP_ID=""
DRY_RUN="false"
for arg in "$@"; do
    case "$arg" in
        --backup-id=*)  BACKUP_ID="${arg#--backup-id=}" ;;
        --dry-run)      DRY_RUN="true" ;;
        --help|-h)
            echo "Usage: $0 [--backup-id=<uuid>] [--dry-run]"
            echo "  --dry-run  run every pre-flight check and report the space"
            echo "             the base backup would need, writing nothing."
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly TIMESTAMP="$(date +%Y-%m-%d)"
readonly DATETIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
readonly LOCK_FILE="/var/run/ivgs/basebackup.lock"
readonly LOG_FILE="/var/log/ivgs/basebackup.log"
readonly LOG_DIR="/var/log/ivgs"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ivgs}"
POSTGRES_DB="${POSTGRES_DB:-ivgs}"
BACKUP_NAS_DIR="${BACKUP_BASEBACKUP_NAS_DIR:-/mnt/backup/ivgs/basebackup}"
# The retention default is argued, not inherited. See the runbook: it must
# exceed the WAL retention window, or the promise is false on day one.
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_BASEBACKUP_DAYS:-35}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://localhost:9091}"
MIN_DISK_SPACE_MB="${MIN_BASEBACKUP_DISK_SPACE_MB:-2048}"

readonly TARGET_DIR="${BACKUP_NAS_DIR}/${TIMESTAMP}"

# ---------------------------------------------------------------------------
# Shared libraries
# ---------------------------------------------------------------------------
# backup_records row ownership: the SCRIPT owns the row, not the caller, so a
# cron run and an API-triggered run are equally visible. See lib/backup_record.sh.
BACKUP_RECORD_TYPE="physical_base_backup"
# shellcheck source=lib/backup_record.sh
. "${SCRIPT_DIR}/lib/backup_record.sh"

# WP-59 Task 9. Every process that writes under /mnt/backup asserts the
# destination is NFS before it writes. A new writer is exactly the case the
# guard exists for: this script did not exist when the shadowed-tree incident
# happened, and without the guard it would have been the third instance.
# shellcheck source=lib/nfs_guard.sh
. "${SCRIPT_DIR}/lib/nfs_guard.sh"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_json() {
    local level="$1" message="$2" extra="${3:-}"
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    mkdir -p "${LOG_DIR}"
    if [ -n "${extra}" ]; then
        echo "{\"timestamp\":\"${timestamp}\",\"level\":\"${level}\",\"service\":\"basebackup\",\"backup_id\":\"${BACKUP_ID:-}\",\"message\":\"${message}\",\"context\":${extra}}" >> "${LOG_FILE}"
    else
        echo "{\"timestamp\":\"${timestamp}\",\"level\":\"${level}\",\"service\":\"basebackup\",\"backup_id\":\"${BACKUP_ID:-}\",\"message\":\"${message}\"}" >> "${LOG_FILE}"
    fi
}
log_info()  { log_json "INFO"  "$1" "${2:-}"; }
log_warn()  { log_json "WARN"  "$1" "${2:-}"; }
log_error() { log_json "ERROR" "$1" "${2:-}"; echo "basebackup: $1" >&2; }

push_metric() {
    local metric_name="$1" metric_value="$2" metric_type="${3:-gauge}" labels="${4:-}"
    if [ -n "${labels}" ]; then labels="{${labels}}"; fi
    cat <<EOF | curl --silent --max-time 10 --data-binary @- \
        "${PROMETHEUS_PUSHGATEWAY}/metrics/job/ivgs_backup/instance/node-01" 2>/dev/null || true
# TYPE ${metric_name} ${metric_type}
${metric_name}${labels} ${metric_value}
EOF
}

# The BackupStale/BackupFailed alert family keys on these two names and on the
# backup_type label. Emitting `physical_base_backup` here is what extends that
# alerting to cover this job -- see ivgs-infra/configs/prometheus/alert_rules.yml,
# where a SEPARATE stale rule carries the weekly threshold, because the 26-hour
# one would page every single week for a weekly job.
push_backup_status() {
    local status="$1" duration="$2" size="$3"
    push_metric "ivgs_backup_last_status" "${status}" "gauge" \
        "backup_type=\"physical_base_backup\",target_path=\"${BACKUP_NAS_DIR}\",node=\"node-01\""
    push_metric "ivgs_backup_last_timestamp" "$(date +%s)" "gauge" \
        "backup_type=\"physical_base_backup\""
    push_metric "ivgs_backup_duration_seconds" "${duration}" "gauge" \
        "backup_type=\"physical_base_backup\""
    push_metric "ivgs_backup_size_bytes" "${size}" "gauge" \
        "backup_type=\"physical_base_backup\""
}

# ---------------------------------------------------------------------------
# Cleanup / failure trap
# ---------------------------------------------------------------------------
EXIT_CODE=0
cleanup() {
    EXIT_CODE=$?
    rm -f "${LOCK_FILE}" 2>/dev/null || true
    if [ "${EXIT_CODE}" -ne 0 ]; then
        # HONEST FAILURE. The row is marked failed and the gauge goes to 0, so
        # BackupFailed fires. This is the WP-00 rule: a task that returns a
        # failure dict while Celery records success is the defect, not the
        # reporting.
        log_error "basebackup failed with exit code ${EXIT_CODE}"
        if [ "${DRY_RUN}" != "true" ] && [ -n "${BACKUP_ID:-}" ]; then
            record_failed "${EXIT_CODE}" "${LOG_FILE}"
            push_backup_status 0 0 0
        fi
        # A partial base backup is worse than none: it looks like a base and
        # cannot be restored from. Remove it.
        if [ "${DRY_RUN}" != "true" ] && [ -d "${TARGET_DIR}" ]; then
            log_warn "removing partial base backup directory ${TARGET_DIR}"
            rm -rf "${TARGET_DIR}" 2>/dev/null || true
        fi
    fi
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
preflight() {
    log_info "Starting pre-flight checks" "{\"dry_run\":${DRY_RUN}}"

    if [ -z "${POSTGRES_PASSWORD:-}" ]; then
        log_error "POSTGRES_PASSWORD is not set"
        exit 1
    fi

    for cmd in pg_basebackup psql du find; do
        if ! command -v "${cmd}" &>/dev/null; then
            log_error "Required command not found: ${cmd}"
            exit 1
        fi
    done

    if [ "${DRY_RUN}" != "true" ]; then
        ensure_backup_id
        # Open the row before anything that can fail, exactly as backup.sh does.
        record_running
    fi

    if [ -f "${LOCK_FILE}" ]; then
        local lock_pid
        lock_pid="$(cat "${LOCK_FILE}" 2>/dev/null || echo unknown)"
        if kill -0 "${lock_pid}" 2>/dev/null; then
            log_error "Another base backup is running (PID ${lock_pid})"
            exit 2
        fi
        log_warn "Stale lock file, removing" "{\"stale_pid\":\"${lock_pid}\"}"
        rm -f "${LOCK_FILE}"
    fi
    mkdir -p "$(dirname "${LOCK_FILE}")" 2>/dev/null || true
    echo $$ > "${LOCK_FILE}"

    # --- WP-59 Task 9: the destination must BE the NAS, not merely look like it.
    # Guarded on the PARENT because BACKUP_NAS_DIR may not exist yet on a first
    # run; creating it under an absent mount is the exact failure being closed.
    local parent
    parent="$(dirname "${BACKUP_NAS_DIR}")"
    if ! assert_nfs_destination "${parent}" "physical base backup"; then
        log_error "Base backup destination parent is not an NFS mount: ${parent}" \
            "{\"guard\":\"assert_nfs_destination\",\"ledger\":\"WP-57 D-3\"}"
        exit 6
    fi
    # NOT in dry-run. "Writes nothing" has to mean nothing, including an empty
    # directory: a dry run that leaves a directory behind is a dry run that
    # changed the filesystem, and the next person to look cannot tell whether a
    # real pass ran and failed.
    if [ "${DRY_RUN}" != "true" ]; then
        mkdir -p "${BACKUP_NAS_DIR}"
    elif [ ! -d "${BACKUP_NAS_DIR}" ]; then
        log_info "Dry run: ${BACKUP_NAS_DIR} does not exist yet and would be created"
    fi

    # --- Space. A base backup is the size of the data directory, and the NAS is
    # 20 T at 1% used, so this is a sanity floor rather than a real constraint.
    local space_check_dir="${BACKUP_NAS_DIR}"
    [ -d "${space_check_dir}" ] || space_check_dir="${parent}"
    local available_mb
    available_mb="$(df -BM "${space_check_dir}" | awk 'NR==2 {print $4}' | tr -d 'M')"
    if [ "${available_mb}" -lt "${MIN_DISK_SPACE_MB}" ]; then
        log_error "Insufficient space on NAS" \
            "{\"available_mb\":${available_mb},\"required_mb\":${MIN_DISK_SPACE_MB}}"
        exit 3
    fi

    # --- Replication privilege. pg_basebackup needs a REPLICATION role and a
    # free walsender slot. Checking here turns "the weekly backup silently
    # produced nothing" into a pre-flight refusal with the reason named.
    local can_replicate
    can_replicate="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" -tAc \
        "SELECT rolreplication OR rolsuper FROM pg_roles WHERE rolname = current_user" \
        2>/dev/null || echo "")"
    if [ "${can_replicate}" != "t" ]; then
        log_error "Role '${POSTGRES_USER}' has neither REPLICATION nor SUPERUSER; pg_basebackup cannot run" \
            "{\"fix\":\"ALTER ROLE ${POSTGRES_USER} REPLICATION;\"}"
        exit 8
    fi

    local max_wal_senders
    max_wal_senders="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" -tAc "SHOW max_wal_senders" 2>/dev/null || echo 0)"
    if [ "${max_wal_senders}" -lt 1 ]; then
        log_error "max_wal_senders is ${max_wal_senders}; pg_basebackup needs at least 1" \
            "{\"fix\":\"set max_wal_senders >= 2 and restart postgres\"}"
        exit 8
    fi

    log_info "Pre-flight checks passed" \
        "{\"available_mb\":${available_mb},\"max_wal_senders\":${max_wal_senders}}"
}

# ---------------------------------------------------------------------------
# The base backup
# ---------------------------------------------------------------------------
take_base_backup() {
    local start_lsn
    start_lsn="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" -tAc "SELECT pg_current_wal_lsn()" 2>/dev/null || echo "")"

    if [ "${DRY_RUN}" = "true" ]; then
        local est_mb
        est_mb="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
            -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
            -d "${POSTGRES_DB}" -tAc \
            "SELECT (sum(pg_database_size(datname)) / 1024 / 1024)::bigint FROM pg_database" \
            2>/dev/null || echo 0)"
        echo "dry_run=true"
        echo "would_write_to=${TARGET_DIR}"
        echo "cluster_size_mb=${est_mb}"
        echo "start_lsn=${start_lsn}"
        log_info "Dry run complete — nothing written" \
            "{\"target\":\"${TARGET_DIR}\",\"cluster_size_mb\":${est_mb}}"
        return 0
    fi

    mkdir -p "${TARGET_DIR}"

    # --checkpoint=fast    : do not wait up to checkpoint_timeout to start.
    # --wal-method=none    : the WAL needed to make this base consistent is
    #                        already going to the archive via archive_command.
    #                        Bundling a second copy inside the tar would double
    #                        the storage of every segment and, worse, invite a
    #                        restore that replays the bundled WAL and stops
    #                        there -- which is a restore to the base's own
    #                        instant, not a point-in-time recovery. The archive
    #                        is the source of WAL. That is the whole design.
    # --format=tar --gzip  : one file per tablespace, portable across the NFS
    #                        mount without preserving thousands of small files.
    # --progress -v        : progress lands in the log, so a slow run is
    #                        distinguishable from a stuck one.
    log_info "Starting pg_basebackup" "{\"target\":\"${TARGET_DIR}\",\"start_lsn\":\"${start_lsn}\"}"
    if ! PGPASSWORD="${POSTGRES_PASSWORD}" pg_basebackup \
            --host="${POSTGRES_HOST}" --port="${POSTGRES_PORT}" \
            --username="${POSTGRES_USER}" \
            --pgdata="${TARGET_DIR}" \
            --format=tar --gzip --compress=6 \
            --checkpoint=fast \
            --wal-method=none \
            --progress --verbose \
            --no-password \
            >> "${LOG_FILE}" 2>&1; then
        log_error "pg_basebackup failed — see ${LOG_FILE}"
        exit 4
    fi

    local end_lsn
    end_lsn="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" -tAc "SELECT pg_current_wal_lsn()" 2>/dev/null || echo "")"

    # The manifest is what a restore reads to know which WAL it needs. Written
    # beside the tars rather than into a database, because the moment it is
    # needed the database is the thing that is gone.
    cat > "${TARGET_DIR}/basebackup_record.json" <<JSON
{
  "backup_id": "${BACKUP_ID}",
  "backup_type": "physical_base_backup",
  "taken_at": "${DATETIME}",
  "postgres_host": "${POSTGRES_HOST}",
  "start_lsn": "${start_lsn}",
  "end_lsn": "${end_lsn}",
  "wal_method": "none",
  "wal_archive_dir": "${WAL_ARCHIVE_DIR:-/mnt/backup/ivgs/wal}",
  "format": "tar.gz",
  "note": "WAL for recovery comes from the archive, not from this directory. Recovery beyond this base requires an unbroken segment run from start_lsn forward."
}
JSON

    echo "start_lsn=${start_lsn}"
    log_info "pg_basebackup completed" \
        "{\"start_lsn\":\"${start_lsn}\",\"end_lsn\":\"${end_lsn}\"}"
}

# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
cleanup_old_basebackups() {
    if [ "${DRY_RUN}" = "true" ]; then return 0; fi

    # Guarded again. A prune that runs against a shadowed local tree deletes
    # nothing on the NAS while reporting a retention pass -- or, if the local
    # tree happens to hold copies, deletes the wrong ones.
    if ! assert_nfs_destination "${BACKUP_NAS_DIR}" "base backup (retention)"; then
        log_error "Skipping base-backup retention: ${BACKUP_NAS_DIR} is not an NFS mount"
        return 0
    fi

    # NEVER prune the last surviving base. A retention rule that can leave the
    # WAL archive with nothing to replay onto reintroduces the exact condition
    # this script was written to remove. The rule is: delete only what is BOTH
    # older than the window AND not the newest.
    local total
    total="$(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d | wc -l)"
    if [ "${total}" -le 1 ]; then
        log_info "Retention: only ${total} base backup present; keeping it"
        return 0
    fi

    local newest
    newest="$(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' \
        | sort -rn | head -1 | cut -d' ' -f2-)"

    local deleted=0
    while IFS= read -r -d '' dir; do
        if [ "${dir}" = "${newest}" ]; then
            log_warn "Retention: newest base backup is older than the window; keeping it anyway" \
                "{\"dir\":\"${dir}\",\"retention_days\":${BACKUP_RETENTION_DAYS}}"
            continue
        fi
        log_info "Removing expired base backup: ${dir}"
        rm -rf "${dir}"
        deleted=$((deleted + 1))
    done < <(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d \
        -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)

    log_info "Base-backup retention completed" \
        "{\"deleted\":${deleted},\"retention_days\":${BACKUP_RETENTION_DAYS}}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local start_time
    start_time="$(date +%s)"

    preflight
    take_base_backup
    cleanup_old_basebackups

    if [ "${DRY_RUN}" = "true" ]; then
        echo "record_write=skipped"
        return 0
    fi

    local end_time duration size
    end_time="$(date +%s)"
    duration=$(( end_time - start_time ))
    size="$(du -sb "${TARGET_DIR}" 2>/dev/null | awk '{print $1}' || echo 0)"

    record_completed "${size}" "${TARGET_DIR}"
    push_backup_status 1 "${duration}" "${size}"

    echo "backup_id=${BACKUP_ID}"
    echo "size_bytes=${size}"
    echo "backup_path=${TARGET_DIR}"
    echo "record_write=${RECORD_WRITE}"

    log_info "Base backup completed" \
        "{\"duration_seconds\":${duration},\"size_bytes\":${size},\"path\":\"${TARGET_DIR}\"}"
}

main
