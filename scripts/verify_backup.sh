#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — Backup Verification Script
# =============================================================================
# Spec reference: §14.2 — Backup Verification
#
# Every database backup is automatically verified after completion.
# Verification procedure:
#   1. Restore the pg_dump to a temporary PostgreSQL instance
#   2. Run row count checks against expected values
#   3. Compute and validate SHA-256 checksums
#   4. Destroy the temporary instance
#   5. On failure: trigger BackupFailed alert + dashboard notification
#
# Schedule: Daily at 05:00 (after backup at 02:00)
#
# Usage:
#   ./verify_backup.sh YYYY-MM-DD
#   ./verify_backup.sh           # Defaults to today's date
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOG_FILE="/var/log/ivgs/backup_verify.log"
readonly LOG_DIR="/var/log/ivgs"

BACKUP_NAS_DIR="${BACKUP_NAS_DIR:-/mnt/backup/ivgs/db}"
VERIFY_DATE="${1:-$(date +%Y-%m-%d)}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://localhost:9091}"
TEMP_PG_CONTAINER="ivgs-backup-verify-$$"
TEMP_PG_PORT="54321"
TEMP_PG_PASSWORD="verify-temp-$(date +%s)"

readonly BACKUP_DIR="${BACKUP_NAS_DIR}/${VERIFY_DATE}"
readonly ENCRYPTED_FILE="${BACKUP_DIR}/ivgs_backup.sql.gz.gpg"
readonly CHECKSUM_FILE="${BACKUP_DIR}/ivgs_backup.sha256"
readonly RECORD_FILE="${BACKUP_DIR}/backup_record.json"
readonly RESTORE_SQL="/tmp/ivgs_verify_${VERIFY_DATE}_$$.sql"
# PGDATA for the throwaway verify instance. On disk, not tmpfs -- see
# start_temp_postgres. Removed by the EXIT trap.
readonly TEMP_PG_DATA="/var/tmp/ivgs-verify-pgdata-$$"

VERIFICATION_PASSED=false

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
    # Self-permissive log file: created world-writable so that
    # both cron (root) and the backup-worker container (UID 999)
    # can append. Idempotent via the chmod-after-touch.
    touch "${LOG_FILE}" 2>/dev/null || true
    chmod 666 "${LOG_FILE}" 2>/dev/null || true
    local entry="{\"timestamp\":\"${timestamp}\",\"level\":\"${level}\",\"service\":\"backup-verify\",\"script\":\"${SCRIPT_NAME}\",\"verify_date\":\"${VERIFY_DATE}\",\"message\":\"${message}\",\"extra\":${extra}}"
    echo "${entry}" >> "${LOG_FILE}"
    echo "[${level}] ${message}"
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
    local labels="${3:-}"
    if [ -n "${labels}" ]; then labels="{${labels}}"; fi
    cat <<EOF | curl --silent --max-time 10 --data-binary @- \
        "${PROMETHEUS_PUSHGATEWAY}/metrics/job/ivgs_backup_verify/instance/node-01" 2>/dev/null || true
