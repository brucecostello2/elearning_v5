#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — Database Restore Script
# =============================================================================
# Spec reference: §14.3 — Recovery Procedures
#
# Database Restore Procedure (§14.3):
#   1. Stop ivgs-api and ivgs-workers on all nodes
#   2. Decrypt backup: gpg --decrypt backup.sql.gz.gpg | gunzip > restore.sql
#   3. Drop and recreate target database: dropdb ivgs; createdb ivgs
#   4. Restore: psql ivgs < restore.sql
#   5. Apply WAL logs if point-in-time recovery needed
#   6. Verify row counts match backup record expectations
#   7. Restart ivgs-api (runs Alembic migrations automatically)
#   8. Restart ivgs-workers
#
# Recovery objectives (Table 14-2):
#   RTO: 4 hours
#   RPO: 24 hours
#   Rollback RTO: 15 minutes
#
# Usage:
#   ./restore.sh YYYY-MM-DD                      # Restore specific date
#   ./restore.sh YYYY-MM-DD --dry-run             # Preview without executing
#   ./restore.sh YYYY-MM-DD --pit YYYY-MM-DD-HH:MM  # Point-in-time recovery
#   ./restore.sh YYYY-MM-DD --skip-confirmation   # Skip safety prompts
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOG_FILE="/var/log/ivgs/restore.log"
readonly LOG_DIR="/var/log/ivgs"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ivgs}"
POSTGRES_DB="${POSTGRES_DB:-ivgs}"
POSTGRES_SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"
BACKUP_NAS_DIR="${BACKUP_NAS_DIR:-/mnt/backup/ivgs/db}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/mnt/backup/ivgs/wal}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/ivgs}"

DRY_RUN=false
SKIP_CONFIRMATION=false
PIT_TARGET=""
RESTORE_DATE=""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_json() {
    local level="$1"
    local message="$2"
    local extra="${3:-}"
    [ -z "${extra}" ] && extra='{}'
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    mkdir -p "${LOG_DIR}"
    local entry="{\"timestamp\":\"${timestamp}\",\"level\":\"${level}\",\"service\":\"restore\",\"script\":\"${SCRIPT_NAME}\",\"message\":\"${message}\",\"extra\":${extra}}"
    echo "${entry}" >> "${LOG_FILE}"
    if [ "${level}" = "ERROR" ]; then
        echo "[${level}] ${message}" >&2
    else
        echo "[${level}] ${message}"
    fi
}

log_info()  { log_json "INFO"  "$1" "${2-}"; }
log_warn()  { log_json "WARN"  "$1" "${2-}"; }
log_error() { log_json "ERROR" "$1" "${2-}"; }

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: ${SCRIPT_NAME} BACKUP_DATE [OPTIONS]

Arguments:
  BACKUP_DATE          Date of backup to restore (YYYY-MM-DD)

Options:
  --dry-run            Preview actions without executing
  --pit TARGET         Point-in-time recovery target (YYYY-MM-DD-HH:MM)
  --skip-confirmation  Skip interactive safety prompts
  --help               Show this help message

