#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — Daily Database Backup Script
# =============================================================================
# Spec reference: §14.1 Table 14-1 — Backup Schedule (Row 1: Full database)
#
# Schedule: Daily at 02:00 (via cron — see configs/cron/backup_cron)
# Method:   pg_dump → gzip → GPG encrypt → rsync to NAS
# Target:   /mnt/backup/ivgs/db/YYYY-MM-DD/
# Retention: 30 days
#
# Environment variables required:
#   POSTGRES_HOST       — PostgreSQL host (default: localhost)
#   POSTGRES_PORT       — PostgreSQL port (default: 5432)
#   POSTGRES_USER       — PostgreSQL user (default: ivgs)
#   POSTGRES_PASSWORD   — PostgreSQL password (required)
#   POSTGRES_DB         — Database name (default: ivgs)
#   BACKUP_GPG_RECIPIENT — GPG key ID or email for encryption (required)
#   BACKUP_DIR          — Local staging directory (default: /tmp/ivgs-backup)
#   BACKUP_NAS_DIR      — NAS target directory (default: /mnt/backup/ivgs/db)
#   BACKUP_RETENTION_DAYS — Days to retain backups (default: 30)
#   PROMETHEUS_PUSHGATEWAY — Pushgateway URL (default: http://localhost:9091)
#
# Exit codes:
#   0 — Success
#   1 — Missing required environment variable
#   2 — Lock file exists (another backup running)
#   3 — Insufficient disk space
#   4 — pg_dump failed
#   5 — GPG encryption failed
#   6 — rsync to NAS failed
#   7 — Retention cleanup failed
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
# Supported flags (all optional):
#   --backup-id=<uuid>  Backup ID supplied by API caller. Recorded in metadata
#                       and emitted on stdout so API can correlate. If absent,
#                       cron invocations use the date-based timestamp.
#
# On success, the script emits to STDOUT in addition to its JSON log file:
#   backup_id=<uuid-or-date>
#   size_bytes=<int>
#   backup_path=<host-path>
#   checksum=<sha256>
# These KEY=VALUE lines are parsed by the API's _parse_backup_size and the
# backup.py response builder. They must NOT contain spaces or extra fields.

BACKUP_ID=""
for arg in "$@"; do
    case "$arg" in
        --backup-id=*)  BACKUP_ID="${arg#--backup-id=}" ;;
        --help|-h)
            echo "Usage: $0 [--backup-id=<uuid>]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--backup-id=<uuid>]" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Configuration with defaults
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly TIMESTAMP="$(date +%Y-%m-%d)"
readonly DATETIME="$(date +%Y-%m-%dT%H:%M:%S%z)"
readonly LOCK_FILE="/var/run/ivgs/backup.lock"
readonly LOG_FILE="/var/log/ivgs/backup.log"
readonly LOG_DIR="/var/log/ivgs"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ivgs}"
POSTGRES_DB="${POSTGRES_DB:-ivgs}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/ivgs-backup}"
BACKUP_NAS_DIR="${BACKUP_NAS_DIR:-/mnt/backup/ivgs/db}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://localhost:9091}"
MIN_DISK_SPACE_MB="${MIN_DISK_SPACE_MB:-5120}"

readonly DUMP_FILE="${BACKUP_DIR}/${TIMESTAMP}/ivgs_backup.sql"
readonly COMPRESSED_FILE="${DUMP_FILE}.gz"
readonly ENCRYPTED_FILE="${COMPRESSED_FILE}.gpg"
readonly CHECKSUM_FILE="${BACKUP_DIR}/${TIMESTAMP}/ivgs_backup.sha256"
readonly NAS_TARGET="${BACKUP_NAS_DIR}/${TIMESTAMP}/"
readonly RECORD_FILE="${BACKUP_DIR}/${TIMESTAMP}/backup_record.json"

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------
log_json() {
    local level="$1"
    local message="$2"
    local extra="${3:-}"
    [ -z "${extra}" ] && extra='{}'
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"

    mkdir -p "${LOG_DIR}"
    # Self-permissive log file: created world-writable so that
    # both cron (root) and the backup-worker container (UID 999)
    # can append. Idempotent via the chmod-after-touch.
    touch "${LOG_FILE}" 2>/dev/null || true
    chmod 666 "${LOG_FILE}" 2>/dev/null || true

    local entry
    entry=$(cat <<EOF
{"timestamp":"${timestamp}","level":"${level}","service":"backup","script":"${SCRIPT_NAME}","message":"${message}","backup_date":"${TIMESTAMP}","extra":${extra}}
EOF
    )
    echo "${entry}" >> "${LOG_FILE}"
    if [ "${level}" = "ERROR" ] || [ "${level}" = "WARN" ]; then
        echo "${entry}" >&2
    else
        echo "${entry}"
    fi
}

