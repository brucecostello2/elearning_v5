#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — Asset Backup Script
# =============================================================================
# Spec reference: §14.1 Table 14-1 — Backup Schedule (Row 3: Asset backup)
#
# Type:      Asset backup (incremental)
# Scope:     SeaweedFS volume data + filer metadata + master config + shared volume
# Method:    rsync with --link-dest (hard-link unchanged files to previous backup)
# Schedule:  Daily at 03:00 (via cron — see configs/cron/ivgs-backup-crontab)
# Target:    /mnt/backup/ivgs/assets/YYYY-MM-DD/
# Retention: 14 days
#
# Environment variables required:
#   POSTGRES_PASSWORD       — needed for status updates to backup_records table
#   POSTGRES_USER           — Postgres user (default: ivgs)
#   POSTGRES_DB             — Database name (default: ivgs)
#   POSTGRES_HOST           — Postgres host (default: localhost)
#   POSTGRES_PORT           — Postgres port (default: 5432)
#   BACKUP_NAS_DIR          — NAS target directory (default: /mnt/backup/ivgs/assets)
#   BACKUP_RETENTION_DAYS   — Days to retain backups (default: 14)
#   PROMETHEUS_PUSHGATEWAY  — Pushgateway URL (default: http://localhost:9091)
#
# Exit codes:
#   0 — Success
#   1 — Missing required environment variable / failed pre-flight
#   2 — Lock file exists (another asset backup running)
#   3 — Insufficient disk space at staging or NAS
#   4 — rsync of seaweedfs-volume failed
#   5 — rsync of seaweedfs-filer failed
#   6 — rsync of seaweedfs-master failed
#   7 — rsync of /mnt/ivgs-shared failed
#   8 — Retention cleanup failed
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing (Stream B API integration)
# ---------------------------------------------------------------------------
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
readonly TIMESTAMP="$(date +%Y-%m-%d)"
readonly DATETIME="$(date +%Y-%m-%dT%H:%M:%S%z)"
readonly LOCK_FILE="/var/run/ivgs/asset-backup.lock"
readonly LOG_FILE="/var/log/ivgs/asset_backup.log"
readonly LOG_DIR="/var/log/ivgs"

# Source paths (host-side; these are Docker named-volume mountpoints)
readonly SRC_SEAWEEDFS_VOLUME="/var/lib/docker/volumes/ivgs-infra_seaweedfs-volume-data/_data"
readonly SRC_SEAWEEDFS_FILER="/var/lib/docker/volumes/ivgs-infra_seaweedfs-filer-data/_data"
readonly SRC_SEAWEEDFS_MASTER="/var/lib/docker/volumes/ivgs-infra_seaweedfs-master-data/_data"
readonly SRC_SHARED_VOLUME="/mnt/ivgs-shared"

# Target / retention / metrics
BACKUP_NAS_DIR="${BACKUP_NAS_DIR:-/mnt/backup/ivgs/assets}"

# WP-58 Task 3. AD-09.14 open question 7, RULED: library assets and actors get
# INDEFINITE retention.
#
# WHY THEY ARE DIFFERENT FROM EVERY OTHER ASSET. A project asset is
# REGENERABLE - the prompt, the certified model and the seed are all held, so a
# lost render can be re-rendered. A library asset is SOURCE MATERIAL WITH NO
# UPSTREAM: an uploaded logo, an actor's reference clip, a music bed, a font.
# Nothing can reproduce it. AD-09.4.2 stores both in the same SeaweedFS volumes,
# so the 14-day prune below would eventually delete the only copy of material
# that cannot be remade - and the schema already says the opposite is intended
# (`library_assets.superseded_by`: never hard-deleted while referenced). Backup
# retention must not contradict the schema's own intent.
#
# TIERED, NOT A SEPARATE LINEAGE. The alternative was a second backup that
# identifies library objects and copies them on their own. Rejected: this script
# is a whole-volume rsync and "has no concept of an asset" by construction.
# Teaching it one means resolving library_assets -> fids -> filer objects, which
# is a second copy path that can silently drift out of step with the volume
# snapshot. The volume rsync ALREADY captures library assets; the only thing
# missing was a copy the daily prune cannot reach.
#
# COST IS ~ZERO AND THAT IS MEASURED, not assumed: with --link-dest an unchanged
# day costs 274 KB on the live store (2026-08-20/21/22), and the NAS is at 1% of
# 20T. A monthly snapshot of static material is one directory of hard links.
MONTHLY_DIR="${MONTHLY_DIR:-${BACKUP_NAS_DIR}/monthly}"

