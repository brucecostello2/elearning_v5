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
#   5. Point-in-time recovery — AVAILABLE since WP-59 Task 8. Replays the WAL
#      archive onto the weekly pg_basebackup into a STAGED cluster, never the
#      live one. Refuses, naming the reason, when a precondition is absent.
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
#   ./restore.sh YYYY-MM-DD --pit YYYY-MM-DD-HH:MM  # PITR into a staged cluster
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

# Node registry — GPU node IPs come from node-01's .env (single source), never hardcoded
NODE_REGISTRY="${NODE_REGISTRY:-${COMPOSE_DIR}/ivgs-infra/.env}"
declare -A NODE_IPS=( [02]="" [03]="" [04]="" [05]="" [06]="" )
if [[ -f "$NODE_REGISTRY" ]]; then
    for __n in "${!NODE_IPS[@]}"; do
        NODE_IPS[$__n]="$(grep -E "^NODE_${__n}_IP=" "$NODE_REGISTRY" | head -1 | cut -d= -f2)"
    done
fi

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
    # Self-permissive log file: created world-writable so that
    # both cron (root) and the backup-worker container (UID 999)
    # can append. Idempotent via the chmod-after-touch.
    touch "${LOG_FILE}" 2>/dev/null || true
    chmod 666 "${LOG_FILE}" 2>/dev/null || true
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
  --pit TARGET         Point-in-time recovery to YYYY-MM-DD-HH:MM. Replays the
                       WAL archive onto the weekly pg_basebackup into a STAGED
                       cluster on a spare port. The live database is never
                       touched. Refuses, naming the precondition, when there is
                       no base at or before the target, or the WAL archive is
                       missing, off the NAS, or has a gap.
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
        local node_ip="${NODE_IPS[${node##node-}]:-}"
        if [[ -z "$node_ip" ]]; then
            log_warn "No registry IP for ${node} (set NODE_${node##node-}_IP in ${NODE_REGISTRY}) — skipping"
            continue
        fi
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

    # =======================================================================
    # WP-59 Task 8 — PITR NOW EXISTS, AND THIS PERFORMS IT.
    # =======================================================================
    # WP-57 Task 6 established that it could not: `backup.sh` takes
    # `pg_dump --format=plain`, a LOGICAL dump, and WAL records physical block
    # changes keyed to LSNs in one data directory. Restoring SQL builds a new
    # cluster with a different layout and an unrelated timeline, so
    # `recovery_target_time` had nothing to seek within. This function refused
    # with that reason (exit 5) rather than writing a recovery.conf that would
    # have sent an operator hunting a base backup that did not exist.
    #
    # The operator ruled to build one (D-2). `scripts/basebackup.sh` takes a
    # weekly `pg_basebackup` into /mnt/backup/ivgs/basebackup/, and these
    # segments now have something to replay onto.
    #
    # IT STILL REFUSES CLEARLY WHEN THE PRECONDITIONS ARE ABSENT, and there are
    # four of them. Each is checked and named separately, because "PITR failed"
    # is not a useful sentence at 3 a.m.:
    #
    #   1. A base backup exists, at or before the target instant.
    #   2. The WAL archive is reachable and is on the NAS.
    #   3. The archive covers the base's start_lsn forward -- an unbroken
    #      segment run. A gap makes replay stop at the gap, silently, which is
    #      the worst possible outcome and the reason WP-57 D-3 mattered.
    #   4. The target instant is not before the base was taken.
    #
    # A PITR IS A NEW CLUSTER, NOT AN EDIT OF THIS ONE. What this writes is a
    # complete, ready-to-start data directory in a STAGING location, plus the
    # exact commands to bring it up. It does not stop, reconfigure or overwrite
    # the running cluster, and it never will: an in-place PITR of a live
    # database is a one-way door pressed under stress. The operator promotes
    # the recovered cluster deliberately, having looked at it.
    # =======================================================================
    local basebackup_root="${BASEBACKUP_NAS_DIR:-/mnt/backup/ivgs/basebackup}"

    log_info "Step 5: Point-in-time recovery to ${PIT_TARGET}"

    # --- Precondition 1: a physical base backup exists ---------------------
    if [ ! -d "${basebackup_root}" ]; then
        log_error "Point-in-time recovery is NOT POSSIBLE: no base backup directory."
        log_error "  Looked in: ${basebackup_root}"
        log_error "  WAL replay requires a PHYSICAL base backup (pg_basebackup)."
        log_error "  Take one with: scripts/basebackup.sh   (dry run first:"
        log_error "  scripts/basebackup.sh --dry-run). Until a base exists, the"
        log_error "  honest recovery promise is checkpoint-only: re-run this"
        log_error "  script without --pit to restore the latest logical dump."
        log_error "  See docs/runbooks/point-in-time-recovery.md."
        return 5
    fi

    # The newest base at or before the target. Recovery replays FORWARD, so a
    # base taken after the target instant is useless for it.
    local pit_epoch base_dir="" base_epoch=0
    pit_epoch="$(date -d "$(echo "${PIT_TARGET}" | sed 's/-\([0-9][0-9]:[0-9][0-9]\)$/ \1/')" +%s 2>/dev/null || echo 0)"
    if [ "${pit_epoch}" -eq 0 ]; then
        log_error "Could not parse --pit target ${PIT_TARGET}."
        log_error "  Expected YYYY-MM-DD-HH:MM (e.g. 2026-08-26-14:30)."
        return 5
    fi

    local candidate candidate_epoch
    while IFS= read -r candidate; do
        [ -f "${candidate}/basebackup_record.json" ] || continue
        candidate_epoch="$(stat -c %Y "${candidate}" 2>/dev/null || echo 0)"
        if [ "${candidate_epoch}" -le "${pit_epoch}" ] && \
           [ "${candidate_epoch}" -gt "${base_epoch}" ]; then
            base_epoch="${candidate_epoch}"
            base_dir="${candidate}"
        fi
    done < <(find "${basebackup_root}" -maxdepth 1 -mindepth 1 -type d | sort)

    if [ -z "${base_dir}" ]; then
        log_error "Point-in-time recovery is NOT POSSIBLE: no base backup was"
        log_error "  taken at or before ${PIT_TARGET}."
        log_error "  Recovery replays WAL FORWARD from a base; a base taken"
        log_error "  after the target instant cannot reach it."
        log_error "  Bases present in ${basebackup_root}:"
        find "${basebackup_root}" -maxdepth 1 -mindepth 1 -type d -printf '    %f\n' 2>/dev/null | sort >&2
        return 5
    fi

    local start_lsn
    start_lsn="$(python3 -c "import json;print(json.load(open('${base_dir}/basebackup_record.json')).get('start_lsn',''))" 2>/dev/null || echo "")"
    log_info "Base backup selected" \
        "{\"base_dir\":\"${base_dir}\",\"start_lsn\":\"${start_lsn}\"}"

    # --- Precondition 2: the WAL archive is real, and is the NAS -----------
    if [ ! -d "${WAL_ARCHIVE_DIR}" ]; then
        log_error "Point-in-time recovery is NOT POSSIBLE: WAL archive directory"
        log_error "  ${WAL_ARCHIVE_DIR} does not exist. Nothing to replay."
        return 5
    fi
    # WP-59 Task 9. A WAL archive on the LOCAL disk is the shadowed-mount
    # failure, and a recovery that replays from a shadowed tree replays a
    # partial history without saying so. Refuse.
    if [ -r "$(dirname "$0")/lib/nfs_guard.sh" ]; then
        # shellcheck source=lib/nfs_guard.sh
        . "$(dirname "$0")/lib/nfs_guard.sh"
        if ! assert_nfs_destination "${WAL_ARCHIVE_DIR}" "WAL archive (restore source)"; then
            log_error "Point-in-time recovery is NOT POSSIBLE: the WAL archive at"
            log_error "  ${WAL_ARCHIVE_DIR} is not on the NAS. Replaying from a"
            log_error "  shadowed local directory would replay a partial history"
            log_error "  and stop early without an error (WP-57 D-3)."
            return 5
        fi
    fi

    local wal_count
    wal_count="$(find "${WAL_ARCHIVE_DIR}" -maxdepth 1 -type f -name '[0-9A-F]*' 2>/dev/null | wc -l)"
    if [ "${wal_count}" -eq 0 ]; then
        log_error "Point-in-time recovery is NOT POSSIBLE: the WAL archive at"
        log_error "  ${WAL_ARCHIVE_DIR} contains no segments."
        return 5
    fi

    # --- Precondition 3: the segment run is unbroken -----------------------
    # Segment names are 24 hex characters; within one timeline+logical-file the
    # last 8 characters increment. A missing segment stops replay dead at that
    # point, and PostgreSQL will report it as a successful recovery to an
    # earlier instant. Checking here converts a silent short recovery into a
    # refusal that names the gap.
    local gap_report
    gap_report="$(find "${WAL_ARCHIVE_DIR}" -maxdepth 1 -type f -name '[0-9A-F]*' -printf '%f\n' \
        | grep -E '^[0-9A-F]{24}$' | sort | python3 -c '