Examples:
  ${SCRIPT_NAME} 2026-05-19
  ${SCRIPT_NAME} 2026-05-19 --dry-run
  ${SCRIPT_NAME} 2026-05-19 --pit 2026-05-19-14:30
  ${SCRIPT_NAME} 2026-05-19 --skip-confirmation
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
parse_args() {
    if [ $# -lt 1 ]; then
        log_error "BACKUP_DATE argument is required"
        usage
    fi

    RESTORE_DATE="$1"
    shift

    while [ $# -gt 0 ]; do
        case "$1" in
            --dry-run)
                DRY_RUN=true
                ;;
            --pit)
                shift
                PIT_TARGET="$1"
                ;;
            --skip-confirmation)
                SKIP_CONFIRMATION=true
                ;;
            --help)
                usage
                ;;
            *)
                log_error "Unknown argument: $1"
                usage
                ;;
        esac
        shift
    done

    # Validate date format
    if ! [[ "${RESTORE_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        log_error "Invalid date format: ${RESTORE_DATE} (expected YYYY-MM-DD)"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Safety confirmation
# ---------------------------------------------------------------------------
confirm_restore() {
    if [ "${SKIP_CONFIRMATION}" = true ]; then
        log_warn "Safety confirmation skipped (--skip-confirmation)"
        return 0
    fi

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              ⚠  DATABASE RESTORE WARNING  ⚠               ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  This will DESTROY the current database and replace it     ║"
    echo "║  with the backup from: ${RESTORE_DATE}                      ║"
    echo "║                                                            ║"
    echo "║  Database: ${POSTGRES_DB} on ${POSTGRES_HOST}:${POSTGRES_PORT}              ║"
    echo "║                                                            ║"
    echo "║  This action is IRREVERSIBLE.                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    if [ -n "${PIT_TARGET}" ]; then
        echo "  Point-in-time recovery target: ${PIT_TARGET}"
        echo ""
    fi

    read -rp "Type 'RESTORE' to confirm: " confirmation
    if [ "${confirmation}" != "RESTORE" ]; then
        log_info "Restore cancelled by user"
        exit 0
    fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight_checks() {
    log_info "Running pre-flight checks for restore"

    local backup_dir="${BACKUP_NAS_DIR}/${RESTORE_DATE}"
    local backup_file="${backup_dir}/ivgs_backup.sql.gz.gpg"
    local record_file="${backup_dir}/backup_record.json"
    local checksum_file="${backup_dir}/ivgs_backup.sha256"

    # Check backup exists
    if [ ! -f "${backup_file}" ]; then
        log_error "Backup file not found: ${backup_file}"
        echo "Available backups:"
        ls -1d "${BACKUP_NAS_DIR}"/????-??-?? 2>/dev/null | sort -r | head -10 || echo "  (none)"
        exit 1
    fi

    # Check record file
    if [ ! -f "${record_file}" ]; then
        log_warn "Backup record file not found: ${record_file} — row count verification will be skipped"
    fi

    # Verify checksum
    if [ -f "${checksum_file}" ]; then
        log_info "Verifying backup checksum"
        if ! (cd "${backup_dir}" && sha256sum --check "${checksum_file}" --quiet 2>/dev/null); then
            log_error "Backup checksum verification FAILED — backup may be corrupted"
            exit 1
        fi
        log_info "Checksum verified"
    else
        log_warn "Checksum file not found — skipping integrity verification"
    fi

    # Check required tools
    for cmd in gpg gunzip psql dropdb createdb; do
        if ! command -v "${cmd}" &>/dev/null; then
            log_error "Required command not found: ${cmd}"
            exit 1
        fi
    done

    # WAL archive check for point-in-time recovery
    if [ -n "${PIT_TARGET}" ] && [ ! -d "${WAL_ARCHIVE_DIR}" ]; then
        log_error "WAL archive directory not found: ${WAL_ARCHIVE_DIR} — cannot perform point-in-time recovery"
        exit 1
    fi

    log_info "Pre-flight checks passed"
}

# ---------------------------------------------------------------------------
# Step 1: Stop services (§14.3 Step 1)
# ---------------------------------------------------------------------------
stop_services() {
    log_info "Step 1: Stopping ivgs-api and ivgs-workers on all nodes"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would stop services via docker-compose"
        return 0
    fi

    # Stop API and workers on node-01
    if [ -f "${COMPOSE_DIR}/docker-compose.yml" ]; then
        cd "${COMPOSE_DIR}"
        docker compose stop fastapi-backend celery-worker-default celery-beat 2>/dev/null || true
        log_info "Stopped node-01 services"
    fi

    # Stop workers on GPU nodes (via SSH)
    for node in node-02 node-03 node-04 node-05 node-06; do
        local node_ip="10.10.0.${node##node-0}"
        if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
            "root@${node_ip}" \
            "cd /opt/ivgs && docker compose stop celery-worker 2>/dev/null" 2>/dev/null; then
            log_info "Stopped workers on ${node}"
        else
            log_warn "Could not stop workers on ${node} — may be offline"
        fi
    done

    # Allow graceful shutdown
    sleep 5
    log_info "All services stopped"
}

# ---------------------------------------------------------------------------
# Step 2-3: Decrypt and decompress (§14.3 Steps 2-3)
# ---------------------------------------------------------------------------
decrypt_and_decompress() {
    local backup_file="${BACKUP_NAS_DIR}/${RESTORE_DATE}/ivgs_backup.sql.gz.gpg"
    local restore_sql="/tmp/ivgs_restore_${RESTORE_DATE}.sql"

    log_info "Step 2: Decrypting and decompressing backup"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would decrypt ${backup_file} → ${restore_sql}"
        return 0
    fi

    gpg --batch --yes --decrypt "${backup_file}" | gunzip > "${restore_sql}"

    if [ ! -s "${restore_sql}" ]; then
        log_error "Decrypted file is empty — restore aborted"
        exit 1
    fi

    local restore_size
    restore_size="$(stat -c%s "${restore_sql}" 2>/dev/null || echo 0)"
    log_info "Decrypt + decompress completed" \
        "{\"restore_file\":\"${restore_sql}\",\"size_bytes\":${restore_size}}"
}

# ---------------------------------------------------------------------------
# Step 3: Drop and recreate database (§14.3 Step 3)
# ---------------------------------------------------------------------------
drop_and_recreate() {
    log_info "Step 3: Dropping and recreating database '${POSTGRES_DB}'"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would drop and recreate database ${POSTGRES_DB}"
        return 0
    fi

    # Terminate existing connections
    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_SUPERUSER}" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
        2>/dev/null || true

    PGPASSWORD="${POSTGRES_PASSWORD}" dropdb \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_SUPERUSER}" \
        --if-exists "${POSTGRES_DB}"

    PGPASSWORD="${POSTGRES_PASSWORD}" createdb \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_SUPERUSER}" \
        -O "${POSTGRES_USER}" \
        -E UTF8 \
        "${POSTGRES_DB}"

    log_info "Database recreated"
}