# THE GUARD THAT MAKES THIS SAFE. Both the prune and the link-dest search below
# used a bare `-type d` under BACKUP_NAS_DIR. Adding ANY sibling directory to
# that path - which is exactly what MONTHLY_DIR is - would have made it a
# candidate for both:
#   * the prune would `rm -rf` the monthly tree the day it turned 15 days old,
#     destroying the very thing this task exists to protect;
#   * determine_link_dest sorts descending and takes the first hit, and
#     "monthly" sorts AFTER "2026-..." , so every future backup would have
#     hard-linked against the wrong tree.
# Restricting both finds to date-named directories closes both at once.
readonly DATED_SNAPSHOT_GLOB='20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
# WP-58 Task 1 - see the banner in scripts/backup.sh for the full reasoning.
# Reads its OWN class variable. A single shared name would let the assets number
# govern database retention too.
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_ASSETS_DAYS:-${BACKUP_RETENTION_DAYS:-14}}"
PROMETHEUS_PUSHGATEWAY="${PROMETHEUS_PUSHGATEWAY:-http://localhost:9091}"
MIN_DISK_SPACE_MB="${MIN_DISK_SPACE_MB:-5120}"

# Postgres connection for status reporting (matches backup.sh convention)
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ivgs}"
POSTGRES_DB="${POSTGRES_DB:-ivgs}"

readonly TARGET_DIR="${BACKUP_NAS_DIR}/${TIMESTAMP}"
readonly RECORD_FILE="${TARGET_DIR}/backup_record.json"

# ---------------------------------------------------------------------------
# backup_records row ownership
# ---------------------------------------------------------------------------
# This script, not the Celery task, owns the row — see the header of
# lib/backup_record.sh. Without this, a cron or direct `docker exec` asset
# backup produced files on the NAS that the GUI could not see.
BACKUP_RECORD_TYPE="asset_backup"
# shellcheck source=lib/backup_record.sh
. "$(dirname "$0")/lib/backup_record.sh"

# WP-59 Task 9 (WP-57 D-3). This script is the one whose destination check DID
# pass over a shadowed local directory: the 45 GB of orphaned July snapshots on
# node-01's root volume were written here, by this script, while its surface
# reported the asset backup working.
# shellcheck source=lib/nfs_guard.sh
. "$(dirname "$0")/lib/nfs_guard.sh"
ensure_backup_id

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
{"timestamp":"${timestamp}","level":"${level}","service":"asset-backup","script":"${SCRIPT_NAME}","message":"${message}","backup_date":"${TIMESTAMP}","extra":${extra}}
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