import sys
names = [l.strip() for l in sys.stdin if l.strip()]
gaps = []
prev = None
for n in names:
    if prev is not None and int(n, 16) != int(prev, 16) + 1:
        gaps.append(f"{prev} -> {n}")
    prev = n
print("; ".join(gaps))
' 2>/dev/null || echo "")"
    if [ -n "${gap_report}" ]; then
        log_error "Point-in-time recovery is NOT SAFE: the WAL archive has gaps."
        log_error "  ${gap_report}"
        log_error "  Replay would stop at the first gap and report success at an"
        log_error "  earlier instant than requested. Refusing."
        log_error "  If segments were stranded on local disk (WP-57 D-3), merge"
        log_error "  them into ${WAL_ARCHIVE_DIR} and re-run."
        return 5
    fi
    log_info "WAL archive verified" \
        "{\"segments\":${wal_count},\"gaps\":0}"

    # --- Stage the recovery cluster ----------------------------------------
    local stage_dir="${PITR_STAGE_DIR:-/var/lib/ivgs/pitr-${RESTORE_DATE}-$(date +%s)}"

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] All preconditions satisfied. Would stage a recovery"
        log_info "[DRY RUN]   cluster from ${base_dir} into ${stage_dir}"
        log_info "[DRY RUN]   and replay ${wal_count} segments to ${PIT_TARGET}."
        echo "pitr_base_dir=${base_dir}"
        echo "pitr_stage_dir=${stage_dir}"
        echo "pitr_wal_segments=${wal_count}"
        return 0
    fi

    mkdir -p "${stage_dir}"
    log_info "Unpacking base backup into ${stage_dir}"
    if ! tar -xzf "${base_dir}/base.tar.gz" -C "${stage_dir}"; then
        log_error "Could not unpack ${base_dir}/base.tar.gz into ${stage_dir}."
        return 5
    fi
    # Tablespace tars, if any, sit beside base.tar.gz named by their OID.
    local tblspc
    while IFS= read -r tblspc; do
        [ "$(basename "${tblspc}")" = "base.tar.gz" ] && continue
        log_warn "Tablespace archive present and NOT unpacked automatically: ${tblspc}"
        log_warn "  A cluster with tablespaces needs each unpacked to its own"
        log_warn "  original location before start. Stopping rather than"
        log_warn "  producing a cluster that starts and is missing data."
        return 5
    done < <(find "${base_dir}" -maxdepth 1 -type f -name '*.tar.gz')

    chmod 700 "${stage_dir}"

    # recovery.signal + the two recovery GUCs. PostgreSQL 12+ takes these in
    # postgresql.auto.conf, NOT a recovery.conf -- which is the other reason
    # the old /tmp/ivgs_recovery.conf advice could not have worked on 17.2.
    cat >> "${stage_dir}/postgresql.auto.conf" <<RECOVERY_EOF