log_info()  { log_json "INFO"  "$1" "${2-}"; }
log_warn()  { log_json "WARN"  "$1" "${2-}"; }
log_error() { log_json "ERROR" "$1" "${2-}"; }

# ---------------------------------------------------------------------------
# Prometheus metric push
# ---------------------------------------------------------------------------
push_metric() {
    local metric_name="$1"
    local metric_value="$2"
    local metric_type="${3:-gauge}"
    local labels="${4:-}"

    if [ -n "${labels}" ]; then
        labels="{${labels}}"
    fi

    cat <<EOF | curl --silent --max-time 10 --data-binary @- \
        "${PROMETHEUS_PUSHGATEWAY}/metrics/job/ivgs_backup/instance/node-01" 2>/dev/null || true
# TYPE ${metric_name} ${metric_type}
${metric_name}${labels} ${metric_value}
EOF
}

push_backup_status() {
    local status="$1"  # 1=success, 0=failure
    local duration="$2"
    local size_bytes="${3:-0}"

    push_metric "ivgs_backup_last_status" "${status}" "gauge" "backup_type=\"database\",target_path=\"${BACKUP_NAS_DIR}\",node=\"node-01\""
    push_metric "ivgs_backup_last_timestamp" "$(date +%s)" "gauge" "backup_type=\"database\""
    push_metric "ivgs_backup_duration_seconds" "${duration}" "gauge" "backup_type=\"database\""
    push_metric "ivgs_backup_size_bytes" "${size_bytes}" "gauge" "backup_type=\"database\""
}

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
cleanup() {
    local exit_code=$?
    rm -f "${LOCK_FILE}" 2>/dev/null || true
    if [ ${exit_code} -ne 0 ]; then
        log_error "Backup failed with exit code ${exit_code}"
        push_backup_status 0 0 0
    fi
    exit ${exit_code}
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight_checks() {
    log_info "Starting pre-flight checks"

    # Required environment variables
    if [ -z "${POSTGRES_PASSWORD:-}" ]; then
        log_error "POSTGRES_PASSWORD is not set"
        exit 1
    fi
    if [ -z "${BACKUP_GPG_RECIPIENT:-}" ]; then
        log_error "BACKUP_GPG_RECIPIENT is not set"
        exit 1
    fi

    # Lock file check (prevent concurrent runs)
    if [ -f "${LOCK_FILE}" ]; then
        local lock_pid
        lock_pid="$(cat "${LOCK_FILE}" 2>/dev/null || echo "unknown")"
        if kill -0 "${lock_pid}" 2>/dev/null; then
            log_error "Another backup is running (PID: ${lock_pid})" \
                "{\"lock_file\":\"${LOCK_FILE}\",\"lock_pid\":\"${lock_pid}\"}"
            exit 2
        else
            log_warn "Stale lock file found, removing" \
                "{\"lock_file\":\"${LOCK_FILE}\",\"stale_pid\":\"${lock_pid}\"}"
            rm -f "${LOCK_FILE}"
        fi
    fi
    echo $$ > "${LOCK_FILE}"

    # Required tools
    for cmd in pg_dump gpg rsync gzip sha256sum curl; do
        if ! command -v "${cmd}" &>/dev/null; then
            log_error "Required command not found: ${cmd}"
            exit 1
        fi
    done

    # GPG key availability
    if ! gpg --list-keys "${BACKUP_GPG_RECIPIENT}" &>/dev/null; then
        log_error "GPG key not found for recipient: ${BACKUP_GPG_RECIPIENT}"
        exit 1
    fi

    # Disk space check on staging directory
    mkdir -p "${BACKUP_DIR}"
    local available_mb
    available_mb="$(df -BM "${BACKUP_DIR}" | awk 'NR==2 {print $4}' | tr -d 'M')"
    if [ "${available_mb}" -lt "${MIN_DISK_SPACE_MB}" ]; then
        log_error "Insufficient disk space" \
            "{\"available_mb\":${available_mb},\"required_mb\":${MIN_DISK_SPACE_MB}}"
        exit 3
    fi

    # NAS mount check
    if [ ! -d "${BACKUP_NAS_DIR}" ]; then
        log_error "NAS backup directory not available: ${BACKUP_NAS_DIR}"
        exit 6
    fi

    # PostgreSQL connectivity
    if ! PGPASSWORD="${POSTGRES_PASSWORD}" pg_isready \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" &>/dev/null; then
        log_error "Cannot connect to PostgreSQL" \
            "{\"host\":\"${POSTGRES_HOST}\",\"port\":${POSTGRES_PORT}}"
        exit 4
    fi

    log_info "Pre-flight checks passed"
}

# ---------------------------------------------------------------------------
# Database dump
# ---------------------------------------------------------------------------
perform_dump() {
    log_info "Starting pg_dump" \
        "{\"host\":\"${POSTGRES_HOST}\",\"database\":\"${POSTGRES_DB}\"}"

    mkdir -p "${BACKUP_DIR}/${TIMESTAMP}"

    local dump_start
    dump_start="$(date +%s)"

    # pg_dump is invoked INSIDE the ivgs-postgres container so the dump tool's
    # version matches the server version (host's pg_dump may be older — e.g.
    # Ubuntu 24.04 ships pg_dump 16, server is 17). Stdout streams back to host
    # and we redirect to DUMP_FILE.
    # Inside the container, connect to 127.0.0.1 (loopback) since the postgres
    # process is in the same network namespace.
    docker exec \
        -e PGPASSWORD="${POSTGRES_PASSWORD}" \
        ivgs-postgres \
        pg_dump \
            --host=127.0.0.1 \
            --port=5432 \
            --username="${POSTGRES_USER}" \
            --dbname="${POSTGRES_DB}" \
            --format=plain \
            --verbose \
            --no-owner \
            --no-privileges \
            --clean \
            --if-exists \
            --create \
            --encoding=UTF8 \
        > "${DUMP_FILE}" \
        2>> "${LOG_FILE}"

    local dump_end
    dump_end="$(date +%s)"
    local dump_duration=$(( dump_end - dump_start ))
    local dump_size
    dump_size="$(stat -c%s "${DUMP_FILE}" 2>/dev/null || echo 0)"

    log_info "pg_dump completed" \
        "{\"duration_seconds\":${dump_duration},\"size_bytes\":${dump_size}}"
}

# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------
compress_dump() {
    log_info "Compressing dump with gzip"

    gzip --best --force "${DUMP_FILE}"

    local compressed_size
    compressed_size="$(stat -c%s "${COMPRESSED_FILE}" 2>/dev/null || echo 0)"

    log_info "Compression completed" \
        "{\"compressed_size_bytes\":${compressed_size}}"
}

# ---------------------------------------------------------------------------
# GPG encryption
# ---------------------------------------------------------------------------
encrypt_dump() {
    log_info "Encrypting with GPG" \
        "{\"recipient\":\"${BACKUP_GPG_RECIPIENT}\"}"

    gpg --batch --yes --trust-model always \
        --recipient "${BACKUP_GPG_RECIPIENT}" \
        --output "${ENCRYPTED_FILE}" \
        --encrypt "${COMPRESSED_FILE}"

    if [ ! -f "${ENCRYPTED_FILE}" ]; then
        log_error "GPG encryption produced no output file"
        exit 5
    fi

    # Remove unencrypted compressed file
    rm -f "${COMPRESSED_FILE}"

    local encrypted_size
    encrypted_size="$(stat -c%s "${ENCRYPTED_FILE}" 2>/dev/null || echo 0)"

    log_info "Encryption completed" \
        "{\"encrypted_size_bytes\":${encrypted_size}}"
}

# ---------------------------------------------------------------------------
# SHA-256 checksum
# ---------------------------------------------------------------------------
# Global used by compute_checksum to return the hash to the caller.
# (Stdout-as-return-value would be polluted by log_info's stdout writes.)
COMPUTED_CHECKSUM=""

compute_checksum() {
    log_info "Computing SHA-256 checksum"

    sha256sum "${ENCRYPTED_FILE}" > "${CHECKSUM_FILE}"

    local checksum
    checksum="$(awk '{print $1}' "${CHECKSUM_FILE}")"

    log_info "Checksum computed" \
        "{\"sha256\":\"${checksum}\"}"

    COMPUTED_CHECKSUM="${checksum}"
}

# ---------------------------------------------------------------------------
# Row count capture (for verification — §14.2)
# ---------------------------------------------------------------------------
capture_row_counts() {
    log_info "Capturing row counts for verification"

    local row_counts
    row_counts=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -t -A -F',' \
        -c "SELECT schemaname || '.' || relname AS table_name,
                   n_live_tup AS row_count
            FROM pg_stat_user_tables
            ORDER BY schemaname, relname;" 2>/dev/null)

    # Write backup record JSON
    local total_tables
    total_tables="$(echo "${row_counts}" | wc -l)"
    local total_rows
    total_rows="$(echo "${row_counts}" | awk -F',' '{sum+=$2} END {print sum+0}')"

    cat > "${RECORD_FILE}" <<RECORD_EOF
{
    "backup_date": "${TIMESTAMP}",
    "backup_timestamp": "${DATETIME}",
    "database": "${POSTGRES_DB}",
    "host": "${POSTGRES_HOST}",
    "total_tables": ${total_tables},
    "total_rows": ${total_rows},
    "checksum_file": "${CHECKSUM_FILE}",
    "encrypted_file": "ivgs_backup.sql.gz.gpg",
    "row_counts": {
$(echo "${row_counts}" | awk -F',' '{printf "        \"%s\": %s", $1, $2; if (NR>0) printf ",\n"}' | sed '$ s/,$//')
    }
}
RECORD_EOF

    log_info "Row counts captured" \
        "{\"total_tables\":${total_tables},\"total_rows\":${total_rows}}"
}

# ---------------------------------------------------------------------------
# Rsync to NAS
# ---------------------------------------------------------------------------
sync_to_nas() {
    log_info "Syncing backup to NAS" \
        "{\"target\":\"${NAS_TARGET}\"}"

    mkdir -p "${NAS_TARGET}"

    rsync --archive --compress --checksum --progress \
        "${BACKUP_DIR}/${TIMESTAMP}/" \
        "${NAS_TARGET}" \
        2>> "${LOG_FILE}"

    if [ $? -ne 0 ]; then
        log_error "rsync to NAS failed"
        exit 6
    fi

    log_info "NAS sync completed"
}

# ---------------------------------------------------------------------------
# Retention cleanup (30 days per Table 14-1)
# ---------------------------------------------------------------------------
cleanup_old_backups() {
    log_info "Cleaning up backups older than ${BACKUP_RETENTION_DAYS} days"

    local deleted_count=0

    # Clean local staging
    if [ -d "${BACKUP_DIR}" ]; then
        while IFS= read -r -d '' dir; do
            log_info "Removing old local backup: ${dir}"
            rm -rf "${dir}"
            ((deleted_count++)) || true
        done < <(find "${BACKUP_DIR}" -maxdepth 1 -mindepth 1 -type d \
            -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)
    fi

    # Clean NAS
    if [ -d "${BACKUP_NAS_DIR}" ]; then
        while IFS= read -r -d '' dir; do
            log_info "Removing old NAS backup: ${dir}"
            rm -rf "${dir}"
            ((deleted_count++)) || true
        done < <(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d \
            -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)
    fi

    log_info "Retention cleanup completed" \
        "{\"deleted_count\":${deleted_count},\"retention_days\":${BACKUP_RETENTION_DAYS}}"
}

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
main() {
    local start_time
    start_time="$(date +%s)"

    log_info "=== IVGS v5 Daily Database Backup Starting ===" \
        "{\"backup_date\":\"${TIMESTAMP}\"}"

    preflight_checks
    perform_dump
    compress_dump
    encrypt_dump
    compute_checksum
    local checksum="${COMPUTED_CHECKSUM}"
    capture_row_counts
    sync_to_nas
    cleanup_old_backups

    local end_time
    end_time="$(date +%s)"
    local duration=$(( end_time - start_time ))
    local backup_size
    backup_size="$(stat -c%s "${ENCRYPTED_FILE}" 2>/dev/null || echo 0)"

    push_backup_status 1 "${duration}" "${backup_size}"

    log_info "=== IVGS v5 Daily Database Backup Completed Successfully ===" \
        "{\"duration_seconds\":${duration},\"backup_size_bytes\":${backup_size},\"checksum\":\"${checksum}\"}"

    # Stream B API integration: emit KEY=VALUE lines on stdout so that the
    # FastAPI _run_backup / _parse_backup_size code can pick up the size,
    # path, and checksum without parsing the JSON log file.
    # Format is strict KEY=VALUE, one per line, no spaces in values.
    local effective_id="${BACKUP_ID:-${TIMESTAMP}}"
    echo "backup_id=${effective_id}"
    echo "size_bytes=${backup_size}"
    echo "backup_path=${BACKUP_NAS_DIR}/${TIMESTAMP}"
    echo "checksum=${checksum}"
}

main "$@"