push_asset_backup_status() {
    local status="$1"    # 1=success, 0=failure
    local duration="$2"  # seconds
    local size_bytes="${3:-0}"

    push_metric "ivgs_backup_last_status" "${status}" "gauge" "backup_type=\"assets\",target_path=\"${BACKUP_NAS_DIR}\",node=\"node-01\""
    push_metric "ivgs_backup_last_timestamp" "$(date +%s)" "gauge" "backup_type=\"assets\""
    push_metric "ivgs_backup_duration_seconds" "${duration}" "gauge" "backup_type=\"assets\""
    push_metric "ivgs_backup_size_bytes" "${size_bytes}" "gauge" "backup_type=\"assets\""
}

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
cleanup() {
    local exit_code=$?
    rm -f "${LOCK_FILE}" 2>/dev/null || true
    if [ ${exit_code} -ne 0 ]; then
        log_error "Asset backup failed with exit code ${exit_code}"
        record_failed "${exit_code}" "${LOG_FILE}"
        push_asset_backup_status 0 0 0
    fi
    exit ${exit_code}
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight_checks() {
    log_info "Starting pre-flight checks"

    # Open the row before anything that can fail — the lock-file write below
    # included. On 2026-08-14 that write failed with "Permission denied" on
    # /var/run/ivgs/asset-backup.lock.
    record_running

    # Lock file check (prevent concurrent runs)
    if [ -f "${LOCK_FILE}" ]; then
        local lock_pid
        lock_pid="$(cat "${LOCK_FILE}" 2>/dev/null || echo "unknown")"
        if kill -0 "${lock_pid}" 2>/dev/null; then
            log_error "Another asset backup is running (PID: ${lock_pid})" \
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
    for cmd in rsync curl; do
        if ! command -v "${cmd}" &>/dev/null; then
            log_error "Required command not found: ${cmd}"
            exit 1
        fi
    done

    # Source path existence
    for src in "${SRC_SEAWEEDFS_VOLUME}" "${SRC_SEAWEEDFS_FILER}" "${SRC_SEAWEEDFS_MASTER}"; do
        if [ ! -d "${src}" ]; then
            log_error "Source path missing: ${src}"
            exit 1
        fi
    done

    # /mnt/ivgs-shared may not exist in dev environments — warn but don't fail
    if [ ! -d "${SRC_SHARED_VOLUME}" ]; then
        log_warn "Shared volume not present: ${SRC_SHARED_VOLUME}" \
            "{\"note\":\"will skip rsync of shared volume\"}"
    fi

    # NAS target check — WP-59 Task 9.
    #
    # The PARENT is guarded rather than the target, because the target is
    # created below and a not-yet-existing directory has no filesystem type of
    # its own. Guarding the parent and only then creating the child is what
    # makes the `mkdir -p` safe: it can no longer bring a local directory into
    # existence underneath an absent mount, which is how the shadowed tree grew.
    if ! assert_nfs_destination "$(dirname "${BACKUP_NAS_DIR}")" "asset backup"; then
        log_error "NAS parent directory is not an NFS mount: $(dirname "${BACKUP_NAS_DIR}")" \
            "{\"guard\":\"assert_nfs_destination\",\"ledger\":\"WP-57 D-3\"}"
        exit 6
    fi
    mkdir -p "${BACKUP_NAS_DIR}"

    # Disk space check on NAS
    local available_mb
    available_mb="$(df -BM "${BACKUP_NAS_DIR}" | awk 'NR==2 {print $4}' | tr -d 'M')"
    if [ "${available_mb}" -lt "${MIN_DISK_SPACE_MB}" ]; then
        log_error "Insufficient NAS disk space" \
            "{\"available_mb\":${available_mb},\"required_mb\":${MIN_DISK_SPACE_MB}}"
        exit 3
    fi

    log_info "Pre-flight checks passed"
}

# ---------------------------------------------------------------------------
# Determine --link-dest source (yesterday's backup, if it exists)
# ---------------------------------------------------------------------------
determine_link_dest() {
    # Look for the most recent existing backup directory under BACKUP_NAS_DIR
    # that is not today's. rsync --link-dest will hard-link unchanged files
    # to dramatically reduce space + bandwidth for incremental backups.
    local latest
    # WP-58 Task 3: -name "${DATED_SNAPSHOT_GLOB}". Without it `monthly` is a
    # candidate, and it sorts AFTER every 2026-.. name, so `sort -r | head -1`
    # would pick it every time.
    latest="$(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d \
              -name "${DATED_SNAPSHOT_GLOB}" \
              -not -name "${TIMESTAMP}" 2>/dev/null | sort -r | head -1)"
    if [ -n "${latest}" ] && [ -d "${latest}" ]; then
        echo "${latest}"
    else
        echo ""
    fi
}

# ---------------------------------------------------------------------------
# Rsync a single source to target subdirectory
# ---------------------------------------------------------------------------
# Arguments:
#   $1 — source path (host)
#   $2 — target subdirectory name (under TARGET_DIR)
#   $3 — exit code if this rsync fails
#   $4 — link-dest base directory (optional)
# Global used by rsync_source to return the size to the caller.
# (Function avoids stdout-as-return-value since we also log to stdout.)
RSYNC_LAST_SIZE=0

rsync_source() {
    local src="$1"
    local sub_target="$2"
    local fail_exit_code="$3"
    local link_base="${4:-}"

    local full_target="${TARGET_DIR}/${sub_target}"
    mkdir -p "${full_target}"

    local link_dest_arg=""
    if [ -n "${link_base}" ] && [ -d "${link_base}/${sub_target}" ]; then
        link_dest_arg="--link-dest=${link_base}/${sub_target}"
        log_info "rsync ${sub_target} with --link-dest" \
            "{\"src\":\"${src}\",\"target\":\"${full_target}\",\"link_dest\":\"${link_base}/${sub_target}\"}"
    else
        log_info "rsync ${sub_target} (full copy, no prior backup to link against)" \
            "{\"src\":\"${src}\",\"target\":\"${full_target}\"}"
    fi

    local rsync_start
    rsync_start="$(date +%s)"

    if rsync --archive --hard-links --acls --xattrs \
             --delete-after \
             ${link_dest_arg} \
             "${src}/" "${full_target}/" \
             >> "${LOG_FILE}" 2>&1; then
        local rsync_end
        rsync_end="$(date +%s)"
        local duration=$(( rsync_end - rsync_start ))
        local target_size
        target_size="$(du -sb "${full_target}" 2>/dev/null | awk '{print $1}')"
        log_info "rsync ${sub_target} completed" \
            "{\"duration_seconds\":${duration},\"target_size_bytes\":${target_size}}"
        RSYNC_LAST_SIZE="${target_size}"
    else
        log_error "rsync ${sub_target} failed (see log for rsync output)"
        exit "${fail_exit_code}"
    fi
}

# ---------------------------------------------------------------------------
# Capture metadata
# ---------------------------------------------------------------------------
capture_metadata() {
    local total_bytes="$1"

    # Count files per subdirectory for verification
    local vol_count fil_count mas_count shr_count
    vol_count="$(find "${TARGET_DIR}/seaweedfs-volume" -type f 2>/dev/null | wc -l)"
    fil_count="$(find "${TARGET_DIR}/seaweedfs-filer" -type f 2>/dev/null | wc -l)"
    mas_count="$(find "${TARGET_DIR}/seaweedfs-master" -type f 2>/dev/null | wc -l)"
    shr_count="$(find "${TARGET_DIR}/shared-volume" -type f 2>/dev/null | wc -l)"

    cat > "${RECORD_FILE}" <<RECORD_EOF
{
    "backup_date": "${TIMESTAMP}",
    "backup_timestamp": "${DATETIME}",
    "backup_type": "assets",
    "method": "rsync_link_dest",
    "total_size_bytes": ${total_bytes},
    "subdirectories": {
        "seaweedfs-volume": {"file_count": ${vol_count}},
        "seaweedfs-filer":  {"file_count": ${fil_count}},
        "seaweedfs-master": {"file_count": ${mas_count}},
        "shared-volume":    {"file_count": ${shr_count}}
    },
    "retention_days": ${BACKUP_RETENTION_DAYS},
    "target_dir": "${TARGET_DIR}"
}
RECORD_EOF

    log_info "Metadata captured" \
        "{\"total_files\":$(( vol_count + fil_count + mas_count + shr_count )),\"total_bytes\":${total_bytes}}"
}

# ---------------------------------------------------------------------------
# Monthly promotion — indefinite retention for unregenerable material
# ---------------------------------------------------------------------------
# WP-58 Task 3 / AD-09.14 Q7. One snapshot per calendar month, hard-linked from
# that month's first successful daily run, kept FOREVER.
#
# THERE IS NO PRUNE FOR THIS TREE AND THAT IS THE POINT. Do not add one without
# re-opening AD-09.14 Q7: the ruling is indefinite retention, and a monthly
# snapshot of static source material costs one directory of hard links.
#
# `cp -al` is what makes it free: -a preserves attributes, -l links instead of
# copying, so a promoted month shares every inode with the daily snapshot it
# came from. When the daily is pruned 14 days later, `rm -rf` only decrements
# each link count - the bytes stay reachable through the monthly copy. That is
# the mechanism, not a happy accident, and it is what makes "the prune cannot
# delete the last surviving copy" structurally true rather than a matter of care.
promote_monthly_snapshot() {
    local month target
    month="$(date +%Y-%m)"
    target="${MONTHLY_DIR}/${month}"

    if [ -d "${target}" ]; then
        log_info "Monthly snapshot already present, not re-promoting" \
            "{\"month\":\"${month}\",\"target\":\"${target}\"}"
        return 0
    fi

    if [ ! -d "${TARGET_DIR}" ]; then
        log_info "No daily snapshot to promote" "{\"expected\":\"${TARGET_DIR}\"}"
        return 0
    fi

    mkdir -p "${MONTHLY_DIR}"

    # Hard-link the whole day into the monthly tree. A failure here must NOT
    # fail the backup: the daily snapshot is already on the NAS and is the
    # thing the operator depends on today. It is logged loudly instead, because
    # a silently-missing monthly is how indefinite retention quietly becomes
    # 14-day retention.
    if cp -al "${TARGET_DIR}" "${target}" 2>/dev/null; then
        log_info "Monthly snapshot promoted (hard-linked, indefinite retention)" \
            "{\"month\":\"${month}\",\"source\":\"${TARGET_DIR}\",\"target\":\"${target}\"}"
    else
        # cp -al cannot hard-link across filesystems. Fall back to a real copy
        # rather than skipping: correctness of the retention guarantee outranks
        # the disk saving, and the operator is told which one happened.
        if cp -a "${TARGET_DIR}" "${target}" 2>/dev/null; then
            log_info "Monthly snapshot promoted BY FULL COPY (hard-link failed)" \
                "{\"month\":\"${month}\",\"target\":\"${target}\"}"
        else
            log_error "MONTHLY PROMOTION FAILED - library assets have no long-term copy for this month" \
                "{\"month\":\"${month}\",\"target\":\"${target}\"}"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Retention cleanup (14 days per Table 14-1)
# ---------------------------------------------------------------------------
cleanup_old_backups() {
    log_info "Cleaning up asset backups older than ${BACKUP_RETENTION_DAYS} days"

    local deleted_count=0

    if [ -d "${BACKUP_NAS_DIR}" ]; then
        while IFS= read -r -d '' dir; do
            log_info "Removing old asset backup: ${dir}"
            rm -rf "${dir}"
            ((deleted_count++)) || true
        # WP-58 Task 3. -name "${DATED_SNAPSHOT_GLOB}" is LOAD-BEARING, not
        # tidiness. Without it this find matches ${MONTHLY_DIR} itself and
        # `rm -rf` destroys the indefinite-retention tree the moment it is older
        # than BACKUP_RETENTION_ASSETS_DAYS - i.e. this prune would delete the
        # only surviving copy of every library asset, which is precisely the
        # outcome Task 3 exists to make impossible. Never widen this pattern.
        done < <(find "${BACKUP_NAS_DIR}" -maxdepth 1 -mindepth 1 -type d \
            -name "${DATED_SNAPSHOT_GLOB}" \
            -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)
    fi

    log_info "Retention cleanup completed" \
        "{\"deleted_count\":${deleted_count},\"retention_days\":${BACKUP_RETENTION_DAYS}}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local start_time
    start_time="$(date +%s)"

    log_info "=== IVGS v5 Asset Backup Starting ===" \
        "{\"backup_date\":\"${TIMESTAMP}\"}"

    preflight_checks

    local link_base
    link_base="$(determine_link_dest)"
    if [ -n "${link_base}" ]; then
        log_info "Found prior backup for --link-dest" "{\"link_base\":\"${link_base}\"}"
    else
        log_info "No prior asset backup; doing full first copy"
    fi

    # Run rsync for each source, accumulate total size.
    # rsync_source assigns its result to the global RSYNC_LAST_SIZE.
    local total_size=0

    rsync_source "${SRC_SEAWEEDFS_VOLUME}" "seaweedfs-volume" 4 "${link_base}"
    total_size=$(( total_size + RSYNC_LAST_SIZE ))

    rsync_source "${SRC_SEAWEEDFS_FILER}" "seaweedfs-filer" 5 "${link_base}"
    total_size=$(( total_size + RSYNC_LAST_SIZE ))

    rsync_source "${SRC_SEAWEEDFS_MASTER}" "seaweedfs-master" 6 "${link_base}"
    total_size=$(( total_size + RSYNC_LAST_SIZE ))

    if [ -d "${SRC_SHARED_VOLUME}" ]; then
        rsync_source "${SRC_SHARED_VOLUME}" "shared-volume" 7 "${link_base}"
        total_size=$(( total_size + RSYNC_LAST_SIZE ))
    fi

    capture_metadata "${total_size}"

    # WP-58 Task 3. ORDER MATTERS AND IS NOT COSMETIC: promote BEFORE pruning.
    # Reversing these two lines on the first of a month would prune the day that
    # was about to be promoted, and the month would silently have no long-term
    # snapshot.
    promote_monthly_snapshot
    cleanup_old_backups

    local end_time
    end_time="$(date +%s)"
    local duration=$(( end_time - start_time ))

    record_completed "${total_size}" "${BACKUP_NAS_DIR}/${TIMESTAMP}"

    push_asset_backup_status 1 "${duration}" "${total_size}"

    log_info "=== IVGS v5 Asset Backup Completed Successfully ===" \
        "{\"duration_seconds\":${duration},\"total_size_bytes\":${total_size}}"

    # Stream B API integration: emit KEY=VALUE lines on stdout for the
    # FastAPI _run_backup code to parse.
    echo "backup_id=${BACKUP_ID}"
    echo "size_bytes=${total_size}"
    echo "backup_path=${BACKUP_NAS_DIR}/${TIMESTAMP}"
    # ok | failed — the worker raises on "failed".
    echo "record_write=${RECORD_WRITE}"
}

main "$@"