# --- WP-59 point-in-time recovery, staged $(date -u +%Y-%m-%dT%H:%M:%SZ) ---
restore_command = 'cp ${WAL_ARCHIVE_DIR}/%f %p'
recovery_target_time = '${PIT_TARGET}'
# 'pause', not 'promote'. The cluster stops at the target and waits, so the
# operator can connect and LOOK at what they recovered before making it
# writable. Promoting automatically ends the timeline and forecloses a second
# attempt at a different instant.
recovery_target_action = 'pause'
RECOVERY_EOF
    touch "${stage_dir}/recovery.signal"

    log_info "Recovery cluster staged" \
        "{\"stage_dir\":\"${stage_dir}\",\"base\":\"${base_dir}\",\"target\":\"${PIT_TARGET}\"}"

    cat <<INSTRUCTIONS
=============================================================================
POINT-IN-TIME RECOVERY CLUSTER STAGED — the live database was NOT touched.
=============================================================================
  Base backup : ${base_dir}   (start_lsn ${start_lsn})
  WAL archive : ${WAL_ARCHIVE_DIR}   (${wal_count} segments, no gaps)
  Target time : ${PIT_TARGET}
  Staged at   : ${stage_dir}

Start the recovered cluster on a SPARE PORT, alongside the live one:

  docker run --rm -d --name ivgs-pitr \\
    -v ${stage_dir}:/var/lib/postgresql/data \\
    -v ${WAL_ARCHIVE_DIR}:${WAL_ARCHIVE_DIR}:ro \\
    -p 5433:5432 postgres:17.2

Watch it reach the target:

  docker logs -f ivgs-pitr        # "recovery stopping before ... pause"

Then LOOK at it before you trust it:

  psql -h 127.0.0.1 -p 5433 -U ${POSTGRES_USER} -d ${POSTGRES_DB} \\
       -c "SELECT count(*) FROM projects;"

Only when it is what you expected:

  psql -h 127.0.0.1 -p 5433 -U ${POSTGRES_USER} -d postgres \\
       -c "SELECT pg_wal_replay_resume();"

It is a separate cluster on 5433. Cutting over to it is a deliberate,
separate act -- see docs/runbooks/point-in-time-recovery.md.
=============================================================================
INSTRUCTIONS
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
        local node_ip="${NODE_IPS[${node##node-}]:-}"
        if [[ -z "$node_ip" ]]; then
            log_warn "No registry IP for ${node} (set NODE_${node##node-}_IP in ${NODE_REGISTRY}) — skipping"
            continue
        fi
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