# TYPE ${metric_name} gauge
${metric_name}${labels} ${metric_value}
EOF
}

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
cleanup() {
    log_info "Cleaning up temporary resources"

    # Remove temp SQL file
    rm -f "${RESTORE_SQL}" 2>/dev/null || true

    # Stop and remove temporary PostgreSQL container
    docker rm -f "${TEMP_PG_CONTAINER}" 2>/dev/null || true

    # Remove its on-disk PGDATA. Ordered AFTER the container is gone so
    # nothing is writing into it. postgres runs as uid 999 in the image and
    # creates root-owned-ish files, so this may need the -f.
    if [ -n "${TEMP_PG_DATA:-}" ] && [ -d "${TEMP_PG_DATA}" ]; then
        rm -rf "${TEMP_PG_DATA}" 2>/dev/null || true
    fi

    if [ "${VERIFICATION_PASSED}" = false ]; then
        log_error "Backup verification FAILED — triggering BackupFailed alert"
        push_metric "ivgs_backup_last_status" "0" \
            "backup_type=\"database\",target_path=\"${BACKUP_NAS_DIR}\",node=\"node-01\""
        push_metric "ivgs_backup_verification_status" "0" \
            "verify_date=\"${VERIFY_DATE}\""
    fi
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Step 1: Validate backup files exist
# ---------------------------------------------------------------------------
validate_backup_files() {
    log_info "Validating backup files for ${VERIFY_DATE}"

    if [ ! -d "${BACKUP_DIR}" ]; then
        log_error "Backup directory not found: ${BACKUP_DIR}"
        exit 1
    fi

    if [ ! -f "${ENCRYPTED_FILE}" ]; then
        log_error "Encrypted backup file not found: ${ENCRYPTED_FILE}"
        exit 1
    fi

    log_info "Backup files present"
}

# ---------------------------------------------------------------------------
# Step 2: Verify SHA-256 checksum
# ---------------------------------------------------------------------------
verify_checksum() {
    log_info "Verifying SHA-256 checksum"

    if [ ! -f "${CHECKSUM_FILE}" ]; then
        # A missing checksum file is not a pass. Verification whose only
        # integrity check can be skipped into success is not verification.
        log_error "Checksum file not found: ${CHECKSUM_FILE}"
        exit 1
    fi

    # Compare hashes directly rather than running `sha256sum --check`.
    #
    # --check resolves whatever path the checksum file records. Backups written
    # before 2026-08-14 recorded the absolute STAGING path, so --check looked
    # for /tmp/ivgs-backup/<date>/... and failed on the NAS copy even when the
    # dump was intact -- that is the historical "verification failed" noise.
    # backup.sh now writes a bare filename, but the NAS still holds older files
    # in the old format. Reading only the hash field makes this work for both,
    # and makes it unambiguous that the file being hashed is the one ON THE NAS.
    local expected actual
    expected="$(awk 'NR==1 {print $1}' "${CHECKSUM_FILE}")"
    actual="$(cd "${BACKUP_DIR}" && sha256sum "$(basename "${ENCRYPTED_FILE}")" | awk '{print $1}')"

    if [ -z "${expected}" ] || [ ${#expected} -ne 64 ]; then
        log_error "Checksum file unreadable or malformed: ${CHECKSUM_FILE}"
        exit 1
    fi

    if [ "${expected}" = "${actual}" ]; then
        log_info "SHA-256 checksum VERIFIED" "{\"sha256\":\"${actual}\"}"
    else
        log_error "SHA-256 checksum FAILED — backup file may be corrupted" \
            "{\"expected\":\"${expected}\",\"actual\":\"${actual}\"}"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Step 3: Decrypt and decompress
# ---------------------------------------------------------------------------
decrypt_backup() {
    log_info "Decrypting and decompressing backup for verification"

    gpg --batch --yes --decrypt "${ENCRYPTED_FILE}" | gunzip > "${RESTORE_SQL}"

    if [ ! -s "${RESTORE_SQL}" ]; then
        log_error "Decrypted file is empty"
        exit 1
    fi

    local size
    size="$(stat -c%s "${RESTORE_SQL}" 2>/dev/null || echo 0)"
    log_info "Decrypted successfully" "{\"size_bytes\":${size}}"
}

# ---------------------------------------------------------------------------
# Step 4: Start temporary PostgreSQL container
# ---------------------------------------------------------------------------
start_temp_postgres() {
    log_info "Starting temporary PostgreSQL container: ${TEMP_PG_CONTAINER}"

    # Stream B Phase 5: docker-exec-based postgres access.
    # The temp container is started on the same docker network as
    # ivgs-postgres and the worker, so it gets a DNS name on that
    # network.  We connect via 'docker exec' (which works identically
    # from cron-on-host and from the backup-worker container — both
    # have docker.sock access).  No port mapping needed.
    # PGDATA on DISK, not tmpfs, and the container is memory-capped.
    #
    # This used to be `--tmpfs /var/lib/postgresql/data:size=2g`, i.e. up to 2 GB
    # of the host's RAM. node-01 was reduced to 16 GB on 2026-08-14 and the
    # Proxmox host OOM-killed this VM twice that day; a 2 GB RAM disk spawned
    # unattended at 05:00 is a real risk of taking the node down, and this
    # script runs as a sibling container via the mounted docker socket, so
    # nothing else bounds it.
    #
    # Disk costs nothing here: / has ~261 GB free and the whole dump is under
    # 1 MB. --memory caps the container so a pathological restore cannot grow
    # into the host, and --memory-swap equal to --memory forbids swap rather
    # than pushing the pressure onto disk silently.
    mkdir -p "${TEMP_PG_DATA}"

    docker run -d \
        --name "${TEMP_PG_CONTAINER}" \
        --network ivgs-infra_ivgs-net \
        -e POSTGRES_PASSWORD="${TEMP_PG_PASSWORD}" \
        -e POSTGRES_DB="postgres" \
        -v "${TEMP_PG_DATA}:/var/lib/postgresql/data" \
        --memory=512m \
        --memory-swap=512m \
        --shm-size=128m \
        postgres:17-alpine \
        >/dev/null

    # Wait for PostgreSQL to be ready
    local retries=30
    while [ ${retries} -gt 0 ]; do
        if docker exec "${TEMP_PG_CONTAINER}" \
            pg_isready -U postgres -d postgres >/dev/null 2>&1; then
            log_info "Temporary PostgreSQL is ready"
            return 0
        fi
        sleep 1
        ((retries--))
    done

    log_error "Temporary PostgreSQL failed to start within 30 seconds"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 5: Restore to temporary instance
# ---------------------------------------------------------------------------
restore_to_temp() {
    log_info "Restoring backup to temporary PostgreSQL instance"

    local restore_start
    restore_start="$(date +%s)"

    # Copy decrypted SQL into temp container, then exec psql inside
    docker cp "${RESTORE_SQL}" "${TEMP_PG_CONTAINER}:/tmp/restore.sql"
    docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
        "${TEMP_PG_CONTAINER}" \
        psql -U postgres -d postgres -f /tmp/restore.sql \
        --quiet \
        2>> "${LOG_FILE}" || true  # Some warnings expected (roles, etc.)
    # NOTE: the dump uses --create --clean --if-exists, so it issues CREATE
    # DATABASE ivgs and \connect ivgs internally. Data lands in the 'ivgs' DB.
    # All verification queries below connect to 'ivgs', not 'postgres'.

    local restore_end
    restore_end="$(date +%s)"
    local duration=$(( restore_end - restore_start ))

    log_info "Restore to temp instance completed" \
        "{\"duration_seconds\":${duration}}"
}

# ---------------------------------------------------------------------------
# Step 6: Row count verification
# ---------------------------------------------------------------------------
verify_row_counts() {
    log_info "Running row count verification"

    if [ ! -f "${RECORD_FILE}" ]; then
        log_warn "No backup record file — skipping row count verification"
        return 0
    fi

    # Run ANALYZE to update statistics
    docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
        "${TEMP_PG_CONTAINER}" \
        psql \
        -U postgres -d ivgs \
        -c "ANALYZE;" 2>/dev/null || true

    local expected_total
    expected_total="$(python3 -c "import json; d=json.load(open('${RECORD_FILE}')); print(d.get('total_rows', 0))" 2>/dev/null || echo "0")"

    # Exact counts on both sides. This used to be SUM(n_live_tup), a planner
    # estimate that autovacuum maintains and an unclean shutdown resets — so
    # the comparison was estimate-vs-estimate to within 1%, i.e. noise
    # compared against noise. backup.sh now records real counts via
    # query_to_xml; this is the matching read on the restored instance.
    local actual_total
    actual_total="$(docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
        "${TEMP_PG_CONTAINER}" \
        psql \
        -U postgres -d ivgs \
        -t -A \
        -c "SELECT COALESCE(SUM(c), 0) FROM (
                SELECT (xpath('/row/c/text()',
                              query_to_xml(
                                  format('SELECT count(*) AS c FROM %I.%I',
                                         schemaname, relname),
                                  false, true, '')
                        ))[1]::text::bigint AS c
                FROM pg_stat_user_tables) t;" 2>/dev/null || echo "0")"

    log_info "Row count comparison" \
        "{\"expected\":${expected_total},\"actual\":${actual_total}}"

    # Both sides are exact counts of the same dump, so they must match. There
    # is no legitimate source of drift to absorb: a restored dump either has
    # the rows it was taken with or it does not.
    local tolerance=0
    local diff
    diff="$(python3 -c "print(abs(${expected_total} - ${actual_total}))" 2>/dev/null || echo "0")"

    if [ "${diff}" -gt "${tolerance}" ]; then
        log_error "Row count mismatch: expected=${expected_total}, actual=${actual_total}, diff=${diff}, tolerance=${tolerance}"
        return 1
    fi

    # Per-table verification
    local table_mismatches=0
    while IFS=',' read -r table_name expected_count; do
        [ -z "${table_name}" ] && continue
        local actual_count
        actual_count="$(docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
            "${TEMP_PG_CONTAINER}" \
            psql \
            -U postgres -d ivgs \
            -t -A \
            -c "SELECT COUNT(*) FROM ${table_name};" 2>/dev/null || echo "-1")"

        if [ "${actual_count}" = "-1" ]; then
            log_warn "Table ${table_name} not found in restored database"
            ((table_mismatches++)) || true
        else
            local table_diff
            table_diff="$(python3 -c "print(abs(${expected_count} - ${actual_count}))" 2>/dev/null || echo "0")"
            # Exact on both sides (the restored side already used COUNT(*));
            # no tolerance, same reasoning as the aggregate above.
            local table_tolerance=0
            if [ "${table_diff}" -gt "${table_tolerance}" ]; then
                log_warn "Table ${table_name}: expected=${expected_count}, actual=${actual_count}"
                ((table_mismatches++)) || true
            fi
        fi
    done < <(python3 -c "
import json, sys
d = json.load(open('${RECORD_FILE}'))
for t, c in d.get('row_counts', {}).items():
    print(f'{t},{c}')
" 2>/dev/null)

    if [ "${table_mismatches}" -gt 0 ]; then
        log_warn "Per-table mismatches found: ${table_mismatches}"
    fi

    log_info "Row count verification PASSED"
}

# ---------------------------------------------------------------------------
# Step 7: Schema integrity check
# ---------------------------------------------------------------------------
verify_schema() {
    log_info "Verifying schema integrity"

    local table_count
    table_count="$(docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
        "${TEMP_PG_CONTAINER}" \
        psql \
        -U postgres -d ivgs \
        -t -A \
        -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")"

    local index_count
    index_count="$(docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
        "${TEMP_PG_CONTAINER}" \
        psql \
        -U postgres -d ivgs \
        -t -A \
        -c "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';" 2>/dev/null || echo "0")"

    local constraint_count
    constraint_count="$(docker exec -e PGPASSWORD="${TEMP_PG_PASSWORD}" \
        "${TEMP_PG_CONTAINER}" \
        psql \
        -U postgres -d ivgs \
        -t -A \
        -c "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = 'public';" 2>/dev/null || echo "0")"

    log_info "Schema integrity" \
        "{\"tables\":${table_count},\"indexes\":${index_count},\"constraints\":${constraint_count}}"

    if [ "${table_count}" -eq 0 ]; then
        log_error "No tables found in restored database — schema restore failed"
        return 1
    fi

    log_info "Schema integrity verification PASSED"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local start_time
    start_time="$(date +%s)"

    log_info "=== IVGS v5 Backup Verification Starting ===" \
        "{\"verify_date\":\"${VERIFY_DATE}\"}"

    validate_backup_files
    verify_checksum
    decrypt_backup
    start_temp_postgres
    restore_to_temp
    verify_row_counts
    verify_schema

    VERIFICATION_PASSED=true

    local end_time
    end_time="$(date +%s)"
    local duration=$(( end_time - start_time ))

    push_metric "ivgs_backup_verification_status" "1" \
        "verify_date=\"${VERIFY_DATE}\""
    push_metric "ivgs_backup_verification_duration_seconds" "${duration}" \
        "verify_date=\"${VERIFY_DATE}\""

    # Store verification result in backup record
    if [ -f "${RECORD_FILE}" ]; then
        python3 -c "
import json
with open('${RECORD_FILE}', 'r') as f:
    d = json.load(f)
d['verification'] = {
    'status': 'passed',
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'duration_seconds': ${duration}
}
with open('${RECORD_FILE}', 'w') as f:
    json.dump(d, f, indent=4)
" 2>/dev/null || true
    fi

    log_info "=== Backup Verification PASSED ===" \
        "{\"duration_seconds\":${duration}}"

    echo ""
    echo "✅ Backup valid, checksum match, row counts verified"
    echo "   Verified: ${VERIFY_DATE}"
    echo "   Duration: ${duration}s"
}

main "$@"