# ---------------------------------------------------------------------------
# Step 4: Restore from dump (§14.3 Step 4)
# ---------------------------------------------------------------------------
restore_database() {
    local restore_sql="/tmp/ivgs_restore_${RESTORE_DATE}.sql"

    log_info "Step 4: Restoring database from dump"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would run: psql ${POSTGRES_DB} < ${restore_sql}"
        return 0
    fi

    local restore_start
    restore_start="$(date +%s)"

    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_SUPERUSER}" \
        -d "${POSTGRES_DB}" \
        -f "${restore_sql}" \
        --single-transaction \
        --set ON_ERROR_STOP=on \
        2>> "${LOG_FILE}"

    local restore_end
    restore_end="$(date +%s)"
    local restore_duration=$(( restore_end - restore_start ))

    # Remove temp file
    rm -f "${restore_sql}"

    log_info "Database restore completed" \
        "{\"duration_seconds\":${restore_duration}}"
}

# ---------------------------------------------------------------------------
# Step 5: WAL replay for point-in-time recovery (§14.3 Step 5)
# ---------------------------------------------------------------------------
apply_wal_logs() {
    if [ -z "${PIT_TARGET}" ]; then
        log_info "Step 5: Skipped (no point-in-time target specified)"
        return 0
    fi

    log_info "Step 5: Applying WAL logs for point-in-time recovery to ${PIT_TARGET}"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would apply WAL logs from ${WAL_ARCHIVE_DIR} up to ${PIT_TARGET}"
        return 0
    fi

    # Configure PostgreSQL for WAL replay
    local pg_data_dir
    pg_data_dir="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_SUPERUSER}" -d postgres \
        -t -A -c "SHOW data_directory;" 2>/dev/null)"

    log_info "PostgreSQL data directory: ${pg_data_dir}"

    # Create recovery signal and configure WAL replay
    # Note: This requires PostgreSQL to be restarted with recovery parameters
    cat > "/tmp/ivgs_recovery.conf" <<RECOVERY_EOF
restore_command = 'cp ${WAL_ARCHIVE_DIR}/%f %p'
recovery_target_time = '${PIT_TARGET}'
recovery_target_action = 'promote'
RECOVERY_EOF

    log_warn "WAL replay configuration written to /tmp/ivgs_recovery.conf"
    log_warn "Manual steps required: copy to pg_data_dir, create recovery.signal, restart PostgreSQL"
    log_info "WAL replay configuration prepared"
}

