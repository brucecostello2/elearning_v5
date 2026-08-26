#!/usr/bin/env bash
# =============================================================================
# IVGS v5 — WAL Archive Script
# =============================================================================
# Spec reference: §14.1 Table 14-1 — Backup Schedule (Row 2: WAL archiving)
#
# Type:      Continuous WAL archiving
# Method:    PostgreSQL WAL archive to NAS
# Target:    /mnt/backup/ivgs/wal/
# Retention: 7 days
#
# Called by PostgreSQL archive_command:
#   archive_command = '/opt/ivgs/scripts/wal_archive.sh %p %f'
#
# Parameters:
#   $1 = %p — full path to the WAL file to archive
#   $2 = %f — filename of the WAL file
#
# Exit codes:
#   0 — Success (WAL archived and verified)
#   1 — Failure (PostgreSQL will retry)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly WAL_SOURCE_PATH="${1:?Usage: $0 <wal_path> <wal_filename>}"
readonly WAL_FILENAME="${2:?Usage: $0 <wal_path> <wal_filename>}"
readonly WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/mnt/backup/ivgs/wal}"
# WP-58 Task 2. THE PACKAGE'S PREMISE WAS THAT wal_archive.sh IMPLEMENTS NO
# RETENTION. It does - cleanup_old_wal() below has pruned since it was written.
# What was broken is subtler and is the same defect as Task 1: the prune reads
# WAL_RETENTION_DAYS, while ivgs-infra/.env sets BACKUP_RETENTION_WAL_DAYS, which
# nothing anywhere reads. The value that actually governs was a hardcoded literal
# `WAL_RETENTION_DAYS: 7` in docker-compose.override.node01.yml, in TWO services.
# So there were two names for one setting: one configured and inert, one read and
# not configurable.
#
# BACKUP_RETENTION_WAL_DAYS is now primary, matching the other three classes.
# WAL_RETENTION_DAYS stays as a fallback because postgres' archive_command runs
# this script with the container environment, and that variable is still set
# there; the compose files now interpolate it from the same .env value so the two
# cannot drift.
readonly WAL_RETENTION_DAYS="${BACKUP_RETENTION_WAL_DAYS:-${WAL_RETENTION_DAYS:-7}}"
readonly LOG_FILE="/var/log/ivgs/wal_archive.log"
readonly LOG_DIR="/var/log/ivgs"

readonly DEST_PATH="${WAL_ARCHIVE_DIR}/${WAL_FILENAME}"

# WP-59 Task 9 (WP-57 D-3). THIS SCRIPT IS THE SECOND WRITER THAT WAS CAUGHT.
# postgres' /mnt/wal-archive bind captured the local ext4 inode before the NFS
# mount existed and this script archived segments 5B..D0 -- 1.9 GB -- into the
# shadowed tree, with `archive_wal`'s own `mkdir -p` creating the directory it
# then wrote into. The archive looked continuous from inside the container and
# had a 1.9 GB hole from the NAS's point of view. See scripts/lib/nfs_guard.sh.
#
# shellcheck source=lib/nfs_guard.sh
. "$(dirname "$0")/lib/nfs_guard.sh"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_entry() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    mkdir -p "${LOG_DIR}"
    echo "{\"timestamp\":\"${timestamp}\",\"level\":\"${level}\",\"service\":\"wal-archive\",\"wal_file\":\"${WAL_FILENAME}\",\"message\":\"${message}\"}" >> "${LOG_FILE}"
}

# ---------------------------------------------------------------------------
# Archive WAL segment
# ---------------------------------------------------------------------------
archive_wal() {
    # PRE-FLIGHT BEFORE THE mkdir, not after it. The order is the whole point:
    # `mkdir -p` on a path whose NFS mount is absent CREATES the shadowed local
    # directory, and every subsequent segment lands in it. Asserting first means
    # a missing or non-NFS destination can never be brought into existence by
    # this script.
    #
    # Exit 1 is what PostgreSQL's archive_command needs: it treats non-zero as
    # "not archived", keeps the segment in pg_wal, and retries. So refusing here
    # does NOT lose WAL -- it holds it on the primary until the destination is
    # real again, which is strictly better than writing it somewhere that is not
    # the archive. The pg_wal directory grows meanwhile, which is the visible,
    # recoverable pressure the operator should see rather than a silent split.
    if ! assert_nfs_destination "${WAL_ARCHIVE_DIR}" "WAL archive"; then
        log_entry "ERROR" "WAL archive destination is not an NFS mount: ${WAL_ARCHIVE_DIR} — refusing (segment stays in pg_wal and PostgreSQL will retry)"
        return 1
    fi

    # Safe now: the parent is proven to be the NAS.
    mkdir -p "${WAL_ARCHIVE_DIR}"

    # Check if WAL file already archived (idempotency)
    if [ -f "${DEST_PATH}" ]; then
        local src_checksum
        src_checksum="$(sha256sum "${WAL_SOURCE_PATH}" | awk '{print $1}')"
        local dst_checksum
        dst_checksum="$(sha256sum "${DEST_PATH}" | awk '{print $1}')"

        if [ "${src_checksum}" = "${dst_checksum}" ]; then
            log_entry "INFO" "WAL already archived (identical checksum)"
            return 0
        else
            log_entry "WARN" "WAL exists but checksum differs — overwriting"
        fi
    fi

    # Copy WAL file to archive with sync
    cp --force --preserve=timestamps "${WAL_SOURCE_PATH}" "${DEST_PATH}.tmp"
    sync "${DEST_PATH}.tmp"
    mv "${DEST_PATH}.tmp" "${DEST_PATH}"

    # Verify copy integrity
    local src_checksum
    src_checksum="$(sha256sum "${WAL_SOURCE_PATH}" | awk '{print $1}')"
    local dst_checksum
    dst_checksum="$(sha256sum "${DEST_PATH}" | awk '{print $1}')"

    if [ "${src_checksum}" != "${dst_checksum}" ]; then
        log_entry "ERROR" "Checksum mismatch after copy: src=${src_checksum} dst=${dst_checksum}"
        rm -f "${DEST_PATH}"
        return 1
    fi

    log_entry "INFO" "WAL archived successfully (${src_checksum})"
}

# ---------------------------------------------------------------------------
# Retention cleanup (7 days)
# ---------------------------------------------------------------------------
cleanup_old_wal() {
    # Guarded too. A prune that runs against a shadowed local tree deletes the
    # wrong files while reporting a retention pass on the archive.
    if ! assert_nfs_destination "${WAL_ARCHIVE_DIR}" "WAL archive (retention)"; then
        log_entry "ERROR" "Skipping WAL retention: ${WAL_ARCHIVE_DIR} is not an NFS mount"
        return 0
    fi

    local deleted=0
    while IFS= read -r -d '' old_file; do
        rm -f "${old_file}"
        ((deleted++)) || true
    done < <(find "${WAL_ARCHIVE_DIR}" -maxdepth 1 -type f -mtime "+${WAL_RETENTION_DAYS}" -print0 2>/dev/null)

    if [ "${deleted}" -gt 0 ]; then
        log_entry "INFO" "Cleaned up ${deleted} WAL files older than ${WAL_RETENTION_DAYS} days"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    archive_wal
    cleanup_old_wal
}

main