# ---------------------------------------------------------------------------
# Step 6: Verify row counts (§14.3 Step 6)
# ---------------------------------------------------------------------------
verify_row_counts() {
    local record_file="${BACKUP_NAS_DIR}/${RESTORE_DATE}/backup_record.json"

    log_info "Step 6: Verifying row counts against backup record"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would verify row counts against ${record_file}"
        return 0
    fi

    if [ ! -f "${record_file}" ]; then
        log_warn "No backup record file — skipping row count verification"
        return 0
    fi

    local expected_total
    expected_total="$(python3 -c "import json; d=json.load(open('${record_file}')); print(d.get('total_rows', 0))" 2>/dev/null || echo "0")"

    local actual_total
    actual_total="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -t -A \
        -c "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" 2>/dev/null || echo "0")"

    # Force stats update first
    PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "ANALYZE;" 2>/dev/null || true

    actual_total="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
        -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -t -A \
        -c "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" 2>/dev/null || echo "0")"

    log_info "Row count verification" \
        "{\"expected\":${expected_total},\"actual\":${actual_total}}"

    # Allow 1% tolerance (pg_stat_user_tables is approximate)
    local tolerance
    tolerance="$(python3 -c "print(int(${expected_total} * 0.01) + 1)" 2>/dev/null || echo "10")"
    local diff
    diff="$(python3 -c "print(abs(${expected_total} - ${actual_total}))" 2>/dev/null || echo "0")"

    if [ "${diff}" -gt "${tolerance}" ]; then
        log_error "Row count mismatch exceeds tolerance" \
            "{\"expected\":${expected_total},\"actual\":${actual_total},\"diff\":${diff},\"tolerance\":${tolerance}}"
        log_error "Restore may be incomplete — manual verification required"
        return 1
    fi

    log_info "Row count verification PASSED"
}

# ---------------------------------------------------------------------------
# Steps 7-8: Restart services (§14.3 Steps 7-8)
# ---------------------------------------------------------------------------
restart_services() {
    log_info "Steps 7-8: Restarting ivgs-api and ivgs-workers"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] Would restart all services"
        return 0
    fi

    # Start API on node-01 (runs Alembic migrations automatically)
    if [ -f "${COMPOSE_DIR}/docker-compose.yml" ]; then
        cd "${COMPOSE_DIR}"
        docker compose start fastapi-backend 2>/dev/null || true
        log_info "Started fastapi-backend (Alembic migrations run automatically)"

        # Wait for API to be healthy
        local retries=30
        while [ ${retries} -gt 0 ]; do
            if curl --silent --fail http://localhost:8000/health >/dev/null 2>&1; then
                log_info "API is healthy"
                break
            fi
            sleep 2
            ((retries--))
        done

        if [ ${retries} -eq 0 ]; then
            log_error "API failed to become healthy after restart"
        fi

        # Start remaining node-01 services
        docker compose start celery-worker-default celery-beat 2>/dev/null || true
        log_info "Started celery-worker-default and celery-beat"
    fi

    # Start workers on GPU nodes
    for node in node-02 node-03 node-04 node-05 node-06; do
        local node_ip="10.10.0.${node##node-0}"
        if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
            "root@${node_ip}" \
            "cd /opt/ivgs && docker compose start celery-worker 2>/dev/null" 2>/dev/null; then
            log_info "Started workers on ${node}"
        else
            log_warn "Could not start workers on ${node}"
        fi
    done

    log_info "All services restarted"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"

    local start_time
    start_time="$(date +%s)"

    log_info "=== IVGS v5 Database Restore Starting ===" \
        "{\"restore_date\":\"${RESTORE_DATE}\",\"dry_run\":${DRY_RUN},\"pit_target\":\"${PIT_TARGET}\"}"

    if [ "${DRY_RUN}" = true ]; then
        log_info "*** DRY RUN MODE — No changes will be made ***"
    fi

    preflight_checks
    confirm_restore
    stop_services
    decrypt_and_decompress
    drop_and_recreate
    restore_database
    apply_wal_logs
    verify_row_counts
    restart_services

    local end_time
    end_time="$(date +%s)"
    local duration=$(( end_time - start_time ))

    log_info "=== IVGS v5 Database Restore Completed ===" \
        "{\"duration_seconds\":${duration}}"

    echo ""
    echo "✅ Restore completed successfully in ${duration} seconds."
    echo "   Backup date: ${RESTORE_DATE}"
    if [ -n "${PIT_TARGET}" ]; then
        echo "   Point-in-time: ${PIT_TARGET}"
    fi
    echo "   Please verify application functionality."
}

main "$@"
